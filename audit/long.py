"""Audit : le long terme. Les techniques du bot sur des bougies d'un jour et plusieurs années de vraies données Binance,
puis le portefeuille « momentum » (garder les cryptos qui montent le plus).

Comme pour le court terme : on cherche sur une première période, on ne croit que ce qui se confirme sur la suivante.

- L'univers est reconstitué jour par jour : les `--cryptos` paires USDT les plus échangées sur les 30 jours d'avant (au
  moins 5 M$ par jour), y compris celles qui ont été retirées de la cote depuis (sinon le passé est embelli).
- Chaque technique, à l'achat et à la vente, avec les trois sorties, passe par le moteur des bots (fleet.simulate) :
  frais des contrats à terme et financement compris, sans levier. Un trade compte s'il a été ouvert pendant que la
  crypto était dans l'univers.
- Sur des années, le marché monte ou baisse beaucoup : un achat gagne « tout seul » quand tout monte. Chaque trade est
  donc aussi mesuré contre le marché (le panier de toutes les cryptos de l'univers, à parts égales, sur les mêmes
  jours) : c'est cet écart qui dit si la règle apporte quelque chose de plus que « acheter et garder ».
- La fourchette compare les mois entre eux (risk.clustered_bounds).

Lancer : python audit/long.py --depuis 2020-01-01 --coupure 2024-01-01 --cryptos 50 --sortie long.json
Rien n'est écrit dans data/ ; le cache des bougies est hors du dépôt.
"""
import argparse
import json
import math
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vrai  # noqa: E402
from tradingbot import portfolio, trend  # noqa: E402
from tradingbot.fleet import EXITS, SECURE_PART, SECURE_R, SIDES, Spec, signals_for, simulate, technique  # noqa: E402
from tradingbot.risk import clustered_bounds  # noqa: E402
from tradingbot.scanner import LEVERAGED_SUFFIXES, STABLE_OR_PEGGED, tokenized_stock  # noqa: E402
from tradingbot.strategy import PATTERN_FAMILIES  # noqa: E402
from tradingbot.swarm import LIBRARY, MIN_VOLUME  # noqa: E402

DAY = 86_400_000
LIQUID_DAYS = 30  # l'univers d'un jour : le volume moyen des 30 jours d'avant
MIN_TRADES = 100  # trades au moins, sur la première période, pour juger une technique dans un sens
SPOT_COST = 0.0015  # portefeuille au comptant : 0,10 % de frais et 0,05 % de glissement par ordre
EARLY = "2017-08-17"  # le premier jour de cotation du Bitcoin en USDT sur Binance
READING = np.array([technique(name).strategy_type in PATTERN_FAMILIES for name in LIBRARY])
LOCAL = threading.local()


def _candles(args):
    symbol, start, end, cache = args
    if not hasattr(LOCAL, "ex"):
        LOCAL.ex = vrai.exchange()
        LOCAL.ex.load_markets()
    try:
        return symbol, vrai.candles(LOCAL.ex, symbol, "1d", start, end, cache)
    except Exception as exc:  # une paire retirée dont l'historique ne répond plus : ignorée, et dite
        return symbol, str(exc)[:80]


def load(ex, start: int, end: int, cache: Path) -> dict[str, pd.DataFrame]:
    """Les bougies d'un jour de toutes les paires USDT au comptant, cotées aujourd'hui ou retirées depuis."""
    names = sorted(s for s, m in ex.markets.items() if m.get("spot") and m.get("quote") == "USDT"
                   and m.get("base") not in STABLE_OR_PEGGED and not str(m.get("base", "")).endswith(LEVERAGED_SUFFIXES)
                   and not tokenized_stock(m))
    gone = sum(1 for s in names if ex.markets[s].get("active") is False)
    print(f"{len(names)} paires USDT (dont {gone} retirées de la cote)", flush=True)
    frames, failed = {}, 0
    with ThreadPoolExecutor(4) as pool:
        for k, (symbol, frame) in enumerate(pool.map(_candles, [(s, start, end, cache) for s in names]), 1):
            if isinstance(frame, str):
                failed += 1
            elif len(frame) >= 60:
                frames[symbol] = frame.reset_index(drop=True)
            if k % 100 == 0:
                print(f"  bougies d'un jour : {k}/{len(names)} paires", flush=True)
    print(f"{len(frames)} paires avec au moins 60 jours d'historique ({failed} sans réponse)", flush=True)
    return frames


