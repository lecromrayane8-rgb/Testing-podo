"""Le bot de tendance : la seule règle qui a tenu au grand test du 13/11/2026 (`audit/long.py`), en argent fictif.

La règle, fixée d'avance (des seuils ronds, jamais ajustés sur les données) : chaque jour, à la clôture de la bougie d'un
jour, on compte combien de moyennes (50, 100 et 200 jours) sont sous le prix de clôture. Le compte tient en crypto un
tiers de sa valeur par moyenne dépassée : rien, un tiers, deux tiers ou tout. L'ordre part à l'ouverture du jour
suivant, au marché, frais et glissement du comptant compris. Jamais de levier, jamais de vente à découvert.

Une seule logique : `replay` rejoue la règle sur des bougies d'un jour. Le compte fictif du site est ce même rejeu depuis
son jour de départ : chaque nouveau jour ajoute une bougie, donc le « direct » est par construction le backtest qui
continue, et un redémarrage ne change rien. La bougie du jour en cours (la dernière) ne décide jamais rien : elle donne
le prix du moment et l'ordre parti à son ouverture.

Les comptes « à risque » (13/11/2026, demande de l'utilisateur : « prendre des risques », « des stop-loss suiveurs »),
définis AVANT d'être mesurés et jamais ajustés ensuite :
- le levier : le compte tient en crypto `LEVERAGE` fois ce que tient le compte normal (×2 : « tout » devient le
  double de sa valeur). Ce qu'il emprunte coûte le financement des contrats à terme, compté chaque jour : le VRAI,
  nuit par nuit, quand il est connu (`Funding` : l'historique embarqué de 2020 à 2026, puis une lecture par jour),
  sinon `FUTURES.funding_rate_8h` (0,01 % toutes les 8 heures, environ 11 % par an). Jusqu'au 14/11/2026, seul ce taux
  fixe était compté ; la relecture indépendante a montré qu'il flattait ces comptes (emprunter coûte presque le
  double quand le marché monte, c'est-à-dire quand le compte emprunte), et l'utilisateur a demandé le vrai coût.
  Le coût d'une nuit, une fois écrit, ne change plus. Tant qu'il emprunte, il est remis à son
  levier dès qu'il s'en écarte de plus de `BAND` (10 %). Il est liquidé, et vaut alors zéro pour toujours, si sa
  valeur ne couvre plus la marge de maintenance de sa position (`fleet.MAINTENANCE`), au plus bas de la journée ;
- le stop suiveur : le « chandelier » de Chuck LeBeau avec ses réglages d'origine, le plus haut des 22 derniers jours
  moins 3 bougies moyennes (moyenne simple de l'amplitude vraie sur 22 jours). Si une clôture passe dessous, le
  compte vend tout à l'ouverture suivante ; il revient quand une clôture repasse au-dessus de la ligne.
Les quatre comptes (`VARIANTS` : normal, normal avec stop, à risque, à risque avec stop) sont rejoués par la même
fonction ; sans levier ni stop, rien ne change au compte normal.

Rien ne part sur une plateforme : ce fichier ne passe aucun ordre et ne lit aucune clé."""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import funding_history
from .backtest import BacktestResult, Trade
from .broker import atomic_write
from .data import COLUMNS, ohlcv_to_frame
from .execution import FUTURES, ExecutionParams
from .fleet import MAINTENANCE
from .robustness import ROBUST, RobustnessRow, evaluate, format_robustness

log = logging.getLogger(__name__)

AVERAGES = (50, 100, 200)  # en jours : les trois moyennes de la règle, un tiers du compte chacune
SYMBOLS = ("BTC/USDT", "ETH/USDT")  # les deux grandes cryptos, les seules où la règle a été mesurée sur trois périodes
NAMES = {"BTC": "Bitcoin", "ETH": "Ether"}
TIMEFRAME, DAY_MS, HOUR_MS = "1d", 86_400_000, 3_600_000
EARLY_MS = 1_502_928_000_000  # 17/08/2017 : le premier jour de cotation du Bitcoin en USDT sur Binance
CAPITAL = 1000.0  # l'argent fictif de chaque compte
SPOT = ExecutionParams()  # au comptant, ordre au marché : 0,10 % de frais et 0,05 % de glissement
CHART_DAYS = 730  # ce que le graphique du site montre
FOLDER = "tendance"  # dans le dossier des données : les bougies gardées, le compte, le dernier test de robustesse
ACCOUNT_FILE = "compte.json"
ROBUSTNESS_FILE = "robustesse.json"
PERIODS = 4  # les sous-périodes du test de robustesse
LEVERAGE = 2.0  # le compte « à risque » : le double de ce que tient le compte normal
BAND = 0.10  # un compte qui emprunte est remis à son levier quand il s'en écarte de plus de 10 %
STOP_DAYS, STOP_ATR = 22, 3.0  # le stop suiveur : le « chandelier » de LeBeau, ses réglages d'origine
FUNDING_WAIT_MS = DAY_MS  # une nuit dont le vrai coût reste introuvable un jour après sa fin est écrite au taux fixe


@dataclass(frozen=True)
class Variant:
    """Un compte fictif : la même règle, avec ou sans levier, avec ou sans stop suiveur."""
    key: str
    name: str
    short: str
    leverage: float = 1.0
    stop: bool = False


VARIANTS = (Variant("normal", "Le compte normal", "Normal"),
            Variant("stop", "Normal, avec stop suiveur", "Normal + stop", stop=True),
            Variant("risque", "À risque : levier ×2", "Risque ×2", LEVERAGE),
            Variant("risque_stop", "À risque ×2, avec stop suiveur", "Risque ×2 + stop", LEVERAGE, True))
ORDERS_SHOWN = 40  # les derniers ordres de chaque compte, sur la page


def average(close: np.ndarray, n: int) -> np.ndarray:
    """La moyenne des n dernières clôtures, jour par jour (NaN tant qu'il n'y en a pas n). Chaque moyenne est calculée
    sur ses seules n clôtures : le résultat ne dépend pas de la longueur de l'historique chargé."""
    close = np.asarray(close, dtype=float)
    out = np.full(len(close), np.nan)
    if len(close) >= n:
        out[n - 1:] = np.lib.stride_tricks.sliding_window_view(close, n).mean(axis=1)
    return out


