"""Le momentum croisé : garder, chaque semaine, les cryptos qui ont le plus monté (labo et portefeuille fictif).

La règle vient de la recherche (Liu, Tsyvinski et Wu ; voir research.py) : chaque semaine, classer les cryptos selon
leur hausse des L derniers jours, garder les K meilleures à parts égales, revendre les autres. En spot, sans vente à
découvert : le bot ne garde que le haut du classement.

Le labo, pour ne pas se tromper soi-même :
- les décisions se prennent sur la clôture d'un jour et s'exécutent à l'ouverture du lendemain (jamais de regard vers
  le futur) ; chaque rotation paie frais et glissement sur ce qui change, la dernière vente comprise ;
- les semaines sont coupées dans le temps comme dans le labo : étude (50 %), validation (30 %), test final (20 %) ;
- le seuil est durci selon le nombre de variantes essayées (Bonferroni) ;
- chaque variante est comparée au panier de toutes les cryptos à parts égales : ce qu'aurait donné le fait de tout
  garder sans rien choisir. Toujours investi en crypto, un portefeuille gagne quand le marché monte : seul ce qu'il
  gagne en plus du panier montre l'effet du momentum. Une variante n'est retenue que si elle bat le panier (étude,
  validation, test final), et « prometteur » demande un écart avec le panier net, seuil durci compris.
Limite connue : les cryptos testées sont celles qui s'échangent aujourd'hui ; celles qui ont disparu manquent, ce qui
embellit le passé (biais du survivant). Le verdict le rappelle.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from .broker import atomic_write

PORTFOLIO_LAB_FILE = "laboratoire-portefeuille.json"
PORTFOLIO_DIR = "portefeuille"  # un fichier par portefeuille fictif, dans data
STUDY_SHARE, TEST_SHARE = 0.5, 0.2
MIN_COINS = 6  # en dessous, pas de classement cette semaine-là
MIN_WEEKS = 15  # semaines de validation pour juger
MIN_TEST_WEEKS = 8
RETAINED = ("prometteur", "à surveiller")


@dataclass(frozen=True)
class PortfolioParams:
    lookback: int = 7  # jours de hausse pour classer les cryptos
    top: int = 3  # cryptos gardées, à parts égales
    hold: int = 7  # jours entre deux rotations


PORTFOLIO_VARIANTS: dict[str, PortfolioParams] = {  # seuils ronds fixés d'avance (1, 2 et 4 semaines ; 3 ou 5 cryptos)
    "Momentum croisé 7 j, 3 cryptos": PortfolioParams(7, 3),
    "Momentum croisé 7 j, 5 cryptos": PortfolioParams(7, 5),
    "Momentum croisé 14 j, 3 cryptos": PortfolioParams(14, 3),
    "Momentum croisé 14 j, 5 cryptos": PortfolioParams(14, 5),
    "Momentum croisé 28 j, 3 cryptos": PortfolioParams(28, 3),
    "Momentum croisé 28 j, 5 cryptos": PortfolioParams(28, 5),
}


def align(frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ouvertures et clôtures journalières côte à côte (une colonne par crypto, vide avant sa cotation)."""
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    def by_day(df: pd.DataFrame, col: str) -> pd.Series:
        series = df[col].copy()
        series.index = series.index.normalize()
        return series[~series.index.duplicated(keep="last")]

    opens = pd.DataFrame({s: by_day(df, "open") for s, df in frames.items()}).sort_index()
    closes = pd.DataFrame({s: by_day(df, "close") for s, df in frames.items()}).sort_index()
    return opens, closes


def ranking(closes: pd.DataFrame, i: int, lookback: int) -> pd.Series:
    """Hausse des `lookback` derniers jours à la clôture du jour i, de la plus forte à la plus faible."""
    if i - lookback < 0:
        return pd.Series(dtype=float)
    change = (closes.iloc[i] / closes.iloc[i - lookback] - 1).dropna()
    return change.sort_values(ascending=False)


@dataclass(frozen=True)
class Week:
    start: str  # jour de l'ouverture où les positions sont prises
    holdings: tuple[str, ...]
    ret: float  # rendement de la période, rotation payée
    gross: float  # avant frais
    basket: float  # toutes les cryptos à parts égales, sans frais
    turnover: float  # part du portefeuille échangée à la rotation


