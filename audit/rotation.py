"""Audit : combien de temps un bot garde-t-il sa place quand sa crypto est retestée toutes les 3 heures ?

Sur des cryptos en marche au hasard, on refait le test de la crypto toutes les 3 heures pendant 48 heures, comme
l'essaim, avec le vrai code : retest_coin choisit, Swarm.apply_test décide qui reste. On mesure la part des bots gardés
d'un test au suivant, leur durée de vie et le nombre de trades qu'ils ont eu le temps de faire. Les garde-fous du
direct (liquidation, moitié du capital perdue, pertes nettes après 20 trades) ne sont pas joués ici.

Lancer (environ 7 minutes sur 4 cœurs) : python audit/rotation.py rotation.json 101 102 103 104 105 106 107 108 109 110 111 112
(le fichier du détail, puis une graine par crypto fabriquée).
"""
import inspect
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hasard import DAY, T_CUT, frame, path  # noqa: E402
from tradingbot.fleet import simulate, spec_from  # noqa: E402
from tradingbot.swarm import TEST_DAYS, Swarm, SwarmSettings, retest_coin  # noqa: E402

HOUR = 3_600_000
STEP_H, ROUNDS = 3, 17  # 17 tests : 48 heures
KEEPS = "keep" in inspect.signature(retest_coin).parameters  # avant l'étape 0 bis, le test ne connaissait pas les bots en place


class NoExchange:
    markets: dict = {}


def study(seed: int):
    market = path(seed)
    symbol = f"H{seed}/USDT"
    settings = SwarmSettings(bots_per_coin=8)
    now = [T_CUT]
    swarm = Swarm(NoExchange(), None, settings, clock=lambda: now[0] / 1000, read=False)
    born: dict[str, int] = {}
    specs: dict[str, dict] = {}
    done = []
    kept, total = [], []
    for k in range(ROUNDS):
        now[0] = T_CUT + k * STEP_H * HOUR
        frames = {tf: frame(market, tf, now[0] - d * DAY, now[0]) for tf, d in TEST_DAYS.items()}
        keep = {"keep": tuple(b["spec"] for b in swarm.bots.values() if b["status"] != "sortie")} if KEEPS else {}
        before = set(swarm.bots)
        swarm.apply_test(retest_coin(symbol, frames, asdict(settings), **keep), now[0])
        for key in [key for key, bot in swarm.bots.items() if bot["status"] == "sortie"]:  # arrêté par le test
            del swarm.bots[key]
        if k:
            total.append(len(before))
            kept.append(len(before & set(swarm.bots)))
        for key in before - set(swarm.bots):
            done.append({"key": key, "born": born.pop(key), "died": k})
        for key in set(swarm.bots) - before:
            born[key], specs[key] = k, swarm.bots[key]["spec"]
    done += [{"key": key, "born": k, "died": None} for key, k in born.items()]
    out = []
    for bot in done:
        spec = spec_from(specs[bot["key"]])
        tf = spec.timeframe
        start = T_CUT + bot["born"] * STEP_H * HOUR
        end = T_CUT + (bot["died"] if bot["died"] is not None else ROUNDS - 1) * STEP_H * HOUR
        df = frame(market, tf, start - TEST_DAYS[tf] * DAY, max(end, start + HOUR))
        trades = [t for t in simulate(df, spec).s["trades"] if start <= t["entry_ts"] < end and t["reason"] != "fin du test"]
        out.append({"tf": tf, "born": bot["born"], "died": bot["died"], "trades": len(trades),
                    "nets": [t["net"] for t in trades]})
    return {"seed": seed, "kept": kept, "total": total, "bots": out, "stopped": sum(b["died"] is not None for b in done)}


def main():
    seeds = [int(s) for s in sys.argv[2:]]
    started = time.time()
    with ProcessPoolExecutor(4) as pool:
        rows = list(pool.map(study, seeds))
    Path(sys.argv[1]).write_text(json.dumps(rows), encoding="utf-8")
    kept = sum(sum(r["kept"]) for r in rows)
    total = sum(sum(r["total"]) for r in rows)
    bots = [b for r in rows for b in r["bots"]]
    stopped = sum(r["stopped"] for r in rows)
    print(f"{len(seeds)} cryptos au hasard, {ROUNDS} tests chacune (toutes les {STEP_H} h pendant {(ROUNDS - 1) * STEP_H} h)")
    print(f"bots gardés d'un test au suivant : {kept}/{total} = {kept / total:.0%}")
    print(f"bots créés en tout : {len(bots)} ({len(bots) / len(seeds):.1f} par crypto, pour 8 places), dont arrêtés par un "
          f"test : {stopped}")
    trades = [b["trades"] for b in bots]
    print(f"trades par bot en {(ROUNDS - 1) * STEP_H} h : médiane {np.median(trades):.0f}, moyenne {np.mean(trades):.1f}, "
          f"bots avec 30 trades ou plus : {np.mean(np.array(trades) >= 30):.0%}, sans aucun trade : {np.mean(np.array(trades) == 0):.0%}")
    for tf in TEST_DAYS:
        sub = [b for b in bots if b["tf"] == tf]
        if sub:
            print(f"  {tf:>3} : {len(sub):3d} bots, {np.mean([b['trades'] for b in sub]):5.1f} trades par bot")
    nets = [x for b in bots for x in b["nets"]]
    if nets:
        print(f"tous leurs trades : {len(nets)}, {np.mean(np.array(nets) > 0):.0%} gagnants, {np.mean(nets):+.3%} par trade")
    print(f"{time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
