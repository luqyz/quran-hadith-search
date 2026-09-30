"""
Tukar corpus kepada unit carian.

    python src/retrieval/units.py            # guna terjemahan hadis jika ada
    python src/retrieval/units.py --no-mt    # abaikan terjemahan (baseline)
"""
import argparse
import pandas as pd
import time
from mt_quality import suspect_reasons
from common import (CORPUS_PATH, CTX_MAX_WORDS, CTX_WINDOW, INDEX_DIR, MS_LANGS, MT_PATH,
                    UNITS_PATH, stem_tokens, tokenize)

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


def quran_lookup(corpus: pd.DataFrame) -> dict:
    """{lang: {(surah, ayat): teks}} untuk mencari ayat jiran."""
    q = corpus[corpus.source == "quran"]
    return {lang: {(int(r.book_no), int(r.item_no)): getattr(r, f"text_{lang}")
                   for r in q.itertuples(index=False)}
            for lang in ("ms", "en")}


def with_context(text: str, lang: str, surah: int, ayah: int, lookup: dict) -> str:
    """Ayat pendek digabung dengan jirannya dalam surah yang sama."""
    if len(text.split()) >= CTX_MAX_WORDS:
        return text
    d = lookup[lang]
    parts = [d.get((surah, ayah + off)) for off in range(-CTX_WINDOW, CTX_WINDOW + 1)]
    return " ".join(p for p in parts if has_text(p))


def build_units(corpus: pd.DataFrame, mt: pd.DataFrame | None = None) -> pd.DataFrame:
    lookup = quran_lookup(corpus)
    rows = []
    en_chunks = {}  # {(doc_id, chunk_no): chunk} untuk semak terjemahan mesin
    for doc in corpus.itertuples(index=False):
        if doc.source == "quran":
            surah, ayah = int(doc.book_no), int(doc.item_no)
            for lang in ("ms", "en"):
                text = getattr(doc, f"text_{lang}")
                if has_text(text):
                    rows.append({"doc_id": doc.id, "source": doc.source, "lang": lang,
                                 "chunk_no": 0, "text": text,
                                 "ctx_text": with_context(text, lang, surah, ayah, lookup)})
        elif has_text(doc.text_en):
            for i, chunk in enumerate(chunk_words(doc.text_en)):
                rows.append({"doc_id": doc.id, "source": doc.source, "lang": "en",
                             "chunk_no": i, "text": chunk, "ctx_text": chunk})
                en_chunks[(doc.id, i)] = chunk

    # Unit terjemahan mesin ditambah DI HUJUNG supaya unit_id asal tidak berubah.
    # Ia hanya untuk carian BM25; teks yang dipaparkan tetap dari corpus asal.
        skipped = {}
    if mt is not None:
        for r in mt.itertuples(index=False):
            if not has_text(r.text_ms_mt):
                continue
            reasons = suspect_reasons(en_chunks.get((r.doc_id, r.chunk_no), ""), r.text_ms_mt)
            if reasons:
                for reason in reasons:
                    skipped[reason] = skipped.get(reason, 0) + 1
                continue
            rows.append({"doc_id": r.doc_id, "source": r.doc_id.split(":")[0],
                         "lang": "ms_mt", "chunk_no": r.chunk_no,
                         "text": r.text_ms_mt, "ctx_text": r.text_ms_mt})
        if skipped:
            print(f"Terjemahan meragukan ditapis: {skipped}")

    # Nota: chapter_title sengaja TIDAK dimasukkan (elak kebocoran semasa evaluation)
    units = pd.DataFrame(rows)
    units.insert(0, "unit_id", range(len(units)))
    return units


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-mt", action="store_true", help="abaikan terjemahan mesin hadis")
    parser.add_argument("--mt-file", default=MT_PATH.name, help="nama fail terjemahan dalam data/index")
    args = parser.parse_args()

    corpus = pd.read_parquet(CORPUS_PATH)
    mt_path = INDEX_DIR / args.mt_file
    mt = None
    if not args.no_mt and mt_path.exists():
        mt = pd.read_parquet(mt_path)
        print(f"Guna terjemahan hadis: {mt_path.name} ({len(mt):,} unit)")
    else:
        print("Tanpa terjemahan hadis")

    units = build_units(corpus, mt)
    print("Mengira kata dasar untuk unit BM...")
    start = time.time()
    is_ms = units["lang"].isin(MS_LANGS)
    units["bm25_text"] = units["text"]
    units.loc[is_ms, "bm25_text"] = units.loc[is_ms, "text"].map(
        lambda s: " ".join(stem_tokens(tokenize(s))))
    print(f"  siap dalam {time.time() - start:.0f}s")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    units.to_parquet(UNITS_PATH, index=False)

    print("\n=== Unit mengikut sumber & bahasa ===")
    print(units.groupby(["source", "lang"]).size().to_string())
    n_ctx = (units["ctx_text"] != units["text"]).sum()
    print(f"\nUnit Quran yang diberi konteks (< {CTX_MAX_WORDS} perkataan): {n_ctx:,}")
    print(f"Disimpan: {UNITS_PATH} ({len(units):,} unit)")


if __name__ == "__main__":
    main()