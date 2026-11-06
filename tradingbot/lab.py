"""Laboratoire : plusieurs familles de stratégies, testées sur plusieurs marchés, validées hors échantillon.

Méthode, pour ne pas se laisser tromper par la chance :
1. Chaque historique est coupé dans le temps : la première moitié sert d'« étude », la tranche suivante
   (de 50 à 80 %) de « validation », et les 20 % les plus récents de « test final ». La validation classe
   les variantes ; le test final, jamais regardé pour les choisir, doit confirmer : sans lui, essayer
   idée après idée sur les mêmes données finirait par en trouver une qui a gagné par hasard.
2. Une variante est jugée sur tous les marchés à la fois (trades mis en commun) : une structure
   qui marche doit marcher un peu partout, pas sur un seul marché choisi après coup.
3. Le seuil est durci selon le nombre de variantes × unités de temps essayées (Bonferroni) :
   en tester beaucoup et garder la meilleure finit toujours par « trouver » un gagnant.
4. Sans les garde-fous du direct (research_risk) : chaque stratégie est jugée sur toute la période.
"""
from __future__ import annotations

import json
import logging
import math
import os
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .execution import ExecutionParams
from .risk import RiskParams
from .robustness import MIN_TRADES, adjusted_lower_bound, bootstrap_means, research_risk
from .research import RESEARCH_VARIANTS
from .strategy import StrategyParams

log = logging.getLogger(__name__)

LAB_FILE = "laboratoire.json"
SHORT_LAB_FILE = "laboratoire-court-terme.json"
LIMIT_LAB_FILE = "laboratoire-court-terme-limites.json"
FUTURES_LAB_FILE = "laboratoire-futures.json"  # scalping avec les frais des contrats à terme (argent fictif)
LAB_FILES = (  # (fichier, titre sur le tableau de bord)
    (LAB_FILE, "Laboratoire long terme"),
    (SHORT_LAB_FILE, "Laboratoire court terme"),
    (LIMIT_LAB_FILE, "Laboratoire court terme, ordres limites"),
    (FUTURES_LAB_FILE, "Laboratoire scalping, frais futures"),
)
STUDY_SHARE = 0.5  # étude : la première moitié de chaque historique
TEST_SHARE = 0.2  # test final : les 20 % les plus récents ; la validation est entre les deux
MIN_MARKET_TRADES = 5
MIN_TEST_TRADES = 10
PROMISING = "prometteur"

TREND = {"stop_atr_mult": 3.0, "max_bars_in_trade": 0}  # suivre une tendance : stop large, pas de stop temporel
TURTLE = {"strategy_type": "cassure", "stop_atr_mult": 2.0, "max_bars_in_trade": 0}

