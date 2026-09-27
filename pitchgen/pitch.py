"""generateMarketingPitch: transparent policy scoring + grounded slide content (every policy claim cites clauses)."""
import json
from datetime import datetime

from . import kb, llm

SEV_W = {"high": 3, "medium": 2, "low": 1}
STATUS_TXT = {"included": "Included", "plan_specific": "Plan-specific", "optional": "Optional add-on",
              "not_mentioned": "Not stated"}


def validate_docs(policy_docs: list[dict]) -> list[dict]:
    if not policy_docs:
        raise ValueError("Please select or upload at least one policy document.")
    return policy_docs


# ---------------------------------------------------------------- scoring
def score_policies(profile: dict, docs: list[dict]) -> list[dict]:
    """Weighted fit score: sum over exposures (severity) x features (weight) x cover status."""
    m = kb.load_matrix()
    ss = m["status_score"]
    results = []
    for d in docs:
        if d["doc_id"] not in next(iter(m["features"].values())):
            results.append({"doc_id": d["doc_id"], "label": kb.doc_label(d), "score": None, "breakdown": {},
                            "note": "Not in verified benefit matrix - excluded from scoring"})
            continue
        total, maxi, breakdown = 0.0, 0.0, {}
        for r in profile["key_risks"]:
            ex = m["exposures"][r["exposure"]]
            w = SEV_W[r["severity"]]
            got = sum(fw * ss[m["features"][f][d["doc_id"]]["status"]] for f, fw in ex["features"].items())
            best = sum(ex["features"].values())
            breakdown[r["exposure"]] = round(100 * got / best)
            total += w * got
            maxi += w * best
        results.append({"doc_id": d["doc_id"], "label": kb.doc_label(d),
                        "score": round(100 * total / maxi, 1) if maxi else 0, "breakdown": breakdown})
    return sorted(results, key=lambda x: -(x["score"] or -1))


def _best_feature(exposure: str, doc_id: str, used: set | None = None) -> tuple[str, dict] | None:
    """Best-covering feature for an exposure; prefers clauses not already used on the slide."""
    m = kb.load_matrix()
    ss = m["status_score"]
    feats = m["exposures"][exposure]["features"]
    ranked = sorted(feats, key=lambda f: -feats[f] * ss[m["features"][f][doc_id]["status"]])
    ranked = [f for f in ranked if m["features"][f][doc_id]["status"] != "not_mentioned"]
    fresh = [f for f in ranked if m["features"][f][doc_id]["clauses"][0] not in (used or set())]
    f = (fresh or ranked or [None])[0]
    return (f, m["features"][f][doc_id]) if f else None


# ---------------------------------------------------------------- content
def _fmt_field(f: dict) -> str:
    return f["value"] + (" (assumption)" if f["basis"] == "assumption" else "")


