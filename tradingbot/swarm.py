"""L'essaim : des centaines de bots en argent fictif, sur les cryptos qui bougent le plus, retestés en continu.

Comment il travaille, sans jamais s'arrêter :
1. Les cryptos : toutes les 10 minutes, les N paires USDT les plus agitées sur 24 h (au moins 5 M$ échangés par jour,
   sans monnaies stables ni tokens à levier). Une crypto qui sort de la liste, ou dont l'amplitude sur 24 h tombe sous
   le seuil (« pas assez de mouvement »), passe en veille : ses bots n'ouvrent plus de trade, ils gèrent ceux en cours.
2. Le labo en direct : chaque crypto est retestée toutes les 3 heures, et dès qu'elle entre dans la liste. Toutes les
   techniques de la bibliothèque, à l'achat et à la vente à découvert, avec quatre façons de sortir (par la règle,
   objectif 2R, stop suiveur, objectif 2R + stop sécurisé), sur cinq unités de temps (1 min à 4 h), sur l'historique
   récent, frais des contrats à terme compris. Une combinaison ne devient un bot que si
   elle gagne sur les trois périodes de cet historique (étude, validation, test final), avec assez de trades. Au plus
   K bots par crypto, des techniques et des unités variées. Les tests tournent à part (un fil pour télécharger, un
   processus pour calculer) : le direct n'attend jamais.
3. Les bots : le même moteur que le backtest (fleet.Book), avec tout leur capital fictif à chaque trade et le levier
   de leur horizon, réduit si le stop est loin. Un bot que le dernier test ne garde plus finit son trade puis s'arrête ;
   un bot liquidé, à moitié ruiné ou nettement perdant après 20 trades est arrêté, et sa combinaison mise de côté 24 h.
4. Les agents : pour chaque bot, dans quelles conditions sa stratégie a gagné ou perdu dans le backtest (tendance de
   fond, volatilité, RSI, volume, heure), sa probabilité de gain dans les conditions du moment, et après chaque trade
   réel, pourquoi il a gagné ou perdu. Ce sont des mesures, jamais des ordres : un bot n'entre que sur le signal de sa
   règle testée. « Apprendre », c'est le re-test continu sur des données fraîches, pas des réglages changés après une
   perte (c'est ainsi qu'on finit par sur-ajuster le passé).
5. Le classement en direct : chaque trade fini compte pour sa stratégie (une technique dans une unité de temps, toutes
   cryptos réunies). Après 30 trades, une stratégie nettement gagnante (seuil durci par le nombre de stratégies) est
   « prouvée » et passe en priorité aux tests ; une stratégie nettement perdante est « recalée » : les tests ne la
   prennent plus et ses bots s'arrêtent après leur trade.

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
from statistics import NormalDist

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
from .risk import TradeStats, elimination_reason
from .scanner import liquid_markets

log = logging.getLogger(__name__)

SWARM_FILE = "essaim.json"  # le résumé que lit le site, réécrit à chaque tour
STATE_FILE = "essaim-etat.json"  # la mémoire de l'essaim (cryptos, tests, mises de côté), reprise au redémarrage
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
MAX_COINS, MAX_BOTS_PER_COIN = 80, 10
SHRINK = 20  # la probabilité estimée est tirée vers la moyenne de la stratégie, comme si on avait 20 trades de plus
LIVE_MIN_TRADES = 30  # trades en direct d'une stratégie avant de la déclarer prouvée ou recalée
LIVE_DAYS = 14  # jours gardés pour le classement du jour et des 7 derniers jours


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
    """Gagnante, frais compris, sur l'étude, la validation et le test final, avec assez de trades, sans liquidation."""
    return (not r["liquidated"] and r["sv_n"] >= MIN_TRADES.get(tf, 15) and r["study_n"] >= MIN_PART_TRADES
            and r["valid_n"] >= MIN_PART_TRADES and r["study_mean"] > 0 and r["valid_mean"] > 0
            and (r["test_n"] < 5 or r["test_mean"] > 0))


def _label(r: dict) -> tuple[str, str]:
    if r["test_n"] >= 5:
        return "3", "Gagnant sur les 3 périodes de son historique"
    return "2", "Gagnant sur l'étude et la validation (trop peu de trades récents pour le test final)"


def strategy_key(technique_name: str, timeframe: str) -> str:
    """Une stratégie, pour le classement en direct : une technique dans une unité de temps (toutes cryptos réunies)."""
    return f"{technique_name}|{timeframe}"


def exit_label(target_r: float, stop_mode: str) -> str:
    if stop_mode == "suiveur":
        return "stop suiveur"
    if stop_mode == "securise":
        return "objectif 2R + stop sécurisé" if target_r else "stop sécurisé"
    return "objectif 2R" if target_r else "sortie par la règle"