def simulate(opens: pd.DataFrame, closes: pd.DataFrame, p: PortfolioParams, cost: float) -> list[Week]:
    """Une période par rotation : classement sur la clôture du jour i, achat à l'ouverture de i+1, revente à
    l'ouverture de i+1+hold. `cost` = frais + glissement d'un ordre (fraction échangée)."""
    weeks: list[Week] = []
    held: tuple[str, ...] = ()
    i = p.lookback
    n = len(closes)
    while i + 1 + p.hold < n:
        entry, exit_ = opens.iloc[i + 1], opens.iloc[i + 1 + p.hold]
        ranks = ranking(closes, i, p.lookback)
        ranks = ranks[entry.reindex(ranks.index).notna().to_numpy() & exit_.reindex(ranks.index).notna().to_numpy()]
        if len(ranks) < max(MIN_COINS, p.top):
            i += 1  # pas encore assez de cryptos cotées : on attend le lendemain
            continue
        chosen = tuple(ranks.index[:p.top])
        period = exit_[ranks.index] / entry[ranks.index] - 1
        gross = float(period[list(chosen)].mean())
        changes = len(set(chosen) - set(held)) + len(set(held) - set(chosen))
        turnover = changes / p.top
        net = (1 + gross) * (1 - turnover * cost) - 1
        weeks.append(Week(str(closes.index[i + 1].date()), chosen, net, gross, float(period.mean()), turnover))
        held = chosen
        i += p.hold
    if weeks:  # la dernière vente se paie aussi
        last = weeks[-1]
        weeks[-1] = Week(last.start, last.holdings, (1 + last.ret) * (1 - cost) - 1, last.gross, last.basket,
                         last.turnover + 1)
    return weeks


def split(weeks: list[Week]) -> tuple[list[Week], list[Week], list[Week]]:
    n = len(weeks)
    a, b = int(n * STUDY_SHARE), int(n * (1 - TEST_SHARE))
    return weeks[:a], weeks[a:b], weeks[b:]


@dataclass(frozen=True)
class PortfolioRow:
    variant: str
    lookback: int
    top: int
    weeks: int  # validation, comme tout ce qui suit sauf mention
    mean_pct: float  # rendement moyen par semaine, après frais (en %)
    gross_pct: float
    basket_pct: float
    excess_pct: float  # au-dessus du panier de toutes les cryptos
    win_rate: float  # part des semaines gagnantes
    ci_low: float
    ci_high: float
    ci_low_adjusted: float
    excess_ci_low_adjusted: float  # borne basse durcie de l'écart hebdomadaire avec le panier
    study_weeks: int
    study_mean_pct: float
    study_excess_pct: float
    test_weeks: int
    test_mean_pct: float
    test_excess_pct: float
    turnover: float  # rotation moyenne par semaine (0 = rien ne change, 2 = tout change)
    verdict: str
    holdings: tuple[str, ...]  # le dernier choix de la variante


def mean_pct(values: list[float]) -> float:
    return 100 * float(np.mean(values)) if values else math.nan


def portfolio_verdict(weeks: int, mean: float, excess: float, study_excess: float, excess_ci_low_adjusted: float,
                      test_weeks: int, test_mean: float, test_excess: float) -> str:
    if weeks < MIN_WEEKS:
        return "trop peu de semaines"
    if not mean > 0:
        return "perd de l'argent"
    if not excess > 0:
        return "ne bat pas le panier"  # garder toutes les cryptos aurait rapporté autant, sans rien choisir
    if not study_excess > 0:
        return "instable"  # battait le panier sur la validation, pas sur l'étude
    confirmed = test_weeks >= MIN_TEST_WEEKS
    if confirmed and not test_excess > 0:
        return "instable"  # ne bat plus le panier sur le test final, la période la plus récente
    if excess_ci_low_adjusted > 0 and confirmed and test_mean > 0:
        return "prometteur"
    return "à surveiller"


