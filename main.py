"""Point d'entrée : python main.py {site,trader,backtest,robustesse,labo,labo-portefeuille,tournoi,portefeuille,prix,telegram,check,run,tableau,reset-guard} --help

Sans argument (double-clic sur la version Windows), le site du bot s'ouvre dans le navigateur.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import multiprocessing
import os
import sys
import time
import webbrowser
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd

from tradingbot.awake import keep_awake
from tradingbot.backtest import format_comparison, format_report, run_backtest
from tradingbot.broker import CcxtBroker, PaperBroker, atomic_write
from tradingbot.config import ConfigError, Settings, load_dotenv
from tradingbot.dashboard import ROBUSTNESS_FILE, write_dashboard
from tradingbot.execution import FUTURES, ExecutionParams
from tradingbot.data import load_csv, load_or_fetch, make_exchange, ohlcv_to_frame, timeframe_to_ms
from tradingbot.lab import (
    ALL_VARIANTS, LAB_FILE, PROMISING, SHORT_TERM_VARIANTS, VARIANTS, env_lines, format_lab, load_lab,
    overall_lab_verdict, run_lab, save_lab,
)
from tradingbot.live import Bot, StateStore, bot_paths, px, run_bots, slug
from tradingbot.obsidian import JOURNAL, ObsidianHandler, ObsidianJournal
from tradingbot.robustness import evaluate, format_robustness, overall_verdict, research_risk, save_results
from tradingbot.notify import ALERT, attach as attach_telegram, call as telegram_call, latest_chat_id
from tradingbot.prices import DEFAULT_CRYPTOS, DEFAULT_PLATFORMS, connect, format_board, label, new_listings, snapshot
from tradingbot.portfolio import (
    MIN_COINS, PORTFOLIO_DIR, PORTFOLIO_LAB_FILE, PORTFOLIO_VARIANTS, RETAINED as PORTFOLIO_RETAINED, PaperPortfolio, align,
    evaluate as evaluate_portfolio, format_rows as format_portfolio, load as load_portfolio_lab,
    overall_verdict as portfolio_verdict, save as save_portfolio_lab,
)
from tradingbot.scanner import ScanResult, by_volume, pick_markets, scan_volatile, tradable
from tradingbot.trader import (
    ACCOUNT_FILE as TRADER_ACCOUNT, REPLAY_DAYS, REPLAY_FILE, TRADER_DIR, Account as TraderAccount,
    choose_playbook, replay as replay_trader, run as run_trader, settings_from_env as trader_settings,
    summary as trader_summary,
)
from tradingbot.webapp import PORT, serve

log = logging.getLogger("tradingbot")

DAY_MS = 86_400_000
LONG_TERM_DAYS = 2500  # bougies d'un jour : ~7 ans d'historique pour avoir assez de trades
LAB_SYMBOLS = "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,PAXG/USDT,EUR/USDT"  # PAXG = or, EUR = euro/dollar


TOURNAMENT_DIR = "tournoi"
WATCH = "à surveiller"
SUMMARY_SECONDS = 300  # résumé du tournoi dans la console toutes les 5 minutes
PHONE_SUMMARY_SECONDS = 3600  # et sur le téléphone (Telegram) toutes les heures


class NothingRetained(ValueError):
    """Le labo n'a retenu aucune stratégie : rien à faire tourner. C'est une réponse, pas une panne."""


def history_days(timeframe: str, days: int) -> int:
    """Jours d'historique : ~7 ans en bougies d'un jour, et environ 86 000 bougies au plus sous 15 min
    (60 jours en 1 min, 300 en 5 min) pour que le labo reste rapide."""
    tf_ms = timeframe_to_ms(timeframe)
    if tf_ms >= DAY_MS:
        return max(days, LONG_TERM_DAYS)
    if tf_ms < 15 * 60_000:
        return min(days, int(60 * tf_ms / 60_000))
    return days


def setup_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(data_dir / "bot.log", encoding="utf-8")],
    )


def make_broker(s: Settings, data: CcxtBroker | None = None):
    if s.mode == "paper":
        data = data or CcxtBroker(s.exchange, s.symbol)
        # Un compte fictif par bot : deux bots sur la même paire ne se partagent jamais leurs fonds.
        pair = s.symbol.replace("/", "-")
        suffix = f"_{slug(s.bot_label)}" if s.bot_label else ""
        wallet = s.data_dir / f"paper_wallet_{s.exchange}_{pair}_{s.timeframe}{suffix}.json"
        legacy = s.data_dir / f"paper_wallet_{s.exchange}_{pair}.json"  # nom des versions précédentes
        if legacy.exists() and not wallet.exists() and not s.bot_label and s.timeframe == s.markets[0][1]:
            legacy.rename(wallet)
        return PaperBroker(data, wallet, s.paper_start_balance, s.execution)
    venue = {"testnet": "testnet", "demo": "demo", "live": "real"}[s.mode]
    return CcxtBroker(s.exchange, s.symbol, s.api_key, s.api_secret, s.api_password, venue=venue)


def make_notes(s: Settings) -> ObsidianJournal | None:
    return ObsidianJournal(s.obsidian_vault) if s.obsidian_vault else None


def refresh_dashboard(s: Settings) -> None:
    """Après une étude : un échec d'écriture (bot qui écrit au même moment...) ne doit pas masquer les résultats."""
    try:
        print(f"\nTableau de bord mis à jour : {write_dashboard(s)}")
    except Exception as exc:
        log.warning("Tableau de bord non mis à jour (relance « 5 - Tableau de bord ») : %s", exc)


def bot_settings(s: Settings) -> list[Settings]:
    return s.per_bot()


