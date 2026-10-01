"""
Carian berasingan untuk Quran dan hadis: BM25, dense dan hybrid (RRF).

    python src/retrieval/search.py "menahan marah"
    python src/retrieval/search.py "menahan marah" --method all --k 5 --stem both
"""
import argparse
import textwrap

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from common import (BM25_PARAMS, CORPUS_PATH, DEFAULT_EMB_VARIANT, DEFAULT_MODEL, MT_LANG,
                    QUERY_STOP_MODE, STEM_SECTIONS, UNITS_PATH, emb_path, expand_with_stems,
                    query_prefix, query_tokens, tokenize)

METHODS = ["bm25", "dense", "hybrid"]
SECTIONS = {"quran": ["quran"], "hadith": ["bukhari", "muslim"]}
STEM_CHOICES = {
    "none": {"quran": False, "hadith": False},
    "quran": {"quran": True, "hadith": False},
    "hadith": {"quran": False, "hadith": True},
    "both": {"quran": True, "hadith": True},
}
QCACHE_MAX = 1000


def section_of(doc_id: str) -> str:
    src = doc_id.split(":")[0]
    return next(name for name, sources in SECTIONS.items() if src in sources)


class Section:
    """Index BM25 & dense untuk satu bahagian (Quran atau hadis)."""

    def __init__(self, units_sec: pd.DataFrame, emb_rows: np.ndarray, emb: np.ndarray | None,
                 flags: pd.DataFrame | None = None, field: str = "text",
                 k1: float = 1.5, b: float = 0.75):
        codes, uniques = pd.factorize(units_sec["doc_id"])
        self.doc_ids = uniques.to_numpy()
        self.doc_index = {d: i for i, d in enumerate(self.doc_ids)}
        self.codes = codes
        self.tokens = [tokenize(t) for t in units_sec[field]]
        self.set_bm25(k1, b)

        # Dokumen yang diabaikan: rujukan silang (semua kaedah), muqatta'ah (dense sahaja)
        n = len(self.doc_ids)
        self.exclude_all = np.zeros(n, dtype=bool)
        self.exclude_dense = np.zeros(n, dtype=bool)
        if flags is not None:
            f = flags.reindex(self.doc_ids)
            if "is_xref" in f.columns:
                self.exclude_all = f["is_xref"].astype("boolean").fillna(False).to_numpy(dtype=bool)
            if "is_muqattaat" in f.columns:
                self.exclude_dense = f["is_muqattaat"].astype("boolean").fillna(False).to_numpy(dtype=bool)

        self.emb = None
        if emb is not None:
            dense_pos = np.flatnonzero((units_sec["lang"] != MT_LANG).to_numpy())
            self.dense_codes = codes[dense_pos]
            self.emb = emb[emb_rows[dense_pos]]

    def set_bm25(self, k1: float, b: float) -> None:
        self.bm25 = BM25Okapi(self.tokens, k1=k1, b=b)

    def _aggregate(self, unit_scores: np.ndarray, codes: np.ndarray, dense: bool = False) -> np.ndarray:
        out = np.full(len(self.doc_ids), -np.inf)
        np.maximum.at(out, codes, unit_scores)
        out[self.exclude_all] = -np.inf
        if dense:
            out[self.exclude_dense] = -np.inf
        return out

    def bm25_scores(self, tokens: list[str]) -> np.ndarray:
        return self._aggregate(self.bm25.get_scores(tokens), self.codes)

    def dense_scores(self, qvec: np.ndarray) -> np.ndarray:
        if self.emb is None:
            raise RuntimeError("Dense tidak dimuatkan (use_dense=False).")
        return self._aggregate(self.emb @ qvec, self.dense_codes, dense=True)


