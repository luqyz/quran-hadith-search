"""
Bantu pilih threshold BM25 & semak pengesan niat terhadap testset.

    python src/eval/pick_thresholds.py
"""
import glob
import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import pandas as pd

from intent import detect_intent
from run_eval import RESULTS_DIR, TESTSET_PATH


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positives", choices=["all", "manual"], default="all",
                        help="'manual' = guna soalan manual sahaja sebagai positif")
    args = parser.parse_args()
    files = [f for f in sorted(glob.glob(str(RESULTS_DIR / "*.csv")))
             if not Path(f).name.startswith("tune_")]
    res = pd.read_csv(files[-1])
    print(f"Guna: {Path(files[-1]).name}\n")

    th = res.drop_duplicates(["qid", "section"]).copy()
    th["kategori"] = th["type"].where(th.type.str.startswith("negative"), "positif")

    for sec in ("quran", "hadith"):
        d = th[th.section == sec]
        pos_rows = d[d.kategori == "positif"]
        if args.positives == "manual":
            pos_rows = pos_rows[pos_rows.type == "manual"]
        pos = pos_rows.bm25_top
        neg = d[d.kategori == "negative"].bm25_top
        hard = d[d.kategori == "negative_hard"].bm25_top
        print(f"=== {sec.upper()} ===")
        print(f"{'T':>5} {'positif kekal':>14} {'negatif ditolak':>16} {'sukar ditolak':>14}")
        for t in range(8, 21):
            print(f"{t:>5} {(pos >= t).mean():>14.0%} {(neg < t).mean():>16.0%} {(hard < t).mean():>14.0%}")
        print()

    with open(TESTSET_PATH, encoding="utf-8") as f:
        testset = [json.loads(line) for line in f]
    intents = pd.DataFrame([{"type": q["type"], "notice": detect_intent(q["query"]) or "-"}
                            for q in testset])
    print("=== Pengesan niat mengikut jenis soalan ===")
    print(pd.crosstab(intents["type"], intents["notice"]).to_string())

    flagged_pos = [q["query"] for q in testset
                   if not q["type"].startswith("negative") and detect_intent(q["query"])]
    if flagged_pos:
        print("\nSoalan positif yang tersalah ditanda:")
        for q in flagged_pos:
            print(" -", q)


if __name__ == "__main__":
    main()