VARIANTS: dict[str, StrategyParams] = {
    # Acheter un repli : stop à 2,5 ATR, stop temporel de 24 bougies.
    "Repli RSI(2) < 10 + MM200": StrategyParams(),
    "Repli RSI(2) < 5 + MM200": StrategyParams(rsi_entry=5.0),
    "Repli RSI(14) < 30 + MM200": StrategyParams(rsi_period=14, rsi_entry=30.0),
    "Repli RSI(2) < 10 sans filtre": StrategyParams(trend_period=0),
    "Bollinger rebond 20/2 + MM200": StrategyParams(strategy_type="bollinger"),
    "Bollinger rebond 20/2,5 + MM200": StrategyParams(strategy_type="bollinger", bb_std=2.5),
    "Bollinger rebond 20/2 sans filtre": StrategyParams(strategy_type="bollinger", trend_period=0),
    # Suivre une tendance.
    "Bollinger cassure 20/2": StrategyParams(strategy_type="bollinger_cassure", trend_period=0, **TREND),
    "Bollinger cassure 20/2 + MM200": StrategyParams(strategy_type="bollinger_cassure", **TREND),
    "Cassure 20/10": StrategyParams(breakout_period=20, breakout_exit_period=10, trend_period=0, **TURTLE),
    "Cassure 55/20": StrategyParams(breakout_period=55, breakout_exit_period=20, trend_period=0, **TURTLE),
    "Cassure 100/50": StrategyParams(breakout_period=100, breakout_exit_period=50, trend_period=0, **TURTLE),
    "Cassure 20/10 + MM200": StrategyParams(breakout_period=20, breakout_exit_period=10, **TURTLE),
    "Croisement MM 10/50": StrategyParams(strategy_type="croisement", fast_period=10, slow_period=50,
                                          trend_period=0, **TREND),
    "Croisement MM 20/100": StrategyParams(strategy_type="croisement", fast_period=20, slow_period=100,
                                           trend_period=0, **TREND),
    "Croisement MM 50/200": StrategyParams(strategy_type="croisement", fast_period=50, slow_period=200,
                                           trend_period=0, **TREND),
    "MACD 12/26/9": StrategyParams(strategy_type="macd", trend_period=0, **TREND),
    "MACD 12/26/9 + MM200": StrategyParams(strategy_type="macd", **TREND),
    "Momentum 50": StrategyParams(strategy_type="momentum", momentum_period=50, trend_period=0, **TREND),
    "Momentum 100": StrategyParams(strategy_type="momentum", momentum_period=100, trend_period=0, **TREND),
    "Momentum 200": StrategyParams(strategy_type="momentum", momentum_period=200, trend_period=0, **TREND),
    "Supertrend 10/2": StrategyParams(strategy_type="supertrend", st_period=10, st_mult=2.0, trend_period=0, **TREND),
    "Supertrend 10/3": StrategyParams(strategy_type="supertrend", st_period=10, st_mult=3.0, trend_period=0, **TREND),
    "Supertrend 20/3": StrategyParams(strategy_type="supertrend", st_period=20, st_mult=3.0, trend_period=0, **TREND),
    # Les règles tirées d'études de finance (tradingbot/research.py) : réglages fixés d'après les études, pas d'après
    # nos données (momentum de 1 et 4 semaines, prix au-dessus de sa moyenne mobile...).
    **RESEARCH_VARIANTS,
}

# Combinaisons pour le très court terme, où un aller-retour coûte environ 0,3 % (frais + glissement).
# Seuils fixés d'avance, pas ajustés sur les données : n'acheter que quand une bougie bouge en moyenne d'au
# moins ce coût (ATR >= 0,3 % du prix), ou quand le volume double (le mouvement a des acheteurs derrière lui).
VOLATILE = {"min_atr_pct": 0.003}
CROWD = {"volume_mult": 2.0}
ACTIVE = {"active_hours": "13-21"}
SQUEEZE = {"squeeze_quantile": 0.2, "squeeze_period": 120}
COMBOS: dict[str, StrategyParams] = {
    "Cassure 20/10 + volatilité": StrategyParams(breakout_period=20, breakout_exit_period=10, trend_period=0,
                                                 **TURTLE, **VOLATILE),
    "Cassure 20/10 + volume x2": StrategyParams(breakout_period=20, breakout_exit_period=10, trend_period=0,
                                                **TURTLE, **CROWD),
    "Cassure 55/20 + volatilité + volume": StrategyParams(breakout_period=55, breakout_exit_period=20,
                                                          trend_period=0, **TURTLE, **VOLATILE, **CROWD),
    "Bollinger cassure 20/2 + volatilité": StrategyParams(strategy_type="bollinger_cassure", trend_period=0,
                                                          **TREND, **VOLATILE),
    "Bollinger cassure 20/2 + volume x2": StrategyParams(strategy_type="bollinger_cassure", trend_period=0,
                                                         **TREND, **CROWD),
    "Supertrend 10/3 + volatilité": StrategyParams(strategy_type="supertrend", trend_period=0, **TREND, **VOLATILE),
    "Supertrend 10/3 + volume x2": StrategyParams(strategy_type="supertrend", trend_period=0, **TREND, **CROWD),
    "Momentum 50 + volume x2": StrategyParams(strategy_type="momentum", momentum_period=50, trend_period=0,
                                              **TREND, **CROWD),
    "MACD 12/26/9 + MM200 + volume x2": StrategyParams(strategy_type="macd", **TREND, **CROWD),
    "Croisement MM 20/100 + volatilité": StrategyParams(strategy_type="croisement", fast_period=20, slow_period=100,
                                                        trend_period=0, **TREND, **VOLATILE),
    "Repli RSI(2) < 5 + MM200 + volatilité": StrategyParams(rsi_entry=5.0, **VOLATILE),
    "Bollinger rebond 20/2,5 + volatilité": StrategyParams(strategy_type="bollinger", bb_std=2.5, **VOLATILE),
    # Heures actives : de 13 h à 21 h UTC, quand l'Europe et les États-Unis échangent en même temps.
    # Compression : la bougie d'avant avait des bandes parmi les 20 % les plus serrées des 120 dernières.
    "Cassure 20/10 + heures actives": StrategyParams(breakout_period=20, breakout_exit_period=10, trend_period=0,
                                                     **TURTLE, **ACTIVE),
    "Supertrend 10/3 + heures actives": StrategyParams(strategy_type="supertrend", trend_period=0, **TREND, **ACTIVE),
    "Bollinger rebond 20/2,5 + MM200 + heures actives": StrategyParams(strategy_type="bollinger", bb_std=2.5,
                                                                       **ACTIVE),
    "Cassure 20/10 + compression": StrategyParams(breakout_period=20, breakout_exit_period=10, trend_period=0,
                                                  **TURTLE, **SQUEEZE),
    "Bollinger cassure 20/2 + compression": StrategyParams(strategy_type="bollinger_cassure", trend_period=0,
                                                           **TREND, **SQUEEZE),
}
# Sauter sur un mouvement soudain : seuils ronds fixés d'avance, pas ajustés sur les
# données. Revente sous le plus bas des 5 bougies précédentes, stop à 2 ATR, et au plus 20 bougies en position.
JUMP = {"strategy_type": "impulsion", "trend_period": 0, "breakout_exit_period": 5, "stop_atr_mult": 2.0,
        "max_bars_in_trade": 20}
