"""Backtest bougie par bougie, avec frais, slippage et mêmes règles que le bot en direct.

Les signaux sont calculés à la clôture d'une bougie et exécutés à l'ouverture de la
suivante (pas de regard vers le futur). Le stop est testé sur le plus bas de chaque bougie.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .risk import RiskGuard, RiskParams, position_size
from .strategy import StrategyParams, compute_indicators, entry_signal, exit_reason, initial_stop


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

    @property
    def pnl(self) -> float:
        return self.proceeds - self.cost

    @property
    def return_pct(self) -> float:
        return self.pnl / self.cost


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


def run_backtest(
    df: pd.DataFrame,
    strategy: StrategyParams = StrategyParams(),
    risk: RiskParams = RiskParams(),
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage: float = 0.0005,
) -> BacktestResult:
    data = compute_indicators(df, strategy)
    index = data.index
    o, l, c = (data[k].to_numpy(float) for k in ("open", "low", "close"))
    trend, rsi_, exit_ma, atr_ = (data[k].to_numpy(float) for k in ("trend_ma", "rsi", "exit_ma", "atr"))
    n = len(data)

    cash = initial_capital
    pos: _Position | None = None
    pending_entry_atr: float | None = None
    pending_exit: str | None = None
    guard = RiskGuard(risk)
    trades: list[Trade] = []
    equity = np.empty(n)
    bars_in_market = 0

    def close_position(i: int, price: float, reason: str) -> None:
        nonlocal cash, pos
        proceeds = pos.qty * price * (1 - fee_rate)
        cash += proceeds
        trades.append(
            Trade(pos.entry_time, index[i], pos.entry_price, price, pos.qty, pos.cost, proceeds, reason)
        )
        pos = None

    for i in range(n):
        if pending_exit and pos:
            close_position(i, o[i] * (1 - slippage), pending_exit)
        if pending_entry_atr is not None and pos is None:
            fill = o[i] * (1 + slippage)
            stop = initial_stop(fill, pending_entry_atr, strategy)
            qty = min(position_size(cash, fill, stop, risk), cash / (fill * (1 + fee_rate)))
            if qty > 0:
                cost = qty * fill * (1 + fee_rate)
                cash -= cost
                pos = _Position(i, index[i], fill, qty, cost, stop)
        pending_entry_atr = None
        pending_exit = None

        if pos:
            if o[i] <= pos.stop:
                close_position(i, o[i] * (1 - slippage), "stop")
            elif l[i] <= pos.stop:
                close_position(i, pos.stop * (1 - slippage), "stop")

        equity[i] = cash + (pos.qty * c[i] if pos else 0.0)
        guard.update(equity[i], index[i].strftime("%Y-%m-%d"))

        if pos:
            bars_in_market += 1
            reason = exit_reason(c[i], exit_ma[i], i - pos.entry_index + 1, strategy)
            if reason:
                pending_exit = reason
        elif guard.can_open() and entry_signal(c[i], trend[i], rsi_[i], atr_[i], strategy):
            pending_entry_atr = atr_[i]

    if pos:
        close_position(n - 1, c[-1] * (1 - slippage), "fin du test")
        equity[-1] = cash

    equity_series = pd.Series(equity, index=index, name="equity")
    result = BacktestResult(trades, equity_series)
    result.metrics = compute_metrics(result, data, initial_capital, bars_in_market)
    result.metrics["arret_garde_fou"] = guard.halted
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

    lines = [
        f"Période               : {m['periode']}",
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
        f"Capital final         : {num(m['capital_final'])}",
    ]
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
