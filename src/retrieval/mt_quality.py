"""Pengesan kasar untuk terjemahan mesin hadis yang meragukan."""
import re

# Nama nabi dalam terjemahan BM, dengan corak padanan dalam teks English asal
NAMES = {
    "Ibrahim": r"Abraham|Ibrahim", "Musa": r"Moses|Musa", "Isa": r"Jesus|`?Isa\b",
    "Nuh": r"Noah|Nuh", "Yusuf": r"Joseph|Yusuf", "Sulaiman": r"Solomon|Sulaiman",
    "Daud": r"David|Da'?w?ud", "Yunus": r"Jonah|Yunus", "Adam": r"\bAdam\b",
}


def added_names(en: str, ms: str) -> list[str]:
    """Nama nabi yang muncul dalam terjemahan tetapi tiada dalam teks asal."""
    return [n for n, pat in NAMES.items()
            if re.search(rf"\b{n}\b", ms) and not re.search(pat, en)]


def length_ratio(en: str, ms: str) -> float:
    return len(ms.split()) / max(len(en.split()), 1)


def is_degenerate(ms: str) -> bool:
    """Gelung berulang: terlalu sedikit perkataan unik untuk teks yang panjang."""
    tokens = ms.lower().split()
    return len(tokens) > 20 and len(set(tokens)) / len(tokens) < 0.35


def suspect_reasons(en: str, ms: str) -> list[str]:
    reasons = []
    if added_names(en, ms):
        reasons.append("nama_ditambah")
    ratio = length_ratio(en, ms)
    if ratio < 0.5 or ratio > 2:
        reasons.append("panjang_luar_biasa")
    if is_degenerate(ms):
        reasons.append("berulang")
    return reasons