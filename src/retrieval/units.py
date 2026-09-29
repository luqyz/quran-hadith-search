"""
Tukar corpus kepada unit carian.

    python src/retrieval/units.py
"""
import pandas as pd

from common import CORPUS_PATH, INDEX_DIR, UNITS_PATH

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


def build_units(corpus: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for doc in corpus.itertuples(index=False):
        if doc.source == "quran":
            # Satu unit per bahasa supaya soalan BM padan dengan teks BM
            for lang in ("ms", "en"):
                text = getattr(doc, f"text_{lang}")
                if has_text(text):
                    rows.append({"doc_id": doc.id, "source": doc.source,
                                 "lang": lang, "chunk_no": 0, "text": text})
        elif has_text(doc.text_en):
            for i, chunk in enumerate(chunk_words(doc.text_en)):
                rows.append({"doc_id": doc.id, "source": doc.source,
                             "lang": "en", "chunk_no": i, "text": chunk})
    # Nota: chapter_title sengaja TIDAK dimasukkan (elak kebocoran semasa evaluation)
    units = pd.DataFrame(rows)
    units.insert(0, "unit_id", range(len(units)))
    return units


def main() -> None:
    corpus = pd.read_parquet(CORPUS_PATH)
    units = build_units(corpus)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    units.to_parquet(UNITS_PATH, index=False)

    print("=== Unit mengikut sumber & bahasa ===")
    print(units.groupby(["source", "lang"]).size().to_string())

    chunks_per_doc = units[units.source != "quran"].groupby("doc_id").size()
    print(f"\nHadis dipecah jadi >1 chunk: {(chunks_per_doc > 1).sum()} "
          f"(maks {chunks_per_doc.max()} chunk)")
    print("\nPanjang unit (perkataan):")
    print(units["text"].str.split().str.len().describe().round(1).to_string())
    print(f"\nDisimpan: {UNITS_PATH} ({len(units):,} unit)")


if __name__ == "__main__":
    main()