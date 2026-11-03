"""Génère un CSV de bougies synthétiques pour vérifier qu'un exécutable fonctionne, sans réseau.

Usage : python packaging/sample_data.py chemin.csv
Ces données sont aléatoires : elles testent la mécanique du bot, jamais sa rentabilité.
"""
import sys

import numpy as np
import pandas as pd

HOUR_MS = 3_600_000


def main(path: str, n: int = 3000) -> None:
    rng = np.random.default_rng(1)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.008, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    ts = 1_700_000_000_000 // HOUR_MS * HOUR_MS + np.arange(n) * HOUR_MS
    pd.DataFrame(dict(ts=ts, open=open_, high=high, low=low, close=close, volume=1.0)).to_csv(path, index=False)


if __name__ == "__main__":
    main(sys.argv[1])
