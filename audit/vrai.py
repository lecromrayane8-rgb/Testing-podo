"""Audit : les mesures du labo sur de VRAIES bougies Binance (prix publics : aucune clé, aucun ordre, argent fictif).

Deux mesures, faites avec le vrai code des bots (swarm.retest_coin, le moteur fleet.Book, les mêmes frais) :

- `essai` : la mesure à l'essai rejouée sur les N derniers jours. L'univers est reconstitué comme le bot l'aurait vu
  (les cryptos USDT les plus agitées sur 24 h, au moins 5 M$ échangés, « en mouvement » au-dessus de 3 % d'amplitude),
  puis, pour chaque crypto, toutes les combinaisons tournent sur tout l'historique et seuls comptent les trades
  ouverts pendant qu'elle bougeait (swarm.Harvest). Chaque combinaison est mesurée sans et avec la sécurisation des
  gains. La fourchette compare les journées entre elles.
- `aujourdhui` : le test que le bot ferait maintenant sur chaque crypto suivie : combien de combinaisons peuvent
  devenir un bot, et ce que vaut leur test final (jamais regardé pour choisir), sans et avec la sécurisation. La
  fourchette compare les cryptos entre elles.

Limites, à garder en tête en lisant les chiffres :
- l'univers est reconstitué heure par heure (le bot le relit toutes les 10 minutes), avec les bougies d'une heure, et
  le volume en USDT est estimé (volume × clôture) ;
- seules les cryptos encore cotées aujourd'hui sont visibles (biais du survivant, petit sur deux semaines) ;
- une seule passe sur tout l'historique, au lieu d'un test toutes les 3 heures sur une fenêtre glissante : les trades
  sont presque les mêmes, pas exactement ;
- ce sont les bougies du marché au comptant, alors que le moteur simule des contrats à terme (levier, vente à
  découvert, financement fixe) : voir le point G5 de PLAN-BOTS.md ;
- le repère « aucun avantage » : environ −0,14 % par trade (le prix des frais).

Depuis une session cloud, seuls data-api.binance.vision (le miroir public officiel) et data.binance.vision répondent :
l'outil passe par le premier. Rien n'est écrit dans le dossier data/ du bot ; le cache des bougies est à part.

Lancer : python audit/vrai.py essai --jours 14 --cryptos 60 --sortie essai.json [--cache DOSSIER] [--coeurs 3]
         python audit/vrai.py aujourdhui --cryptos 60 --sortie aujourdhui.json
"""
import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradingbot.data import fetch_history, make_exchange, timeframe_to_ms  # noqa: E402
from tradingbot.fleet import technique, tf_label  # noqa: E402
from tradingbot.risk import clustered_bounds, paired_bounds  # noqa: E402
from tradingbot.scanner import liquid_markets, tradable  # noqa: E402
from tradingbot.strategy import PATTERN_FAMILIES  # noqa: E402
from tradingbot.swarm import (  # noqa: E402
    MIN_VOLUME, SAFE, TEST_DAYS, TIMEFRAMES, SwarmSettings, merge_record, new_record, retest_coin,
)

DAY, HOUR = 86_400_000, 3_600_000
MIRROR = "https://data-api.binance.vision/api/v3"  # le miroir public officiel de Binance (prix seulement)
CACHE = "/tmp/claude-0/-home-user-Testing-podo/8423a849-16af-51f1-8482-0d4c02d0f21f/scratchpad/vrai-cache"


def exchange():
    """Binance, prix publics seulement, par le miroir officiel ; le proxy et le certificat de l'environnement."""
    ex = make_exchange("binance")
    ex.urls["api"]["public"] = MIRROR
    ex.session.trust_env = True
    return ex