def _rank_key(r: dict) -> float:
    score = r["score"]
    return -score if math.isfinite(score) else (-1e9 if score > 0 else 1e9)


def _choose(rows: list[dict], k: int, verdicts: dict[str, str] | None = None) -> list[dict]:
    """Les k mieux classées d'une crypto : des familles et des unités de temps variées (au plus 2 par unité, une
    combinaison par technique et unité). Ce que le direct a appris passe avant : une stratégie prouvée en direct
    (toutes cryptos réunies) est prise en premier, une stratégie recalée en direct n'est plus prise."""
    verdicts = verdicts or {}

    def verdict(r):
        return verdicts.get(strategy_key(r["technique"], r["timeframe"]))

    rows = [r for r in rows if verdict(r) != "recalee"]
    ranked = sorted(rows, key=lambda r: (verdict(r) != "prouvee", _rank_key(r)))
    chosen, seen, per_tf, families = [], set(), {}, set()
    for strict in (True, False):
        for r in ranked:
            if len(chosen) >= k:
                return chosen
            what = (r["timeframe"], r["technique"])
            if what in seen or per_tf.get(r["timeframe"], 0) >= 2:
                continue
            if strict and (r["family"], r["side"]) in families:
                continue
            chosen.append(r)
            seen.add(what)
            per_tf[r["timeframe"]] = per_tf.get(r["timeframe"], 0) + 1
            families.add((r["family"], r["side"]))
    return chosen