IMPULSES: dict[str, StrategyParams] = {
    "Impulsion +1 % en 5 bougies": StrategyParams(impulse_bars=5, impulse_pct=0.01, **JUMP),
    "Impulsion +1 % en 5 bougies + volume x3": StrategyParams(impulse_bars=5, impulse_pct=0.01, volume_mult=3.0,
                                                             **JUMP),
    "Impulsion +0,5 % en 1 bougie + volume x3": StrategyParams(impulse_bars=1, impulse_pct=0.005, volume_mult=3.0,
                                                              **JUMP),
    "Impulsion +3 % en 15 bougies + volume x3": StrategyParams(impulse_bars=15, impulse_pct=0.03, volume_mult=3.0,
                                                              **JUMP),
}
SHORT_TERM_VARIANTS: dict[str, StrategyParams] = {**VARIANTS, **COMBOS, **IMPULSES}  # labo court terme
ALL_VARIANTS: dict[str, StrategyParams] = SHORT_TERM_VARIANTS  # pour retrouver une variante par son nom


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
    gross_expectancy_pct: float = math.nan  # ce que la stratégie capte sur le prix, avant frais et glissement
    test_trades: int = 0  # test final : les 20 % les plus récents, qui confirment ou non la validation
    test_expectancy_pct: float = math.nan


def lab_verdict(trades: int, study_exp: float, exp: float, ci_low_adjusted: float, positive: int, judged: int,
                test_trades: int = 0, test_exp: float = math.nan) -> str:
    if trades < MIN_TRADES:
        return "trop peu de trades"
    if not exp > 0:
        return "perd de l'argent"
    if not study_exp > 0:
        return "instable"  # gagne sur la validation mais perdait sur l'étude
    confirmed = test_trades >= MIN_TEST_TRADES
    if confirmed and not test_exp > 0:
        return "instable"  # gagnait sur l'étude et la validation, mais perd sur le test final
    if ci_low_adjusted > 0 and judged and positive >= 0.6 * judged and confirmed:
        return PROMISING
    return "à surveiller"


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else math.nan


@dataclass
class MarketOutcome:
    """Ce qu'une variante a donné sur un marché : rendements par trade (%) de chaque tranche de l'historique."""
    study: list[float]
    valid: list[float]
    test: list[float]
    gross: list[float]  # avant frais, sur la validation
    strategy_return: float | None  # sur la validation
    buy_hold_return: float | None


