"""Generate the Word write-up (approach, tools, design decisions)."""
import json

from docx import Document
from docx.shared import Pt, RGBColor

from pitchgen import config

a = json.loads((config.OUTPUT_DIR / "Infosys_Audit_Report.json").read_text())
p = json.loads((config.OUTPUT_DIR / "Infosys_pitch.json").read_text())["pitch"]
a2 = json.loads((config.OUTPUT_DIR / "Tata_Steel_Audit_Report.json").read_text())
p2 = json.loads((config.OUTPUT_DIR / "Tata_Steel_pitch.json").read_text())
prof = json.loads((config.OUTPUT_DIR / "Infosys_pitch.json").read_text())["profile"]
ev = (config.OUTPUT_DIR / "audit_evaluation.md").read_text().splitlines()
S = a["summary"]

doc = Document()
st = doc.styles["Normal"]
st.font.name, st.font.size = "Calibri", Pt(10.5)


def h(t, lvl=1):
    x = doc.add_heading(t, lvl)
    for r in x.runs:
        r.font.color.rgb = RGBColor(0x00, 0x1E, 0x5A)


def b(t, bold_lead=None):
    para = doc.add_paragraph(style="List Bullet")
    if bold_lead:
        para.add_run(bold_lead).bold = True
    para.add_run(t)


h("Marsh AI Pitch Generator & Audit Layer - Solution Write-up", 0)
doc.add_paragraph("NMIMS 2026 Internship Case Study - India Knowledge Services, Data Science Team")
doc.add_paragraph("Live application: https://marsh-pitch-generator.streamlit.app (no API key needed)\nSource code: https://github.com/karanLokhande29/marsh-pitch-generator")

h("1. Problem and approach")
doc.add_paragraph(
    "Advisors need a client-specific pitch in minutes, but every coverage statement must be traceable to the "
    "insurer's documents. The solution therefore separates three concerns: (1) a verified knowledge base built "
    "from the four brochures, (2) a generator that can only speak from that knowledge base, and (3) an "
    "independent auditor that re-checks every statement before an advisor may approve the deck.")
b(" Streamlit screen - company name, select bundled / upload PDFs, Generate; tabs for profile, slide preview, audit, sign-off.", "UI (1.1):")
b(" Wikipedia search + infobox parsing, structured by the LLM into industry, HQ, employees, workforce and 4-5 "
  "health exposures chosen from a fixed taxonomy. Every field is tagged 'sourced' or 'assumption'; figures the "
  "LLM claims are 'sourced' but that do not appear in the source text are automatically downgraded to assumption.",
  "generateCompanyProfile (1.2):")
b(" 5 slides - company overview & risk profile, why Marsh, exposure-to-benefit map, policy comparison with fit "
  "score, and one recommended policy with considerations and next steps. Rendered with python-pptx.",
  "generateMarketingPitch (1.3):")
b(" empty/invalid company name, no documents, unreadable or scanned PDFs, company not found (assumption "
  "fallback), LLM timeouts / rate limits (retries, fallback model, then verified template wording).",
  "Validation & errors (1.4):")
b(" traces each claim to a clause, flags untraceable statements, outputs a confidence score and PASS / REVIEW / "
  "FAIL, plus an Excel/JSON traceability report.", "auditPitchContent (2.1 / 2.2):")

h("2. Key design decisions")
b(" The four brochures were transcribed into ~70 clauses with stable IDs (e.g. HDFC-p11-ROOMRENT), page numbers "
  "and a type: base, optional add-on, plan-specific, exclusion or info. Automatic extraction was unreliable "
  "(ABHI's two-column layout scrambles text; Niva Bupa page 1 is an image). An automated test confirms every "
  "figure in the clause store appears on the cited PDF page. Uploaded, unknown PDFs are auto-chunked by page.",
  "Curated, test-verified knowledge base.")
b(" The recommended policy is chosen by a transparent score, not by the LLM: for each exposure, "
  "severity weight x feature weight x cover status (Included 1.0, Plan-specific 0.6, Optional 0.5, Not stated 0). "
  f"For Infosys: " + ", ".join(f"{s['label']} {s['score']}" for s in p["scores"]) + ".",
  "Deterministic recommendation.")
b(" Slide content is assembled from verified clause text first; the LLM (Groq, openai/gpt-oss-120b) only rewrites "
  "wording and is instructed to keep every number and qualifier. The audit then checks the rewritten text, so an "
  "LLM that drifts is caught rather than trusted.", "Grounded generation, LLM for tone only.")
b(" The biggest real-world risks are subtle: presenting a paid add-on as standard (many Care Supreme headline "
  "benefits are add-ons), dropping a sum-insured condition (Care road ambulance), stating an exclusion as a "
  "benefit (maternity is a standard exclusion in HDFC Optima Secure+) or attributing a feature to the wrong "
  "insurer. The auditor has a specific check for each.", "Targeting realistic hallucinations.")
b(" All four products are retail / family-floater plans. The pitch positions them as employee and family health "
  "benefits rather than inventing group-policy terms. 'Why Marsh' statements cannot be traced to insurer "
  "documents, so they are marked OUT_OF_SCOPE (advisor to verify) and excluded from the score.",
  "Honest scope.")

