"""Étude d'une opportunité du radar : ce que les mêmes mouvements ont donné dans le passé, sur la même crypto.

Le radar voit une crypto bondir (par exemple +2 % en 5 minutes). L'étude reprend 30 jours de bougies de 1 minute
de cette crypto, retrouve tous les bonds du même genre et mesure :
- la courbe du prix dans l'heure qui suit l'achat (médiane, et la moitié centrale des cas) ;
- ce qu'auraient donné trois façons de sortir, testées par le backtest du bot (mêmes règles qu'en direct, frais
  et glissement compris) : rapide, normale, laisser courir ;
- le risque d'un essai : où serait le stop, et combien coûterait le fait de le toucher.
Le verdict dit les choses comme elles sont, dans le bon comme dans le mauvais. Une seule crypto et un seul mois :
même positif, ce n'est pas une preuve, seulement une piste à essayer en argent fictif.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .execution import ExecutionParams
from .risk import RiskParams, position_size
from .robustness import research_risk
from .radar import STRONG
from .strategy import StrategyParams, compute_signals, initial_stop

STUDY_DAYS = 30  # bougies de 1 minute : environ 43 000 bougies, quelques secondes à télécharger
HORIZON = 60  # la courbe suit le prix pendant l'heure qui suit l'achat
MIN_TRADES = 20  # en dessous, l'étude ne juge pas
OPTIONS = {  # (titre, explication, règles de sortie) : seuils ronds fixés d'avance, comme dans le labo
    "rapide": ("Sortie rapide", "revend sous le plus bas des 3 dernières bougies, stop à 1,5 ATR, au plus 5 min",
               {"breakout_exit_period": 3, "stop_atr_mult": 1.5, "max_bars_in_trade": 5}),
    "normale": ("Sortie normale", "revend sous le plus bas des 5 dernières bougies, stop à 2 ATR, au plus 20 min",
                {"breakout_exit_period": 5, "stop_atr_mult": 2.0, "max_bars_in_trade": 20}),
    "longue": ("Laisser courir", "revend sous le plus bas des 15 dernières bougies, stop à 3 ATR, au plus 1 h",
               {"breakout_exit_period": 15, "stop_atr_mult": 3.0, "max_bars_in_trade": 60}),
}


def option_params(window: int, option: str) -> StrategyParams:
    """La stratégie « impulsion » qui achète le même mouvement que le radar, avec la sortie choisie (1 min)."""
    if window not in STRONG or option not in OPTIONS:
        raise ValueError(f"Fenêtre ou option inconnue : {window}, {option}")
    return StrategyParams(strategy_type="impulsion", impulse_bars=window // 60, impulse_pct=STRONG[window],
                          trend_period=0, atr_period=14, **OPTIONS[option][2])


def round_trip_cost(execution: ExecutionParams) -> float:
    """Ce que coûte un aller-retour au marché : frais à l'achat et à la vente, glissement des deux côtés."""
    return 2 * (execution.fee_rate + execution.slippage)


def entry_events(df: pd.DataFrame, window: int) -> np.ndarray:
    """Les bougies où le mouvement apparaît (le signal de la stratégie, exactement comme en direct)."""
    signals = compute_signals(df, option_params(window, "normale"))
    return np.flatnonzero(signals["entry"].to_numpy())


def paths_after(df: pd.DataFrame, events: np.ndarray, horizon: int = HORIZON) -> np.ndarray:
    """Pour chaque mouvement : achat à l'ouverture suivante, puis variation à chaque clôture pendant `horizon` min."""
    opens, closes = df["open"].to_numpy(), df["close"].to_numpy()
    rows = [closes[i + 1:i + 1 + horizon] / opens[i + 1] - 1 for i in events if i + horizon < len(df)]
    return np.array(rows) if rows else np.empty((0, horizon))


def trade_plan(price: float, atr: float, window: int, option: str, equity: float, risk: RiskParams,
               execution: ExecutionParams) -> dict | None:
    """L'essai tel qu'il serait passé maintenant : prix, stop, quantité, et ce que coûterait le stop."""
    if not (price > 0 and atr > 0 and equity > 0):
        return None
    params = option_params(window, option)
    entry = price * (1 + execution.slippage)
    stop = initial_stop(entry, atr, params)
    qty = position_size(equity, entry, stop, risk)
    if stop <= 0 or qty <= 0:
        return None
    notional = qty * entry
    exit_at_stop = stop * (1 - execution.slippage)
    loss = notional * (1 + execution.fee_rate) - qty * exit_at_stop * (1 - execution.fee_rate)
    return {"price": price, "entry": entry, "stop": stop, "stop_pct": stop / entry - 1, "qty": qty,
            "notional": notional, "loss_if_stop": loss, "loss_pct": loss / equity, "equity": equity}


