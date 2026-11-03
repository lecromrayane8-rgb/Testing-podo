"""Point d'entrée : python main.py {backtest,robustesse,check,run,reset-guard} --help"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

import ccxt

from tradingbot.backtest import format_comparison, format_report, run_backtest
from tradingbot.broker import CcxtBroker, PaperBroker
from tradingbot.config import ConfigError, Settings, load_dotenv
from tradingbot.data import load_csv, load_or_fetch, make_exchange
from tradingbot.live import Bot, StateStore
from tradingbot.obsidian import ObsidianHandler, ObsidianJournal
from tradingbot.robustness import evaluate, format_robustness, overall_verdict

log = logging.getLogger("tradingbot")


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
        wallet = s.data_dir / f"paper_wallet_{s.exchange}_{s.symbol.replace('/', '-')}.json"
        return PaperBroker(data, wallet, s.paper_start_balance, s.execution)
    venue = {"testnet": "testnet", "demo": "demo", "live": "real"}[s.mode]
    return CcxtBroker(s.exchange, s.symbol, s.api_key, s.api_secret, s.api_password, venue=venue)


def make_notes(s: Settings) -> ObsidianJournal | None:
    return ObsidianJournal(s.obsidian_vault) if s.obsidian_vault else None


def state_paths(s: Settings) -> tuple[Path, Path]:
    tag = f"{s.mode}_{s.exchange}_{s.symbol.replace('/', '-')}_{s.timeframe}"
    return s.data_dir / f"state_{tag}.json", s.data_dir / f"trades_{tag}.csv"


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
            df = load_or_fetch(s.exchange, symbol, tf, args.days, s.data_dir / "cache", exchange)
        except ccxt.BadSymbol:
            log.warning("%s introuvable sur %s : ignoré", symbol, s.exchange)
            continue
        result = run_backtest(df, s.strategy, s.risk, 10_000.0, s.execution)
        rows.append(evaluate(f"{symbol} {tf}", result, n_tests=len(markets), n_periods=args.periods))
    table = format_robustness(rows, args.periods)
    verdict = overall_verdict(rows)
    print(f"\n=== Robustesse sur {s.exchange}, {args.days} jours, ordres {s.execution.order_type} ===")
    print(table)
    print()
    print(verdict)
    if notes := make_notes(s):
        print(f"\nNote Obsidian : {notes.robustness(s, rows, table, verdict, args.days)}")


def cmd_check(s: Settings, args: argparse.Namespace) -> None:
    s.validate_for_trading()
    broker = make_broker(s)
    balances = broker.balances()
    price = broker.last_price()
    candles = broker.fetch_candles(s.timeframe, 5)
    base, quote = s.symbol.split("/")
    print(f"Connexion OK : mode={s.mode} plateforme={s.exchange}")
    print(f"Prix {s.symbol} : {price:.2f}")
    print(f"Soldes disponibles : {balances.base:.8f} {base} | {balances.quote:.2f} {quote}")
    print(f"Dernière bougie {s.timeframe} : {candles.index[-1]}")
    fees = broker.trading_fees()
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


def cmd_run(s: Settings, args: argparse.Namespace) -> None:
    s.validate_for_trading()
    if s.mode == "live":
        log.warning("MODE LIVE : le bot va passer de vrais ordres, capital max %.2f", s.max_capital)
    state_path, journal_path = state_paths(s)
    notes = make_notes(s)
    if notes:
        logging.getLogger("tradingbot").addHandler(ObsidianHandler(notes))
    Bot(make_broker(s), s, StateStore(state_path), journal_path, notes).run_forever()


def cmd_reset_guard(s: Settings, args: argparse.Namespace) -> None:
    state_path, _ = state_paths(s)
    store = StateStore(state_path)
    state = store.load()
    if not state.get("guard"):
        print("Aucun garde-fou enregistré.")
        return
    state["guard"] = None
    store.save(state)
    print("Garde-fou réarmé : le bot pourra de nouveau ouvrir des positions.")


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
    rb.add_argument("--timeframes", default="15m,1h,4h")
    rb.add_argument("--days", type=int, default=730)
    rb.add_argument("--periods", type=int, default=4, help="nombre de sous-périodes pour juger la régularité")
    sub.add_parser("check", help="vérifier la connexion et les soldes")
    sub.add_parser("run", help="lancer le bot (selon MODE dans .env)")
    sub.add_parser("reset-guard", help="réarmer le bot après un arrêt pour drawdown (bot arrêté)")
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
        "check": cmd_check,
        "run": cmd_run,
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
