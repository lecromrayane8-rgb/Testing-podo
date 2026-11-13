"""Audit : que fait le labo sur un marché de pur hasard (aucun avantage possible) ?

1. On fabrique des cryptos en marche au hasard (aucune tendance, aucune mémoire) : un prix toutes les 10 secondes,
   dont on tire les bougies de 1 min, puis de 5 min, 15 min, 1 h et 4 h. Les plus hauts et les plus bas viennent du
   chemin du prix lui-même : aucune mèche ajoutée, donc rien à gagner pour personne, ni pour un stop ni pour un
   objectif.
2. À l'instant T, le labo (retest_coin, le vrai code) choisit ses bots sur l'historique d'avant T.
3. On fait tourner ces bots sur la suite (après T), avec le même moteur : c'est leur « direct ».
4. On regarde aussi le test final (les derniers 20 % de l'historique, jamais regardés pour choisir) et la mesure à
   l'essai (les trades de toutes les combinaisons après T, sans rien choisir) : un labo honnête y affiche le prix des
   frais, puisqu'il n'y a rien à gagner.
On compare aussi des cryptos prises au hasard et des cryptos choisies, comme le fait l'essaim, parce qu'elles ont le
plus bougé sur les dernières 24 h.

Lancer (quelques minutes sur 4 cœurs) : python audit/hasard.py 80 12 hasard.json
(80 cryptos fabriquées, 12 gardées dans chaque groupe, détail écrit dans hasard.json). Rien n'est lu sur une
plateforme et rien n'est écrit dans data/ : c'est une mesure, pas une partie du bot.
"""
import inspect
import json
import math
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
SUB = 6  # un prix toutes les 10 secondes
FORWARD = {"1m": 2, "5m": 7, "15m": 20, "1h": 60, "4h": 120}  # jours de « direct » simulé après le choix
TRIAL_DAYS_AFTER = 2  # la mesure à l'essai : les trades de toutes les combinaisons pendant les 2 jours qui suivent
HIST_DAYS, FWD_DAYS = 242, 122
N = (HIST_DAYS + FWD_DAYS) * 1440
T0 = 1_760_000_000_000 - 1_760_000_000_000 % DAY
T_CUT = T0 + HIST_DAYS * DAY  # l'instant du choix


def path(seed: int):
    """Le marché d'une crypto : clôture, plus haut et plus bas de chaque minute, et son volume."""
    r = np.random.default_rng(seed)
    fine = 100 * np.exp(np.cumsum(r.normal(0, SIGMA / math.sqrt(SUB), N * SUB))).reshape(N, SUB)
    return fine[:, -1].copy(), fine.max(1), fine.min(1), r.lognormal(0, 0.6, N)


def amplitude(seed: int) -> float:
    close, high, low, _ = path(seed)
    i = HIST_DAYS * 1440
    return float((high[i - 1440:i].max() - low[i - 1440:i].min()) / close[i - 1])


def frame(market, tf: str, start_ms: int, end_ms: int):
    close, high, low, volume = market
    k = timeframe_to_ms(tf) // MIN
    a, b = (start_ms - T0) // MIN // k * k, (end_ms - T0) // MIN // k * k
    c = close[a:b].reshape(-1, k)
    o = np.r_[close[a - 1] if a else close[0], c[:-1, -1]]
    hi = np.maximum(high[a:b].reshape(-1, k).max(1), o)
    lo = np.minimum(low[a:b].reshape(-1, k).min(1), o)
    ts = T0 + (a + np.arange(len(c)) * k) * MIN
    rows = np.c_[ts, o, hi, lo, c[:, -1], volume[a:b].reshape(-1, k).sum(1)]
    return ohlcv_to_frame(rows.tolist())


MEASURES = "trial" in inspect.signature(retest_coin).parameters  # le labo d'avant l'étape 0 bis ne mesurait pas à l'essai


