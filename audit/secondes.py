"""Audit : le très, très court terme. Les techniques du bot sur des bougies de quelques secondes, fabriquées à partir de
chaque transaction réelle (archives publiques de Binance, marché au comptant).

- Les cryptos : les `--cryptos` paires USDT les plus échangées (là où un ordre a le plus de chances d'être servi).
- Chaque technique, à l'achat et à la vente, avec les trois sorties, passe par le moteur des bots (fleet.simulate) :
  signal à la clôture d'une bougie, entrée au prix suivant, frais des contrats à terme et glissement compris.
- On cherche sur la première moitié des jours, on ne croit que ce qui se confirme sur la seconde.
- Le rapport donne aussi le résultat AVANT frais : c'est lui qui dit si « beaucoup de trades » peut payer.

Lancer : python audit/secondes.py --secondes 15 --jours 14 --fin 2026-11-12 --cryptos 10 --sortie secondes.json
Rien n'est écrit dans data/ ; le cache est hors du dépôt.
"""
import argparse
import io
import json
import math
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vrai  # noqa: E402
from tradingbot.data import ohlcv_to_frame  # noqa: E402
from tradingbot.fleet import EXITS, SECURE_PART, SECURE_R, SIDES, Spec, signals_for, simulate, technique  # noqa: E402
from tradingbot.risk import clustered_bounds  # noqa: E402
from tradingbot.scanner import tradable  # noqa: E402
from tradingbot.swarm import LIBRARY  # noqa: E402

DAY = 86_400_000
ARCHIVE = "https://data.binance.vision/data/spot/daily/aggTrades/{id}/{id}-aggTrades-{day}.zip"
MIN_TRADES = 300  # trades au moins, sur la première moitié, pour juger une technique dans un sens


def bars(args) -> tuple[str, str, pd.DataFrame | None]:
    """Les bougies d'une journée d'une crypto, faites de ses transactions (prix, quantité, heure)."""
    market, day, seconds, cache = args
    path = cache / f"{market}-{seconds}s-{day}.pkl"
    if path.exists():
        return market, day, pd.read_pickle(path)
    try:
        reply = requests.get(ARCHIVE.format(id=market, day=day), timeout=120)
    except Exception:
        return market, day, None
    if reply.status_code != 200:
        return market, day, None
    with zipfile.ZipFile(io.BytesIO(reply.content)) as archive:
        trades = pd.read_csv(archive.open(archive.namelist()[0]), header=None, usecols=[1, 2, 5], names=["price", "qty", "ts"],
                             dtype=str)
    trades = trades[pd.to_numeric(trades["ts"], errors="coerce").notna()].astype(float)  # une ligne de titres : ôtée
    stamp = trades["ts"].to_numpy()
    stamp = np.where(stamp > 1e14, stamp // 1000, stamp).astype(np.int64)  # depuis 2025 : des microsecondes
    step = seconds * 1000
    trades["bar"] = stamp // step * step
    made = trades.groupby("bar").agg(open=("price", "first"), high=("price", "max"), low=("price", "min"),
                                     close=("price", "last"), volume=("qty", "sum"))
    start = int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)
    made = made.reindex(np.arange(start, start + DAY, step))
    made["close"] = made["close"].ffill().bfill()  # une bougie sans transaction : le dernier prix, aucun volume
    for column in ("open", "high", "low"):
        made[column] = made[column].fillna(made["close"])
    made["volume"] = made["volume"].fillna(0.0)
    made = made.reset_index(names="ts")
    made.to_pickle(path)
    return market, day, made


def _simulate(args):
    """Toutes les combinaisons d'une crypto sur ses bougies de quelques secondes : chaque trade, avant et après frais."""
    symbol, frame, unit = args
    rows = []
    for t, name in enumerate(LIBRARY):
        params = technique(name)
        for s, side in enumerate(SIDES):
            signals = signals_for(frame, params, side)
            for e, (target, mode) in enumerate(EXITS):
                spec = Spec("scalping", symbol, unit, name, side, target, 5.0, mode, SECURE_R, SECURE_PART)
                for trade in simulate(frame, spec, signals=signals).s["trades"]:
                    if trade["reason"] != "fin du test":
                        rows.append((t, s, e, trade["exit_ts"], trade["net"], trade["gross"]))
    return symbol, np.array(rows, dtype=np.float64).reshape(-1, 6)


