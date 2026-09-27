"""Marsh AI Pitch Generator - Streamlit UI.  Run: streamlit run app.py"""
import re
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from pitchgen import auditPitchContent, config, generateCompanyProfile, generateMarketingPitch, kb, llm
from pitchgen.deck import build_deck
from pitchgen.report import audit_rows, export_audit

st.set_page_config(page_title="Marsh AI Pitch Generator", page_icon="📊", layout="wide")
ss = st.session_state

VERDICT_ICON = {"SUPPORTED": "🟢", "PARTIAL": "🟡", "UNSUPPORTED": "🔴", "CONTRADICTED": "⛔", "OUT_OF_SCOPE": "⚪"}
STATUS_COLOR = {"PASS": "green", "REVIEW": "orange", "FAIL": "red"}

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    if config.SERVER_HAS_KEY:
        st.success("Groq LLM connected - no key needed.")
        override = ""
    else:
        override = st.text_input("Groq API key", type="password", value="",
                                 help="Free key from console.groq.com. Leave empty to run in template mode.")
    if override and override != config.GROQ_API_KEY:
        llm.set_api_key(override)
    use_llm = st.toggle("Use LLM (Groq)", value=llm.is_available(), disabled=not llm.is_available())
    st.caption(f"Model: `{config.GROQ_MODEL}` (fallback `{config.GROQ_FALLBACK_MODEL}`)" if use_llm
               else "Template mode: verified wording, rule-based profile & audit.")
    st.divider()
    st.markdown("**How the audit works**\n\n1. Each claim is traced to a policy clause\n2. Figures checked deterministically"
                "\n3. Optional / plan-specific / conditional benefits must be disclosed\n4. LLM judge checks meaning"
                f"\n\n**PASS** ≥ {config.PASS_SCORE:.0f}% & nothing unsupported · **FAIL** on any contradiction or wrong figure")
    st.divider()
    st.caption("Case-study prototype. Coverage summaries come from insurer brochures; the policy wording prevails. "
               "Company facts come from Wikipedia and are labelled when assumed.")

st.title("📊 Marsh AI Pitch Generator")
st.caption("Client-specific employee health-insurance pitch, grounded in insurer policy documents and audited before use.")

# ---------------------------------------------------------------- inputs (Objective 1.1)
bundled = kb.bundled_policies()
with st.form("inputs"):
    c1, c2 = st.columns([1, 1])
    company = c1.text_input("Client company name", placeholder="e.g. Infosys, Tata Steel, Zomato")
    chosen = c2.multiselect("Baseline policy documents", options=[d["doc_id"] for d in bundled],
                            default=[d["doc_id"] for d in bundled],
                            format_func=lambda i: kb.doc_label(kb.load_curated()[i]))
    uploads = st.file_uploader("…or upload additional policy PDFs", type=["pdf"], accept_multiple_files=True)
    go = st.form_submit_button("🚀 Generate pitch", type="primary", use_container_width=True)


def _slug(s):
    return re.sub(r"\W+", "_", s).strip("_") or "client"


def _session_dir():
    """Per-session output folder so concurrent users of the public app never overwrite each other's files."""
    if "out_dir" not in ss:
        ss.out_dir = Path(tempfile.mkdtemp(prefix="marsh_", dir=config.OUTPUT_DIR))
    return ss.out_dir


def _render_outputs():
    slug = _slug(ss.pitch["company"])
    out = _session_dir()
    ss.deck_path = build_deck(ss.pitch, out / f"{slug}_Pitch_Deck.pptx", ss.audit["summary"])
    ss.xlsx_path = out / f"{slug}_Audit_Report.xlsx"
    ss.json_path = out / f"{slug}_Audit_Report.json"
    export_audit(ss.audit, ss.xlsx_path, ss.json_path, ss.get("decision"))


if go:  # Objective 1.4: validation + error handling
    errors = []
    if not company.strip():
        errors.append("Please enter a client company name.")
    docs = [kb.load_curated()[i] for i in chosen]
    for f in uploads or []:
        try:
            d = kb.load_uploaded(f.name, f.getvalue())
            if d["doc_id"] not in {x["doc_id"] for x in docs}:
                docs.append(d)
        except ValueError as e:
            errors.append(str(e))
    if not docs:
        errors.append("Please select or upload at least one policy document.")
    ss.setdefault("runs", 0)
    if use_llm and config.SERVER_HAS_KEY and not override and ss.runs >= config.MAX_RUNS_PER_SESSION:
        use_llm = False
        st.warning(f"LLM limit of {config.MAX_RUNS_PER_SESSION} pitches per session reached - using template mode.")
    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            with st.status("Generating pitch…", expanded=True) as status:
                st.write("🔎 Building company profile (Wikipedia + LLM)…")
                profile = generateCompanyProfile(company, use_llm=use_llm)
                st.write("🧩 Mapping exposures to policy benefits and scoring policies…")
                pitch = generateMarketingPitch(profile, docs, use_llm=use_llm)
                pitch["profile_sources"] = profile["sources"]
                st.write("🛡️ Auditing every claim against the policy documents…")
                audit = auditPitchContent(pitch["slides"], docs, use_llm=use_llm)
                ss.update(profile=profile, pitch=pitch, audit=audit, docs=docs, decision=None, audit_round=1,
                          runs=ss.get("runs", 0) + 1)
                st.write("📄 Rendering PowerPoint…")
                _render_outputs()
                status.update(label="Done", state="complete")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:  # generation failure
            st.error(f"Generation failed: {e}. Try again, switch off the LLM toggle, or check your API key.")