def levels(close, averages: tuple[int, ...] = AVERAGES) -> np.ndarray:
    """Ce que la règle décide à la clôture de chaque jour : le nombre de moyennes sous le prix de clôture (strictement).
    −1 tant que la plus longue moyenne n'existe pas : le bot ne fait rien sans tout son historique."""
    close = np.asarray(close, dtype=float)
    out = np.zeros(len(close), dtype=int)
    for n in averages:
        out += close > average(close, n)  # une comparaison avec NaN est fausse
    out[:max(averages) - 1] = -1
    return out


def thresholds(closed: np.ndarray, averages: tuple[int, ...] = AVERAGES) -> list[float | None]:
    """Le prix que la clôture du jour en cours doit dépasser pour passer au-dessus de chaque moyenne. La moyenne du
    soir contient la clôture du soir : « clôture > moyenne des n jours » revient à « clôture > moyenne des n − 1
    clôtures d'avant »."""
    closed = np.asarray(closed, dtype=float)
    return [float(closed[-(n - 1):].mean()) if len(closed) >= n - 1 else None for n in averages]


def stop_line(high, low, close) -> np.ndarray:
    """Le stop suiveur à la clôture de chaque jour : le plus haut des `STOP_DAYS` derniers jours moins `STOP_ATR`
    bougies moyennes (la moyenne simple, sur `STOP_DAYS` jours, de l'amplitude vraie). NaN tant qu'il manque des
    jours. Comme les moyennes : chaque valeur ne dépend que de ses derniers jours, pas de l'historique chargé."""
    high, low, close = (np.asarray(x, dtype=float) for x in (high, low, close))
    out = np.full(len(close), np.nan)
    if len(close) > STOP_DAYS:
        before = np.concatenate(([close[0]], close[:-1]))
        true_range = np.maximum(high - low, np.maximum(np.abs(high - before), np.abs(low - before)))
        top = np.lib.stride_tricks.sliding_window_view(high, STOP_DAYS).max(axis=1)
        out[STOP_DAYS:] = (top - STOP_ATR * average(true_range, STOP_DAYS)[STOP_DAYS - 1:])[1:]
    return out


def stop_allows(high, low, close) -> np.ndarray:
    """Ce que le stop suiveur décide à la clôture de chaque jour : vrai = le compte peut tenir sa position, faux = il
    sort (clôture strictement sous la ligne). Sans ligne (historique trop court), il ne dit rien."""
    line = stop_line(high, low, close)
    return ~(np.asarray(close, dtype=float) < line)  # une comparaison avec NaN est fausse : pas de stop


@dataclass
class Run:
    """Un rejeu : le compte jour par jour, depuis son premier jour."""
    ts: np.ndarray  # l'ouverture de chaque jour (ms)
    value: np.ndarray  # la valeur du compte à la clôture de chaque jour
    hold: np.ndarray  # « acheter et garder » depuis le même jour, avec les mêmes frais à l'achat
    level: np.ndarray  # le nombre de parts tenues pendant chaque jour (après l'ordre de l'ouverture)
    orders: list[dict]
    capital: float
    parts: int  # le nombre de moyennes : une part chacune
    cash: float
    qty: float
    decided: int = -1  # ce que la dernière clôture décide (−1 : pas assez d'historique)
    last: float = math.nan  # le dernier prix (la clôture de la dernière bougie)
    paid: float = 0.0  # les intérêts payés sur l'argent emprunté
    dead: int | None = None  # le jour de la liquidation (ms) : le compte vaut zéro depuis
    allowed: bool = True  # ce que le stop suiveur décide à la dernière clôture (toujours vrai sans stop)

    def __len__(self) -> int:
        return len(self.ts)


def _trade(cash: float, qty: float, price: float, share: float, ex: ExecutionParams) -> tuple[float, float, dict]:
    """Ramène la part en crypto à `share` de la valeur du compte, par un ordre au marché au prix `price` du graphique.
    Achat : payé plus cher (glissement), frais pris sur la somme dépensée. Vente : vendue moins cher, frais pris sur ce
    qu'elle rapporte. Jusqu'à `share` = 1, le compte n'emprunte jamais : au plus tout son argent, au plus toutes ses
    cryptos. Au-delà (compte à levier), ce qui manque est emprunté : `cash` devient négatif, c'est sa dette."""
    before = cash + qty * price
    gap = share * before - qty * price
    if gap > 0:
        spend = gap if share > 1 else cash if share >= 1 else min(gap, cash)
        fill = price * (1 + ex.slippage)
        bought = spend * (1 - ex.fee_rate) / fill
        cash, qty = cash - spend, qty + bought
        order = {"side": "achat", "amount": spend, "units": bought, "fill": fill}
    else:
        units = qty if share <= 0 else min(qty, -gap / price)
        fill = price * (1 - ex.slippage)
        cash, qty = cash + units * fill * (1 - ex.fee_rate), qty - units
        order = {"side": "vente", "amount": units * price, "units": units, "fill": fill}
    after = cash + qty * price
    return cash, qty, {**order, "price": price, "cost": before - after, "value": after, "qty": qty, "cash": cash}


