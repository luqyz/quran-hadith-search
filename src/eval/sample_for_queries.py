"""
Pilih ayat & hadis rawak untuk dijadikan soalan sintetik.

    python src/eval/sample_for_queries.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd

from common import CORPUS_PATH, ROOT

EVAL_DIR = ROOT / "eval"
OUT_PATH = EVAL_DIR / "synthetic_candidates.csv"

N_QURAN = 150
N_HADITH = 50
MIN_QURAN_WORDS = 8          # ayat terlalu pendek tak bermakna tanpa konteks
HADITH_WORDS = (15, 200)
SEED = 42


def word_count(s: pd.Series) -> pd.Series:
    return s.fillna("").str.split().str.len()


def main() -> None:
    corpus = pd.read_parquet(CORPUS_PATH)

    quran = corpus[(corpus.source == "quran") & (word_count(corpus.text_ms) >= MIN_QURAN_WORDS)]
    quran = quran.sample(N_QURAN, random_state=SEED).assign(text=lambda d: d.text_ms)

    hadith = corpus[(corpus.source != "quran")
                    & word_count(corpus.text_en).between(*HADITH_WORDS)]
    hadith = hadith.sample(N_HADITH, random_state=SEED).assign(text=lambda d: d.text_en)

    out = pd.concat([quran, hadith])[["id", "ref", "text"]].assign(query="")
    EVAL_DIR.mkdir(exist_ok=True)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"Disimpan: {OUT_PATH} ({len(quran)} ayat, {len(hadith)} hadis)")


if __name__ == "__main__":
    main()