"""
Jana embedding untuk semua unit carian.

    python src/retrieval/build_index.py --limit 300     # uji kelajuan dahulu
    python src/retrieval/build_index.py                 # jana penuh
"""
import argparse
import time

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from common import DEFAULT_MODEL, UNITS_PATH, emb_path, passage_prefix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int, help="uji kelajuan dengan N unit sahaja (tidak disimpan)")
    args = parser.parse_args()

    units = pd.read_parquet(UNITS_PATH)
    texts = (passage_prefix(args.model) + units["text"]).tolist()
    if args.limit:
        texts = texts[:args.limit]

    print(f"Memuatkan model {args.model} (kali pertama akan muat turun)...")
    model = SentenceTransformer(args.model)
    print(f"Peranti: {model.device}")

    start = time.time()
    emb = model.encode(
        texts,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    elapsed = time.time() - start

    if args.limit:
        est_min = elapsed / len(texts) * len(units) / 60
        print(f"\n{len(texts)} unit dalam {elapsed:.1f}s. "
              f"Anggaran untuk semua {len(units):,} unit: ~{est_min:.0f} minit")
        return

    path = emb_path(args.model)
    np.save(path, emb)
    print(f"\nSelesai dalam {elapsed / 60:.1f} minit. Disimpan: {path} {emb.shape}")


if __name__ == "__main__":
    main()