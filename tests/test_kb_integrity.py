"""Every figure in the curated clause store must appear on the cited PDF page (guards transcription errors)."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pitchgen import config, kb, numbers  # noqa: E402


def test_clause_numbers_exist_on_page():
    problems = []
    for d in kb.load_curated().values():
        pages = kb.extract_pdf_pages(str(config.POLICY_DIR / d["file"]))
        for c in d["clauses"]:
            page_text = re.sub(r"\s+", " ", pages[c["page"] - 1].replace("`", "INR ").replace("₹", "INR "))
            chk = numbers.check_claim_numbers(c["text"], page_text)
            if not chk["passed"]:
                problems.append((c["id"], chk["missing"]))
    for p in problems:
        print("MISSING ON PAGE:", p)
    assert not problems


def test_matrix_clauses_exist():
    idx = {c["id"] for d in kb.load_curated().values() for c in d["clauses"]}
    bad = [(f, doc, cid) for f, row in kb.load_matrix()["features"].items() for doc, cell in row.items()
           if isinstance(cell, dict) for cid in cell.get("clauses", []) if cid not in idx]
    assert not bad, bad


if __name__ == "__main__":
    test_matrix_clauses_exist()
    test_clause_numbers_exist_on_page()
    print("KB integrity OK")
