"""generateCompanyProfile: Wikipedia facts + LLM structuring, with clearly-labelled assumptions as fallback."""
import json
import re
from datetime import datetime

import requests

from . import config, kb, llm

WIKI_API = "https://en.wikipedia.org/w/api.php"
SOURCED, ASSUMED = "sourced", "assumption"


def validate_company_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Please enter a company name.")
    if len(name) < 2 or len(name) > 100 or not re.search(r"[A-Za-z]", name):
        raise ValueError("Company name looks invalid. Use 2-100 characters including letters.")
    return name


def _clean_wiki(s: str) -> str:
    s = re.sub(r"<br\s*/?>|\n\*", ", ", s)
    s = re.sub(r"\{\{(?:[^{}]|\{\{[^{}]*\}\})*\}\}", lambda m: _template_text(m.group(0)), s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>|<[^>]+>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", s.replace("'''", "").replace("''", "")).strip(" ,;")


def _template_text(t: str) -> str:
    """Keep the useful payload of simple templates like {{increase}} {{US$|10 billion}} {{ubl|a|b}}."""
    inner = t.strip("{}")
    parts = [p for p in inner.split("|")[1:] if "=" not in p]
    return ", ".join(parts)


def fetch_wikipedia(company: str) -> dict | None:
    headers = {"User-Agent": config.USER_AGENT}
    try:
        r = requests.get(WIKI_API, params={"action": "query", "list": "search", "srsearch": f"{company} company",
                                           "format": "json", "srlimit": 3}, headers=headers, timeout=10)
        hits = r.json().get("query", {}).get("search", [])
        if not hits:
            return None
        key = company.lower().split()[0]
        hit = next((h for h in hits if key in h["title"].lower()), hits[0])
        title = hit["title"]
        r = requests.get(WIKI_API, params={"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
                                           "titles": title, "format": "json", "redirects": 1},
                         headers=headers, timeout=10)
        page = next(iter(r.json()["query"]["pages"].values()))
        extract = page.get("extract", "")
        r = requests.get(WIKI_API, params={"action": "parse", "page": title, "prop": "wikitext", "section": 0,
                                           "format": "json", "redirects": 1}, headers=headers, timeout=10)
        wikitext = r.json().get("parse", {}).get("wikitext", {}).get("*", "")
        infobox = {}
        for field in ("industry", "num_employees", "hq_location", "hq_location_city", "hq_location_country",
                      "revenue", "founded", "area_served", "type", "key_people"):
            m = re.search(rf"^\s*\|\s*{field}\s*=\s*(.+)$", wikitext, re.M)
            if m and _clean_wiki(m.group(1)):
                infobox[field] = _clean_wiki(m.group(1))[:200]
        if not extract and not infobox:
            return None
        return {"title": title, "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "extract": extract[:3500], "infobox": infobox}
    except Exception:
        return None


def _exposure_menu() -> str:
    ex = kb.load_matrix()["exposures"]
    return "\n".join(f"- {k}: {v['label']}" for k, v in ex.items())


_SYSTEM = """You are a corporate risk analyst at an insurance broker. Build a factual company profile for
an employee health-benefits pitch. Use ONLY the source text for facts and mark them basis="sourced".
Anything not in the source text must be basis="assumption" and phrased cautiously ("likely", "estimated").
Never invent precise figures that are not in the source. Respond with JSON only."""

_USER = """Company requested: {company}
Today: {today}

SOURCE TEXT (Wikipedia: {url}):
{source}

Choose 4 or 5 employee-health exposures ONLY from this list (use the exact tag):
{menu}

Return JSON:
{{
 "company_name": str,
 "found_in_sources": bool,
 "fields": {{
   "industry": {{"value": str, "basis": "sourced|assumption"}},
   "headquarters": {{"value": str, "basis": "..."}},
   "employees": {{"value": str, "basis": "..."}},
   "revenue": {{"value": str, "basis": "..."}},
   "operations": {{"value": str, "basis": "..."}},
   "workforce_profile": {{"value": str, "basis": "..."}}
 }},
 "summary": str (2 sentences, facts from source only),
 "key_risks": [{{"exposure": tag, "severity": "high|medium|low", "rationale": str (1 sentence), "basis": "sourced|assumption"}}]
}}"""


def _source_text(wiki: dict | None) -> str:
    if not wiki:
        return "(no source found)"
    ib = "\n".join(f"{k}: {v}" for k, v in wiki["infobox"].items())
    return f"Infobox:\n{ib}\n\nIntro:\n{wiki['extract']}"


def _verify_sourced(profile: dict, source: str):
    """Downgrade any 'sourced' field whose figures do not appear in the source text."""
    src = source.lower().replace(",", "")
    for f in profile["fields"].values():
        if f.get("basis") != SOURCED:
            continue
        nums = re.findall(r"\d[\d,.]*", f.get("value", ""))
        if any(n.replace(",", "").rstrip(".") not in src for n in nums):
            f["basis"] = ASSUMED
            f["note"] = "Figure not found in source; treated as assumption."


def _fallback_profile(company: str, wiki: dict | None) -> dict:
    ib = dict((wiki or {}).get("infobox", {}))
    if not ib.get("hq_location") and ib.get("hq_location_city"):
        ib["hq_location"] = ", ".join(x for x in (ib["hq_location_city"], ib.get("hq_location_country")) if x)
    if ib.get("revenue") and not re.search(r"billion|million|crore|lakh|US\$|₹", ib["revenue"], re.I):
        ib.pop("revenue")

    def fld(key, default):
        return {"value": ib[key], "basis": SOURCED} if ib.get(key) else {"value": default, "basis": ASSUMED}

    return {
        "company_name": company,
        "found_in_sources": bool(wiki),
        "fields": {
            "industry": fld("industry", "Not confirmed - assumed services / corporate sector"),
            "headquarters": fld("hq_location", "Assumed India (metro city)"),
            "employees": fld("num_employees", "Not confirmed - assumed 1,000+ employees"),
            "revenue": fld("revenue", "Not available"),
            "operations": {"value": "Assumed multi-city operations in India", "basis": ASSUMED},
            "workforce_profile": {"value": "Assumed mix of salaried employees aged 25-45 with dependants",
                                  "basis": ASSUMED},
        },
        "summary": (wiki or {}).get("extract", "")[:300] or
                   f"No public information was retrieved for {company}; the profile below is based on assumptions.",
        "key_risks": [
            {"exposure": "high_treatment_costs", "severity": "high", "basis": ASSUMED,
             "rationale": "Hospitalisation costs in Indian metros are high and rising."},
            {"exposure": "lifestyle_chronic", "severity": "high", "basis": ASSUMED,
             "rationale": "Desk-based work is associated with diabetes and hypertension risk."},
            {"exposure": "repeat_claims", "severity": "medium", "basis": ASSUMED,
             "rationale": "Family cover means several claims can arise in one year."},
            {"exposure": "out_of_pocket", "severity": "medium", "basis": ASSUMED,
             "rationale": "Non-payable items can leave employees with out-of-pocket costs."},
        ],
    }


def generateCompanyProfile(company_name: str, use_llm: bool = True) -> dict:
    """Gather company info (industry, size, key risks); fall back to clearly-labelled assumptions."""
    company = validate_company_name(company_name)
    wiki = fetch_wikipedia(company)
    source = _source_text(wiki)
    profile, mode, warning = None, "template", None
    if use_llm and llm.is_available():
        try:
            prompt = _USER.format(company=company, today=datetime.now().strftime("%Y-%m-%d"),
                                  url=(wiki or {}).get("url", "n/a"), source=source, menu=_exposure_menu())
            out = llm.chat_json(_SYSTEM, prompt, temperature=0.1)
            profile, mode = out, "llm"
        except llm.LLMError as e:
            warning = f"LLM unavailable ({e}); used rule-based profile."
    if profile is None:
        profile = _fallback_profile(company, wiki)

    # Normalise and enforce the taxonomy.
    valid = kb.load_matrix()["exposures"]
    risks = [r for r in profile.get("key_risks", []) if r.get("exposure") in valid]
    if len(risks) < 3:
        risks += [r for r in _fallback_profile(company, None)["key_risks"]
                  if r["exposure"] not in {x["exposure"] for x in risks}]
    for r in risks:
        r["label"] = valid[r["exposure"]]["label"]
        r["severity"] = r.get("severity") if r.get("severity") in ("high", "medium", "low") else "medium"
        r["basis"] = r.get("basis") if r.get("basis") in (SOURCED, ASSUMED) else ASSUMED
    profile["key_risks"] = risks[:5]
    fields = profile.setdefault("fields", {})
    for k in ("industry", "headquarters", "employees", "revenue", "operations", "workforce_profile"):
        f = fields.get(k)
        if not isinstance(f, dict) or not f.get("value"):
            fields[k] = {"value": "Not available", "basis": ASSUMED}
        elif f.get("basis") not in (SOURCED, ASSUMED):
            f["basis"] = ASSUMED
    if not wiki:
        for f in fields.values():
            f["basis"] = ASSUMED
    _verify_sourced(profile, source)

    profile.update({
        "company_name": profile.get("company_name") or company,
        "requested_name": company,
        "sources": [{"name": "Wikipedia", "url": wiki["url"]}] if wiki else [],
        "source_text": source,
        "mode": mode,
        "warning": warning,
        "data_available": bool(wiki),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    })
    return profile


if __name__ == "__main__":
    import sys
    print(json.dumps({k: v for k, v in generateCompanyProfile(sys.argv[1] if len(sys.argv) > 1 else "Infosys").items()
                      if k != "source_text"}, indent=2))