def retest_coin(symbol: str, frames: dict[str, pd.DataFrame], settings: dict, banned: tuple[str, ...] = (),
                verdicts: dict[str, str] | None = None, ex: ExecutionParams = FUTURES) -> dict:
    """Toutes les combinaisons sur une crypto : le travail d'un re-test (envoyé à un processus à part). `verdicts` :
    ce que le direct a appris de chaque stratégie (prouvée, recalée)."""
    s = SwarmSettings(**settings)
    verdicts = verdicts or {}
    rows, books, feats = [], {}, {}
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
                        if _eligible(row, tf):
                            books[row["key"]] = book
                except Exception as exc:  # des bougies étranges n'arrêtent jamais le test de la crypto
                    log.warning("%s %s %s : combinaison ignorée (%s)", symbol, tf, name, exc)
    good = [r for r in rows if r["key"] in books and r["key"] not in banned]
    chosen = []
    for r in _choose(good, s.bots_per_coin, verdicts):
        tf = r["timeframe"]
        code, text = _label(r)
        trades = books[r["key"]].s["trades"]
        prof = profile(trades, feats[tf], timeframe_to_ms(tf))
        chosen.append({**r, "label": code, "label_text": text, "profile": prof,
                       "curve": _curve(trades, int(frames[tf]["ts"].iloc[0]), s.capital)})
    best = sorted(rows, key=lambda r: -r["score"] if math.isfinite(r["score"]) else 1e9)[:12]
    return {"symbol": symbol, "tested": len(rows), "eligible": len(good), "chosen": chosen,
            "best": [{k: r[k] for k in ("timeframe", "technique", "side", "target_r", "stop_mode", "sv_n", "sv_mean",
                                        "test_n", "test_mean", "total_return", "drawdown")}
                     | {"eligible": r["key"] in books, "live": verdicts.get(strategy_key(r["technique"], r["timeframe"]))}
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

    def submit(self, symbol: str, banned: tuple[str, ...] = (), verdicts: dict[str, str] | None = None) -> bool:
        with self.lock:
            if symbol in self.pending:
                return False
            self.pending.add(symbol)
        self.jobs.put((symbol, tuple(banned), dict(verdicts or {})))
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
                frames[tf] = fetch_history(exchange, symbol, tf, now - TEST_DAYS[tf] * 86_400_000, now)
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
            symbol, banned, verdicts = self.jobs.get()
            with self.lock:
                self.current = symbol
            try:
                frames = self._frames(exchange, symbol)
                result = None
                if pool is not None:
                    try:
                        result = pool.submit(retest_coin, symbol, frames, settings, banned,
                                             verdicts).result(RETEST_TIMEOUT_S)
                    except FutureTimeout:
                        pool = self._replace(pool)
                        raise RuntimeError("test trop long, le processus de calcul a été remplacé") from None
                    except (BrokenProcessPool, OSError, RuntimeError, pickle.PicklingError) as exc:
                        log.warning("Calcul à part interrompu (%s) : il continue dans le fil.", exc)
                        pool = None
                if result is None:
                    result = retest_coin(symbol, frames, settings, banned, verdicts)
                self.results.put(result)
            except Exception as exc:  # jamais fatal : la crypto sera retestée plus tard
                log.warning("Test de %s impossible : %s", symbol, exc)
                self.results.put({"symbol": symbol, "error": str(exc)[:200]})
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


class CandleStore:
    """Les bougies de chaque (crypto, unité), gardées en mémoire et complétées à chaque tour par les dernières
    seulement : des centaines de bots sans télécharger mille bougies à chaque minute."""

    def __init__(self, exchange):
        self.exchange = exchange
        self.frames: dict[tuple[str, str], pd.DataFrame] = {}
        self.asked: dict[tuple[str, str], int] = {}  # la plus longue fenêtre déjà demandée

    def closed(self, symbol: str, timeframe: str, limit: int, now_ms: int) -> pd.DataFrame:
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
        return df[df["ts"] + tf_ms <= now_ms]

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
        self.candles = CandleStore(exchange)
        self.next_fetch: dict[tuple[str, str], int] = {}
        self.fetch_failures: dict[tuple[str, str], int] = {}
        self.dirty: set[str] = set()
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

    def event(self, kind: str, text: str, **extra) -> dict:
        e = {"t": _iso(self.clock() * 1000), "kind": kind, "text": text, **extra}
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
        now_ms = int(self.clock() * 1000) if now_ms is None else now_ms
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
                closed = self.candles.closed(symbol, tf, limit, now_ms)
            except Exception as exc:  # une crypto qui ne répond pas ne bloque jamais les autres
                fails = self.fetch_failures[(symbol, tf)] = self.fetch_failures.get((symbol, tf), 0) + 1
                if fails in (1, 10) or fails % 60 == 0:  # pas une ligne par minute dans le journal
                    log.warning("%s %s : bougies indisponibles (%s), nouvel essai dans une minute", symbol, tf, exc)
                self.next_fetch[(symbol, tf)] = now_ms + 60_000
                continue
            self.fetch_failures.pop((symbol, tf), None)
            if closed.empty:
                continue
            self.next_fetch[(symbol, tf)] = int(closed["ts"].iloc[-1]) + 2 * tf_ms + 2000
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
        day = _iso(self.clock() * 1000)[:10]
        live = self.state.setdefault("live", {})
        for key in (f"strategie:{strategy_key(spec.technique, spec.timeframe)}", f"technique:{spec.technique}",
                    f"sortie:{exit_label(spec.target_r, spec.stop_mode)}", f"sens:{spec.side}",
                    f"unite:{spec.timeframe}"):
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

    def verdicts(self) -> dict[str, str]:
        """Après au moins 30 trades en direct : « recalee » si même le haut de sa fourchette à 95 % est négatif,
        « prouvee » si le bas de sa fourchette est positif avec un seuil durci par le nombre de stratégies comparées
        (sinon la chance en ferait gagner). Les autres restent à confirmer."""
        live = self.state.get("live") or {}
        keys = [k for k in live if k.startswith("strategie:")]
        z = NormalDist().inv_cdf(1 - 0.025 / max(len(keys), 1))
        out = {}
        for key in keys:
            rec = live[key]
            if rec["n"] < LIVE_MIN_TRADES:
                continue
            stats = TradeStats(rec["n"], rec["total"], rec["total_sq"])
            if stats.bounds()[1] < 0:
                out[key.split(":", 1)[1]] = "recalee"
            elif stats.bounds(z)[0] > 0:
                out[key.split(":", 1)[1]] = "prouvee"
        return out

    def _judge_strategies(self) -> list[dict]:
        """Une stratégie recalée en direct : ses bots finissent leur trade puis s'arrêtent, sans attendre le prochain
        test de leur crypto. Chaque changement de verdict est annoncé."""
        verdicts = self.verdicts()
        before = self.state.setdefault("verdicts", {})
        events = []
        live = self.state.get("live") or {}
        for key, verdict in verdicts.items():
            if before.get(key) == verdict:
                continue
            rec = live.get(f"strategie:{key}") or {}
            name, tf = key.rsplit("|", 1)
            mean = rec.get("total", 0.0) / rec["n"] if rec.get("n") else 0.0
            if verdict == "prouvee":
                text = (f"{name} en {tf_label(tf)} est prouvée en direct ({rec.get('n')} trades, {pct(mean, 2)} par trade "
                        "en moyenne, frais compris) : elle passe en priorité aux prochains tests.")
            else:
                text = (f"{name} en {tf_label(tf)} perd nettement en direct ({rec.get('n')} trades, {pct(mean, 2)} par "
                        "trade) : ses bots finissent leur trade puis s'arrêtent, et les tests ne la prennent plus.")
            events.append(self.event("prouvee" if verdict == "prouvee" else "recalee", text))
        self.state["verdicts"] = verdicts
        if verdicts != before:
            self.state_dirty = True
        for bot in self.bots.values():
            spec = bot["spec"]
            if verdicts.get(strategy_key(spec["technique"], spec["timeframe"])) == "recalee" \
                    and bot["status"] != "sortie":
                bot["status"] = "sortie"
                self.dirty.add(bot["key"])
        return events

    def ranking(self) -> dict:
        """Le classement des stratégies pour le site : tout le direct, le jour (UTC) et les 7 derniers jours."""
        live = self.state.get("live") or {}
        verdicts = self.state.get("verdicts") or {}
        today = datetime.fromtimestamp(self.clock(), tz=timezone.utc).date()
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
        for symbol in [s for s, info in coins.items() if not info.get("followed")
                       and not any(b["spec"]["symbol"] == s for b in self.bots.values())]:
            del coins[symbol]  # plus suivie et plus aucun bot : oubliée
            self.candles.forget(symbol)
        return events

    def _schedule_tests(self, now_ms: int) -> None:
        if self.tester is None:
            return
        banned = self.state["banned"]
        for key in [k for k, until in banned.items() if until <= now_ms]:
            del banned[key]
        verdicts = None
        for symbol, info in sorted(self.state["coins"].items(), key=lambda kv: -(kv[1].get("amplitude") or 0)):
            if info.get("moving") and now_ms >= int(info.get("next_test") or 0):
                keys = tuple(k for k in banned if k.startswith(symbol + "|"))
                verdicts = self.verdicts() if verdicts is None else verdicts
                if self.tester.submit(symbol, keys, verdicts):
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
        """Le résultat d'un re-test : les nouvelles combinaisons gagnantes deviennent des bots, celles que le test ne
        garde plus finissent leur trade puis s'arrêtent."""
        symbol = result["symbol"]
        info = self.state["coins"].setdefault(symbol, {"next_test": now_ms + RETEST_S * 1000})
        self.state_dirty = True
        if result.get("error"):
            info.update(status="test impossible", error=result["error"])
            info["next_test"] = now_ms + 600_000  # nouvel essai dans 10 minutes
            return []
        verdicts = self.state.get("verdicts") or {}  # un verdict tombé pendant le test passe avant son résultat
        chosen = [r for r in result.get("chosen") or []
                  if verdicts.get(strategy_key(r["technique"], r["timeframe"])) != "recalee"]
        info.update(status="actif" if chosen else "aucune stratégie gagnante", tested=_iso(now_ms),
                    n_tested=result.get("tested", 0), n_eligible=result.get("eligible", 0), best=result.get("best") or [],
                    error=None)
        keys = {r["key"] for r in chosen}
        events = []
        for bot in [b for b in self.bots.values() if b["spec"]["symbol"] == symbol]:
            if bot["key"] in keys:
                r = next(x for x in chosen if x["key"] == bot["key"])
                bot["backtest"] = backtest_of(r)
                bot["label"], bot["label_text"], bot["tested"] = r["label"], r["label_text"], _iso(now_ms)
                if bot["status"] == "sortie":
                    bot["status"] = "actif" if info.get("moving", True) else "veille"
                self.dirty.add(bot["key"])
            elif bot["status"] != "sortie":
                bot["status"] = "sortie"
                self.dirty.add(bot["key"])
        live = sum(1 for b in self.bots.values() if b["status"] != "sortie")
        for r in chosen:
            if r["key"] in self.bots:
                continue
            if live >= self.settings.max_bots:
                break
            bot = self.add_bot(r, now_ms)
            bot["status"] = "actif" if info.get("moving", True) else "veille"
            live += 1
            spec = spec_from(r)
            events.append(self.event("nouveau", f"Nouveau bot sur {spec.coin} : {spec.technique} en "
                                     f"{tf_label(spec.timeframe)}, {SIDE_LABELS[spec.side]} ({r['label_text'].lower()}).",
                                     bot=bot["id"], symbol=symbol))
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
                    reason = "le dernier test ne le garde plus"
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
        """Le résumé à chaque tour ; le compte complet d'un bot quand il change (trade, nouveau test) et toutes les
        10 minutes. Sous Windows, une écriture refusée un instant (le site lisait) est retentée."""
        if not self.folder:
            return
        now = self.clock()
        checkpoint = now - self.checkpoint >= CHECKPOINT_S
        for key in list(self.bots) if checkpoint else list(self.dirty):
            bot = self.bots.get(key)
            if bot:
                self._write(self.folder / DETAIL_DIR / f"{bot['id']}.json", bot)
        self.dirty.clear()
        if checkpoint:
            self.checkpoint = now
        if self.state_dirty or checkpoint:
            self._write(self.folder / STATE_FILE, self.state)
            self.state_dirty = False
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

    def summary(self) -> dict:
        """Ce que lit le site : les cryptos, chaque bot en bref, les totaux, les événements, le classement."""
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
                "ranking": self.ranking(),
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
