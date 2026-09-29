"""
Carian BM25 dan dense.

    python src/retrieval/search.py "sabar ketika diuji" --method both
"""
import argparse
import textwrap

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from common import CORPUS_PATH, DEFAULT_MODEL, UNITS_PATH, emb_path, query_prefix, tokenize


class Searcher:
    def __init__(self, model_name: str = DEFAULT_MODEL, use_dense: bool = True):
        self.units = pd.read_parquet(UNITS_PATH)
        self.corpus = pd.read_parquet(CORPUS_PATH).set_index("id")
        self.bm25 = BM25Okapi([tokenize(t) for t in self.units["text"]])

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

    def unit_scores(self, query: str, method: str) -> np.ndarray:
        if method == "bm25":
            return self.bm25.get_scores(tokenize(query))
        if self.model is None:
            raise RuntimeError("Dense tidak dimuatkan (use_dense=False).")
        q = self.model.encode([query_prefix(self.model_name) + query],
                              normalize_embeddings=True)[0]
        return self.emb @ q

    def search(self, query: str, method: str = "dense", k: int = 5) -> pd.DataFrame:
        scores = self.unit_scores(query, method)
        # Agregat unit -> dokumen: ambil skor tertinggi antara unit sesuatu dokumen
        best = (self.units[["doc_id"]].assign(score=scores)
                .groupby("doc_id")["score"].max().nlargest(k))
        results = self.corpus.loc[best.index, ["source", "ref", "chapter_title", "text_ms", "text_en"]]
        return results.assign(score=best.values).reset_index(names="doc_id")


def print_results(results: pd.DataFrame) -> None:
    for r in results.itertuples():
        text = r.text_ms if isinstance(r.text_ms, str) else r.text_en
        print(f"[{r.score:.3f}] {r.ref} ({r.chapter_title})")
        print("   ", textwrap.shorten(text, 220, placeholder="..."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--method", choices=["bm25", "dense", "both"], default="both")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    searcher = Searcher(args.model, use_dense=args.method != "bm25")
    methods = ["bm25", "dense"] if args.method == "both" else [args.method]
    for m in methods:
        print(f"\n=== {m.upper()} ===")
        print_results(searcher.search(args.query, m, args.k))


if __name__ == "__main__":
    main()