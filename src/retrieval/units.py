"""
Tukar corpus kepada unit carian.

    python src/retrieval/units.py            # guna terjemahan hadis jika ada
    python src/retrieval/units.py --no-mt    # abaikan terjemahan (baseline)
"""
import argparse

import pandas as pd

from common import CORPUS_PATH, INDEX_DIR, MT_PATH, UNITS_PATH

CHUNK_WORDS = 150
CHUNK_OVERLAP = 30


def has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def chunk_words(text: str, size: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [text]
    step = size - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return chunks


def build_units(corpus: pd.DataFrame, mt: pd.DataFrame | None = None) -> pd.DataFrame:
    rows = []
    for doc in corpus.itertuples(index=False):
        if doc.source == "quran":
            for lang in ("ms", "en"):
                text = getattr(doc, f"text_{lang}")
                if has_text(text):
                    rows.append({"doc_id": doc.id, "source": doc.source,
                                 "lang": lang, "chunk_no": 0, "text": text})
        elif has_text(doc.text_en):
            for i, chunk in enumerate(chunk_words(doc.text_en)):
                rows.append({"doc_id": doc.id, "source": doc.source,
                             "lang": "en", "chunk_no": i, "text": chunk})

    # Unit terjemahan mesin ditambah DI HUJUNG supaya unit_id asal tidak berubah.
    # Ia hanya untuk carian; teks yang dipaparkan tetap dari corpus asal.
    if mt is not None:
        for r in mt.itertuples(index=False):
            if has_text(r.text_ms_mt):
                rows.append({"doc_id": r.doc_id, "source": r.doc_id.split(":")[0],
                             "lang": "ms_mt", "chunk_no": r.chunk_no, "text": r.text_ms_mt})

    # Nota: chapter_title sengaja TIDAK dimasukkan (elak kebocoran semasa evaluation)
    units = pd.DataFrame(rows)
    units.insert(0, "unit_id", range(len(units)))
    return units


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-mt", action="store_true", help="abaikan terjemahan mesin hadis")
    args = parser.parse_args()

    corpus = pd.read_parquet(CORPUS_PATH)
    mt = None
    if not args.no_mt and MT_PATH.exists():
        mt = pd.read_parquet(MT_PATH)
        print(f"Guna terjemahan hadis: {MT_PATH.name} ({len(mt):,} unit)")
    else:
        print("Tanpa terjemahan hadis")

    units = build_units(corpus, mt)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    units.to_parquet(UNITS_PATH, index=False)

    print("\n=== Unit mengikut sumber & bahasa ===")
    print(units.groupby(["source", "lang"]).size().to_string())
    print(f"\nDisimpan: {UNITS_PATH} ({len(units):,} unit)")


if __name__ == "__main__":
    main()