def replay(df: pd.DataFrame, start_ts: int | None = None, capital: float = CAPITAL, ex: ExecutionParams = SPOT,
           averages: tuple[int, ...] = AVERAGES, leverage: float = 1.0, stop: bool = False,
           funding_8h: float = FUTURES.funding_rate_8h, nights=None) -> Run:
    """Rejoue la règle sur des bougies d'un jour (colonnes ts, open, high, low, close). Le compte ouvre au premier jour
    d'ouverture `ts >= start_ts` qui a tout son historique derrière lui (sans `start_ts` : dès que possible). Chaque
    jour, dans cet ordre : les intérêts de la nuit sur l'argent emprunté (`nights` : le coût de la nuit qui finit à
    l'ouverture de chaque bougie, une valeur par bougie ; sans lui, ou pour une nuit inconnue (NaN), le taux fixe
    `funding_8h` × 3 ; un coût négatif est reçu par le compte) ; ce que la clôture de la VEILLE a décidé (la
    règle, et le stop suiveur s'il y en a un) s'exécute à l'ouverture ; un compte qui emprunte est liquidé si le plus
    bas du jour ne couvre plus sa marge ; puis le compte est valorisé à la clôture.
    Passé et futur sont séparés : ajouter des bougies ne change aucun ordre déjà passé."""
    ts = df["ts"].to_numpy(dtype="int64")
    close = df["close"].to_numpy(dtype=float)
    want, parts, n = levels(close, averages), len(averages), len(ts)
    high, low = df["high"].to_numpy(dtype=float), df["low"].to_numpy(dtype=float)
    allows = stop_allows(high, low, close) if stop else None
    first = max(averages)  # la veille, la plus longue moyenne existe pour la première fois
    if start_ts is not None:
        first = max(first, int(np.searchsorted(ts, start_ts, side="left")))
    decided = int(want[-1]) if n else -1
    last = float(close[-1]) if n else math.nan
    allowed = bool(allows[-1]) if allows is not None and n else True
    if first >= n:
        empty = np.array([], dtype=float)
        return Run(ts[n:], empty, empty, np.array([], dtype=int), [], capital, parts, capital, 0.0, decided, last,
                   allowed=allowed)
    opens, lows, closes = df["open"].to_numpy(dtype=float).tolist(), low.tolist(), close.tolist()
    rule = want.tolist()
    gate = allows.tolist() if allows is not None else None
    value, level = np.empty(n - first), np.zeros(n - first, dtype=int)
    cash, qty, orders, paid, dead = float(capital), 0.0, [], 0.0, None
    held, open_gate, aim, fixed = 0, True, 0.0, 3 * funding_8h  # trois périodes de 8 heures par jour
    costs = None if nights is None else np.where(np.isfinite(nights), nights, fixed).tolist()
    for i in range(first, n):
        if dead is None:
            price = opens[i]
            if cash < 0:  # les intérêts de la nuit sur ce que le compte emprunte
                night = fixed if costs is None else costs[i]
                paid, cash = paid - cash * night, cash * (1 + night)
            today, today_gate = rule[i - 1], gate is None or gate[i - 1]
            target = leverage * today / parts if today_gate else 0.0
            if cash < 0 and cash + qty * price <= MAINTENANCE * qty * price:  # ouverture sous le prix de liquidation
                dead = _liquidate(orders, int(ts[i]), price, held if open_gate else 0)
            else:
                why = None
                if target != aim:
                    why = "stop" if today_gate != open_gate else "regle"
                elif cash < 0 and abs(qty * price / (cash + qty * price) - target) > BAND * target:
                    why = "levier"  # la position a trop dérivé : le compte est remis à son levier
                if why:
                    before = held if open_gate else 0
                    cash, qty, order = _trade(cash, qty, price, target, ex)
                    orders.append({"ts": int(ts[i]), "from": before, "to": today if today_gate else 0, "why": why,
                                   **order})
                held, open_gate, aim = today, today_gate, target
                if cash < 0 < qty and lows[i] <= -cash / (qty * (1 - MAINTENANCE)):  # liquidé au plus bas du jour
                    dead = _liquidate(orders, int(ts[i]), -cash / (qty * (1 - MAINTENANCE)), held if open_gate else 0)
            if dead is not None:
                cash, qty, held = 0.0, 0.0, 0
        value[i - first] = cash + qty * closes[i]
        level[i - first] = held if open_gate and dead is None else 0
    hold = capital * (1 - ex.fee_rate) / (opens[first] * (1 + ex.slippage)) * close[first:]
    return Run(ts[first:], value, hold, level, orders, capital, parts, cash, qty, decided, last, paid, dead, allowed)


def _liquidate(orders: list[dict], ts: int, price: float, held: int) -> int:
    """La liquidation : la plateforme ferme la position, la marge qui restait part avec. Le compte vaut zéro."""
    orders.append({"ts": ts, "from": held, "to": 0, "why": "liquidation", "side": "liquidation", "amount": 0.0,
                   "units": 0.0, "fill": price, "price": price, "cost": 0.0, "value": 0.0, "qty": 0.0, "cash": 0.0})
    return ts


def worst(values: np.ndarray, base: float) -> float:
    """La pire baisse depuis un sommet (0 = jamais sous son plus haut), le point de départ compris."""
    path = np.concatenate(([base], np.asarray(values, dtype=float)))
    return float((path / np.maximum.accumulate(path) - 1).min())


def growth(values: np.ndarray, base: float) -> dict:
    """Ce que devient `base` : le total (×), la pire baisse en route, et le rythme par an (jours du calendrier)."""
    total = float(values[-1] / base)
    return {"total": total, "worst": worst(values, base),
            "yearly": total ** (365 / len(values)) - 1 if total > 0 else -1.0}


def by_year(run: Run) -> list[dict]:
    """Année par année : la règle et « acheter et garder », gain de l'année et pire baisse dans l'année."""
    years = pd.to_datetime(run.ts, unit="ms", utc=True).year.to_numpy()
    out, rule0, hold0 = [], run.capital, run.capital
    for year in np.unique(years):
        idx = np.flatnonzero(years == year)
        rule, hold = run.value[idx], run.hold[idx]
        out.append({"year": int(year), "days": int(len(idx)), "rule": float(rule[-1] / rule0 - 1),
                    "hold": float(hold[-1] / hold0 - 1), "rule_worst": worst(rule, rule0),
                    "hold_worst": worst(hold, hold0)})
        rule0, hold0 = float(rule[-1]), float(hold[-1])
    return out


# --- le test de robustesse : la règle fait-elle mieux que garder ? ----------------------------------------------

