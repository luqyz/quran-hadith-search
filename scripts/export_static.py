"""
Eksport data bacaan sebagai JSON statik untuk laman web (dihidangkan oleh Firebase Hosting).

    python scripts/export_static.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "retrieval"))

import pandas as pd

from common import CORPUS_PATH, NAWAWI_PATH, ROOT, SURAHS_PATH

OUT_DIR = ROOT / "web" / "data"


def clean(value):
    return value if isinstance(value, str) and value.strip() else None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    with open(SURAHS_PATH, encoding="utf-8") as f:
        surahs = sorted(json.load(f), key=lambda s: s["number"])
    meta = {s["number"]: s for s in surahs}
    write_json(OUT_DIR / "surahs.json", surahs)

    corpus = pd.read_parquet(CORPUS_PATH)
    quran = corpus[corpus["source"] == "quran"].sort_values(["book_no", "item_no"])
    total = 0
    for number, rows in quran.groupby("book_no", sort=True):
        number = int(number)
        ayahs = [{
            "ayah": int(r.item_no), "ref": r.ref,
            "text_ar": clean(r.text_ar), "text_ms": clean(r.text_ms), "text_en": clean(r.text_en),
        } for r in rows.itertuples(index=False)]
        write_json(OUT_DIR / "surah" / f"{number}.json", {"surah": meta.get(number), "ayahs": ayahs})
        total += len(ayahs)

    with open(NAWAWI_PATH, encoding="utf-8") as f:
        nawawi = json.load(f)
    write_json(OUT_DIR / "nawawi.json", nawawi)

    files = list(OUT_DIR.rglob("*.json"))
    assert total == 6236, f"Bilangan ayat tak dijangka: {total}"
    size_mb = sum(p.stat().st_size for p in files) / 1e6
    print(f"Disimpan dalam {OUT_DIR}: {len(surahs)} surah, {total:,} ayat, "
          f"{len(nawawi)} hadis ({len(files)} fail, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()