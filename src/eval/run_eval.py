"""
Nilai kaedah carian terhadap testset.

    python src/eval/run_eval.py --methods bm25
    python src/eval/run_eval.py --methods bm25 dense --model intfloat/multilingual-e5-base
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd

from common import DEFAULT_MODEL, ROOT, model_slug
from search import Searcher

EVAL_DIR = ROOT / "eval"
TESTSET_PATH = EVAL_DIR / "testset.jsonl"
RESULTS_DIR = EVAL_DIR / "results"


def recall_at_k(ranked, relevant, k):
    return len(set(ranked[:k]) & relevant) / len(relevant)


def rr_at_k(ranked, relevant, k):
    for rank, doc in enumerate(ranked[:k], start=1):
        if doc in relevant:
            return 1.0 / rank
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--methods", nargs="+", choices=["bm25", "dense"], default=["bm25", "dense"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    with open(TESTSET_PATH, encoding="utf-8") as f:
        testset = [json.loads(line) for line in f]

    searcher = Searcher(args.model, use_dense="dense" in args.methods)
    rows = []
    for method in args.methods:
        for q in testset:
            res = searcher.search(q["query"], method, args.k)
            ranked = res["doc_id"].tolist()
            relevant = set(q["relevant"])
            row = {"qid": q["qid"], "type": q["type"], "method": method,
                   "query": q["query"], "top_score": res["score"].iloc[0],
                   "top_ref": res["ref"].iloc[0]}
            if relevant:
                row.update({
                    "recall@5": recall_at_k(ranked, relevant, 5),
                    f"recall@{args.k}": recall_at_k(ranked, relevant, args.k),
                    f"mrr@{args.k}": rr_at_k(ranked, relevant, args.k),
                })
            rows.append(row)
        print(f"[{method}] selesai {len(testset)} soalan")

    df = pd.DataFrame(rows)
    metric_cols = ["recall@5", f"recall@{args.k}", f"mrr@{args.k}"]

    print("\n=== Keputusan (soalan positif) ===")
    pos = df[df.type != "negative"]
    summary = pos.groupby(["type", "method"])[metric_cols].mean().round(3)
    overall = pos.groupby("method")[metric_cols].mean().round(3)
    overall.index = pd.MultiIndex.from_product([["SEMUA"], overall.index])
    print(pd.concat([summary, overall]).to_string())

    print("\n=== Skor teratas: positif vs negatif (untuk threshold) ===")
    df["kategori"] = df["type"].where(df.type == "negative", "positif")
    print(df.groupby(["method", "kategori"])["top_score"].describe()[["mean", "min", "max"]].round(3).to_string())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = RESULTS_DIR / f"{stamp}_{model_slug(args.model)}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nButiran setiap soalan: {out}")


if __name__ == "__main__":
    main()