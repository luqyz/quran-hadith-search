"""
Bina data/processed/corpus.parquet daripada data mentah.

Jalankan dari root repo:
    python src/ingest/clean.py
"""
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "processed" / "corpus.parquet"
SURAHS_PATH = ROOT / "data" / "processed" / "surahs.json"

NAWAWI_PATH = ROOT / "data" / "processed" / "nawawi.json"

# (tajuk ringkas BM, sumber riwayat). Tajuk ialah ringkasan editorial, bukan terjemahan.
NAWAWI_META = {
    1: ("Amalan bergantung pada niat", "Bukhari & Muslim"),
    2: ("Islam, Iman dan Ihsan", "Muslim"),
    3: ("Rukun Islam", "Bukhari & Muslim"),
    4: ("Penciptaan manusia dan takdir", "Bukhari & Muslim"),
    5: ("Perkara baharu dalam agama ditolak", "Bukhari & Muslim"),
    6: ("Halal dan haram itu jelas", "Bukhari & Muslim"),
    7: ("Agama itu nasihat", "Muslim"),
    8: ("Kehormatan nyawa dan harta", "Bukhari & Muslim"),
    9: ("Lakukan perintah sekadar mampu", "Bukhari & Muslim"),
    10: ("Allah hanya menerima yang baik", "Muslim"),
    11: ("Tinggalkan yang meragukan", "Tirmidhi & An-Nasa'i"),
    12: ("Tinggalkan perkara yang tidak berfaedah", "Tirmidhi"),
    13: ("Mengasihi saudara seperti diri sendiri", "Bukhari & Muslim"),
    14: ("Kehormatan darah seorang Muslim", "Bukhari & Muslim"),
    15: ("Berkata baik atau diam", "Bukhari & Muslim"),
    16: ("Jangan marah", "Bukhari"),
    17: ("Ihsan dalam segala perkara", "Muslim"),
    18: ("Takwa dan akhlak yang baik", "Tirmidhi"),
    19: ("Jagalah Allah, Allah akan menjagamu", "Tirmidhi"),
    20: ("Sifat malu", "Bukhari"),
    21: ("Beriman dan istiqamah", "Muslim"),
    22: ("Jalan ke syurga melalui amalan wajib", "Muslim"),
    23: ("Kebersihan sebahagian daripada iman", "Muslim"),
    24: ("Pengharaman kezaliman (hadis qudsi)", "Muslim"),
    25: ("Pintu-pintu sedekah", "Muslim"),
    26: ("Setiap sendi bersedekah", "Bukhari & Muslim"),
    27: ("Kebaikan dan dosa", "Muslim; Ahmad & Ad-Darimi"),
    28: ("Berpegang teguh pada sunnah", "Abu Dawud & Tirmidhi"),
    29: ("Amalan yang memasukkan ke syurga", "Tirmidhi"),
    30: ("Batasan-batasan Allah", "Ad-Daraqutni"),
    31: ("Zuhud", "Ibn Majah"),
    32: ("Tiada mudarat dan membalas mudarat", "Ibn Majah & Ad-Daraqutni"),
    33: ("Beban bukti ke atas pendakwa", "Al-Bayhaqi"),
    34: ("Mencegah kemungkaran", "Muslim"),
    35: ("Persaudaraan Islam", "Muslim"),
    36: ("Membantu sesama Muslim dan menuntut ilmu", "Muslim"),
    37: ("Pencatatan kebaikan dan kejahatan", "Bukhari & Muslim"),
    38: ("Wali Allah dan amalan sunat", "Bukhari"),
    39: ("Kemaafan atas silap, lupa dan paksaan", "Ibn Majah & Al-Bayhaqi"),
    40: ("Hidup di dunia seperti orang asing", "Bukhari"),
    41: ("Mengikut ajaran Nabi", "Kitab al-Hujjah"),
    42: ("Keluasan keampunan Allah", "Tirmidhi"),
}

QURAN_EDITIONS = {"ar": "quran-simple", "ms": "ms.basmeih", "en": "en.sahih"}
HADITH_COLLECTIONS = ["bukhari", "muslim"]
EXPECTED_AYAH_COUNT = 6236
UNCLASSIFIED = "Tidak diklasifikasikan"