def evaluate(opens: pd.DataFrame, closes: pd.DataFrame, cost: float,
             variants: dict[str, PortfolioParams] = PORTFOLIO_VARIANTS) -> list[PortfolioRow]:
    z = NormalDist().inv_cdf(1 - 0.05 / (2 * max(len(variants), 1)))  # seuil durci par le nombre de variantes
    rows = []
    for name, p in variants.items():
        weeks = simulate(opens, closes, p, cost)
        study, valid, test = split(weeks)
        rets = [w.ret for w in valid]
        n = len(rets)
        sd = float(np.std(rets, ddof=1)) if n >= 2 else math.nan
        m = float(np.mean(rets)) if n else math.nan
        half, half_adj = (1.96 * sd / math.sqrt(n), z * sd / math.sqrt(n)) if n >= 2 else (math.nan, math.nan)
        gaps = [w.ret - w.basket for w in valid]
        gap_half_adj = z * float(np.std(gaps, ddof=1)) / math.sqrt(n) if n >= 2 else math.nan
        basket, test_basket = mean_pct([w.basket for w in valid]), mean_pct([w.basket for w in test])
        row = PortfolioRow(
            variant=name, lookback=p.lookback, top=p.top, weeks=n, mean_pct=100 * m,
            gross_pct=mean_pct([w.gross for w in valid]), basket_pct=basket, excess_pct=100 * m - basket,
            win_rate=float(np.mean([r > 0 for r in rets])) if n else math.nan,
            ci_low=100 * (m - half), ci_high=100 * (m + half), ci_low_adjusted=100 * (m - half_adj),
            excess_ci_low_adjusted=100 * (float(np.mean(gaps)) - gap_half_adj) if n >= 2 else math.nan,
            study_weeks=len(study), study_mean_pct=mean_pct([w.ret for w in study]),
            study_excess_pct=mean_pct([w.ret - w.basket for w in study]),
            test_weeks=len(test), test_mean_pct=mean_pct([w.ret for w in test]),
            test_excess_pct=mean_pct([w.ret for w in test]) - test_basket,
            turnover=float(np.mean([w.turnover for w in weeks])) if weeks else math.nan,
            verdict="", holdings=weeks[-1].holdings if weeks else (),
        )
        rows.append(PortfolioRow(**{**asdict(row), "verdict": portfolio_verdict(
            row.weeks, row.mean_pct, row.excess_pct, row.study_excess_pct, row.excess_ci_low_adjusted, row.test_weeks,
            row.test_mean_pct, row.test_excess_pct)}))
    return sorted(rows, key=lambda r: -(r.mean_pct if math.isfinite(r.mean_pct) else -math.inf))


def overall_verdict(rows: list[PortfolioRow], universe: int) -> str:
    bias = (f"Attention : les {universe} cryptos testées sont celles qui s'échangent aujourd'hui ; celles qui ont "
            "disparu manquent, ce qui embellit le passé.")
    retained = [r for r in rows if r.verdict in RETAINED]
    if retained:
        best = retained[0]
        return (f"VERDICT : {len(retained)} variante(s) retenue(s). La meilleure : {best.variant}, "
                f"{best.mean_pct:+.2f} % par semaine après frais, soit {best.excess_pct:+.2f} % de plus que le panier "
                f"de toutes les cryptos ({best.verdict}).\nProchaine étape : le portefeuille en argent fictif, "
                f"plusieurs semaines.\n{bias}")
    return ("VERDICT : aucune variante du momentum croisé ne bat, hors échantillon et frais compris, le simple panier "
            f"de toutes les cryptos : le portefeuille ne démarrera pas.\n{bias}")


def format_rows(rows: list[PortfolioRow]) -> str:
    width = max([32, *(len(r.variant) + 1 for r in rows)])
    header = (f"{'Variante':<{width}}{'Semaines':>9}{'Par semaine':>13}{'Panier':>9}{'Au-dessus':>11}"
              f"{'Test final':>12}  Verdict")
    lines = [header, "-" * (len(header) + 16)]
    for r in rows:
        def pct(x: float) -> str:
            return "n/a" if not math.isfinite(x) else f"{x:+.2f} %"
        lines.append(f"{r.variant:<{width}}{r.weeks:>9}{pct(r.mean_pct):>13}{pct(r.basket_pct):>9}"
                     f"{pct(r.excess_pct):>11}{pct(r.test_mean_pct):>12}  {r.verdict}")
    return "\n".join(lines)


def save(path: Path, rows: list[PortfolioRow], verdict: str, **meta) -> None:
    payload = {**meta, "verdict": verdict, "rows": [asdict(r) for r in rows]}
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, default=list))


def load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# --- Le portefeuille en argent fictif ------------------------------------------------------------------------------