def _build_skeleton(profile: dict, docs: list[dict], scores: list[dict]) -> dict:
    """Deterministic, fully-grounded slide content. The LLM (if available) only rewrites wording."""
    idx = kb.clause_index(docs)
    m = kb.load_matrix()
    scored = [s for s in scores if s["score"] is not None]
    rec_id = scored[0]["doc_id"] if scored else docs[0]["doc_id"]
    rec = next(d for d in docs if d["doc_id"] == rec_id)
    company = profile["company_name"]
    F = profile["fields"]

    s1 = {"no": 1, "type": "overview", "title": f"{company}: Company Overview & Health-Risk Profile",
          "summary": profile.get("summary", ""),
          "items": [
              {"text": f"Industry: {_fmt_field(F['industry'])}", "kind": "company", "basis": F["industry"]["basis"]},
              {"text": f"Headquarters: {_fmt_field(F['headquarters'])}", "kind": "company", "basis": F["headquarters"]["basis"]},
              {"text": f"Employees: {_fmt_field(F['employees'])}", "kind": "company", "basis": F["employees"]["basis"]},
              {"text": f"Workforce: {_fmt_field(F['workforce_profile'])}", "kind": "company", "basis": F["workforce_profile"]["basis"]},
          ],
          "exposures": [{"label": r["label"], "severity": r["severity"], "rationale": r["rationale"],
                         "basis": r["basis"]} for r in profile["key_risks"]]}

    s2 = {"no": 2, "type": "why_marsh", "title": "Why Choose Marsh",
          "items": [
              {"text": f"Independent comparison of {len(docs)} insurer product{'s' if len(docs) != 1 else ''} against {company}'s specific health exposures - not a single-insurer sales pitch.", "kind": "marsh"},
              {"text": "Transparent, weighted fit-scoring: every recommendation can be traced back to the exposure it addresses.", "kind": "marsh"},
              {"text": "Every coverage claim in this deck is traced to a clause in the insurer's own documentation and independently audited before it reaches you.", "kind": "marsh"},
              {"text": "Ongoing advisory support on plan design, add-on selection, employee communication, claims and renewals.", "kind": "marsh"},
          ]}

    rows, used = [], set()
    for r in profile["key_risks"]:
        hit = _best_feature(r["exposure"], rec_id, used)
        doc_for_row = rec_id
        if hit is None:  # recommended policy is silent -> show the best alternative, honestly labelled
            for s in scored[1:]:
                hit = _best_feature(r["exposure"], s["doc_id"], used)
                if hit:
                    doc_for_row = s["doc_id"]
                    break
        if hit is None:
            rows.append({"exposure": r["label"], "severity": r["severity"], "doc_id": None, "clause_ids": [],
                         "text": "Not addressed by the selected policy documents - advisor to discuss.", "kind": "gap"})
            continue
        f, cell = hit
        cid = cell["clauses"][0]
        used.add(cid)
        c = idx[cid]
        d = next(x for x in docs if x["doc_id"] == doc_for_row)
        prefix = "" if doc_for_row == rec_id else f"[Alternative: {d['product']}] "
        rows.append({"exposure": r["label"], "severity": r["severity"], "doc_id": doc_for_row,
                     "clause_ids": [cid], "feature": m["features"][f]["label"],
                     "text": prefix + f"{d['product']}: {c['pitch']}", "kind": "policy"})
    s3 = {"no": 3, "type": "exposure_map", "title": f"{company}'s Exposures Mapped to Policy Benefits", "rows": rows}

    feats = []
    for r in profile["key_risks"]:
        for f in m["exposures"][r["exposure"]]["features"]:
            if f not in feats:
                feats.append(f)
    feats = feats[:8]
    cols = [s["doc_id"] for s in scored][:4]
    s4 = {"no": 4, "type": "comparison", "title": "Policy Comparison & Fit Score", "columns": cols,
          "column_labels": {c: next(d["product"] for d in docs if d["doc_id"] == c) for c in cols},
          "rows": [{"feature": m["features"][f]["label"], "feature_key": f,
                    "cells": {c: m["features"][f][c] for c in cols}} for f in feats],
          "scores": {s["doc_id"]: s["score"] for s in scored}}

    # recommendation: strongest base features of the recommended product for the exposures
    rec_items, seen = [], set()
    for r in profile["key_risks"]:
        for f in sorted(m["exposures"][r["exposure"]]["features"],
                        key=lambda f: -m["exposures"][r["exposure"]]["features"][f]):
            cell = m["features"][f].get(rec_id, {})
            if cell.get("status") in ("included", "plan_specific") and cell["clauses"][0] not in seen:
                seen.add(cell["clauses"][0])
                rec_items.append({"text": idx[cell["clauses"][0]]["pitch"], "kind": "policy",
                                  "doc_id": rec_id, "clause_ids": [cell["clauses"][0]]})
                break
    # add the product's strongest headline benefits (standard cover only) so the recommendation sells its real strengths
    for f in ("day1_extra_cover", "unlimited_restore", "cover_growth", "non_medical_items", "chronic_day1",
              "no_room_rent_cap", "wellness_rewards", "cashless_network"):
        if len(rec_items) >= 6:
            break
        cell = m["features"][f].get(rec_id, {})
        if cell.get("status") == "included" and cell["clauses"][0] not in seen:
            seen.add(cell["clauses"][0])
            rec_items.append({"text": idx[cell["clauses"][0]]["pitch"], "kind": "policy",
                              "doc_id": rec_id, "clause_ids": [cell["clauses"][0]]})
    weak = {"HDFC-p10-OPTIONS", "CARE-p2-ELIGIBILITY", "NIVA-p2-SI", "ABHI-p2-MORE"}
    rec_items = ([it for it in rec_items if it["clause_ids"][0] not in weak] or rec_items)[:5]
    cons = []
    for c in rec["clauses"]:
        if (c["type"] == "base" and "WAITING" in c["id"]) or "DISCLAIMER" in c["id"]:
            cons.append({"text": c["pitch"], "kind": "policy", "doc_id": rec_id, "clause_ids": [c["id"]]})
    opt = [m["features"][f][rec_id] for f in feats if m["features"][f][rec_id]["status"] == "optional"]
    if opt:
        cid = opt[0]["clauses"][0]
        cons.append({"text": "Consider add-on: " + idx[cid]["pitch"], "kind": "policy", "doc_id": rec_id,
                     "clause_ids": [cid]})
    s5 = {"no": 5, "type": "recommendation",
          "title": f"Recommendation: {rec['insurer']} {rec['product']}",
          "fit_score": scores[0]["score"] if scores else None,
          "items": rec_items, "considerations": cons[:2],
          "next_steps": [{"text": "These are individual / family-floater products: agree with the insurer how they are offered to employees (employer-paid or voluntary top-up).", "kind": "action"},
                         {"text": "Confirm employee census (ages, dependants, locations) to obtain premium quotes.", "kind": "action"},
                         {"text": "Validate final terms against the full policy wording before placement.", "kind": "action"}]}
    if len(scored) > 1 and scored[0]["score"] - scored[1]["score"] < 5:
        s5["next_steps"].insert(0, {"text": f"Close fit: {scored[1]['label']} scores {scored[1]['score']:.1f} vs "
                                            f"{scored[0]['score']:.1f} - obtain quotes for both before deciding.",
                                    "kind": "action"})
    return {"slides": [s1, s2, s3, s4, s5], "recommended": {"doc_id": rec_id, "label": kb.doc_label(rec)}}


