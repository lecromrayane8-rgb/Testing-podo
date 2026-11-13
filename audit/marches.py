"""La règle du bot de tendance sur d'autres marchés, avec des dizaines d'années de prix (option A, 13/11/2026).

La question : la règle des trois moyennes (`tradingbot.trend`, inchangée : 50, 100 et 200 bougies d'un jour, un tiers
du compte par moyenne dépassée, 0,15 % par ordre) fait-elle aussi mieux que « garder » ailleurs que sur le Bitcoin et
l'Ether, ou sa réussite sur deux cryptos est-elle de la chance ?

LE PROTOCOLE, ÉCRIT AVANT DE CALCULER LE MOINDRE RÉSULTAT (pour ne rien choisir après coup) :

1. Les marchés : toutes les séries de prix d'un jour d'au moins 20 ans que la banque centrale américaine (FRED) donne
   sans clé, une seule par marché : actions américaines (Nasdaq Composite, 1971), actions japonaises (Nikkei 225,
   1949), pétrole (Brent, 1987) et cinq grandes monnaies face au dollar depuis 1971 (yen, livre, franc suisse, dollar
   canadien, dollar australien). Écartés d'avance : S&P 500 et Dow Jones (10 ans seulement chez FRED), Nasdaq-100 (le
   même marché que le Nasdaq Composite), pétrole WTI (le même marché que le Brent, et un prix négatif en 2020). L'or :
   aucune source officielle sans clé ne répond (FRED l'a retiré, la LBMA et Stooq refusent les robots) ; l'or en
   jetons de Binance (PAXG, depuis 2019) est montré à part, pour information.
2. Les prix de FRED sont des clôtures. L'ordre décidé à la clôture d'un jour passe à la clôture du jour SUIVANT (un
   jour de retard : aucun regard vers le futur, et c'est plus dur que la réalité). Les jours sans cotation sont
   retirés : 200 jours = 200 jours de cotation. Indices hors dividendes, argent dehors sans intérêts, monnaies sans
   leurs taux : pareil pour la règle et pour « garder ». Marchés ouverts jour et nuit (cryptos) : l'ordre passe au
   prix de la clôture qui décide, comme le bot à l'ouverture suivante.
3. Ce qui est regardé pour chaque marché : ce que devient l'argent avec la règle et en gardant, la pire baisse de
   chacun, décennie par décennie ; la porte du projet (chaque sortie jugée contre « garder », seuil durci par le
   nombre de lignes) ; et LE TEST DU MÉLANGE : les mêmes journées tirées dans le désordre (mêmes hausses, mêmes
   baisses, même prix d'arrivée, donc « garder » finit pareil, mais plus aucune tendance). Si la règle exploite de
   vraies tendances, elle doit finir plus haut sur le vrai marché que sur presque tous ses mélanges. 1 000 mélanges
   par marché ; « net » = mieux que 99,5 % des mélanges (les 5 % d'erreur admis, partagés entre les 10 marchés jugés).
4. Le verdict d'ensemble, sur les 8 marchés indépendants : les tests du mélange réunis (méthode de Stouffer), et
   toutes les sorties réunies, comparées année par année (`risk.clustered_bounds`), avec un témoin : la même mesure
   sur des marchés tirés au hasard sans tendance (elle doit rendre les frais d'une sortie, −0,30 %).
5. Les cryptos du bot (bougies de Binance) passent le même test du mélange. Le Bitcoin et l'Ether de Coinbase (FRED,
   depuis 2014 et 2016) servent de recoupement : même actif, autre plateforme, donc pas une preuve de plus.

AJOUTÉ APRÈS LES PREMIERS RÉSULTATS, HORS PROTOCOLE (pour comprendre, pas pour juger) :
- le témoin est refait 20 fois au lieu d'une (un seul tirage peut tomber loin de −0,30 % par hasard) ;
- « ce qui mange l'avantage » : la même règle sans le jour de retard, puis avec des frais presque nuls (0,03 % par
  ordre). Le verdict reste celui du protocole : frais du bot, ordre au lendemain.

    python audit/marches.py --sortie marches.json          # --melanges 1000 --coeurs N --csv-dir dossier

`--csv-dir` : des fichiers « Date,Open,High,Low,Close » donnés à la main (or, S&P 500…), mesurés à part avec leurs
vrais prix d'ouverture. Rien n'est lu sur une plateforme d'échange sauf les prix publics de Binance ; rien n'est écrit
dans `data/`."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vrai  # noqa: E402
from tradingbot import trend  # noqa: E402
from tradingbot.data import load_csv  # noqa: E402
from tradingbot.risk import clustered_bounds  # noqa: E402
from tradingbot.robustness import ROBUST  # noqa: E402

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
DAY = trend.DAY_MS
MAIN, CHECK, INFO = "principal", "recoupement", "information"
# (clé courte, nom, série FRED, prix à inverser, marché ouvert jour et nuit, groupe) : la liste du protocole
MARKETS = (
    ("Nasdaq", "Actions américaines (Nasdaq Composite)", "NASDAQCOM", False, False, MAIN),
    ("Nikkei", "Actions japonaises (Nikkei 225)", "NIKKEI225", False, False, MAIN),
    ("Brent", "Pétrole (Brent)", "DCOILBRENTEU", False, False, MAIN),
    ("Yen", "Yen face au dollar", "DEXJPUS", True, False, MAIN),
    ("Livre", "Livre sterling face au dollar", "DEXUSUK", False, False, MAIN),
    ("Franc", "Franc suisse face au dollar", "DEXSZUS", True, False, MAIN),
    ("CAD", "Dollar canadien face au dollar", "DEXCAUS", True, False, MAIN),
    ("AUD", "Dollar australien face au dollar", "DEXUSAL", False, False, MAIN),
    ("BTC-Coinbase", "Bitcoin, prix de Coinbase", "CBBTCUSD", False, True, CHECK),
    ("ETH-Coinbase", "Ether, prix de Coinbase", "CBETHUSD", False, True, CHECK),
)
BINANCE = (("BTC", "Bitcoin, bougies du bot (Binance)", "BTC/USDT", "crypto"),
           ("ETH", "Ether, bougies du bot (Binance)", "ETH/USDT", "crypto"),
           ("Or-jetons", "Or en jetons (PAXG, Binance)", "PAXG/USDT", INFO))
JUDGED = 10  # les 8 marchés indépendants et les 2 cryptos du bot : le seuil « net » est partagé entre eux
WITNESSES = 20  # le témoin sans tendance, refait autant de fois
EXIT_COST = math.log((1 - trend.SPOT.slippage) * (1 - trend.SPOT.fee_rate) ** 2 / (1 + trend.SPOT.slippage))
CHEAP = replace(trend.SPOT, fee_rate=0.0002, slippage=0.0001)  # des frais de professionnel : 0,03 % par ordre


def fred(series: str, cache: Path) -> tuple[np.ndarray, np.ndarray]:
    """Une série de FRED : (jours en ms, valeurs), jours sans cotation retirés ; gardée un jour sur le disque."""
    path = cache / f"fred-{series}.csv"
    if not path.exists() or time.time() - path.stat().st_mtime > 20 * 3600:
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(FRED + series, timeout=90) as response:
            text = response.read().decode("utf-8")
        if not text.startswith("observation_date"):
            raise ValueError(f"FRED ne donne pas la série {series}.")
        path.write_text(text, encoding="utf-8")
    raw = pd.read_csv(path, na_values=["."]).dropna()
    days = pd.to_datetime(raw.iloc[:, 0], utc=True)
    ts = ((days - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1)).to_numpy(dtype="int64")
    return ts, raw.iloc[:, 1].to_numpy(dtype=float)


def frame(ts: np.ndarray, close: np.ndarray, late: bool) -> pd.DataFrame:
    """Des bougies pour le moteur du bot à partir de seules clôtures. `late` : l'ordre décidé à la clôture d'un jour
    passe à la clôture du lendemain (l'« ouverture » du jour d'exécution est sa propre clôture). Sinon, marché ouvert
    jour et nuit : il passe au prix de la clôture qui décide (l'ouverture d'un jour = la clôture de la veille)."""
    open_ = close if late else np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame({"ts": ts, "open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close),
                         "close": close, "volume": 0.0})


def decades(run: trend.Run) -> list[dict]:
    """Décennie par décennie : la règle et « garder » (ce que devient 1, pire baisse dans la décennie)."""
    tens = pd.to_datetime(run.ts, unit="ms", utc=True).year.to_numpy() // 10 * 10
    out, rule0, hold0 = [], run.capital, run.capital
    for ten in np.unique(tens):
        idx = np.flatnonzero(tens == ten)
        rule, hold = run.value[idx], run.hold[idx]
        out.append({"decade": int(ten), "days": int(len(idx)), "rule": float(rule[-1] / rule0),
                    "hold": float(hold[-1] / hold0), "rule_worst": trend.worst(rule, rule0),
                    "hold_worst": trend.worst(hold, hold0)})
        rule0, hold0 = float(rule[-1]), float(hold[-1])
    return out


def sold_year(ms: int) -> int:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").year


def exit_logs(df: pd.DataFrame) -> list[tuple[int, float]]:
    """Toutes les sorties des trois rejeux à une moyenne : (année de la vente, gain en cryptos, en logarithme)."""
    return [(sold_year(e["sold"]), math.log1p(e["ret"])) for n in trend.AVERAGES
            for e in trend.exits(trend.replay(df, averages=(n,)))]


def measure(job: tuple) -> dict:
    """Un marché : la règle contre « garder », le test du mélange, les sorties, et le témoin sans tendance."""
    key, name, group, ts, close, late, shuffles, seed, real = job
    df = frame(ts, close, late) if real is None else real  # `real` : de vraies bougies (ouvertures comprises)
    run = trend.replay(df)
    years = (run.ts[-1] - run.ts[0]) / (365.25 * DAY)
    side = lambda values: {**trend.growth(values, run.capital),  # noqa: E731
                           "yearly": float((values[-1] / run.capital) ** (1 / years) - 1)}
    out = {"key": key, "name": name, "group": group, "from": int(run.ts[0]), "to": int(run.ts[-1]), "years": years,
           "late": bool(late), "rule": side(run.value), "hold": side(run.hold),
           "inside": float((run.level / run.parts).mean()), "orders_per_year": len(run.orders) / years,
           "decades": decades(run), "exits": exit_logs(df)}
    # Le test du mélange, toujours sur les seules clôtures (le vrai marché et ses mélanges, comptés de la même façon).
    rng = np.random.default_rng(seed)
    steps = np.diff(np.log(close))
    path = lambda moves: close[0] * np.exp(np.concatenate(([0.0], np.cumsum(moves))))  # noqa: E731
    base = trend.replay(frame(ts, close, late))
    finals, worsts = np.empty(shuffles), np.empty(shuffles)
    for k in range(shuffles):
        mixed = trend.replay(frame(ts, path(rng.permutation(steps)), late))
        finals[k], worsts[k] = mixed.value[-1], trend.worst(mixed.value, mixed.capital)
    real_final = float(base.value[-1])
    out["shuffle"] = {"n": shuffles, "real": real_final / base.capital, "median": float(np.median(finals)) / base.capital,
                      "beats": float((real_final > finals).mean()),
                      "p": float((1 + (finals >= real_final).sum()) / (shuffles + 1)),
                      "worst": trend.worst(base.value, base.capital), "worst_median": float(np.median(worsts)),
                      "worst_beats": float((trend.worst(base.value, base.capital) > worsts).mean())}
    # Le témoin : des marchés tirés au hasard, sans tendance ni dérive, aussi longs et aussi agités que le vrai.
    out["witness"] = [exit_logs(frame(ts, path(rng.normal(0.0, steps.std(), len(steps))), late))
                      for _ in range(WITNESSES)]
    # Hors protocole : ce qui mange l'avantage (le jour de retard, puis les frais).
    finish = lambda late_, ex: trend.replay(frame(ts, close, late_), ex=ex)  # noqa: E731
    out["what_if"] = {name_: {"total": float(r.value[-1] / r.capital), "worst": trend.worst(r.value, r.capital)}
                      for name_, r in (("protocole", base), ("sans_retard", finish(False, trend.SPOT)),
                                       ("sans_retard_frais_bas", finish(False, CHEAP)))}
    out["what_if"]["garder"] = {"total": float(base.hold[-1] / base.capital), "worst": trend.worst(base.hold, base.capital)}
    return out


def pooled(rows: list[dict], field: str) -> dict:
    """Toutes les sorties réunies, comparées année par année (les marchés chutent souvent ensemble)."""
    by_year: dict[int, list[float]] = {}
    for row in rows:
        for year, log in row[field]:
            by_year.setdefault(year, []).append(log)
    mean, low, high = clustered_bounds([(len(v), sum(v)) for v in by_year.values()])
    logs = [x for v in by_year.values() for x in v]
    return {"n": len(logs), "years": len(by_year), "mean": mean, "low": low, "high": high,
            "wins": float(np.mean(np.array(logs) > 0)) if logs else math.nan}


def stouffer(ps: list[float]) -> float:
    """Plusieurs tests indépendants réunis en un seul (méthode de Stouffer) : la chance que le hasard seul donne ça."""
    normal = NormalDist()
    z = sum(normal.inv_cdf(1 - p) for p in ps) / math.sqrt(len(ps))
    return 1 - normal.cdf(z)


def day(ms: int) -> str:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").strftime("%d/%m/%Y")


def show(row: dict, net: float) -> None:
    pct = lambda x: f"{100 * x:+.0f} %"  # noqa: E731
    rule, hold, mix = row["rule"], row["hold"], row["shuffle"]
    print(f"\n{row['name']} · du {day(row['from'])} au {day(row['to'])} ({row['years']:.0f} ans)"
          + (" · ordre à la clôture du lendemain" if row["late"] else ""))
    print(f"  la règle  ×{rule['total']:<9.2f} ({100 * rule['yearly']:+.1f} % par an) pire baisse {pct(rule['worst'])} · "
          f"{row['orders_per_year']:.0f} ordres par an · investie {100 * row['inside']:.0f} % du temps")
    print(f"  garder    ×{hold['total']:<9.2f} ({100 * hold['yearly']:+.1f} % par an) pire baisse {pct(hold['worst'])}")
    print("  par décennie (règle / garder) : " + " · ".join(
        f"{d['decade']} ×{d['rule']:.2f} / ×{d['hold']:.2f}" for d in row["decades"]))
    verdict = "NET" if mix["p"] <= net else "pas net" if mix["p"] <= 0.05 else "non"
    print(f"  test du mélange : mieux que {100 * mix['beats']:.1f} % des {mix['n']} mélanges (sans tendance, la règle "
          f"finit à ×{mix['median']:.2f} en médiane ; vraie : ×{mix['real']:.2f}) → tendances exploitées : {verdict} ; "
          f"pire baisse plus petite que {100 * mix['worst_beats']:.0f} % des mélanges")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--melanges", type=int, default=1000)
    parser.add_argument("--coeurs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--cache", default=vrai.CACHE)
    parser.add_argument("--csv-dir", help="dossier de fichiers Date,Open,High,Low,Close à mesurer à part")
    parser.add_argument("--sortie")
    args = parser.parse_args()
    cache = Path(args.cache) / "marches"
    jobs = []
    for seed, (key, name, series, invert, always, group) in enumerate(MARKETS):
        ts, values = fred(series, cache)
        jobs.append((key, name, group, ts, 1 / values if invert else values, not always, args.melanges, 1000 + seed, None))
    feed = trend.Feed(lambda _id: vrai.exchange(), "binance", cache / "binance")
    for seed, (key, name, symbol, group) in enumerate(BINANCE):
        got = feed.get(symbol)
        if got.df is None:
            print(f"{name} : pas de bougies ({got.error})")
            continue
        closed = got.df.iloc[:-1] if got.live else got.df  # jamais la bougie du jour en cours
        jobs.append((key, name, group, closed["ts"].to_numpy(dtype="int64"), closed["close"].to_numpy(dtype=float),
                     False, args.melanges, 2000 + seed, closed))
    for seed, path in enumerate(sorted(Path(args.csv_dir).glob("*.csv")) if args.csv_dir else []):
        df = load_csv(path)
        jobs.append((path.stem, f"{path.stem} (fichier fourni)", INFO, df["ts"].to_numpy(dtype="int64"),
                     df["close"].to_numpy(dtype=float), True, args.melanges, 3000 + seed, df))
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=min(args.coeurs, len(jobs))) as pool:
        rows = list(pool.map(measure, jobs))
    net = 0.05 / JUDGED
    print(f"LA RÈGLE DU BOT DE TENDANCE SUR D'AUTRES MARCHÉS ({args.melanges} mélanges par marché, "
          f"{time.perf_counter() - started:.0f} s)")
    titles = {MAIN: "LES HUIT MARCHÉS INDÉPENDANTS (prix de la banque centrale américaine)",
              "crypto": "LES CRYPTOS DU BOT", CHECK: "RECOUPEMENT : LES MÊMES CRYPTOS SUR UNE AUTRE PLATEFORME",
              INFO: "POUR INFORMATION (trop court pour juger, ou fichier fourni)"}
    for group, title in titles.items():
        if any(r["group"] == group for r in rows):
            print(f"\n=== {title} ===")
        for row in rows:
            if row["group"] == group:
                show(row, net)
    main_rows = [r for r in rows if r["group"] == MAIN]
    frames = {key: frame(ts, close, late) for key, _name, group, ts, close, late, *_rest in jobs if group == MAIN}
    gate = trend.robustness_rows(frames)
    print("\n=== LA PORTE DU PROJET SUR LES HUIT MARCHÉS (chaque sortie, contre « garder ») ===")
    print(trend.robustness_report(gate).split("\n\n")[0])
    robust = [r.market for r in gate if r.verdict == ROBUST]
    print(f"Lignes « robustes » : {len(robust)} sur {len(gate)}" + (f" ({', '.join(robust)})" if robust else ""))
    exits = pooled(main_rows, "exits")
    witness = [pooled([{"w": r["witness"][k]} for r in main_rows], "w") for k in range(WITNESSES)]
    combined = stouffer([r["shuffle"]["p"] for r in main_rows])
    better = sum(r["rule"]["total"] > r["hold"]["total"] for r in main_rows)
    safer = sum(r["rule"]["worst"] > r["hold"]["worst"] for r in main_rows)
    print("\n=== L'ENSEMBLE DES HUIT MARCHÉS ===")
    print(f"La règle finit plus haut que « garder » sur {better} marchés sur {len(main_rows)} ; sa pire baisse est plus "
          f"petite sur {safer} sur {len(main_rows)}.")
    print(f"Tests du mélange réunis : la chance que le hasard seul donne ça = {100 * combined:.3f} % "
          f"(marchés nets à eux seuls : {sum(r['shuffle']['p'] <= net for r in main_rows)} sur {len(main_rows)}).")
    line = lambda title, m: (f"{title} : {m['n']} sorties sur {m['years']} années, {100 * m['wins']:.0f} % gagnantes, "  # noqa: E731
                             f"{100 * m['mean']:+.2f} % par sortie (de {100 * m['low']:+.2f} à {100 * m['high']:+.2f})")
    print(line("Toutes les sorties réunies, contre « garder »", exits))
    means = [w["mean"] for w in witness]
    held = sum(w["low"] <= EXIT_COST <= w["high"] for w in witness)
    print(f"Le témoin (marchés au hasard, sans tendance), refait {WITNESSES} fois : {100 * np.mean(means):+.2f} % par sortie en "
          f"moyenne (de {100 * min(means):+.2f} à {100 * max(means):+.2f}) ; attendu : les frais d'une sortie, "
          f"{100 * EXIT_COST:+.2f} % ; sa fourchette les contient {held} fois sur {WITNESSES}.")
    print("\n=== HORS PROTOCOLE : CE QUI MANGE L'AVANTAGE (ce que devient 1, pire baisse) ===")
    labels = (("protocole", "protocole"), ("sans_retard", "sans le jour de retard"),
              ("sans_retard_frais_bas", "sans retard, frais 0,03 %"), ("garder", "garder"))
    print(f"  {'':<10}" + "".join(f"{title:>28}" for _key, title in labels))
    for row in main_rows:
        print(f"  {row['key']:<10}" + "".join(
            f"{'×%.2f (%+.0f %%)' % (row['what_if'][k]['total'], 100 * row['what_if'][k]['worst']):>28}" for k, _t in labels))
    for k, title in labels[:3]:
        above = sum(r["what_if"][k]["total"] > r["what_if"]["garder"]["total"] for r in main_rows)
        print(f"  {title} : la règle finit plus haut que « garder » sur {above} marchés sur {len(main_rows)}")
    if args.sortie:
        report = {"markets": [{k: v for k, v in r.items() if k not in ("exits", "witness")} for r in rows],
                  "gate": [r.__dict__ for r in gate], "pooled": exits, "witness": witness, "stouffer": combined,
                  "exit_cost": EXIT_COST,
                  "better": better, "safer": safer, "net": net}
        Path(args.sortie).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\nDétail écrit dans {args.sortie}")


if __name__ == "__main__":
    main()