def candles(ex, symbol: str, tf: str, start_ms: int, end_ms: int, cache: Path) -> pd.DataFrame:
    """Les bougies terminées de [start_ms, end_ms], gardées sur le disque et complétées par ce qui manque."""
    tf_ms = timeframe_to_ms(tf)
    path = cache / f"{symbol.replace('/', '-')}-{tf}.pkl"
    df = pd.read_pickle(path) if path.exists() else None
    fresh = []
    if df is None or df.empty:
        fresh.append(fetch_history(ex, symbol, tf, start_ms, end_ms))
    else:
        first, last = int(df["ts"].iloc[0]), int(df["ts"].iloc[-1])
        if start_ms < first - tf_ms:
            fresh.append(fetch_history(ex, symbol, tf, start_ms, first))
        if end_ms > last + 2 * tf_ms:
            fresh.append(fetch_history(ex, symbol, tf, last + tf_ms, end_ms))
    if fresh:
        df = pd.concat(([df] if df is not None else []) + fresh)
        df = df[~df["ts"].duplicated(keep="last")].sort_values("ts")
        cache.mkdir(parents=True, exist_ok=True)
        df.to_pickle(path)
    return df[(df["ts"] >= start_ms) & (df["ts"] + tf_ms <= end_ms)]


def universe(ex, start_ms: int, end_ms: int, cache: Path, coins: int, min_move: float) -> dict[str, list]:
    """Les périodes pendant lesquelles chaque crypto « bougeait » pour le bot, entre start_ms et end_ms : parmi les
    `coins` paires USDT les plus agitées sur 24 h (au moins 5 M$ échangés), avec une amplitude d'au moins `min_move`."""
    symbols = sorted(s for s, m in ex.markets.items() if tradable(m, "USDT"))
    amplitude, volume = {}, {}
    for k, symbol in enumerate(symbols):
        try:
            df = candles(ex, symbol, "1h", start_ms - 26 * HOUR, end_ms, cache)
        except Exception as exc:  # une paire qui ne répond pas ne bloque pas les autres
            print(f"  {symbol} : bougies indisponibles ({exc})", flush=True)
            continue
        if len(df) < 25:
            continue
        ts = pd.Index(df["ts"] + HOUR)  # l'instant où la bougie se termine
        high = pd.Series(df["high"].to_numpy(), ts).rolling(24).max()
        low = pd.Series(df["low"].to_numpy(), ts).rolling(24).min()
        last = pd.Series(df["close"].to_numpy(), ts)
        amplitude[symbol] = (high - low) / last
        volume[symbol] = pd.Series((df["volume"] * df["close"]).to_numpy(), ts).rolling(24).sum()
        if k % 100 == 99:
            print(f"  univers : {k + 1}/{len(symbols)} paires lues", flush=True)
    amp, vol = pd.DataFrame(amplitude), pd.DataFrame(volume)
    amp = amp[(amp.index >= start_ms) & (amp.index <= end_ms)]
    vol = vol.reindex(amp.index)
    liquid = amp.where(vol >= MIN_VOLUME)
    rank = liquid.rank(axis=1, ascending=False, method="first")
    moving = (rank <= coins) & (liquid >= min_move)
    stretches: dict[str, list] = {}
    for symbol in moving.columns:
        on = moving[symbol].to_numpy()
        times = moving.index.to_numpy()
        current = None
        for t, flag in zip(times, on):
            if flag and current is None:
                current = int(t)
            elif not flag and current is not None:
                stretches.setdefault(symbol, []).append([current, int(t)])
                current = None
        if current is not None:
            stretches.setdefault(symbol, []).append([current, int(end_ms)])
    return stretches