COLUMNS = [
    "id", "source", "ref", "book_no", "item_no", "chapter_title",
    "text_ar", "text_ms", "text_en", "grade", "grade_source", "book_inferred",
    "is_xref", "is_muqattaat",
]


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
INVISIBLE_RE = re.compile(r"[\ufeff\u200b-\u200f]")
AR_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
AR_ALIF_RE = re.compile(r"[\u0622\u0623\u0625\u0671]")
XREF_RE = re.compile(
    r"^(?:narrated [^:]{0,60}:\s*)?(?:as above|see (?:the )?previous|see translation for hadith"
    r"|same as (?:the )?previous)"
    r"|(?:has been|was) (?:narrated|transmitted|reported)\b.{0,120}?"
    r"(?:same chain|another chain|chain of transmitters|similar)",
    re.IGNORECASE,
)
XREF_MAX_WORDS = 40


def clean_text(text):
    if not isinstance(text, str):
        return None
    text = unicodedata.normalize("NFC", text)
    text = INVISIBLE_RE.sub("", text)
    text = TAG_RE.sub(" ", text)
    text = WS_RE.sub(" ", text).strip()
    return text or None


def ar_skeleton(text: str) -> str:
    """Rangka huruf Arab: tanpa harakat, semua bentuk alif diseragamkan."""
    text = AR_DIACRITICS_RE.sub("", text)
    return AR_ALIF_RE.sub("\u0627", text)

def is_xref(text) -> bool:
    """Rujukan silang tanpa kandungan sendiri (contohnya 'As above', nota rantaian perawi)."""
    return (isinstance(text, str) and len(text.split()) < XREF_MAX_WORDS
            and bool(XREF_RE.search(text)))


def is_muqattaat(text_ar) -> bool:
    """Ayat yang terdiri daripada huruf muqatta'ah sahaja (contohnya الم, يس, حم)."""
    if not isinstance(text_ar, str):
        return False
    tokens = text_ar.split()
    return len(tokens) == 1 and len(ar_skeleton(tokens[0])) <= 5

def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} tiada. Jalankan download.py dahulu.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fmt_num(n) -> str:
    """1.0 -> '1', 2.5 -> '2.5' (sesetengah nombor hadis bukan integer)."""
    n = float(n)
    return str(int(n)) if n.is_integer() else str(n)


# ---------------- Quran ----------------

def load_quran_edition(lang: str, edition: str) -> pd.DataFrame:
    data = load_json(RAW_DIR / "quran" / f"{edition}.json")
    rows = []
    for surah in data["surahs"]:
        for ayah in surah["ayahs"]:
            rows.append({
                "surah_no": surah["number"],
                "ayah_no": ayah["numberInSurah"],
                "surah_name": surah.get("englishName"),
                f"text_{lang}": clean_text(ayah["text"]),
            })
    return pd.DataFrame(rows)


