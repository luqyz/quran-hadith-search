"""
Anggaran kadar halusinasi dalam terjemahan mesin hadis.

    python src/eval/check_mt.py
"""
import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd

from common import MT_LANG, UNITS_PATH

# Nama nabi dalam terjemahan BM, dengan corak padanan dalam teks English asal
from mt_quality import added_names as _added_names


def added_names(row) -> list[str]:
    return _added_names(row.text_en, row.text_ms)


def main() -> None:
    units = pd.read_parquet(UNITS_PATH)
    en = units[(units.lang == "en") & (units.source != "quran")][["doc_id", "chunk_no", "text"]]
    mt = units[units.lang == MT_LANG][["doc_id", "chunk_no", "text"]]
    pair = en.merge(mt, on=["doc_id", "chunk_no"], suffixes=("_en", "_ms"))

    pair["added"] = pair.apply(added_names, axis=1)
    pair["ratio"] = pair.text_ms.str.split().str.len() / pair.text_en.str.split().str.len()

    has_added = pair.added.str.len() > 0
    odd_len = (pair.ratio < 0.5) | (pair.ratio > 2)
    print(f"Jumlah unit dibandingkan: {len(pair):,}")
    print(f"Nama nabi ditambah (tiada dalam asal): {has_added.sum():,} ({has_added.mean():.2%})")
    print(f"Nisbah panjang luar biasa (<0.5 atau >2): {odd_len.sum():,} ({odd_len.mean():.2%})")

    print("\n=== Contoh nama ditambah ===")
    for r in pair[has_added].head(5).itertuples():
        print(f"\n{r.doc_id} (chunk {r.chunk_no}) +{r.added}")
        print("  EN:", r.text_en[:160])
        print("  MS:", r.text_ms[:160])


if __name__ == "__main__":
    main()