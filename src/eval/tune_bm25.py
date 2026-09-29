"""
Tala parameter BM25 (k1, b) untuk satu bahagian.
Ditala pada soalan SINTETIK; soalan MANUAL sebagai semakan bebas.

    python src/eval/tune_bm25.py --model intfloat/multilingual-e5-base
"""
import argparse
import itertools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd

from common import DEFAULT_MODEL
from run_eval import RESULTS_DIR, TESTSET_PATH, recall_at_k, rr_at_k
from search import Searcher, section_of

GRID_K1 = [0.9, 1.2, 1.5, 2.0]
GRID_B = [0.3, 0.5, 0.75, 0.9]
METRICS = ["recall@5", "recall@10", "mrr@10"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--section", default="quran", choices=["quran", "hadith"])
    args = parser.parse_args()

    with open(TESTSET_PATH, encoding="utf-8") as f:
        testset = [json.loads(line) for line in f]

    queries = []
    for q in testset:
        rel = {d for d in q["relevant"] if section_of(d) == args.section}
        if rel:
            split = "tune" if q["type"].startswith("synthetic") else "check"
            queries.append((q["query"], rel, split))
    n_tune = sum(s == "tune" for *_, s in queries)
    print(f"Bahagian {args.section}: {n_tune} soalan tala (sintetik), "
          f"{len(queries) - n_tune} soalan semakan (manual)")

    searcher = Searcher(args.model)
    sec = searcher.sections[args.section]

    rows = []
    for k1, b in itertools.product(GRID_K1, GRID_B):
        start = time.time()
        sec.set_bm25(k1, b)
        for method in ("bm25", "hybrid"):
            for query, rel, split in queries:
                ids, _ = searcher.rank(query, method, 10, args.section)
                ranked = list(ids)
                rows.append({"k1": k1, "b": b, "method": method, "split": split,
                             "recall@5": recall_at_k(ranked, rel, 5),
                             "recall@10": recall_at_k(ranked, rel, 10),
                             "mrr@10": rr_at_k(ranked, rel, 10)})
        print(f"  k1={k1}, b={b} siap ({time.time() - start:.0f}s)")

    df = pd.DataFrame(rows)
    table = df.groupby(["method", "split", "k1", "b"])[METRICS].mean().round(3)

    for method in ("bm25", "hybrid"):
        t = table.loc[method].unstack("split")
        t = t.sort_values([("recall@10", "tune"), ("mrr@10", "tune")], ascending=False)
        print(f"\n=== {method.upper()}: 6 terbaik mengikut soalan tala ===")
        print(t.head(6).to_string())
        if (1.5, 0.75) in t.index:
            print(f"\nLalai (k1=1.5, b=0.75):")
            print(t.loc[[(1.5, 0.75)]].to_string())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"tune_bm25_{args.section}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nButiran: {out}")


if __name__ == "__main__":
    main()