def study(job):
    seed, group = job
    market = path(seed)
    symbol = f"H{seed}/USDT"
    settings = asdict(SwarmSettings(bots_per_coin=8))
    frames = {tf: frame(market, tf, T_CUT - d * DAY, T_CUT) for tf, d in TEST_DAYS.items()}
    result = retest_coin(symbol, frames, settings)
    live = []
    for r in result["chosen"]:
        tf = r["timeframe"]
        df = frame(market, tf, T_CUT - TEST_DAYS[tf] * DAY, T_CUT + FORWARD[tf] * DAY)
        book = simulate(df, spec_from(r))
        after = [t for t in book.s["trades"] if t["entry_ts"] >= T_CUT and t["reason"] != "fin du test"]
        live.append({"tf": tf, "technique": r["technique"], "side": r["side"], "exit": (r["target_r"], r["stop_mode"]),
                     "label": r["label"], "in_mean": r["sv_mean"], "in_n": r["sv_n"],
                     "nets": [t["net"] for t in after], "rois": [t["roi"] for t in after]})
    out = {"seed": seed, "group": group, "tested": result["tested"], "eligible": result["eligible"],
           "chosen": len(result["chosen"]), "live": live}
    if MEASURES:
        # La mesure à l'essai : deux jours plus tard, un nouveau test compte les trades de TOUTES les combinaisons
        # ouverts depuis T, sans rien choisir.
        later = T_CUT + TRIAL_DAYS_AFTER * DAY
        done = {tf: int(df["ts"].iloc[-1]) for tf, df in frames.items()}  # la dernière bougie du test fait à T
        frames = {tf: frame(market, tf, later - d * DAY, later) for tf, d in TEST_DAYS.items()}
        trial = retest_coin(symbol, frames, settings, trial={"done": done, "active": [[T_CUT, None]], "final": True})["trial"]
        measured = [v for k, v in trial["stats"].items() if k.startswith("unite:")]
        out.update(holdout=result["holdout"], holdout_eligible=result["holdout_eligible"],
                   trial={k: sum(v[k] for v in measured) for k in ("n", "total", "wins")})
        if "secure" in result:  # depuis l'étape 1 : chaque combinaison est mesurée sans et avec la sécurisation des gains
            safe = [v for k, v in trial["stats"].items() if k.startswith("avec:unite:")]
            out.update(trial_safe={k: sum(v[k] for v in safe) for k in ("n", "total", "wins")},
                       final_plain=result["secure"]["all"]["sans"], final_safe=result["secure"]["all"]["avec"],
                       variant=result["secure"]["live"])
    return out


def pooled(rows, key):
    """Trades, gain moyen et part de gagnants, toutes cryptos réunies."""
    n = sum(r[key]["n"] for r in rows)
    if not n:
        return 0, float("nan"), float("nan")
    return n, sum(r[key]["total"] for r in rows) / n, sum(r[key]["wins"] for r in rows) / n


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
        rule = "sur l'étude et la validation" if MEASURES else "sur 3 périodes"
        print(f"combinaisons testées par crypto : {rows[0]['tested']} ; gagnantes {rule} : "
              f"{np.mean([r['eligible'] for r in rows]):.0f} en moyenne ({np.mean([r['eligible'] for r in rows]) / rows[0]['tested']:.1%}) ; "
              f"bots créés : {np.mean([r['chosen'] for r in rows]):.1f} par crypto")
        ins = [b["in_mean"] for r in rows for b in r["live"]]
        print(f"dans le backtest qui les a choisis (étude et validation) : {np.mean(ins):+.3%} par trade en moyenne")
        bots = [np.mean(b["nets"]) for r in rows for b in r["live"] if b["nets"]]
        if MEASURES:
            n, mean, win = pooled(rows, "holdout")
            print(f"leur test final, jamais regardé pour les choisir : {n} trades, {win:.0%} gagnants, {mean:+.3%} par trade")
            n, mean, win = pooled(rows, "holdout_eligible")
            print(f"le test final de toutes les gagnantes de l'étude et de la validation : {n} trades, {win:.0%} gagnants, "
                  f"{mean:+.3%} par trade")
        if nets:
            se = np.std(nets, ddof=1) / np.sqrt(len(nets))
            print(f"ensuite, en « direct » simulé : {len(nets)} trades, {np.mean(np.array(nets) > 0):.0%} gagnants, "
                  f"{np.mean(nets):+.3%} par trade (± {1.96 * se:.3%}), {np.mean(rois):+.2%} du capital par trade avec le levier")
            print(f"bots qui finissent quand même positifs : {np.mean(np.array(bots) > 0):.0%}")
        if MEASURES:
            n, mean, win = pooled(rows, "trial")
            print(f"la mesure à l'essai sur les {TRIAL_DAYS_AFTER} jours suivants (toutes les combinaisons, sans choix) : {n} "
                  f"trades, {win:.0%} gagnants, {mean:+.3%} par trade")
        if MEASURES and "trial_safe" in rows[0]:
            print(f"(les bots et les choix ci-dessus : variante « {rows[0]['variant']} » sécurisation des gains)")
            for title, plain, safe in (("à l'essai", "trial", "trial_safe"),
                                       ("sur le test final de toutes les combinaisons", "final_plain", "final_safe")):
                (n0, m0, w0), (n1, m1, w1) = pooled(rows, plain), pooled(rows, safe)
                print(f"sécurisation des gains, {title} : sans {m0:+.3%} par trade ({w0:.0%} gagnants, {n0} trades), "
                      f"avec {m1:+.3%} ({w1:.0%} gagnants, {n1} trades), écart {m1 - m0:+.3%}")
    print(f"\n{time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