def market_outcome(df: pd.DataFrame, params: StrategyParams, execution: ExecutionParams,
                   risk: RiskParams) -> MarketOutcome | None:
    if len(df) < params.warmup_bars + 50:
        return None
    result = run_backtest(df, params, research_risk(risk), 10_000.0, execution)
    index = result.equity.index
    cutoff = index[0] + (index[-1] - index[0]) * STUDY_SHARE
    test_start = index[0] + (index[-1] - index[0]) * (1 - TEST_SHARE)
    in_valid = [t for t in result.trades if cutoff <= t.entry_time < test_start]
    window = (index >= cutoff) & (index < test_start)
    equity = result.equity[window]
    closes = df["close"][(df.index >= cutoff) & (df.index < test_start)]
    enough = len(equity) > 1
    return MarketOutcome(
        study=[100 * t.return_pct for t in result.trades if t.entry_time < cutoff],
        valid=[100 * t.return_pct for t in in_valid],
        test=[100 * t.return_pct for t in result.trades if t.entry_time >= test_start],
        gross=[100 * t.gross_return for t in in_valid],
        strategy_return=float(equity.iloc[-1] / equity.iloc[0] - 1) if enough else None,
        buy_hold_return=float(closes.iloc[-1] / closes.iloc[0] - 1) if enough else None,
    )


def combine(name: str, timeframe: str, outcomes: list[MarketOutcome | None], n_tests: int) -> LabRow:
    """Une ligne du labo : les trades de tous les marchés réunis, dans l'ordre des marchés."""
    study, valid, test, gross, strategy_returns, buy_hold, per_market = [], [], [], [], [], [], []
    for o in outcomes:
        if o is None:
            continue
        study += o.study
        valid += o.valid
        test += o.test
        gross += o.gross
        if o.strategy_return is not None:
            strategy_returns.append(o.strategy_return)
            buy_hold.append(o.buy_hold_return)
        if len(o.valid) >= MIN_MARKET_TRADES:
            per_market.append(np.mean(o.valid))
    if len(valid) >= 2:
        ci_low, ci_high = (float(q) for q in np.quantile(bootstrap_means(np.array(valid), n_resamples=10_000), [0.025, 0.975]))
    else:
        ci_low = ci_high = math.nan
    ci_adj = adjusted_lower_bound(np.array(valid), n_tests)
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
        verdict=lab_verdict(len(valid), study_exp, exp, ci_adj, positive, len(per_market), len(test), _mean(test)),
        gross_expectancy_pct=_mean(gross),
        test_trades=len(test),
        test_expectancy_pct=_mean(test),
    )


def evaluate_variant(
    name: str,
    params: StrategyParams,
    timeframe: str,
    datasets: dict[str, pd.DataFrame],
    execution: ExecutionParams,
    risk: RiskParams,
    n_tests: int,
) -> LabRow:
    return combine(name, timeframe, [market_outcome(df, params, execution, risk) for df in datasets.values()], n_tests)


def _market_job(job: tuple) -> dict[str, MarketOutcome | None]:
    """Toutes les variantes sur un marché : la tâche envoyée à chaque cœur du processeur."""
    df, variants, execution, risk = job
    return {name: market_outcome(df, params, execution, risk) for name, params in variants.items()}


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)  # un cœur reste libre pour que l'ordinateur réponde


def run_lab(
    datasets_by_timeframe: dict[str, dict[str, pd.DataFrame]],
    execution: ExecutionParams,
    risk: RiskParams,
    variants: dict[str, StrategyParams] = VARIANTS,
    workers: int | None = None,
) -> list[LabRow]:
    """Chaque (unité, marché) est calculé à part, sur plusieurs cœurs si possible : mêmes résultats qu'en série."""
    n_tests = len(variants) * len(datasets_by_timeframe)
    jobs = [(tf, market) for tf, group in datasets_by_timeframe.items() for market in group]
    workers = default_workers() if workers is None else max(1, workers)
    outcomes: dict[tuple[str, str], dict] = {}
    if workers > 1 and len(jobs) > 1:
        try:
            with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
                futures = {
                    pool.submit(_market_job, (datasets_by_timeframe[tf][m], variants, execution, risk)): (tf, m)
                    for tf, m in jobs
                }
                for done, future in enumerate(as_completed(futures), start=1):
                    outcomes[futures[future]] = future.result()
                    log.info("Labo : %d/%d marchés calculés (%d cœurs)", done, len(jobs), min(workers, len(jobs)))
        except (OSError, RuntimeError, BrokenProcessPool, pickle.PicklingError) as exc:
            log.warning("Calcul en parallèle impossible (%s) : le labo continue sur un seul cœur.", exc)
            outcomes = {}
    for done, (tf, m) in enumerate(jobs, start=1):
        if (tf, m) not in outcomes:
            outcomes[(tf, m)] = _market_job((datasets_by_timeframe[tf][m], variants, execution, risk))
            log.info("Labo : %d/%d marchés calculés", done, len(jobs))
    rows = [
        combine(name, tf, [outcomes[(tf, m)][name] for m in datasets_by_timeframe[tf]], n_tests)
        for tf in datasets_by_timeframe
        for name in variants
    ]
    return sorted(rows, key=lambda r: -r.expectancy_pct if not math.isnan(r.expectancy_pct) else math.inf)