def cmd_backtest(s: Settings, args: argparse.Namespace) -> None:
    if args.csv:
        df = load_csv(Path(args.csv))
    else:
        df = load_or_fetch(s.exchange, s.symbol, s.timeframe, args.days, s.data_dir / "cache")
    results = {
        order_type: run_backtest(df, s.strategy, s.risk, args.capital, replace(s.execution, order_type=order_type))
        for order_type in ("market", "limit")
    }
    result = results[s.execution.order_type]
    print(f"\n=== Backtest {s.symbol} {s.timeframe} sur {s.exchange} ===")
    print(format_report(result.metrics))
    print(
        f"\nComparaison (frais taker {100 * s.execution.fee_rate:.3f} %, "
        f"maker {100 * s.execution.maker_fee_rate:.3f} %) :"
    )
    print(format_comparison(results))
    out = s.data_dir / "backtest_trades.csv"
    result.trades_frame().to_csv(out, index=False)
    result.equity.to_csv(s.data_dir / "backtest_equity.csv")
    print(f"\nDétail des trades : {out}")
    if notes := make_notes(s):
        note = notes.backtest(s, result.metrics, format_report(result.metrics), format_comparison(results))
        print(f"Note Obsidian : {note}")


def cmd_robustness(s: Settings, args: argparse.Namespace) -> None:
    symbols = [x.strip() for x in args.symbols.split(",") if x.strip()]
    timeframes = [x.strip() for x in args.timeframes.split(",") if x.strip()]
    markets = [(symbol, tf) for symbol in symbols for tf in timeframes]
    exchange = make_exchange(s.exchange)
    rows = []
    for symbol, tf in markets:
        try:
            df = load_or_fetch(s.exchange, symbol, tf, history_days(tf, args.days), s.data_dir / "cache", exchange)
        except ccxt.BadSymbol:
            log.warning("%s introuvable sur %s : ignoré", symbol, s.exchange)
            continue
        except ccxt.NetworkError as exc:
            log.warning("%s %s ignoré (réseau) : %s", symbol, tf, exc)
            continue
        result = run_backtest(df, s.strategy, research_risk(s.risk), 10_000.0, s.execution)
        rows.append(evaluate(f"{symbol} {tf}", result, n_tests=len(markets), n_periods=args.periods))
    table = format_robustness(rows, args.periods)
    verdict = overall_verdict(rows)
    print(f"\n=== Robustesse sur {s.exchange}, {args.days} jours, ordres {s.execution.order_type} ===")
    if any(timeframe_to_ms(tf) >= DAY_MS for tf in timeframes):
        print(f"(bougies d'un jour : historique étendu à {max(args.days, LONG_TERM_DAYS)} jours pour avoir assez de trades)")
    print(table)
    print()
    print(verdict)
    save_results(
        s.data_dir / ROBUSTNESS_FILE, rows, verdict,
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"), jours=args.days, ordres=s.execution.order_type,
    )
    refresh_dashboard(s)
    if notes := make_notes(s):
        print(f"Note Obsidian : {notes.robustness(s, rows, table, verdict, args.days)}")


def cmd_lab(s: Settings, args: argparse.Namespace) -> None:
    keep_awake()  # un labo dure parfois une heure : l'ordinateur ne doit pas s'endormir en route
    attach_telegram(s, journal=False)  # le verdict part sur le téléphone, si les alertes sont réglées
    symbols = [x.strip().upper() for x in args.symbols.split(",") if x.strip()]
    timeframes = [x.strip() for x in args.timeframes.split(",") if x.strip()]
    exchange = make_exchange(s.exchange)
    if args.scanner or args.memecoins:
        extra = pick_markets(exchange, top=args.scanner, memecoins=args.memecoins)
        symbols += [r.symbol for r in extra if r.symbol not in symbols]
    datasets: dict[str, dict] = {}
    for tf in timeframes:
        for symbol in symbols:
            try:
                df = load_or_fetch(s.exchange, symbol, tf, history_days(tf, args.days), s.data_dir / "cache", exchange)
            except (ccxt.BadSymbol, ccxt.NetworkError) as exc:
                log.warning("%s %s ignoré : %s", symbol, tf, exc)
                continue
            datasets.setdefault(tf, {})[symbol] = df
    if args.csv_dir:
        for path in sorted(Path(args.csv_dir).glob("*.csv")):
            try:
                datasets.setdefault("1d", {})[path.stem] = load_csv(path)  # exports quotidiens (actions, ETF...)
            except ValueError as exc:
                log.warning("%s ignoré : %s", path.name, exc)
    if not datasets:
        raise ValueError("Aucune donnée récupérée : vérifie ta connexion internet.")
    markets = sorted({m for group in datasets.values() for m in group})
    variants = SHORT_TERM_VARIANTS if args.combinaisons else VARIANTS
    # Ordres limites : on attend son prix au lieu de payer l'écart et le glissement (frais maker du .env).
    # Futures : les frais plus bas des contrats à terme, financement compris (argent fictif seulement).
    execution = FUTURES if args.futures else s.execution
    execution = replace(execution, order_type="limit") if args.ordres_limites else execution
    log.info("Laboratoire : %d variantes × %d unités de temps sur %d marchés, %s", len(variants), len(datasets),
             len(markets), describe_execution(execution))
    rows = run_lab(datasets, execution, s.risk, variants, workers=args.coeurs)
    table, verdict = format_lab(rows), overall_lab_verdict(rows)
    print(f"\n=== Laboratoire de stratégies : {', '.join(markets)} ===")
    print(table)
    print()
    print(verdict)
    best = next((r for r in rows if r.verdict == PROMISING), None)
    if best:
        tradable = [m for m in datasets.get(best.timeframe, {}) if "/" in m]
        print("\nPour l'essayer en argent fictif, mets ces lignes dans .env (« Modifier les reglages ») :")
        print(env_lines(ALL_VARIANTS[best.variant]))
        print(f"BOTS={','.join(f'{m}@{best.timeframe}' for m in tradable)}")
    save_lab(
        s.data_dir / Path(args.resultats).name, rows, verdict,
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"), jours=args.days, marches=markets,
        execution=asdict(execution),  # le tournoi reprendra exactement ces ordres et ces frais
    )
    refresh_dashboard(s)
    if notes := make_notes(s):
        print(f"Note Obsidian : {notes.lab(s, rows, table, verdict, args.days)}")
    log.info("Labo terminé (%s, %s) :\n%s", ", ".join(datasets), describe_execution(execution), verdict, extra=ALERT)


