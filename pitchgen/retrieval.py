"""Lexical (BM25) retrieval over policy clauses."""
import re

from rank_bm25 import BM25Okapi

_STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to with
up upto your you our we will can per any all under""".split())


_EXPAND = {"si": ["sum", "insured"], "bsi": ["base", "sum", "insured"], "lac": ["lakh"], "lacs": ["lakh"],
           "lakhs": ["lakh"], "hospitalization": ["hospitalisation"], "rs": ["inr"]}


def tokenize(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if t not in _STOP:
            out.extend(_EXPAND.get(t, [t]))
    return out


class ClauseIndex:
    def __init__(self, clauses: list[dict]):
        self.clauses = clauses
        corpus = [tokenize(f"{c.get('section', '')} {c['text']}") for c in clauses]
        self.bm25 = BM25Okapi(corpus) if clauses else None

    def search(self, query: str, doc_ids: set | None = None, k: int = 3) -> list[tuple[dict, float]]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self.clauses, scores), key=lambda x: -x[1])
        return [(c, float(s)) for c, s in ranked if (not doc_ids or c["doc_id"] in doc_ids) and s > 0][:k]
