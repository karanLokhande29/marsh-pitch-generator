"""Render a pitch (slide JSON) to a 16:9 PowerPoint deck with python-pptx."""
import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

NAVY = RGBColor(0x00, 0x1E, 0x5A)
BLUE = RGBColor(0x00, 0x6D, 0xC6)
TEAL = RGBColor(0x00, 0x8C, 0x8C)
GREY = RGBColor(0x5F, 0x63, 0x6B)
LIGHT = RGBColor(0xEE, 0xF2, 0xF8)
AMBER = RGBColor(0xB0, 0x6A, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x1F, 0x23, 0x2B)
SEV = {"high": RGBColor(0xC0, 0x39, 0x2B), "medium": AMBER, "low": TEAL}
STATUS = {"included": ("Included", TEAL), "plan_specific": ("Plan-specific", BLUE),
          "optional": ("Optional add-on", AMBER), "not_mentioned": ("Not stated", GREY)}


def _ref(cid: str) -> str:
    m = re.match(r"([A-Z0-9]+)-p(\d+)", cid or "")
    return f"{m.group(1)} p{m.group(2)}" if m else cid


def _text(tf, text, size=14, bold=False, color=DARK, italic=False, align=None, first=False):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    r = p.add_run()
    r.text = text
    r.font.size, r.font.bold, r.font.italic = Pt(size), bold, italic
    r.font.color.rgb = color
    r.font.name = "Calibri"
    if align:
        p.alignment = align
    return p


def _box(slide, x, y, w, h, fill=None, line=None):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
    s.shadow.inherit = False
    return s