def exits(run: Run, ex: ExecutionParams = SPOT) -> list[dict]:
    """Les sorties d'un rejeu à UNE moyenne, chacune jugée comme un pari : vendre pour racheter moins cher. `ret` = les
    cryptos rachetées au retour, divisées par celles vendues, moins 1, frais des deux ordres compris : positif quand la
    règle a fait mieux que garder pendant son absence. Sur une crypto qui monte, être acheteur gagne de toute façon :
    c'est donc la sortie qu'il faut juger, pas le séjour. La sortie en cours est comptée au dernier prix."""
    if run.parts != 1:
        raise ValueError("Les sorties se jugent moyenne par moyenne.")
    out, sold = [], None
    for order in run.orders:
        if order["side"] == "vente":
            sold = order
        elif sold is not None:
            out.append({"sold": sold["ts"], "back": order["ts"], "sell": sold["fill"], "buy": order["fill"],
                        "units": sold["units"], "ret": order["units"] / sold["units"] - 1, "open": False})
            sold = None
    if sold is not None and len(run) and run.ts[-1] > sold["ts"]:
        fill = run.last * (1 + ex.slippage)
        back = run.cash * (1 - ex.fee_rate) / fill
        out.append({"sold": sold["ts"], "back": int(run.ts[-1]), "sell": sold["fill"], "buy": fill,
                    "units": sold["units"], "ret": back / sold["units"] - 1, "open": True})
    return out


def as_backtest(run: Run, ex: ExecutionParams = SPOT) -> BacktestResult:
    """Les sorties d'un rejeu, dans la forme que lit le test de robustesse du projet (`robustness.evaluate`) : un
    « trade » = une sortie ; la courbe = la règle divisée par « acheter et garder ».
    Le gain d'une sortie est compté en logarithme : dans le compte, les sorties s'enchaînent en se multipliant (doubler
    ses cryptos puis les diviser par deux ne rapporte rien), alors qu'une moyenne simple compterait +25 %. Mesuré sur
    un marché sans avantage : la moyenne simple annonce +1,1 % par sortie, celle des logarithmes rend les frais."""
    stamp = lambda ms: pd.Timestamp(int(ms), unit="ms", tz="UTC")  # noqa: E731
    bets = exits(run, ex)
    trades = [Trade(stamp(b["sold"]), stamp(b["back"]), b["sell"], b["buy"], b["units"], 1.0,
                    1.0 + math.log1p(b["ret"]), "en cours" if b["open"] else "rachat") for b in bets]
    logs = np.array([t.return_pct for t in trades])
    equity = pd.Series(run.value / run.hold, index=pd.to_datetime(run.ts, unit="ms", utc=True))
    metrics = {"taux_reussite": float((logs > 0).mean()) if len(logs) else math.nan,
               "esperance_pct": float(100 * logs.mean()) if len(logs) else math.nan,
               "rendement_total": float(equity.iloc[-1] - 1) if len(equity) else math.nan}
    return BacktestResult(trades, equity, metrics)


def label(symbol: str, n: int) -> str:
    return f"{symbol.split('/')[0]} moy. {n} j"


def robustness_rows(frames: dict[str, pd.DataFrame], ex: ExecutionParams = SPOT,
                    averages: tuple[int, ...] = AVERAGES) -> list[RobustnessRow]:
    """La porte du projet (`robustesse`) appliquée à la règle : une ligne par crypto et par moyenne, mêmes seuils que
    pour toute stratégie (30 paris au moins, fourchette au-dessus de 0 avec un seuil durci par le nombre de lignes,
    gagnante dans 3 sous-périodes sur 4). Ce qui est jugé : chaque sortie, contre « acheter et garder »."""
    jobs = [(symbol, df, n) for symbol, df in frames.items() for n in averages if len(df) > n]
    return [evaluate(label(symbol, n), as_backtest(replay(df, ex=ex, averages=(n,)), ex), len(jobs), PERIODS)
            for symbol, df, n in jobs]


def verdict(rows: list[RobustnessRow]) -> str:
    """Ce que le test dit, en une phrase franche : « robuste » ou non, et ce que cela autorise."""
    if not rows:
        return "Pas assez d'historique pour juger la règle."
    robust = [r.market for r in rows if r.verdict == ROBUST]
    if robust:
        return (f"{len(robust)} ligne(s) sur {len(rows)} sont « robustes » : {', '.join(robust)}. Le seuil tient déjà compte "
                "du nombre de lignes. Avant tout argent réel : plusieurs semaines de compte fictif, puis un essai en mode "
                "test sur une plateforme agréée. Les performances passées ne garantissent rien.")
    positive = sum(r.expectancy_pct > 0 for r in rows)  # une ligne positive = plus de cryptos à la fin qu'en gardant
    if not positive:
        return (f"Aucune des {len(rows)} lignes n'est « robuste », et aucune n'est positive : sur cette période, sortir du "
                "marché sous la moyenne a laissé moins de cryptos que de les garder. Argent fictif seulement.")
    return (f"Aucune des {len(rows)} lignes n'est « robuste ». Sur cette période, sortir du marché sous la moyenne a laissé "
            f"plus de cryptos que de les garder pour {positive} ligne(s) sur {len(rows)}, mais pas assez nettement pour le "
            "seuil (durci par le nombre de lignes). Ce test ne peut pas trancher entre un avantage et de la chance : il y "
            "a peu de sorties, et presque tout vient de quelques grandes chutes évitées. Argent fictif seulement.")


def robustness_report(rows: list[RobustnessRow]) -> str:
    """Le tableau du test de robustesse (celui de `robustesse`), avec ce que ses colonnes veulent dire ici."""
    table = format_robustness(rows, PERIODS).split("\n\n")[0].replace("Marché", "Sortie", 1).replace("Trades", "Paris ", 1)
    return "\n".join([table, "", *ROBUSTNESS_NOTES])


ROBUSTNESS_NOTES = (
    "Ce qui est jugé ici : chaque SORTIE du marché, comme un pari (vendre pour racheter moins cher), frais compris. "
    "Être acheteur d'une crypto qui a monté gagne de toute façon : la règle n'a un avantage que si ses sorties font "
    "mieux que garder.",
    "« Espérance » : ce qu'une sortie rapporte en moyenne, en cryptos (comptée comme le compte les enchaîne : doubler "
    "puis diviser par deux fait zéro). « Rendement » : la règle contre « acheter et garder » sur toute la période. "
    "« robuste » : la fourchette reste au-dessus de 0 avec un seuil durci, et les sorties gagnent dans 3 "
    "sous-périodes sur 4.",
)


# --- les bougies : tout l'historique une fois, puis les derniers jours -------------------------------------------

