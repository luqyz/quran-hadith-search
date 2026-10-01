"""
API carian Quran & hadis.

Tempatan:  uvicorn api:app --app-dir src/app --port 8000
Deploy:    Cloud Run; fail index dimuat turun dari repo dataset peribadi Hugging Face.
"""
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from common import (BM25_THRESHOLDS, CORPUS_PATH, DEFAULT_EMB_VARIANT, DEFAULT_MODEL, NAWAWI_PATH,
                    ROOT, SURAHS_PATH, UNITS_PATH, emb_path)
from intent import detect_intent
from search import SECTIONS, Searcher

COLLECTION_NAMES = {"bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim"}
REQUIRED_FILES = [CORPUS_PATH, UNITS_PATH, SURAHS_PATH, NAWAWI_PATH,
                  emb_path(DEFAULT_MODEL, DEFAULT_EMB_VARIANT)]
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
state = {}


def ensure_artifacts() -> None:
    """Muat turun fail index yang tiada dari repo dataset (ARTIFACT_REPO)."""
    missing = [p for p in REQUIRED_FILES if not p.exists()]
    if not missing:
        return
    repo = os.environ.get("ARTIFACT_REPO")
    if not repo:
        raise RuntimeError(f"Fail index tiada dan ARTIFACT_REPO tidak ditetapkan: {missing}")
    from huggingface_hub import hf_hub_download
    for p in missing:
        rel = p.relative_to(ROOT).as_posix()
        print(f"Memuat turun {rel} dari {repo}...", flush=True)
        hf_hub_download(repo_id=repo, filename=rel, repo_type="dataset",
                        local_dir=ROOT, token=os.environ.get("HF_TOKEN"))


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
    meta = state.get("surahs", {}).get(surah, {})
    return {
        "id": doc_id, "ref": row.ref, "surah": surah, "ayah": ayah,
        "surah_name": row.chapter_title,
        "surah_name_ar": meta.get("name_ar"),
        "revelation": meta.get("revelation"),
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
    ensure_artifacts()
    with open(SURAHS_PATH, encoding="utf-8") as f:
        state["surahs"] = {s["number"]: s for s in json.load(f)}
    with open(NAWAWI_PATH, encoding="utf-8") as f:
        state["nawawi"] = json.load(f)
    state["searcher"] = Searcher()
    yield
    state.clear()


app = FastAPI(title="Carian Quran & Hadis", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["GET"], allow_headers=["*"])


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok", "ready": "searcher" in state}

@app.get("/surahs")
def surahs():
    return [state["surahs"][n] for n in sorted(state["surahs"])]

@app.get("/nawawi")
def nawawi():
    return state["nawawi"]

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


@app.get("/surah/{number}")
def surah(number: int = PathParam(..., ge=1, le=114)):
    corpus = state["searcher"].corpus
    rows = corpus[(corpus["source"] == "quran") & (corpus["book_no"] == number)].sort_values("item_no")
    return {
        "surah": state["surahs"].get(number),
        "ayahs": [{"ayah": int(r.item_no), "ref": r.ref, "text_ar": clean(r.text_ar),
                   "text_ms": clean(r.text_ms), "text_en": clean(r.text_en)}
                  for r in rows.itertuples(index=False)],
    }


@app.get("/similar/{doc_id}")
def similar(doc_id: str,
            section: str = Query("quran", pattern="^(quran|hadith)$"),
            k: int = Query(5, ge=1, le=10)):
    searcher = state["searcher"]
    try:
        ids, scores = searcher.similar(doc_id, section, k)
    except KeyError:
        raise HTTPException(status_code=404, detail="Dokumen tidak dijumpai")
    corpus = searcher.corpus
    rows = corpus.loc[ids]
    fmt = format_quran if section == "quran" else format_hadith
    return {
        "id": doc_id, "section": section,
        "results": [{**fmt(d, r, corpus), "score": round(float(s), 4)}
                    for d, r, s in zip(ids, rows.itertuples(index=False), scores)],
    }