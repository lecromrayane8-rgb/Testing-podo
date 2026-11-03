"""Laboratoire : plusieurs familles de stratégies, testées sur plusieurs marchés, validées hors échantillon.

Méthode, pour ne pas se laisser tromper par la chance :
1. Chaque historique est coupé dans le temps : les 60 % les plus anciens servent d'« étude »,
   les 40 % les plus récents de « validation ». Seule la validation décide du verdict.
2. Une variante est jugée sur tous les marchés à la fois (trades mis en commun) : une structure
   qui marche doit marcher un peu partout, pas sur un seul marché choisi après coup.
3. Le seuil est durci selon le nombre de variantes × unités de temps essayées (Bonferroni) :
   en tester beaucoup et garder la meilleure finit toujours par « trouver » un gagnant.
4. Sans les garde-fous du direct (research_risk) : chaque stratégie est jugée sur toute la période.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .execution import ExecutionParams
from .risk import RiskParams
from .robustness import MIN_TRADES, bootstrap_means, research_risk
from .strategy import StrategyParams

LAB_FILE = "laboratoire.json"
STUDY_SHARE = 0.6
MIN_MARKET_TRADES = 5
PROMISING = "prometteur"

VARIANTS: dict[str, StrategyParams] = {
    "Retour à la moyenne RSI(2) < 10": StrategyParams(),
    "Retour à la moyenne RSI(2) < 5": StrategyParams(rsi_entry=5.0),
    "Cassure 20 / 10": StrategyParams(
        strategy_type="cassure", breakout_period=20, breakout_exit_period=10, trend_period=0,
        stop_atr_mult=2.0, max_bars_in_trade=0),
    "Cassure 55 / 20": StrategyParams(
        strategy_type="cassure", breakout_period=55, breakout_exit_period=20, trend_period=0,
        stop_atr_mult=2.0, max_bars_in_trade=0),
    "Cassure 20 / 10 + tendance MM200": StrategyParams(
        strategy_type="cassure", breakout_period=20, breakout_exit_period=10, trend_period=200,
        stop_atr_mult=2.0, max_bars_in_trade=0),
    "Croisement MM 20 / 100": StrategyParams(
        strategy_type="croisement", fast_period=20, slow_period=100, trend_period=0,
        stop_atr_mult=3.0, max_bars_in_trade=0),
    "Croisement MM 50 / 200": StrategyParams(
        strategy_type="croisement", fast_period=50, slow_period=200, trend_period=0,
        stop_atr_mult=3.0, max_bars_in_trade=0),
}


@dataclass(frozen=True)
class LabRow:
    variant: str
    timeframe: str
    study_trades: int
    study_expectancy_pct: float
    trades: int  # sur la validation, comme tout ce qui suit
    win_rate: float
    expectancy_pct: float
    ci_low: float
    ci_high: float
    ci_low_adjusted: float
    markets_positive: int
    markets_judged: int
    strategy_return: float  # rendement moyen par marché
    buy_hold_return: float  # achat-conservation moyen, pour comparer
    verdict: str


def lab_verdict(trades: int, study_exp: float, exp: float, ci_low_adjusted: float, positive: int, judged: int) -> str:
    if trades < MIN_TRADES:
        return "trop peu de trades"
    if not exp > 0:
        return "perd de l'argent"
    if not study_exp > 0:
        return "instable"  # gagne sur la validation mais perdait sur l'étude
    if ci_low_adjusted > 0 and judged and positive >= 0.6 * judged:
        return PROMISING
    return "à surveiller"


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else math.nan


def evaluate_variant(
    name: str,
    params: StrategyParams,
    timeframe: str,
    datasets: dict[str, pd.DataFrame],
    execution: ExecutionParams,
    risk: RiskParams,
    n_tests: int,
) -> LabRow:
    study, valid, strategy_returns, buy_hold, per_market = [], [], [], [], []
    for df in datasets.values():
        if len(df) < params.warmup_bars + 50:
            continue
        result = run_backtest(df, params, research_risk(risk), 10_000.0, execution)
        index = result.equity.index
        cutoff = index[0] + (index[-1] - index[0]) * STUDY_SHARE
        market_valid = [100 * t.return_pct for t in result.trades if t.entry_time >= cutoff]
        study += [100 * t.return_pct for t in result.trades if t.entry_time < cutoff]
        valid += market_valid
        equity = result.equity[index >= cutoff]
        closes = df["close"][df.index >= cutoff]
        if len(equity) > 1:
            strategy_returns.append(equity.iloc[-1] / equity.iloc[0] - 1)
            buy_hold.append(closes.iloc[-1] / closes.iloc[0] - 1)
        if len(market_valid) >= MIN_MARKET_TRADES:
            per_market.append(np.mean(market_valid))
    if len(valid) >= 2:
        alpha = 0.05
        means = bootstrap_means(np.array(valid))
        ci_low, ci_high, ci_adj = (float(q) for q in np.quantile(means, [alpha / 2, 1 - alpha / 2, alpha / n_tests / 2]))
    else:
        ci_low = ci_high = ci_adj = math.nan
    exp, study_exp = _mean(valid), _mean(study)
    positive = int(sum(m > 0 for m in per_market))
    return LabRow(
        variant=name,
        timeframe=timeframe,
        study_trades=len(study),
        study_expectancy_pct=study_exp,
        trades=len(valid),
        win_rate=sum(r > 0 for r in valid) / len(valid) if valid else math.nan,
        expectancy_pct=exp,
        ci_low=ci_low,
        ci_high=ci_high,
        ci_low_adjusted=ci_adj,
        markets_positive=positive,
        markets_judged=len(per_market),
        strategy_return=_mean(strategy_returns),
        buy_hold_return=_mean(buy_hold),
        verdict=lab_verdict(len(valid), study_exp, exp, ci_adj, positive, len(per_market)),
    )


def run_lab(
    datasets_by_timeframe: dict[str, dict[str, pd.DataFrame]],
    execution: ExecutionParams,
    risk: RiskParams,
    variants: dict[str, StrategyParams] = VARIANTS,
) -> list[LabRow]:
    n_tests = len(variants) * len(datasets_by_timeframe)
    rows = [
        evaluate_variant(name, params, tf, datasets, execution, risk, n_tests)
        for tf, datasets in datasets_by_timeframe.items()
        for name, params in variants.items()
    ]
    return sorted(rows, key=lambda r: -r.expectancy_pct if not math.isnan(r.expectancy_pct) else math.inf)


def format_lab(rows: list[LabRow]) -> str:
    def pct(x: float, fmt: str) -> str:
        return "n/a" if math.isnan(x) else format(x, fmt)

    header = (
        f"{'Variante':<34}{'Unité':>6}{'Trades':>8}{'Réussite':>10}{'Espérance':>11}  {'IC 95 %':<20}"
        f"{'Marchés +':>10}{'Rendement':>11}{'Buy&hold':>10}  Verdict"
    )
    lines = [header, "-" * (len(header) + 16)]
    for r in rows:
        ci = "n/a" if math.isnan(r.ci_low) else f"[{r.ci_low:+.3f} ; {r.ci_high:+.3f}]"
        markets = f"{r.markets_positive}/{r.markets_judged}" if r.markets_judged else "n/a"
        lines.append(
            f"{r.variant:<34}{r.timeframe:>6}{r.trades:>8}{pct(100 * r.win_rate, '.1f') + ' %':>10}"
            f"{pct(r.expectancy_pct, '+.3f') + ' %':>11}  {ci:<20}{markets:>10}"
            f"{pct(100 * r.strategy_return, '+.1f') + ' %':>11}{pct(100 * r.buy_hold_return, '+.1f') + ' %':>10}  {r.verdict}"
        )
    lines += [
        "",
        f"Tout est mesuré sur la validation : les {100 - int(100 * STUDY_SHARE)} % les plus récents de chaque historique.",
        "Espérance : gain moyen par trade, frais inclus, tous marchés réunis. Marchés + : marchés où elle est positive.",
        "Rendement / Buy&hold : moyenne par marché de la stratégie et du simple achat-conservation sur la même période.",
        f"« {PROMISING} » : gagnant sur l'étude ET la validation, fourchette au-dessus de 0 avec un seuil durci",
        f"pour les {len(rows)} essais, et positif sur au moins 60 % des marchés.",
    ]
    return "\n".join(lines)


def overall_lab_verdict(rows: list[LabRow]) -> str:
    promising = [r for r in rows if r.verdict == PROMISING]
    if promising:
        best = promising[0]
        return (
            f"VERDICT : {len(promising)} structure(s) tiennent hors échantillon. La meilleure : {best.variant} en "
            f"{best.timeframe}, {best.expectancy_pct:+.3f} % par trade sur la validation.\n"
            "Prochaine étape : la faire tourner en argent fictif (réglages ci-dessous), puis en testnet."
        )
    watch = [r for r in rows if r.verdict == "à surveiller"]
    hint = f"\nLa plus proche : {watch[0].variant} en {watch[0].timeframe} (à surveiller)." if watch else ""
    return (
        f"VERDICT : aucune des {len(rows)} combinaisons testées ne tient hors échantillon.\n"
        "Ne mets pas d'argent réel, et encore moins de levier, sur ces stratégies." + hint
    )


def env_lines(params: StrategyParams) -> str:
    """Réglages à copier dans .env pour essayer une variante."""
    return "\n".join(f"{f.name.upper()}={getattr(params, f.name)}" for f in fields(params))


def save_lab(path: Path, rows: list[LabRow], verdict: str, **meta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**meta, "verdict": verdict, "rows": [asdict(r) for r in rows]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_lab(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
