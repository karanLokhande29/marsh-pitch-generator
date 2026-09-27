# Marsh AI Pitch Generator (NMIMS 2026 case study)

**Live app:** https://marsh-pitch-generator.streamlit.app (no API key needed)  
**Code:** https://github.com/karanLokhande29/marsh-pitch-generator

A Streamlit app that turns a **client company name** + **insurer policy brochures** into a 5-slide PowerPoint pitch,
then **audits every claim** against the source documents before the advisor can approve it.

## Run it
```bash
cd 1_Working_Application
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # paste your free Groq key (console.groq.com); optional
streamlit run app.py
```
Without a Groq key the app still works in **template mode** (verified clause wording, rule-based profile, deterministic audit).

Command line (sample deliverables): `python make_sample.py "Infosys"` → files in `outputs/`.
Tests: `python -m pytest -q tests` · audit evaluation: `python tests/test_audit_planted_errors.py [--llm]`.

## Case-study objectives → code
| Objective | Where |
|---|---|
| 1.1 UI: company name, select/upload policies, Generate | `app.py` (form) |
| 1.2 `generateCompanyProfile(company_name)` | `pitchgen/profile.py` – Wikipedia + Groq; every field tagged *sourced* / *assumption* |
| 1.3 `generateMarketingPitch()` 3–5 slides | `pitchgen/pitch.py` (content + scoring), `pitchgen/deck.py` (PPTX) |
| 1.4 validation & error handling | `app.py`, `profile.validate_company_name`, `pitch.validate_docs`, `kb.load_uploaded`, LLM retries/fallback in `llm.py` |
| 2.1 claim → clause traceability, flags, score | `pitchgen/audit.py` |
| 2.2 `auditPitchContent(pitch_slides, policy_docs)` + approve/edit/reject | `pitchgen/audit.py`, Audit & Approve tabs in `app.py` |

## Layout
```
pitchgen/data/clauses.json         curated clause store (IDs like HDFC-p11-ROOMRENT, page-referenced)
pitchgen/data/benefit_matrix.json  policy x feature matrix + exposure taxonomy (drives the fit score)
pitchgen/{profile,pitch,audit,deck,kb,retrieval,numbers,llm,report}.py
tests/test_kb_integrity.py         every figure in the clause store exists on the cited PDF page
tests/test_audit_planted_errors.py 8 planted hallucinations -> detection rate
outputs/                           sample deck, audit report (xlsx/json), audit evaluation
```
