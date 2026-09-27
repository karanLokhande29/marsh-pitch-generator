"""auditPitchContent: trace every claim to a policy clause, flag untraceable statements, score the deck.

Layers per claim:
  1. Retrieval   - cited clauses + BM25 top-k (restricted to the insurer the claim names).
  2. Figures     - deterministic: every number in the claim must appear in the evidence.
  3. Qualifiers  - deterministic: optional add-ons / plan-specific / conditional clauses must be disclosed;
                   claims matching an exclusion clause are contradictions.
  4. Semantics   - LLM judge (Groq) returns SUPPORTED / PARTIAL / UNSUPPORTED / CONTRADICTED;
                   lexical-overlap heuristic when the LLM is unavailable.
Final verdict = the most severe of the deterministic and semantic verdicts.
"""
import json
import re
from datetime import datetime

from . import config, kb, llm, numbers
from .retrieval import ClauseIndex, tokenize

ORDER = {"SUPPORTED": 0, "PARTIAL": 1, "UNSUPPORTED": 2, "CONTRADICTED": 3}
CREDIT = {"SUPPORTED": 1.0, "PARTIAL": 0.5, "UNSUPPORTED": 0.0, "CONTRADICTED": 0.0}
_DISCLOSE_OPTIONAL = re.compile(r"optional|add-on|addon|rider|additional premium|extra premium|consider", re.I)
_NEGATION = re.compile(r"exclu|not covered|only (?:through|via|under)|not included|add-on", re.I)


_DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
                         "\u00a0": " ", "\u202f": " "})


def _norm(text: str) -> str:
    return (text or "").translate(_DASHES)


def _worse(a: str, b: str) -> str:
    return a if ORDER[a] >= ORDER[b] else b


def _extract_claims(pitch_slides: list[dict]) -> list[dict]:
    claims = []
    for s in pitch_slides:
        for key in ("items", "rows", "considerations"):
            if key == "rows" and s.get("type") == "comparison":
                continue
            for it in s.get(key, []):
                kind = it.get("kind")
                if kind in ("action",):
                    continue
                claims.append({"claim_id": it.get("id"), "slide_no": s["no"], "slide_title": s["title"],
                               "text": _norm(it["text"]), "kind": kind, "doc_id": it.get("doc_id"),
                               "cited": it.get("clause_ids", []), "basis": it.get("basis")})
        if s.get("type") == "comparison":
            for r in s["rows"]:
                for doc_id, cell in r["cells"].items():
                    claims.append({"claim_id": f"S4-{r['feature_key']}-{doc_id}", "slide_no": 4,
                                   "slide_title": s["title"], "kind": "matrix", "doc_id": doc_id,
                                   "text": f"{s['column_labels'][doc_id]} - {r['feature']}: {cell['value']} ({cell['status']})",
                                   "cited": cell.get("clauses", []), "status": cell["status"]})
    return claims


