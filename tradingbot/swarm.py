"""L'essaim : des centaines de bots en argent fictif, sur les cryptos qui bougent le plus, retestés en continu.

Comment il travaille, sans jamais s'arrêter :
1. Les cryptos : toutes les 10 minutes, les N paires USDT les plus agitées sur 24 h (au moins 5 M$ échangés par jour,
   sans monnaies stables ni tokens à levier). Une crypto qui sort de la liste, ou dont l'amplitude sur 24 h tombe sous
   le seuil (« pas assez de mouvement »), passe en veille : ses bots n'ouvrent plus de trade, ils gèrent ceux en cours.
2. Le labo en direct : chaque crypto est retestée toutes les 3 heures, et dès qu'elle entre dans la liste. Toutes les
   techniques de la bibliothèque, à l'achat et à la vente à découvert, avec quatre façons de sortir (par la règle,
   objectif 2R, stop suiveur, objectif 2R + stop sécurisé), sur cinq unités de temps (1 min à 4 h), sur l'historique
   récent, frais des contrats à terme compris. Une combinaison peut devenir un bot si elle gagne sur l'étude et sur
   la validation, avec assez de trades. Le test final (les derniers 20 % de l'historique) n'est jamais regardé pour
   choisir : il mesure ce que vaut le choix. Au plus K bots par crypto, des techniques et des unités variées. Les
   tests tournent à part (un fil pour télécharger, un processus pour calculer) : le direct n'attend jamais.
3. Les bots : le même moteur que le backtest (fleet.Book), avec tout leur capital fictif à chaque trade et le levier
   de leur horizon, réduit si le stop est loin. Un bot garde sa place d'un test à l'autre (un classement qui bouge ne
   l'arrête plus) : il n'est arrêté que s'il est liquidé, à moitié ruiné, nettement perdant après 20 trades (sa
   combinaison est alors mise de côté 24 h), ou si sa stratégie est recalée.
4. Les agents : pour chaque bot, dans quelles conditions sa stratégie a gagné ou perdu dans le backtest (tendance de
   fond, volatilité, RSI, volume, heure), sa probabilité de gain dans les conditions du moment, et après chaque trade
   réel, pourquoi il a gagné ou perdu. Ce sont des mesures, jamais des ordres : un bot n'entre que sur le signal de sa
   règle testée. « Apprendre », c'est le re-test continu sur des données fraîches, pas des réglages changés après une
   perte (c'est ainsi qu'on finit par sur-ajuster le passé).
5. La mesure à l'essai : à chaque test, les trades de TOUTES les combinaisons (pas seulement des bots choisis) sont
   comptés par stratégie (une technique dans une unité de temps, toutes cryptos réunies), une seule fois, et seulement
   s'ils ont été ouverts pendant que la crypto bougeait. Aucun choix préalable : rien ne peut embellir cette mesure.
   C'est elle qui juge : après 7 jours, une stratégie nettement gagnante (fourchette qui compare les journées entre
   elles, seuil durci par le nombre de stratégies) est « prouvée » et passe en priorité aux tests ; une stratégie
   nettement perdante est « recalée » : les tests ne la prennent plus et ses bots s'arrêtent après leur trade.
6. Le classement en direct : chaque trade fini d'un bot compte aussi pour sa stratégie (tout le direct, 7 jours,
   aujourd'hui) : c'est ce que les bots choisis ont vraiment fait, à côté de la mesure à l'essai.

Argent fictif seulement : rien ne part jamais sur une plateforme.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import pickle
import queue
import threading
import time
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeout
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

from .broker import atomic_write
from .data import fetch_history, ohlcv_to_frame, timeframe_to_ms
from .execution import FUTURES, ExecutionParams
from .explain import pct, price as fmt_price, read_chart
from .fleet import (
    EXITS, LOCK_FILE, MIN_PART_TRADES, SIDE_HINTS, SIDE_LABELS, SIDES, Book, Spec, _iso, _position_view, condition,
    entry_rule, exit_rule, finite, load_json, lookback_for, save_json, signals_for, simulate, spec_from, technique,
    tf_label,
)
from .indicators import atr, rsi, sma
from .notify import ALERT
from .risk import TradeStats, clustered_bounds, elimination_reason
from .scanner import liquid_markets

log = logging.getLogger(__name__)

SWARM_FILE = "essaim.json"  # le résumé que lit le site, réécrit à chaque tour
STATE_FILE = "essaim-etat.json"  # la mémoire de l'essaim (cryptos, tests, mises de côté), reprise au redémarrage
TRIAL_FILE = "essaim-essais.json"  # la mesure à l'essai : les trades de toutes les combinaisons, par stratégie
REFERENCE_FILE = "reference.json"  # les chiffres d'avant la mesure à l'essai, gardés une fois pour toutes
DETAIL_DIR = "essaim"  # un fichier par bot : son compte complet, repris au redémarrage
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h")
TEAMS = {"1m": "scalping", "5m": "scalping", "15m": "court", "1h": "court", "4h": "long", "1d": "long"}
TEAM_TITLES = {"scalping": "Scalping", "court": "Court terme", "long": "Long terme"}
TEST_DAYS = {"1m": 2, "5m": 7, "15m": 20, "1h": 60, "4h": 240}  # l'historique de chaque re-test
MIN_TRADES = {"1m": 25, "5m": 20, "15m": 15, "1h": 12, "4h": 8}  # trades (étude + validation) pour juger
MIN_BARS = 300
# La bibliothèque : toutes les familles du bot, réglages classiques fixés d'avance (jamais ajustés sur les données).
LIBRARY = (
    "Repli RSI(2) < 10 + MM200", "Repli RSI(2) < 10 sans filtre", "Bollinger rebond 20/2 + MM200",
    "Bollinger rebond 20/2 sans filtre", "Bollinger cassure 20/2", "Bollinger cassure 20/2 + volume x2",
    "Bollinger cassure 20/2 + compression", "Cassure 20/10", "Cassure 55/20", "Cassure 20/10 + volume x2",
    "Croisement MM 10/50", "Croisement MM 20/100", "MACD 12/26/9", "MACD 12/26/9 + MM200", "Momentum 28",
    "Momentum 50", "Supertrend 10/3", "Supertrend 10/2", "Impulsion +1 % en 5 bougies + volume x3",
    "Impulsion +3 % en 15 bougies + volume x3", "Rebond sur support", "Cassure de résistance",
    "Cassure de résistance + volume x2", "Prix au-dessus de la MM 20", "Prix au-dessus de la MM 50",
    "EMA 9/21", "EMA 9/21 + MM200", "EMA 20/50", "VWAP + EMA 9/21", "Stochastique 14/3", "Stochastique 14/3 + MM200",
    "Keltner 20/2", "ADX 14 > 25", "Parabolic SAR", "Ichimoku 9/26/52", "Écart à la moyenne 20/2",
    "Écart à la moyenne 20/2 + MM200", "Heikin-Ashi 2 bougies", "Heikin-Ashi 3 bougies + MM200",
)
UNIVERSE_EVERY_S = 600
RETEST_S = 3 * 3600
BAN_S = 24 * 3600
UNFOLLOWED_S = 6 * 3600  # une crypto sortie de la liste depuis 6 h : ses bots sans position laissent leur place
RETEST_TIMEOUT_S = 900  # un test dure quelques secondes : au-delà, le processus de calcul est remplacé
CHECKPOINT_S = 600
MOOD_EVERY_S = 3600
MIN_VOLUME = 5_000_000
REPLACE_DRAWDOWN = 0.5
ELIMINATE_AFTER = 20
KEEP_TRADES = 100
KEEP_EVENTS = 400
KEEP_RETIRED = 200
MAX_COINS, MAX_BOTS_PER_COIN = 80, 20
SHRINK = 20  # la probabilité estimée est tirée vers la moyenne de la stratégie, comme si on avait 20 trades de plus
LIVE_MIN_TRADES = 30  # trades d'une stratégie avant tout verdict
LIVE_DAYS = 14  # jours gardés pour le classement du jour et des 7 derniers jours
TRIAL_DAYS = 30  # la mesure à l'essai juge sur les 30 derniers jours
TRIAL_MIN_DAYS = 7  # journées différentes avant de déclarer une stratégie prouvée ou recalée
STRETCH_GAP_S = 1800  # sans nouvelles depuis 30 min (PC éteint), on ne sait plus si la crypto bougeait
CLOSE_DELAY_S = 3600  # une crypto qui ne bouge plus : sa mesure à l'essai est close une heure après, si elle n'a pas repris
KEEP_STRETCHES = 200
SYNC_EVERY_S = 600  # l'heure de la plateforme est redemandée toutes les 10 minutes


@dataclass(frozen=True)
class SwarmSettings:
    capital: float = 1000.0  # argent fictif de chaque bot
    leverage_long: float = 1.0
    leverage_court: float = 3.0
    leverage_scalping: float = 5.0
    coins: int = 60  # les cryptos qui bougent le plus
    bots_per_coin: int = 8
    min_move: float = 0.03  # amplitude sur 24 h en dessous de laquelle une crypto est en veille

    def __post_init__(self):
        if not 10 <= self.capital <= 1e9:
            raise ValueError("FLOTTE_CAPITAL doit être entre 10 et 1 000 000 000 USDT")
        for value in (self.leverage_long, self.leverage_court, self.leverage_scalping):
            if not 1 <= value <= 20:
                raise ValueError("Les leviers des bots (FLOTTE_LEVIER_...) doivent être entre 1 et 20")
        if not 1 <= self.coins <= MAX_COINS or not 1 <= self.bots_per_coin <= MAX_BOTS_PER_COIN:
            raise ValueError(f"FLOTTE_CRYPTOS doit être entre 1 et {MAX_COINS}, FLOTTE_BOTS_PAR_CRYPTO entre 1 et "
                             f"{MAX_BOTS_PER_COIN}")
        if not 0 <= self.min_move <= 0.5:
            raise ValueError("FLOTTE_MOUVEMENT_MIN doit être entre 0 et 50 (en %)")

    def leverage(self, timeframe: str) -> float:
        return {"long": self.leverage_long, "court": self.leverage_court,
                "scalping": self.leverage_scalping}[TEAMS.get(timeframe, "court")]

    @property
    def max_bots(self) -> int:
        return self.coins * self.bots_per_coin


def settings_from_env(environ: dict[str, str]) -> SwarmSettings:
    """FLOTTE_CAPITAL, FLOTTE_LEVIER_LONG/COURT/SCALPING, FLOTTE_CRYPTOS, FLOTTE_BOTS_PAR_CRYPTO et FLOTTE_MOUVEMENT_MIN
    (en %) dans .env ; absents : les valeurs par défaut."""
    d = SwarmSettings()

    def num(name, default, kind=float):
        raw = (environ.get(name) or "").strip().replace(",", ".")
        if not raw:
            return default
        try:
            return kind(float(raw))
        except ValueError:
            raise ValueError(f"{name} doit être un nombre (reçu : {raw!r})") from None

    return SwarmSettings(capital=num("FLOTTE_CAPITAL", d.capital),
                         leverage_long=num("FLOTTE_LEVIER_LONG", d.leverage_long),
                         leverage_court=num("FLOTTE_LEVIER_COURT", d.leverage_court),
                         leverage_scalping=num("FLOTTE_LEVIER_SCALPING", d.leverage_scalping),
                         coins=num("FLOTTE_CRYPTOS", d.coins, int),
                         bots_per_coin=num("FLOTTE_BOTS_PAR_CRYPTO", d.bots_per_coin, int),
                         min_move=num("FLOTTE_MOUVEMENT_MIN", 100 * d.min_move) / 100)


def bot_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


# --- Les agents d'analyse ---------------------------------------------------------------------------------------------

SESSIONS = ((0, 8, "Asie (0-8 h UTC)"), (8, 14, "Europe (8-14 h UTC)"), (14, 22, "Amérique (14-22 h UTC)"),
            (22, 24, "nuit (22-24 h UTC)"))
GROUPS = {"trend": "la tendance de fond", "vol": "la volatilité", "rsi": "le RSI", "volume": "le volume",
          "session": "l'heure"}


def features(df: pd.DataFrame) -> pd.DataFrame:
    """Ce que montrait le graphique à chaque bougie : tendance de fond, volatilité, RSI, volume, heure (UTC)."""
    close = df["close"]
    ma = sma(close, 200)
    slope = ma - ma.shift(20)
    trend = np.where(close.isna() | ma.isna(), None,
                     np.where((close > ma) & (slope > 0), "hausse",
                              np.where((close < ma) & (slope < 0), "baisse", "indécise")))
    volume = df["volume"]
    avg = volume.rolling(20, min_periods=20).mean().shift(1)
    return pd.DataFrame({"trend": trend, "atr_pct": atr(df, 14) / close, "rsi": rsi(close, 14),
                         "vol_ratio": volume / avg.where(avg > 0), "hour": df.index.hour}, index=df.index)


def buckets(row, cuts: tuple[float, float] | None) -> dict:
    """Les conditions d'une bougie, rangées dans des cases lisibles."""
    out = {}
    trend = row.get("trend")
    if trend:
        out["trend"] = trend
    a = finite(row.get("atr_pct"))
    if a is not None and cuts:
        out["vol"] = "calme" if a < cuts[0] else "agitée" if a > cuts[1] else "normale"
    r = finite(row.get("rsi"))
    if r is not None:
        out["rsi"] = "survendu (sous 30)" if r < 30 else "suracheté (au-dessus de 70)" if r > 70 else "entre 30 et 70"
    v = finite(row.get("vol_ratio"))
    if v is not None:
        out["volume"] = "fort" if v >= 1.5 else "normal"
    h = row.get("hour")
    if h is not None:
        out["session"] = next(label for lo, hi, label in SESSIONS if lo <= int(h) < hi)
    return out