@dataclass
class Candles:
    df: pd.DataFrame | None  # toutes les bougies connues, la plus récente en dernier
    live: bool  # la dernière bougie est celle du jour en cours (reçue de la plateforme pendant cette session)
    asof: float | None  # l'heure de la dernière réponse de la plateforme (horloge du PC, pour l'affichage seulement)
    error: str | None


class Feed:
    """Les bougies d'un jour des cryptos suivies. Les bougies terminées sont gardées dans `data/tendance/` ; à chaque
    relève, seuls les derniers jours sont redemandés. La dernière bougie reçue est celle du jour en cours : c'est la
    plateforme qui dit qu'un jour est fini (une bougie suivante existe), jamais l'horloge du PC."""

    PAGE = 50  # moins de bougies que ça dans une réponse : on est arrivé à aujourd'hui

    def __init__(self, make_exchange, exchange_id: str, folder: Path, every: float = 30.0, since_ms: int = EARLY_MS):
        self.make_exchange, self.exchange_id, self.folder = make_exchange, exchange_id, Path(folder)
        self.every, self.since_ms = every, since_ms
        self.exchange = None
        self.closed: dict[str, pd.DataFrame] = {}
        self.today: dict[str, pd.DataFrame] = {}
        self.checked: dict[str, float] = {}
        self.asof: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.lock = threading.Lock()

    def path(self, symbol: str) -> Path:
        return self.folder / f"{self.exchange_id}_{symbol.replace('/', '-')}_{TIMEFRAME}.csv"

    def get(self, symbol: str) -> Candles:
        with self.lock:
            if symbol not in self.closed:
                try:  # relu au chiffre près : un redémarrage ne change aucune moyenne
                    saved = pd.read_csv(self.path(symbol), float_precision="round_trip")
                    self.closed[symbol] = ohlcv_to_frame(saved[COLUMNS].values.tolist())
                except (OSError, ValueError, KeyError):  # pas encore de fichier, ou fichier abîmé : tout est redemandé
                    self.closed[symbol] = ohlcv_to_frame([])
            now = time.monotonic()
            if now - self.checked.get(symbol, -math.inf) >= self.every:
                self.checked[symbol] = now
                try:
                    self._update(symbol)
                    self.errors.pop(symbol, None)
                except Exception as exc:  # réseau coupé, plateforme en panne : on garde ce qu'on a
                    self.errors[symbol] = f"{type(exc).__name__} : {str(exc)[:160]}"
                    log.debug("Bougies d'un jour de %s : %s", symbol, self.errors[symbol])
            closed, today = self.closed[symbol], self.today.get(symbol)
            df = closed if today is None else pd.concat([closed, today])
            return Candles(df if len(df) else None, today is not None, self.asof.get(symbol), self.errors.get(symbol))

    def _update(self, symbol: str) -> None:
        if self.exchange is None:
            self.exchange = self.make_exchange(self.exchange_id)
        closed = self.closed[symbol]
        last = int(closed["ts"].iloc[-1]) if len(closed) else None
        cursor = self.since_ms if last is None else last  # la dernière bougie finie est redemandée : la suite s'y raccroche
        rows: list[list[float]] = []
        while True:
            batch = self.exchange.fetch_ohlcv(symbol, TIMEFRAME, since=cursor, limit=1000)
            rows.extend(batch or [])
            if not batch or len(batch) < self.PAGE or batch[-1][0] + DAY_MS <= cursor:
                break
            cursor = int(batch[-1][0]) + DAY_MS
        fresh = ohlcv_to_frame(rows)
        newer = fresh if last is None else fresh[fresh["ts"] > last]
        self.asof[symbol] = time.time()
        if not len(newer):  # rien après la dernière bougie finie : le jour suivant n'a pas encore commencé
            return
        done = pd.concat([closed, newer.iloc[:-1]])  # tout sauf la dernière reçue : celle du jour en cours
        if len(done) != len(closed):
            atomic_write(self.path(symbol), done[COLUMNS].to_csv(index=False, lineterminator="\n"))
        self.closed[symbol], self.today[symbol] = done, newer.iloc[-1:]


# --- le compte fictif et la vue du site ----------------------------------------------------------------------------