def summary(net: np.ndarray, gross: np.ndarray, day: np.ndarray) -> dict:
    if not len(net):
        return {"n": 0}
    days = np.unique(day)
    by = lambda v: [(int((day == d).sum()), float(v[day == d].sum())) for d in days]  # noqa: E731
    clean = lambda x: x if math.isfinite(x) else None  # noqa: E731
    mean, lo, hi = clustered_bounds(by(net))
    before, before_lo, before_hi = clustered_bounds(by(gross))
    return {"n": int(len(net)), "mean": mean, "lo": clean(lo), "hi": clean(hi), "gross": before, "gross_lo": clean(before_lo),
            "gross_hi": clean(before_hi), "win": float((net > 0).mean())}


def show(title: str, m: dict) -> str:
    if not m.get("n"):
        return f"  {title:<44} aucun trade"
    span = lambda a, b: f"[{vrai.pct(a)} ; {vrai.pct(b)}]" if a is not None else ""  # noqa: E731
    return (f"  {title:<44} {m['n']:>8} trades  après frais {vrai.pct(m['mean'])} {span(m['lo'], m['hi'])}  "
            f"avant frais {vrai.pct(m['gross'])} {span(m['gross_lo'], m['gross_hi'])}  {100 * m['win']:.0f} % gagnants")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--secondes", type=int, default=15)
    parser.add_argument("--jours", type=int, default=14)
    parser.add_argument("--fin", default="", help="dernier jour (AAAA-MM-JJ) ; défaut : avant-hier")
    parser.add_argument("--cryptos", type=int, default=10)
    parser.add_argument("--cache", default=vrai.CACHE)
    parser.add_argument("--coeurs", type=int, default=3)
    parser.add_argument("--sortie", default="")
    args = parser.parse_args()
    cache = Path(args.cache) / "secondes"
    cache.mkdir(parents=True, exist_ok=True)
    ex = vrai.exchange()
    ex.load_markets()
    last = pd.Timestamp(args.fin, tz="UTC") if args.fin else pd.Timestamp(ex.fetch_time() - 2 * DAY, unit="ms", tz="UTC").normalize()
    days = [str((last - pd.Timedelta(days=k)).date()) for k in range(args.jours - 1, -1, -1)]
    tickers = ex.fetch_tickers()
    liquid = sorted((s for s, m in ex.markets.items() if tradable(m, "USDT") and s in tickers),
                    key=lambda s: -(tickers[s].get("quoteVolume") or 0.0))[:args.cryptos]
    unit = f"{args.secondes}s"
    print(f"Bougies de {args.secondes} secondes, du {days[0]} au {days[-1]}, pour : {', '.join(s.split('/')[0] for s in liquid)}",
          flush=True)
    jobs = [(ex.market(s)["id"], day, args.secondes, cache) for s in liquid for day in days]
    made: dict[str, list] = {}
    with ThreadPoolExecutor(4) as pool:
        for k, (market, day, frame) in enumerate(pool.map(bars, jobs), 1):
            if frame is not None:
                made.setdefault(market, []).append(frame)
            if k % 20 == 0 or k == len(jobs):
                print(f"  transactions : {k}/{len(jobs)} journées lues", flush=True)
    frames = {}
    for symbol in liquid:
        parts = made.get(ex.market(symbol)["id"]) or []
        if len(parts) >= args.jours // 2:
            whole = pd.concat(parts).sort_values("ts")
            frames[symbol] = ohlcv_to_frame(whole[["ts", "open", "high", "low", "close", "volume"]].to_numpy().tolist())
    sizes = [float((f["high"] / f["low"] - 1).median()) for f in frames.values()]
    print(f"{len(frames)} cryptos · une bougie de {args.secondes} s bouge de {np.median(sizes):.3%} (médiane, du plus bas au plus "
          "haut) ; un aller-retour coûte 0,14 %", flush=True)
    began, parts = time.time(), []
    with ProcessPoolExecutor(max_workers=args.coeurs) as pool:
        for k, (symbol, rows) in enumerate(pool.map(_simulate, [(s, f, unit) for s, f in frames.items()]), 1):
            parts.append(rows)
            print(f"  {k}/{len(frames)} {symbol:<12} {len(rows)} trades · {time.time() - began:4.0f} s", flush=True)
    rows = np.concatenate(parts)
    tech, short, way = rows[:, 0].astype(int), rows[:, 1].astype(bool), rows[:, 2].astype(int)
    out, net, gross = rows[:, 3].astype(np.int64), rows[:, 4], rows[:, 5]
    day = out // DAY
    half = np.sort(np.unique(day))[len(np.unique(day)) // 2]
    first, second = day < half, day >= half
    report = {"seconds": args.secondes, "days": days, "coins": list(frames), "trades": int(len(net)), "pooled": {}}
    print(f"\nLE TRÈS COURT TERME : {len(net)} trades en bougies de {args.secondes} secondes, {len(frames)} cryptos, {len(days)} jours")
    groups = {"Tous les trades": np.ones(len(net), bool), "Achats": ~short, "Ventes à découvert": short,
              **{f"Sortie : {('par la règle', 'objectif 2R', 'stop suiveur')[e]}": way == e for e in range(len(EXITS))}}
    for title, pick in groups.items():
        report["pooled"][title] = summary(net[pick], gross[pick], day[pick])
        print(show(title, report["pooled"][title]))
    cells = []
    for t, name in enumerate(LIBRARY):
        for s in (False, True):
            pick = (tech == t) & (short == s)
            cells.append({"name": f"{name} · {'vente' if s else 'achat'}", "t": t, "s": s,
                          "a": summary(net[pick & first], gross[pick & first], day[pick & first]),
                          "b": summary(net[pick & second], gross[pick & second], day[pick & second]),
                          "all": summary(net[pick], gross[pick], day[pick])})
    judged = [c for c in cells if c["a"].get("n", 0) >= MIN_TRADES]
    candidates = [c for c in judged if (c["a"]["lo"] or -1) > 0]
    alpha = 0.025 / max(len(candidates), 1)

    def confirmed(c) -> bool:
        pick = (tech == c["t"]) & (short == c["s"]) & second
        groups = [(int((day[pick] == d).sum()), float(net[pick][day[pick] == d].sum())) for d in np.unique(day[pick])]
        return bool(len(groups) >= 2 and clustered_bounds(groups, alpha)[1] > 0)

    kept = [c for c in candidates if confirmed(c)]
    print(f"\nTECHNIQUES (une technique dans un sens) : {len(judged)} avec au moins {MIN_TRADES} trades sur la première moitié")
    print(f"  gagnent après frais sur la première moitié (fourchette toute positive) : {len(candidates)} · gagnent encore en "
          f"moyenne sur la seconde : {sum(1 for c in candidates if c['b'].get('n') and c['b']['mean'] > 0)} · CONFIRMÉES : {len(kept)}")
    print(f"  ont un gain AVANT frais nettement positif sur toute la période : "
          f"{sum(1 for c in cells if c['all'].get('n', 0) >= MIN_TRADES and (c['all']['gross_lo'] or -1) > 0)} sur "
          f"{sum(1 for c in cells if c['all'].get('n', 0) >= MIN_TRADES)}")
    ranked = sorted((c for c in cells if c["all"].get("n", 0) >= MIN_TRADES), key=lambda c: -c["all"]["mean"])
    for title, part in (("Les 8 meilleures après frais (toute la période)", ranked[:8]), ("Les 3 pires", ranked[-3:])):
        print(title + " :")
        for c in part:
            print(show(("CONFIRMÉE " if c in kept else "") + c["name"], c["all"]))
    report.update(cells=cells, counts={"judged": len(judged), "candidates": len(candidates),
                                       "confirmed": [c["name"] for c in kept]})
    if args.sortie:
        Path(args.sortie).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\nDétail écrit dans {args.sortie}")


if __name__ == "__main__":
    main()
