"""Extract and normalise quantities (money, %, days, multipliers, counts) for deterministic figure checks."""
import re

_UNIT_MULT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5,
              "crore": 1e7, "crores": 1e7, "cr": 1e7}

_NUM = r"\d(?:[\d,]*\d)?(?:\.\d+)?"
_PATTERNS = [
    ("money", re.compile(rf"(?:₹|\binr|\brs\.?|`)\s*({_NUM})\s*(lakhs?|lacs?|crores?|cr|l)?\b", re.I)),
    ("money", re.compile(rf"({_NUM})\s*(lakhs?|lacs?|crores?|cr)\b", re.I)),
    ("money", re.compile(rf"\b({_NUM})\s*(l)\b(?![\w-])", re.I)),
    ("pct", re.compile(rf"({_NUM})\s*%")),
    ("days", re.compile(rf"({_NUM})\s*(?:-\s*)?days?\b", re.I)),
    ("months", re.compile(rf"({_NUM})\s*months?\b", re.I)),
    ("hours", re.compile(rf"({_NUM})\s*(?:hrs?|hours?)\b", re.I)),
    ("mult", re.compile(rf"\b({_NUM})\s*(?:x|times)\b(?!\d)", re.I)),
    ("mult", re.compile(r"\b(\d+)x\b", re.I)),
]
_IGNORE = re.compile(r"\b24\s*x\s*7\b|\b\d{4}-\d{2,4}\b|\bp\d+\b", re.I)


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def extract(text: str) -> list[dict]:
    """Return quantities found in text: [{kind, value, display, raw}]."""
    text = _IGNORE.sub(" ", text or "")
    found, spans = [], []
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            if any(a <= m.start() < b for a, b in spans):
                continue
            num = m.group(1)
            try:
                display = _to_float(num)
            except ValueError:
                continue
            value = display
            if kind == "money":
                unit = (m.group(2) or "").lower() if m.lastindex and m.lastindex >= 2 else ""
                value = display * _UNIT_MULT.get(unit, 1)
            found.append({"kind": kind, "value": value, "display": display, "raw": m.group(0).strip()})
            spans.append((m.start(), m.end()))
    # bare numbers not already captured (e.g. "51 critical illnesses", "16,000 hospitals")
    for m in re.finditer(_NUM, text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        try:
            v = _to_float(m.group(0))
        except ValueError:
            continue
        found.append({"kind": "num", "value": v, "display": v, "raw": m.group(0)})
    return found


def evidence_numbers(text: str) -> set[float]:
    """All plausible numeric values in evidence text (lenient: raw, lakh and crore scalings)."""
    vals = set()
    for q in extract(text):
        vals.add(q["value"])
        vals.add(q["display"])
    lowered = (text or "").lower()
    has_lakh = any(w in lowered for w in ("lakh", "lac", " l ", "l,", "l /"))
    has_crore = "crore" in lowered or " cr" in lowered
    for v in list(vals):
        if has_lakh:
            vals.add(v * 1e5)
        if has_crore:
            vals.add(v * 1e7)
    return vals


def check_claim_numbers(claim: str, evidence_text: str) -> dict:
    """Every figure in the claim must appear in the evidence."""
    qs = [q for q in extract(claim) if q["kind"] != "num" or q["display"] >= 2]
    ev = evidence_numbers(evidence_text)
    matched, missing = [], []
    for q in qs:
        ok = q["value"] in ev or q["display"] in ev
        (matched if ok else missing).append(q["raw"])
    return {"numbers": [q["raw"] for q in qs], "matched": matched, "missing": missing,
            "passed": not missing}
