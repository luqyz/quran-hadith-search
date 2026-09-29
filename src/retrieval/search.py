"""
Carian berasingan untuk Quran dan hadis: BM25, dense dan hybrid (RRF).

    python src/retrieval/search.py "sabar ketika diuji"
    python src/retrieval/search.py "sabar ketika diuji" --method hybrid --k 3
"""
import argparse
import textwrap

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from common import (BM25_PARAMS, CORPUS_PATH, DEFAULT_MODEL, MT_LANG, UNITS_PATH, emb_path, query_prefix, tokenize)

METHODS = ["bm25", "dense", "hybrid"]
SECTIONS = {"quran": ["quran"], "hadith": ["bukhari", "muslim"]}


def section_of(doc_id: str) -> str:
    src = doc_id.split(":")[0]
    return next(name for name, sources in SECTIONS.items() if src in sources)


class Section:
    """Index BM25 & dense untuk satu bahagian (Quran atau hadis)."""

    def __init__(self, units_sec: pd.DataFrame, emb_rows: np.ndarray, emb: np.ndarray | None,
                 k1: float = 1.5, b: float = 0.75):
        codes, uniques = pd.factorize(units_sec["doc_id"])
        self.doc_ids = uniques.to_numpy()
        self.codes = codes
        self.tokens = [tokenize(t) for t in units_sec["text"]]
        self.set_bm25(k1, b)

        self.emb = None
        if emb is not None:
            dense_pos = np.flatnonzero((units_sec["lang"] != MT_LANG).to_numpy())
            self.dense_codes = codes[dense_pos]
            self.emb = emb[emb_rows[dense_pos]]

    def set_bm25(self, k1: float, b: float) -> None:
        self.bm25 = BM25Okapi(self.tokens, k1=k1, b=b)

    def _aggregate(self, unit_scores: np.ndarray, codes: np.ndarray) -> np.ndarray:
        out = np.full(len(self.doc_ids), -np.inf)
        np.maximum.at(out, codes, unit_scores)
        return out

    def bm25_scores(self, tokens: list[str]) -> np.ndarray:
        return self._aggregate(self.bm25.get_scores(tokens), self.codes)

    def dense_scores(self, qvec: np.ndarray) -> np.ndarray:
        if self.emb is None:
            raise RuntimeError("Dense tidak dimuatkan (use_dense=False).")
        return self._aggregate(self.emb @ qvec, self.dense_codes)


class Searcher:
    def __init__(self, model_name: str = DEFAULT_MODEL, use_dense: bool = True,
                 rrf_k: int = 60, rrf_depth: int = 100,
                 w_bm25: float = 1.0, w_dense: float = 1.0, emb_variant: str = DEFAULT_EMB_VARIANT):
        units = pd.read_parquet(UNITS_PATH)
        self.corpus = pd.read_parquet(CORPUS_PATH).set_index("id")
        self.rrf_k = rrf_k
        self.rrf_depth = rrf_depth
        self.weights = {"bm25": w_bm25, "dense": w_dense}

        # Embedding hanya wujud untuk unit bukan terjemahan mesin, mengikut susunan asal
        dense_mask = (units["lang"] != MT_LANG).to_numpy()
        emb_row = np.cumsum(dense_mask) - 1

        self.model_name = model_name
        self.model = None
        emb = None
        if use_dense:
            path = emb_path(model_name, emb_variant)
            if not path.exists():
                raise FileNotFoundError(f"{path} tiada. Jalankan build_index.py dahulu.")
            emb = np.load(path)
            if len(emb) != dense_mask.sum():
                raise ValueError(f"Embedding ada {len(emb):,} baris, dijangka {dense_mask.sum():,} "
                                 f"(unit tanpa terjemahan). Jana semula index.")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)

        self.sections = {}
        for name, sources in SECTIONS.items():
            idx = np.flatnonzero(units["source"].isin(sources).to_numpy())
            self.sections[name] = Section(units.iloc[idx], emb_row[idx], emb,
                                          **BM25_PARAMS.get(name, {}))

        self._qcache: dict[str, np.ndarray] = {}

    def _qvec(self, query: str) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Dense tidak dimuatkan (use_dense=False).")
        if query not in self._qcache:
            self._qcache[query] = self.model.encode(
                [query_prefix(self.model_name) + query], normalize_embeddings=True)[0]
        return self._qcache[query]

    def doc_scores(self, query: str, method: str, section: str) -> np.ndarray:
        sec = self.sections[section]
        if method == "bm25":
            return sec.bm25_scores(tokenize(query))
        return sec.dense_scores(self._qvec(query))

    def top_bm25(self, query: str, section: str) -> float:
        return float(self.doc_scores(query, "bm25", section).max())

    @staticmethod
    def _top(scores: np.ndarray, n: int) -> np.ndarray:
        n = min(n, len(scores))
        idx = np.argpartition(-scores, n - 1)[:n]
        return idx[np.argsort(-scores[idx])]

    def rank(self, query: str, method: str, k: int, section: str):
        doc_ids = self.sections[section].doc_ids
        if method in ("bm25", "dense"):
            scores = self.doc_scores(query, method, section)
            idx = self._top(scores, k)
            return doc_ids[idx], scores[idx]

        if method == "hybrid":
            fused = np.zeros(len(doc_ids))
            for m in ("bm25", "dense"):
                top = self._top(self.doc_scores(query, m, section), self.rrf_depth)
                ranks = np.arange(1, len(top) + 1)
                fused[top] += self.weights[m] / (self.rrf_k + ranks)
            idx = self._top(fused, k)
            return doc_ids[idx], fused[idx]

        raise ValueError(f"Kaedah tidak dikenali: {method}")

    def search(self, query: str, method: str = "hybrid", k: int = 5,
               section: str = "quran") -> pd.DataFrame:
        ids, scores = self.rank(query, method, k, section)
        results = self.corpus.loc[ids, ["source", "ref", "chapter_title", "text_ms", "text_en"]]
        return results.assign(score=scores).reset_index(names="doc_id")


def print_results(results: pd.DataFrame) -> None:
    for r in results.itertuples():
        text = r.text_ms if isinstance(r.text_ms, str) else r.text_en
        print(f"  [{r.score:.4f}] {r.ref} ({r.chapter_title})")
        print("     ", textwrap.shorten(text, 200, placeholder="..."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--method", choices=METHODS + ["all"], default="hybrid")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    methods = METHODS if args.method == "all" else [args.method]
    searcher = Searcher(args.model, use_dense=any(m != "bm25" for m in methods))
    for m in methods:
        for sec in SECTIONS:
            print(f"\n=== {m.upper()} | {sec.upper()} "
                  f"(BM25 teratas: {searcher.top_bm25(args.query, sec):.1f}) ===")
            print_results(searcher.search(args.query, m, args.k, section=sec))


if __name__ == "__main__":
    main()