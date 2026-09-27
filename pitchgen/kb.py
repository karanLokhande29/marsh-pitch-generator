"""Policy knowledge base: curated clause store for bundled brochures + generic chunking for uploads."""
import hashlib
import io
import json
import logging
import re
from pathlib import Path

from . import config

logging.getLogger("pdfminer").setLevel(logging.ERROR)

_CURATED = None
_MATRIX = None


def load_curated() -> dict:
    """doc_id -> document dict (with clauses)."""
    global _CURATED
    if _CURATED is None:
        raw = json.loads((config.DATA_DIR / "clauses.json").read_text())
        _CURATED = {}
        for d in raw["documents"]:
            d = dict(d, curated=True)
            for c in d["clauses"]:
                c["doc_id"] = d["doc_id"]
            _CURATED[d["doc_id"]] = d
    return _CURATED


def load_matrix() -> dict:
    global _MATRIX
    if _MATRIX is None:
        _MATRIX = json.loads((config.DATA_DIR / "benefit_matrix.json").read_text())
    return _MATRIX


def bundled_policies() -> list[dict]:
    return list(load_curated().values())


def extract_pdf_pages(path_or_bytes) -> list[str]:
    import pdfplumber
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else path_or_bytes
    with pdfplumber.open(src) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def _match_curated(name: str, pages: list[str]) -> str | None:
    """Recognise an uploaded copy of a bundled brochure (by filename or text fingerprint)."""
    for d in load_curated().values():
        if Path(name).name.lower() == d["file"].lower():
            return d["doc_id"]
    blob = " ".join(pages).lower()
    for doc_id, fp in {"HDFC": "optima secure", "CARE": "care supreme",
                       "NIVA": "reassure 2.0", "ABHI": "activ one"}.items():
        if fp in blob:
            return doc_id
    return None


def load_uploaded(name: str, data: bytes) -> dict:
    """Parse an uploaded PDF. Known brochures map to the curated store; others are auto-chunked."""
    try:
        pages = extract_pdf_pages(data)
    except Exception as e:
        raise ValueError(f"Could not read '{name}' as a PDF: {e}") from e
    if not any(p.strip() for p in pages):
        raise ValueError(f"'{name}' has no extractable text (scanned image?). Please upload a text PDF.")
    known = _match_curated(name, pages)
    if known:
        return load_curated()[known]
    stem = re.sub(r"[^A-Z0-9]", "", Path(name).stem.upper())[:6] or "DOC"
    doc_id = f"U{stem}{hashlib.md5(data).hexdigest()[:4].upper()}"
    clauses = []
    for pno, text in enumerate(pages, start=1):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        buf, k = [], 0
        for line in lines:
            buf.append(line)
            if sum(len(x) for x in buf) > 350:
                k += 1
                clauses.append({"id": f"{doc_id}-p{pno}-c{k}", "page": pno, "section": f"Page {pno}",
                                "type": "unknown", "text": " ".join(buf), "doc_id": doc_id})
                buf = buf[-1:]
        if len(buf) > 1 or (buf and k == 0):
            k += 1
            clauses.append({"id": f"{doc_id}-p{pno}-c{k}", "page": pno, "section": f"Page {pno}",
                            "type": "unknown", "text": " ".join(buf), "doc_id": doc_id})
    return {"doc_id": doc_id, "insurer": Path(name).stem, "product": Path(name).stem, "file": name,
            "aliases": [Path(name).stem.lower()], "clauses": clauses, "curated": False}


def all_clauses(docs: list[dict]) -> list[dict]:
    return [c for d in docs for c in d["clauses"]]


def clause_index(docs: list[dict]) -> dict:
    return {c["id"]: c for c in all_clauses(docs)}


def doc_label(doc: dict) -> str:
    return f"{doc['insurer']} {doc['product']}"