def funding_days(payments) -> dict[int, float]:
    """Des échéances de financement (moment en ms, taux) rangées par journée. Le coût d'une journée d'emprunt est la
    somme de ses échéances, celle de minuit comprise (elle paie la journée qui finit). Seules les journées COMPLÈTES
    sont rendues : au moins trois échéances, la première dans les 8 premières heures, la dernière à minuit."""
    days: dict[int, list[tuple[int, float]]] = {}
    for stamp, rate in payments:
        stamp = (int(stamp) + HOUR_MS // 2) // HOUR_MS * HOUR_MS  # les plateformes datent avec quelques ms de retard
        days.setdefault((stamp - 1) // DAY_MS * DAY_MS, []).append((stamp, float(rate)))
    return {day: sum(rate for _, rate in {stamp: (stamp, rate) for stamp, rate in rows}.values())
            for day, rows in days.items()
            if len({stamp for stamp, _ in rows}) >= 3 and min(stamp for stamp, _ in rows) <= day + 8 * HOUR_MS
            and max(stamp for stamp, _ in rows) == day + DAY_MS}


class Funding:
    """Le vrai coût d'une nuit d'emprunt, pour les comptes à levier : le financement du contrat perpétuel de la crypto.
    De 2020 à fin octobre 2026, il est embarqué (`funding_history`). Ensuite, il est lu une fois par jour sur une
    plateforme (Binance, sinon OKX : prix publics, sans clé) et gardé dans `data/tendance/financement_<crypto>.csv`.
    Une nuit écrite ne change plus jamais : le compte ne réécrit pas son passé. Si aucune plateforme n'a répondu un
    jour après la fin d'une journée, c'est le taux fixe qui est écrit pour elle, pour de bon ; d'ici là, et pour les
    nuits d'avant 2020, le rejeu compte le taux fixe."""

    SOURCES = ("binance", "okx")

    def __init__(self, make_exchange, folder: Path, every: float = 3600.0, now=None):
        self.make_exchange, self.folder, self.every = make_exchange, Path(folder), every
        self.now = now or (lambda: int(time.time() * 1000))
        self.exchanges: dict[str, object] = {}
        self.kept: dict[str, dict[int, tuple[float, str]]] = {}
        self.tried: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.lock = threading.Lock()

    def path(self, coin: str) -> Path:
        return self.folder / f"financement_{coin}.csv"

    def _known(self, coin: str) -> dict[int, tuple[float, str]]:
        if coin not in self.kept:
            days = {funding_history.FIRST_DAY + k * DAY_MS: (value * funding_history.UNIT, "historique")
                    for k, value in enumerate(funding_history.DAYS.get(coin, ()))}
            try:  # relu au chiffre près ; l'historique embarqué passe toujours avant le fichier
                saved = pd.read_csv(self.path(coin), float_precision="round_trip")
                for day, rate, source in saved[["ts", "rate", "source"]].values.tolist():
                    days.setdefault(int(day), (float(rate), str(source)))
            except (OSError, ValueError, KeyError):
                pass
            self.kept[coin] = days
        return self.kept[coin]

    def _payments(self, source: str, coin: str, since_ms: int) -> list[tuple[int, float]]:
        """Les échéances d'un contrat depuis `since_ms`, par une lecture publique (aucune clé, aucun ordre)."""
        if source not in self.exchanges:
            self.exchanges[source] = self.make_exchange(source)
            self.exchanges[source].timeout = 5000  # une plateforme muette ne doit pas bloquer la page longtemps
        exchange = self.exchanges[source]
        if source == "binance":
            rows = exchange.fapiPublicGetFundingRate({"symbol": f"{coin}USDT", "startTime": since_ms, "limit": 1000})
            return [(int(row["fundingTime"]), float(row["fundingRate"])) for row in rows]
        out, after = [], None
        for _ in range(12):  # OKX : cent échéances par page, des plus récentes aux plus anciennes
            params = {"instId": f"{coin}-USDT-SWAP", "limit": "100", **({"after": str(after)} if after else {})}
            rows = exchange.publicGetPublicFundingRateHistory(params).get("data") or []
            out += [(int(row["fundingTime"]), float(row.get("realizedRate") or row["fundingRate"])) for row in rows]
            if not rows or min(int(row["fundingTime"]) for row in rows) <= since_ms:
                break
            after = min(int(row["fundingTime"]) for row in rows)
        return out

    def _complete(self, coin: str, known: dict, wanted: list[int]) -> None:
        """Cherche les journées qui manquent ; écrit ce qui est trouvé, et le taux fixe pour celles qui ont trop tardé."""
        clock = time.monotonic()
        if clock - self.tried.get(coin, -math.inf) < self.every:
            return
        self.tried[coin], fresh = clock, {}
        for source in self.SOURCES:
            missing = [day for day in wanted if day not in fresh]
            if not missing:
                break
            try:
                days = funding_days(self._payments(source, coin, min(missing)))
                fresh.update({day: (days[day], source) for day in missing if day in days})
                self.errors.pop(coin, None)
            except Exception as exc:  # une plateforme qui ne répond pas : on essaie la suivante
                self.errors[coin] = f"{source} : {type(exc).__name__}"
        fixed = 3 * FUTURES.funding_rate_8h
        fresh.update({day: (fixed, "fixe") for day in wanted
                      if day not in fresh and self.now() - (day + DAY_MS) > FUNDING_WAIT_MS})
        if fresh:
            known.update(fresh)
            rows = sorted((day, rate, source) for day, (rate, source) in known.items() if source != "historique")
            atomic_write(self.path(coin), pd.DataFrame(rows, columns=["ts", "rate", "source"]).to_csv(index=False))

    def nights(self, symbol: str, ts) -> tuple[np.ndarray, dict]:
        """Pour chaque bougie d'un jour, le coût de la nuit qui finit à son ouverture : le financement de la journée
        de la veille (NaN quand il n'est pas connu : le rejeu prend le taux fixe). Et ce que la page en dit."""
        coin, ts = symbol.split("/")[0], np.asarray(ts, dtype="int64")
        with self.lock:
            known = self._known(coin)
            if coin in funding_history.DAYS:
                end = funding_history.FIRST_DAY + (len(funding_history.DAYS[coin]) - 1) * DAY_MS
                wanted = [int(day) - DAY_MS for day in ts if end < int(day) - DAY_MS and int(day) - DAY_MS not in known]
                if wanted:
                    try:
                        self._complete(coin, known, wanted)
                    except OSError as exc:  # le fichier ne s'écrit pas : on continue avec ce qui est en mémoire
                        self.errors[coin] = f"fichier : {type(exc).__name__}"
            got = [known.get(int(day) - DAY_MS) for day in ts]
            real = [(int(day) - DAY_MS, item) for day, item in zip(ts, got) if item and item[1] != "fixe"]
            summary = {"real": len(real), "fixed": len(got) - len(real),
                       "until": real[-1][0] if real else None, "last": real[-1][1][0] if real else None,
                       "source": real[-1][1][1] if real else None, "default": 3 * FUTURES.funding_rate_8h,
                       "error": self.errors.get(coin)}
            return np.array([item[0] if item else math.nan for item in got], dtype=float), summary


def account_since(folder: Path, now: datetime | None = None) -> int:
    """Le moment où le compte fictif a été créé (ms), écrit une fois dans `compte.json` et plus jamais changé : le
    compte ouvre à l'ouverture du jour suivant, pour ne rien devoir à un prix déjà passé.
    Le fichier n'est créé que s'il n'existe pas. S'il existe mais ne se lit pas (verrouillé un instant par un
    antivirus ou un dossier synchronisé, ou abîmé), rien n'est réécrit et l'erreur remonte : une date de départ écrasée
    ferait repartir les comptes de zéro sans le dire."""
    path = Path(folder) / ACCOUNT_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        now = now or datetime.now(timezone.utc)
        atomic_write(path, json.dumps({"since": now.isoformat(timespec="seconds"), "capital": CAPITAL,
                                       "regle": f"moyennes {', '.join(map(str, AVERAGES))} jours"},
                                      ensure_ascii=False, indent=1))
        return int(now.timestamp() * 1000)
    try:
        return int(datetime.fromisoformat(json.loads(text)["since"]).timestamp() * 1000)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"La date de départ du compte fictif ({path}) est illisible : rien n'a été réécrit. Supprimer ce "
                         "fichier fait repartir les comptes d'aujourd'hui.") from exc


def _clean(value):
    """Pour le JSON du site : pas de NaN ni d'infini, pas de types numpy."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def _order(order: dict) -> dict:
    return {k: order[k] for k in ("ts", "side", "from", "to", "why", "price", "fill", "amount", "cost", "value")}


def _ready(df: pd.DataFrame | None) -> bool:
    return df is not None and len(df) > max(AVERAGES) + 1


def _account(variant: Variant, df: pd.DataFrame, since_ms: int, ex: ExecutionParams, nights=None) -> dict:
    """Un compte fictif depuis sa création : sa valeur, sa pire baisse, ce qu'il a payé, ses derniers ordres."""
    run = replay(df, start_ts=since_ms, ex=ex, leverage=variant.leverage, stop=variant.stop, nights=nights)
    started = bool(len(run))
    return {"key": variant.key, "name": variant.name, "short": variant.short, "leverage": variant.leverage,
            "stop": variant.stop, "since": since_ms, "started": started, "capital": run.capital,
            "start": int(run.ts[0]) if started else None, "days": int(len(run)),
            "value": float(run.value[-1]) if started else run.capital,
            "hold": float(run.hold[-1]) if started else run.capital,
            "level": int(run.level[-1]) if started else 0,
            "worst": worst(run.value, run.capital) if started else 0.0,
            "hold_worst": worst(run.hold, run.capital) if started else 0.0,
            "costs": float(sum(o["cost"] for o in run.orders)), "paid": float(run.paid), "liquidated": run.dead,
            "count": len(run.orders), "orders": [_order(o) for o in run.orders][::-1][:ORDERS_SHOWN]}


def _past(variant: Variant, df: pd.DataFrame, ex: ExecutionParams, nights=None) -> dict:
    """Ce que ce compte aurait fait sur tout l'historique : ce que devient 1, la pire baisse, ce que ça a coûté."""
    run = replay(df, ex=ex, leverage=variant.leverage, stop=variant.stop, nights=nights)
    years = len(run) / 365
    return {"key": variant.key, "name": variant.name, "short": variant.short, **growth(run.value, run.capital),
            "orders_per_year": len(run.orders) / years if years else 0.0, "paid": float(run.paid),
            "costs": float(sum(o["cost"] for o in run.orders)), "liquidated": run.dead}


def coin_view(symbol: str, candles: Candles, since_ms: int, ex: ExecutionParams = SPOT,
              funding: Funding | None = None) -> dict:
    """Ce que le site montre pour une crypto : où en est la règle, ses comptes fictifs (normal, avec stop suiveur, à
    risque, à risque avec stop) et l'histoire année par année. Avec `funding`, les comptes à levier paient le vrai
    coût de chaque nuit d'emprunt ; sans lui, le taux fixe."""
    coin = symbol.split("/")[0]
    out = {"symbol": symbol, "coin": coin, "name": NAMES.get(coin, coin), "error": candles.error, "live": candles.live,
           "asof": candles.asof, "parts": len(AVERAGES)}
    df = candles.df
    if not _ready(df):
        return {**out, "ready": False, "days": 0 if df is None else int(len(df)), "needed": max(AVERAGES) + 2}
    whole = replay(df, ex=ex)
    close = df["close"].to_numpy(dtype=float)
    marks = thresholds(close[:-1] if candles.live else close)
    price = float(close[-1])
    nights, cost = funding.nights(symbol, df["ts"]) if funding is not None else (None, None)
    accounts = [_account(variant, df, since_ms, ex, nights) for variant in VARIANTS]
    line = stop_line(df["high"], df["low"], close)
    years = len(whole) / 365
    return _clean({
        **out, "ready": True, "price": price, "day": int(df["ts"].iloc[-1]), "next_open": int(df["ts"].iloc[-1]) + DAY_MS,
        "level": int(whole.level[-1]), "since": whole.orders[-1]["ts"] if whole.orders else None,
        "tonight": int(whole.decided),
        "averages": [{"days": n, "threshold": mark, "above": bool(mark is not None and price > mark),
                      "gap": price / mark - 1 if mark else None} for n, mark in zip(AVERAGES, marks)],
        "account": accounts[0], "accounts": accounts,
        "stop": {"line": float(line[-1]), "allowed": bool(not price < line[-1])}, "funding": cost,
        "history": {"from": int(whole.ts[0]), "to": int(whole.ts[-1]), "years": years,
                    "rule": growth(whole.value, whole.capital), "hold": growth(whole.hold, whole.capital),
                    "orders": len(whole.orders), "orders_per_year": len(whole.orders) / years if years else 0.0,
                    "inside": float((whole.level / whole.parts).mean()), "by_year": by_year(whole),
                    "variants": [_past(variant, df, ex, nights) for variant in VARIANTS]},
    })


def chart_view(symbol: str, candles: Candles, ex: ExecutionParams = SPOT) -> dict:
    """Le graphique d'une crypto : ses bougies d'un jour, ses trois moyennes, et les ordres que la règle y a passés."""
    df = candles.df
    if not _ready(df):
        raise ValueError("Pas assez de bougies d'un jour pour ce graphique.")
    close = df["close"].to_numpy(dtype=float)
    shown = df.iloc[-CHART_DAYS:]
    first = len(df) - len(shown)
    colors = ("var(--series-1)", "var(--series-4)", "var(--series-2)")
    return _clean({
        "symbol": symbol, "coin": symbol.split("/")[0],
        "candles": [[int(row[0]), *row[1:]] for row in shown[COLUMNS].to_numpy().tolist()],
        "lines": [{"key": f"moyenne-{n}", "label": f"Moyenne {n} jours", "color": color,
                   "values": average(close, n)[first:].tolist()} for n, color in zip(AVERAGES, colors)]
        + [{"key": "stop-suiveur", "label": "Stop suiveur (pointillés)", "color": "var(--critical)", "dash": True,
            "values": stop_line(df["high"], df["low"], close)[first:].tolist()}],
        "orders": [_order(o) for o in replay(df, ex=ex).orders if o["ts"] >= int(shown["ts"].iloc[0])]})


def closed_frames(got: dict[str, Candles]) -> dict[str, pd.DataFrame]:
    """Les jours finis de chaque crypto (jamais celui en cours), quand il y en a assez pour la règle."""
    frames = {s: c.df.iloc[:-1] if c.live else c.df for s, c in got.items() if c.df is not None}
    return {s: df for s, df in frames.items() if len(df) > max(AVERAGES)}


def view(feed: Feed, folder: Path, ex: ExecutionParams = SPOT, symbols: tuple[str, ...] = SYMBOLS,
         cache: dict | None = None, funding: Funding | None = None) -> dict:
    """La page « Tendance » : une fiche par crypto, puis le test de robustesse (refait seulement quand un jour finit ;
    sans `cache`, la page vient sans lui : c'est la commande `robustesse --tendance` qui le donne)."""
    since_ms = account_since(folder)
    got = {symbol: feed.get(symbol) for symbol in symbols}
    out = {"coins": [coin_view(symbol, candles, since_ms, ex, funding) for symbol, candles in got.items()],
           "averages": list(AVERAGES), "cost": ex.fee_rate + ex.slippage, "capital": CAPITAL,
           "exchange": feed.exchange_id, "since": since_ms, "robustness": None}
    if cache is not None:
        frames = closed_frames(got)
        key = tuple((s, int(df["ts"].iloc[-1])) for s, df in frames.items())
        if cache.get("key") != key:  # le tirage au sort du test prend du temps : une fois par jour suffit
            rows = robustness_rows(frames, ex)
            cache.update(key=key, rows=[asdict(r) for r in rows], verdict=verdict(rows))
        out["robustness"] = {"rows": cache["rows"], "verdict": cache["verdict"], "periods": PERIODS}
    return _clean(out)


# --- la console ---------------------------------------------------------------------------------------------------

def _day(ms: int | None) -> str:
    return "?" if ms is None else datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%d/%m/%Y")


def _share(level: int, parts: int) -> str:
    return "dehors (rien en crypto)" if level <= 0 else "dedans en entier" if level >= parts else \
        f"dedans à {level} part{'s' if level > 1 else ''} sur {parts}"


def report(data: dict) -> str:
    """La même page que le site, en texte, pour `python main.py tendance`."""
    pct = lambda x: "n/a" if x is None else f"{100 * x:+.1f} %"  # noqa: E731
    lines = [f"=== Le bot de tendance (argent fictif) : moyennes {', '.join(map(str, data['averages']))} jours, "
             f"{100 * data['cost']:.2f} % par ordre, prix de {data['exchange']} ==="]
    for c in data["coins"]:
        lines.append("")
        if not c["ready"]:
            lines.append(f"{c['name']} : pas assez de bougies d'un jour ({c['days']} sur {c['needed']})."
                         + (f" {c['error']}" if c["error"] else ""))
            continue
        lines.append(f"{c['name']} à {c['price']:,.2f} : {_share(c['level'], c['parts'])}"
                     + (f" depuis le {_day(c['since'])}" if c["since"] else ""))
        for a in c["averages"]:
            lines.append(f"  moyenne {a['days']:>3} jours : à dépasser ce soir {a['threshold']:>12,.2f}   le prix est "
                         f"{'au-dessus' if a['above'] else 'en dessous'} ({pct(a['gap'])})")
        if c["tonight"] != c["level"]:
            lines.append(f"  Si la journée finissait à ce prix : {_share(c['tonight'], c['parts'])} dès demain.")
        acc = c["account"]
        if acc["started"]:
            lines.append(f"  Compte fictif depuis le {_day(acc['start'])} : {acc['value']:,.2f} USDT pour "
                         f"{acc['capital']:,.0f} au départ ({pct(acc['value'] / acc['capital'] - 1)}) ; acheter et "
                         f"garder : {acc['hold']:,.2f} ({pct(acc['hold'] / acc['capital'] - 1)}) ; "
                         f"{acc['count']} ordre(s).")
            lines.append("  Les autres comptes fictifs : " + " · ".join(
                f"{a['short']} {a['value']:,.2f}" + (" (liquidé)" if a["liquidated"] else "") for a in c["accounts"][1:]))
        else:
            lines.append(f"  Compte fictif créé le {_day(acc['since'])} : il ouvre à la prochaine ouverture du jour.")
        h = c["history"]
        lines.append(f"  Depuis le {_day(h['from'])} ({h['years']:.1f} ans) : la règle ×{h['rule']['total']:.2f} "
                     f"(pire baisse {pct(h['rule']['worst'])}), acheter et garder ×{h['hold']['total']:.2f} "
                     f"(pire baisse {pct(h['hold']['worst'])}), {h['orders_per_year']:.0f} ordres par an.")
        for v in h["variants"][1:]:
            lines.append(f"    {v['name']} : ×{v['total']:.2f}, pire baisse {pct(v['worst'])}"
                         + (f", liquidé le {_day(v['liquidated'])}" if v["liquidated"] else ""))
        lines.append(f"  {'Année':<7}{'La règle':>10}{'Garder':>10}{'Pire baisse : règle':>22}{'garder':>10}")
        for y in h["by_year"]:
            lines.append(f"  {y['year']:<7}{pct(y['rule']):>10}{pct(y['hold']):>10}{pct(y['rule_worst']):>22}"
                         f"{pct(y['hold_worst']):>10}")
        if c["error"]:
            lines.append(f"  Attention, dernière relève en échec : {c['error']}")
    lines += ["", "Le passé ne garantit rien. Argent fictif : aucun ordre ne part sur une plateforme.",
              "Le test de robustesse de la règle : python main.py robustesse --tendance"]
    return "\n".join(lines)


def save_robustness(folder: Path, rows: list[RobustnessRow], text: str) -> None:
    payload = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "verdict": text,
               "rows": _clean([asdict(r) for r in rows])}
    atomic_write(Path(folder) / ROBUSTNESS_FILE, json.dumps(payload, ensure_ascii=False, indent=1))