def profile(trades: list[dict], feats: pd.DataFrame, tf_ms: int = 0) -> dict:
    """Dans quelles conditions la stratégie a gagné ou perdu : pour chaque case, le nombre de trades, la part de
    gagnants et le gain moyen (frais compris)."""
    atr_pct = feats["atr_pct"].dropna()
    cuts = (float(atr_pct.quantile(1 / 3)), float(atr_pct.quantile(2 / 3))) if len(atr_pct) > 30 else None
    rows = feats.to_dict("records")
    where = {int(ts.value // 1_000_000): i for i, ts in enumerate(feats.index)}
    groups: dict[str, dict[str, list[float]]] = {}
    nets = []
    for t in trades:
        if t.get("reason") == "fin du test":
            continue
        nets.append(t["net"])
        i = where.get(int(t["entry_ts"]))
        if not i:
            continue
        row = rows[i - 1]  # la bougie du signal : celle d'avant l'achat
        for group, value in buckets(row, cuts).items():
            groups.setdefault(group, {}).setdefault(value, []).append(t["net"])
    stats = {g: {v: {"n": len(x), "win": sum(y > 0 for y in x) / len(x), "mean": float(np.mean(x))}
                 for v, x in values.items()} for g, values in groups.items()}
    overall = {"n": len(nets), "win": sum(x > 0 for x in nets) / len(nets) if nets else None,
               "mean": float(np.mean(nets)) if nets else None}
    return {"overall": overall, "groups": stats, "cuts": list(cuts) if cuts else None}


def insights(prof: dict | None, minimum: int = 8) -> dict:
    """L'agent « où il gagne, où il perd » : les cases qui s'écartent le plus de sa moyenne, avec assez de trades."""
    if not prof or not prof.get("overall", {}).get("n"):
        return {"wins": [], "losses": []}
    base = prof["overall"]["win"] or 0.0
    cases = []
    for group, values in (prof.get("groups") or {}).items():
        for value, st in values.items():
            if st["n"] >= minimum:
                cases.append((st["win"] - base, group, value, st))
    cases.sort(key=lambda c: c[0])

    def sentence(c):
        _, group, value, st = c
        return (f"Quand {GROUPS.get(group, group)} est « {value} » : {round(100 * st['win'])} % de trades gagnants "
                f"(sur {st['n']}), contre {round(100 * base)} % en moyenne ; {pct(st['mean'], 2)} par trade.")

    return {"wins": [sentence(c) for c in reversed(cases) if c[0] >= 0.08][:3],
            "losses": [sentence(c) for c in cases if c[0] <= -0.08][:3]}


def probability(prof: dict | None, now: dict) -> dict | None:
    """L'agent « probabilité » : la part de trades gagnants dans les conditions du moment, d'après le backtest, tirée vers
    la moyenne de la stratégie quand les cas comparables sont peu nombreux. Une estimation, pas une promesse."""
    if not prof or not prof.get("overall", {}).get("n"):
        return None
    base, n0 = prof["overall"]["win"] or 0.0, prof["overall"]["n"]
    total, weight, used = 0.0, 0, []
    for group, value in now.items():
        st = (prof.get("groups") or {}).get(group, {}).get(value)
        if st and st["n"] >= 5:
            total += st["win"] * st["n"]
            weight += st["n"]
            used.append(f"{GROUPS.get(group, group)} {value}")
    p = (total + SHRINK * base * max(1, len(used))) / (weight + SHRINK * max(1, len(used)))
    return {"p": p, "base": base, "trades": n0, "conditions": used,
            "text": f"{round(100 * p)} % de chances de gain estimées dans les conditions du moment ("
                    + (", ".join(used) if used else "aucune condition assez fréquente : moyenne de la stratégie")
                    + f"), d'après {n0} trades du backtest. Une estimation, pas une promesse."}


def trade_analysis(trade: dict, prof: dict | None) -> list[str]:
    """L'agent « pourquoi ce trade a gagné ou perdu » : ses conditions d'entrée comparées au passé de la stratégie."""
    out = []
    context = trade.get("context") or {}
    if not prof or not context:
        return out
    base = prof["overall"]["win"] or 0.0
    won = trade.get("pnl", 0) > 0
    for group, value in context.items():
        st = (prof.get("groups") or {}).get(group, {}).get(value)
        if not st or st["n"] < 5:
            continue
        diff = st["win"] - base
        if abs(diff) < 0.08:
            continue
        side = "favorables" if diff > 0 else "défavorables"
        verdict = ("comme souvent" if (diff > 0) == won else "contre la tendance de son passé")
        out.append(f"Entré quand {GROUPS.get(group, group)} était « {value} », des conditions {side} pour cette stratégie "
                   f"({round(100 * st['win'])} % de gagnants sur {st['n']} trades, contre {round(100 * base)} % en "
                   f"moyenne) : il a {'gagné' if won else 'perdu'}, {verdict}.")
    return out[:3]


# --- Le labo en direct : tester une crypto ------------------------------------------------------------------------------

def _eligible(r: dict, tf: str) -> bool:
    """Gagnante, frais compris, sur l'étude et sur la validation, avec assez de trades, sans liquidation pendant ces
    deux périodes. Le test final n'est jamais regardé ici : il sert à mesurer ce que vaut ce choix."""
    return (not r["liquidated_early"] and r["sv_n"] >= MIN_TRADES.get(tf, 15) and r["study_n"] >= MIN_PART_TRADES
            and r["valid_n"] >= MIN_PART_TRADES and r["study_mean"] > 0 and r["valid_mean"] > 0)


def _label(r: dict, eligible: bool = True) -> tuple[str, str]:
    """Ce que dit le test final d'une combinaison (il n'a pas servi à la choisir) : « 3 » gagnant, « 1 » perdant,
    « 2 » trop peu de trades pour le dire ; « 0 » : un bot en place qui ne gagne plus sur l'étude et la validation."""
    if not eligible:
        return "0", ("Ne gagne plus sur l'étude et la validation de son dernier test : il garde sa place, ce sont ses "
                     "trades en direct qui le jugent")
    chosen = "Choisi sur l'étude et la validation"
    if r["test_n"] < 5:
        return "2", f"{chosen} ; trop peu de trades sur le test final pour en dire plus"
    if r["test_mean"] > 0:
        return "3", f"{chosen} ; gagnant aussi sur le test final, qui n'a pas servi à le choisir"
    return "1", f"{chosen} ; perdant sur le test final, qui n'a pas servi à le choisir"


LABEL_SHORT = {"3": "test final gagnant", "1": "test final perdant", "2": "trop peu de trades sur le test final",
               "0": "ne gagne plus sur son dernier test"}


def strategy_key(technique_name: str, timeframe: str) -> str:
    """Une stratégie, pour les classements : une technique dans une unité de temps (toutes cryptos réunies)."""
    return f"{technique_name}|{timeframe}"


def exit_label(target_r: float, stop_mode: str) -> str:
    if stop_mode == "suiveur":
        return "stop suiveur"
    if stop_mode == "securise":
        return "objectif 2R + stop sécurisé" if target_r else "stop sécurisé"
    return "objectif 2R" if target_r else "sortie par la règle"


def stat_keys(spec: Spec) -> tuple[str, ...]:
    """Les lignes des classements auxquelles compte un trade : sa stratégie, sa technique, sa sortie, son sens, son
    unité de temps."""
    return (f"strategie:{strategy_key(spec.technique, spec.timeframe)}", f"technique:{spec.technique}",
            f"sortie:{exit_label(spec.target_r, spec.stop_mode)}", f"sens:{spec.side}", f"unite:{spec.timeframe}")


def detail_key(spec: Spec) -> str:
    """La combinaison complète (technique, unité, sens, sortie), toutes cryptos réunies."""
    return f"detail:{spec.technique}|{spec.timeframe}|{spec.side}|{exit_label(spec.target_r, spec.stop_mode)}"


def _rank_key(r: dict) -> float:
    score = r["score"]
    return -score if math.isfinite(score) else (-1e9 if score > 0 else 1e9)


def per_timeframe(k: int) -> int:
    """Bots au plus dans une même unité de temps, sur une crypto : 2 jusqu'à 8 bots, davantage au-delà."""
    return max(2, math.ceil(k / 4))


def _choose(rows: list[dict], k: int, verdicts: dict[str, str] | None = None,
            taken: list[dict] | tuple = ()) -> list[dict]:
    """Les mieux classées d'une crypto, pour remplir ses k places : des familles et des unités de temps variées (une
    combinaison par technique et unité). `taken` : les bots déjà en place, qui gardent leur place et comptent dans la
    variété. Ce que la mesure à l'essai a appris passe avant : une stratégie prouvée (toutes cryptos réunies) est
    prise en premier, une stratégie recalée n'est plus prise."""
    verdicts = verdicts or {}

    def verdict(r):
        return verdicts.get(strategy_key(r["technique"], r["timeframe"]))

    rows = [r for r in rows if verdict(r) != "recalee"]
    ranked = sorted(rows, key=lambda r: (verdict(r) != "prouvee", _rank_key(r)))
    chosen, seen, per_tf, families = [], set(), {}, set()
    for r in taken:
        seen.add((r["timeframe"], r["technique"]))
        per_tf[r["timeframe"]] = per_tf.get(r["timeframe"], 0) + 1
        families.add((r["family"], r["side"]))
    room, cap = k - len(taken), per_timeframe(k)
    for strict in (True, False):
        for r in ranked:
            if len(chosen) >= room:
                return chosen
            what = (r["timeframe"], r["technique"])
            if what in seen or per_tf.get(r["timeframe"], 0) >= cap:
                continue
            if strict and (r["family"], r["side"]) in families:
                continue
            chosen.append(r)
            seen.add(what)
            per_tf[r["timeframe"]] = per_tf.get(r["timeframe"], 0) + 1
            families.add((r["family"], r["side"]))
    return chosen


def new_record(days: bool = True) -> dict:
    """Une ligne de la mesure à l'essai : trades, somme des rendements (et de leurs carrés), gagnants, somme des gains
    (`gain`, pour le gain moyen, la perte moyenne et le profit factor), somme des rendements comptés en R (`r`), et le
    détail par jour (trades, somme, gagnants)."""
    rec = {"n": 0, "total": 0.0, "total_sq": 0.0, "wins": 0, "gain": 0.0, "r": 0.0}
    if days:
        rec["days"] = {}
    return rec


def merge_record(into: dict, rec: dict) -> None:
    for k in ("n", "total", "total_sq", "wins", "gain", "r"):
        into[k] = into.get(k, 0) + rec.get(k, 0)
    if "days" in rec:
        mine = into.setdefault("days", {})
        for day, (n, total, wins) in rec["days"].items():
            d = mine.setdefault(day, [0, 0.0, 0])
            d[0], d[1], d[2] = d[0] + n, d[1] + total, d[2] + wins


class Harvest:
    """La mesure à l'essai, pendant le test d'une crypto : les trades de toutes les combinaisons, pas seulement ceux
    des bots choisis. Un trade est compté une seule fois, au test qui suit sa fermeture (`done` : la dernière bougie
    du test précédent, par unité), et seulement s'il a été ouvert pendant que la crypto bougeait (`active`), comme un
    vrai bot. La position encore ouverte attend sa fermeture ; au dernier test d'une crypto qui ne bouge plus
    (`final`), elle est comptée à sa valeur du moment, frais de sortie compris."""

    def __init__(self, trial: dict):
        self.since = {tf: int(ts) for tf, ts in (trial.get("done") or {}).items()}
        self.done = dict(self.since)
        self.active = [(int(a), math.inf if b is None else int(b)) for a, b in trial.get("active") or []]
        self.final = bool(trial.get("final"))
        self.stats: dict[str, dict] = {}
        self.open = self.counted = 0

    def watched(self, ts: int) -> bool:
        return any(a <= ts <= b for a, b in self.active)

    def add(self, spec: Spec, trades: list[dict]) -> None:
        since = self.since.get(spec.timeframe, 0)
        for t in reversed(trades):
            still_open = t["reason"] == "fin du test"
            if not still_open and t["exit_ts"] <= since:
                break  # celui-ci et les précédents ont été comptés aux tests d'avant
            if not self.watched(t["entry_ts"]):
                continue
            if still_open and not self.final:
                self.open += 1
                continue
            self._count(spec, t)

    def _count(self, spec: Spec, t: dict) -> None:
        net = float(t["net"])
        if not math.isfinite(net):
            return
        day = _iso(t["exit_ts"])[:10]
        in_r = net / t["risk"] if t.get("risk") else 0.0
        for key in stat_keys(spec) + (detail_key(spec),):
            rec = self.stats.setdefault(key, new_record(days=not key.startswith("detail:")))
            rec["n"] += 1
            rec["total"] += net
            rec["total_sq"] += net * net
            rec["wins"] += int(net > 0)
            rec["gain"] += max(net, 0.0)
            rec["r"] += in_r
            if "days" in rec:
                d = rec["days"].setdefault(day, [0, 0.0, 0])
                d[0], d[1], d[2] = d[0] + 1, d[1] + net, d[2] + int(net > 0)
        self.counted += 1

    def result(self) -> dict:
        return {"done": self.done, "stats": self.stats, "open": self.open, "counted": self.counted, "final": self.final}


def _holdout(rows: list[dict]) -> dict:
    """Le test final de ces combinaisons, réuni : il n'a pas servi à les choisir."""
    return {"n": sum(r["test_n"] for r in rows), "total": sum(r["test_total"] for r in rows),
            "total_sq": sum(r["test_sq"] for r in rows), "wins": sum(r["test_wins"] for r in rows)}


def retest_coin(symbol: str, frames: dict[str, pd.DataFrame], settings: dict, banned: tuple[str, ...] = (),
                verdicts: dict[str, str] | None = None, keep: tuple[dict, ...] = (), trial: dict | None = None,
                ex: ExecutionParams = FUTURES) -> dict:
    """Toutes les combinaisons sur une crypto : le travail d'un re-test (envoyé à un processus à part). `verdicts` :
    ce que la mesure à l'essai a appris de chaque stratégie (prouvée, recalée). `keep` : les fiches des bots déjà en
    place sur cette crypto ; ils gardent leur place, le test ne choisit que de quoi remplir les places libres.
    `trial` : la mesure à l'essai (voir Harvest)."""
    s = SwarmSettings(**settings)
    verdicts = verdicts or {}
    kept_keys = {spec_from(d).key for d in keep}
    harvest = Harvest(trial) if trial is not None else None
    rows, books, feats = [], {}, {}
    eligible: set[str] = set()
    for tf, df in frames.items():
        if df is None or len(df) < MIN_BARS:
            continue
        start, end = int(df["ts"].iloc[0]), int(df["ts"].iloc[-1])
        try:
            feats[tf] = features(df)
        except Exception as exc:
            log.warning("%s %s : conditions illisibles (%s)", symbol, tf, exc)
            continue
        for name in LIBRARY:
            params = technique(name)
            if len(df) < params.warmup_bars + MIN_BARS:
                continue
            for side in SIDES:
                try:
                    sig = signals_for(df, params, side)
                    for target, mode in EXITS:
                        spec = Spec(TEAMS[tf], symbol, tf, name, side, target, s.leverage(tf), mode)
                        book = simulate(df, spec, s.capital, ex, sig)
                        row = judge_row(book, start, end)
                        rows.append(row)
                        if harvest is not None:
                            harvest.add(spec, book.s["trades"])
                        if _eligible(row, tf):
                            eligible.add(row["key"])
                        if row["key"] in eligible or row["key"] in kept_keys:
                            books[row["key"]] = book
                except Exception as exc:  # des bougies étranges n'arrêtent jamais le test de la crypto
                    log.warning("%s %s %s : combinaison ignorée (%s)", symbol, tf, name, exc)
        if harvest is not None:
            harvest.done[tf] = end

    def full(r: dict) -> dict:
        tf = r["timeframe"]
        code, text = _label(r, r["key"] in eligible)
        trades = books[r["key"]].s["trades"]
        return {**r, "label": code, "label_text": text, "profile": profile(trades, feats[tf], timeframe_to_ms(tf)),
                "curve": _curve(trades, int(frames[tf]["ts"].iloc[0]), s.capital)}

    by_key = {r["key"]: r for r in rows}
    taken = [by_key[k] for k in sorted(kept_keys) if k in by_key]
    good = [r for r in rows if r["key"] in eligible and r["key"] not in banned]
    final = bool(trial and trial.get("final"))  # la crypto ne bouge plus : on clôt sa mesure, on ne choisit rien
    chosen = [] if final else _choose([r for r in good if r["key"] not in kept_keys], s.bots_per_coin, verdicts, taken)
    best = sorted(rows, key=lambda r: -r["score"] if math.isfinite(r["score"]) else 1e9)[:12]
    return {"symbol": symbol, "tested": len(rows), "eligible": len(good), "chosen": [full(r) for r in chosen],
            "kept": [full(r) for r in taken], "final": final,
            # ce que le labo choisirait aujourd'hui, et toutes les gagnantes de l'étude et de la validation, jugés sur
            # le test final qu'ils n'ont jamais vu
            "holdout": _holdout(_choose(good, s.bots_per_coin, verdicts)), "holdout_eligible": _holdout(good),
            "trial": harvest.result() if harvest is not None else None,
            "best": [{k: r[k] for k in ("timeframe", "technique", "side", "target_r", "stop_mode", "sv_n", "sv_mean",
                                        "test_n", "test_mean", "total_return", "drawdown")}
                     | {"eligible": r["key"] in eligible,
                        "live": verdicts.get(strategy_key(r["technique"], r["timeframe"]))}
                     for r in best]}


def judge_row(book: Book, start: int, end: int) -> dict:
    from .fleet import judge
    return judge(book, start, end)


def _curve(trades: list[dict], first: int, capital: float, points: int = 120) -> list:
    curve = [[first, capital]] + [[t["exit_ts"], t["equity"]] for t in trades]
    if len(curve) > points:
        step = len(curve) / points
        curve = [curve[int(i * step)] for i in range(points)] + [curve[-1]]
    return curve


class Retester:
    """Les re-tests, à part du direct : un fil télécharge l'historique (sa propre connexion), un processus calcule.
    Si le calcul en parallèle est impossible (PC limité, antivirus...), il se fait dans le fil, plus lentement."""

    def __init__(self, make_exchange, exchange_id: str, settings: SwarmSettings, workers: int = 1):
        self.make_exchange, self.exchange_id, self.settings, self.workers = make_exchange, exchange_id, settings, workers
        self.jobs: queue.Queue = queue.Queue()
        self.results: queue.Queue = queue.Queue()
        self.pending: set[str] = set()
        self.current: str | None = None
        self.done = 0
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def submit(self, symbol: str, banned: tuple[str, ...] = (), verdicts: dict[str, str] | None = None,
               keep: tuple[dict, ...] = (), trial: dict | None = None) -> bool:
        with self.lock:
            if symbol in self.pending:
                return False
            self.pending.add(symbol)
        self.jobs.put((symbol, tuple(banned), dict(verdicts or {}), tuple(keep), trial))
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._loop, name="labo-en-direct", daemon=True)
            self.thread.start()
        return True

    def status(self) -> dict:
        with self.lock:
            return {"queue": len(self.pending), "current": self.current, "done": self.done}

    def _frames(self, exchange, symbol: str) -> dict[str, pd.DataFrame]:
        frames = {}
        now = exchange.milliseconds()
        for tf in TIMEFRAMES:
            try:
                # Jusqu'à la bougie en cours comprise, puis sans elle : une bougie n'est terminée que lorsque la
                # plateforme a ouvert la suivante (l'horloge du PC peut avancer ou retarder).
                df = fetch_history(exchange, symbol, tf, now - TEST_DAYS[tf] * 86_400_000, now + timeframe_to_ms(tf))
                frames[tf] = df.iloc[:-1]
            except Exception as exc:  # une unité qui ne répond pas : les autres sont quand même testées
                log.warning("%s %s : historique indisponible (%s)", symbol, tf, exc)
        return frames

    def _replace(self, pool):
        """Un calcul bloqué : son processus est arrêté et remplacé (None : la suite se fait dans le fil)."""
        try:
            for process in list((getattr(pool, "_processes", None) or {}).values()):
                process.terminate()
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:  # le processus est peut-être déjà mort
            log.debug("Arrêt du calcul bloqué : %s", exc)
        try:
            return ProcessPoolExecutor(max_workers=self.workers)
        except (OSError, RuntimeError, ValueError):
            return None

    def _loop(self) -> None:
        exchange = self.make_exchange(self.exchange_id)
        pool = None
        if self.workers > 0:
            try:
                pool = ProcessPoolExecutor(max_workers=self.workers)
            except (OSError, RuntimeError, ValueError) as exc:
                log.warning("Calcul à part impossible (%s) : les tests se font dans le direct, plus lentement.", exc)
        settings = asdict(self.settings)
        while True:
            symbol, banned, verdicts, keep, trial = self.jobs.get()
            with self.lock:
                self.current = symbol
            try:
                frames = self._frames(exchange, symbol)
                result = None
                if pool is not None:
                    try:
                        result = pool.submit(retest_coin, symbol, frames, settings, banned, verdicts, keep,
                                             trial).result(RETEST_TIMEOUT_S)
                    except FutureTimeout:
                        pool = self._replace(pool)
                        raise RuntimeError("test trop long, le processus de calcul a été remplacé") from None
                    except (BrokenProcessPool, OSError, RuntimeError, pickle.PicklingError) as exc:
                        log.warning("Calcul à part interrompu (%s) : il continue dans le fil.", exc)
                        pool = None
                if result is None:
                    result = retest_coin(symbol, frames, settings, banned, verdicts, keep, trial)
                self.results.put(result)
            except Exception as exc:  # jamais fatal : la crypto sera retestée plus tard
                log.warning("Test de %s impossible : %s", symbol, exc)
                self.results.put({"symbol": symbol, "error": str(exc)[:200],
                                  "final": bool(trial and trial.get("final"))})
            finally:
                with self.lock:
                    self.pending.discard(symbol)
                    self.current = None
                    self.done += 1


def fetch_mood() -> dict | None:
    """L'indice peur et avidité du jour (alternative.me) : une information, jamais un signal d'achat."""
    from .news import FNG_URL, _http_get, parse_fng, zone
    series = parse_fng(json.loads(_http_get(FNG_URL.replace("limit=0", "limit=2"))))
    if series.empty:
        return None
    value = float(series.iloc[-1])
    return {"value": value, "zone": zone(value), "date": str(series.index[-1].date())}


class PlatformClock:
    """L'heure de la plateforme, pas celle du PC : une horloge d'ordinateur qui avance de quelques secondes ferait
    décider un bot sur une bougie pas terminée, une horloge qui retarde le ferait entrer en retard. L'heure est
    demandée à la plateforme, puis avancée avec l'horloge monotone du PC (insensible aux remises à l'heure). Si la
    plateforme ne la donne pas, ou si les deux horloges ne s'accordent plus (mise en veille, remise à l'heure), on
    revient à l'horloge du PC et `synced` est faux : une bougie n'est alors terminée que lorsque la suivante existe."""

    def __init__(self, exchange, clock=time.time, monotonic=time.monotonic):
        self.exchange, self.clock, self.monotonic = exchange, clock, monotonic
        self.base: tuple[float, float, float] | None = None  # heure de la plateforme (ms), instant monotone, écart au PC
        self.asked = -math.inf  # dernier essai (instant monotone)

    @property
    def synced(self) -> bool:
        return self.base is not None

    def due(self) -> bool:
        """Faut-il redemander l'heure ? Toutes les 10 minutes, ou chaque minute tant qu'on ne l'a pas."""
        return self.monotonic() - self.asked >= (SYNC_EVERY_S if self.synced else 60)

    def sync(self) -> bool:
        self.asked = self.monotonic()
        fetch = getattr(self.exchange, "fetch_time", None)
        if fetch is None:
            return False
        try:
            sent = self.monotonic()
            server = fetch()
            back = self.monotonic()
        except Exception as exc:  # jamais bloquant : on garde l'heure qu'on avait
            log.debug("Heure de la plateforme indisponible : %s", exc)
            return False
        if not server or back - sent > 2.0:
            return False  # réponse trop lente : mesure trop floue pour s'y fier
        now = float(server) + (back - sent) * 500  # le milieu de l'aller-retour
        self.base = (now, back, now - self.clock() * 1000)
        return True

    def now_ms(self) -> int:
        if self.base is None:
            return int(self.clock() * 1000)
        server, at, offset = self.base
        now = server + (self.monotonic() - at) * 1000
        if abs(now - (self.clock() * 1000 + offset)) > 3000:  # veille du PC ou remise à l'heure : on ne sait plus
            self.base, self.asked = None, -math.inf
            return int(self.clock() * 1000)
        return int(now)


class CandleStore:
    """Les bougies de chaque (crypto, unité), gardées en mémoire et complétées à chaque tour par les dernières
    seulement : des centaines de bots sans télécharger mille bougies à chaque minute."""

    def __init__(self, exchange):
        self.exchange = exchange
        self.frames: dict[tuple[str, str], pd.DataFrame] = {}
        self.asked: dict[tuple[str, str], int] = {}  # la plus longue fenêtre déjà demandée

    def closed(self, symbol: str, timeframe: str, limit: int, now_ms: int, synced: bool = False) -> pd.DataFrame:
        """Les bougies terminées. La dernière que rend la plateforme est celle en cours : elle n'est terminée que
        lorsque la suivante existe, ou lorsque l'heure de la plateforme (`synced`) a dépassé sa fin. L'horloge du PC
        seule ne suffit jamais à le décider."""
        tf_ms = timeframe_to_ms(timeframe)
        key = (symbol, timeframe)
        df = self.frames.get(key)
        if df is None or df.empty or limit > self.asked.get(key, 0) or now_ms - int(df["ts"].iloc[-1]) > 4 * tf_ms:
            df = ohlcv_to_frame(self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit))
            self.asked[key] = limit  # un bot qui lit plus loin arrive : la fenêtre est retéléchargée en entier
        else:
            fresh = ohlcv_to_frame(self.exchange.fetch_ohlcv(symbol, timeframe, limit=5))
            df = pd.concat([df, fresh])
            df = df[~df["ts"].duplicated(keep="last")].sort_values("ts").iloc[-max(limit, self.asked.get(key, 0)):]
        self.frames[key] = df
        if synced:
            return df[(df["ts"] + tf_ms <= now_ms) | (df["ts"] < df["ts"].iloc[-1])] if len(df) else df
        return df.iloc[:-1]

    def forget(self, symbol: str) -> None:
        for key in [k for k in self.frames if k[0] == symbol]:
            del self.frames[key]
            self.asked.pop(key, None)


