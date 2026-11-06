"""L'actualité des cryptos, pour comprendre ce qui se passe : jamais une source d'ordres.

- Les derniers titres de grands sites spécialisés (flux RSS publics), les cryptos qu'ils citent, et ce que le prix de
  chacune a fait depuis la publication. La recherche trouve que le marché digère les grandes nouvelles en moins d'une
  heure, et commence parfois à bouger avant leur publication (Blasco et al., 2025) : quand on lit le titre, une bonne
  partie du mouvement a souvent déjà eu lieu.
- L'indice « peur et avidité » (alternative.me, de 0 = peur extrême à 100 = avidité extrême), son historique depuis
  2018, et ce qu'a fait le Bitcoin dans les 30 jours qui ont suivi ses extrêmes, comparé à un jour quelconque. Les
  études sont partagées sur son pouvoir de prévision ; l'étude du bot le rappelle (jours qui se chevauchent : bien
  moins d'épisodes indépendants qu'il n'y paraît).
"""
from __future__ import annotations

import email.utils
import json
import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

FEEDS = (
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
)
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
USER_AGENT = "Mozilla/5.0 (compatible; tradingbot-actualite)"
KEEP_NEWS = 40
EXTREME_FEAR, EXTREME_GREED = 25, 75  # les bornes des zones extrêmes de l'indice
STUDY_DAYS = 30

# Noms courants des cryptos dans les titres en anglais (les tickers seuls, comme « BTC », sont aussi reconnus).
NAMES = {
    "bitcoin": "BTC", "ether": "ETH", "ethereum": "ETH", "solana": "SOL", "ripple": "XRP", "dogecoin": "DOGE",
    "cardano": "ADA", "binance coin": "BNB", "tron": "TRX", "chainlink": "LINK", "avalanche": "AVAX",
    "polkadot": "DOT", "litecoin": "LTC", "shiba inu": "SHIB", "toncoin": "TON", "stellar": "XLM", "uniswap": "UNI",
    "aptos": "APT", "arbitrum": "ARB", "optimism": "OP", "polygon": "POL", "cosmos": "ATOM", "filecoin": "FIL",
    "hedera": "HBAR", "monero": "XMR", "pepe": "PEPE", "bonk": "BONK", "floki": "FLOKI", "dogwifhat": "WIF",
}
NOT_COINS = {"CEO", "ETF", "SEC", "USD", "USA", "AI", "IPO", "FBI", "DOJ", "CFTC", "EU", "UK", "GDP", "CPI", "FOMC",
             "NFT", "DAO", "DEX", "CEX", "API", "OTC", "ATH", "ICO", "FTX", "IRS", "IMF", "ECB", "US", "THE", "NEW"}


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        when = email.utils.parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        try:
            when = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _text(node, tag: str) -> str:
    child = node.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def parse_feed(xml_text: str, source: str) -> list[dict]:
    """Les articles d'un flux RSS 2.0 ou Atom : titre, lien, date (UTC), résumé sans balises."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    atom = "{http://www.w3.org/2005/Atom}"
    for item in root.iter("item"):
        items.append({"title": _text(item, "title"), "link": _text(item, "link"),
                      "published": parse_date(_text(item, "pubDate")), "summary": _text(item, "description")})
    for entry in root.iter(atom + "entry"):
        link = entry.find(atom + "link")
        items.append({"title": _text(entry, atom + "title"), "link": link.get("href", "") if link is not None else "",
                      "published": parse_date(_text(entry, atom + "updated") or _text(entry, atom + "published")),
                      "summary": _text(entry, atom + "summary")})
    out = []
    for it in items:
        if not it["title"] or not it["link"].startswith(("http://", "https://")):
            continue
        summary = re.sub(r"<[^>]+>", " ", it["summary"])
        out.append({**it, "summary": " ".join(summary.split())[:280], "source": source})
    return out


def mentions(text: str, known: set[str] | None = None) -> list[str]:
    """Les cryptos citées, par leur nom (« Bitcoin ») ou leur ticker en majuscules (« BTC »), dans l'ordre où elles
    apparaissent. Avec `known` (les tickers suivis), un ticker inconnu est ignoré."""
    hits = []
    lower = text.lower()
    for name, base in NAMES.items():
        for m in re.finditer(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", lower):
            hits.append((m.start(), base))
    for m in re.finditer(r"(?<![A-Za-z0-9$])\$?([A-Z]{2,6})(?![A-Za-z0-9])", text):
        ticker = m.group(1)
        if ticker not in NOT_COINS and (known is None or ticker in known):
            hits.append((m.start(), ticker))
    found = []
    for _, base in sorted(hits):
        if base not in found:
            found.append(base)
    return found


def merge(items: list[dict], known: set[str] | None = None) -> list[dict]:
    """Les articles de tous les flux, sans doublon, du plus récent au plus ancien, avec leurs cryptos citées."""
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        key = it["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({**it, "coins": mentions(it["title"] + " " + it["summary"], known)[:4]})
    return out[:KEEP_NEWS]


def parse_fng(payload: dict) -> pd.Series:
    """L'historique de l'indice peur et avidité : une valeur par jour (UTC), du plus ancien au plus récent."""
    rows = []
    for d in payload.get("data") or []:
        try:
            rows.append((pd.Timestamp(int(d["timestamp"]), unit="s", tz="UTC").normalize(), float(d["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(dict(rows)).sort_index()
    return s[~s.index.duplicated(keep="last")]


def zone(value: float) -> str:
    if value <= EXTREME_FEAR:
        return "peur extrême"
    if value < 45:
        return "peur"
    if value <= 55:
        return "neutre"
    if value < EXTREME_GREED:
        return "avidité"
    return "avidité extrême"


def fng_study(fng: pd.Series, closes: pd.Series, days: int = STUDY_DAYS) -> dict | None:
    """Ce qu'a fait le prix (souvent le Bitcoin) dans les `days` jours suivant chaque jour de peur ou d'avidité
    extrême, comparé à tous les jours. L'indice du jour J est publié à 00 h UTC sur les données de la veille : on
    l'utilise avec la clôture du jour J, sans regard vers le futur."""
    if fng.empty or closes.empty:
        return None
    closes = closes.copy()
    closes.index = closes.index.normalize()
    closes = closes[~closes.index.duplicated(keep="last")]
    forward = closes.shift(-days) / closes - 1
    joined = pd.DataFrame({"fng": fng, "ret": forward}).dropna()
    if len(joined) < 100:
        return None

    def stats(mask) -> dict:
        r = joined.loc[mask, "ret"]
        episodes = int((mask & ~mask.shift(1, fill_value=False)).sum())  # séries de jours d'affilée
        return {"days": int(len(r)), "episodes": episodes, "mean": float(r.mean()) if len(r) else math.nan,
                "win_rate": float((r > 0).mean()) if len(r) else math.nan}

    everything = pd.Series(True, index=joined.index)
    return {"horizon": days, "since": str(joined.index[0].date()), "all": stats(everything),
            "fear": stats(joined["fng"] <= EXTREME_FEAR), "greed": stats(joined["fng"] >= EXTREME_GREED)}