def universe(frames: dict[str, pd.DataFrame], top: int) -> tuple[pd.DataFrame, pd.Series]:
    """Pour chaque jour, les cryptos suivies (connues la veille : aucun regard vers le futur), et le « marché » : la
    somme des variations journalières du panier de ces cryptos à parts égales (en logarithme, à la clôture)."""
    close = pd.DataFrame({s: f.set_index("ts")["close"] for s, f in frames.items()}).sort_index()
    money = pd.DataFrame({s: f.set_index("ts")["volume"] * f.set_index("ts")["close"] for s, f in frames.items()})
    liquid = money.sort_index().rolling(LIQUID_DAYS, min_periods=20).mean().shift(1)
    member = (liquid.rank(axis=1, ascending=False) <= top) & (liquid >= MIN_VOLUME)
    change = close.pct_change(fill_method=None).where(member)
    market = np.log1p(change.mean(axis=1).fillna(0.0)).cumsum()
    return member, market


def stretches(flags: pd.Series) -> list[list[int]]:
    out, current = [], None
    for ts, flag in flags.items():
        if flag and current is None:
            current = int(ts)
        elif not flag and current is not None:
            out.append([current, int(ts) - 1])
            current = None
    if current is not None:
        out.append([current, int(flags.index[-1]) + DAY])
    return out


def _simulate(args):
    """Toutes les combinaisons d'une crypto en bougies d'un jour : les trades ouverts pendant qu'elle était suivie."""
    symbol, frame, active = args
    rows = []
    for t, name in enumerate(LIBRARY):
        params = technique(name)
        if len(frame) < params.warmup_bars + 30:
            continue
        for s, side in enumerate(SIDES):
            signals = signals_for(frame, params, side)
            for e, (target, mode) in enumerate(EXITS):
                spec = Spec("long", symbol, "1d", name, side, target, 1.0, mode, SECURE_R, SECURE_PART)
                for trade in simulate(frame, spec, signals=signals).s["trades"]:
                    start = trade["entry_ts"]
                    if trade["reason"] != "fin du test" and any(a <= start <= b for a, b in active):
                        rows.append((t, s, e, start, trade["exit_ts"], trade["net"]))
    return symbol, np.array(rows, dtype=np.float64).reshape(-1, 6)


def summary(net: np.ndarray, extra: np.ndarray, month: np.ndarray) -> dict:
    """Trades, gain moyen par trade et gain moyen contre le marché, avec leurs fourchettes par mois."""
    if not len(net):
        return {"n": 0}
    months = np.unique(month)
    by = lambda values: [(int((month == m).sum()), float(values[month == m].sum())) for m in months]  # noqa: E731
    clean = lambda x: x if math.isfinite(x) else None  # noqa: E731
    mean, lo, hi = clustered_bounds(by(net))
    gap, gap_lo, gap_hi = clustered_bounds(by(extra))
    return {"n": int(len(net)), "mean": mean, "lo": clean(lo), "hi": clean(hi), "extra": gap, "extra_lo": clean(gap_lo),
            "extra_hi": clean(gap_hi), "win": float((net > 0).mean()), "months": int(len(months))}


