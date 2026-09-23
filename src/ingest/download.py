"""
Muat turun data mentah Quran dan hadis ke data/raw/.

Jalankan dari root repo:
    python src/ingest/download.py
    python src/ingest/download.py --force   # muat turun semula
"""
import argparse
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"

# Quran: alquran.cloud (teks & terjemahan berasal dari Tanzil.net)
QURAN_URL = "https://api.alquran.cloud/v1/quran/{edition}"
QURAN_EDITIONS = ["quran-simple", "ms.basmeih", "en.sahih"]

# Hadis: fawazahmed0/hadith-api melalui CDN jsDelivr
HADITH_URLS = [
    "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/{edition}.min.json",
    "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/{edition}.json",
]
HADITH_EDITIONS = ["eng-bukhari", "ara-bukhari", "eng-muslim", "ara-muslim"]


def fetch_json(url: str, retries: int = 3, timeout: int = 120) -> dict:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as err:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  Gagal ({err}), cuba semula dalam {wait}s...")
            time.sleep(wait)


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def download_quran(force: bool) -> None:
    for edition in QURAN_EDITIONS:
        path = RAW_DIR / "quran" / f"{edition}.json"
        if path.exists() and not force:
            print(f"[skip] {path.name} dah wujud")
            continue
        print(f"[quran] {edition}")
        payload = fetch_json(QURAN_URL.format(edition=edition))
        if payload.get("code") != 200 or "data" not in payload:
            raise RuntimeError(f"Respons tak dijangka untuk {edition}: {payload.get('status')}")
        save_json(payload["data"], path)


def download_hadith(force: bool) -> None:
    for edition in HADITH_EDITIONS:
        path = RAW_DIR / "hadith" / f"{edition}.json"
        if path.exists() and not force:
            print(f"[skip] {path.name} dah wujud")
            continue
        print(f"[hadith] {edition}")
        last_err = None
        for template in HADITH_URLS:
            try:
                data = fetch_json(template.format(edition=edition))
                break
            except requests.RequestException as err:
                last_err = err
        else:
            raise RuntimeError(f"Gagal muat turun {edition}: {last_err}")
        save_json(data, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="muat turun semula walaupun fail wujud")
    args = parser.parse_args()

    download_quran(args.force)
    download_hadith(args.force)
    print("\nSelesai. Fail dalam:", RAW_DIR)


if __name__ == "__main__":
    main()