def frames_for(ex, symbol: str, start_ms: int, end_ms: int, cache: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for tf in TIMEFRAMES:
        try:
            frames[tf] = candles(ex, symbol, tf, start_ms - TEST_DAYS[tf] * DAY, end_ms, cache)
        except Exception as exc:
            print(f"  {symbol} {tf} : historique indisponible ({exc})", flush=True)
    return frames


def _job(args):
    symbol, frames, settings, trial = args
    started = time.time()
    result = retest_coin(symbol, frames, settings, trial=trial)
    return {"symbol": symbol, "seconds": time.time() - started, "tested": result["tested"],
            "eligible": result["eligible"], "holdout": result["holdout"], "holdout_eligible": result["holdout_eligible"],
            "secure": result["secure"], "trial": result["trial"]}


def run_tests(jobs: list, workers: int) -> list[dict]:
    out = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for k, r in enumerate(pool.map(_job, jobs), 1):
            out.append(r)
            print(f"  {k}/{len(jobs)} {r['symbol']:<14} {r['seconds']:5.0f} s de calcul · {time.time() - started:5.0f} s "
                  "écoulées", flush=True)
    return out


# --- le rapport ------------------------------------------------------------------------------------------------------

def pct(x, digits=3) -> str:
    return "—" if x is None or not math.isfinite(x) else f"{100 * x:+.{digits}f} %".replace(".", ",")


def measure(rec: dict | None) -> dict:
    """Une ligne de la mesure : trades, gain moyen par trade, fourchette par journées, part de gagnants, jours."""
    days = (rec or {}).get("days") or {}
    n = sum(v[0] for v in days.values())
    if not n:
        return {"n": 0, "mean": None, "lo": None, "hi": None, "win": None, "days": 0}
    mean, lo, hi = clustered_bounds([(v[0], v[1]) for v in days.values()])
    return {"n": n, "mean": mean, "lo": lo if math.isfinite(lo) else None, "hi": hi if math.isfinite(hi) else None,
            "win": sum(v[2] for v in days.values()) / n, "days": len(days)}


def united(stats: dict, keys: list[str]) -> dict:
    """Plusieurs lignes réunies jour par jour (chaque trade n'est compté que dans une ligne de la famille)."""
    out = new_record()
    for key in keys:
        if key in stats:
            merge_record(out, stats[key])
    return out


def gap(stats: dict, keys: list[str]) -> dict:
    """« Avec » moins « sans », sur les mêmes journées."""
    plain, safe = united(stats, keys), united(stats, [SAFE + k for k in keys])
    days = sorted(set(plain["days"]) | set(safe["days"]))
    groups = [((safe["days"].get(d) or [0, 0.0, 0])[0], (safe["days"].get(d) or [0, 0.0, 0])[1],
               (plain["days"].get(d) or [0, 0.0, 0])[0], (plain["days"].get(d) or [0, 0.0, 0])[1]) for d in days]
    diff, lo, hi = paired_bounds(groups)
    clean = lambda x: x if math.isfinite(x) else None  # noqa: E731
    return {"sans": measure(plain), "avec": measure(safe), "diff": clean(diff), "lo": clean(lo), "hi": clean(hi),
            "days": len(days)}


def show(title: str, m: dict) -> str:
    span = f"[{pct(m['lo'])} ; {pct(m['hi'])}]" if m["lo"] is not None else "(pas de fourchette)"
    wins = "" if m["win"] is None else f"{100 * m['win']:.0f} % gagnants"
    return f"  {title:<34} {m['n']:>8} trades  {pct(m['mean'])} {span:<28} {wins}  {m['days']} j"


def show_gap(title: str, g: dict) -> str:
    span = f"[{pct(g['lo'])} ; {pct(g['hi'])}]" if g["lo"] is not None else "(pas de fourchette)"
    verdict = ("pas encore mesuré" if g["diff"] is None else "pas assez de recul" if g["lo"] is None else
               "mieux avec" if g["lo"] > 0 else "moins bien avec" if g["hi"] < 0 else "pas de différence nette")
    return (f"  {title:<34} sans {pct(g['sans']['mean'])} ({g['sans']['n']})  avec {pct(g['avec']['mean'])} "
            f"({g['avec']['n']})  écart {pct(g['diff'])} {span} : {verdict}")


def trial_report(stats: dict, live: str) -> dict:
    prefix = SAFE if live == "avec" else ""
    units = [f"unite:{tf}" for tf in TIMEFRAMES]
    family = lambda name: sorted({k[len(SAFE):] if k.startswith(SAFE) else k for k in stats  # noqa: E731
                                  if k.startswith((name, SAFE + name))})
    report = {"variant": live, "total": gap(stats, units),
              "units": {tf: gap(stats, [f"unite:{tf}"]) for tf in TIMEFRAMES},
              "exits": {k.partition(":")[2]: gap(stats, [k]) for k in family("sortie:")},
              "sides": {k.partition(":")[2]: gap(stats, [k]) for k in family("sens:")}}
    rows = []
    for key in family("strategie:"):
        m = measure(stats.get(prefix + key))
        if m["n"]:
            rows.append({"key": key.partition(":")[2], **m})
    alpha = 0.025 / max(len(rows), 1)
    for r in rows:
        days = stats[prefix + "strategie:" + r["key"]]["days"]
        hard = clustered_bounds([(v[0], v[1]) for v in days.values()], alpha)[1]
        r["proven"] = bool(r["days"] >= 7 and r["n"] >= 30 and math.isfinite(hard) and hard > 0)
        r["failed"] = bool(r["days"] >= 7 and r["n"] >= 30 and r["hi"] is not None and r["hi"] < 0)
    report["strategies"] = sorted(rows, key=lambda r: -r["mean"])
    names = []  # chaque technique, toutes unités réunies : ce qui ressort, et ce que valent les lectures du graphique
    for key in family("technique:"):
        m = measure(stats.get(prefix + key))
        if m["n"]:
            name = key.partition(":")[2]
            names.append({"key": name, "reading": technique(name).strategy_type in PATTERN_FAMILIES, **m})
    report["techniques"] = sorted(names, key=lambda r: -r["mean"])
    report["readings"] = gap(stats, [f"technique:{r['key']}" for r in names if r["reading"]])
    report["others"] = gap(stats, [f"technique:{r['key']}" for r in names if not r["reading"]])
    return report


def print_trial(report: dict) -> None:
    live = report["variant"]
    print(f"\nLA MESURE À L'ESSAI SUR DE VRAIES BOUGIES (variante des bots : {live} sécurisation)")
    print("Repère « aucun avantage » : environ −0,14 % par trade (le prix des frais).")
    print(show("Toutes les combinaisons", report["total"][live]))
    print("Par unité de temps :")
    for tf, g in report["units"].items():
        print(show(tf_label(tf), g[live]))
    print("Par façon de sortir :")
    for name, g in report["exits"].items():
        print(show(name, g[live]))
    print("Par sens :")
    for name, g in report["sides"].items():
        print(show({"long": "achat", "short": "vente à découvert"}.get(name, name), g[live]))
    print("\nSÉCURISATION DES GAINS : AVEC OU SANS (mêmes combinaisons, mêmes journées)")
    print(show_gap("Toutes les combinaisons", report["total"]))
    for tf, g in report["units"].items():
        print(show_gap(tf_label(tf), g))
    for name, g in report["exits"].items():
        print(show_gap(name, g))
    rows = [r for r in report["strategies"] if r["n"] >= 200]
    print(f"\nSTRATÉGIES (une technique dans une unité de temps) : {len(report['strategies'])} mesurées, "
          f"{len(rows)} avec au moins 200 trades")
    print(f"  fourchette entièrement positive : {sum(1 for r in rows if r['lo'] is not None and r['lo'] > 0)} · "
          f"entièrement négative : {sum(1 for r in rows if r['hi'] is not None and r['hi'] < 0)} · "
          f"« prouvées » (seuil durci) : {sum(r['proven'] for r in report['strategies'])} · "
          f"« recalées » : {sum(r['failed'] for r in report['strategies'])}")
    for title, part in (("Les 10 meilleures", rows[:10]), ("Les 10 pires", rows[-10:])):
        print(title + " :")
        for r in part:
            print(show(r["key"].replace("|", " · "), r))
    if report.get("techniques"):
        print(f"\nPAR TECHNIQUE, toutes unités réunies ({len(report['techniques'])}, de la meilleure à la pire ; "
              "* = lecture du graphique)")
        for r in report["techniques"]:
            print(show(("* " if r["reading"] else "  ") + r["key"], r))
        if report["readings"][live]["n"]:
            print(show("Les lectures du graphique réunies", report["readings"][live]))
            print(show("Les autres techniques réunies", report["others"][live]))


def final_report(results: list[dict]) -> dict:
    """Le test final réuni sur les cryptos, sans et avec, la fourchette comparant les cryptos entre elles."""
    out = {}
    for scope in ("eligible", "all"):
        groups = [(r["secure"][scope]["avec"]["n"], r["secure"][scope]["avec"]["total"],
                   r["secure"][scope]["sans"]["n"], r["secure"][scope]["sans"]["total"]) for r in results]
        diff, lo, hi = paired_bounds(groups)
        side = {}
        for variant in ("sans", "avec"):
            n = sum(r["secure"][scope][variant]["n"] for r in results)
            total = sum(r["secure"][scope][variant]["total"] for r in results)
            wins = sum(r["secure"][scope][variant]["wins"] for r in results)
            mean, low, high = clustered_bounds([(r["secure"][scope][variant]["n"], r["secure"][scope][variant]["total"])
                                                for r in results])
            side[variant] = {"n": n, "mean": total / n if n else None, "win": wins / n if n else None,
                             "lo": low if math.isfinite(low) else None, "hi": high if math.isfinite(high) else None,
                             "days": len(results)}
        clean = lambda x: x if math.isfinite(x) else None  # noqa: E731
        out[scope] = {**side, "diff": clean(diff), "lo": clean(lo), "hi": clean(hi), "days": len(results)}
    return out


def print_final(final: dict, results: list[dict], live: str) -> None:
    print("\nLE TEST FINAL (les derniers 20 % de l'historique, jamais regardés pour choisir), cryptos réunies")
    print(f"  combinaisons testées par crypto : {np.mean([r['tested'] for r in results]):.0f} · peuvent devenir un bot : "
          f"{np.mean([r['eligible'] for r in results]):.0f} ({np.mean([r['eligible'] / max(r['tested'], 1) for r in results]):.1%})")
    choices = [(r["holdout"]["n"], r["holdout"]["total"]) for r in results]
    n = sum(c[0] for c in choices)
    mean, lo, hi = clustered_bounds(choices)
    print(show("Les choix du labo (variante des bots)", {"n": n, "mean": mean if n else None,
                                                        "lo": lo if n and math.isfinite(lo) else None,
                                                        "hi": hi if n and math.isfinite(hi) else None,
                                                        "win": (sum(r["holdout"]["wins"] for r in results) / n) if n else None,
                                                        "days": len(results)}).replace(" j", " cryptos"))
    for scope, title in (("eligible", "Celles qui peuvent devenir un bot"), ("all", "Toutes les combinaisons")):
        print(show(title + f" ({live})", final[scope][live]).replace(" j", " cryptos"))
        print(show_gap("  avec ou sans sécurisation", final[scope]))


# --- les deux mesures ------------------------------------------------------------------------------------------------

def essai(args) -> None:
    cache = Path(args.cache)
    ex = exchange()
    ex.load_markets()
    end = (args.fin or ex.fetch_time()) // HOUR * HOUR  # --fin : rejouer exactement une période déjà mesurée
    start = end - args.jours * DAY
    settings = SwarmSettings(coins=args.cryptos)
    print(f"Univers reconstitué du {pd.to_datetime(start, unit='ms')} au {pd.to_datetime(end, unit='ms')} (UTC)", flush=True)
    stretches = universe(ex, start, end, cache, settings.coins, settings.min_move)
    active = sorted(stretches, key=lambda s: -sum(b - a for a, b in stretches[s]))
    if args.max_symboles:
        active = active[:args.max_symboles]
    hours = {s: sum(b - a for a, b in stretches[s]) / HOUR for s in active}
    print(f"{len(stretches)} cryptos ont bougé pendant la période ; {len(active)} mesurées "
          f"(en mouvement {np.mean(list(hours.values())):.0f} h en moyenne sur {args.jours * 24} h)", flush=True)
    jobs = []
    for k, symbol in enumerate(active, 1):
        frames = frames_for(ex, symbol, start, end, cache)
        jobs.append((symbol, frames, asdict(settings), {"done": {}, "active": stretches[symbol], "final": True}))
        if k % 10 == 0:
            print(f"  bougies : {k}/{len(active)} cryptos", flush=True)
    if args.telecharger:
        print("Bougies en cache ; calcul non lancé (--telecharger).")
        return
    results = run_tests(jobs, args.coeurs)
    stats: dict[str, dict] = {}
    for r in results:
        for key, rec in ((r["trial"] or {}).get("stats") or {}).items():
            merge_record(stats.setdefault(key, new_record("days" in rec)), rec)
    report = trial_report(stats, settings.variant)
    final = final_report(results)
    print_trial(report)
    print_final(final, results, settings.variant)
    payload = {"kind": "essai", "start": start, "end": end, "days": args.jours, "settings": asdict(settings),
               "symbols": {s: {"hours": hours[s], "stretches": stretches[s]} for s in active},
               "trial": report, "final": final,
               "coins": [{k: r[k] for k in ("symbol", "seconds", "tested", "eligible", "holdout", "secure")} for r in results]}
    if args.sortie:
        Path(args.sortie).write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\nDétail écrit dans {args.sortie}")


def aujourdhui(args) -> None:
    cache = Path(args.cache)
    ex = exchange()
    ex.load_markets()
    end = ex.fetch_time() // 60_000 * 60_000
    settings = SwarmSettings(coins=args.cryptos)
    liquid = liquid_markets(ex, "USDT", MIN_VOLUME)[:settings.coins]
    moving = [r for r in liquid if r.amplitude >= settings.min_move]
    print(f"{len(liquid)} cryptos suivies maintenant, dont {len(moving)} assez agitées "
          f"(amplitude médiane {np.median([r.amplitude for r in liquid]):.1%})", flush=True)
    symbols = [r.symbol for r in moving][:args.max_symboles or None]
    jobs = [(s, frames_for(ex, s, end, end, cache), asdict(settings), None) for s in symbols]
    if args.telecharger:
        print("Bougies en cache ; calcul non lancé (--telecharger).")
        return
    results = run_tests(jobs, args.coeurs)
    final = final_report(results)
    print_final(final, results, settings.variant)
    if args.sortie:
        payload = {"kind": "aujourdhui", "end": end, "settings": asdict(settings), "final": final,
                   "coins": [{k: r[k] for k in ("symbol", "seconds", "tested", "eligible", "holdout", "holdout_eligible",
                                                "secure")} for r in results]}
        Path(args.sortie).write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\nDétail écrit dans {args.sortie}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Les mesures du labo sur de vraies bougies Binance (prix publics).")
    sub = parser.add_subparsers(dest="mesure", required=True)
    for name in ("essai", "aujourdhui"):
        p = sub.add_parser(name)
        p.add_argument("--cryptos", type=int, default=60, help="cryptos suivies, comme FLOTTE_CRYPTOS")
        p.add_argument("--cache", default=CACHE, help="dossier des bougies déjà téléchargées (hors du dépôt)")
        p.add_argument("--sortie", default="", help="fichier JSON du détail")
        p.add_argument("--coeurs", type=int, default=3)
        p.add_argument("--max-symboles", type=int, default=0, help="pour un essai rapide : les K premières cryptos")
        p.add_argument("--telecharger", action="store_true", help="remplir le cache sans lancer le calcul")
        if name == "essai":
            p.add_argument("--jours", type=int, default=14, help="jours rejoués")
            p.add_argument("--fin", type=int, default=0, help="fin de la période, en millisecondes (défaut : maintenant)")
    args = parser.parse_args()
    (essai if args.mesure == "essai" else aujourdhui)(args)


if __name__ == "__main__":
    main()