if "pitch" not in ss:
    st.info("Enter a company name, choose policy documents and click **Generate pitch**.")
    st.stop()

profile, pitch, audit = ss.profile, ss.pitch, ss.audit
for w in [profile.get("warning")] + pitch.get("warnings", []) + audit.get("warnings", []):
    if w:
        st.warning(w)

summ = audit["summary"]
m = st.columns(4)
m[0].markdown(f"### Audit: :{STATUS_COLOR[summ['status']]}[{summ['status']}]")
m[1].metric("Confidence", f"{summ['confidence_score']:.0f}%")
m[2].metric("Supported", f"{summ['supported']}/{summ['policy_claims_scored']}")
m[3].metric("Needs review", summ["needs_human_review"])
st.markdown(f"**Recommended policy:** {pitch['recommended']['label']} · generation mode: `{pitch['mode']}` · "
            f"audit method: `{audit['method']}`")

t1, t2, t3, t4 = st.tabs(["🏢 Company profile", "🖼️ Pitch preview", "🛡️ Audit report", "✅ Approve & export"])

# ---------------------------------------------------------------- profile (Objective 1.2)
with t1:
    st.subheader(profile["company_name"])
    if not profile["data_available"]:
        st.warning("No public data found - every field below is an **assumption**.")
    st.write(profile.get("summary", ""))
    st.dataframe(pd.DataFrame([{"Field": k.replace("_", " ").title(), "Value": v["value"],
                                "Basis": "✅ Sourced" if v["basis"] == "sourced" else "⚠️ Assumption"}
                               for k, v in profile["fields"].items()]), hide_index=True, use_container_width=True)
    st.markdown("**Key health exposures**")
    st.dataframe(pd.DataFrame([{"Exposure": r["label"], "Severity": r["severity"], "Why": r["rationale"],
                                "Basis": "✅ Sourced" if r["basis"] == "sourced" else "⚠️ Assumption"}
                               for r in profile["key_risks"]]), hide_index=True, use_container_width=True)
    for s in profile["sources"]:
        st.caption(f"Source: [{s['name']}]({s['url']})")

# ---------------------------------------------------------------- slides (Objective 1.3)
with t2:
    verdict = {c["claim_id"]: c["verdict"] for c in audit["claims"]}
    for s in pitch["slides"]:
        with st.container(border=True):
            st.markdown(f"#### Slide {s['no']} · {s['title']}")
            if s["type"] == "comparison":
                df = pd.DataFrame({s["column_labels"][c]: [f"{r['cells'][c]['status'].replace('_', ' ')}: {r['cells'][c]['value']}"
                                                          for r in s["rows"]] for c in s["columns"]},
                                  index=[r["feature"] for r in s["rows"]])
                df.loc["Fit score"] = [f"{s['scores'][c]:.0f}" for c in s["columns"]]
                st.dataframe(df, use_container_width=True)
                continue
            for key in ("items", "rows", "considerations", "next_steps"):
                for it in s.get(key, []):
                    icon = VERDICT_ICON.get(verdict.get(it.get("id")), "▫️")
                    lead = f"**{it['exposure']}** → " if key == "rows" else ""
                    cite = f"  `{', '.join(it.get('clause_ids', []))}`" if it.get("clause_ids") else ""
                    st.markdown(f"{icon} {lead}{it['text']}{cite}")
            if s["type"] == "overview":
                st.caption(" · ".join(f"{e['severity'].upper()}: {e['label']}" for e in s["exposures"]))
    st.download_button("⬇️ Download draft deck (.pptx)", open(ss.deck_path, "rb").read(),
                       file_name=ss.deck_path.name, use_container_width=True)

