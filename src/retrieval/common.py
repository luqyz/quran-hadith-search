"""Tetapan & fungsi kongsi untuk retrieval."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "data" / "processed" / "corpus.parquet"
INDEX_DIR = ROOT / "data" / "index"
UNITS_PATH = INDEX_DIR / "units.parquet"

DEFAULT_MODEL = "intfloat/multilingual-e5-base"

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def model_slug(model_name: str) -> str:
    return model_name.split("/")[-1]


def emb_path(model_name: str) -> Path:
    return INDEX_DIR / f"emb_{model_slug(model_name)}.npy"


def is_e5(model_name: str) -> bool:
    return "e5" in model_name.lower()


def passage_prefix(model_name: str) -> str:
    # Model e5 dilatih dengan prefix ini; tanpanya prestasi jatuh
    return "passage: " if is_e5(model_name) else ""


def query_prefix(model_name: str) -> str:
    return "query: " if is_e5(model_name) else ""