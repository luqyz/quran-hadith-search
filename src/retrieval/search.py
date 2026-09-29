"""
Carian BM25, dense dan hybrid (Reciprocal Rank Fusion).

    python src/retrieval/search.py "sabar ketika diuji"
    python src/retrieval/search.py "sabar ketika diuji" --method hybrid --k 10
"""
import argparse
import textwrap

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from common import CORPUS_PATH, DEFAULT_MODEL, UNITS_PATH, emb_path, query_prefix, tokenize

METHODS = ["bm25", "dense", "hybrid"]


class Searcher:
    def __init__(self, model_name: str = DEFAULT_MODEL, use_dense: bool = True,
                 rrf_k: int = 60, rrf_depth: int = 100,
                 w_bm25: float = 1.0, w_dense: float = 1.0):
        self.units = pd.read_parquet(UNITS_PATH)
        self.corpus = pd.read_parquet(CORPUS_PATH).set_index("id")
        self.bm25 = BM25Okapi([tokenize(t) for t in self.units["text"]])

        # Peta unit -> dokumen, dikira sekali untuk agregat yang pantas
        codes, uniques = pd.factorize(self.units["doc_id"])
        self.doc_codes = codes
        self.doc_ids = uniques.to_numpy()

        self.rrf_k = rrf_k
        self.rrf_depth = rrf_depth
        self.weights = {"bm25": w_bm25, "dense": w_dense}

        self.model_name = model_name
        self.model = None
        self.emb = None
        if use_dense:
            path = emb_path(model_name)
            if not path.exists():
                raise FileNotFoundError(f"{path} tiada. Jalankan build_index.py dahulu.")
            self.emb = np.load(path)
            if len(self.emb) != len(self.units):
                raise ValueError("Bilangan embedding tak sama dengan unit. Jana semula index.")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)

    # ---------- skor ----------

    def unit_scores(self, query: str, method: str) -> np.ndarray:
        if method == "bm25":
            return self.bm25.get_scores(tokenize(query))
        if self.model is None:
            raise RuntimeError("Dense tidak dimuatkan (use_dense=False).")
        q = self.model.encode([query_prefix(self.model_name) + query],
                              normalize_embeddings=True)[0]
        return self.emb @ q

    def doc_scores(self, query: str, method: str) -> np.ndarray:
        """Skor setiap dokumen = skor tertinggi antara unit-unitnya."""
        out = np.full(len(self.doc_ids), -np.inf)
        np.maximum.at(out, self.doc_codes, self.unit_scores(query, method))
        return out

    @staticmethod
    def _top(scores: np.ndarray, n: int) -> np.ndarray:
        n = min(n, len(scores))
        idx = np.argpartition(-scores, n - 1)[:n]
        return idx[np.argsort(-scores[idx])]

    def rank(self, query: str, method: str, k: int):
        if method in ("bm25", "dense"):
            scores = self.doc_scores(query, method)
            idx = self._top(scores, k)
            return idx, scores[idx]

        if method == "hybrid":
            fused = np.zeros(len(self.doc_ids))
            for m in ("bm25", "dense"):
                top = self._top(self.doc_scores(query, m), self.rrf_depth)
                ranks = np.arange(1, len(top) + 1)
                fused[top] += self.weights[m] / (self.rrf_k + ranks)
            idx = self._top(fused, k)
            return idx, fused[idx]

        raise ValueError(f"Kaedah tidak dikenali: {method}")

    def search(self, query: str, method: str = "hybrid", k: int = 5) -> pd.DataFrame:
        idx, scores = self.rank(query, method, k)
        ids = self.doc_ids[idx]
        results = self.corpus.loc[ids, ["source", "ref", "chapter_title", "text_ms", "text_en"]]
        return results.assign(score=scores).reset_index(names="doc_id")


def print_results(results: pd.DataFrame) -> None:
    for r in results.itertuples():
        text = r.text_ms if isinstance(r.text_ms, str) else r.text_en
        print(f"[{r.score:.4f}] {r.ref} ({r.chapter_title})")
        print("   ", textwrap.shorten(text, 220, placeholder="..."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--method", choices=METHODS + ["all"], default="all")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--w-bm25", type=float, default=1.0)
    parser.add_argument("--w-dense", type=float, default=1.0)
    args = parser.parse_args()

    methods = METHODS if args.method == "all" else [args.method]
    searcher = Searcher(args.model, use_dense=any(m != "bm25" for m in methods),
                        w_bm25=args.w_bm25, w_dense=args.w_dense)
    for m in methods:
        print(f"\n=== {m.upper()} ===")
        print_results(searcher.search(args.query, m, args.k))


if __name__ == "__main__":
    main()