def summarize(returns: list[float], gross: list[float]) -> dict:
    values = np.array(returns)
    n = len(values)
    out = {"trades": n, "winners": float((values > 0).mean()) if n else None,
           "mean": float(values.mean()) if n else None, "gross_mean": float(np.mean(gross)) if gross else None,
           "median": float(np.median(values)) if n else None, "worst": float(values.min()) if n else None,
           "best": float(values.max()) if n else None, "ci_low": None, "ci_high": None}
    if n >= 2:
        half = 1.96 * values.std(ddof=1) / math.sqrt(n)  # fourchette à 95 % de la moyenne
        out["ci_low"], out["ci_high"] = float(values.mean() - half), float(values.mean() + half)
    return out


def pct(x: float, sign: bool = True) -> str:
    """Une fraction en pourcentage à la française : 0.0123 -> « +1,23 % »."""
    return f"{100 * x:{'+' if sign else ''}.2f} %".replace(".", ",")


def verdict(option: dict, cost: float, days: int) -> dict:
    """Le verdict, en clair, sur l'option « normale » : bon, mauvais ou rien de net."""
    n, mean = option["trades"], option["mean"]
    if n < MIN_TRADES:
        return {"kind": "few", "text": f"Trop peu de mouvements de ce genre sur {days} jours ({n} trades) pour en "
                                       "juger : impossible de distinguer une opportunité d'un coup de chance."}
    if option["ci_high"] < 0:
        return {"kind": "bad", "text": f"Dans le passé, acheter ce genre de mouvement a perdu nettement : {pct(mean)} "
                                       "par trade en moyenne, frais compris (un aller-retour coûte environ "
                                       f"{pct(cost, sign=False)}). Ce n'est pas une opportunité."}
    if option["ci_low"] > 0:
        return {"kind": "good", "text": f"Dans le passé, positif après frais : {pct(mean)} par trade en moyenne, "
                                        f"au-delà du hasard sur ces {days} jours. Attention : une seule crypto, un "
                                        "seul mois, et tu en regardes beaucoup (sur 20, une sortira positive par "
                                        "chance). À confirmer en argent fictif avant tout."}
    return {"kind": "neutral", "text": f"Rien de net : en moyenne {pct(mean)} par trade après frais, et la "
                                       f"fourchette va de {pct(option['ci_low'])} à {pct(option['ci_high'])}. Le "
                                       "plus probable : on paie surtout des frais."}


def study(df: pd.DataFrame, window: int, execution: ExecutionParams, risk: RiskParams, equity: float = 1000.0,
          price: float | None = None) -> dict:
    """L'étude complète d'un mouvement (fenêtre en secondes : 60, 300 ou 900) sur des bougies de 1 minute."""
    if window not in STRONG:
        raise ValueError(f"Fenêtre inconnue : {window}")
    if len(df) < 200:
        raise ValueError("Pas assez de bougies de 1 minute pour étudier cette crypto.")
    execution = replace(execution, order_type="market")  # un essai sur un mouvement s'achète au marché
    cost = round_trip_cost(execution)
    paths = paths_after(df, entry_events(df, window))
    path = None
    if len(paths):
        q25, median, q75 = np.percentile(paths, [25, 50, 75], axis=0)
        path = {"minutes": list(range(1, paths.shape[1] + 1)), "median": median.tolist(), "q25": q25.tolist(),
                "q75": q75.tolist()}
    atr = float(compute_signals(df.iloc[-200:], option_params(window, "normale"))["atr"].iloc[-1])
    last = float(price or df["close"].iloc[-1])
    options = []
    for key, (title, description, _) in OPTIONS.items():
        result = run_backtest(df, option_params(window, key), research_risk(risk), 10_000.0, execution)
        trades = [t for t in result.trades if t.reason != "fin du test"]
        options.append({"key": key, "title": title, "description": description,
                        **summarize([t.return_pct for t in trades], [t.gross_return for t in trades]),
                        "plan": trade_plan(last, atr, window, key, equity, risk, execution)})
    days = max(1, round((df.index[-1] - df.index[0]).total_seconds() / 86_400))
    return {
        "window": window, "threshold": STRONG[window], "days": days, "bars": len(df), "events": int(len(paths)),
        "from": df.index[0].isoformat(), "to": df.index[-1].isoformat(), "cost": cost, "path": path,
        "options": options, "verdict": verdict(options[1], cost, days),
    }