def build_quran() -> pd.DataFrame:
    keys = ["surah_no", "ayah_no"]
    df = load_quran_edition("ar", QURAN_EDITIONS["ar"])
    for lang in ("ms", "en"):
        other = load_quran_edition(lang, QURAN_EDITIONS[lang]).drop(columns="surah_name")
        df = df.merge(other, on=keys, how="outer", validate="one_to_one")

    if len(df) != EXPECTED_AYAH_COUNT:
        print(f"AMARAN: {len(df)} ayat, dijangka {EXPECTED_AYAH_COUNT}")

        # Buang Basmalah yang tercantum pada ayat 1 (kecuali Al-Fatihah & At-Taubah)
    basmalah_words = df.loc[(df.surah_no == 1) & (df.ayah_no == 1), "text_ar"].iloc[0].split()
    n = len(basmalah_words)
    target = ar_skeleton(" ".join(basmalah_words))

    def strip_basmalah(text):
        words = text.split()
        if len(words) > n and ar_skeleton(" ".join(words[:n])) == target:
            return " ".join(words[n:])
        return text

    is_first = (df.ayah_no == 1) & ~df.surah_no.isin([1, 9])
    original = df.loc[is_first, "text_ar"]
    stripped = original.apply(strip_basmalah)
    df.loc[is_first, "text_ar"] = stripped
    removed = (stripped != original).sum()
    print(f"[quran] Basmalah dibuang dari {removed} ayat pertama")

    if removed < is_first.sum():
        # Diagnostik: tunjuk perbezaan Unicode kalau masih ada yang tak padan
        sample = original[stripped == original].iloc[0]
        print("  Rujukan 1:1 :", [hex(ord(c)) for c in " ".join(basmalah_words)[:12]])
        print("  Tak padan   :", [hex(ord(c)) for c in sample[:12]])

    ref = df["surah_no"].astype(str) + ":" + df["ayah_no"].astype(str)
    return pd.DataFrame({
        "id": "quran:" + ref,
        "source": "quran",
        "ref": ref,
        "book_no": df["surah_no"],
        "item_no": df["ayah_no"].astype(float),
        "chapter_title": df["surah_name"],
        "text_ar": df["text_ar"],
        "text_ms": df["text_ms"],
        "text_en": df["text_en"],
        "grade": None,
        "grade_source": None,
        "book_inferred": False,
        "is_xref": False,
        "is_muqattaat": df["text_ar"].apply(is_muqattaat),
    })


# ---------------- Hadis ----------------

def load_hadith_edition(lang: str, collection: str):
    data = load_json(RAW_DIR / "hadith" / f"{lang}-{collection}.json")
    sections = data.get("metadata", {}).get("sections", {})
    rows = []
    for h in data["hadiths"]:
        ref = h.get("reference") or {}
        rows.append({
            "hadith_no": h["hadithnumber"],
            "book_no": ref.get("book"),
            "text": clean_text(h.get("text")),
            "grades": h.get("grades") or [],
        })
    df = pd.DataFrame(rows)

    dupes = df["hadith_no"].duplicated().sum()
    if dupes:
        print(f"AMARAN: {dupes} nombor hadis berulang dalam {lang}-{collection}, simpan yang pertama")
        df = df.drop_duplicates("hadith_no")
    return df, sections


def fill_book_from_neighbors(df: pd.DataFrame, collection: str, sections: dict) -> pd.DataFrame:
    """
    Isi book_no = 0 berdasarkan hadis sebelum & selepas, tetapi hanya jika
    dataset tiada tajuk untuk kitab 0 (maksudnya 0 = tidak dipetakan).
    Hanya diisi jika kedua-dua jiran dalam kitab yang sama.
    """
    df = df.sort_values("hadith_no").copy()
    book = pd.to_numeric(df["book_no"], errors="coerce")
    if not clean_text(sections.get("0")):
        book = book.replace(0, float("nan"))

    prev_book = book.ffill()
    next_book = book.bfill()
    missing = book.isna()
    fillable = missing & (prev_book == next_book)

    df["book_no"] = book.where(~fillable, prev_book).astype("Int64")
    df["book_inferred"] = fillable
    print(f"[{collection}] book_no diisi dari jiran: {fillable.sum()}, "
          f"masih tidak diklasifikasikan: {(missing & ~fillable).sum()}")
    return df


def pick_grade(grades, collection):
    for g in grades:
        if isinstance(g, dict) and g.get("grade"):
            return clean_text(g["grade"]), "dataset"
    # Bukhari & Muslim secara umum diterima sahih; ditanda supaya jelas ia bukan dari dataset
    if collection in ("bukhari", "muslim"):
        return "Sahih", "collection"
    return None, None


