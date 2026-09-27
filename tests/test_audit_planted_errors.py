"""Plant realistic hallucinations into a clean pitch and measure how many the audit catches."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pitchgen import config, kb  # noqa: E402
from pitchgen.audit import auditPitchContent  # noqa: E402
from pitchgen.pitch import generateMarketingPitch  # noqa: E402

PLANTED = [
    ("Exclusion stated as benefit", "HDFC ERGO Optima Secure+ covers maternity expenses as a standard benefit.", "HDFC"),
    ("Condition dropped", "Care Supreme covers road ambulance up to 100% of sum insured.", "CARE"),
    ("Wrong figure", "Optima Secure+ covers 60 days pre- and 90 days post-hospitalisation.", "HDFC"),
    ("Wrong insurer", "Niva Bupa ReAssure 2.0 grows the sum insured to 6X base by year 6 via Super Credit.", "NIVA"),
    ("Optional shown as standard", "Care Supreme includes Claim Shield covering 68 listed non-payable items.", "CARE"),
    ("Plan-specific shown as general", "Activ One provides global cover for emergency and planned treatment abroad.", "ABHI"),
    ("Fabricated benefit", "Optima Secure+ gives every employee a free annual gym membership and dental cover.", "HDFC"),
    ("Wrong limit", "Niva Bupa ReAssure 2.0 covers air ambulance up to INR 5,00,000 per hospitalisation.", "NIVA"),
]

PROFILE = {"company_name": "TestCo", "fields": {k: {"value": "x", "basis": "sourced"} for k in
           ("industry", "headquarters", "employees", "revenue", "operations", "workforce_profile")},
           "key_risks": [{"exposure": e, "severity": "high", "rationale": "", "basis": "assumption",
                          "label": kb.load_matrix()["exposures"][e]["label"]}
                         for e in ("high_treatment_costs", "lifestyle_chronic", "repeat_claims", "out_of_pocket")]}


def run(use_llm=False):
    docs = kb.bundled_policies()
    pitch = generateMarketingPitch(PROFILE, docs, use_llm=False)
    clean = auditPitchContent(pitch["slides"], docs, use_llm=use_llm)
    slides = copy.deepcopy(pitch["slides"])
    for i, (_, text, doc) in enumerate(PLANTED, start=1):
        slides[4]["items"].append({"id": f"PLANT{i}", "text": text, "kind": "policy", "doc_id": doc, "clause_ids": []})
    rep = auditPitchContent(slides, docs, use_llm=use_llm)
    by_id = {c["claim_id"]: c for c in rep["claims"]}
    rows = []
    for i, (cat, text, _) in enumerate(PLANTED, start=1):
        c = by_id[f"PLANT{i}"]
        rows.append((cat, text, c["verdict"], ", ".join(c["flags"]) or "-", c["verdict"] != "SUPPORTED"))
    return clean, rep, rows


def test_planted_errors_detected():
    _, rep, rows = run(use_llm=False)
    assert all(r[4] for r in rows), [r for r in rows if not r[4]]
    assert rep["summary"]["status"] == "FAIL"


if __name__ == "__main__":
    from pitchgen import llm
    use_llm = "--llm" in sys.argv and llm.is_available()
    clean, rep, rows = run(use_llm)
    caught = sum(r[4] for r in rows)
    md = [f"# Audit evaluation - planted hallucinations ({'LLM + deterministic' if use_llm else 'deterministic + lexical'} mode)\n",
          f"Clean deck: **{clean['summary']['status']}** (score {clean['summary']['confidence_score']}, "
          f"{clean['summary']['supported']}/{clean['summary']['policy_claims_scored']} policy claims supported, 0 false alarms expected)\n",
          f"Deck with {len(rows)} planted errors: **{rep['summary']['status']}** (score {rep['summary']['confidence_score']})\n",
          f"**Detection rate: {caught}/{len(rows)}**\n",
          "| # | Error type | Planted claim | Verdict | Flags | Caught |", "|---|---|---|---|---|---|"]
    for i, (cat, text, v, f, ok) in enumerate(rows, start=1):
        md.append(f"| {i} | {cat} | {text} | {v} | {f} | {'Yes' if ok else 'No'} |")
    out = config.OUTPUT_DIR / "audit_evaluation.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))
