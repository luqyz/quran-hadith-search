"""
Eksport data bacaan sebagai JSON statik untuk laman web (dihidangkan oleh Firebase Hosting).

    python scripts/export_static.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "retrieval"))

import pandas as pd

from common import CORPUS_PATH, NAWAWI_PATH, ROOT, SURAHS_PATH

OUT_DIR = ROOT / "web" / "data"
RAW_AR = ROOT / "data" / "raw" / "quran" / "quran-simple.json"   # mengandungi juz & halaman setiap ayat


def clean(value):
    return value if isinstance(value, str) and value.strip() else None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def load_ayah_meta() -> dict:
    """(surah, ayat) -> (juz, halaman mushaf)."""
    if not RAW_AR.exists():
        raise FileNotFoundError(f"{RAW_AR} tiada. Jalankan src/ingest/download.py dahulu.")
    with open(RAW_AR, encoding="utf-8") as f:
        obj = json.load(f)
    obj = obj.get("data", obj)
    return {(s["number"], a["numberInSurah"]): (a["juz"], a["page"])
            for s in obj["surahs"] for a in s["ayahs"]}


def main() -> None:
    with open(SURAHS_PATH, encoding="utf-8") as f:
        surahs = sorted(json.load(f), key=lambda s: s["number"])
    meta = {s["number"]: s for s in surahs}
    write_json(OUT_DIR / "surahs.json", surahs)

    ayah_meta = load_ayah_meta()
    corpus = pd.read_parquet(CORPUS_PATH)
    quran = corpus[corpus["source"] == "quran"].sort_values(["book_no", "item_no"])

    by_surah = defaultdict(list)
    by_juz = defaultdict(list)
    for r in quran.itertuples(index=False):
        s, a = int(r.book_no), int(r.item_no)
        juz, page = ayah_meta[(s, a)]
        text = {"ref": r.ref, "page": page, "text_ar": clean(r.text_ar),
                "text_ms": clean(r.text_ms), "text_en": clean(r.text_en)}
        by_surah[s].append({"ayah": a, **text})
        by_juz[juz].append({"s": s, "a": a, **text})

    for s, ayahs in by_surah.items():
        write_json(OUT_DIR / "surah" / f"{s}.json", {"surah": meta.get(s), "ayahs": ayahs})

    juz_list = []
    for j in sorted(by_juz):
        ayahs = by_juz[j]
        first, last = ayahs[0], ayahs[-1]
        write_json(OUT_DIR / "juz" / f"{j}.json", {"juz": j, "ayahs": ayahs})
        juz_list.append({
            "number": j,
            "start": {"s": first["s"], "a": first["a"], "name": meta[first["s"]]["english_name"]},
            "end": {"s": last["s"], "a": last["a"], "name": meta[last["s"]]["english_name"]},
            "surahs": sorted({x["s"] for x in ayahs}),
            "ayah_count": len(ayahs),
        })
    write_json(OUT_DIR / "juz.json", juz_list)

    with open(NAWAWI_PATH, encoding="utf-8") as f:
        nawawi = json.load(f)
    write_json(OUT_DIR / "nawawi.json", nawawi)

    total = sum(len(v) for v in by_surah.values())
    pages = {p for _, p in ayah_meta.values()}
    assert total == 6236, f"Bilangan ayat tak dijangka: {total}"
    assert len(juz_list) == 30, f"Bilangan juz tak dijangka: {len(juz_list)}"
    files = list(OUT_DIR.rglob("*.json"))
    size_mb = sum(p.stat().st_size for p in files) / 1e6
    print(f"Disimpan dalam {OUT_DIR}: {len(surahs)} surah, 30 juz, {len(pages)} halaman, "
          f"{total:,} ayat, {len(nawawi)} hadis ({len(files)} fail, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()