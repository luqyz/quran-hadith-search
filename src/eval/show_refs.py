"""
Papar teks bagi setiap rujukan dalam eval/manual_queries.csv untuk disemak.

    python src/eval/show_refs.py                    # semua soalan
    python src/eval/show_refs.py --contains Bukhari # soalan hadis sahaja
"""
import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd

from build_testset import MANUAL_PATH, ref_to_id
from common import CORPUS_PATH


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contains", default="", help="tapis rujukan yang mengandungi teks ini")
    args = parser.parse_args()

    corpus = pd.read_parquet(CORPUS_PATH).set_index("id")
    manual = pd.read_csv(MANUAL_PATH, encoding="utf-8-sig").dropna(subset=["query", "relevant"])

    for r in manual.itertuples():
        if args.contains and args.contains.lower() not in str(r.relevant).lower():
            continue
        print(f"\n### {r.query}")
        for ref in str(r.relevant).split(";"):
            ref = ref.strip()
            if not ref:
                continue
            doc_id = ref_to_id(ref)
            if doc_id not in corpus.index:
                print(f"  [TIADA] {ref}")
                continue
            row = corpus.loc[doc_id]
            text = row.text_ms if isinstance(row.text_ms, str) else row.text_en
            print(f"  {ref}: {textwrap.shorten(text, 170, placeholder='...')}")


if __name__ == "__main__":
    main()