def _mentioned_docs(text: str, docs: list[dict]) -> set:
    t = text.lower()
    return {d["doc_id"] for d in docs
            if any(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", t) for a in d.get("aliases", []))}


def _lexical_verdict(claim: str, evidence: str) -> tuple[str, float]:
    ct = set(tokenize(claim)) - {"inr", "lakh", "benefit", "cover", "covered", "policy"}
    et = set(tokenize(evidence))
    if not ct:
        return "SUPPORTED", 1.0
    overlap = len(ct & et) / len(ct)
    return ("SUPPORTED" if overlap >= 0.6 else "PARTIAL" if overlap >= 0.35 else "UNSUPPORTED"), overlap


_JUDGE_SYS = """You are a strict insurance compliance auditor. For each claim decide, using ONLY the evidence
clauses given, whether the claim is:
SUPPORTED (every fact, figure and qualifier is in the evidence), PARTIAL (core is supported but a figure,
condition or qualifier is missing/overstated), UNSUPPORTED (not in evidence), or CONTRADICTED (evidence says
otherwise, e.g. benefit is excluded or a different figure). Attributing a benefit to the wrong insurer is
UNSUPPORTED. Presenting an optional add-on as standard is PARTIAL. Respond with JSON only:
{"results": [{"claim_id": str, "verdict": str, "best_clause_id": str, "reason": str (<=25 words),
"suggested_fix": str (<=25 words, empty if SUPPORTED)}]}"""


def _llm_judge(batch: list[dict]) -> dict:
    payload = [{"claim_id": c["claim_id"], "claim": c["text"],
                "evidence": [{"clause_id": e["clause_id"], "insurer_product": e["doc"], "type": e["type"],
                              "text": e["text"]} for e in c["evidence"]]} for c in batch]
    out = llm.chat_json(_JUDGE_SYS, json.dumps(payload, indent=1), temperature=0.0, max_tokens=3000)
    return {r.get("claim_id"): r for r in out.get("results", []) if isinstance(r, dict)}


def auditPitchContent(pitch_slides: list[dict], policy_docs: list[dict], use_llm: bool = True,
                      profile: dict | None = None) -> dict:
    """Return a structured audit report tracing each claim to a policy clause."""
    if not policy_docs:
        raise ValueError("No policy documents supplied to audit against.")
    docs_by_id = {d["doc_id"]: d for d in policy_docs}
    cidx = kb.clause_index(policy_docs)
    index = ClauseIndex(kb.all_clauses(policy_docs))
    claims = _extract_claims(pitch_slides)
    product_names = sorted({n for d in policy_docs for n in [d["product"], d["insurer"]] + d.get("aliases", [])},
                           key=len, reverse=True)
    llm_on = use_llm and llm.is_available()
    warnings = []

    to_judge = []
    for c in claims:
        c.update({"flags": [], "evidence": [], "reason": "", "suggested_fix": "", "advisor_action": "pending"})
        if c["kind"] in ("company", "marsh", "gap"):
            c["verdict"] = "OUT_OF_SCOPE"
            c["reason"] = {"company": f"Company fact ({c.get('basis') or 'n/a'}) - not a policy claim; verify against source.",
                           "marsh": "Statement about Marsh, not traceable to policy documents - advisor to verify.",
                           "gap": "Exposure not addressed by selected policies - disclosed as a gap."}[c["kind"]]
            if c["kind"] == "company" and c.get("basis") == "assumption":
                c["flags"].append("ASSUMPTION")
            continue
        if c["kind"] == "matrix" and c.get("status") == "not_mentioned":
            c["verdict"] = "SUPPORTED"
            c["reason"] = "Absence statement ('not stated in brochure'); confirmed when the knowledge base was curated."
            continue

        # 1. evidence: cited clauses first, then retrieval restricted to named / attributed insurer
        named = _mentioned_docs(c["text"], policy_docs)
        scope = named or ({c["doc_id"]} if c.get("doc_id") in docs_by_id else set())
        if c.get("doc_id") and named and c["doc_id"] not in named:
            c["flags"].append("INSURER_MISMATCH")
        ev_clauses = [cidx[x] for x in c["cited"] if x in cidx]
        missing_cites = [x for x in c["cited"] if x not in cidx]
        if missing_cites:
            c["flags"].append("CITATION_NOT_FOUND")
        for cl, _ in index.search(c["text"], scope or None, k=3):
            if cl not in ev_clauses:
                ev_clauses.append(cl)
        if scope:
            wrong = [cl for cl in ev_clauses if cl["doc_id"] not in scope]
            if wrong and c["cited"] and all(cidx[x]["doc_id"] not in scope for x in c["cited"] if x in cidx):
                c["flags"].append("INSURER_MISMATCH")
            ev_clauses = [cl for cl in ev_clauses if cl["doc_id"] in scope] or ev_clauses
        c["evidence"] = [{"clause_id": cl["id"], "doc": kb.doc_label(docs_by_id[cl["doc_id"]]),
                          "page": cl["page"], "section": cl.get("section", ""), "type": cl.get("type", "unknown"),
                          "text": cl["text"]} for cl in ev_clauses[:4]]
        if not c["evidence"]:
            c["verdict"] = "UNSUPPORTED"
            c["reason"] = "No matching clause found in the selected policy documents."
            c["suggested_fix"] = "Remove the statement or cite a supporting clause."
            continue
        ev_text = " ".join(e["text"] for e in c["evidence"])
        # primary clause = cited clause, else the evidence clause with the highest word overlap with the claim
        if not (c["cited"] and c["cited"][0] in cidx):
            names = {t for d in policy_docs for a in d.get("aliases", []) + [d["insurer"], d["product"]] for t in tokenize(a)}
            core = " ".join(t for t in tokenize(c["text"]) if t not in names)
            c["evidence"].sort(key=lambda e: -_lexical_verdict(core, e["text"])[1])
        primary_text = " ".join([c["evidence"][0]["text"]] + [cidx[x]["text"] for x in c["cited"] if x in cidx])

        # 2. figures (strict: must be in the primary / cited clause, not anywhere in the brochure)
        num_text = c["text"].split(":", 1)[-1] if c["kind"] == "matrix" else c["text"]
        for nm in product_names:  # "ReAssure 2.0" is a name, not a figure
            num_text = re.sub(re.escape(nm), " ", num_text, flags=re.I)
        num = numbers.check_claim_numbers(num_text, primary_text)
        c["numeric_check"] = num
        det = "SUPPORTED"
        if not num["passed"]:
            c["flags"].append("NUMBER_MISMATCH")
            det = "UNSUPPORTED"

        # 3. qualifiers (curated clause types)
        primary = c["evidence"][0]
        pcl = cidx.get(primary["clause_id"], {})
        if c["kind"] == "matrix":
            expected = {"optional": "optional", "plan_specific": "plan_specific", "included": None}
            if c["status"] == "included" and pcl.get("type") == "optional":
                c["flags"].append("OPTIONAL_PRESENTED_AS_STANDARD")
                det = _worse(det, "PARTIAL")
            _ = expected
        else:
            if pcl.get("type") == "optional" and not _DISCLOSE_OPTIONAL.search(c["text"]):
                c["flags"].append("OPTIONAL_PRESENTED_AS_STANDARD")
                det = _worse(det, "PARTIAL")
            if pcl.get("type") == "plan_specific" and not any(t in c["text"].lower() for t in pcl.get("condition_terms", [])):
                c["flags"].append("PLAN_CONDITION_OMITTED")
                det = _worse(det, "PARTIAL")
            if pcl.get("condition_terms") and pcl.get("type") != "plan_specific" and \
                    not any(t in c["text"].lower() for t in pcl["condition_terms"]):
                c["flags"].append("CONDITION_OMITTED")
                det = _worse(det, "PARTIAL")
            excl = [e for e in c["evidence"] if e["type"] == "exclusion"]
            if excl and not _NEGATION.search(c["text"]):
                ex_tokens = set(tokenize(excl[0]["text"]))
                hit = [t for t in set(tokenize(c["text"])) & ex_tokens if len(t) > 5]
                if hit:
                    c["flags"].append("CONFLICTS_WITH_EXCLUSION")
                    det = "CONTRADICTED"
                    c["reason"] = f"Matches standard exclusion ({', '.join(hit[:3])})."
        c["det_verdict"] = det

        # 4. semantics
        lex, ov = _lexical_verdict(c["text"], ev_text)
        c["lexical_overlap"] = round(ov, 2)
        if c["kind"] == "matrix":  # structural check only: cited clause, insurer, figures, status/type
            c["verdict"] = det
            if det == "SUPPORTED":
                c["reason"] = "Cell value and status match the cited clause."
        else:
            c["verdict"] = _worse(det, lex) if not llm_on else det
        if llm_on and c["kind"] != "matrix":
            to_judge.append(c)

    if to_judge:
        for i in range(0, len(to_judge), 8):
            batch = to_judge[i:i + 8]
            try:
                res = _llm_judge(batch)
            except llm.LLMError as e:
                warnings.append(f"LLM judge unavailable ({e}); lexical heuristic used.")
                for c in batch:
                    c["verdict"] = _worse(c["det_verdict"], _lexical_verdict(c["text"], " ".join(e["text"] for e in c["evidence"]))[0])
                continue
            for c in batch:
                r = res.get(c["claim_id"])
                if not r or r.get("verdict") not in ORDER:
                    c["verdict"] = _worse(c["det_verdict"], "PARTIAL")
                    c["flags"].append("JUDGE_NO_ANSWER")
                    continue
                c["llm_verdict"] = r["verdict"]
                c["verdict"] = _worse(c["det_verdict"], r["verdict"])
                c["reason"] = c["reason"] or r.get("reason", "")
                c["suggested_fix"] = r.get("suggested_fix", "")
                best = r.get("best_clause_id")
                if best in {e["clause_id"] for e in c["evidence"]}:
                    c["evidence"].sort(key=lambda e: e["clause_id"] != best)

    # reasons / fixes for deterministic findings
    fixes = {"NUMBER_MISMATCH": "Correct the figure(s) to match the cited clause.",
             "OPTIONAL_PRESENTED_AS_STANDARD": "State that this is an optional add-on at extra premium.",
             "PLAN_CONDITION_OMITTED": "State the plan variant this applies to.",
             "CONDITION_OMITTED": "Add the condition from the clause (e.g. sum-insured threshold).",
             "CONFLICTS_WITH_EXCLUSION": "Remove - the benefit is a standard exclusion.",
             "INSURER_MISMATCH": "Attribute the benefit to the correct insurer/product.",
             "CITATION_NOT_FOUND": "Cite a clause from the selected documents."}
    for c in claims:
        if c["verdict"] == "OUT_OF_SCOPE":
            continue
        if not c["reason"]:
            parts = []
            if c.get("numeric_check") and c["numeric_check"]["missing"]:
                parts.append(f"Figure(s) not in source: {', '.join(c['numeric_check']['missing'])}.")
            parts += [f.replace("_", " ").capitalize() + "." for f in c["flags"] if f != "NUMBER_MISMATCH"]
            c["reason"] = " ".join(parts) or ("Claim matches the cited clause." if c["verdict"] == "SUPPORTED"
                                                else "Only partially reflected in the evidence.")
        if not c["suggested_fix"] and c["verdict"] != "SUPPORTED":
            c["suggested_fix"] = " ".join(fixes[f] for f in c["flags"] if f in fixes) or "Review wording against the cited clause."

    for c in claims:
        c["flags"] = list(dict.fromkeys(c["flags"]))
    scored = [c for c in claims if c["verdict"] != "OUT_OF_SCOPE"]
    counts = {v: sum(c["verdict"] == v for c in claims) for v in list(ORDER) + ["OUT_OF_SCOPE"]}
    score = round(100 * sum(CREDIT[c["verdict"]] for c in scored) / len(scored), 1) if scored else 0.0
    hard_fail = counts["CONTRADICTED"] > 0 or any("NUMBER_MISMATCH" in c["flags"] for c in scored)
    if hard_fail:
        status = "FAIL"
    elif score >= config.PASS_SCORE and counts["UNSUPPORTED"] == 0:
        status = "PASS"
    else:
        status = "REVIEW"
    assumptions = [c for c in claims if "ASSUMPTION" in c["flags"]]
    return {
        "summary": {"status": status, "confidence_score": score, "total_claims": len(claims),
                    "policy_claims_scored": len(scored), **{k.lower(): v for k, v in counts.items()},
                    "needs_human_review": sum(c["verdict"] != "SUPPORTED" for c in claims),
                    "assumptions_flagged": len(assumptions),
                    "rule": f"PASS if score >= {config.PASS_SCORE:.0f} and no UNSUPPORTED; FAIL on any CONTRADICTED or figure mismatch; else REVIEW"},
        "claims": claims,
        "method": "llm+deterministic" if llm_on and not warnings else "deterministic+lexical",
        "warnings": warnings,
        "audited_at": datetime.now().isoformat(timespec="seconds"),
        "policy_docs": [kb.doc_label(d) for d in policy_docs],
    }
