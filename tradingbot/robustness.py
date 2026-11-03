"""Tests de robustesse : l'avantage vu en backtest est-il réel, ou dû à la chance ?

Trois garde-fous statistiques :
- intervalle de confiance (bootstrap) sur l'espérance par trade : s'il contient 0, le gain
  observé peut s'expliquer par le hasard ;
- régularité dans le temps : l'historique est coupé en sous-périodes, un avantage réel doit
  gagner dans la plupart d'entre elles, pas seulement dans une bonne passe ;
- correction des comparaisons multiples (Bonferroni) : tester 15 marchés et garder le meilleur
  finit toujours par « trouver » un gagnant ; le seuil devient donc plus strict avec le nombre
  de marchés testés.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from .backtest import BacktestResult
from .risk import RiskParams

MIN_TRADES = 30
MIN_TRADES_PER_PERIOD = 5
ROBUST = "robuste"


def research_risk(risk: RiskParams) -> RiskParams:
    """Sans les garde-fous du direct : une étude juge la stratégie sur toute la période.

    En direct, l'arrêt après -15 % protège l'argent. En étude, il couperait les trades dès qu'une
    stratégie perd, et ne laisserait juger qu'un bout de l'historique.
    """
    return replace(risk, daily_loss_limit=1.0, max_drawdown=1.0)


def bootstrap_means(values: np.ndarray, n_resamples: int = 20_000, seed: int = 0, chunk: int = 1_000) -> np.ndarray:
    """Moyennes de `n_resamples` rééchantillonnages avec remise (par blocs pour limiter la mémoire)."""
    rng = np.random.default_rng(seed)
    return np.concatenate(
        [
            rng.choice(values, size=(min(chunk, n_resamples - start), len(values))).mean(axis=1)
            for start in range(0, n_resamples, chunk)
        ]
    )


def period_means(result: BacktestResult, n_periods: int) -> list[float]:
    """Espérance (%) des trades ouverts dans chaque sous-période ; NaN si moins de 5 trades."""
    index = result.equity.index
    start, span = index[0], index[-1] - index[0]
    buckets: list[list[float]] = [[] for _ in range(n_periods)]
    for trade in result.trades:
        k = min(int((trade.entry_time - start) / span * n_periods), n_periods - 1) if span else 0
        buckets[k].append(trade.return_pct)
    return [100 * float(np.mean(b)) if len(b) >= MIN_TRADES_PER_PERIOD else math.nan for b in buckets]


@dataclass(frozen=True)
class RobustnessRow:
    market: str
    nb_trades: int
    win_rate: float
    expectancy_pct: float
    ci_low: float  # IC 95 % de l'espérance par trade, en %
    ci_high: float
    ci_low_adjusted: float  # borne basse corrigée pour le nombre de marchés testés
    period_means: tuple[float, ...]
    total_return: float
    verdict: str

    @property
    def periods_label(self) -> str:
        judged = [p for p in self.period_means if not math.isnan(p)]
        return f"{sum(p > 0 for p in judged)}/{len(judged)}" if judged else "n/a"


def verdict_for(nb_trades: int, expectancy_pct: float, ci_low_adjusted: float, periods: list[float]) -> str:
    if nb_trades < MIN_TRADES:
        return "trop peu de trades"
    if not expectancy_pct > 0:
        return "perd de l'argent"
    judged = [p for p in periods if not math.isnan(p)]
    regular = len(judged) >= 2 and sum(p > 0 for p in judged) >= 0.75 * len(judged)
    if ci_low_adjusted > 0 and regular:
        return ROBUST
    return "positif, peut-être de la chance"


def evaluate(market: str, result: BacktestResult, n_tests: int, n_periods: int = 4, seed: int = 0) -> RobustnessRow:
    returns = 100 * np.array([t.return_pct for t in result.trades])
    alpha = 0.05
    if len(returns) >= 2:
        means = bootstrap_means(returns, seed=seed)
        ci_low, ci_high, ci_low_adj = np.quantile(means, [alpha / 2, 1 - alpha / 2, alpha / max(n_tests, 1) / 2])
    else:
        ci_low = ci_high = ci_low_adj = math.nan
    periods = period_means(result, n_periods)
    m = result.metrics
    return RobustnessRow(
        market=market,
        nb_trades=len(returns),
        win_rate=m["taux_reussite"],
        expectancy_pct=m["esperance_pct"],
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        ci_low_adjusted=float(ci_low_adj),
        period_means=tuple(periods),
        total_return=m["rendement_total"],
        verdict=verdict_for(len(returns), m["esperance_pct"], float(ci_low_adj), periods),
    )


def format_robustness(rows: list[RobustnessRow], n_periods: int) -> str:
    def pct(x: float, fmt: str) -> str:
        return "n/a" if math.isnan(x) else format(x, fmt)

    header = (
        f"{'Marché':<16}{'Trades':>7}{'Réussite':>10}{'Espérance':>11}  {'IC 95 %':<20}"
        f"{'Périodes +':>11}{'Rendement':>11}  Verdict"
    )
    lines = [header, "-" * (len(header) + 20)]
    for r in rows:
        ci = "n/a" if math.isnan(r.ci_low) else f"[{r.ci_low:+.3f} ; {r.ci_high:+.3f}]"
        win = pct(100 * r.win_rate, ".1f")
        lines.append(
            f"{r.market:<16}{r.nb_trades:>7}{win + ' %':>10}{pct(r.expectancy_pct, '+.3f') + ' %':>11}  {ci:<20}"
            f"{r.periods_label:>11}{pct(100 * r.total_return, '+.1f') + ' %':>11}  {r.verdict}"
        )
    lines += [
        "",
        "Espérance : gain moyen par trade, frais inclus.",
        "IC 95 % : fourchette probable de l'espérance réelle. Si elle contient 0, le gain peut venir du hasard.",
        f"Périodes + : sous-périodes (sur {n_periods}, celles avec au moins {MIN_TRADES_PER_PERIOD} trades) "
        "où la stratégie a gagné de l'argent.",
        "« robuste » : la fourchette reste au-dessus de 0 avec un seuil durci selon le nombre de marchés testés,",
        "et la stratégie gagne dans au moins 3 sous-périodes sur 4.",
    ]
    return "\n".join(lines)


def save_results(path: Path, rows: list[RobustnessRow], verdict: str, **meta) -> None:
    """Dernier test de robustesse, relu par le tableau de bord."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**meta, "verdict": verdict, "rows": [asdict(r) for r in rows]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_results(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def overall_verdict(rows: list[RobustnessRow]) -> str:
    robust = [r.market for r in rows if r.verdict == ROBUST]
    if not rows:
        return "VERDICT : aucun marché n'a pu être testé."
    if not robust:
        return (
            f"VERDICT : aucun des {len(rows)} marchés testés ne montre un avantage solide.\n"
            "Ne mets pas d'argent réel sur ces réglages."
        )
    return (
        f"VERDICT : {len(robust)} marché(s) sur {len(rows)} montrent un avantage solide : {', '.join(robust)}.\n"
        "Le seuil tient déjà compte du nombre de marchés testés. Étape suivante : plusieurs semaines\n"
        "en testnet sur ce(s) marché(s) uniquement. Les performances passées ne garantissent rien."
    )