def build_hadith(collection: str) -> pd.DataFrame:
    en, sections = load_hadith_edition("eng", collection)
    ar, _ = load_hadith_edition("ara", collection)
    ar = ar[["hadith_no", "text"]].rename(columns={"text": "text_ar"})
    df = en.merge(ar, on="hadith_no", how="left", validate="one_to_one")

    before = len(df)
    df = df[df["text"].notna() | df["text_ar"].notna()]
    if len(df) < before:
        print(f"[{collection}] buang {before - len(df)} baris tanpa teks")

    df = fill_book_from_neighbors(df, collection, sections)
    df["chapter_title"] = (
        df["book_no"]
        .apply(lambda b: clean_text(sections.get(str(int(b)))) if pd.notna(b) else None)
        .fillna(UNCLASSIFIED)
    )

    grade_info = df["grades"].apply(lambda g: pick_grade(g, collection))
    nums = df["hadith_no"].apply(fmt_num)
    return pd.DataFrame({
        "id": f"{collection}:" + nums,
        "source": collection,
        "ref": f"{collection.capitalize()} " + nums,
        "book_no": df["book_no"],
        "item_no": df["hadith_no"].astype(float),
        "chapter_title": df["chapter_title"],
        "text_ar": df["text_ar"],
        "text_ms": None,
        "text_en": df["text"],
        "grade": grade_info.apply(lambda t: t[0]),
        "grade_source": grade_info.apply(lambda t: t[1]),
        "book_inferred": df["book_inferred"],
        "is_xref": df["text"].apply(is_xref),
        "is_muqattaat": False,
    })


# ---------------- Main ----------------
def build_surah_meta() -> list[dict]:
    data = load_json(RAW_DIR / "quran" / f"{QURAN_EDITIONS['ar']}.json")
    return [{
        "number": s["number"],
        "name_ar": s.get("name"),
        "english_name": s.get("englishName"),
        "translation": s.get("englishNameTranslation"),
        "revelation": s.get("revelationType"),
        "ayah_count": len(s["ayahs"]),
    } for s in data["surahs"]]

def build_nawawi() -> list[dict]:
    en = load_json(RAW_DIR / "hadith" / "eng-nawawi.json")["hadiths"]
    ar = {h["hadithnumber"]: h.get("text") for h in load_json(RAW_DIR / "hadith" / "ara-nawawi.json")["hadiths"]}
    out = []
    for h in en:
        n = int(h["hadithnumber"])
        if n not in NAWAWI_META:
            continue
        title, sources = NAWAWI_META[n]
        out.append({
            "number": n,
            "title_ms": title,
            "sources": sources,
            "text_ar": clean_text(ar.get(h["hadithnumber"])),
            "text_en": clean_text(h.get("text")),
        })
    return sorted(out, key=lambda x: x["number"])

def validate(corpus: pd.DataFrame) -> None:
    assert corpus["id"].is_unique, "Ada id berulang!"
    print("\n=== Bilangan mengikut sumber ===")
    print(corpus["source"].value_counts().to_string())

    cols = ["text_ar", "text_ms", "text_en", "grade"]
    print("\n=== Nilai kosong (%) ===")
    print((corpus[cols].isna().groupby(corpus["source"]).mean() * 100).round(1).to_string())

    print("\n=== 'Tidak diklasifikasikan' mengikut sumber ===")
    unclassified = (corpus["chapter_title"] == UNCLASSIFIED).groupby(corpus["source"]).sum()
    print(unclassified.to_string())


def main() -> None:
    parts = [build_quran()] + [build_hadith(c) for c in HADITH_COLLECTIONS]
    corpus = pd.concat(parts, ignore_index=True)[COLUMNS]
    corpus["book_no"] = pd.to_numeric(corpus["book_no"], errors="coerce").astype("Int64")

    validate(corpus)

    print("\n=== Bendera ===")
    print("Rujukan silang hadis:", int(corpus["is_xref"].sum()))
    print("Ayat muqatta'ah:", corpus.loc[corpus["is_muqattaat"], "ref"].tolist())

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    corpus.to_parquet(OUT_PATH, index=False)
    print(f"\nDisimpan: {OUT_PATH} ({len(corpus):,} baris)")

    with open(SURAHS_PATH, "w", encoding="utf-8") as f:
        json.dump(build_surah_meta(), f, ensure_ascii=False, indent=1)
    print(f"Disimpan: {SURAHS_PATH}")

    nawawi = build_nawawi()
    with open(NAWAWI_PATH, "w", encoding="utf-8") as f:
        json.dump(nawawi, f, ensure_ascii=False, indent=1)
    print(f"Disimpan: {NAWAWI_PATH} ({len(nawawi)} hadis)")


if __name__ == "__main__":
    main()