"""Audit : que fait le labo sur un marché de pur hasard (aucun avantage possible) ?

1. On fabrique des cryptos en marche au hasard (aucune tendance, aucune mémoire), bougies de 1 min agrégées en 5 min,
   15 min, 1 h et 4 h.
2. À l'instant T, le labo (retest_coin, le vrai code) choisit ses bots sur l'historique d'avant T.
3. On fait tourner ces bots sur la suite (après T), avec le même moteur : c'est leur « direct ».
On compare aussi des cryptos prises au hasard et des cryptos choisies, comme le fait l'essaim, parce qu'elles ont le
plus bougé sur les dernières 24 h.

Lancer (quelques minutes sur 4 cœurs) : python audit/hasard.py 80 12 hasard.json
(80 cryptos fabriquées, 12 gardées dans chaque groupe, détail écrit dans hasard.json). Rien n'est lu sur une
plateforme et rien n'est écrit dans data/ : c'est une mesure, pas une partie du bot.
"""
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradingbot.data import ohlcv_to_frame, timeframe_to_ms  # noqa: E402
from tradingbot.fleet import simulate, spec_from  # noqa: E402
from tradingbot.swarm import TEST_DAYS, SwarmSettings, retest_coin  # noqa: E402

MIN, DAY = 60_000, 86_400_000
SIGMA = 0.0010  # écart-type d'une minute : environ 3,8 % par jour, une crypto agitée
FORWARD = {"1m": 2, "5m": 7, "15m": 20, "1h": 60, "4h": 120}  # jours de « direct » simulé après le choix
HIST_DAYS, FWD_DAYS = 242, 122
N = (HIST_DAYS + FWD_DAYS) * 1440
T0 = 1_760_000_000_000 - 1_760_000_000_000 % DAY
T_CUT = T0 + HIST_DAYS * DAY  # l'instant du choix


def path(seed: int):
    r = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(r.normal(0, SIGMA, N)))
    wick = np.abs(r.normal(0, SIGMA * 0.4, N))
    volume = r.lognormal(0, 0.6, N)
    return close, wick, volume


def amplitude(seed: int) -> float:
    close, _, _ = path(seed)
    i = HIST_DAYS * 1440
    day = close[i - 1440:i]
    return float((day.max() - day.min()) / day[-1])


def frame(close, wick, volume, tf: str, start_ms: int, end_ms: int):
    k = timeframe_to_ms(tf) // MIN
    a, b = (start_ms - T0) // MIN // k * k, (end_ms - T0) // MIN // k * k
    c = close[a:b].reshape(-1, k)
    o = np.r_[close[a - 1] if a else close[0], c[:-1, -1]]
    hi = np.maximum(np.maximum(c.max(1), o) * (1 + wick[a:b].reshape(-1, k).max(1)), 0)
    lo = np.minimum(c.min(1), o) * (1 - wick[a:b].reshape(-1, k).max(1))
    ts = T0 + (a + np.arange(len(c)) * k) * MIN
    rows = np.c_[ts, o, hi, lo, c[:, -1], volume[a:b].reshape(-1, k).sum(1)]
    return ohlcv_to_frame(rows.tolist())


def study(job):
    seed, group = job
    close, wick, volume = path(seed)
    symbol = f"H{seed}/USDT"
    frames = {tf: frame(close, wick, volume, tf, T_CUT - d * DAY, T_CUT) for tf, d in TEST_DAYS.items()}
    result = retest_coin(symbol, frames, asdict(SwarmSettings(bots_per_coin=8)))
    live = []
    for r in result["chosen"]:
        tf = r["timeframe"]
        df = frame(close, wick, volume, tf, T_CUT - TEST_DAYS[tf] * DAY, T_CUT + FORWARD[tf] * DAY)
        book = simulate(df, spec_from(r))
        after = [t for t in book.s["trades"] if t["entry_ts"] >= T_CUT and t["reason"] != "fin du test"]
        live.append({"tf": tf, "technique": r["technique"], "side": r["side"], "exit": (r["target_r"], r["stop_mode"]),
                     "label": r["label"], "in_mean": r["sv_mean"], "in_n": r["sv_n"],
                     "nets": [t["net"] for t in after], "rois": [t["roi"] for t in after]})
    return {"seed": seed, "group": group, "tested": result["tested"], "eligible": result["eligible"],
            "chosen": len(result["chosen"]), "live": live}


def main():
    n_pool, n_each = int(sys.argv[1]), int(sys.argv[2])
    started = time.time()
    with ProcessPoolExecutor(4) as pool:
        amps = list(pool.map(amplitude, range(n_pool), chunksize=4))
    order = np.argsort(amps)[::-1]
    top = [int(s) for s in order[:n_each]]
    rest = [int(s) for s in np.random.default_rng(1).permutation(order[n_each:])[:n_each]]
    print(f"{n_pool} cryptos au hasard, amplitude 24 h médiane {np.median(amps):.1%}, des plus agitées {np.mean([amps[s] for s in top]):.1%}",
          flush=True)
    jobs = [(s, "agitées") for s in top] + [(s, "au hasard") for s in rest]
    with ProcessPoolExecutor(4) as pool:
        out = list(pool.map(study, jobs))
    Path(sys.argv[3]).write_text(json.dumps(out), encoding="utf-8")
    for group in ("au hasard", "agitées"):
        rows = [r for r in out if r["group"] == group]
        nets = [x for r in rows for b in r["live"] for x in b["nets"]]
        rois = [x for r in rows for b in r["live"] for x in b["rois"]]
        print(f"\n--- cryptos {group} ({len(rows)}) ---")
        print(f"combinaisons testées par crypto : {rows[0]['tested']} ; déclarées gagnantes sur 3 périodes : "
              f"{np.mean([r['eligible'] for r in rows]):.0f} en moyenne ({np.mean([r['eligible'] for r in rows]) / rows[0]['tested']:.1%}) ; "
              f"bots créés : {np.mean([r['chosen'] for r in rows]):.1f} par crypto")
        ins = [b["in_mean"] for r in rows for b in r["live"]]
        print(f"dans le backtest qui les a choisis : {np.mean(ins):+.3%} par trade en moyenne")
        if nets:
            se = np.std(nets, ddof=1) / np.sqrt(len(nets))
            print(f"ensuite, en « direct » simulé : {len(nets)} trades, {np.mean(np.array(nets) > 0):.0%} gagnants, "
                  f"{np.mean(nets):+.3%} par trade (± {1.96 * se:.3%}), {np.mean(rois):+.2%} du capital par trade avec le levier")
    print(f"\n{time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
