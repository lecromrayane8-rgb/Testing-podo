"""Point d'entrée : python main.py {backtest,robustesse,check,run,tableau,reset-guard} --help"""
from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from tradingbot.backtest import format_comparison, format_report, run_backtest
from tradingbot.broker import CcxtBroker, PaperBroker
from tradingbot.config import ConfigError, Settings, load_dotenv
from tradingbot.dashboard import ROBUSTNESS_FILE, write_dashboard
from tradingbot.data import load_csv, load_or_fetch, make_exchange, timeframe_to_ms
from tradingbot.lab import (
    LAB_FILE, PROMISING, VARIANTS, env_lines, format_lab, overall_lab_verdict, run_lab, save_lab,
)
from tradingbot.live import Bot, StateStore, bot_paths, run_bots
from tradingbot.obsidian import ObsidianHandler, ObsidianJournal
from tradingbot.robustness import evaluate, format_robustness, overall_verdict, research_risk, save_results

log = logging.getLogger("tradingbot")

DAY_MS = 86_400_000
LONG_TERM_DAYS = 2500  # bougies d'un jour : ~7 ans d'historique pour avoir assez de trades
LAB_SYMBOLS = "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,PAXG/USDT,EUR/USDT"  # PAXG = or, EUR = euro/dollar


def history_days(timeframe: str, days: int) -> int:
    return max(days, LONG_TERM_DAYS) if timeframe_to_ms(timeframe) >= DAY_MS else days


def setup_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(data_dir / "bot.log", encoding="utf-8")],
    )


def make_broker(s: Settings):
    if s.mode == "paper":
        data = CcxtBroker(s.exchange, s.symbol)
        # Un compte fictif par bot : deux bots sur la même paire ne se partagent jamais leurs fonds.
        pair = s.symbol.replace("/", "-")
        wallet = s.data_dir / f"paper_wallet_{s.exchange}_{pair}_{s.timeframe}.json"
        legacy = s.data_dir / f"paper_wallet_{s.exchange}_{pair}.json"  # nom des versions précédentes
        if legacy.exists() and not wallet.exists() and s.timeframe == s.markets[0][1]:
            legacy.rename(wallet)
        return PaperBroker(data, wallet, s.paper_start_balance, s.execution)
    venue = {"testnet": "testnet", "demo": "demo", "live": "real"}[s.mode]
    return CcxtBroker(s.exchange, s.symbol, s.api_key, s.api_secret, s.api_password, venue=venue)


def make_notes(s: Settings) -> ObsidianJournal | None:
    return ObsidianJournal(s.obsidian_vault) if s.obsidian_vault else None


def bot_settings(s: Settings) -> list[Settings]:
    """Un jeu de réglages par bot (BOTS), chacun avec sa paire et son unité de temps."""
    return [replace(s, symbol=symbol, timeframe=timeframe) for symbol, timeframe in s.markets]


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
    print(f"\nTableau de bord mis à jour : {write_dashboard(s)}")
    if notes := make_notes(s):
        print(f"Note Obsidian : {notes.robustness(s, rows, table, verdict, args.days)}")


def cmd_lab(s: Settings, args: argparse.Namespace) -> None:
    symbols = [x.strip().upper() for x in args.symbols.split(",") if x.strip()]
    timeframes = [x.strip() for x in args.timeframes.split(",") if x.strip()]
    exchange = make_exchange(s.exchange)
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
    log.info("Laboratoire : %d variantes × %d unités de temps sur %d marchés", len(VARIANTS), len(datasets), len(markets))
    rows = run_lab(datasets, s.execution, s.risk)
    table, verdict = format_lab(rows), overall_lab_verdict(rows)
    print(f"\n=== Laboratoire de stratégies : {', '.join(markets)} ===")
    print(table)
    print()
    print(verdict)
    best = next((r for r in rows if r.verdict == PROMISING), None)
    if best:
        tradable = [m for m in datasets.get(best.timeframe, {}) if "/" in m]
        print("\nPour l'essayer en argent fictif, mets ces lignes dans .env (« Modifier les reglages ») :")
        print(env_lines(VARIANTS[best.variant]))
        print(f"BOTS={','.join(f'{m}@{best.timeframe}' for m in tradable)}")
    save_lab(
        s.data_dir / LAB_FILE, rows, verdict,
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"), jours=args.days, marches=markets,
    )
    print(f"\nTableau de bord mis à jour : {write_dashboard(s)}")
    if notes := make_notes(s):
        print(f"Note Obsidian : {notes.lab(s, rows, table, verdict, args.days)}")


def cmd_check(s: Settings, args: argparse.Namespace) -> None:
    s.validate_for_trading()
    for bs in bot_settings(s):
        broker = make_broker(bs)
        balances = broker.balances()
        price = broker.last_price()
        candles = broker.fetch_candles(bs.timeframe, 5)
        base, quote = bs.symbol.split("/")
        print(f"\n[{bs.symbol} {bs.timeframe}] connexion OK : mode={bs.mode} plateforme={bs.exchange}")
        print(f"Prix {bs.symbol} : {price:.2f}")
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
    if s.mode == "live":
        log.warning("MODE LIVE : les bots vont passer de vrais ordres, capital max %.2f chacun", s.max_capital)
    notes = make_notes(s)
    if notes:
        logging.getLogger("tradingbot").addHandler(ObsidianHandler(notes))
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
        if not state.get("guard"):
            print(f"[{bs.symbol} {bs.timeframe}] aucun garde-fou enregistré.")
            continue
        state["guard"] = None
        store.save(state)
        print(f"[{bs.symbol} {bs.timeframe}] garde-fou réarmé : le bot pourra de nouveau ouvrir des positions.")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Bot de trading spot (retour à la moyenne)")
    sub = parser.add_subparsers(dest="command", required=True)
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
    sub.add_parser("check", help="vérifier la connexion et les soldes")
    sub.add_parser("run", help="lancer le ou les bots (selon MODE et BOTS dans .env)")
    tb = sub.add_parser("tableau", help="générer et ouvrir le tableau de bord")
    tb.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    sub.add_parser("reset-guard", help="réarmer les bots après un arrêt pour drawdown (bots arrêtés)")
    args = parser.parse_args(argv)

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
        "check": cmd_check,
        "run": cmd_run,
        "tableau": cmd_dashboard,
        "reset-guard": cmd_reset_guard,
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
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("Arrêt demandé. La position éventuelle reste ouverte et sera reprise au redémarrage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
