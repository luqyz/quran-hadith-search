"""
API carian Quran & hadis.

    uvicorn api:app --app-dir src/app --port 8000
    # kemudian buka http://localhost:8000/docs
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from common import BM25_THRESHOLDS
from intent import detect_intent
from search import SECTIONS, Searcher

COLLECTION_NAMES = {"bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim"}
state = {}


def clean(value):
    return value if isinstance(value, str) and value.strip() else None


def ayah_brief(corpus, surah: int, ayah: int):
    doc_id = f"quran:{surah}:{ayah}"
    if doc_id not in corpus.index:
        return None
    row = corpus.loc[doc_id]
    return {"ref": row["ref"], "text_ms": clean(row["text_ms"])}


def format_quran(doc_id, row, corpus) -> dict:
    surah, ayah = int(row.book_no), int(row.item_no)
    return {
        "id": doc_id, "ref": row.ref, "surah": surah, "ayah": ayah,
        "surah_name": row.chapter_title,
        "text_ar": clean(row.text_ar), "text_ms": clean(row.text_ms), "text_en": clean(row.text_en),
        "context": {"prev": ayah_brief(corpus, surah, ayah - 1),
                    "next": ayah_brief(corpus, surah, ayah + 1)},
    }


def format_hadith(doc_id, row, corpus) -> dict:
    return {
        "id": doc_id, "ref": row.ref,
        "collection": COLLECTION_NAMES.get(row.source, row.source),
        "book_title": row.chapter_title,
        "text_ar": clean(row.text_ar), "text_en": clean(row.text_en),
        # Terjemahan mesin TIDAK dipulangkan; hanya teks sahih dipaparkan
        "grade": clean(row.grade), "grade_source": clean(row.grade_source),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["searcher"] = Searcher()
    yield
    state.clear()


app = FastAPI(title="Carian Quran & Hadis", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "ready": "searcher" in state}


@app.get("/search")
def search(q: str = Query(..., min_length=2, max_length=200),
           k: int = Query(5, ge=1, le=10)):
    searcher = state["searcher"]
    corpus = searcher.corpus
    q = q.strip()

    sections = {}
    for sec in SECTIONS:
        ids, scores = searcher.rank(q, "hybrid", k, sec)
        rows = corpus.loc[ids]
        fmt = format_quran if sec == "quran" else format_hadith
        top_bm25 = searcher.top_bm25(q, sec)
        sections[sec] = {
            "confident": bool(top_bm25 >= BM25_THRESHOLDS[sec]),
            "results": [{**fmt(doc_id, row, corpus), "score": round(float(s), 5)}
                        for doc_id, row, s in zip(ids, rows.itertuples(index=False), scores)],
        }

    return {"query": q, "notice": detect_intent(q), "sections": sections}