h("3. Audit layer - how a claim is checked")
for t in ["Evidence: cited clause(s) plus BM25 retrieval restricted to the insurer named in the claim.",
          "Figures (deterministic): every amount, %, day count and multiplier must appear in the primary clause "
          "(lakh/crore and INR formats normalised). A mismatch forces FAIL.",
          "Qualifiers (deterministic, from clause types): optional add-ons must be disclosed as optional; "
          "plan-specific benefits must name the plan; conditional clauses must state the condition; a claim "
          "matching an exclusion clause is CONTRADICTED.",
          "Meaning: an LLM judge returns SUPPORTED / PARTIAL / UNSUPPORTED / CONTRADICTED with reason and suggested "
          "fix (word-overlap heuristic when the LLM is unavailable). The final verdict is the most severe of all checks.",
          f"Score: SUPPORTED 1, PARTIAL 0.5, else 0, over policy claims. PASS if score >= {config.PASS_SCORE:.0f}% "
          "and nothing unsupported; FAIL on any contradiction or wrong figure; otherwise REVIEW."]:
    b(" " + t)
h("Advisor workflow (approve / edit / reject)", 2)
doc.add_paragraph(
    "The Audit tab lists every flagged claim with its verdict, source clause and page, reason and suggested fix. "
    "For each row the advisor chooses Accept (keeps it, recorded as an explicit override), Edit (types corrected "
    "text) or Reject (removes it from the deck), then clicks 'Apply & re-audit' - the deck is re-audited and "
    "re-rendered. The Approve button is locked unless the audit is PASS, or REVIEW with every flagged claim "
    "explicitly accepted; FAIL must be fixed or the pitch rejected. The decision (name, time, comment, score) is "
    "written into the exported audit report, and the client-ready PPTX download unlocks only after approval.")

h("4. Results")
b(f" exposures identified - " + ", ".join(r["label"].lower() for r in prof["key_risks"]) +
  f". Recommended {p['recommended']['label']}; audit {S['status']} with confidence {S['confidence_score']}% - "
  f"{S['supported']}/{S['policy_claims_scored']} policy claims supported, {S['out_of_scope']} non-policy statements "
  f"flagged for advisor verification, {S['assumptions_flagged']} company-profile assumption(s) labelled.",
  "Sample deck 1 - Infosys (IT services):")
S2 = a2["summary"]
b(" exposures identified - " + ", ".join(r["label"].lower() for r in p2["profile"]["key_risks"]) +
  f". Recommended {p2['pitch']['recommended']['label']}; audit {S2['status']} ({S2['confidence_score']}%, "
  f"{S2['supported']}/{S2['policy_claims_scored']} supported). " +
  ("The different recommendation shows the pitch is driven by each client's exposures rather than a fixed favourite product."
   if p2['pitch']['recommended']['doc_id'] != p['recommended']['doc_id'] else
   "Both clients score highest on the same product, but for different reasons: the exposure map, comparison rows and "
   "fit scores differ (" + ", ".join(f"{x['label'].split()[0]} {x['score']}" for x in p2['pitch']['scores']) +
   "), showing the pitch is driven by each client's exposures."), "Sample deck 2 - Tata Steel (manufacturing):")
b(" the first Groq-generated Tata Steel draft was flagged FAIL: the figure check read '2.0' in the product name "
  "'ReAssure 2.0' as a benefit figure. This was a false positive, so product names are now stripped before figure "
  "checks. An earlier Infosys draft was flagged PARTIAL where the LLM dropped the 'depends on sum insured' "
  "qualifier from a health check-up amount - a genuine catch of the kind the audit is designed for.",
  "What the audit caught during development:")
det = next((l for l in ev if l.startswith("**Detection")), "")
mode = "with the Groq LLM judge enabled" if "LLM" in ev[0] else "in deterministic mode"
b(f" 8 realistic errors planted into a clean deck (exclusion as benefit, dropped condition, wrong figure, wrong "
  f"insurer, optional as standard, plan-specific as general, fabricated benefit, wrong limit), run {mode}. "
  f"{det.strip('*')} (also 8/8 in deterministic-only mode); "
  "the deck status moved to FAIL and the clean deck produced zero false alarms. Full table: outputs/audit_evaluation.md.",
  "Audit evaluation:")

h("5. Tools and libraries")
doc.add_paragraph("Python 3, Streamlit (UI), Groq API - openai/gpt-oss-120b with openai/gpt-oss-20b fallback "
                  "(profile structuring, wording, LLM judge; JSON mode, disk cache to stay within free-tier limits), "
                  "pdfplumber (PDF text), rank_bm25 (retrieval), python-pptx (deck), pandas/openpyxl (audit report), "
                  "python-docx (this write-up), Wikipedia API (company facts), pytest.")

h("6. Limitations and next steps")
for t in ["Brochures are summaries; production should ingest full policy wordings and the product benefit tables.",
          "The LLM judge is not fully deterministic: re-running it can move a borderline claim between PARTIAL and "
          "SUPPORTED. The deterministic checks (figures, add-on, plan and condition disclosure, exclusions) do not vary, "
          "and the advisor sign-off remains the final control.",
          "Uploaded non-bundled PDFs are chunked automatically without clause types, so optional/exclusion checks "
          "are weaker for them; an LLM-assisted clause-typing step with human review would close this gap.",
          "Company data relies on Wikipedia; paid firmographic sources (and the client's census) would sharpen exposures.",
          "Add premium quotes from the census, a Marsh-approved content library for 'Why Marsh', and audit-log storage."]:
    b(" " + t)

out = config.OUTPUT_DIR / "Marsh_Case_Study_Writeup.docx"
doc.save(out)
print(out)