def study_text(study: dict | None, coin: str = "Bitcoin") -> str:
    if not study or not study["fear"]["days"] or not study["greed"]["days"]:
        return "Pas assez d'historique pour étudier l'indice."

    def p(x):
        return "—" if not math.isfinite(x) else f"{100 * x:+.1f} %".replace(".", ",").replace("-", "−")

    f, g, a = study["fear"], study["greed"], study["all"]
    return (f"Depuis {study['since'][:4]}, après un jour de peur extrême, le {coin} a fait en moyenne {p(f['mean'])} "
            f"les {study['horizon']} jours suivants ({f['days']} jours, en {f['episodes']} épisodes) ; après un jour "
            f"d'avidité extrême, {p(g['mean'])} ({g['days']} jours, {g['episodes']} épisodes) ; un jour quelconque, "
            f"{p(a['mean'])}. Les jours d'un même épisode se suivent et se ressemblent : il y a bien moins de cas "
            "indépendants qu'il n'y paraît. C'est une observation, pas une règle testée par le labo.")


class NewsSource:
    """Le site va chercher les titres toutes les 10 minutes et l'indice toutes les heures (cache dans data/cache)."""

    def __init__(self, cache_dir: Path, get=None, closes=None, known=None):
        self.cache_dir = cache_dir
        self.get = get or _http_get
        self.closes = closes  # () -> clôtures journalières du Bitcoin, pour l'étude de l'indice
        self.known = known  # () -> les cryptos cotées sur la plateforme
        self.fng_at, self.fng = -math.inf, None
        self.prices_at_pub: dict[tuple[str, str], float] = {}

    def fetch(self) -> dict:
        items, errors = [], []
        for name, url in FEEDS:
            try:
                items += parse_feed(self.get(url), name)
            except Exception as exc:  # un site en panne n'arrête pas les autres
                errors.append(f"{name} : {short(exc)}")
        known = self.known() if self.known else None
        news = merge(items, known)
        if time.time() - self.fng_at >= 3600 or self.fng is None:
            try:
                self.fng = self._fng()
                self.fng_at = time.time()
            except Exception as exc:
                errors.append(f"indice peur et avidité : {short(exc)}")
        for n in news:
            n["published"] = n["published"].isoformat() if n["published"] else None
        return {"news": news, "fng": self.fng, "errors": errors}

    def _fng(self) -> dict:
        path = self.cache_dir / "peur-avidite.json"
        payload = json.loads(self.get(FNG_URL))
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
        series = parse_fng(payload)
        if series.empty:
            raise ValueError("indice vide")
        study = None
        if self.closes:
            try:
                study = fng_study(series, self.closes())
            except Exception as exc:
                log.warning("Étude de l'indice impossible : %s", short(exc))
        last = series.iloc[-1]
        recent = series.iloc[-365:]
        return {"value": float(last), "zone": zone(float(last)), "date": str(series.index[-1].date()),
                "history": [[str(d.date()), float(v)] for d, v in recent.items()],
                "study": study, "study_text": study_text(study)}


def short(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    return text if len(text) <= 120 else text[:117] + "…"


def _http_get(url: str) -> str:
    import requests
    response = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def reaction(news: list[dict], price_then, price_now) -> None:
    """Ajoute à chaque crypto citée son prix à la publication et son mouvement depuis (en place)."""
    for n in news:
        moves = []
        for base in n.get("coins") or []:
            then, now = price_then(base, n.get("published")), price_now(base)
            moves.append({"coin": base, "change": now / then - 1 if then and now else None})
        n["moves"] = moves
