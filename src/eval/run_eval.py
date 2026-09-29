"""
Nilai kaedah carian terhadap testset, secara berasingan untuk Quran dan hadis.

    python src/eval/run_eval.py --model intfloat/multilingual-e5-base --tag sections
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd

from common import DEFAULT_MODEL, ROOT, model_slug
from search import METHODS, SECTIONS, Searcher, section_of

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
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--w-bm25", type=float, default=1.0)
    parser.add_argument("--w-dense", type=float, default=1.0)
    parser.add_argument("--emb-variant", default="", choices=["", "ctx"])
    parser.add_argument("--tag", default="", help="label tambahan untuk nama fail keputusan")
    args = parser.parse_args()

    with open(TESTSET_PATH, encoding="utf-8") as f:
        testset = [json.loads(line) for line in f]

    searcher = Searcher(args.model, use_dense=any(m != "bm25" for m in args.methods),
                    rrf_k=args.rrf_k, w_bm25=args.w_bm25, w_dense=args.w_dense,
                    emb_variant=args.emb_variant)

    bm25_top_cache = {}
    rows = []
    for method in args.methods:
        for q in testset:
            relevant = set(q["relevant"])
            # Soalan positif dinilai dalam bahagian jawapannya; negatif dalam kedua-dua bahagian
            sections = sorted({section_of(d) for d in relevant}) if relevant else list(SECTIONS)
            for sec in sections:
                res = searcher.search(q["query"], method, args.k, section=sec)
                ranked = res["doc_id"].tolist()
                key = (q["query"], sec)
                if key not in bm25_top_cache:
                    bm25_top_cache[key] = searcher.top_bm25(q["query"], sec)
                row = {"qid": q["qid"], "type": q["type"], "method": method, "section": sec,
                       "query": q["query"], "top_ref": res["ref"].iloc[0],
                       "top_score": res["score"].iloc[0], "bm25_top": bm25_top_cache[key]}
                rel_sec = {d for d in relevant if section_of(d) == sec}
                if rel_sec:
                    row.update({
                        "recall@5": recall_at_k(ranked, rel_sec, 5),
                        f"recall@{args.k}": recall_at_k(ranked, rel_sec, args.k),
                        f"mrr@{args.k}": rr_at_k(ranked, rel_sec, args.k),
                    })
                rows.append(row)
        print(f"[{method}] selesai {len(testset)} soalan")

    df = pd.DataFrame(rows)
    metric_cols = ["recall@5", f"recall@{args.k}", f"mrr@{args.k}"]

    print(f"\n=== Keputusan (rrf_k={args.rrf_k}, w_bm25={args.w_bm25}, w_dense={args.w_dense}) ===")
    pos = df[df.type != "negative"]
    summary = pos.groupby(["type", "section", "method"])[metric_cols].mean().round(3)
    overall = pos.groupby(["section", "method"])[metric_cols].mean().round(3)
    overall.index = pd.MultiIndex.from_tuples([("SEMUA", *i) for i in overall.index],
                                              names=summary.index.names)
    print(pd.concat([summary, overall]).to_string())

    print("\n=== Skor BM25 teratas: positif vs negatif (untuk threshold) ===")
    th = df[df.method == args.methods[0]].copy()
    th["kategori"] = th["type"].where(th.type == "negative", "positif")
    print(th.groupby(["section", "kategori"])["bm25_top"]
          .describe()[["mean", "min", "max"]].round(2).to_string())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    tag = f"_{args.tag}" if args.tag else ""
    out = RESULTS_DIR / f"{stamp}_{model_slug(args.model)}{tag}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nButiran setiap soalan: {out}")


if __name__ == "__main__":
    main()