# --- Le direct ---------------------------------------------------------------------------------------------------------

BACKTEST_KEYS = ("trades", "win_rate", "mean", "gross_mean", "sv_n", "sv_mean", "study_n", "study_mean", "valid_n",
                 "valid_mean", "test_n", "test_mean", "total_return", "drawdown", "start_ts", "end_ts", "score")


def backtest_of(r: dict) -> dict:
    """Ce que le bot garde de son dernier test : ses chiffres, sa courbe et son profil (pour les agents)."""
    return {k: r.get(k) for k in BACKTEST_KEYS} | {"curve": r.get("curve") or [], "profile": r.get("profile")}


def new_bot(r: dict, capital: float, now_ms: int) -> dict:
    spec = spec_from(r)
    return {"id": bot_id(spec.key), "key": spec.key, "spec": asdict(spec), "team": TEAMS.get(spec.timeframe, "court"),
            "status": "actif", "label": r.get("label", "2"), "label_text": r.get("label_text", ""),
            "started": _iso(now_ms), "tested": _iso(now_ms), "backtest": backtest_of(r),
            "book": Book(spec, capital).s, "signal": None, "last_price": None, "proba": None}


class Swarm:
    """Les bots en direct : un tour toutes les quelques secondes, sans fin."""

    def __init__(self, exchange, folder: Path | None, settings: SwarmSettings = SwarmSettings(),
                 ex: ExecutionParams = FUTURES, clock=time.time, tester: Retester | None = None, read: bool = True,
                 universe_every: float = UNIVERSE_EVERY_S, mood=None):
        self.exchange, self.folder, self.settings, self.ex = exchange, folder, settings, ex
        self.clock, self.tester, self.read, self.universe_every = clock, tester, read, universe_every
        self.mood = mood  # fetch_mood en vrai ; rien dans les tests
        self.time = PlatformClock(exchange, clock)
        self.candles = CandleStore(exchange)
        self.next_fetch: dict[tuple[str, str], int] = {}
        self.last_closed: dict[tuple[str, str], int] = {}
        self.waits: dict[tuple[str, str], int] = {}  # tours d'attente d'une bougie que la plateforme n'a pas finie
        self.fetch_failures: dict[tuple[str, str], int] = {}
        self.dirty: set[str] = set()
        self.rotation: list[str] = []  # les fiches des bots, réécrites peu à peu (toutes en dix minutes)
        self.state_dirty = True
        self.checkpoint = 0.0
        self.beat_lock = threading.Lock()
        now = int(clock() * 1000)
        fresh = {"version": 2, "created": _iso(now), "coins": {}, "universe": [], "universe_at": 0, "events": [],
                 "retired": [], "retired_totals": {"start": 0.0, "end": 0.0, "count": 0, "wins": 0, "bots": 0},
                 "banned": {}, "mood": None, "mood_at": 0}
        state = load_json(folder / STATE_FILE, tries=3) if folder else None
        if isinstance(state, dict) and state.get("version") == 2 and isinstance(state.get("coins"), dict):
            self.state = {**fresh, **state}
        else:
            self.state = fresh
        for info in self.state["coins"].values():
            if info.get("status") == "test en cours":  # le test d'avant l'arrêt est perdu : il sera refait
                info.update(status="en attente de test", next_test=0)
        self.state["capital"] = settings.capital
        trial = load_json(folder / TRIAL_FILE, tries=3) if folder else None
        if isinstance(trial, dict) and trial.get("version") == 1 and isinstance(trial.get("stats"), dict):
            self.trial = trial
        else:
            self.trial = {"version": 1, "since": _iso(now), "stats": {}}
        self.trial_dirty = True
        self.trial_cache: tuple | None = None
        self.reference = self._reference(now)
        self.bots: dict[str, dict] = {}
        if folder:
            for path in sorted((folder / DETAIL_DIR).glob("*.json")):
                bot = load_json(path, tries=2)
                try:
                    if bot and bot.get("key"):
                        spec_from(bot["spec"])  # une technique disparue d'une ancienne version : bot ignoré
                        self.bots[bot["key"]] = bot
                except (KeyError, TypeError, ValueError) as exc:
                    log.warning("Bot %s illisible, ignoré : %s", path.name, exc)
        self.save()

    # --- outils ---
    def book(self, bot: dict) -> Book:
        return Book(spec_from(bot["spec"]), state=bot["book"], ex=self.ex, keep=KEEP_TRADES, explain=True)

    def _reference(self, now_ms: int) -> dict | None:
        """Le point de référence : les chiffres du site tels qu'ils étaient au premier lancement de cette version,
        avant la mesure à l'essai. Écrit une seule fois, jamais remplacé."""
        if not self.folder:
            return None
        path = self.folder / REFERENCE_FILE
        saved = load_json(path, tries=3)
        if isinstance(saved, dict) and saved.get("saved"):
            return saved
        if path.exists():
            return None  # illisible à l'instant : on n'écrase jamais un point de référence
        before = load_json(self.folder / SWARM_FILE, tries=3) or {}
        totals = before.get("totals") if isinstance(before.get("totals"), dict) else None
        ranking = before.get("ranking") if isinstance(before.get("ranking"), dict) else None
        saved = {"saved": _iso(now_ms), "since": before.get("created"), "totals": totals, "ranking": ranking,
                 "note": "Les chiffres du site au premier lancement de la version qui mesure toutes les combinaisons "
                         "à l'essai : le point de comparaison pour la suite. Jamais réécrit."}
        self._write(path, saved)
        return saved

    def event(self, kind: str, text: str, **extra) -> dict:
        e = {"t": _iso(self.time.now_ms()), "kind": kind, "text": text, **extra}
        self.state["events"].append(e)
        del self.state["events"][:-KEEP_EVENTS]
        self.state_dirty = True
        return e

    def add_bot(self, r: dict, now_ms: int) -> dict:
        bot = new_bot(r, self.settings.capital, now_ms)
        self.bots[bot["key"]] = bot
        self.dirty.add(bot["key"])
        return bot

    # --- un tour ---
    def cycle(self, now_ms: int | None = None) -> list[dict]:
        if now_ms is None:
            if self.time.due():
                self.time.sync()
            now_ms = self.time.now_ms()
        at = _iso(now_ms)
        events: list[dict] = []
        events += self._apply_tests(now_ms)
        if now_ms - int(self.state.get("universe_at") or 0) >= self.universe_every * 1000:
            events += self._refresh_universe(now_ms)
        self._schedule_tests(now_ms)
        bots = list(self.bots.values())
        symbols = sorted({b["spec"]["symbol"] for b in bots})
        prices = self._prices(symbols) if symbols else {}
        groups: dict[tuple[str, str], list[dict]] = {}
        for bot in bots:
            groups.setdefault((bot["spec"]["symbol"], bot["spec"]["timeframe"]), []).append(bot)
        for (symbol, tf), items in groups.items():
            if now_ms < self.next_fetch.get((symbol, tf), 0):
                continue
            tf_ms = timeframe_to_ms(tf)
            limit = max(lookback_for(technique(b["spec"]["technique"])) for b in items)
            try:
                closed = self.candles.closed(symbol, tf, limit, now_ms, self.time.synced)
            except Exception as exc:  # une crypto qui ne répond pas ne bloque jamais les autres
                fails = self.fetch_failures[(symbol, tf)] = self.fetch_failures.get((symbol, tf), 0) + 1
                if fails in (1, 10) or fails % 60 == 0:  # pas une ligne par minute dans le journal
                    log.warning("%s %s : bougies indisponibles (%s), nouvel essai dans une minute", symbol, tf, exc)
                self.next_fetch[(symbol, tf)] = now_ms + 60_000
                continue
            self.fetch_failures.pop((symbol, tf), None)
            if closed.empty:
                continue
            newest = int(closed["ts"].iloc[-1])
            if newest == self.last_closed.get((symbol, tf)):
                # La bougie attendue n'est pas encore terminée côté plateforme (horloge du PC en avance, ou la
                # suivante pas encore ouverte) : on redemande bientôt, de moins en moins souvent.
                waits = self.waits[(symbol, tf)] = self.waits.get((symbol, tf), 0) + 1
                self.next_fetch[(symbol, tf)] = now_ms + min(60_000, 5000 * 2 ** max(0, waits - 2))
            else:
                self.last_closed[(symbol, tf)] = newest
                self.waits.pop((symbol, tf), None)
                self.next_fetch[(symbol, tf)] = newest + 2 * tf_ms + 2000
            now_feats = self._now_features(closed)
            reading = self._reading(closed) if self.read else None
            for bot in items:
                try:
                    events += self._on_candles(bot, closed, prices.get(symbol), at, now_feats, reading)
                except Exception as exc:  # un bot qui bute sur ses bougies ne bloque jamais les autres
                    log.warning("Bot %s : bougie non traitée (%s)", bot.get("id"), exc)
        for bot in bots:  # le prix du moment : stop et objectif entre deux bougies
            price = prices.get(bot["spec"]["symbol"])
            if not price:
                continue
            bot["last_price"] = price
            book = self.book(bot)
            if book.position:
                forming = now_ms - now_ms % book.tf_ms
                events += self._report(bot, book.range_bar(forming, None, price, price, at))
        events += self._judge_strategies()
        events += self._retire(now_ms)
        if now_ms - int(self.state.get("mood_at") or 0) >= MOOD_EVERY_S * 1000:
            self._refresh_mood(now_ms)
        self.state["updated"] = at
        self.save(now_ms)
        return events

    def _prices(self, symbols: list[str]) -> dict[str, float]:
        try:
            tickers = self.exchange.fetch_tickers(symbols)
        except ccxt.NetworkError:
            raise  # réseau coupé : le tour est retenté plus tard
        except Exception as exc:  # une liste refusée : chaque crypto à part
            log.debug("Prix groupés indisponibles (%s)", exc)
            tickers = {}
            for s in symbols:
                try:
                    tickers[s] = self.exchange.fetch_ticker(s)
                except Exception as exc2:
                    log.debug("%s : prix indisponible (%s)", s, exc2)
        return {s: float(t["last"]) for s, t in tickers.items() if s in symbols and (t or {}).get("last")}

    @staticmethod
    def _now_features(closed: pd.DataFrame) -> dict:
        try:
            f = features(closed.iloc[-260:])
            return f.iloc[-1].to_dict()
        except Exception:
            return {}

    def _reading(self, closed: pd.DataFrame) -> dict | None:
        try:
            r = read_chart(closed, fees=2 * (self.ex.fee_rate + self.ex.slippage))
        except Exception as exc:
            log.debug("Lecture du graphique impossible : %s", exc)
            return None
        return {k: r.get(k) for k in ("price", "trend", "ma200", "support", "resistance", "rsi", "candle_pct", "change",
                                      "volume_ratio", "round_below", "round_above")} | {"sentences": r["sentences"][:9]}

    def _on_candles(self, bot: dict, closed: pd.DataFrame, price: float | None, at: str, now_feats: dict,
                    reading: dict | None) -> list[dict]:
        """Les bougies terminées depuis le dernier tour, une par une, dans l'ordre du backtest : l'ordre décidé à la
        clôture précédente à l'ouverture, puis stop et objectif, puis les signaux à la clôture. Après une coupure (PC
        éteint, réseau coupé), le bot rattrape ainsi exactement ce qu'aurait fait son backtest. La décision de la
        dernière clôture est exécutée tout de suite, au prix du moment."""
        book = self.book(bot)
        last = book.s["last_ts"]
        new = closed[closed["ts"] > last] if last is not None else closed.iloc[-1:]
        if new.empty:
            return []
        events = []
        active = bot["status"] == "actif"
        sig = signals_for(closed, book.params, book.spec.side) if len(closed) >= book.params.warmup_bars else None
        prof = (bot.get("backtest") or {}).get("profile")
        now_b = buckets(now_feats, tuple(prof["cuts"]) if prof and prof.get("cuts") else None)
        first, count = len(closed) - len(new), len(new)
        for k, row in enumerate(new.itertuples()):
            ts, row_at = int(row.ts), at if k == count - 1 else None  # rattrapage : l'heure de la bougie
            if book.s["pending"]:
                events += self._opened(bot, book, book.open_bar(ts, float(row.open), row_at), now_b)
            if book.position is not None and ts >= book.position["entry_ts"]:
                events += self._report(bot, book.range_bar(ts, float(row.open), float(row.high), float(row.low),
                                                           row_at))
            if sig is not None:
                i = first + k
                book.close_bar(ts, float(row.close), bool(sig.entry[i]) and active, bool(sig.exit[i]),
                               float(sig.atr[i]))
            else:
                book.s["last_ts"] = ts
        last_ts = int(new["ts"].iloc[-1])
        if sig is not None:
            bot["signal"] = {"ts": last_ts, "entry": bool(sig.entry[-1]), "exit": bool(sig.exit[-1])}
        bot["proba"] = probability(prof, now_b)
        if book.s["pending"]:
            events += self._opened(bot, book, book.open_bar(last_ts + book.tf_ms, price or float(new["close"].iloc[-1]),
                                                            at), now_b)
        if reading:
            bot["reading"] = reading
        return events

    def _opened(self, bot: dict, book: Book, results: list[dict], now_b: dict) -> list[dict]:
        if book.position is not None and results and results[-1]["kind"] == "entry":
            book.position["context"] = now_b  # ce que montrait le graphique au signal (l'analyse du trade s'en sert)
        return self._report(bot, results)

    def _report(self, bot: dict, results: list[dict]) -> list[dict]:
        out = []
        spec = spec_from(bot["spec"])
        name = f"{spec.coin} · {tf_label(spec.timeframe)} · {spec.technique}"
        for r in results:
            self.dirty.add(bot["key"])
            if r["kind"] == "entry":
                verb = "achète" if r["side"] == "long" else "vend à découvert"
                target = f", objectif {fmt_price(r['target'])}" if r["target"] else ", sortie par sa règle"
                text = (f"{name} : {verb} à {fmt_price(r['price'])}, levier ×{r['leverage']:g}, stop "
                        f"{fmt_price(r['stop'])}{target}. Signal : {condition(spec.params, spec.side)}.")
                out.append(self.event("achat" if r["side"] == "long" else "vente", text, bot=bot["id"],
                                      symbol=spec.symbol))
            else:
                trade = bot["book"]["trades"][-1] if bot["book"]["trades"] else r
                trade["analysis"] = trade_analysis(trade, (bot.get("backtest") or {}).get("profile"))
                self._learn(spec, r)
                text = (f"{name} : sort à {fmt_price(r['exit_price'])} ({r['reason']}), {pct(r['roi'])} sur son capital "
                        f"({pct(r['net'], 2)} sur la position, frais compris).")
                out.append(self.event("sortie", text, bot=bot["id"], symbol=spec.symbol, roi=r["roi"]))
        return out

    # --- le classement des stratégies en direct ---
    def _learn(self, spec: Spec, trade: dict) -> None:
        """Chaque trade fini compte pour sa stratégie (technique et unité, toutes cryptos réunies), sa façon de sortir,
        son sens, sa technique et son unité : rendement par trade sans levier, frais compris (comparable d'un bot à
        l'autre). Jour par jour, pour le classement du jour et des 7 derniers jours."""
        net = float(trade["net"])
        if not math.isfinite(net):
            return
        day = _iso(self.time.now_ms())[:10]
        live = self.state.setdefault("live", {})
        for key in stat_keys(spec):
            rec = live.setdefault(key, {"n": 0, "total": 0.0, "total_sq": 0.0, "wins": 0, "days": {}})
            rec["n"] += 1
            rec["total"] += net
            rec["total_sq"] += net * net
            rec["wins"] += int(net > 0)
            d = rec["days"].setdefault(day, [0, 0.0, 0])
            d[0], d[1], d[2] = d[0] + 1, d[1] + net, d[2] + int(net > 0)
            for old in sorted(rec["days"])[:-LIVE_DAYS]:
                del rec["days"][old]
        self.state_dirty = True

    # --- la mesure à l'essai : ce qui juge les stratégies ---
    def _merge_trial(self, info: dict, trial: dict | None) -> None:
        """Les trades à l'essai d'un test rejoignent la mesure (toutes cryptos réunies)."""
        if not trial:
            return
        info["trial_done"] = trial.get("done") or {}
        info["trial_open"] = int(trial.get("open") or 0)
        stats = self.trial["stats"]
        first = _iso(self.time.now_ms() - (TRIAL_DAYS - 1) * 86_400_000)[:10]
        for key, rec in (trial.get("stats") or {}).items():
            mine = stats.setdefault(key, new_record(days="days" in rec))
            merge_record(mine, rec)
            for day in [d for d in mine.get("days", {}) if d < first]:
                del mine["days"][day]  # on juge sur les 30 derniers jours
        if trial.get("stats"):
            self.trial_dirty, self.trial_cache = True, None
        if trial.get("final"):  # la crypto ne bouge plus : tout ce qui était ouvert a été compté
            info.update(stretches=[], trial_close=False, trial_open=0)
            info.pop("close_at", None)

    def trial_view(self) -> dict:
        """La mesure à l'essai pour le site et pour les verdicts : par stratégie, sortie, sens et unité, sur 30 jours,
        7 jours et aujourd'hui. La fourchette compare les journées entre elles (les trades d'une même journée se
        ressemblent : le marché monte ou baisse pour toutes les cryptos à la fois). Verdict d'une stratégie après
        TRIAL_MIN_DAYS journées et LIVE_MIN_TRADES trades : « recalee » si même le haut de sa fourchette à 95 % est
        négatif, « prouvee » si le bas, durci par le nombre de stratégies comparées, est positif."""
        today = _iso(self.time.now_ms())[:10]
        if self.trial_cache and self.trial_cache[0] == today:
            return self.trial_cache[1]
        day0 = datetime.fromisoformat(today).date()
        week = {(day0 - timedelta(days=k)).isoformat() for k in range(7)}
        month = {(day0 - timedelta(days=k)).isoformat() for k in range(TRIAL_DAYS)}
        stats = self.trial["stats"]
        judged = [k for k, rec in stats.items() if k.startswith("strategie:")]
        alpha = 0.025 / max(len(judged), 1)
        out: dict[str, list] = {"strategie": [], "technique": [], "sortie": [], "sens": [], "unite": []}
        verdicts: dict[str, str] = {}
        for key, rec in stats.items():
            kind, _, name = key.partition(":")
            days = {d: v for d, v in (rec.get("days") or {}).items() if d in month}
            n = sum(v[0] for v in days.values())
            if kind not in out or not n:
                continue
            groups = [(v[0], v[1]) for v in days.values()]
            mean, lo, hi = clustered_bounds(groups)
            day = days.get(today) or [0, 0.0, 0]
            w = [sum(v[0] for d, v in days.items() if d in week), sum(v[1] for d, v in days.items() if d in week)]
            row = {"key": name, "n": n, "all": rec.get("n", n), "win": sum(v[2] for v in days.values()) / n,
                   "mean": mean, "lo": lo if math.isfinite(lo) else None, "hi": hi if math.isfinite(hi) else None,
                   "days": len(days), "today_n": day[0], "today_mean": day[1] / day[0] if day[0] else None,
                   "week_n": w[0], "week_mean": w[1] / w[0] if w[0] else None}
            if kind == "strategie":
                technique_name, tf = name.rsplit("|", 1)
                verdict = None
                if len(days) >= TRIAL_MIN_DAYS and n >= LIVE_MIN_TRADES:
                    if hi < 0:
                        verdict = "recalee"
                    elif clustered_bounds(groups, alpha)[1] > 0:
                        verdict = "prouvee"
                if verdict:
                    verdicts[name] = verdict
                row.update(technique=technique_name, timeframe=tf, tf_label=tf_label(tf), verdict=verdict)
            out[kind].append(row)
        for rows in out.values():
            rows.sort(key=lambda r: -r["mean"])
        every = {}  # tous les trades à l'essai, comptés une fois chacun (par unité de temps), jour par jour
        for key, rec in stats.items():
            if key.startswith("unite:"):
                for d, v in (rec.get("days") or {}).items():
                    if d in month:
                        e = every.setdefault(d, [0, 0.0, 0])
                        e[0], e[1], e[2] = e[0] + v[0], e[1] + v[1], e[2] + v[2]
        n = sum(v[0] for v in every.values())
        mean, lo, hi = clustered_bounds([(v[0], v[1]) for v in every.values()])
        out.update(min_trades=LIVE_MIN_TRADES, min_days=TRIAL_MIN_DAYS, window_days=TRIAL_DAYS)
        view = {"since": self.trial.get("since"), "n": n, "days": len(every),
                "all": sum(rec.get("n", 0) for k, rec in stats.items() if k.startswith("unite:")),
                "win": sum(v[2] for v in every.values()) / n if n else None, "mean": mean if n else None,
                "lo": lo if math.isfinite(lo) else None, "hi": hi if math.isfinite(hi) else None,
                "ranking": out, "verdicts": verdicts}
        self.trial_cache = (today, view)
        return view

    def verdicts(self) -> dict[str, str]:
        """Le verdict de chaque stratégie : il vient de la mesure à l'essai (toutes les combinaisons, sans choix
        préalable), pas des seuls bots choisis. Les stratégies sans verdict restent à confirmer."""
        return dict(self.trial_view()["verdicts"])

    def _judge_strategies(self) -> list[dict]:
        """Une stratégie recalée : ses bots finissent leur trade puis s'arrêtent, sans attendre le prochain test de
        leur crypto. Un verdict levé : ses bots reprennent. Chaque nouveau verdict est annoncé."""
        verdicts = self.verdicts()
        before = self.state.setdefault("verdicts", {})
        events = []
        rows = {r["key"]: r for r in self.trial_view()["ranking"]["strategie"]}
        for key, verdict in verdicts.items():
            if before.get(key) == verdict:
                continue
            row = rows.get(key) or {}
            name, tf = key.rsplit("|", 1)
            facts = (f"{row.get('n')} trades à l'essai sur {row.get('days')} jours, {pct(row.get('mean') or 0.0, 2)} par "
                     "trade en moyenne, frais compris")
            if verdict == "prouvee":
                text = (f"{name} en {tf_label(tf)} est prouvée à l'essai ({facts}) : elle passe en priorité aux "
                        "prochains tests.")
            else:
                text = (f"{name} en {tf_label(tf)} perd nettement à l'essai ({facts}) : ses bots finissent leur trade "
                        "puis s'arrêtent, et les tests ne la prennent plus.")
            events.append(self.event("prouvee" if verdict == "prouvee" else "recalee", text))
        if verdicts != before:
            self.state["verdicts"] = verdicts
            self.state_dirty = True
        coins = self.state["coins"]
        for bot in self.bots.values():
            spec = bot["spec"]
            failed = verdicts.get(strategy_key(spec["technique"], spec["timeframe"])) == "recalee"
            if failed and bot["status"] != "sortie":
                bot["status"] = "sortie"
                self.dirty.add(bot["key"])
            elif not failed and bot["status"] == "sortie":  # le verdict est levé : il reprend sa place
                bot["status"] = "actif" if (coins.get(spec["symbol"]) or {}).get("moving") else "veille"
                self.dirty.add(bot["key"])
        return events

    def ranking(self) -> dict:
        """Le classement des bots choisis, en direct, pour le site : tout le direct, le jour (UTC) et les 7 derniers
        jours. Le verdict affiché est celui de la mesure à l'essai."""
        live = self.state.get("live") or {}
        verdicts = self.state.get("verdicts") or {}
        today = datetime.fromtimestamp(self.time.now_ms() / 1000, tz=timezone.utc).date()
        week = {(today - timedelta(days=k)).isoformat() for k in range(7)}
        out: dict[str, list] = {"strategie": [], "technique": [], "sortie": [], "sens": [], "unite": []}
        for key, rec in live.items():
            kind, _, name = key.partition(":")
            if kind not in out or not rec.get("n"):
                continue
            stats = TradeStats(rec["n"], rec["total"], rec["total_sq"])
            lo, hi = stats.bounds()
            day = rec["days"].get(today.isoformat()) or [0, 0.0, 0]
            w = [sum(v[0] for d, v in rec["days"].items() if d in week),
                 sum(v[1] for d, v in rec["days"].items() if d in week)]
            row = {"key": name, "n": rec["n"], "win": rec["wins"] / rec["n"], "mean": stats.mean,
                   "lo": lo if math.isfinite(lo) else None, "hi": hi if math.isfinite(hi) else None,
                   "today_n": day[0], "today_mean": day[1] / day[0] if day[0] else None,
                   "week_n": w[0], "week_mean": w[1] / w[0] if w[0] else None}
            if kind == "strategie":
                name_, tf = name.rsplit("|", 1)
                row.update(technique=name_, timeframe=tf, tf_label=tf_label(tf), verdict=verdicts.get(name))
            out[kind].append(row)
        for rows in out.values():
            rows.sort(key=lambda r: -(r["mean"] if r["mean"] is not None and math.isfinite(r["mean"]) else -1e9))
        out["min_trades"] = LIVE_MIN_TRADES
        return out

    # --- les cryptos suivies et leurs tests ---
    def _refresh_universe(self, now_ms: int) -> list[dict]:
        self.state["universe_at"] = now_ms
        self.state_dirty = True
        try:
            liquid = liquid_markets(self.exchange, "USDT", MIN_VOLUME)
        except Exception as exc:
            log.warning("Liste des cryptos indisponible (%s) : la précédente est gardée, nouvel essai dans une "
                        "minute.", exc)
            self.state["universe_at"] = now_ms - int(max(0.0, self.universe_every - 60) * 1000)
            return []
        chosen = liquid[:self.settings.coins]
        names = {r.symbol for r in chosen}
        coins = self.state["coins"]
        events = []
        for r in liquid:
            if r.symbol in names or r.symbol in coins:
                info = coins.setdefault(r.symbol, {"status": "en attente de test", "next_test": 0})
                info.update(amplitude=r.amplitude, change=r.change, volume=r.volume, followed=r.symbol in names)
        for symbol, info in coins.items():
            if symbol not in names:
                info["followed"] = False
            if info.get("followed"):
                info.pop("left_at", None)
            else:
                info.setdefault("left_at", now_ms)  # depuis quand elle n'est plus parmi les plus agitées
        self.state["universe"] = sorted(names)
        for symbol, info in coins.items():
            moving = info.get("followed") and (info.get("amplitude") or 0) >= self.settings.min_move
            was = info.get("moving")
            info["moving"] = bool(moving)
            self._stretch(info, bool(moving), now_ms)
            if was and not moving:
                events.append(self.event("veille", f"{symbol.split('/')[0]} passe en veille : pas assez de mouvement "
                                         "(ou sortie de la liste des cryptos agitées).", symbol=symbol))
        for bot in self.bots.values():
            info = coins.get(bot["spec"]["symbol"]) or {}
            if bot["status"] in ("actif", "veille"):
                status = "actif" if info.get("moving") else "veille"
                if status != bot["status"]:
                    bot["status"] = status
                    self.dirty.add(bot["key"])
        waiting = self.tester is not None  # sans testeur, personne ne viendra clore la mesure à l'essai
        for symbol in [s for s, info in coins.items() if not info.get("followed")
                       and not (waiting and info.get("trial_close"))
                       and not any(b["spec"]["symbol"] == s for b in self.bots.values())]:
            del coins[symbol]  # plus suivie, plus aucun bot, mesure à l'essai close : oubliée
            self.candles.forget(symbol)
        return events

    @staticmethod
    def _stretch(info: dict, moving: bool, now_ms: int) -> None:
        """Les périodes pendant lesquelles la crypto bouge assez pour être tradée (`stretches`, et `moving_since` pour
        celle en cours). La mesure à l'essai ne compte que les trades ouverts pendant ces périodes, comme un vrai bot.
        Sans nouvelles depuis 30 minutes (PC éteint), la période d'avant est close à la dernière fois où on l'a vue."""
        since, seen = info.get("moving_since"), int(info.get("seen") or 0)
        if since and (not moving or now_ms - seen > STRETCH_GAP_S * 1000):
            end = now_ms if now_ms - seen <= STRETCH_GAP_S * 1000 else seen
            info["stretches"] = ((info.get("stretches") or []) + [[since, max(end, since)]])[-KEEP_STRETCHES:]
            info["moving_since"] = since = None
            if not moving:
                # Un dernier test comptera ce qui est encore ouvert, à sa valeur du moment : dans une heure, pour ne pas
                # tester pour rien une crypto qui entre et sort de la liste toutes les dix minutes.
                info.update(trial_close=True, close_at=now_ms + CLOSE_DELAY_S * 1000)
        if moving:
            info["moving_since"] = since or now_ms
            info["seen"] = now_ms
            info["trial_close"] = False

    def _trial_args(self, info: dict, final: bool) -> dict:
        active = [list(x) for x in info.get("stretches") or []]
        if info.get("moving_since") and not final:
            active.append([info["moving_since"], None])  # encore en cours : jusqu'au téléchargement des bougies
        return {"done": dict(info.get("trial_done") or {}), "active": active, "final": final}

    def _schedule_tests(self, now_ms: int) -> None:
        if self.tester is None:
            return
        banned = self.state["banned"]
        for key in [k for k, until in banned.items() if until <= now_ms]:
            del banned[key]
        verdicts = None
        for symbol, info in sorted(self.state["coins"].items(), key=lambda kv: -(kv[1].get("amplitude") or 0)):
            closing = bool(info.get("trial_close")) and not info.get("moving")
            if closing and now_ms >= int(info.get("close_at") or 0):
                # Elle ne bouge plus : un dernier test clôt sa mesure à l'essai (aucun bot n'est choisi).
                if self.tester.submit(symbol, (), {}, (), self._trial_args(info, final=True)):
                    info["close_at"] = now_ms + RETEST_S * 1000  # s'il se perd, il sera redemandé
                    self.state_dirty = True
            elif info.get("moving") and now_ms >= int(info.get("next_test") or 0):
                keys = tuple(k for k in banned if k.startswith(symbol + "|"))
                verdicts = self.verdicts() if verdicts is None else verdicts
                keep = tuple(b["spec"] for b in self.bots.values()
                             if b["spec"]["symbol"] == symbol and b["status"] != "sortie")
                if self.tester.submit(symbol, keys, verdicts, keep, self._trial_args(info, final=False)):
                    info["status"] = "test en cours"
                    info["next_test"] = now_ms + RETEST_S * 1000
                    self.state_dirty = True

    def _apply_tests(self, now_ms: int) -> list[dict]:
        events = []
        if self.tester is None:
            return events
        while True:
            try:
                result = self.tester.results.get_nowait()
            except queue.Empty:
                break
            events += self.apply_test(result, now_ms)
        return events

    def apply_test(self, result: dict, now_ms: int) -> list[dict]:
        """Le résultat d'un re-test. Les bots en place gardent leur place (un classement qui bouge ne les arrête plus) :
        leur fiche de backtest est rafraîchie, et les places libres de la crypto reçoivent les mieux classées. Les
        trades de toutes les combinaisons rejoignent la mesure à l'essai."""
        symbol = result["symbol"]
        info = self.state["coins"].setdefault(symbol, {"next_test": now_ms + RETEST_S * 1000})
        self.state_dirty = True
        if result.get("error"):
            if result.get("final"):
                info["close_at"] = now_ms + 600_000  # la clôture de sa mesure sera redemandée dans 10 minutes
            else:
                info.update(status="test impossible", error=result["error"])
                info["next_test"] = now_ms + 600_000  # nouvel essai dans 10 minutes
            return []
        self._merge_trial(info, result.get("trial"))
        if result.get("final"):
            return []
        verdicts = self.state.get("verdicts") or {}  # un verdict tombé pendant le test passe avant son résultat
        chosen = [r for r in result.get("chosen") or []
                  if verdicts.get(strategy_key(r["technique"], r["timeframe"])) != "recalee"]
        mine = [b for b in self.bots.values() if b["spec"]["symbol"] == symbol]
        kept = {r["key"]: r for r in result.get("kept") or []}
        for bot in mine:
            r = kept.get(bot["key"])
            if r:
                bot["backtest"] = backtest_of(r)
                bot["label"], bot["label_text"], bot["tested"] = r["label"], r["label_text"], _iso(now_ms)
                self.dirty.add(bot["key"])
        events = []
        places = self.settings.bots_per_coin - sum(1 for b in mine if b["status"] != "sortie")
        live = sum(1 for b in self.bots.values() if b["status"] != "sortie")
        added = 0
        for r in chosen:
            if places <= added or live >= self.settings.max_bots:
                break
            if r["key"] in self.bots:
                continue
            bot = self.add_bot(r, now_ms)
            bot["status"] = "actif" if info.get("moving", True) else "veille"
            live, added = live + 1, added + 1
            spec = spec_from(r)
            events.append(self.event("nouveau", f"Nouveau bot sur {spec.coin} : {spec.technique} en "
                                     f"{tf_label(spec.timeframe)}, {SIDE_LABELS[spec.side]} (choisi sur l'étude et la "
                                     f"validation ; {LABEL_SHORT.get(r.get('label'), 'test final à venir')}).",
                                     bot=bot["id"], symbol=symbol))
        info.update(status="actif" if mine or added else "aucune stratégie gagnante", tested=_iso(now_ms),
                    n_tested=result.get("tested", 0), n_eligible=result.get("eligible", 0), best=result.get("best") or [],
                    holdout=result.get("holdout"), holdout_eligible=result.get("holdout_eligible"), error=None)
        return events

    def _retire(self, now_ms: int) -> list[dict]:
        events = []
        for key, bot in list(self.bots.items()):
            book = self.book(bot)
            s = book.s
            reason, ban = None, False
            if s["dead"]:
                reason, ban = s["dead"], True
            elif s["position"] is None and s["pending"] is None:
                if s["cash"] < s["start"] * (1 - REPLACE_DRAWDOWN):
                    reason, ban = "a perdu plus de la moitié de son capital", True
                elif elimination_reason(TradeStats.from_dict(s["stats"]), ELIMINATE_AFTER):
                    reason, ban = elimination_reason(TradeStats.from_dict(s["stats"]), ELIMINATE_AFTER), True
                elif bot["status"] == "sortie":
                    reason = "sa stratégie est recalée : elle perd nettement à l'essai, toutes cryptos réunies"
                elif now_ms - int((self.state["coins"].get(bot["spec"]["symbol"]) or {}).get("left_at") or now_ms) \
                        >= UNFOLLOWED_S * 1000:
                    reason = "sa crypto n'est plus parmi les plus agitées depuis 6 heures"
            if not reason:
                continue
            spec = spec_from(bot["spec"])
            totals = self.state["retired_totals"]
            totals.update(start=totals["start"] + s["start"], end=totals["end"] + s["cash"],
                          count=totals["count"] + s["count"], wins=totals["wins"] + s["wins"], bots=totals["bots"] + 1)
            self.state["retired"].append({"id": bot["id"], "spec": bot["spec"], "reason": reason, "until": _iso(now_ms),
                                          "started": bot["started"], "start": s["start"], "end": s["cash"],
                                          "count": s["count"], "wins": s["wins"]})
            del self.state["retired"][:-KEEP_RETIRED]
            if ban:
                self.state["banned"][key] = now_ms + BAN_S * 1000
            del self.bots[key]
            self.dirty.discard(key)
            if self.folder:
                try:
                    (self.folder / DETAIL_DIR / f"{bot['id']}.json").unlink()
                except OSError:
                    pass
            events.append(self.event("arret", f"Bot arrêté sur {spec.coin} ({spec.technique}, "
                                     f"{tf_label(spec.timeframe)}) : {reason}. Résultat : "
                                     f"{pct(s['cash'] / s['start'] - 1)}.", symbol=spec.symbol, bot=bot["id"]))
        return events

    def _refresh_mood(self, now_ms: int) -> None:
        """L'humeur du marché : l'indice peur et avidité du jour, une fois par heure."""
        self.state["mood_at"] = now_ms
        self.state_dirty = True
        if self.mood is None:
            return
        try:
            mood = self.mood()
            if mood:
                self.state["mood"] = mood
        except Exception as exc:  # l'humeur est un plus : jamais bloquante
            log.debug("Indice peur et avidité indisponible : %s", exc)

    # --- sur le disque ---
    def save(self, now_ms: int | None = None) -> None:
        """Le résumé à chaque tour ; le compte complet d'un bot quand il change (trade, nouveau test), et tous à tour
        de rôle en dix minutes (jamais des centaines de fichiers d'un coup) ; la mesure à l'essai quand un test l'a
        complétée. Sous Windows, une écriture refusée un instant (le site lisait) est retentée."""
        if not self.folder:
            return
        now = self.clock()
        checkpoint = now - self.checkpoint >= CHECKPOINT_S
        if not self.rotation:
            self.rotation = sorted(self.bots)
        turn = max(1, math.ceil(len(self.bots) / 100))  # à 5 secondes le tour, toutes les fiches en dix minutes
        again, self.rotation = self.rotation[:turn], self.rotation[turn:]
        for key in list(self.dirty) + [k for k in again if k not in self.dirty]:
            bot = self.bots.get(key)
            if bot:
                self._write(self.folder / DETAIL_DIR / f"{bot['id']}.json", bot)
        self.dirty.clear()
        if checkpoint:
            self.checkpoint = now
        if self.state_dirty or checkpoint:
            self._write(self.folder / STATE_FILE, self.state)
            self.state_dirty = False
        if self.trial_dirty:
            self._write(self.folder / TRIAL_FILE, self.trial)
            self.trial_dirty = False
        self._write(self.folder / SWARM_FILE, self.summary())
        self.beat()

    def _write(self, path: Path, payload: dict) -> None:
        for attempt in range(3):
            try:
                save_json(path, payload)
                return
            except OSError as exc:
                if attempt == 2:
                    log.debug("%s non écrit ce tour-ci : %s", path.name, exc)
                else:
                    time.sleep(0.1)

    def beat(self) -> None:
        if self.folder:
            with self.beat_lock:
                try:
                    atomic_write(self.folder / LOCK_FILE, json.dumps({"pid": os.getpid(), "t": self.clock()}))
                except OSError as exc:
                    log.debug("Signal de vie non écrit : %s", exc)

    def release(self) -> None:
        if self.folder:
            try:
                (self.folder / LOCK_FILE).unlink()
            except OSError:
                pass

    def _trial_summary(self) -> dict:
        """La mesure à l'essai pour le site. Un bot à l'essai : une combinaison sur une crypto qui bouge."""
        view = self.trial_view()
        moving = [c for c in self.state["coins"].values() if c.get("moving")]
        return {**{k: view[k] for k in ("since", "n", "all", "days", "win", "mean", "lo", "hi", "ranking")},
                "bots": sum(int(c.get("n_tested") or 0) for c in moving),
                "coins": sum(1 for c in moving if c.get("n_tested")),
                "positions": sum(int(c.get("trial_open") or 0) for c in moving)}

    def _holdout_summary(self) -> dict:
        """Le test final des combinaisons que le labo choisirait aujourd'hui, toutes cryptos suivies réunies : il n'a
        pas servi à les choisir (dernier test de chaque crypto)."""
        held = [c["holdout"] for c in self.state["coins"].values() if c.get("followed") and c.get("holdout")]
        n = sum(h["n"] for h in held)
        return {"n": n, "coins": len(held), "mean": sum(h["total"] for h in held) / n if n else None,
                "win": sum(h["wins"] for h in held) / n if n else None}

    def _reference_summary(self) -> dict | None:
        if not self.reference:
            return None
        totals = self.reference.get("totals") or {}
        return {"saved": self.reference["saved"],
                **{k: totals.get(k) for k in ("count", "win_rate", "pnl_pct", "bots", "retired")}}

    def summary(self) -> dict:
        """Ce que lit le site : les cryptos, chaque bot en bref, les totaux, les événements, les classements, la
        mesure à l'essai, le test final et le point de référence."""
        verdicts = self.state.get("verdicts") or {}
        bots = [bot_brief(b) | {"live": verdicts.get(strategy_key(b["spec"]["technique"], b["spec"]["timeframe"]))}
                for b in self.bots.values()]
        retired = self.state["retired_totals"]
        start = sum(b["start"] for b in bots) + retired["start"]
        value = sum(b["value"] for b in bots) + retired["end"]
        count = sum(b["count"] for b in bots) + retired["count"]
        wins = sum(b["wins"] for b in bots) + retired["wins"]
        coins = []
        for symbol, info in self.state["coins"].items():
            mine = [b for b in bots if b["symbol"] == symbol]
            coins.append({"symbol": symbol, "coin": symbol.split("/")[0], **{k: info.get(k) for k in (
                "status", "amplitude", "change", "volume", "followed", "moving", "tested", "n_tested", "n_eligible",
                "best", "error")}, "next_test": _iso(info["next_test"]) if info.get("next_test") else None,
                "bots": len(mine), "positions": sum(1 for b in mine if b["position"]),
                "pnl": sum(b["value"] - b["start"] for b in mine),
                "price": next((b["last_price"] for b in mine if b["last_price"]), None)})
        coins.sort(key=lambda c: (not c["followed"], -(c["amplitude"] or 0)))
        return {"version": 2, "created": self.state["created"], "updated": self.state.get("updated"),
                "settings": asdict(self.settings), "max_bots": self.settings.max_bots,
                "totals": {"bots": len(bots), "active": sum(1 for b in bots if b["status"] == "actif"),
                           "positions": sum(1 for b in bots if b["position"]), "start": start, "value": value,
                           "pnl": value - start, "pnl_pct": value / start - 1 if start else None, "count": count,
                           "wins": wins, "win_rate": wins / count if count else None, "retired": retired["bots"],
                           "coins": len(self.state["universe"]),
                           "moving": sum(1 for c in self.state["coins"].values() if c.get("moving"))},
                "coins": coins, "bots": bots, "events": list(reversed(self.state["events"]))[:80],
                "retired": list(reversed(self.state["retired"]))[:40], "mood": self.state.get("mood"),
                "ranking": self.ranking(), "trial": self._trial_summary(), "holdout": self._holdout_summary(),
                "reference": self._reference_summary(),
                "tester": self.tester.status() if self.tester else None}


