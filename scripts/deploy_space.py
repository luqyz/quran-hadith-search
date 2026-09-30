"""
Hantar kod API ke Hugging Face Space (Docker).

    # Kali pertama (tetapkan token untuk membaca repo dataset peribadi):
    python scripts/deploy_space.py --space <username>/quran-hadith-api \
        --artifacts <username>/quran-hadith-artifacts --set-token

    # Kemas kini kod sahaja:
    python scripts/deploy_space.py --space <username>/quran-hadith-api \
        --artifacts <username>/quran-hadith-artifacts
"""
import argparse
import getpass
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
SPACE_FILES = {
    "deploy/space/Dockerfile": "Dockerfile",
    "deploy/space/README.md": "README.md",
    "deploy/space/requirements.txt": "requirements.txt",
}
CODE_DIRS = ["src/retrieval", "src/app"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", required=True)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--set-token", action="store_true", help="tetapkan token READ sebagai secret")
    parser.add_argument("--origins", help="domain yang dibenarkan (CORS), dipisah koma")
    args = parser.parse_args()

    api = HfApi()
    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)

    # Tetapan runtime ditetapkan dahulu supaya build pertama terus menggunakannya
    api.add_space_variable(args.space, "ARTIFACT_REPO", args.artifacts)
    if args.origins:
        api.add_space_variable(args.space, "ALLOWED_ORIGINS", args.origins)
    if args.set_token:
        token = getpass.getpass("Tampal token READ Hugging Face (tidak akan dipaparkan): ").strip()
        api.add_space_secret(args.space, "HF_TOKEN", token)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for src, dst in SPACE_FILES.items():
            shutil.copy(ROOT / src, tmp / dst)
        for d in CODE_DIRS:
            (tmp / d).mkdir(parents=True, exist_ok=True)
            for f in (ROOT / d).glob("*.py"):
                shutil.copy(f, tmp / d / f.name)
        api.upload_folder(folder_path=str(tmp), repo_id=args.space, repo_type="space",
                          commit_message="Deploy API")

    user, name = args.space.split("/")
    print(f"\nSpace:   https://huggingface.co/spaces/{args.space}")
    print(f"API:     https://{user.lower()}-{name.lower()}.hf.space/docs")


if __name__ == "__main__":
    main()