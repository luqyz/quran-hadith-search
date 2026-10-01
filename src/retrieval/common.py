"""Tetapan & fungsi kongsi untuk retrieval."""
from functools import lru_cache
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "data" / "processed" / "corpus.parquet"
INDEX_DIR = ROOT / "data" / "index"
UNITS_PATH = INDEX_DIR / "units.parquet"
SURAHS_PATH = ROOT / "data" / "processed" / "surahs.json"
NAWAWI_PATH = ROOT / "data" / "processed" / "nawawi.json"
MT_PATH = INDEX_DIR / "hadith_ms_mt_v2.parquet"
MT_LANG = "ms_mt"   # unit terjemahan mesin: untuk BM25 sahaja, tidak di-embed
DEFAULT_EMB_VARIANT = "ctx"

DEFAULT_MODEL = "intfloat/multilingual-e5-base"

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def model_slug(model_name: str) -> str:
    return model_name.split("/")[-1]


CTX_MAX_WORDS = 12   # ayat lebih pendek dari ini diberi konteks (untuk dense sahaja)
CTX_WINDOW = 1       # bilangan ayat jiran di setiap sisi


def emb_path(model_name: str, variant: str = "") -> Path:
    suffix = f"_{variant}" if variant else ""
    return INDEX_DIR / f"emb_{model_slug(model_name)}{suffix}.npy"


def is_e5(model_name: str) -> bool:
    return "e5" in model_name.lower()


def passage_prefix(model_name: str) -> str:
    # Model e5 dilatih dengan prefix ini; tanpanya prestasi jatuh
    return "passage: " if is_e5(model_name) else ""


def query_prefix(model_name: str) -> str:
    return "query: " if is_e5(model_name) else ""

# Parameter BM25 per bahagian (ditala dengan src/eval/tune_bm25.py)
BM25_PARAMS = {
    "quran": {"k1": 1.2, "b": 0.3},
    "hadith": {"k1": 1.5, "b": 0.75},
}

# Threshold keyakinan: skor BM25 teratas bawah nilai ini = "mungkin kurang berkaitan"
# (dipilih dengan src/eval/pick_thresholds.py)
BM25_THRESHOLDS = {"quran": 10.0, "hadith": 11.0}

# Perkataan fungsi (termasuk kata ganti) yang diabaikan oleh BM25 pada soalan
FUNCTION_WORDS = {
    "yang", "dan", "di", "ke", "dari", "daripada", "dalam", "pada", "untuk", "dengan",
    "ini", "itu", "ada", "adalah", "ialah", "akan", "telah", "sudah", "juga", "atau",
    "tetapi", "kerana", "sebab", "bagi", "oleh", "ketika", "semasa", "apabila", "bila",
    "kita", "kami", "saya", "aku", "kamu", "mereka", "nya", "lah", "pun",
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are", "was",
}

# Perkataan yang menerangkan JENIS soalan, bukan topiknya
INTENT_WORDS = {
    "apa", "apakah", "bagaimana", "kenapa", "mengapa", "siapa", "adakah", "tentang",
    "mengenai", "hukum", "ayat", "hadis", "hadith", "quran", "surah", "maksud", "dalil",
    "what", "how", "why", "who", "about", "does", "do", "verse", "verses", "ruling", "regarding",
}

STOPWORD_MODES = {
    "none": set(),
    "intent": INTENT_WORDS,
    "full": FUNCTION_WORDS | INTENT_WORDS,
}

# Tetapan lalai per bahagian (dikemas kini selepas ablation)
QUERY_STOP_MODE = {"quran": "intent", "hadith": "full"}


def query_tokens(query: str, mode: str = "full") -> list[str]:
    """Token soalan untuk BM25; jika semua dibuang, guna token asal."""
    stop = STOPWORD_MODES[mode]
    tokens = tokenize(query)
    kept = [t for t in tokens if t not in stop]
    return kept or tokens

# ---------- Stemming BM (eksperimen) ----------
MS_LANGS = {"ms", "ms_mt"}
STEM_SECTIONS = {"quran": True, "hadith": False}   # dikemas kini selepas eksperimen

_stemmer = None


# Kata dasar ejaan Malaysia (atau ejaan lama Basmeih) yang tiada dalam kamus Sastrawi (Indonesia)
MALAY_ROOTS = [
    "kahwin", "fikir", "faham", "fasal", "ubat", "wang", "sedar", "sihat", "derhaka",
    "taubat", "solat", "wuduk", "redha", "jiran", "ugama", "halau", "hurai", "baiki",
    "cuai", "rosak", "sesat", "takbur", "sombong", "musnah", "tipu", "bohong",
]


def _get_stemmer():
    global _stemmer
    if _stemmer is None:
        from Sastrawi.Dictionary.ArrayDictionary import ArrayDictionary
        from Sastrawi.Stemmer.Stemmer import Stemmer
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        words = list(StemmerFactory().get_words()) + MALAY_ROOTS
        _stemmer = Stemmer(ArrayDictionary(words))
    return _stemmer


@lru_cache(maxsize=None)
def stem_word(word: str) -> str:
    """Kata dasar BM (contoh: kemarahannya -> marah). Perkataan pendek atau bukan huruf tidak diubah."""
    if len(word) <= 3 or not word.isalpha():
        return word
    return _get_stemmer().stem(word) or word


def stem_tokens(tokens: list[str]) -> list[str]:
    return [stem_word(t) for t in tokens]


def expand_with_stems(tokens: list[str]) -> list[str]:
    """Token asal + kata dasar yang berbeza, supaya soalan padan dengan unit BM (di-stem) dan English (tidak)."""
    out, seen = list(tokens), set(tokens)
    for t in tokens:
        s = stem_word(t)
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out