def show(title: str, m: dict) -> str:
    if not m.get("n"):
        return f"  {title:<44} aucun trade"
    span = lambda a, b: f"[{vrai.pct(a, 2)} ; {vrai.pct(b, 2)}]" if a is not None else ""  # noqa: E731
    return (f"  {title:<44} {m['n']:>6} trades  par trade {vrai.pct(m['mean'], 2)} {span(m['lo'], m['hi'])}  "
            f"contre le marché {vrai.pct(m['extra'], 2)} {span(m['extra_lo'], m['extra_hi'])}  "
            f"{100 * m['win']:.0f} % gagnants")


def growth(returns) -> dict:
    """Ce que devient 1 placé au début : le total, le rythme par an, la pire baisse depuis un sommet."""
    values = np.cumprod(1 + np.asarray(returns, dtype=float))
    peak = np.maximum.accumulate(values)
    return {"total": float(values[-1]), "worst": float((values / peak - 1).min())}


def trend_rules(majors: dict[str, pd.DataFrame], cut: int) -> list[dict]:
    """Le filtre de tendance sur le Bitcoin et l'Ether, rejoué par le moteur du bot (`tradingbot.trend.replay` : la
    même fonction que le compte fictif du site, pas une formule à part). Toutes les règles partent du même jour."""
    y2020 = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp() * 1000)
    spans = (("avant 2020", 0, y2020), ("de 2020 à la coupure", y2020, cut), ("depuis la coupure", cut, 2 ** 62),
             ("tout", 0, 2 ** 62))
    dear = replace(trend.SPOT, fee_rate=0.004, slippage=0.001)  # une plateforme chère : 0,50 % par ordre
    out = []
    for symbol, df in majors.items():
        first = int(df["ts"].iloc[max(trend.AVERAGES)])
        rules = [("acheté et gardé", None, trend.SPOT),
                 *[(f"au-dessus de sa moyenne {n} jours", (n,), trend.SPOT) for n in trend.AVERAGES],
                 ("les trois moyennes, un tiers chacune", trend.AVERAGES, trend.SPOT),
                 ("les trois moyennes, à 0,50 % par ordre", trend.AVERAGES, dear)]
        for name, averages, ex in rules:
            run = trend.replay(df, start_ts=first, ex=ex, averages=averages or trend.AVERAGES)
            values = run.hold if averages is None else run.value
            cells = {}
            for label, lo, hi in spans:
                inside = np.flatnonzero((run.ts >= lo) & (run.ts < hi))
                base = run.capital if inside[0] == 0 else values[inside[0] - 1]
                cells[label] = {k: v for k, v in trend.growth(values[inside], base).items() if k != "yearly"}
            orders = 0.0 if averages is None else len(run.orders) / (len(run) / 365)
            print(f"  {symbol.split('/')[0]} {name:<38} " + " · ".join(
                f"{label} ×{g['total']:.2f} ({g['worst']:.0%})" for label, g in cells.items()) + f" · {orders:.0f} ordres par an")
            out.append({"symbol": symbol, "rule": name, "orders_per_year": orders, **cells})
    return out