def bot_brief(bot: dict) -> dict:
    """Un bot en bref : ce qu'affichent les listes."""
    spec = spec_from(bot["spec"])
    book = Book(spec, state=bot["book"])
    s = book.s
    last = finite(bot.get("last_price"))
    value = book.equity(last)
    trades = s["trades"]
    lt = trades[-1] if trades else None
    return {"id": bot["id"], "symbol": spec.symbol, "coin": spec.coin, "timeframe": spec.timeframe,
            "tf_label": tf_label(spec.timeframe), "team": bot.get("team"), "technique": spec.technique,
            "family": spec.family, "side": spec.side, "target_r": spec.target_r, "leverage": spec.leverage,
            "stop_mode": spec.stop_mode, "exit": exit_label(spec.target_r, spec.stop_mode),
            "status": bot["status"], "label": bot.get("label"), "start": s["start"], "value": value,
            "pnl": value - s["start"], "pnl_pct": value / s["start"] - 1, "count": s["count"], "wins": s["wins"],
            "win_rate": s["wins"] / s["count"] if s["count"] else None, "dead": s["dead"], "last_price": last,
            "position": _position_view(book, last), "started": bot.get("started"),
            "proba": {k: v for k, v in bot["proba"].items() if k != "text"} if bot.get("proba") else None,
            "signal": bot.get("signal"),
            "last_trade": {k: lt.get(k) for k in ("exit_ts", "roi", "net", "reason", "side")} if lt else None,
            "backtest": {k: (bot.get("backtest") or {}).get(k) for k in ("sv_n", "sv_mean", "test_n", "test_mean",
                                                                          "total_return", "drawdown")}}


