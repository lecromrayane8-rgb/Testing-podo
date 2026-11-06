"""Backtest bougie par bougie, avec frais, slippage et mêmes règles que le bot en direct.

Les signaux sont calculés à la clôture d'une bougie et exécutés à l'ouverture de la
suivante (pas de regard vers le futur). Le stop est testé sur le plus bas de chaque bougie.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .execution import ExecutionParams
from .explain import read_chart
from .risk import RiskGuard, RiskParams, TradeStats, elimination_reason, position_size
from .strategy import StrategyParams, compute_signals, exit_reason, initial_stop


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    qty: float
    cost: float
    proceeds: float
    reason: str
    entry_mark: float = math.nan  # prix du graphique, avant glissement et frais
    exit_mark: float = math.nan
    entry_index: int = -1  # bougies d'entrée et de sortie
    exit_index: int = -1
    stop: float = math.nan  # stop de départ
    funding: float = 0.0  # financement payé (futures)
    mfe: float = math.nan  # plus haut atteint pendant le trade, par rapport au prix d'entrée du graphique
    mae: float = math.nan  # plus bas atteint
    context: dict | None = None  # la lecture du graphique à la bougie du signal (avec explain=True)

    @property
    def pnl(self) -> float:
        return self.proceeds - self.cost

    @property
    def return_pct(self) -> float:
        return self.pnl / self.cost

    @property
    def gross_return(self) -> float:
        """Ce que la stratégie a capté sur le prix, avant frais et glissement."""
        return self.exit_mark / self.entry_mark - 1


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity: pd.Series
    metrics: dict = field(default_factory=dict)

    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "entree": t.entry_time,
                    "sortie": t.exit_time,
                    "prix_entree": t.entry_price,
                    "prix_sortie": t.exit_price,
                    "quantite": t.qty,
                    "pnl": t.pnl,
                    "rendement_pct": 100 * t.return_pct,
                    "raison": t.reason,
                }
                for t in self.trades
            ]
        )


@dataclass
class _Position:
    entry_index: int
    entry_time: pd.Timestamp
    entry_price: float
    qty: float
    cost: float
    stop: float
    entry_mark: float = math.nan


@dataclass
class _LimitOrder:
    side: str
    price: float
    placed_index: int
    expires_index: int  # bougie à l'ouverture de laquelle l'ordre est annulé
    reason: str
    atr: float = math.nan


def run_backtest(
    df: pd.DataFrame,
    strategy: StrategyParams = StrategyParams(),
    risk: RiskParams = RiskParams(),
    initial_capital: float = 10_000.0,
    execution: ExecutionParams = ExecutionParams(),
    explain: bool = False,
) -> BacktestResult:
    """Ordres limites : placés à l'ouverture de la bougie qui suit le signal (≈ meilleur prix du
    carnet à ce moment), exécutés seulement si le prix passe strictement au-delà de la limite
    pendant leur durée de vie. Si une bougie touche à la fois le stop et la limite de sortie,
    on suppose le pire (le stop). Futures : le financement est payé à la sortie, au prorata du temps passé.
    `explain` : chaque trade garde la lecture du graphique au signal, et le plus haut et le plus bas atteints
    (plus lent : seulement pour montrer des trades, pas dans le labo)."""
    ex = execution
    data = compute_signals(df, strategy)
    index = data.index
    o, h, l, c, atr_ = (data[k].to_numpy(float) for k in ("open", "high", "low", "close", "atr"))
    entry_sig, exit_sig = data["entry"].to_numpy(bool), data["exit"].to_numpy(bool)
    days = list(index.strftime("%Y-%m-%d"))  # calculé une fois : strftime par bougie coûtait cher
    n = len(data)

    cash = initial_capital
    pos: _Position | None = None
    order: _LimitOrder | None = None
    pending_entry_atr: float | None = None
    pending_exit: str | None = None
    guard = RiskGuard(risk)
    trades: list[Trade] = []
    equity = np.empty(n)
    bars_in_market = 0
    fees_paid = 0.0
    skipped_entries = 0
    stats = TradeStats()
    eliminated: str | None = None

    def open_position(i: int, entry_index: int, price: float, atr_value: float, fee: float, mark: float) -> None:
        nonlocal cash, pos, fees_paid
        stop = initial_stop(price, atr_value, strategy)
        qty = min(position_size(cash, price, stop, risk), cash / (price * (1 + fee)))
        if qty > 0:
            cost = qty * price * (1 + fee)
            fees_paid += qty * price * fee
            cash -= cost
            pos = _Position(entry_index, index[i], price, qty, cost, stop, mark)

    def close_position(i: int, price: float, reason: str, fee: float, mark: float) -> None:
        nonlocal cash, pos, fees_paid, eliminated
        hours = (index[i] - pos.entry_time).total_seconds() / 3600
        funding = pos.qty * pos.entry_price * ex.funding_rate_8h * hours / 8
        proceeds = pos.qty * price * (1 - fee) - funding
        fees_paid += pos.qty * price * fee + funding
        cash += proceeds
        trades.append(Trade(
            pos.entry_time, index[i], pos.entry_price, price, pos.qty, pos.cost, proceeds, reason, pos.entry_mark, mark,
            pos.entry_index, i, pos.stop, funding,
        ))
        stats.add((proceeds - pos.cost) / pos.cost)
        eliminated = eliminated or elimination_reason(stats, risk.eliminate_after_trades)
        pos = None

    def market_buy(i: int, entry_index: int, atr_value: float) -> None:
        open_position(i, entry_index, o[i] * (1 + ex.slippage), atr_value, ex.fee_rate, o[i])

    def market_sell(i: int, reason: str) -> None:
        close_position(i, o[i] * (1 - ex.slippage), reason, ex.fee_rate, o[i])

    def check_stop(i: int) -> bool:
        if pos and l[i] <= pos.stop:
            mark = min(o[i], pos.stop)
            close_position(i, mark * (1 - ex.slippage), "stop", ex.fee_rate, mark)
            return True
        return False

    for i in range(n):
        # 1. À l'ouverture : ordres limites expirés, puis décisions prises à la clôture précédente.
        if order and i >= order.expires_index:
            if order.side == "sell":
                market_sell(i, order.reason)
            elif ex.limit_entry_fallback == "market":
                market_buy(i, order.placed_index, order.atr)
            else:
                skipped_entries += 1
            order = None
        if pending_exit and pos:
            if ex.order_type == "market":
                market_sell(i, pending_exit)
            else:
                order = _LimitOrder("sell", o[i], i, i + ex.limit_timeout_bars, pending_exit)
        if pending_entry_atr is not None and pos is None:
            if ex.order_type == "market":
                market_buy(i, i, pending_entry_atr)
            else:
                order = _LimitOrder("buy", o[i], i, i + ex.limit_timeout_bars, "entree", pending_entry_atr)
        pending_entry_atr = None
        pending_exit = None

        # 2. Pendant la bougie : stop d'abord (hypothèse prudente), puis ordres limites.
        if check_stop(i) and order and order.side == "sell":
            order = None
        if order and order.side == "sell" and h[i] > order.price:
            close_position(i, order.price, order.reason, ex.maker_fee_rate, order.price)
            order = None
        elif order and order.side == "buy" and l[i] < order.price:
            open_position(i, order.placed_index, order.price, order.atr, ex.maker_fee_rate, order.price)
            order = None
            check_stop(i)

        equity[i] = cash + (pos.qty * c[i] if pos else 0.0)
        guard.update(equity[i], days[i])

        # 3. À la clôture : signaux (aucun nouveau signal tant qu'un ordre limite est en attente),
        #    seulement une fois l'historique de chauffe atteint, exactement comme le bot en direct.
        if i + 1 < strategy.warmup_bars:
            continue
        if pos:
            bars_in_market += 1
            reason = exit_reason(exit_sig[i], i - pos.entry_index + 1, strategy) if order is None else None
            if reason:
                pending_exit = reason
        elif order is None and not eliminated and guard.can_open() and entry_sig[i]:
            pending_entry_atr = atr_[i]

    if pos:
        close_position(n - 1, c[-1] * (1 - ex.slippage), "fin du test", ex.fee_rate, c[-1])
        equity[-1] = cash

    if explain:
        for t in trades:
            base = t.entry_mark if t.entry_mark > 0 else t.entry_price
            t.mfe = float(h[t.entry_index:t.exit_index + 1].max()) / base - 1
            t.mae = float(l[t.entry_index:t.exit_index + 1].min()) / base - 1
            signal = max(t.entry_index - 1, 0)  # la bougie dont la clôture a donné le signal
            t.context = read_chart(df.iloc[max(0, signal - 400):signal + 1],
                                   fees=2 * (ex.fee_rate + ex.slippage))

    equity_series = pd.Series(equity, index=index, name="equity")
    result = BacktestResult(trades, equity_series)
    result.metrics = compute_metrics(result, data, initial_capital, bars_in_market)
    result.metrics.update(
        type_ordres=ex.order_type,
        frais_payes=fees_paid,
        entrees_abandonnees=skipped_entries,
        arret_garde_fou=guard.halted or (f"stratégie éliminée : {eliminated}" if eliminated else None),
    )
    return result


def compute_metrics(result: BacktestResult, data: pd.DataFrame, initial_capital: float, bars_in_market: int) -> dict:
    trades = result.trades
    equity = result.equity
    pnls = np.array([t.pnl for t in trades])
    rets = np.array([t.return_pct for t in trades])
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gross_profit, gross_loss = wins.sum(), -losses.sum()

    bar_seconds = data["ts"].diff().median() / 1000 if len(data) > 1 else math.nan
    bars_per_year = 365 * 24 * 3600 / bar_seconds if bar_seconds else math.nan
    bar_returns = equity.pct_change().dropna()
    sharpe = (
        bar_returns.mean() / bar_returns.std() * math.sqrt(bars_per_year)
        if len(bar_returns) > 1 and bar_returns.std() > 0
        else math.nan
    )

    return {
        "periode": f"{data.index[0]:%Y-%m-%d} -> {data.index[-1]:%Y-%m-%d}",
        "nb_trades": len(trades),
        "taux_reussite": len(wins) / len(trades) if trades else math.nan,
        "gain_moyen_pct": 100 * rets[pnls > 0].mean() if len(wins) else math.nan,
        "perte_moyenne_pct": 100 * rets[pnls <= 0].mean() if len(losses) else math.nan,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else math.inf if gross_profit > 0 else math.nan,
        "esperance_pct": 100 * rets.mean() if trades else math.nan,
        "rendement_total": equity.iloc[-1] / initial_capital - 1,
        "rendement_buy_and_hold": data["close"].iloc[-1] / data["open"].iloc[0] - 1,
        "drawdown_max": (equity / equity.cummax() - 1).min(),
        "sharpe": sharpe,
        "exposition": bars_in_market / len(data),
        "capital_final": equity.iloc[-1],
    }


def format_report(m: dict) -> str:
    def pct(x: float) -> str:
        return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+.2f} %"

    def num(x: float, fmt: str = ".2f") -> str:
        return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, fmt)

    order_label = "limites (post-only)" if m.get("type_ordres") == "limit" else "au marché"
    lines = [
        f"Période               : {m['periode']}",
        f"Type d'ordres         : {order_label}",
        f"Nombre de trades      : {m['nb_trades']}",
        f"Taux de réussite      : {num(100 * m['taux_reussite'], '.1f')} %",
        f"Gain moyen / trade    : {num(m['gain_moyen_pct'], '+.2f')} %",
        f"Perte moyenne / trade : {num(m['perte_moyenne_pct'], '+.2f')} %",
        f"Profit factor         : {num(m['profit_factor'])}",
        f"Espérance / trade     : {num(m['esperance_pct'], '+.3f')} %",
        f"Rendement total       : {pct(m['rendement_total'])}",
        f"Buy & hold (référence): {pct(m['rendement_buy_and_hold'])}",
        f"Drawdown max          : {pct(m['drawdown_max'])}",
        f"Sharpe (annualisé)    : {num(m['sharpe'])}",
        f"Temps en position     : {num(100 * m['exposition'], '.1f')} %",
        f"Frais payés           : {num(m.get('frais_payes', math.nan))}",
        f"Capital final         : {num(m['capital_final'])}",
    ]
    if m.get("type_ordres") == "limit":
        lines.append(f"Entrées abandonnées   : {m['entrees_abandonnees']} (ordre limite non exécuté)")
    if m.get("arret_garde_fou"):
        lines.append(f"Garde-fou déclenché   : {m['arret_garde_fou']}")
    lines.append("")
    lines.append(verdict(m))
    return "\n".join(lines)


def verdict(m: dict) -> str:
    if m["nb_trades"] < 30:
        return "VERDICT : moins de 30 trades, échantillon trop petit pour conclure quoi que ce soit."
    if not m["esperance_pct"] > 0 or not m["profit_factor"] > 1:
        return (
            "VERDICT : espérance négative après frais. Un taux de réussite élevé ne suffit pas :\n"
            "les pertes mangent les gains. NE PAS utiliser ces réglages avec de l'argent réel."
        )
    if m["rendement_total"] < m["rendement_buy_and_hold"]:
        return (
            "VERDICT : espérance positive, mais moins bien que simplement acheter et garder sur la période.\n"
            "À valider sur d'autres périodes et en testnet avant tout argent réel."
        )
    return (
        "VERDICT : espérance positive sur cette période. Les performances passées ne garantissent rien :\n"
        "vérifie sur d'autres périodes/paires, puis plusieurs semaines en testnet avant l'argent réel."
    )


def format_comparison(results: dict[str, BacktestResult]) -> str:
    """Tableau court : mêmes réglages, ordres au marché vs ordres limites."""
    labels = {"market": "Au marché", "limit": "Limites"}
    header = f"{'Ordres':<11}{'Trades':>8}{'Réussite':>10}{'Espérance':>11}{'Rendement':>11}{'Frais':>10}"
    rows = [header, "-" * len(header)]
    for key, result in results.items():
        m = result.metrics
        win = "n/a" if math.isnan(m["taux_reussite"]) else f"{100 * m['taux_reussite']:.1f} %"
        exp = "n/a" if math.isnan(m["esperance_pct"]) else f"{m['esperance_pct']:+.3f} %"
        rows.append(
            f"{labels.get(key, key):<11}{m['nb_trades']:>8}{win:>10}{exp:>11}"
            f"{100 * m['rendement_total']:>+10.2f}%{m['frais_payes']:>10.2f}"
        )
    return "\n".join(rows)
