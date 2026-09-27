"""Generate the sample deliverables (deck + audit report) for a company from the command line.

Usage: python make_sample.py "Infosys" [--no-llm]
"""
import json
import re
import sys

from pitchgen import auditPitchContent, config, generateCompanyProfile, generateMarketingPitch, kb, llm
from pitchgen.deck import build_deck
from pitchgen.report import export_audit

company = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "Infosys"
use_llm = "--no-llm" not in sys.argv
docs = kb.bundled_policies()
print(f"LLM available: {llm.is_available() and use_llm}")
profile = generateCompanyProfile(company, use_llm=use_llm)
pitch = generateMarketingPitch(profile, docs, use_llm=use_llm)
pitch["profile_sources"] = profile["sources"]
audit = auditPitchContent(pitch["slides"], docs, use_llm=use_llm)
slug = re.sub(r"\W+", "_", company).strip("_")
deck = build_deck(pitch, config.OUTPUT_DIR / f"{slug}_Pitch_Deck.pptx", audit["summary"])
export_audit(audit, config.OUTPUT_DIR / f"{slug}_Audit_Report.xlsx", config.OUTPUT_DIR / f"{slug}_Audit_Report.json")
(config.OUTPUT_DIR / f"{slug}_pitch.json").write_text(json.dumps(
    {"profile": {k: v for k, v in profile.items() if k != "source_text"}, "pitch": pitch}, indent=2))
print("Recommended:", pitch["recommended"]["label"], "| mode:", pitch["mode"], profile["mode"])
print("Audit:", audit["summary"])
print("Warnings:", profile.get("warning"), pitch["warnings"], audit["warnings"])
print("Saved:", deck)