def bot_detail(bot: dict) -> dict:
    """Tout sur un bot : sa page."""
    spec = spec_from(bot["spec"])
    out = bot_brief(bot)
    prof = (bot.get("backtest") or {}).get("profile")
    out.update(rule=entry_rule(spec), exit_rule=exit_rule(spec), side_label=SIDE_LABELS[spec.side],
               side_hint=SIDE_HINTS[spec.side], label_text=bot.get("label_text"), tested=bot.get("tested"),
               reading=bot.get("reading"), insights=insights(prof), backtest=bot.get("backtest") or {},
               drawdown=bot["book"]["drawdown"],
               trades=list(reversed(bot["book"]["trades"])), pending=bot["book"]["pending"],
               team_title=TEAM_TITLES.get(bot.get("team"), ""))
    return out


def swarm_running(folder: Path) -> bool:
    from .fleet import fleet_running
    return fleet_running(folder)


def run(swarm: Swarm, seconds: float = 5.0, once: bool = False, sleep=time.sleep) -> None:
    """La boucle sans fin. Réseau coupé : le tour est retenté de plus en plus tard (jusqu'à une minute)."""
    failures = 0
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(10):
            swarm.beat()

    if not once:
        threading.Thread(target=heartbeat, name="signal-de-vie", daemon=True).start()
    try:
        while True:
            try:
                for e in swarm.cycle():
                    log.info("%s", e["text"], extra=ALERT if e["kind"] in ("arret",) else None)
                if failures:
                    log.info("Bots : la connexion est revenue, ils reprennent.")
                failures = 0
            except Exception as exc:  # le réseau coupe : on retente plus tard
                failures += 1
                if failures in (1, 5) or failures % 60 == 0:
                    log.warning("Bots : %s (tour %d raté, ils réessaient tout seuls)", exc, failures)
            if once:
                return
            sleep(seconds if not failures else min(60.0, seconds * 2 ** min(failures, 4)))
    finally:
        stop.set()
        swarm.release()
