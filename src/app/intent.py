"""Pengesan niat mudah berasaskan peraturan untuk soalan pengguna."""
import re

# Soalan berbentuk hukum: dialihkan ke sumber fatwa rasmi
FATWA_PATTERNS = [
    r"\bhukum\b",
    r"\b(halal|haram|harus|makruh|sunat|wajib)\s+(ke|tak|tidak|atau)\b",
    r"\bboleh\s+(ke|tak)\b",
    r"\badakah\s+(boleh|dibenarkan|halal|haram)\b",
    r"\bfatwa\b",
    r"\bis it (halal|haram|allowed|permissible)\b",
]

# Soalan maklumat semasa: bukan sesuatu yang dijawab oleh teks Quran/hadis
CURRENT_INFO_PATTERNS = [
    r"\bhari ini\b", r"\besok\b", r"\bsemalam\b", r"\bterdekat\b",
    r"\bharga\b", r"\btarikh\b", r"\bwaktu solat\b", r"\bjadual\b",
    r"\bcara (daftar|bayar|mohon|memohon)\b", r"\bonline\b",
    r"\baplikasi\b", r"\bapp\b", r"\b20\d\d\b",
    r"\bnear me\b", r"\btoday\b", r"\bprice\b",
]


def detect_intent(query: str) -> str | None:
    q = query.lower()
    if any(re.search(p, q) for p in FATWA_PATTERNS):
        return "fatwa"
    if any(re.search(p, q) for p in CURRENT_INFO_PATTERNS):
        return "current_info"
    return None