def format_lab(rows: list[LabRow]) -> str:
    """Tableau pour la console : assez étroit pour une fenêtre Windows (le détail complet est sur le tableau de bord)."""
    def pct(x: float, fmt: str = "+.3f") -> str:
        return "n/a" if math.isnan(x) else format(x, fmt) + " %"

    width = max([34, *(len(r.variant) + 1 for r in rows)])
    header = (
        f"{'Variante':<{width}}{'Unité':>6}{'Trades':>8}{'Réussite':>10}{'Avant frais':>13}{'Après frais':>13}"
        f"{'Test final':>12}{'Marchés +':>11}  Verdict"
    )
    lines = [header, "-" * (len(header) + 18)]
    for r in rows:
        markets = f"{r.markets_positive}/{r.markets_judged}" if r.markets_judged else "n/a"
        test = pct(r.test_expectancy_pct) if r.test_trades else "n/a"
        lines.append(
            f"{r.variant:<{width}}{r.timeframe:>6}{r.trades:>8}{pct(100 * r.win_rate, '.1f'):>10}"
            f"{pct(r.gross_expectancy_pct):>13}{pct(r.expectancy_pct):>13}{test:>12}{markets:>11}  {r.verdict}"
        )
    holds = {}
    for r in rows:  # même période et mêmes marchés pour toutes les variantes d'une unité
        if not math.isnan(r.buy_hold_return):
            holds.setdefault(r.timeframe, r.buy_hold_return)
    lines += [
        "",
        f"Validation : de {int(100 * STUDY_SHARE)} à {int(100 * (1 - TEST_SHARE))} % de chaque historique. Test final : les "
        f"{int(100 * TEST_SHARE)} % les plus récents, jamais regardés pour choisir : ils confirment, ou non.",
        "Avant frais : ce que la stratégie capte sur le prix. Après frais : le gain moyen par trade, frais et glissement",
        "compris, tous marchés réunis. L'écart entre les deux est le coût d'un aller-retour. Marchés + : marchés gagnants.",
        f"« {PROMISING} » : gagnant sur l'étude, la validation (seuil durci pour les {len(rows)} essais, au moins 60 % des",
        "marchés) et le test final.",
    ]
    if holds:
        lines.append("Garder simplement les cryptos sur la même période (buy & hold) : "
                     + ", ".join(f"{tf} {100 * h:+.1f} %" for tf, h in holds.items()) + ".")
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
        "Ne mets pas d'argent réel, et encore moins de levier, sur ces stratégies." + hint + cost_diagnosis(rows)
    )


def cost_diagnosis(rows: list[LabRow]) -> str:
    """Les frais sont-ils le problème ? Compare le meilleur gain avant frais au coût d'un aller-retour."""
    judged = [r for r in rows if r.trades >= MIN_TRADES and not math.isnan(r.gross_expectancy_pct)]
    if not judged:
        return ""
    best = max(judged, key=lambda r: r.gross_expectancy_pct)
    cost = best.gross_expectancy_pct - best.expectancy_pct
    line = (f"\nAvant frais, la meilleure capte {best.gross_expectancy_pct:+.3f} % par trade ({best.variant} en "
            f"{best.timeframe}) ; un aller-retour lui coûte {cost:.3f} %.")
    if best.gross_expectancy_pct <= 0:
        return line + "\nMême sans aucun frais, rien ne gagne : changer de plateforme n'y changerait rien."
    if best.expectancy_pct <= 0:
        return line + (f"\nCe sont les frais qui la font perdre. Attention : c'est la meilleure de {len(rows)} essais, "
                       "son gain avant frais peut aussi venir du hasard.")
    return line


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
