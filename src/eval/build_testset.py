"""
Gabungkan soalan sintetik, manual & negatif jadi eval/testset.jsonl.

    python src/eval/build_testset.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd

from common import CORPUS_PATH, ROOT

EVAL_DIR = ROOT / "eval"
SYNTH_PATH = EVAL_DIR / "synthetic_queries.csv"
MANUAL_PATH = EVAL_DIR / "manual_queries.csv"
OUT_PATH = EVAL_DIR / "testset.jsonl"

NEGATIVE_QUERIES = [
    "resepi nasi lemak sambal sotong",
    "cara tukar tayar kereta",
    "keputusan perlawanan bola sepak semalam",
    "harga emas hari ini",
    "cara install python di windows",
    "laptop terbaik untuk pelajar universiti",
    "jadual tren KTM Komuter",
    "cara menulis resume untuk fresh graduate",
    "tips menanam cili dalam pasu",
    "how to fix a leaking tap",
    "best budget smartphone 2026",
    "cara renew lesen memandu",
]


def ref_to_id(ref: str) -> str:
    """'2:153' -> 'quran:2:153', 'Bukhari 1283' -> 'bukhari:1283'."""
    ref = ref.strip()
    if ":" in ref and ref.split(":")[0].isdigit():
        return f"quran:{ref}"
    name, num = ref.rsplit(" ", 1)
    return f"{name.strip().lower()}:{num.strip()}"


def main() -> None:
    valid_ids = set(pd.read_parquet(CORPUS_PATH, columns=["id"])["id"])
    rows = []

    if SYNTH_PATH.exists():
        synth = pd.read_csv(SYNTH_PATH, encoding="utf-8-sig").dropna(subset=["query"])
        for r in synth.itertuples():
            qtype = "synthetic_quran" if r.id.startswith("quran:") else "synthetic_hadith"
            rows.append({"query": r.query.strip(), "type": qtype, "relevant": [r.id]})
    else:
        print(f"(tiada {SYNTH_PATH.name}, dilangkau)")

    if MANUAL_PATH.exists():
        manual = pd.read_csv(MANUAL_PATH, encoding="utf-8-sig").dropna(subset=["query", "relevant"])
        for r in manual.itertuples():
            ids = [ref_to_id(x) for x in str(r.relevant).split(";") if x.strip()]
            unknown = [i for i in ids if i not in valid_ids]
            if unknown:
                print(f"AMARAN: '{r.query}' ada rujukan tak wujud: {unknown}")
            ids = [i for i in ids if i in valid_ids]
            if ids:
                rows.append({"query": r.query.strip(), "type": "manual", "relevant": ids})

    for q in NEGATIVE_QUERIES:
        rows.append({"query": q, "type": "negative", "relevant": []})

    

    EVAL_DIR.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for i, row in enumerate(rows):
            f.write(json.dumps({"qid": f"q{i:04d}", **row}, ensure_ascii=False) + "\n")

    counts = pd.Series([r["type"] for r in rows]).value_counts()
    print(counts.to_string())
    print(f"\nDisimpan: {OUT_PATH} ({len(rows)} soalan)")


if __name__ == "__main__":
    main()