def _tb(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    return tf


def _frame(prs, title, no, footer_left, audit):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _box(s, 0, 0, 13.333, 1.05, fill=NAVY)
    tf = _tb(s, 0.5, 0.2, 11.2, 0.7)
    _text(tf, title, 26, True, WHITE, first=True)
    tf = _tb(s, 11.6, 0.3, 1.5, 0.5)
    _text(tf, "MARSH", 18, True, WHITE, align=PP_ALIGN.RIGHT, first=True)
    _box(s, 0, 7.0, 13.333, 0.02, fill=BLUE)
    tf = _tb(s, 0.5, 7.03, 9.8, 0.45)
    _text(tf, footer_left, 8, color=GREY, first=True)
    tf = _tb(s, 10.2, 7.03, 2.9, 0.45)
    stamp = f"AI audit: {audit['status']} ({audit['confidence_score']:.0f}%)  |  {no}" if audit else f"{no}"
    _text(tf, stamp, 9, True, NAVY, align=PP_ALIGN.RIGHT, first=True)
    return s


DISCLAIMER = "Summary of brochure features only; the insurer's policy wording prevails. Insurance is the subject matter of solicitation."


def build_deck(pitch: dict, out_path: str | Path, audit_summary: dict | None = None) -> Path:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    sl = {s["type"]: s for s in pitch["slides"]}

    # 1 overview
    s1 = sl["overview"]
    src = "; ".join(f"{x['name']}: {x['url']}" for x in pitch.get("profile_sources", [])) or "No public source found - assumptions labelled"
    s = _frame(prs, s1["title"], 1, f"Sources: {src}. Items marked (assumption) are not from public sources.", audit_summary)
    tf = _tb(s, 0.5, 1.35, 6.0, 0.4)
    _text(tf, "Company snapshot", 16, True, BLUE, first=True)
    tf = _tb(s, 0.5, 1.8, 6.0, 4.8)
    first = True
    for it in s1["items"]:
        assumed = it.get("basis") == "assumption"
        _text(tf, "• " + it["text"], 14, color=AMBER if assumed else DARK, italic=assumed, first=first).space_after = Pt(6)
        first = False
    if s1.get("summary"):
        _text(tf, "", 8)
        _text(tf, "About the company", 14, True, BLUE)
        _text(tf, s1["summary"][:420], 12, color=GREY)
    _box(s, 6.9, 1.35, 5.95, 5.4, fill=LIGHT)
    tf = _tb(s, 7.1, 1.45, 5.6, 0.4)
    _text(tf, "Key employee-health exposures", 16, True, NAVY, first=True)
    tf = _tb(s, 7.1, 1.9, 5.6, 4.8)
    first = True
    for e in s1["exposures"]:
        p = _text(tf, f"{e['severity'].upper()}  ", 11, True, SEV[e["severity"]], first=first)
        r = p.add_run()
        r.text = e["label"]
        r.font.size, r.font.bold, r.font.color.rgb = Pt(13), True, DARK
        _text(tf, e["rationale"] + (" (assumption)" if e["basis"] == "assumption" else ""), 11,
              color=AMBER if e["basis"] == "assumption" else GREY, italic=e["basis"] == "assumption").space_after = Pt(10)
        first = False

    # 2 why marsh
    s2 = sl["why_marsh"]
    s = _frame(prs, s2["title"], 2, "Marsh statements are advisor-verified and not drawn from insurer documents.", audit_summary)
    heads = ["Independent", "Transparent", "Verified", "Partnership"]
    for i, it in enumerate(s2["items"][:4]):
        x = 0.5 + i * 3.1
        _box(s, x, 1.6, 2.9, 3.6, fill=LIGHT)
        _box(s, x, 1.6, 2.9, 0.12, fill=BLUE)
        tf = _tb(s, x + 0.2, 1.9, 2.5, 0.6)
        _text(tf, heads[i], 20, True, NAVY, first=True)
        tf = _tb(s, x + 0.2, 2.6, 2.5, 2.5)
        _text(tf, it["text"], 15, color=DARK, first=True)
    tf = _tb(s, 0.5, 5.6, 12.3, 1.1)
    _text(tf, f"This proposal positions the selected insurer products as employee and family health benefits for "
              f"{pitch['company']}. Premiums depend on the employee census and are quoted separately.", 13, color=GREY,
          italic=True, first=True)

    # 3 exposure map
    s3 = sl["exposure_map"]
    rows = s3["rows"]
    s = _frame(prs, s3["title"], 3, DISCLAIMER + " Source = insurer document and page.", audit_summary)
    tbl = s.shapes.add_table(len(rows) + 1, 4, Inches(0.5), Inches(1.35), Inches(12.33), Inches(0.5)).table
    widths = [3.3, 1.1, 6.6, 1.33]
    for i, w in enumerate(widths):
        tbl.columns[i].width = Inches(w)
    for j, h in enumerate(["Exposure", "Severity", "How the policy responds", "Source"]):
        c = tbl.cell(0, j)
        c.fill.solid()
        c.fill.fore_color.rgb = NAVY
        _text(c.text_frame, h, 13, True, WHITE, first=True)
    for i, r in enumerate(rows, start=1):
        vals = [r["exposure"], r["severity"].capitalize(), r["text"], ", ".join(_ref(x) for x in r["clause_ids"]) or "-"]
        for j, v in enumerate(vals):
            c = tbl.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = LIGHT if i % 2 else WHITE
            color = SEV.get(r["severity"], DARK) if j == 1 else DARK
            _text(c.text_frame, v, 13, j == 1, color, first=True)
        tbl.rows[i].height = Inches(min(1.0, 5.0 / max(len(rows), 1)))

    # 4 comparison
    s4 = sl["comparison"]
    cols = s4["columns"]
    rec = pitch["recommended"]["doc_id"]
    s = _frame(prs, s4["title"], 4, "Fit score = severity-weighted coverage of the exposures on slide 1 (Included 1.0, Plan-specific 0.6, Optional 0.5, Not stated 0). " + DISCLAIMER, audit_summary)
    tbl = s.shapes.add_table(len(s4["rows"]) + 2, len(cols) + 1, Inches(0.5), Inches(1.3), Inches(12.33), Inches(0.4)).table
    tbl.columns[0].width = Inches(3.0)
    for j in range(len(cols)):
        tbl.columns[j + 1].width = Inches(9.33 / len(cols))
    hdr = ["Benefit"] + [s4["column_labels"][c] + ("  ★" if c == rec else "") for c in cols]
    for j, h in enumerate(hdr):
        c = tbl.cell(0, j)
        c.fill.solid()
        c.fill.fore_color.rgb = BLUE if j and cols[j - 1] == rec else NAVY
        _text(c.text_frame, h, 12, True, WHITE, first=True)
    for i, r in enumerate(s4["rows"], start=1):
        c = tbl.cell(i, 0)
        c.fill.solid()
        c.fill.fore_color.rgb = LIGHT
        _text(c.text_frame, r["feature"], 11, True, DARK, first=True)
        for j, col in enumerate(cols, start=1):
            cell = r["cells"][col]
            lab, colr = STATUS[cell["status"]]
            c = tbl.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = RGBColor(0xE3, 0xEF, 0xFB) if col == rec else WHITE
            _text(c.text_frame, lab, 10, True, colr, first=True)
            if cell["status"] != "not_mentioned":
                _text(c.text_frame, cell["value"], 10, color=GREY)
        tbl.rows[i].height = Inches(min(0.62, 4.8 / max(len(s4["rows"]), 1)))
    last = len(s4["rows"]) + 1
    c = tbl.cell(last, 0)
    c.fill.solid()
    c.fill.fore_color.rgb = NAVY
    _text(c.text_frame, "Fit score (0-100)", 12, True, WHITE, first=True)
    for j, col in enumerate(cols, start=1):
        c = tbl.cell(last, j)
        c.fill.solid()
        c.fill.fore_color.rgb = BLUE if col == rec else NAVY
        _text(c.text_frame, f"{s4['scores'].get(col, 0):.1f}", 14, True, WHITE, first=True)

    # 5 recommendation
    s5 = sl["recommendation"]
    refs = sorted({_ref(x) for it in s5["items"] + s5["considerations"] for x in it.get("clause_ids", [])})
    s = _frame(prs, s5["title"], 5, "Sources: " + ", ".join(refs) + ". " + DISCLAIMER, audit_summary)
    tf = _tb(s, 0.5, 1.35, 7.6, 0.5)
    _text(tf, f"Why it fits {pitch['company']}", 18, True, BLUE, first=True)
    tf = _tb(s, 0.5, 1.9, 7.6, 4.9)
    first = True
    for it in s5["items"]:
        p = _text(tf, "✓  " + it["text"], 15, color=DARK, first=first)
        r = p.add_run()
        r.text = f"  [{', '.join(_ref(x) for x in it['clause_ids'])}]"
        r.font.size, r.font.color.rgb = Pt(9), GREY
        p.space_after = Pt(12)
        first = False
    _box(s, 8.5, 1.35, 4.35, 1.5, fill=NAVY)
    tf = _tb(s, 8.7, 1.45, 4.0, 1.3)
    _text(tf, "Fit score", 14, color=WHITE, first=True)
    _text(tf, f"{s5.get('fit_score') or 0:.1f} / 100", 32, True, WHITE)
    _box(s, 8.5, 3.0, 4.35, 3.8, fill=LIGHT)
    tf = _tb(s, 8.7, 3.1, 4.0, 3.6)
    _text(tf, "Things to consider", 14, True, AMBER, first=True)
    for it in s5["considerations"]:
        _text(tf, "• " + it["text"], 11, color=DARK)
    _text(tf, "Next steps", 14, True, NAVY)
    for it in s5["next_steps"]:
        _text(tf, "• " + it["text"], 11, color=DARK)

    out_path = Path(out_path)
    prs.save(out_path)
    return out_path
