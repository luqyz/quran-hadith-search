"""
Terjemah unit hadis (English) ke Bahasa Melayu untuk tujuan INDEX sahaja.
Terjemahan mesin TIDAK dipaparkan kepada pengguna.

Direka untuk Colab (GPU). Kemajuan disimpan per shard supaya boleh disambung.

    python src/ingest/translate_hadith.py --ckpt-dir /content/drive/MyDrive/quran_mt_ckpt
    python src/ingest/translate_hadith.py --limit-shards 1     # ujian pantas
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))

import pandas as pd
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from common import INDEX_DIR, MT_PATH, UNITS_PATH

MODEL = "facebook/nllb-200-distilled-600M"
SRC_LANG = "eng_Latn"
TGT_LANG = "zsm_Latn"      # Bahasa Melayu standard
MAX_TOKENS = 256
SHARD_SIZE = 2000

SENT_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_RE.split(text) if s.strip()]


def shard_path(ckpt_dir: Path, i: int) -> Path:
    return ckpt_dir / f"shard_{i:04d}.parquet"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt-dir", default=str(INDEX_DIR / "mt_ckpt"))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit-shards", type=int, help="proses N shard sahaja (untuk ujian)")
    args = parser.parse_args()

    ckpt_dir = Path(args.ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    units = pd.read_parquet(UNITS_PATH)
    hadith = (units[(units.source != "quran") & (units.lang == "en")]
              [["doc_id", "chunk_no", "text"]].reset_index(drop=True))

    sents = (hadith.assign(sentence=hadith["text"].apply(split_sentences))
             .explode("sentence").dropna(subset=["sentence"]))
    unique = sorted(set(sents["sentence"]), key=lambda s: (len(s), s))
    shards = [unique[i:i + SHARD_SIZE] for i in range(0, len(unique), SHARD_SIZE)]
    print(f"{len(hadith):,} unit hadis -> {len(sents):,} sentence -> "
          f"{len(unique):,} unik -> {len(shards)} shard")

    todo = [i for i in range(len(shards)) if not shard_path(ckpt_dir, i).exists()]
    print(f"Shard sudah siap: {len(shards) - len(todo)}/{len(shards)}")
    if args.limit_shards:
        todo = todo[:args.limit_shards]

    if todo:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            print("AMARAN: tiada GPU, proses ini akan sangat lambat.")
        tok = AutoTokenizer.from_pretrained(MODEL, src_lang=SRC_LANG)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL).to(device).eval()
        if device == "cuda":
            model = model.half()
        tgt_id = tok.convert_tokens_to_ids(TGT_LANG)

        @torch.inference_mode()
        def translate(batch: list[str]) -> list[str]:
            enc = tok(batch, return_tensors="pt", padding=True,
                      truncation=True, max_length=MAX_TOKENS).to(device)
            out = model.generate(**enc, forced_bos_token_id=tgt_id, num_beams=1,
                                 max_new_tokens=int(enc["input_ids"].shape[1] * 1.5) + 10)
            return tok.batch_decode(out, skip_special_tokens=True)

        for i in todo:
            start = time.time()
            src = shards[i]
            mt = []
            for j in range(0, len(src), args.batch_size):
                mt.extend(translate(src[j:j + args.batch_size]))
            pd.DataFrame({"src": src, "mt": mt}).to_parquet(shard_path(ckpt_dir, i), index=False)
            print(f"  shard {i + 1}/{len(shards)} siap dalam {time.time() - start:.0f}s")

    missing = [i for i in range(len(shards)) if not shard_path(ckpt_dir, i).exists()]
    if missing:
        print(f"\nMasih ada {len(missing)} shard belum siap. Jalankan semula untuk sambung.")
        return

    done = pd.concat(pd.read_parquet(p) for p in sorted(ckpt_dir.glob("shard_*.parquet")))
    mapping = dict(zip(done["src"], done["mt"]))
    sents["mt"] = sents["sentence"].map(mapping)
    n_missing = sents["mt"].isna().sum()
    if n_missing:
        print(f"AMARAN: {n_missing} sentence tiada terjemahan (checkpoint tak sepadan dengan data?)")

    out = (sents.groupby(["doc_id", "chunk_no"], sort=False)["mt"]
           .apply(lambda s: " ".join(s.dropna()))
           .reset_index(name="text_ms_mt"))
    MT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(MT_PATH, index=False)
    print(f"\nDisimpan: {MT_PATH} ({len(out):,} unit)")

    print("\n=== Contoh terjemahan ===")
    sample = hadith.merge(out, on=["doc_id", "chunk_no"]).sample(3, random_state=0)
    for r in sample.itertuples():
        print(f"\n{r.doc_id}")
        print("  EN:", r.text[:220])
        print("  MS:", r.text_ms_mt[:220])


if __name__ == "__main__":
    main()