"""
Jana embedding untuk semua unit carian (kecuali terjemahan mesin).

    python src/retrieval/build_index.py --limit 300       # uji kelajuan
    python src/retrieval/build_index.py                   # versi biasa
    python src/retrieval/build_index.py --variant ctx     # ayat pendek diberi konteks
"""
import argparse
import time

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from common import DEFAULT_MODEL, MT_LANG, UNITS_PATH, emb_path, passage_prefix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--variant", default="", choices=["", "ctx"])
    parser.add_argument("--limit", type=int, help="uji kelajuan dengan N unit sahaja (tidak disimpan)")
    args = parser.parse_args()

    units = pd.read_parquet(UNITS_PATH)
    units = units[units["lang"] != MT_LANG]   # terjemahan mesin untuk BM25 sahaja
    field = "ctx_text" if args.variant == "ctx" else "text"
    if field not in units.columns:
        raise SystemExit(f"Kolum {field} tiada. Jalankan semula units.py.")

    texts = (passage_prefix(args.model) + units[field]).tolist()
    if args.limit:
        texts = texts[:args.limit]

    print(f"Memuatkan model {args.model}...")
    model = SentenceTransformer(args.model)
    print(f"Peranti: {model.device} | Varian: {args.variant or 'biasa'} | Kolum: {field}")

    start = time.time()
    emb = model.encode(texts, batch_size=args.batch_size, normalize_embeddings=True,
                       show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
    elapsed = time.time() - start

    if args.limit:
        est_min = elapsed / len(texts) * len(units) / 60
        print(f"\n{len(texts)} unit dalam {elapsed:.1f}s. "
              f"Anggaran untuk semua {len(units):,} unit: ~{est_min:.0f} minit")
        return

    path = emb_path(args.model, args.variant)
    np.save(path, emb)
    print(f"\nSelesai dalam {elapsed / 60:.1f} minit. Disimpan: {path} {emb.shape}")


if __name__ == "__main__":
    main()