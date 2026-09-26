"""Download MADBase (real handwritten Arabic-Indic digits) once, for training only.

Source: https://huggingface.co/datasets/MagedSaeed/MADBase (parquet, ~15 MB).
Original: El-Sherif & Abdelazeem (2007), "A Two-Stage System for Arabic Handwritten
Digit Recognition Tested on a New Large Database". Free for research; cite the source.
Stored under research/downloads/madbase/ (git-ignored). Needs `pip install pyarrow`.
"""
import io
from pathlib import Path
import urllib.request

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research' / 'downloads' / 'madbase'
URL = 'https://huggingface.co/api/datasets/MagedSaeed/MADBase/parquet/default/{split}/0.parquet'


def main():
    import pyarrow.parquet as pq
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ('train', 'test'):
        parquet = OUT / f'{split}.parquet'
        if not parquet.exists():
            urllib.request.urlretrieve(URL.format(split=split), parquet)
        table = pq.read_table(parquet).to_pydict()
        X = np.stack([np.array(Image.open(io.BytesIO(d['bytes'])).convert('L')) for d in table['image']])
        np.savez_compressed(OUT / f'{split}.npz', X=X, y=np.array(table['label']))
        print(split, X.shape)


if __name__ == '__main__':
    main()