# ---------------------------------------------------------------- audit (Objective 2.1 / 2.2)
with t3:
    st.markdown(f"**Audit round {ss.audit_round}** · {summ['total_claims']} statements · "
                f"{summ['policy_claims_scored']} policy claims scored · rule: {summ['rule']}")
    show_all = st.toggle("Show supported claims too", value=False)
    rows = []
    for c in audit["claims"]:
        if not show_all and c["verdict"] == "SUPPORTED":
            continue
        ev = c["evidence"][0] if c.get("evidence") else {}
        rows.append({"Claim ID": c["claim_id"], "Verdict": f"{VERDICT_ICON[c['verdict']]} {c['verdict']}",
                     "Claim": c["text"], "Source": f"{ev.get('clause_id', '-')} (p{ev.get('page', '-')})",
                     "Flags": ", ".join(c["flags"]), "Reason": c["reason"], "Suggested fix": c["suggested_fix"],
                     "Action": c.get("advisor_action", "pending") if c.get("advisor_action") != "pending" else
                     ("Accept" if c["verdict"] in ("SUPPORTED", "OUT_OF_SCOPE") else "Review"),
                     "Edited text": ""})
    if rows:
        edited = st.data_editor(pd.DataFrame(rows), hide_index=True, use_container_width=True, key=f"ed{ss.audit_round}",
                                disabled=["Claim ID", "Verdict", "Claim", "Source", "Flags", "Reason", "Suggested fix"],
                                column_config={"Action": st.column_config.SelectboxColumn(
                                    options=["Review", "Accept", "Edit", "Reject"], required=True),
                                    "Claim": st.column_config.TextColumn(width="large"),
                                    "Edited text": st.column_config.TextColumn(width="large")})
        if st.button("✏️ Apply advisor actions & re-audit", type="primary"):
            acts = {r["Claim ID"]: (r["Action"], r["Edited text"]) for _, r in edited.iterrows()}
            for s in pitch["slides"]:
                for key in ("items", "rows", "considerations"):
                    if key == "rows" and s["type"] == "comparison":
                        continue
                    keep = []
                    for it in s.get(key, []):
                        a, txt = acts.get(it.get("id"), ("", ""))
                        if a == "Reject":
                            continue
                        if a == "Edit" and txt.strip():
                            it["text"] = txt.strip()
                        keep.append(it)
                    s[key] = keep
            accepted = {k for k, (a, _) in acts.items() if a == "Accept"}
            ss.audit = auditPitchContent(pitch["slides"], ss.docs, use_llm=use_llm)
            for c in ss.audit["claims"]:
                if c["claim_id"] in accepted:
                    c["advisor_action"] = "accepted"
            ss.audit_round += 1
            _render_outputs()
            st.rerun()
    else:
        st.success("Every policy claim is supported by a cited clause.")
    with st.expander("🔍 Evidence for every claim"):
        for c in audit["claims"]:
            if not c.get("evidence"):
                continue
            st.markdown(f"{VERDICT_ICON[c['verdict']]} **{c['claim_id']}** - {c['text']}")
            for e in c["evidence"][:2]:
                st.caption(f"{e['clause_id']} · {e['doc']} · page {e['page']} · {e['type']} — {e['text'][:300]}")

# ---------------------------------------------------------------- decision
with t4:
    st.markdown("**Advisor sign-off.** A pitch can be approved only when the audit is PASS, or when it is REVIEW and "
                "every flagged claim has been explicitly accepted by the advisor. FAIL must be fixed or rejected.")
    open_items = [c for c in audit["claims"] if c["verdict"] in ("PARTIAL", "UNSUPPORTED", "CONTRADICTED")
                  and c.get("advisor_action") != "accepted"]
    can_approve = summ["status"] == "PASS" or (summ["status"] == "REVIEW" and not open_items)
    name = st.text_input("Advisor name")
    note = st.text_area("Comment (optional)")
    c1, c2 = st.columns(2)
    if c1.button("✅ Approve for client", disabled=not (can_approve and name.strip()), use_container_width=True):
        ss.decision = {"decision": "APPROVED", "by": name, "at": datetime.now().isoformat(timespec="seconds"),
                       "comment": note, "audit_status": summ["status"], "score": summ["confidence_score"]}
        _render_outputs()
    if c2.button("⛔ Reject pitch", disabled=not name.strip(), use_container_width=True):
        ss.decision = {"decision": "REJECTED", "by": name, "at": datetime.now().isoformat(timespec="seconds"),
                       "comment": note, "audit_status": summ["status"], "score": summ["confidence_score"]}
        _render_outputs()
    if not can_approve:
        st.info(f"Approval locked: audit is {summ['status']} with {len(open_items)} open flagged claim(s). "
                "Fix or accept them in the Audit tab.")
    if ss.get("decision"):
        d = ss.decision
        (st.success if d["decision"] == "APPROVED" else st.error)(f"{d['decision']} by {d['by']} at {d['at']}")
    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇️ Pitch deck (.pptx)", open(ss.deck_path, "rb").read(), file_name=ss.deck_path.name,
                       disabled=not (ss.get("decision") or {}).get("decision") == "APPROVED", use_container_width=True)
    d2.download_button("⬇️ Audit report (.xlsx)", open(ss.xlsx_path, "rb").read(), file_name=ss.xlsx_path.name,
                       use_container_width=True)
    d3.download_button("⬇️ Audit report (.json)", open(ss.json_path, "rb").read(), file_name=ss.json_path.name,
                       use_container_width=True)