def simple_rules(frames: dict, opens: pd.DataFrame, closes: pd.DataFrame, member: pd.DataFrame, cut: int,
                 majors: dict[str, pd.DataFrame]) -> dict:
    """Ce qu'un débutant peut vraiment tenir, comparé franchement à « acheter et garder », en argent composé (ce que
    devient 1 placé au début) et avec la pire baisse en route. Seuils ronds, fixés d'avance : 50, 100 et 200 jours.
    1. Le filtre de tendance sur le Bitcoin et l'Ether : ne tenir que si la clôture est au-dessus de sa moyenne des N
       derniers jours (décidé à la clôture, ordre à l'ouverture du lendemain, 0,15 % par ordre).
    2. Le même filtre sur toutes les cryptos suivies : chaque jour, à parts égales, celles qui sont au-dessus de leur
       moyenne, contre le panier de toutes.
    3. Les portefeuilles de la semaine : les 3 qui ont le plus monté, les 3 qui ont le plus baissé."""
    out = {"trend": [], "basket": [], "weekly": []}
    parts = (("avant la coupure", lambda ts: ts < cut), ("après", lambda ts: ts >= cut))
    print("\nLES RÈGLES SIMPLES, EN ARGENT COMPOSÉ (ce que devient 1 placé au début ; entre parenthèses : la pire baisse)")
    print("1. Bitcoin et Ether depuis 2017 : ne tenir que si la clôture est au-dessus de sa moyenne des N jours (décidé à "
          "la clôture, ordre à l'ouverture du lendemain, 0,15 % par ordre). « Les trois moyennes » : un tiers du compte "
          "par moyenne dépassée, pour ne pas choisir un réglage après coup. C'est la règle du bot de tendance.")
    out["trend"] = trend_rules(majors, cut)
    print("2. Toutes les cryptos suivies, à parts égales, revues chaque jour (0,15 % sur ce qui change) :")
    close = pd.DataFrame({s: f.set_index("ts")["close"] for s, f in frames.items()}).sort_index()
    tomorrow = close.pct_change(fill_method=None).shift(-1)
    baskets = {"le panier de toutes": member}
    for n in (50, 100, 200):
        baskets[f"seulement au-dessus de leur moyenne {n} jours"] = member & (close > close.rolling(n).mean())
    keep = close.index >= close.index[230]
    for name, held in baskets.items():
        weight = held.astype(float).div(held.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        earned = (weight * tomorrow.fillna(0.0)).sum(axis=1) - SPOT_COST * weight.diff().abs().sum(axis=1)
        earned = earned[keep & tomorrow.notna().any(axis=1).to_numpy()]
        whole = growth(earned)
        halves = [growth(earned[np.asarray(when(earned.index))]) for _, when in parts]
        print(f"  {name:<46} ×{whole['total']:<6.2f} pire baisse {whole['worst']:.0%} · avant la coupure ×{halves[0]['total']:.2f} "
              f"({halves[0]['worst']:.0%}) · après ×{halves[1]['total']:.2f} ({halves[1]['worst']:.0%}) · "
              f"{held[keep].sum(axis=1).mean():.0f} cryptos tenues en moyenne")
        out["basket"].append({"rule": name, **whole, "before": halves[0], "after": halves[1]})
    print("3. Chaque semaine, parmi les cryptos suivies (frais compris) :")
    for title, prices, params in (("les 3 qui ont le plus monté en 28 jours", closes, portfolio.PortfolioParams(28, 3)),
                                  ("les 3 qui ont le plus baissé en 7 jours", 1 / closes, portfolio.PortfolioParams(7, 3)),
                                  ("les 3 qui ont le plus baissé en 28 jours", 1 / closes, portfolio.PortfolioParams(28, 3))):
        totals = []
        for shift in range(7):  # les sept jours de rotation possibles : le résultat ne doit pas dépendre du jour choisi
            weeks = portfolio.simulate(opens.iloc[60 + shift:], prices.iloc[60 + shift:], params, SPOT_COST)
            totals.append((growth([w.ret for w in weeks]), growth([w.basket for w in weeks])))
        spread = sorted(t[0]["total"] for t in totals)
        rule, basket = totals[0]
        print(f"  {title} : de ×{spread[0]:.2f} à ×{spread[-1]:.2f} selon le jour de rotation, pire baisse {rule['worst']:.0%} · "
              f"le panier de toutes : ×{basket['total']:.2f}")
        out["weekly"].append({"rule": title, "low": spread[0], "high": spread[-1], "worst": rule["worst"], "basket": basket["total"]})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--depuis", default="2020-01-01")
    parser.add_argument("--coupure", default="2024-01-01", help="avant : on cherche ; après : on confirme")
    parser.add_argument("--cryptos", type=int, default=50, help="cryptos suivies chaque jour (les plus échangées)")
    parser.add_argument("--cache", default=vrai.CACHE)
    parser.add_argument("--coeurs", type=int, default=4)
    parser.add_argument("--sortie", default="")
    args = parser.parse_args()
    cache = Path(args.cache)
    ex = vrai.exchange()
    ex.load_markets()
    start = int(pd.Timestamp(args.depuis, tz="UTC").timestamp() * 1000)
    cut = int(pd.Timestamp(args.coupure, tz="UTC").timestamp() * 1000)
    end = ex.fetch_time() // DAY * DAY
    frames = load(ex, start, end, cache)
    member, market = universe(frames, args.cryptos)
    followed = {s: stretches(member[s]) for s in member.columns if member[s].any()}
    print(f"{len(followed)} cryptos ont été suivies à un moment (les {args.cryptos} plus échangées de chaque jour)", flush=True)
    began, parts = time.time(), []
    jobs = [(s, frames[s], followed[s]) for s in sorted(followed)]
    with ProcessPoolExecutor(max_workers=args.coeurs) as pool:
        for k, (symbol, rows) in enumerate(pool.map(_simulate, jobs), 1):
            parts.append(rows)
            if k % 40 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)} cryptos simulées · {time.time() - began:4.0f} s", flush=True)
    rows = np.concatenate(parts)
    tech, short = rows[:, 0].astype(int), rows[:, 1].astype(bool)
    entry, out, net = rows[:, 3].astype(np.int64), rows[:, 4].astype(np.int64), rows[:, 5]
    # contre le marché : la variation du panier entre la veille de l'entrée et le jour de la sortie
    level = lambda ts: market.reindex(pd.Index(ts // DAY * DAY), method="ffill").to_numpy()  # noqa: E731
    moved = np.expm1(level(out) - level(entry - DAY))
    extra = net - np.where(short, -moved, moved)
    month = pd.to_datetime(out, unit="ms").to_period("M").astype(str).to_numpy()
    days = (out - entry) / DAY
    halves = {"recherche": out < cut, "confirmation": out >= cut}
    label = {"recherche": f"du {args.depuis} au {args.coupure}", "confirmation": f"depuis le {args.coupure}"}
    report = {"start": start, "cut": cut, "end": end, "coins": len(followed), "trades": int(len(net)), "pooled": {},
              "cells": []}
    print(f"\nLE LONG TERME : {len(net)} trades en bougies d'un jour, {len(followed)} cryptos, durée moyenne d'un trade "
          f"{days.mean():.0f} jours (frais et financement compris, sans levier)")
    for name, mask in halves.items():
        span = market[(market.index >= (start if name == "recherche" else cut)) & (market.index < (cut if name == "recherche" else end))]
        yearly = math.expm1((span.iloc[-1] - span.iloc[0]) * 365 / max(len(span), 1)) if len(span) > 1 else math.nan
        print(f"\n--- {label[name]} : le panier de l'univers a fait {yearly:+.0%} par an (repère « acheter et garder ») ---")
        groups = {"Tous les trades": mask, "Achats": mask & ~short, "Ventes à découvert": mask & short,
                  "Lectures du graphique": mask & READING[tech], "Indicateurs": mask & ~READING[tech]}
        report["pooled"][name] = {}
        for title, pick in groups.items():
            report["pooled"][name][title] = summary(net[pick], extra[pick], month[pick])
            print(show(title, report["pooled"][name][title]))
    # chercher sur la première période, confirmer sur la seconde : une technique dans un sens
    first, second = halves["recherche"], halves["confirmation"]
    cells = []
    for t, name in enumerate(LIBRARY):
        for s in (False, True):
            pick = (tech == t) & (short == s)
            a = summary(net[pick & first], extra[pick & first], month[pick & first])
            b = summary(net[pick & second], extra[pick & second], month[pick & second])
            cells.append({"name": f"{name} · {'vente' if s else 'achat'}", "t": t, "s": s, "a": a, "b": b,
                          "days": float(days[pick].mean()) if pick.any() else 0.0})
    judged = [c for c in cells if c["a"].get("n", 0) >= MIN_TRADES]
    earns = [c for c in judged if (c["a"]["lo"] or -1) > 0]
    beats = [c for c in judged if (c["a"]["extra_lo"] or -1) > 0]
    solid = [c for c in judged if (c["a"]["lo"] or -1) > 0 and (c["a"]["extra_lo"] or -1) > 0]
    alpha = 0.025 / max(len(solid), 1)

    def confirmed(c) -> bool:
        b = c["b"]
        if b.get("n", 0) < MIN_TRADES // 2:
            return False
        pick = (tech == c["t"]) & (short == c["s"]) & second
        months = np.unique(month[pick])
        low = lambda v: clustered_bounds([(int((month[pick] == m).sum()), float(v[pick][month[pick] == m].sum())) for m in months], alpha)[1]  # noqa: E731
        return bool(low(net) > 0 and low(extra) > 0)

    print(f"\nTECHNIQUES (une technique dans un sens, les trois sorties réunies) : {len(judged)} avec au moins {MIN_TRADES} trades "
          f"sur la première période")
    print(f"  sur la première période, fourchette toute positive : {len(earns)} gagnent de l'argent · {len(beats)} font mieux "
          f"que le marché · {len(solid)} font les deux (les candidates)")
    kept = [c for c in solid if confirmed(c)]
    still = [c for c in solid if c["b"].get("n", 0) and c["b"]["mean"] > 0 and c["b"]["extra"] > 0]
    print(f"  sur la seconde période : {len(still)} candidates gagnent encore et battent encore le marché en moyenne · "
          f"CONFIRMÉES (fourchettes durcies toutes positives) : {len(kept)}")
    for title, part in (("Les candidates (jusqu'à 12, les meilleures contre le marché d'abord)",
                         sorted(solid, key=lambda c: -c["a"]["extra"])[:12]),
                        ("Les 8 meilleures de la première période contre le marché, candidates ou non",
                         sorted(judged, key=lambda c: -c["a"]["extra"])[:8])):
        print(title + " :")
        for c in part:
            print(f"  {'CONFIRMÉE ' if c in kept else ''}{c['name']} (trade de {c['days']:.0f} jours en moyenne)")
            print("    " + show("recherche", c["a"]).strip())
            print("    " + show("confirmation", c["b"]).strip())
    report["cells"] = cells
    report["counts"] = {"judged": len(judged), "earns": len(earns), "beats": len(beats), "candidates": len(solid),
                        "still": len(still), "confirmed": [c["name"] for c in kept]}
    # le portefeuille momentum : garder chaque semaine les cryptos de l'univers qui ont le plus monté
    opens = pd.DataFrame({s: f.set_index("ts")["open"] for s, f in frames.items()}).sort_index()
    closes = pd.DataFrame({s: f.set_index("ts")["close"] for s, f in frames.items()}).sort_index().where(member)
    for frame in (opens, closes):
        frame.index = pd.to_datetime(frame.index, unit="ms")
    results = portfolio.evaluate(opens, closes, SPOT_COST)
    print("\nLE PORTEFEUILLE MOMENTUM (au comptant, sans levier : garder 7 jours les cryptos qui ont le plus monté) :")
    print(portfolio.format_rows(results))
    print(portfolio.overall_verdict(results, len(followed)))
    report["portfolio"] = [r.__dict__ for r in results]
    early = int(pd.Timestamp(EARLY, tz="UTC").timestamp() * 1000)  # les deux grandes cryptos, depuis leur cotation
    majors = {s: vrai.candles(ex, s, "1d", early, end, cache) for s in trend.SYMBOLS}
    report["simple"] = simple_rules(frames, opens, closes, member, cut, majors)
    if args.sortie:
        Path(args.sortie).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\nDétail écrit dans {args.sortie}")


if __name__ == "__main__":
    main()