class Searcher:
    def __init__(self, model_name: str = DEFAULT_MODEL, use_dense: bool = True,
                 rrf_k: int = 60, rrf_depth: int = 100,
                 w_bm25: float = 1.0, w_dense: float = 1.0,
                 emb_variant: str = DEFAULT_EMB_VARIANT,
                 stop_modes: dict | None = None,
                 stem: dict | None = None):
        units = pd.read_parquet(UNITS_PATH)
        self.corpus = pd.read_parquet(CORPUS_PATH).set_index("id")
        self.rrf_k = rrf_k
        self.rrf_depth = rrf_depth
        self.weights = {"bm25": w_bm25, "dense": w_dense}
        self.stop_modes = {**QUERY_STOP_MODE, **(stop_modes or {})}
        self.stem = {**STEM_SECTIONS, **(stem or {})}

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

        flag_cols = [c for c in ("is_xref", "is_muqattaat") if c in self.corpus.columns]
        flags = self.corpus[flag_cols] if flag_cols else None

        self.sections = {}
        for name, sources in SECTIONS.items():
            idx = np.flatnonzero(units["source"].isin(sources).to_numpy())
            field = "text"
            if self.stem.get(name):
                if "bm25_text" in units.columns:
                    field = "bm25_text"
                else:
                    print(f"AMARAN: kolum bm25_text tiada; stemming {name} dimatikan. Jalankan units.py.")
                    self.stem[name] = False
            self.sections[name] = Section(units.iloc[idx], emb_row[idx], emb, flags, field=field,
                                          **BM25_PARAMS.get(name, {}))

        self._qcache: dict[str, np.ndarray] = {}

    def _qvec(self, query: str) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Dense tidak dimuatkan (use_dense=False).")
        if len(self._qcache) > QCACHE_MAX:
            self._qcache.clear()
        if query not in self._qcache:
            self._qcache[query] = self.model.encode(
                [query_prefix(self.model_name) + query], normalize_embeddings=True)[0]
        return self._qcache[query]

    def bm25_query_tokens(self, query: str, section: str) -> list[str]:
        tokens = query_tokens(query, self.stop_modes[section])
        if self.stem.get(section):
            tokens = expand_with_stems(tokens)
        return tokens

    def doc_scores(self, query: str, method: str, section: str) -> np.ndarray:
        sec = self.sections[section]
        if method == "bm25":
            return sec.bm25_scores(self.bm25_query_tokens(query, section))
        return sec.dense_scores(self._qvec(query))

    def top_bm25(self, query: str, section: str) -> float:
        return float(self.doc_scores(query, "bm25", section).max())

    @staticmethod
    def _neighbours(doc_id: str, n: int) -> list[str]:
        parts = doc_id.split(":")
        if parts[0] == "quran" and len(parts) == 3:
            s, a = int(parts[1]), int(parts[2])
            return [f"quran:{s}:{a + d}" for d in range(-n, n + 1)]
        return [doc_id]

    def similar(self, doc_id: str, target_section: str, k: int = 5, exclude_neighbours: int = 1):
        """Dokumen dengan maksud paling dekat (embedding) dalam bahagian sasaran."""
        try:
            src = self.sections[section_of(doc_id)]
        except StopIteration:
            raise KeyError(doc_id)
        if src.emb is None:
            raise RuntimeError("Dense tidak dimuatkan.")
        pos = src.doc_index[doc_id]
        rows = np.flatnonzero(src.dense_codes == pos)
        if len(rows) == 0:
            raise KeyError(doc_id)
        vec = src.emb[rows].mean(axis=0)
        vec /= np.linalg.norm(vec)

        tgt = self.sections[target_section]
        scores = tgt.dense_scores(vec)
        for nb in self._neighbours(doc_id, exclude_neighbours):
            i = tgt.doc_index.get(nb)
            if i is not None:
                scores[i] = -np.inf
        idx = self._top(scores, k)
        return tgt.doc_ids[idx], scores[idx]

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
                scores = self.doc_scores(query, m, section)
                top = self._top(scores, self.rrf_depth)
                # Hanya dokumen yang benar-benar padan menyumbang kepada RRF
                valid = np.isfinite(scores[top])
                if m == "bm25":
                    valid &= scores[top] > 0
                top = top[valid]
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
    parser.add_argument("--stem", choices=list(STEM_CHOICES))
    args = parser.parse_args()

    methods = METHODS if args.method == "all" else [args.method]
    searcher = Searcher(args.model, use_dense=any(m != "bm25" for m in methods),
                        stem=STEM_CHOICES[args.stem] if args.stem else None)
    for sec in SECTIONS:
        print(f"[{sec}] token BM25: {searcher.bm25_query_tokens(args.query, sec)}")
    for m in methods:
        for sec in SECTIONS:
            print(f"\n=== {m.upper()} | {sec.upper()} "
                  f"(BM25 teratas: {searcher.top_bm25(args.query, sec):.1f}) ===")
            print_results(searcher.search(args.query, m, args.k, section=sec))


if __name__ == "__main__":
    main()