def next_rotation(now: datetime, hour: int = 0, minute: int = 10) -> datetime:
    """La prochaine rotation : le lendemain à 00 h 10 UTC (la bougie du jour vient de se clôturer), puis chaque semaine."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


class PaperPortfolio:
    """Un portefeuille fictif qui applique une variante retenue : chaque semaine, garder les K cryptos qui ont le plus
    monté, à parts égales, au prix réel du moment, frais et glissement compris. Rien ne part sur une plateforme."""

    def __init__(self, path: Path, name: str, params: PortfolioParams, fee: float, slippage: float, start: float):
        self.path, self.name, self.params, self.fee, self.slippage = path, name, params, fee, slippage
        try:
            self.state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = None
        if not isinstance(self.state, dict) or self.state.get("variant") != name:
            self.state = {"variant": name, "params": asdict(params), "start": start, "cash": start, "holdings": {},
                          "since": datetime.now(timezone.utc).isoformat(timespec="seconds"), "next": None,
                          "rotations": [], "history": []}

    def save(self) -> None:
        atomic_write(self.path, json.dumps(self.state, ensure_ascii=False, indent=1))

    def value(self, prices: dict[str, float]) -> float:
        """Argent fictif + cryptos au prix du moment (au dernier prix connu si une plateforme n'a pas répondu)."""
        known = self.state.get("prices") or {}
        return self.state["cash"] + sum(q * (prices.get(s) or known.get(s) or 0.0)
                                        for s, q in self.state["holdings"].items())

    def due(self, now: datetime) -> bool:
        nxt = self.state.get("next")
        return nxt is None or now >= datetime.fromisoformat(nxt)

    def rotate(self, closes: pd.DataFrame, prices: dict[str, float], now: datetime) -> dict:
        """La rotation de la semaine : classement sur les dernières clôtures journalières, puis ventes et achats."""
        ranks = ranking(closes, len(closes) - 1, self.params.lookback)
        ranks = ranks[[s for s in ranks.index if prices.get(s)]]
        if len(ranks) < max(MIN_COINS, self.params.top):
            raise ValueError(f"Seulement {len(ranks)} cryptos avec un historique suffisant : rotation reportée.")
        chosen = list(ranks.index[:self.params.top])
        holdings, known = self.state["holdings"], self.state.get("prices") or {}
        price = {s: prices.get(s) or known.get(s) for s in [*holdings, *chosen]}  # dernier prix connu en secours
        if missing := [s for s in holdings if not price[s]]:
            raise ValueError(f"Pas de prix pour {', '.join(missing)} : rotation reportée.")
        sold, bought, costs = [], [], 0.0

        def sell(symbol: str, qty: float) -> None:
            nonlocal costs
            gross = qty * price[symbol]
            net = gross * (1 - self.slippage) * (1 - self.fee)
            self.state["cash"] += net
            costs += gross - net

        for symbol in [s for s in holdings if s not in chosen]:  # d'abord vendre ce qui sort du classement
            sell(symbol, holdings.pop(symbol))
            sold.append(symbol)
        target = self.value(price) / len(chosen)  # puis remettre chaque crypto gardée à sa part
        gaps = {s: target - holdings.get(s, 0.0) * price[s] for s in chosen}
        for symbol, gap in sorted(gaps.items(), key=lambda kv: kv[1]):  # alléger avant de renforcer : l'argent suit
            if abs(gap) < max(1.0, 0.01 * target):  # écart minime : pas d'ordre (évite des frais pour rien)
                continue
            if gap < 0:
                qty = -gap / price[symbol]
                holdings[symbol] -= qty
                sell(symbol, qty)
            else:
                spend = min(gap, self.state["cash"])
                qty = spend * (1 - self.fee) / (price[symbol] * (1 + self.slippage))
                holdings[symbol] = holdings.get(symbol, 0.0) + qty
                self.state["cash"] -= spend
                costs += spend - qty * price[symbol]
                bought.append(symbol)
        rotation = {"t": now.isoformat(timespec="seconds"), "chosen": chosen, "sold": sold, "bought": bought,
                    "costs": costs, "value": self.value(price),
                    "ranking": {s: float(v) for s, v in ranks.head(10).items()}}
        self.state["rotations"].append(rotation)
        del self.state["rotations"][:-200]
        self.state["next"] = (next_rotation(now) + timedelta(days=self.params.hold - 1)).isoformat(timespec="seconds")
        self.mark(price, now, force=True)
        return rotation

    def mark(self, prices: dict[str, float], now: datetime, force: bool = False) -> None:
        """Note la valeur du portefeuille (au plus une fois par heure)."""
        history = self.state["history"]
        if force or not history or now - datetime.fromisoformat(history[-1]["t"]) >= timedelta(hours=1):
            history.append({"t": now.isoformat(timespec="seconds"), "value": self.value(prices)})
            del history[:-2000]
        self.state["value"] = self.value(prices)
        known = self.state.get("prices") or {}
        self.state["prices"] = {s: prices.get(s) or known.get(s) for s in self.state["holdings"]}
        self.save()
