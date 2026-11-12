"""Audit : combien de temps un bot survit-il aux re-tests toutes les 3 heures ?

Sur des cryptos en marche au hasard, on refait le test de la crypto toutes les 3 heures pendant 48 heures, comme
l'essaim (retest_coin, le vrai code), et on applique sa règle : un bot que le test ne choisit plus s'arrête. On mesure
la part des bots gardés d'un test au suivant, leur durée de vie et le nombre de trades qu'ils ont eu le temps de faire.

Lancer (environ 7 minutes sur 4 cœurs) : python audit/rotation.py rotation.json 101 102 103 104 105 106 107 108 109 110 111 112
(le fichier du détail, puis une graine par crypto fabriquée).
"""
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
from tradingbot.swarm import TEST_DAYS, SwarmSettings, retest_coin  # noqa: E402

HOUR = 3_600_000
STEP_H, ROUNDS = 3, 17  # 17 tests : 48 heures


def study(seed: int):
    close, wick, volume = path(seed)
    symbol = f"H{seed}/USDT"
    settings = asdict(SwarmSettings(bots_per_coin=8))
    alive: dict[str, dict] = {}  # clé -> {"born": tour, "row": ligne du test}
    done = []
    kept, total = [], []
    for k in range(ROUNDS):
        now = T_CUT + k * STEP_H * HOUR
        frames = {tf: frame(close, wick, volume, tf, now - d * DAY, now) for tf, d in TEST_DAYS.items()}
        result = retest_coin(symbol, frames, settings)
        chosen = {r["key"]: r for r in result["chosen"]}
        if k:
            total.append(len(alive))
            kept.append(sum(1 for key in alive if key in chosen))
        for key in [key for key in alive if key not in chosen]:
            done.append({**alive.pop(key), "died": k})
        for key, r in chosen.items():
            alive.setdefault(key, {"born": k, "row": {x: r[x] for x in ("symbol", "timeframe", "technique", "side",
                                                                          "target_r", "stop_mode", "leverage", "section")}})
    for key, bot in alive.items():
        done.append({**bot, "died": None})
    out = []
    for bot in done:
        tf = bot["row"]["timeframe"]
        born = T_CUT + bot["born"] * STEP_H * HOUR
        end = T_CUT + (bot["died"] if bot["died"] is not None else ROUNDS - 1) * STEP_H * HOUR
        df = frame(close, wick, volume, tf, born - TEST_DAYS[tf] * DAY, max(end, born + HOUR))
        book = simulate(df, spec_from(bot["row"]))
        trades = [t for t in book.s["trades"] if born <= t["entry_ts"] < end and t["reason"] != "fin du test"]
        out.append({"tf": tf, "born": bot["born"], "died": bot["died"], "trades": len(trades),
                    "nets": [t["net"] for t in trades]})
    return {"seed": seed, "kept": kept, "total": total, "bots": out}


def main():
    seeds = [int(s) for s in sys.argv[2:]]
    started = time.time()
    with ProcessPoolExecutor(4) as pool:
        rows = list(pool.map(study, seeds))
    Path(sys.argv[1]).write_text(json.dumps(rows), encoding="utf-8")
    kept = sum(sum(r["kept"]) for r in rows)
    total = sum(sum(r["total"]) for r in rows)
    bots = [b for r in rows for b in r["bots"]]
    ended = [b for b in bots if b["died"] is not None]
    lives = [(b["died"] - b["born"]) * STEP_H for b in ended]
    print(f"{len(seeds)} cryptos au hasard, {ROUNDS} tests chacune (toutes les {STEP_H} h pendant {(ROUNDS - 1) * STEP_H} h)")
    print(f"bots gardés d'un test au suivant : {kept}/{total} = {kept / total:.0%}")
    print(f"bots créés en tout : {len(bots)} ({len(bots) / len(seeds):.1f} par crypto), dont arrêtés par un test : {len(ended)}")
    if lives:
        print(f"durée de vie des bots arrêtés : médiane {np.median(lives):.0f} h, moyenne {np.mean(lives):.1f} h ; "
              f"arrêtés dès le test suivant : {np.mean(np.array(lives) <= STEP_H):.0%}")
    trades = [b["trades"] for b in bots]
    print(f"trades par bot pendant sa vie : médiane {np.median(trades):.0f}, moyenne {np.mean(trades):.1f}, "
          f"bots avec 30 trades ou plus : {np.mean(np.array(trades) >= 30):.0%}, sans aucun trade : {np.mean(np.array(trades) == 0):.0%}")
    for tf in TEST_DAYS:
        sub = [b for b in bots if b["tf"] == tf]
        if not sub:
            continue
        sub_ended = [(b["died"] - b["born"]) * STEP_H for b in sub if b["died"] is not None]
        print(f"  {tf:>3} : {len(sub):3d} bots, {np.mean([b['trades'] for b in sub]):5.1f} trades par bot, arrêtés "
              f"{len(sub_ended)}/{len(sub)}, vie médiane {np.median(sub_ended) if sub_ended else float('nan'):.0f} h")
    nets = [x for b in bots for x in b["nets"]]
    if nets:
        print(f"tous leurs trades : {len(nets)}, {np.mean(np.array(nets) > 0):.0%} gagnants, {np.mean(nets):+.3%} par trade")
    print(f"{time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
