"""
Muat naik fail index ke repositori dataset PERIBADI di Hugging Face.

    python scripts/upload_artifacts.py --repo <username>/quran-hadith-artifacts
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "retrieval"))

from huggingface_hub import HfApi

from common import (CORPUS_PATH, DEFAULT_EMB_VARIANT, DEFAULT_MODEL, ROOT, SURAHS_PATH,
                    UNITS_PATH, emb_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="contoh: username/quran-hadith-artifacts")
    args = parser.parse_args()

    files = [CORPUS_PATH, UNITS_PATH, SURAHS_PATH, emb_path(DEFAULT_MODEL, DEFAULT_EMB_VARIANT)]
    missing = [f for f in files if not f.exists()]
    if missing:
        raise SystemExit(f"Fail tiada: {missing}")

    api = HfApi()
    api.create_repo(args.repo, repo_type="dataset", private=True, exist_ok=True)
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        print(f"Memuat naik {rel} ({f.stat().st_size / 1e6:.1f} MB)...")
        api.upload_file(path_or_fileobj=str(f), path_in_repo=rel,
                        repo_id=args.repo, repo_type="dataset")
    print(f"\nSelesai: https://huggingface.co/datasets/{args.repo} (peribadi)")


if __name__ == "__main__":
    main()