def describe_execution(ex: ExecutionParams) -> str:
    funding = f", financement {100 * ex.funding_rate_8h:.3f} % par 8 h" if ex.funding_rate_8h else ""
    if ex.order_type == "limit":
        return f"ordres limites (frais maker {100 * ex.maker_fee_rate:.3f} %{funding})"
    return f"ordres au marché (frais {100 * ex.fee_rate:.3f} %, glissement {100 * ex.slippage:.3f} %{funding})"


def cmd_check(s: Settings, args: argparse.Namespace) -> None:
    s.validate_for_trading()
    for bs in bot_settings(s):
        broker = make_broker(bs)
        balances = broker.balances()
        price = broker.last_price()
        candles = broker.fetch_candles(bs.timeframe, 5)
        base, quote = bs.symbol.split("/")
        print(f"\n[{bs.symbol} {bs.timeframe}] connexion OK : mode={bs.mode} plateforme={bs.exchange}")
        print(f"Prix {bs.symbol} : {px(price)}")
        print(f"Soldes disponibles : {balances.base:.8f} {base} | {balances.quote:.2f} {quote}")
        print(f"Dernière bougie {bs.timeframe} : {candles.index[-1]}")
        print_fees(bs, broker.trading_fees())


def print_fees(s: Settings, fees: tuple[float, float] | None) -> None:
    if fees is None:
        print("Frais du compte : non fournis par la plateforme (vérifie-les sur son site)")
        return
    maker, taker = fees
    print(f"Frais {'simulés' if s.mode == 'paper' else 'du compte'} : maker {100 * maker:.3f} % | taker {100 * taker:.3f} %")
    if maker >= taker:
        print("  -> Ici un ordre limite ne coûte pas moins cher en frais : il évite seulement l'écart et le glissement.")
    else:
        print(f"  -> Un ordre limite économise {100 * (taker - maker):.3f} % par ordre exécuté.")
    if s.mode != "paper" and (abs(maker - s.execution.maker_fee_rate) > 1e-9 or abs(taker - s.execution.fee_rate) > 1e-9):
        print(f"  -> Mets MAKER_FEE_RATE={maker} et FEE_RATE={taker} dans .env pour des backtests réalistes.")


def check_capital_allocation(bots: list[Bot]) -> None:
    """Sur un vrai compte, les bots qui démarrent doivent tous pouvoir recevoir leur MAX_CAPITAL."""
    starting = [b for b in bots if b.state.get("capital") is None]
    if bots[0].s.mode == "paper" or len(bots) < 2 or not starting:
        return
    quote = bots[0].broker.balances().quote
    needed = len(starting) * bots[0].s.max_capital
    if quote < needed:
        raise ConfigError(
            f"{len(starting)} bots à {bots[0].s.max_capital:.2f} chacun demandent {needed:.2f}, "
            f"mais le compte n'a que {quote:.2f} disponibles. Baisse MAX_CAPITAL ou le nombre de bots."
        )


def cmd_run(s: Settings, args: argparse.Namespace) -> None:
    s.validate_for_trading()
    keep_awake()  # un ordinateur en veille ne surveille plus les stops
    if s.mode == "live":
        log.warning("MODE LIVE : les bots vont passer de vrais ordres, capital max %.2f chacun", s.max_capital)
    notes = make_notes(s)
    if notes:
        logging.getLogger("tradingbot").addHandler(ObsidianHandler(notes))
    if attach_telegram(s):
        log.info("Alertes Telegram actives : achats, ventes et alertes partent sur ton téléphone")
    bots = []
    for bs in bot_settings(s):
        state_path, journal_path = bot_paths(bs)
        bots.append(Bot(make_broker(bs), bs, StateStore(state_path), journal_path, notes))
    check_capital_allocation(bots)
    try:
        log.info("Tableau de bord : %s (se met à jour tout seul pendant que les bots tournent)", write_dashboard(s))
    except Exception as exc:  # le tableau de bord ne doit jamais empêcher de trader
        log.warning("Tableau de bord non écrit : %s", exc)
    run_bots(bots, s.poll_seconds, after_cycle=lambda: write_dashboard(s))


def tournament_picks(lab: dict, unite: str | None, limit: int) -> list[tuple[str, str, dict]]:
    """(variante, unité, ligne du labo) des stratégies « prometteur » ou « à surveiller », les meilleures d'abord."""
    picks, seen = [], set()
    for row in lab.get("rows", []):  # le labo les trie déjà de la meilleure espérance à la moins bonne
        if row.get("verdict") not in (PROMISING, WATCH) or row.get("variant") not in ALL_VARIANTS:
            continue
        key = (row["variant"], unite or row["timeframe"])
        if key not in seen:
            seen.add(key)
            picks.append((*key, row))
    return picks[:limit]


def merge_picks(labs: list[tuple[str, dict]], unite: str | None, limit: int,
                default: ExecutionParams) -> list[tuple[str, str, dict, ExecutionParams]]:
    """Les meilleures stratégies retenues par un ou plusieurs labos, chacune avec les ordres de son labo."""
    candidates = []
    for name, lab in labs:
        try:
            execution = ExecutionParams(**lab["execution"]) if lab.get("execution") else default
        except (TypeError, ValueError) as exc:
            log.warning("Ordres du labo %s illisibles, réglages du .env utilisés : %s", name, exc)
            execution = default
        for variant, tf, row in tournament_picks(lab, unite, len(lab.get("rows", []))):
            candidates.append((variant, tf, row, execution))
    best = sorted(candidates, key=lambda c: -(num_or(c[2].get("expectancy_pct"), -math.inf)))
    picks, seen = [], set()
    for variant, tf, row, execution in best:  # une stratégie retenue par deux labos : la meilleure version
        if (variant, tf) not in seen:
            seen.add((variant, tf))
            picks.append((variant, tf, row, execution))
    return picks[:limit]