_SYS = """You are a Marsh client advisor writing concise pitch-deck bullets for Indian employee health insurance.
STRICT RULES: rewrite each bullet to be client-friendly and tailored to the company, but
(1) keep EVERY number, limit, and qualifier exactly (e.g. 'optional', 'add-on', 'VIP+ plan', 'for SI of INR 15 lakh and above');
(2) do not add any benefit, figure, or fact that is not in the given clause text;
(3) keep the product name in the bullet; max 30 words each;
(4) you are the broker, not the insurer: never use 'our', 'we' or 'us' for insurer features (say 'the insurer's network').
Respond with JSON only."""


def _llm_polish(pitch: dict, profile: dict, docs: list[dict]) -> str | None:
    """Rewrite policy bullets for tone; returns a warning string if polishing failed."""
    idx = kb.clause_index(docs)
    items = []
    for s in pitch["slides"]:
        for key in ("rows", "items", "considerations"):
            for i, it in enumerate(s.get(key, []) if not (key == "rows" and s["type"] == "comparison") else []):
                if it.get("kind") == "policy":
                    items.append({"ref": f"{s['no']}|{key}|{i}", "bullet": it["text"],
                                  "clause_text": " ".join(idx[c]["text"] for c in it["clause_ids"]),
                                  "exposure": it.get("exposure", "")})
    user = (f"Company: {profile['company_name']} ({profile['fields']['industry']['value']}).\n"
            f"Rewrite these bullets. Return {{\"bullets\": [{{\"ref\": str, \"text\": str}}]}}.\n"
            + json.dumps(items, indent=1))
    try:
        out = llm.chat_json(_SYS, user, temperature=0.3, max_tokens=3000)
    except llm.LLMError as e:
        return f"LLM wording step skipped ({e}); using verified template wording."
    by_ref = {b.get("ref"): b.get("text") for b in out.get("bullets", []) if isinstance(b, dict)}
    for s in pitch["slides"]:
        for key in ("rows", "items", "considerations"):
            for i, it in enumerate(s.get(key, [])):
                t = by_ref.get(f"{s['no']}|{key}|{i}")
                if t and it.get("kind") == "policy":
                    it["template_text"] = it["text"]
                    it["text"] = t.strip()
    pitch["model"] = out.get("_model")
    return None


def generateMarketingPitch(profile: dict, policy_docs: list[dict], use_llm: bool = True) -> dict:
    """Produce a 5-slide pitch (overview, why Marsh, exposure map, comparison, recommendation)."""
    docs = validate_docs(policy_docs)
    if not profile or not profile.get("key_risks"):
        raise ValueError("Company profile is missing - run generateCompanyProfile first.")
    scores = score_policies(profile, docs)
    pitch = _build_skeleton(profile, docs, scores)
    pitch.update({"company": profile["company_name"], "scores": scores, "mode": "template",
                  "policy_docs": [d["doc_id"] for d in docs],
                  "generated_at": datetime.now().isoformat(timespec="seconds"), "warnings": []})
    if use_llm and llm.is_available():
        warn = _llm_polish(pitch, profile, docs)
        if warn:
            pitch["warnings"].append(warn)
        else:
            pitch["mode"] = "llm"
    # stable claim ids
    for s in pitch["slides"]:
        for key in ("items", "rows", "considerations", "next_steps"):
            if key == "rows" and s["type"] == "comparison":
                continue
            for i, it in enumerate(s.get(key, []), start=1):
                it["id"] = f"S{s['no']}-{key[:3].upper()}{i}"
    return pitch