def num_or(value, default: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def tournament_summary(bots: list[Bot]) -> str:
    """Une ligne pour la console : le détail de chaque bougie reste dans le tableau de bord."""
    states = [b.state for b in bots]
    realized = sum(st["capital"] - (st.get("initial_capital") or st["capital"]) for st in states if st.get("capital"))
    quotes = {b.s.symbol.split("/")[-1] for b in bots}
    unit = f" {quotes.pop()}" if len(quotes) == 1 else ""
    return (
        f"Tournoi : {len(bots)} bots, {sum(1 for st in states if st.get('position'))} en position, "
        f"{sum((st.get('perf') or {}).get('n', 0) for st in states)} trades clôturés, "
        f"résultat réalisé {realized:+.2f}{unit}, {sum(1 for st in states if st.get('eliminated'))} éliminé(s)"
    )


def tournament_dir(lab_file: str) -> str:
    """Un dossier par labo : « laboratoire.json » -> tournoi, « laboratoire-court-terme.json » -> tournoi-court-terme."""
    stem = Path(lab_file).stem
    suffix = stem.removeprefix("laboratoire").strip("-_")
    return f"{TOURNAMENT_DIR}-{slug(suffix)}" if suffix else TOURNAMENT_DIR


def is_short_term(timeframe: str) -> bool:
    try:
        return timeframe_to_ms(timeframe) < 15 * 60_000
    except (ValueError, ccxt.BaseError):
        return False


def unmarked(symbol: str) -> ScanResult:
    return ScanResult(symbol, math.nan, math.nan, math.nan)


def cmd_tournament(s: Settings, args: argparse.Namespace) -> None:
    lab_files = [Path(x.strip()).name for x in args.labo.split(",") if x.strip()]
    labs = [(name, lab) for name in lab_files if (lab := load_lab(s.data_dir / name)) and lab.get("rows")]
    if not labs:
        raise ValueError(
            f"Aucun résultat de labo dans data/ ({', '.join(lab_files)}). Lance d'abord le laboratoire correspondant "
            "(« 6 - Laboratoire de strategies » ou « 7 - Labo court terme ») : le tournoi reprend ses stratégies "
            "« à surveiller »."
        )
    lab_file, lab = labs[0]  # le premier labo donne le dossier du tournoi et ses marchés
    if args.unite:
        try:  # unité invalide : erreur claire avant de démarrer
            timeframe_to_ms(args.unite)
        except (ValueError, ccxt.BaseError):
            raise ValueError(f"Unité de temps inconnue : {args.unite!r} (exemples : 1m, 5m, 1h, 4h, 1d)") from None
    picks = merge_picks(labs, args.unite, args.strategies, s.execution)
    if not picks:
        timeframes = {r.get("timeframe", "?") for _, one in labs for r in one["rows"]}
        hint = (" Pour le long terme, relance d'abord « 6 - Laboratoire de strategies »."
                if all(is_short_term(tf) for tf in timeframes) else "")
        raise NothingRetained(
            f"Le labo ({', '.join(sorted(timeframes))}) n'a retenu aucune stratégie « à surveiller » ou « prometteur » : "
            "rien à mettre en compétition. C'est le signe qu'aucune ne gagne après frais sur ces marchés et à ces "
            f"unités de temps.{hint}"
        )
    exchange = make_exchange(s.exchange)
    if args.symbols:
        markets = [unmarked(x.strip().upper()) for x in args.symbols.split(",") if x.strip()]
    else:
        markets = pick_markets(exchange, top=args.top, memecoins=not args.sans_memecoins)
    if args.avec_marches_du_labo:  # là où le labo a trouvé ses stratégies, en plus des autres
        known = {m.symbol for m in markets}
        markets = [unmarked(m) for m in lab.get("marches", []) if "/" in m and m not in known] + markets
    # Toujours en argent fictif, chaque bot avec son propre compte de `--capital` (MAX_CAPITAL vise le vrai compte).
    base = replace(s, mode="paper", data_dir=s.data_dir / tournament_dir(lab_file), paper_start_balance=args.capital,
                   max_capital=args.capital, bots=())
    executions = {describe_execution(ex) for *_, ex in picks}
    # Pas de notes Obsidian : des dizaines de bots en 1 minute y écriraient des milliers de notes par jour.
    data, chosen = {}, []
    for m in markets:
        try:  # une connexion et un cache par crypto, partagés par toutes les stratégies
            data[m.symbol] = CcxtBroker(s.exchange, m.symbol, exchange=exchange, cache_seconds=5)
            chosen.append(m)
        except ValueError as exc:
            log.warning("%s ignorée : %s", m.symbol, exc)
    if not data:
        raise ValueError("Aucune crypto utilisable : vérifie ta connexion internet.")
    bots = []
    for variant, tf, _, execution in picks:  # mêmes ordres et mêmes frais que le labo qui a retenu la stratégie
        for symbol, market_data in data.items():
            bs = replace(base, symbol=symbol, timeframe=tf, strategy=ALL_VARIANTS[variant], bot_label=variant,
                         execution=execution)
            state_path, journal_path = bot_paths(bs)
            bots.append(Bot(make_broker(bs, market_data), bs, StateStore(state_path), journal_path))
    registry_path = base.data_dir / "tournoi.json"
    lineup = sorted((v, tf) for v, tf, *_ in picks)
    try:  # le même tournoi relancé reprend ses bots et garde sa date de départ ; un autre repart de zéro
        previous = json.loads(registry_path.read_text(encoding="utf-8"))
        same = sorted((p["variant"], p["timeframe"]) for p in previous.get("strategies", [])) == lineup
        started = previous.get("started") if same else None
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        started = None
    registry = {
        "started": started or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lab_file": ", ".join(name for name, _ in labs),
        "markets": [asdict(m) for m in chosen],
        "strategies": [
            {"variant": v, "timeframe": tf, "lab_timeframe": row["timeframe"], "lab_verdict": row["verdict"],
             "lab_expectancy_pct": row.get("expectancy_pct"), "order_type": ex.order_type}
            for v, tf, row, ex in picks
        ],
        "capital": args.capital,
    }
    atomic_write(registry_path, json.dumps(registry, ensure_ascii=False, indent=2))
    # Sur le téléphone, seulement les résumés et les éliminations : des dizaines de bots y tradent.
    attach_telegram(s, journal=False)
    log.info(
        "Tournoi : %d stratégies × %d cryptos = %d bots, %.0f USDT fictifs chacun, %s",
        len(picks), len(data), len(bots), args.capital,
        executions.pop() if len(executions) == 1 else "ordres et frais repris de chaque labo",
        extra={**JOURNAL, **ALERT},
    )
    bot_list = [b.s for b in bots]
    last_summary = [-math.inf, -math.inf]  # console, téléphone

    def refresh() -> Path:
        path = write_dashboard(base, bots=bot_list, registry=registry)
        now = time.monotonic()
        if now - last_summary[0] >= SUMMARY_SECONDS:
            last_summary[0] = now
            phone = now - last_summary[1] >= PHONE_SUMMARY_SECONDS
            if phone:
                last_summary[1] = now
            log.info("%s", tournament_summary(bots), extra=ALERT if phone else None)
        return path

    try:
        page = refresh()
        if not args.sans_navigateur:  # lancé depuis le site : son onglet « Tableau de bord » le montre déjà
            webbrowser.open(page.resolve().as_uri())
    except Exception as exc:  # le tableau de bord ne doit jamais empêcher de trader
        log.warning("Tableau de bord du tournoi non écrit : %s", exc)
    # Bougies de moins de 15 min : un tour toutes les 15 s au plus ; au-delà, le rythme habituel suffit.
    fast = any(is_short_term(tf) for _, tf, *_ in picks)
    keep_awake()  # plusieurs jours de tournoi : l'ordinateur ne doit pas s'endormir
    run_bots(bots, min(s.poll_seconds, 15) if fast else s.poll_seconds, after_cycle=refresh)


def cmd_portfolio_lab(s: Settings, args: argparse.Namespace) -> None:
    """Le momentum croisé (garder chaque semaine les cryptos qui ont le plus monté), testé hors échantillon."""
    keep_awake()
    attach_telegram(s, journal=False)
    exchange = make_exchange(s.exchange)
    universe = [r.symbol for r in by_volume(exchange, top=args.cryptos)]
    frames = {}
    for symbol in universe:  # bougies d'un jour : le même cache que le labo long terme
        try:
            frames[symbol] = load_or_fetch(s.exchange, symbol, "1d", history_days("1d", args.days), s.data_dir / "cache",
                                           exchange)
        except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
            log.warning("%s ignorée : %s", symbol, exc)
    if len(frames) < MIN_COINS:
        raise ValueError(f"Seulement {len(frames)} cryptos récupérées : vérifie ta connexion internet.")
    opens, closes = align(frames)
    cost = s.execution.fee_rate + s.execution.slippage  # par ordre : frais au marché et glissement
    log.info("Labo portefeuille : %d variantes sur %d cryptos, %d jours", len(PORTFOLIO_VARIANTS), len(frames),
             len(closes))
    rows = evaluate_portfolio(opens, closes, cost)
    verdict = portfolio_verdict(rows, len(frames))
    print(f"\n=== Labo portefeuille (momentum croisé) : {len(frames)} cryptos ===")
    print(format_portfolio(rows))
    print()
    print(verdict)
    save_portfolio_lab(s.data_dir / Path(args.resultats).name, rows, verdict,
                       date=datetime.now(timezone.utc).isoformat(timespec="seconds"), jours=len(closes),
                       univers=sorted(frames), cout=cost)
    refresh_dashboard(s)
    log.info("Labo portefeuille terminé :\n%s", verdict, extra=ALERT)


def daily_closes(exchange: ccxt.Exchange, symbols: list[str], days: int) -> "pd.DataFrame":
    """Les dernières clôtures journalières terminées de chaque crypto (celle du jour en cours est écartée)."""
    frames, now = {}, exchange.milliseconds()
    for symbol in symbols:
        try:
            frame = ohlcv_to_frame(exchange.fetch_ohlcv(symbol, "1d", limit=days + 2))
        except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
            log.warning("%s : bougies journalières indisponibles (%s)", symbol, exc)
            continue
        frames[symbol] = frame[frame["ts"] + DAY_MS <= now]
    return align(frames)[1]


def cmd_portfolio(s: Settings, args: argparse.Namespace) -> None:
    """Le portefeuille en argent fictif : les variantes retenues par le labo portefeuille, une rotation par semaine."""
    lab = load_portfolio_lab(s.data_dir / PORTFOLIO_LAB_FILE)
    if not lab or not lab.get("rows"):
        raise ValueError("Aucun résultat du labo portefeuille : lance-le d'abord (« Labo portefeuille » sur le site).")
    retained = [r for r in lab["rows"] if r.get("verdict") in PORTFOLIO_RETAINED
                and r.get("variant") in PORTFOLIO_VARIANTS][:args.variantes]
    if not retained:
        raise NothingRetained("Le labo portefeuille n'a retenu aucune variante : sur ces cryptos, le momentum croisé "
                              "ne bat pas le panier de toutes les cryptos, frais compris. Donc pas de portefeuille, "
                              "c'est voulu.")
    universe = lab.get("univers") or []
    exchange = make_exchange(s.exchange)
    exchange.load_markets()
    universe = [u for u in universe if tradable(exchange.markets.get(u), "USDT")]  # toujours cotées
    folder = s.data_dir / PORTFOLIO_DIR
    books = [PaperPortfolio(folder / f"{slug(r['variant'])}.json", r["variant"], PORTFOLIO_VARIANTS[r["variant"]],
                            s.execution.fee_rate, s.execution.slippage, args.capital) for r in retained]
    keep_awake()  # une rotation par semaine : l'ordinateur doit rester éveillé
    attach_telegram(s, journal=False)
    log.info("Portefeuille fictif : %s, sur %d cryptos, %.0f USDT fictifs chacun",
             ", ".join(b.name for b in books), len(universe), args.capital, extra={**JOURNAL, **ALERT})
    lookback = max(b.params.lookback for b in books)
    postponed: dict[str, datetime] = {}  # rotation reportée : nouvel essai un quart d'heure plus tard
    while True:
        now = datetime.now(timezone.utc)
        try:
            tickers = exchange.fetch_tickers()  # une requête pour tout : une crypto retirée ne bloque pas les autres
            prices = {sym: float(tickers[sym]["last"]) for sym in universe if (tickers.get(sym) or {}).get("last")}
            due = [b for b in books if b.due(now) and now >= postponed.get(b.name, now)]
            if due:
                closes = daily_closes(exchange, universe, lookback + 1)
                for book in due:
                    try:
                        rotation = book.rotate(closes, prices, now)
                    except ValueError as exc:
                        postponed[book.name] = now + timedelta(minutes=15)
                        log.warning("Portefeuille %s : %s", book.name, exc)
                        continue
                    log.info("Portefeuille %s : rotation, garde %s (vendu %s), valeur %.2f USDT fictifs", book.name,
                             ", ".join(rotation["chosen"]), ", ".join(rotation["sold"]) or "rien", rotation["value"],
                             extra={**JOURNAL, **ALERT})
            for book in books:
                book.mark(prices, now)
        except (ccxt.NetworkError, ccxt.ExchangeError, ValueError, KeyError) as exc:
            log.warning("Portefeuille : %s (nouvel essai dans %.0f s)", exc, args.secondes)
        if args.une_fois:
            return
        time.sleep(args.secondes)


def cmd_trader(s: Settings, args: argparse.Namespace) -> None:
    """Le trader fictif : les stratégies retenues par le labo, sur les cryptos les plus échangées, une explication par
    trade. Avec --rejouer : les mêmes règles rejouées sur l'historique récent, pour voir des trades tout de suite."""
    settings = trader_settings(os.environ)
    execution = settings.execution(s.execution)
    folder = s.data_dir / TRADER_DIR
    exchange = make_exchange(s.exchange)

    def universe() -> list[str]:
        return [r.symbol for r in by_volume(exchange, top=settings.coins)]

    if args.rejouer:
        plays = choose_playbook(s.data_dir, settings, s.execution)
        if not plays:
            raise NothingRetained("Le labo n'a retenu aucune stratégie jouable : rien à rejouer pour l'instant.")
        keep_awake()
        coins = universe()
        frames = {}
        for tf in sorted({p.timeframe for p in plays}, key=timeframe_to_ms):
            for symbol in coins:
                try:
                    frames[(symbol, tf)] = load_or_fetch(s.exchange, symbol, tf, REPLAY_DAYS.get(tf, 90),
                                                         s.data_dir / "cache", exchange)
                except (ccxt.ExchangeError, ccxt.NetworkError) as exc:
                    log.warning("%s %s ignorée : %s", symbol, tf, exc)
        account = replay_trader(frames, plays, settings, execution, folder / REPLAY_FILE)
        view = trader_summary(account.state)
        print(f"\n=== Rejeu du trader : {', '.join(p.key for p in plays)} sur {len(coins)} cryptos ===")
        print(f"{view['count']} trades, valeur finale {view['value']:.2f} USDT fictifs pour {view['start']:.0f} au "
              f"départ ({view['pnl_pct']:+.1f} %). Rejoué sur un passé qui a servi à choisir ces stratégies : "
              "forcément flatteur, ce n'est pas une preuve.")
        for lesson in view["lessons"]:
            print("-", lesson["text"])
        return

    def refresh():
        return choose_playbook(s.data_dir, settings, s.execution), universe()

    account = TraderAccount(folder / TRADER_ACCOUNT, settings, execution, datetime.now(timezone.utc))
    keep_awake()  # le trader surveille ses stops : l'ordinateur doit rester éveillé
    attach_telegram(s, journal=False)
    plays, coins = refresh()
    log.info("Trader fictif (%s, levier jusqu'à %.0f, risque %.1f %% par trade) : %s, sur %d cryptos",
             settings.profile, settings.leverage, 100 * settings.risk_per_trade,
             ", ".join(p.key for p in plays) or "aucune stratégie retenue pour l'instant, il attend", len(coins),
             extra=ALERT)
    run_trader(exchange, account, refresh, seconds=args.secondes, once=args.une_fois, initial=(plays, coins))


HOT_REFRESH_S = 60  # la liste des cryptos agitées demande tout le marché : une fois par minute suffit


def cmd_prices(s: Settings, args: argparse.Namespace) -> None:
    """Les vrais prix de plusieurs plateformes, côte à côte, rafraîchis en continu (données publiques)."""
    bases = list(dict.fromkeys(x.strip().upper().split("/")[0] for x in args.cryptos.split(",") if x.strip()))
    platforms = [x.strip().lower() for x in args.plateformes.split(",") if x.strip()]
    exchanges, errors = connect(platforms, make_exchange)
    if not exchanges:
        raise ValueError("Aucune plateforme joignable : vérifie ta connexion internet. " + "; ".join(
            f"{label(p)} : {e}" for p, e in errors.items()))
    first_id, first = next(iter(exchanges.items()))
    try:  # « le nouveau truc » : les paires apparues sur la première plateforme depuis la dernière visite
        listings = new_listings(first, s.data_dir / f"marches-connus-{first_id}.json")
    except OSError as exc:
        log.warning("Nouvelles cotations non vérifiées : %s", exc)
        listings = None
    hot, hot_at = None, -math.inf
    while True:
        board = snapshot(exchanges, bases, errors)
        if args.agitees and time.monotonic() - hot_at >= HOT_REFRESH_S:
            try:
                hot, hot_at = scan_volatile(first, top=args.agitees), time.monotonic()
            except ccxt.BaseError as exc:
                log.warning("Liste des cryptos agitées indisponible : %s", exc)
        text = format_board(board, datetime.now(), hot, None if args.une_fois else args.secondes, listings)
        if args.une_fois:
            print(text)
            return
        os.system("cls" if os.name == "nt" else "clear")
        print(text, flush=True)
        time.sleep(args.secondes)


def cmd_telegram(s: Settings, args: argparse.Namespace) -> None:
    """Vérifie les alertes Telegram : trouve l'identifiant de la discussion s'il manque, puis envoie un test."""
    if not s.telegram_token:
        raise ConfigError(
            "Mets d'abord TELEGRAM_TOKEN dans les réglages : dans Telegram, écris à @BotFather, envoie /newbot "
            "et copie le « token » qu'il te donne."
        )
    try:
        chat = s.telegram_chat_id or latest_chat_id(s.telegram_token)
        if not chat:
            raise ValueError("Écris d'abord un message à ton bot dans Telegram, puis relance cette commande.")
        if not s.telegram_chat_id:
            print(f"Ton identifiant de discussion : {chat}")
            print(f"Ajoute cette ligne dans les réglages (« Modifier les reglages ») : TELEGRAM_CHAT_ID={chat}")
        telegram_call(s.telegram_token, "sendMessage",
                      {"chat_id": chat, "text": "Le bot de trading est bien relié à Telegram. Tu recevras ici "
                                                "ses achats, ses ventes et ses alertes."})
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Telegram a refusé : {exc}. Vérifie TELEGRAM_TOKEN (et TELEGRAM_CHAT_ID).") from None
    print("Message de test envoyé : regarde Telegram.")


def cmd_site(s: Settings, args: argparse.Namespace) -> None:
    """Le site du bot : tout à portée de main dans le navigateur (voir tradingbot/webapp.py)."""
    serve(Path.cwd(), args.pristine_env, make_exchange, port=args.port, open_browser=not args.sans_navigateur,
          lan=args.ipad)


def cmd_dashboard(s: Settings, args: argparse.Namespace) -> None:
    path = write_dashboard(s)
    print(f"Tableau de bord : {path}")
    if not args.no_open:
        webbrowser.open(path.resolve().as_uri())


def cmd_reset_guard(s: Settings, args: argparse.Namespace) -> None:
    for bs in bot_settings(s):
        state_path, _ = bot_paths(bs)
        store = StateStore(state_path)
        state = store.load()
        if not state.get("guard") and not state.get("eliminated"):
            print(f"[{bs.symbol} {bs.timeframe}] aucun garde-fou enregistré.")
            continue
        # Une stratégie éliminée repart de zéro : sinon ses anciens trades l'élimineraient au premier trade.
        state.update(guard=None, eliminated=None, perf=None)
        store.save(state)
        print(f"[{bs.symbol} {bs.timeframe}] garde-fou réarmé : le bot pourra de nouveau ouvrir des positions.")


def live_output() -> None:
    """Lancé par le site : sortie en UTF-8, ligne par ligne, pour que son journal s'affiche en direct."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("TRADINGBOT_SITE"):
        live_output()
    pristine_env = dict(os.environ)  # avant .env : le site le donne aux commandes, qui relisent .env elles-mêmes
    load_dotenv()
    if argv is None:
        argv = sys.argv[1:] or ["site"]  # double-clic sur le programme : le site s'ouvre
    parser = argparse.ArgumentParser(description="Bot de trading spot : backtest, labo, tournoi et bots en direct")
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("site", help="ouvrir le site du bot dans le navigateur (tout à portée de main)")
    st.add_argument("--port", type=int, default=PORT)
    st.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur")
    st.add_argument("--ipad", action="store_true",
                    help="ouvrir aussi le site aux appareils du Wi-Fi de la maison (avec un code)")
    bt = sub.add_parser("backtest", help="tester la stratégie sur l'historique")
    bt.add_argument("--days", type=int, default=730, help="profondeur d'historique en jours")
    bt.add_argument("--capital", type=float, default=10_000.0)
    bt.add_argument("--csv", help="fichier CSV ts,open,high,low,close,volume au lieu de télécharger")
    rb = sub.add_parser("robustesse", help="tester la stratégie sur plusieurs marchés et périodes")
    rb.add_argument("--symbols", default="BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT")
    rb.add_argument("--timeframes", default="15m,1h,4h,1d")
    rb.add_argument("--days", type=int, default=730)
    rb.add_argument("--periods", type=int, default=4, help="nombre de sous-périodes pour juger la régularité")
    lb = sub.add_parser("labo", help="comparer plusieurs stratégies sur plusieurs marchés, validées hors échantillon")
    lb.add_argument("--symbols", default=LAB_SYMBOLS)
    lb.add_argument("--timeframes", default="15m,1h,4h,1d")
    lb.add_argument("--days", type=int, default=730)
    lb.add_argument("--csv-dir", help="dossier de CSV quotidiens (actions, ETF...) ajoutés aux tests en 1 jour")
    lb.add_argument("--scanner", type=int, default=0, help="ajouter les N cryptos les plus agitées du moment")
    lb.add_argument("--memecoins", action="store_true", help="ajouter les memecoins cotés et assez échangés")
    lb.add_argument("--ordres-limites", action="store_true",
                    help="simuler des ordres limites (frais maker, sans écart ni glissement à l'entrée)")
    lb.add_argument("--futures", action="store_true",
                    help="frais des contrats à terme (0,05 %% au marché, 0,02 %% en limite, financement toutes les 8 h)")
    lb.add_argument("--combinaisons", action="store_true",
                    help="ajouter les combinaisons court terme (filtres de volatilité, de volume, d'heures et de "
                         "compression) et les impulsions (sauter sur un mouvement soudain)")
    lb.add_argument("--coeurs", type=int, default=None,
                    help="cœurs du processeur à utiliser (par défaut : tous sauf un)")
    lb.add_argument("--resultats", default=LAB_FILE,
                    help="fichier des résultats dans data (le court terme a le sien pour ne pas écraser le long terme)")
    tn = sub.add_parser("tournoi", help="faire s'affronter en argent fictif les stratégies retenues par le labo")
    tn.add_argument("--unite", help="forcer une unité de temps pour toutes les stratégies (ex. 1m)")
    tn.add_argument("--top", type=int, default=8, help="nombre de cryptos agitées choisies par le scanner")
    tn.add_argument("--symbols", help="liste de paires à la place du scanner (ex. BTC/USDT,PEPE/USDT)")
    tn.add_argument("--sans-memecoins", action="store_true", help="ne pas ajouter les memecoins")
    tn.add_argument("--labo", default=LAB_FILE, help="fichier de résultats du labo à reprendre (dans data)")
    tn.add_argument("--avec-marches-du-labo", action="store_true",
                    help="ajouter les marchés sur lesquels le labo a testé ses stratégies")
    tn.add_argument("--strategies", type=int, default=6, help="nombre maximum de stratégies en compétition")
    tn.add_argument("--capital", type=float, default=1000.0, help="capital fictif de chaque bot")
    tn.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le tableau de bord au départ")
    pr = sub.add_parser("prix", help="les vrais prix de plusieurs plateformes, en direct et sans compte")
    pr.add_argument("--cryptos", default=",".join(DEFAULT_CRYPTOS))
    pr.add_argument("--plateformes", default=",".join(DEFAULT_PLATFORMS))
    pr.add_argument("--secondes", type=float, default=10.0, help="délai entre deux mises à jour")
    pr.add_argument("--agitees", type=int, default=8, help="nombre de cryptos agitées à lister (0 = aucune)")
    pr.add_argument("--une-fois", action="store_true", help="afficher une seule fois, puis s'arrêter")
    lp = sub.add_parser("labo-portefeuille", help="tester le momentum croisé (garder les cryptos qui ont le plus monté)")
    lp.add_argument("--cryptos", type=int, default=30, help="nombre de cryptos, les plus échangées")
    lp.add_argument("--days", type=int, default=2500, help="jours d'historique (bougies d'un jour)")
    lp.add_argument("--resultats", default=PORTFOLIO_LAB_FILE)
    pf = sub.add_parser("portefeuille", help="le momentum croisé en argent fictif, une rotation par semaine")
    pf.add_argument("--capital", type=float, default=1000.0, help="capital fictif de chaque portefeuille")
    pf.add_argument("--variantes", type=int, default=2, help="nombre de variantes retenues à faire tourner")
    pf.add_argument("--secondes", type=float, default=60.0, help="délai entre deux relevés de prix")
    pf.add_argument("--une-fois", action="store_true", help="un seul tour (rotation si elle est due), puis s'arrêter")
    tr = sub.add_parser("trader", help="le trader fictif : les stratégies du labo sur beaucoup de cryptos, expliquées")
    tr.add_argument("--rejouer", action="store_true", help="rejouer ses règles sur l'historique récent, puis s'arrêter")
    tr.add_argument("--secondes", type=float, default=20.0, help="délai entre deux tours")
    tr.add_argument("--une-fois", action="store_true", help="un seul tour, puis s'arrêter")
    sub.add_parser("telegram", help="relier les alertes du bot à Telegram et envoyer un message de test")
    sub.add_parser("check", help="vérifier la connexion et les soldes")
    sub.add_parser("run", help="lancer le ou les bots (selon MODE et BOTS dans .env)")
    tb = sub.add_parser("tableau", help="générer et ouvrir le tableau de bord")
    tb.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    sub.add_parser("reset-guard", help="réarmer les bots après un arrêt pour drawdown (bots arrêtés)")
    args = parser.parse_args(argv)
    args.pristine_env = pristine_env

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.data_dir)
    commands = {
        "backtest": cmd_backtest,
        "robustesse": cmd_robustness,
        "labo": cmd_lab,
        "tournoi": cmd_tournament,
        "prix": cmd_prices,
        "telegram": cmd_telegram,
        "check": cmd_check,
        "run": cmd_run,
        "tableau": cmd_dashboard,
        "reset-guard": cmd_reset_guard,
        "site": cmd_site,
        "labo-portefeuille": cmd_portfolio_lab,
        "portefeuille": cmd_portfolio,
        "trader": cmd_trader,
    }
    try:
        commands[args.command](settings, args)
    except ConfigError as exc:
        log.error("Configuration invalide : %s", exc)
        return 2
    except ccxt.AuthenticationError as exc:
        log.error("Clés API refusées (vérifie API_KEY, API_SECRET et que MODE correspond à leur origine) : %s", exc)
        return 1
    except ccxt.NetworkError as exc:
        log.error("Impossible de joindre %s : %s", settings.exchange, exc)
        return 1
    except NothingRetained as exc:
        log.warning("%s", exc)
        return 0
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("Arrêt demandé. La position éventuelle reste ouverte et sera reprise au redémarrage.")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()  # version Windows sans Python : le labo lance plusieurs processus
    sys.exit(main())
