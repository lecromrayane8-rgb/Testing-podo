"""Tableau de bord : une page HTML autonome qui résume tous les bots.

Réécrite dans data/tableau-de-bord.html à chaque tour de la boucle (et par `python main.py tableau`),
elle se recharge toute seule chaque minute. Aucune ressource externe : elle s'ouvre hors ligne.
"""
from __future__ import annotations

import csv
import html
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .broker import atomic_write
from .config import Settings
from .data import timeframe_to_ms
from .lab import LAB_FILE, PROMISING, load_lab
from .robustness import MIN_TRADES
from .live import bot_name, bot_paths
from .risk import RiskGuard, TradeStats, is_candidate
from .robustness import ROBUST, load_results

FILENAME = "tableau-de-bord.html"
ROBUSTNESS_FILE = "robustesse.json"
STALE_AFTER_S = 10 * 60
MAX_SERIES = 8  # couleurs de la palette ; au-delà, un bot reste dans les cartes et le tableau
MAX_EVENTS = 20
W, H, ML, MR, MT, MB = 960, 320, 64, 208, 16, 36

MODE_LABELS = {
    "paper": "argent fictif (paper)",
    "testnet": "testnet (argent fictif)",
    "demo": "démo (argent fictif)",
    "live": "ARGENT RÉEL",
}
VERDICT_STYLE = {
    ROBUST: ("good", "✓"),
    PROMISING: ("good", "✓"),
    "perd de l'argent": ("critical", "✕"),
    "positif, peut-être de la chance": ("warning", "!"),
    "à surveiller": ("warning", "!"),
    "instable": ("warning", "!"),
}


# --- lecture des fichiers des bots ----------------------------------------------------
def num(value, default=None):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def parse_time(text) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


@dataclass
class BotView:
    name: str
    symbol: str
    timeframe: str
    label: str  # stratégie d'un bot du tournoi ("" sinon)
    slot: int
    initial: float | None
    equity: float | None
    trades: list[dict]
    position: dict | None
    order: dict | None
    blocked: str | None
    updated_at: datetime | None
    last_price: float | None = None
    eliminated: str | None = None
    stats: TradeStats = field(default_factory=TradeStats)

    @property
    def started(self) -> bool:
        return bool(self.initial) and self.equity is not None

    @property
    def pnl(self) -> float:
        return self.equity - self.initial if self.started else 0.0

    @property
    def pnl_pct(self) -> float:
        return 100 * self.pnl / self.initial if self.started else 0.0

    @property
    def win_rate(self) -> float | None:
        return sum(t["pnl"] > 0 for t in self.trades) / len(self.trades) if self.trades else None


def read_trades(path: Path) -> list[dict]:
    if not path.exists():
        return []
    trades = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            pnl, exit_time = num(row.get("pnl")), parse_time(row.get("sortie"))
            if pnl is None or exit_time is None:
                continue
            entry_price, qty = num(row.get("prix_entree")), num(row.get("quantite"))
            cost = num(row.get("cout")) or (entry_price or 0) * (qty or 0)
            trades.append({
                "entree": parse_time(row.get("entree")),
                "sortie": exit_time,
                "prix_entree": entry_price,
                "prix_sortie": num(row.get("prix_sortie")),
                "pnl": pnl,
                "pct": 100 * pnl / cost if cost else None,
                "raison": row.get("raison") or "",
            })
    return sorted(trades, key=lambda t: t["sortie"])


def load_views(settings: Settings, now: datetime | None = None, bots: list[Settings] | None = None) -> list[BotView]:
    now = now or datetime.now(timezone.utc)
    views = []
    for slot, bs in enumerate(bots if bots is not None else settings.per_bot(), start=1):
        state_path, journal_path = bot_paths(bs)
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            state = {}
        trades = read_trades(journal_path)
        capital = num(state.get("capital"))
        initial = num(state.get("initial_capital"))
        if initial is None and capital is not None:
            initial = capital - sum(t["pnl"] for t in trades)
        guard = RiskGuard.from_dict(bs.risk, state.get("guard")) if state.get("guard") else None
        equity = num(state.get("equity"), capital)
        if guard and equity is not None:
            # Copie locale (rien n'est sauvegardé) : la limite journalière d'un jour passé expire, comme dans le bot.
            guard.update(equity, now.astimezone(timezone.utc).strftime("%Y-%m-%d"))
        stats = TradeStats()
        for t in trades:
            if t["pct"] is not None:
                stats.add(t["pct"] / 100)
        views.append(BotView(
            name=bot_name(bs),
            symbol=bs.symbol,
            timeframe=bs.timeframe,
            label=bs.bot_label,
            slot=slot,
            initial=initial,
            equity=equity,
            trades=trades,
            position=state.get("position"),
            order=state.get("order"),
            blocked=guard.blocked_reason() if guard else None,
            updated_at=parse_time(state.get("updated_at")),
            last_price=num(state.get("last_price")),
            eliminated=state.get("eliminated"),
            stats=stats,
        ))
    return views


# --- mise en forme ---------------------------------------------------------------------
def esc(value) -> str:
    return html.escape(str(value), quote=True)


def fmt(x: float, decimals: int = 2) -> str:
    """1234.5 -> « 1 234,50 » (espace fine, virgule décimale)."""
    return f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")


def fmt_signed(x: float, decimals: int = 2, unit: str = "") -> str:
    x = round(x, decimals)
    sign = "+" if x > 0 else "−" if x < 0 else ""
    return f"{sign}{fmt(abs(x), decimals)}{unit}"


def fmt_price(x: float | None) -> str:
    """Cinq chiffres significatifs, au moins deux décimales : 58 500,00 pour le BTC, 0,000012340 pour PEPE."""
    if x is None:
        return "—"
    if x <= 0:
        return fmt(x, 2)
    return fmt(x, max(2, 4 - math.floor(math.log10(x))))


def fmt_qty(x: float | None) -> str:
    """Quantité sans zéros inutiles : 0.05 -> « 0,05 », 0.00672 -> « 0,00672 »."""
    if x is None:
        return "—"
    if x >= 1000:
        return fmt(x, 2)
    return f"{x:.8f}".rstrip("0").rstrip(".").replace(".", ",")


def tick_decimals(step: float) -> int:
    """Assez de décimales pour que chaque graduation affiche sa vraie valeur (0,25 et non 0,2)."""
    return next((d for d in range(5) if abs(round(step, d) - step) < 1e-9), 4)


def local(t: datetime, pattern: str = "%d/%m %H:%M") -> str:
    return t.astimezone().strftime(pattern)


def duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 120:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{minutes // 60} h"
    return f"{minutes // (24 * 60)} jours"


def delta(x: float, decimals: int = 2, unit: str = "") -> str:
    """Variation signée : seule la flèche porte la couleur, le nombre reste à l'encre du texte."""
    if round(x, decimals) == 0:
        return f"{fmt(0, decimals)}{unit}"
    cls, arrow = ("up", "▲") if x > 0 else ("down", "▼")
    return f'<span class="{cls}" aria-hidden="true">{arrow}</span> {fmt_signed(x, decimals, unit)}'


def status(view: BotView, now: datetime, stale_after_s: float = STALE_AFTER_S) -> tuple[str, str, str, str]:
    """(style, icône, libellé court, détail) de l'état d'un bot."""
    if not view.started:
        return "muted", "○", "Pas encore lancé", ""
    if view.updated_at and (now - view.updated_at).total_seconds() > stale_after_s:
        return "critical", "✕", "Arrêté ?", f"Aucune nouvelle depuis {duration((now - view.updated_at).total_seconds())}"
    if view.eliminated:
        return "critical", "✕", "Éliminée", view.eliminated
    if view.blocked:
        return "warning", "!", "Achats bloqués", view.blocked
    if view.order:
        side = "d'achat" if view.order.get("side") == "buy" else "de vente"
        return "neutral", "●", f"Ordre limite {side} en attente", ""
    if view.position:
        return "neutral", "●", "En position", ""
    return "neutral", "○", "En attente d'un signal", ""


def chip(style: str, icon: str, label: str) -> str:
    return f'<span class="chip chip-{style}"><span aria-hidden="true">{icon}</span> {esc(label)}</span>'


# --- graphique ---------------------------------------------------------------------------
@dataclass
class Series:
    name: str
    slot: int
    points: list[tuple[float, float]]


def _ms(t: datetime) -> float:
    return t.timestamp() * 1000


def points(view: BotView) -> list[tuple[float, float]]:
    """Rendement cumulé (%) : 0 au départ, puis après chaque trade clôturé, puis la valeur actuelle."""
    return group_points([view])


def group_points(members: list[BotView]) -> list[tuple[float, float]]:
    """Rendement cumulé (%) d'un groupe de bots (un bot seul, ou tous ceux d'une même stratégie)."""
    started = [v for v in members if v.started]
    starts = [(v.trades[0]["entree"] or v.trades[0]["sortie"]) if v.trades else v.updated_at for v in started]
    starts = [t for t in starts if t is not None]
    if not starts:
        return []
    initial = sum(v.initial for v in started)
    pts = [(_ms(min(starts)), 0.0)]
    realized = 0.0
    for when, pnl in sorted((t["sortie"], t["pnl"]) for v in started for t in v.trades):
        realized += pnl
        pts.append((_ms(when), 100 * realized / initial))
    latest = max((v.updated_at for v in started if v.updated_at), default=None)
    if latest and _ms(latest) >= pts[-1][0]:
        pts.append((_ms(latest), 100 * sum(v.pnl for v in started) / initial))
    return pts


def bot_series(views: list[BotView]) -> list[Series]:
    return [Series(v.name, v.slot, pts) for v in views[:MAX_SERIES] if len(pts := points(v)) >= 2]


def strategy_series(views: list[BotView]) -> list[Series]:
    """Une courbe par stratégie : la couleur suit la stratégie, jamais son rang."""
    groups: dict[str, list[BotView]] = {}
    for v in views:
        groups.setdefault(v.label, []).append(v)
    series = []
    for slot, (label, members) in enumerate(list(groups.items())[:MAX_SERIES], start=1):
        if len(pts := group_points(members)) >= 2:
            series.append(Series(label, slot, pts))
    return series


def color_slots(views: list[BotView]) -> dict[str, int]:
    """Couleur de chaque bot dans les tableaux : celle de sa courbe (celle de sa stratégie dans le tournoi)."""
    if any(v.label for v in views):
        labels = {label: slot for slot, label in enumerate(dict.fromkeys(v.label for v in views), start=1)}
        return {v.name: labels[v.label] for v in views if labels[v.label] <= MAX_SERIES}
    return {v.name: v.slot for v in views if v.slot <= MAX_SERIES}


def bot_cell(view: BotView, slots: dict[str, int]) -> str:
    """Nom du bot avec la couleur de sa courbe ; sur téléphone, la stratégie passe à la ligne."""
    slot = slots.get(view.name)
    key = f'<span class="line-key" style="background: var(--series-{slot})"></span>' if slot else ""
    strategy = f'<span class="strat"><span class="sep"> · </span>{esc(view.label)}</span>' if view.label else ""
    return (f'<td class="bot-cell"><span class="bot">{key}<span><span class="pair">{esc(view.symbol)} '
            f"{esc(view.timeframe)}</span>{strategy}</span></span></td>")


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    raw = (hi - lo) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    first, last = math.floor(lo / step) * step, math.ceil(hi / step) * step
    return [first + i * step for i in range(int(round((last - first) / step)) + 1)]


def chart(series: list[Series]) -> str:
    if not series:
        return '<p class="empty">La courbe apparaîtra quand un bot aura tourné quelques minutes.</p>'
    times = [t for sr in series for t, _ in sr.points]
    values = [v for sr in series for _, v in sr.points]
    t0, t1 = min(times), max(times)
    t1 = t1 if t1 > t0 else t0 + 3_600_000
    lo, hi = min(min(values), -0.5), max(max(values), 0.5)
    ticks = nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    decimals = tick_decimals(ticks[1] - ticks[0])

    def x_of(t: float) -> float:
        return ML + (t - t0) / (t1 - t0) * (W - ML - MR)

    def y_of(v: float) -> float:
        return MT + (hi - v) / (hi - lo) * (H - MT - MB)

    parts = []
    for v in ticks:
        y = y_of(v)
        cls = "zero" if abs(v) < 1e-9 else "grid"
        parts.append(f'<line class="{cls}" x1="{ML}" x2="{W - MR}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{ML - 8}" y="{y + 4:.1f}" text-anchor="end">{fmt_signed(v, decimals, " %")}</text>')
    pattern = "%d/%m" if t1 - t0 > 2 * 86_400_000 else "%d/%m %H:%M"
    for i in range(5):
        t = t0 + i * (t1 - t0) / 4
        anchor = "start" if i == 0 else "end" if i == 4 else "middle"
        label = local(datetime.fromtimestamp(t / 1000, tz=timezone.utc), pattern)
        parts.append(f'<text class="tick" x="{x_of(t):.1f}" y="{H - 12}" text-anchor="{anchor}">{label}</text>')

    ends = []
    for sr in series:
        pts = sr.points
        d = f"M{x_of(pts[0][0]):.1f} {y_of(pts[0][1]):.1f}" + "".join(
            f"H{x_of(t):.1f}V{y_of(v):.1f}" for t, v in pts[1:]
        )
        parts.append(f'<path class="line" style="stroke: var(--series-{sr.slot})" d="{d}"/>')
        ends.append((sr, x_of(pts[-1][0]), y_of(pts[-1][1]), pts[-1][1]))
    # Étiquettes directes en bout de ligne, écartées d'au moins 16 px, reliées par un trait si déplacées.
    ends.sort(key=lambda e: e[2])
    label_y = []
    for _, _, y, _ in ends:
        label_y.append(max(y, label_y[-1] + 16) if label_y else max(y, MT + 8))
    overflow = label_y[-1] - (H - MB) if label_y else 0
    if overflow > 0:
        label_y = [y - overflow for y in label_y]
    for (sr, x, y, value), ly in zip(ends, label_y):
        lx = W - MR + 14
        if abs(ly - y) > 2 or lx - x > 16:
            parts.append(f'<line class="leader" x1="{x:.1f}" y1="{y:.1f}" x2="{lx - 4}" y2="{ly:.1f}"/>')
        parts.append(f'<circle class="end" style="fill: var(--series-{sr.slot})" cx="{x:.1f}" cy="{y:.1f}" r="4"/>')
        parts.append(
            f'<text class="end-label" x="{lx}" y="{ly + 4:.1f}">{esc(short(sr.name, 16))} '
            f'<tspan class="end-value">{fmt_signed(value, 2, " %")}</tspan></text>'
        )
    parts.append(f'<line id="crosshair" class="crosshair" x1="0" x2="0" y1="{MT}" y2="{H - MB}"/>')
    parts.append(f'<rect class="hit" x="{ML}" y="{MT}" width="{W - ML - MR}" height="{H - MT - MB}"/>')

    data = {
        "w": W, "ml": ML, "mr": MR, "t0": t0, "t1": t1,
        "series": [{"name": sr.name, "slot": sr.slot, "points": sr.points} for sr in series],
    }
    payload = json.dumps(data).replace("</", "<\\/")
    legend = "".join(
        f'<li><span class="line-key" style="background: var(--series-{sr.slot})"></span>{esc(sr.name)}</li>'
        for sr in series
    )
    return (
        f'<ul class="legend">{legend}</ul>'
        f'<div class="chart-box"><svg id="equity-chart" viewBox="0 0 {W} {H}" role="img" tabindex="0" '
        f'aria-label="Rendement cumulé depuis le départ, en pourcentage">{"".join(parts)}</svg>'
        f'<div id="chart-tip" class="tip" hidden></div></div>'
        f'<script type="application/json" id="chart-data">{payload}</script>'
    )


def short(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"


# --- sections ------------------------------------------------------------------------------
ICONS = {
    "scanner": '<circle cx="11" cy="11" r="6"/><path d="M16 16l4 4"/>',
    "stratege": '<path d="M5 19V11M12 19V5M19 19v-6"/>',
    "execution": '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    "gardien": '<path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z"/>',
}


def kpis(views: list[BotView], quote: str) -> str:
    started = [v for v in views if v.started]
    if not started:
        return '<p class="empty">Aucun bot n\'a encore tourné. Lance « 4 - Lancer le bot ».</p>'
    initial = sum(v.initial for v in started)
    equity = sum(v.equity for v in started)
    pnl = equity - initial
    trades = [t for v in views for t in v.trades]
    wins = sum(t["pnl"] > 0 for t in trades)
    unit = f" ({esc(quote)})" if quote else ""
    tiles = [  # l'unité dans le libellé : les grands nombres tiennent sur une ligne
        (f"Résultat net après frais{unit}", delta(pnl), fmt_signed(100 * pnl / initial, 2, " %"), " tile-hero"),
        (f"Portefeuille{unit}", fmt(equity), f"départ {fmt(initial)}", ""),
        ("Trades", str(len(trades)), f"{fmt(100 * wins / len(trades), 0)} % gagnants" if trades else "aucun pour l'instant", ""),
        ("En position", f"{sum(1 for v in views if v.position)} / {len(views)}", "bots", ""),
        ("Éliminées", str(sum(1 for v in views if v.eliminated)), "coupées par le gardien", ""),
    ]
    return '<div class="kpis">' + "".join(
        f'<div class="tile{extra}"><p class="tile-label">{label}</p><p class="tile-value">{value}</p>'
        f'<p class="tile-sub">{sub}</p></div>'
        for label, value, sub, extra in tiles
    ) + "</div>"


def agent(kind: str, slot: int, name: str, role: str, metric: str, detail: str) -> str:
    return (
        f'<article class="agent"><div class="agent-head"><svg viewBox="0 0 24 24" aria-hidden="true" '
        f'style="color: var(--series-{slot})">{ICONS[kind]}</svg><div><h3>{name}</h3><p class="role">{role}</p></div></div>'
        f'<p class="agent-metric">{metric}</p><p class="agent-detail">{detail}</p></article>'
    )


def team(views: list[BotView], settings: Settings, registry: dict | None) -> str:
    symbols = list(dict.fromkeys(v.symbol for v in views))
    markets = (registry or {}).get("markets") or []
    if markets:
        hot = [f"{esc(m['symbol'].split('/')[0])} {fmt(100 * m['amplitude'], 0)} %" for m in markets[:3]
               if num(m.get("amplitude")) is not None]
        scanner = agent("scanner", 1, "Scanner", "choisit les cryptos agitées et assez échangées",
                        f"{len(markets)} cryptos suivies", "amplitude sur 24 h : " + ", ".join(hot) if hot else "liste fixée à la main")
    else:
        scanner = agent("scanner", 1, "Scanner", "suit les marchés choisis dans les réglages",
                        f"{len(symbols)} marché{'s' if len(symbols) > 1 else ''}", esc(", ".join(symbols[:4])))
    labels = list(dict.fromkeys(v.label for v in views if v.label))
    if labels:
        totals = {lab: sum(v.pnl for v in views if v.label == lab) for lab in labels}
        best = max(totals, key=totals.get)
        dead = len({v.label for v in views if v.eliminated})
        strat = agent("stratege", 2, "Stratèges", "les stratégies retenues par le labo",
                      f"{len(labels)} en course", f"en tête : {esc(best)}" + (f" · {dead} avec des bots éliminés" if dead else ""))
    else:
        strat = agent("stratege", 2, "Stratège", "applique la même règle à chaque bot",
                      esc(settings.strategy.strategy_type.replace("_", " ")), "réglages dans le fichier .env")
    trades = sum(len(v.trades) for v in views)
    execution = agent("execution", 3, "Exécution", "passe les ordres, frais et écart compris",
                      f"{trades} trade{'s' if trades > 1 else ''}",
                      f"{sum(1 for v in views if v.position)} position(s) ouverte(s)")
    blocked = sum(1 for v in views if v.blocked)
    eliminated = sum(1 for v in views if v.eliminated)
    guard = agent("gardien", 4, "Gardien", "coupe les pertes, élimine les stratégies perdantes",
                  f"{fmt(100 * settings.risk.risk_per_trade, 0)} % de risque par trade",
                  f"{eliminated} éliminé(s) · {blocked} bloqué(s)")
    return f'<div class="team">{scanner}{strat}{execution}{guard}</div>'


def positions_table(views: list[BotView]) -> str:
    slots = color_slots(views)
    rows = []
    for v in views:
        pos = v.position
        if not pos:
            continue
        entry, last = num(pos.get("entry_price")), v.last_price
        latent = 100 * (last / entry - 1) if entry and last else None
        since = parse_time(pos.get("entry_time"))
        rows.append(
            "<tr>"
            f"{bot_cell(v, slots)}"
            f"<td class=\"n\">{fmt_price(entry)}</td><td class=\"n\">{fmt_price(last)}</td>"
            f"<td class=\"n\">{delta(latent, 2, ' %') if latent is not None else '—'}</td>"
            f"<td class=\"n\">{fmt_price(num(pos.get('stop')))}</td>"
            f"<td>{local(since) if since else '—'}</td>"
            "</tr>"
        )
    if not rows:
        return '<p class="empty">Aucune position ouverte : les bots attendent un signal.</p>'
    return (
        '<div class="table-wrap"><table><thead><tr><th class="bot-cell">Bot</th><th class="n">Prix d\'entrée</th>'
        '<th class="n">Dernier prix</th><th class="n">Latent</th><th class="n">Stop</th><th>Depuis</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def leaderboard(views: list[BotView], now: datetime, stale_after_s: float) -> str:
    ranked = sorted(views, key=lambda v: (v.started, v.pnl), reverse=True)
    slots = color_slots(views)
    rows = []
    for rank, v in enumerate(ranked, start=1):
        style, icon, label, detail = status(v, now, stale_after_s)
        badges = chip(style, icon, label)
        if not v.eliminated and is_candidate(v.stats, n_tests=len(views)):
            badges += " " + chip("good", "✓", "candidate au testnet")
        if detail:
            badges += f'<p class="why">{esc(detail)}</p>'
        rate = v.win_rate
        rows.append(
            "<tr>"
            f'<td class="n">{rank}</td>{bot_cell(v, slots)}<td class="status">{badges}</td>'
            f'<td class="n">{len(v.trades)}</td>'
            f"<td class=\"n\">{fmt(100 * rate, 0) + ' %' if rate is not None else '—'}</td>"
            f"<td class=\"n\">{fmt_signed(100 * v.stats.mean, 2, ' %') if v.stats.n else '—'}</td>"
            f"<td class=\"n\">{delta(v.pnl) + ' (' + fmt_signed(v.pnl_pct, 2, ' %') + ')' if v.started else '—'}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th class="n">#</th><th class="bot-cell">Bot</th><th>Statut</th>'
        '<th class="n">Trades</th><th class="n">Réussite</th><th class="n">Espérance / trade</th>'
        f"<th class=\"n\">Résultat</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def strategy_table(views: list[BotView]) -> str:
    groups: dict[str, list[BotView]] = {}
    for v in views:
        groups.setdefault(v.label, []).append(v)
    rows = []
    for label, members in sorted(groups.items(), key=lambda kv: -sum(v.pnl for v in kv[1])):
        stats = TradeStats()
        for v in members:
            for t in v.trades:
                if t["pct"] is not None:
                    stats.add(t["pct"] / 100)
        started = [v for v in members if v.started]
        initial = sum(v.initial for v in started)
        pnl = sum(v.pnl for v in started)
        trades = [t for v in members for t in v.trades]
        wins = sum(t["pnl"] > 0 for t in trades)
        # Trades de toutes les cryptos réunis, comme dans le labo : 30 trades arrivent bien plus vite.
        badge = " " + chip("good", "✓", "candidate au testnet") if is_candidate(stats, n_tests=len(groups)) else ""
        rows.append(
            "<tr>"
            f"<td>{esc(label)}{badge}</td><td class=\"n\">{len(members)}</td><td class=\"n\">{len(trades)}</td>"
            f"<td class=\"n\">{fmt(100 * wins / len(trades), 0) + ' %' if trades else '—'}</td>"
            f"<td class=\"n\">{fmt_signed(100 * stats.mean, 2, ' %') if stats.n else '—'}</td>"
            f"<td class=\"n\">{delta(pnl) + ' (' + fmt_signed(100 * pnl / initial, 2, ' %') + ')' if initial else '—'}</td>"
            f"<td class=\"n\">{sum(1 for v in members if v.eliminated)} / {len(members)}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Stratégie</th><th class="n">Bots</th><th class="n">Trades</th>'
        '<th class="n">Réussite</th><th class="n">Espérance / trade</th><th class="n">Résultat</th>'
        f"<th class=\"n\">Éliminés</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def feed(views: list[BotView]) -> str:
    events = []
    for v in views:
        for t in v.trades:
            if t["entree"]:
                events.append((t["entree"], v, "buy", "ACHAT", f"à {fmt_price(t['prix_entree'])}"))
            events.append((t["sortie"], v, "sell", "VENTE", f"{esc(t['raison'])} · {delta(t['pnl'])}"))
        pos = v.position
        if pos and (when := parse_time(pos.get("entry_time"))):
            events.append((when, v, "buy", "ACHAT", f"à {fmt_price(num(pos.get('entry_price')))} · stop "
                                                    f"{fmt_price(num(pos.get('stop')))}"))
    if not events:
        return '<p class="empty">Aucun trade pour l\'instant : chaque achat et chaque vente s\'afficheront ici.</p>'
    events.sort(key=lambda e: e[0], reverse=True)
    items = "".join(
        f'<li><time>{local(when)}</time><span class="tag tag-{kind}">{word}</span>'
        f'<span class="who">{esc(v.name)}</span><span class="what">{what}</span></li>'
        for when, v, kind, word, what in events[:MAX_EVENTS]
    )
    return f'<ol class="feed">{items}</ol>'


def robustness_section(results: dict | None) -> str:
    if not results or not results.get("rows"):
        return '<p class="empty">Lance le test de robustesse pour voir ici quels marchés tiennent.</p>'
    when = parse_time(results.get("date"))
    meta = f"Test du {local(when, '%d/%m/%Y à %H:%M')}" if when else "Dernier test"
    rows = []
    for r in results["rows"]:
        judged = [p for p in r.get("period_means", []) if num(p) is not None]
        periods = f"{sum(p > 0 for p in judged)}/{len(judged)}" if judged else "—"
        low, high, exp, win = num(r.get("ci_low")), num(r.get("ci_high")), num(r.get("expectancy_pct")), num(r.get("win_rate"))
        ci = f"{fmt_signed(low, 3)} à {fmt_signed(high, 3)} %" if low is not None and high is not None else "—"
        style, icon = VERDICT_STYLE.get(r.get("verdict"), ("muted", "○"))
        rows.append(
            "<tr>"
            f"<td>{esc(r.get('market', ''))}</td>"
            f"<td class=\"n\">{int(num(r.get('nb_trades'), 0))}</td>"
            f"<td class=\"n\">{fmt(100 * win, 1) + ' %' if win is not None else '—'}</td>"
            f"<td class=\"n\">{fmt_signed(exp, 3, ' %') if exp is not None else '—'}</td>"
            f"<td class=\"n\">{ci}</td>"
            f"<td class=\"n\">{periods}</td>"
            f"<td>{chip(style, icon, r.get('verdict', ''))}</td>"
            "</tr>"
        )
    verdict = esc(results.get("verdict", "")).replace("\n", "<br>")
    return (
        f'<p class="meta">{esc(meta)} · {esc(results.get("jours", "?"))} jours d\'historique · ordres {esc(results.get("ordres", "?"))}</p>'
        f'<p class="verdict">{verdict}</p>'
        '<div class="table-wrap"><table><thead><tr><th>Marché</th><th class="n">Trades</th><th class="n">Réussite</th>'
        '<th class="n">Espérance</th><th class="n">IC 95 %</th><th class="n">Périodes +</th><th>Verdict</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def timeframe_label(tf: str) -> str:
    unit = {"m": "min", "h": "h", "d": "jour", "w": "semaine"}.get(tf[-1:], tf[-1:])
    return f"{tf[:-1]} {unit}"


def cost_chart(rows: list[dict]) -> str:
    """Par unité de temps : la meilleure variante avant frais, face au coût d'un aller-retour (ligne verticale).
    Une barre qui ne dépasse pas la ligne perd après frais."""
    best: dict[str, tuple[float, float, str]] = {}
    costs = []
    for r in rows:
        gross, net = num(r.get("gross_expectancy_pct")), num(r.get("expectancy_pct"))
        if num(r.get("trades"), 0) < MIN_TRADES or gross is None or net is None:
            continue
        costs.append(gross - net)
        tf = str(r.get("timeframe", ""))
        if tf not in best or gross > best[tf][0]:
            best[tf] = (gross, net, str(r.get("variant", "")))
    if not best:
        return ""
    try:
        order = sorted(best, key=timeframe_to_ms)
    except Exception:  # unité inattendue (fichier d'une autre version) : ordre du fichier
        order = list(best)
    cost = sorted(costs)[len(costs) // 2]
    values = [best[tf][0] for tf in order]
    top = max(cost, *values)
    ticks = nice_ticks(min(0.0, *values), top * 1.1 if top > 0 else 0.1)
    lo, hi = ticks[0], ticks[-1]
    w, ml, mr, mt, row = 960, 250, 96, 44, 50
    h = mt + row * len(order) + 34
    decimals = tick_decimals(ticks[1] - ticks[0])

    def x(v: float) -> float:
        return ml + (v - lo) / (hi - lo) * (w - ml - mr)

    parts = []
    for t in ticks:
        cls = "zero" if abs(t) < 1e-12 else "grid"
        parts.append(f'<line class="{cls}" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{mt - 8}" y2="{h - 30}"/>')
        parts.append(f'<text class="tick" x="{x(t):.1f}" y="{h - 10}" text-anchor="middle">'
                     f'{fmt_signed(t, decimals, " %")}</text>')
    for i, tf in enumerate(order):
        gross, net, variant = best[tf]
        cy = mt + row * i + row / 2
        left, right = min(x(0), x(gross)), max(x(0), x(gross))
        r = min(4.0, (right - left) / 2)
        if gross >= 0:  # bout arrondi côté valeur, carré côté zéro
            d = (f"M{left:.1f} {cy - 10:.1f}H{right - r:.1f}Q{right:.1f} {cy - 10:.1f} {right:.1f} {cy - 10 + r:.1f}"
                 f"V{cy + 10 - r:.1f}Q{right:.1f} {cy + 10:.1f} {right - r:.1f} {cy + 10:.1f}H{left:.1f}Z")
        else:
            d = (f"M{right:.1f} {cy - 10:.1f}H{left + r:.1f}Q{left:.1f} {cy - 10:.1f} {left:.1f} {cy - 10 + r:.1f}"
                 f"V{cy + 10 - r:.1f}Q{left:.1f} {cy + 10:.1f} {left + r:.1f} {cy + 10:.1f}H{right:.1f}Z")
        parts.append(f'<path class="bar" d="{d}"/>')
        tip_x, anchor = (right + 6, "start") if gross >= 0 else (left - 6, "end")
        parts.append(f'<text class="bar-value" x="{tip_x:.1f}" y="{cy + 4:.1f}" text-anchor="{anchor}">'
                     f'{fmt_signed(gross, 2, " %")}</text>')
        parts.append(f'<text class="row-label" x="{ml - 14}" y="{cy - 3:.1f}" text-anchor="end">'
                     f'{esc(timeframe_label(tf))}</text>')
        parts.append(f'<text class="row-sub" x="{ml - 14}" y="{cy + 13:.1f}" text-anchor="end">'
                     f'{esc(short(variant, 34))}</text>')
        detail = (f"{timeframe_label(tf)} · {variant}|avant frais {fmt_signed(gross, 3, ' %')}|"
                  f"après frais {fmt_signed(net, 3, ' %')}|aller-retour {fmt(gross - net, 3)} %")
        parts.append(f'<rect class="bar-hit" x="{ml}" y="{cy - row / 2:.1f}" width="{w - ml - mr}" height="{row}" '
                     f'tabindex="0" data-tip="{esc(detail)}"><title>{esc(detail.replace("|", " · "))}</title></rect>')
    xc = x(cost)
    parts.append(f'<line class="cost" x1="{xc:.1f}" x2="{xc:.1f}" y1="{mt - 10}" y2="{h - 30}"/>')
    parts.append(f'<text class="cost-label" x="{xc:.1f}" y="{mt - 18}" text-anchor="middle">'
                 f"coût d'un aller-retour : {fmt(cost, 2)} %</text>")
    return (
        '<h3 class="chart-title">Ce que la meilleure stratégie capte avant frais, par unité de temps</h3>'
        "<p class=\"note\">Pour gagner après frais, une barre doit dépasser la ligne du coût d'un aller-retour.</p>"
        f'<div class="chart-box"><svg id="cost-chart" viewBox="0 0 {w} {h}" role="img" '
        "aria-label=\"Meilleur gain avant frais par unité de temps, comparé au coût d'un aller-retour\">"
        f'{"".join(parts)}</svg><div id="cost-tip" class="tip" hidden></div></div>'
    )


def lab_section(results: dict | None) -> str:
    if not results or not results.get("rows"):
        return '<p class="empty">Lance le laboratoire pour comparer les stratégies sur plusieurs marchés.</p>'
    when = parse_time(results.get("date"))
    meta = f"Test du {local(when, '%d/%m/%Y à %H:%M')}" if when else "Dernier test"
    markets = ", ".join(results.get("marches", []))
    rows = []
    for r in results["rows"]:
        low, high = num(r.get("ci_low")), num(r.get("ci_high"))
        exp, win, gross = num(r.get("expectancy_pct")), num(r.get("win_rate")), num(r.get("gross_expectancy_pct"))
        test = num(r.get("test_expectancy_pct")) if num(r.get("test_trades"), 0) else None
        ret, bh = num(r.get("strategy_return")), num(r.get("buy_hold_return"))
        judged, positive = int(num(r.get("markets_judged"), 0)), int(num(r.get("markets_positive"), 0))
        ci = f"{fmt_signed(low, 3)} à {fmt_signed(high, 3)} %" if low is not None and high is not None else "—"
        markets_label = f"{positive}/{judged}" if judged else "—"
        style, icon = VERDICT_STYLE.get(r.get("verdict"), ("muted", "○"))
        rows.append(
            "<tr>"
            f"<td>{esc(r.get('variant', ''))}</td>"
            f"<td>{esc(r.get('timeframe', ''))}</td>"
            f"<td class=\"n\">{int(num(r.get('trades'), 0))}</td>"
            f"<td class=\"n\">{fmt(100 * win, 1) + ' %' if win is not None else '—'}</td>"
            f"<td class=\"n\">{fmt_signed(gross, 3, ' %') if gross is not None else '—'}</td>"
            f"<td class=\"n\">{fmt_signed(exp, 3, ' %') if exp is not None else '—'}</td>"
            f"<td class=\"n\">{ci}</td>"
            f"<td class=\"n\">{fmt_signed(test, 3, ' %') if test is not None else '—'}</td>"
            f"<td class=\"n\">{markets_label}</td>"
            f"<td class=\"n\">{fmt_signed(100 * ret, 1, ' %') if ret is not None else '—'}</td>"
            f"<td class=\"n\">{fmt_signed(100 * bh, 1, ' %') if bh is not None else '—'}</td>"
            f"<td>{chip(style, icon, r.get('verdict', ''))}</td>"
            "</tr>"
        )
    verdict = esc(results.get("verdict", "")).replace("\n", "<br>")
    return (
        f'<p class="meta">{esc(meta)} · marchés : {esc(markets)} · validation de 50 à 80 % de chaque historique, test final sur les 20 % les plus récents</p>'
        f'<p class="verdict">{verdict}</p>{cost_chart(results["rows"])}'
        '<div class="table-wrap"><table><thead><tr><th>Variante</th><th>Unité</th><th class="n">Trades</th>'
        '<th class="n">Réussite</th><th class="n">Avant frais</th><th class="n">Espérance</th><th class="n">IC 95 %</th>'
        '<th class="n">Test final</th><th class="n">Marchés +</th>'
        '<th class="n">Rendement</th><th class="n">Buy &amp; hold</th><th>Verdict</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render(views: list[BotView], settings: Settings, robustness: dict | None, now: datetime,
           lab: dict | None = None, registry: dict | None = None) -> str:
    tournament = registry is not None
    quotes = {v.symbol.split("/")[-1] for v in views}
    quote = quotes.pop() if len(quotes) == 1 else ""
    mode = MODE_LABELS.get(settings.mode, settings.mode)
    title = "Tournoi en argent fictif" if tournament else "Tableau de bord"
    started = parse_time((registry or {}).get("started"))
    running = f" · en course depuis {duration((now - started).total_seconds())}" if started else ""
    banner = (
        '<p class="banner">Argent réel : chaque trade engage ton argent. Vérifie que les stops sont surveillés '
        "(statut des bots ci-dessous).</p>"
        if settings.mode == "live" else ""
    )
    stale_after_s = max(STALE_AFTER_S, 3 * settings.poll_seconds)  # trois tours manqués
    labelled = any(v.label for v in views)
    sections = [
        ("", kpis(views, quote)),
        ("L'équipe", team(views, settings, registry)),
        ("Positions ouvertes", positions_table(views)),
        ("Classement", leaderboard(views, now, stale_after_s)),
    ]
    if labelled:
        sections.append(("Par stratégie", strategy_table(views)))
    sections += [
        ("Rendement cumulé par stratégie" if labelled else "Rendement cumulé depuis le départ",
         chart(strategy_series(views) if labelled else bot_series(views))),
        ("Journal en direct", feed(views)),
    ]
    if not tournament:
        sections += [("Laboratoire de stratégies", lab_section(lab)),
                     ("Dernier test de robustesse", robustness_section(robustness))]
    body = "".join(f"<section>{f'<h2>{name}</h2>' if name else ''}{content}</section>" for name, content in sections)
    return (
        '<!doctype html><html lang="fr" data-theme="dark"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="refresh" content="60"><title>{title}</title>'
        "<script>try { const t = localStorage.getItem('theme'); if (t) document.documentElement.dataset.theme = t; }"
        " catch (e) {}</script>"
        f"<style>{CSS}</style></head><body><main>"
        f'<header class="topbar"><div><p class="brand">Trading bot <span class="badge">{esc(mode)}</span></p>'
        f'<h1>{title}</h1><p class="meta">{esc(settings.exchange)} · 24 h/24{running} · mis à jour le '
        f"{local(now, '%d/%m/%Y à %H:%M')} · la page se recharge chaque minute</p></div>"
        '<button id="theme-toggle" class="theme" type="button">Clair / sombre</button></header>'
        f"{banner}{body}"
        '<footer><p class="note">Les performances passées ne garantissent rien. Un bot arrêté ne surveille plus '
        "ses stops : garde un œil sur le statut de chaque bot.</p></footer>"
        f"</main><script>{JS}</script></body></html>"
    )


def write_dashboard(settings: Settings, now: datetime | None = None, bots: list[Settings] | None = None,
                    registry: dict | None = None) -> Path:
    """`bots` et `registry` : ceux du tournoi ; sinon les bots de BOTS, avec labo et robustesse."""
    now = now or datetime.now(timezone.utc)
    tournament = registry is not None
    page = render(
        load_views(settings, now, bots), settings,
        None if tournament else load_results(settings.data_dir / ROBUSTNESS_FILE), now,
        None if tournament else load_lab(settings.data_dir / LAB_FILE), registry,
    )
    path = settings.data_dir / FILENAME
    atomic_write(path, page)
    return path


CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e;
  --muted: #898781; --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11, 11, 11, 0.10);
  --up: #006300; --down: #d03b3b; --good: #0ca30c; --warning: #fab219; --critical: #d03b3b;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100;
  --series-5: #e87ba4; --series-6: #008300; --series-7: #6250d6; --series-8: #e34948;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
    --muted: #898781; --grid: #2c2c2a; --axis: #383835; --border: rgba(255, 255, 255, 0.10);
    --up: #0ca30c; --down: #d03b3b;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
    --series-5: #d55181; --series-6: #008300; --series-7: #9085e9; --series-8: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
  --muted: #898781; --grid: #2c2c2a; --axis: #383835; --border: rgba(255, 255, 255, 0.10);
  --up: #0ca30c; --down: #d03b3b;
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
  --series-5: #d55181; --series-6: #008300; --series-7: #9085e9; --series-8: #e66767;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1120px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 28px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 0 0 12px; }
section { margin-top: 32px; }
.meta, .note, .empty { color: var(--text-secondary); margin: 0; }
.note { font-size: 13px; margin-top: 8px; }
.banner { margin-top: 16px; padding: 12px 16px; border-radius: 8px; border: 2px solid var(--critical);
  font-weight: 600; }
.topbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.brand { margin: 0 0 4px; font-weight: 600; letter-spacing: 0.02em; color: var(--text-secondary); }
.badge { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 999px; font-size: 12px;
  border: 1px solid var(--series-1); color: var(--text-primary); text-transform: uppercase; }
.theme { background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--border);
  border-radius: 999px; padding: 6px 14px; font: inherit; font-size: 13px; cursor: pointer; }
.kpis { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.tile-hero { grid-column: span 2; }
@media (max-width: 1000px) {
  .kpis { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .tile-hero { grid-column: span 4; }
}
@media (max-width: 600px) {
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tile-hero { grid-column: span 2; }
}
.tile-label, .tile-sub { margin: 0; color: var(--text-secondary); font-size: 13px; }
.tile-value { margin: 4px 0; font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums;
  white-space: nowrap; }
.tile-hero .tile-value { font-size: 32px; }
.tile-value .up, .tile-value .down { font-size: 0.6em; vertical-align: 0.2em; }
.team { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 1000px) { .team { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .team { grid-template-columns: minmax(0, 1fr); } }
.agent { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.agent-head { display: flex; gap: 12px; align-items: center; }
.agent-head svg { width: 28px; height: 28px; flex: none; fill: none; stroke: currentColor; stroke-width: 2;
  stroke-linecap: round; stroke-linejoin: round; }
.agent h3 { margin: 0; font-size: 15px; }
.role, .agent-detail { margin: 0; color: var(--text-secondary); font-size: 13px; }
.agent-metric { margin: 12px 0 2px; font-weight: 600; font-variant-numeric: tabular-nums; }
.feed { list-style: none; margin: 0; padding: 0; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 12px; }
.feed li { display: grid; grid-template-columns: 96px 64px minmax(0, 1.2fr) minmax(0, 1fr); gap: 12px;
  padding: 8px 14px; border-bottom: 1px solid var(--grid); font-size: 14px; align-items: baseline; }
.feed li:last-child { border-bottom: 0; }
.feed time { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.tag { font-size: 12px; font-weight: 600; letter-spacing: 0.04em; }
.tag-buy { color: var(--series-1); }
.tag-sell { color: var(--series-2); }
.who { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.what { color: var(--text-secondary); }
@media (max-width: 600px) {
  .feed li { grid-template-columns: 80px 56px 1fr; }
  .feed .what { grid-column: 2 / -1; }
}
.chip { display: inline-flex; gap: 6px; align-items: baseline; padding: 2px 10px; border-radius: 999px;
  border: 1px solid var(--border); font-size: 13px; color: var(--text-primary); white-space: nowrap; }
td.status { white-space: normal; min-width: 200px; }
.why { margin: 4px 0 0; max-width: 300px; color: var(--text-secondary); font-size: 12px; }
.chip-good > span { color: var(--good); }
.chip-warning { border-color: var(--warning); }
.chip-warning > span { color: var(--warning); }
.chip-critical { border-color: var(--critical); }
.chip-critical > span { color: var(--critical); }
.chip-muted { color: var(--text-secondary); }
.up { color: var(--up); }
.down { color: var(--down); }
.line-key { display: inline-block; width: 16px; height: 2px; border-radius: 1px; vertical-align: middle; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 20px; list-style: none; padding: 0; margin: 0 0 8px;
  color: var(--text-secondary); font-size: 13px; }
.legend li { display: flex; align-items: center; gap: 6px; }
.chart-box { position: relative; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 12px; padding: 8px; overflow-x: auto; }
.chart-box svg { display: block; width: 100%; min-width: 760px; height: auto; font-size: 13px; outline-offset: 4px; }
.grid { stroke: var(--grid); stroke-width: 1; }
.zero { stroke: var(--axis); stroke-width: 1; }
.tick { fill: var(--muted); font-variant-numeric: tabular-nums; }
.line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.end { stroke: var(--surface-1); stroke-width: 2; }
.leader { stroke: var(--axis); stroke-width: 1; }
.end-label { fill: var(--text-primary); font-size: 13px; }
.end-value { fill: var(--text-secondary); }
.crosshair { stroke: var(--axis); stroke-width: 1; visibility: hidden; }
.hit { fill: transparent; cursor: crosshair; }
.chart-title { font-size: 15px; margin: 20px 0 2px; }
.chart-box + .table-wrap { margin-top: 16px; }
.bar { fill: var(--series-1); }
.bar-value, .row-label { fill: var(--text-primary); font-variant-numeric: tabular-nums; }
.row-sub { fill: var(--text-secondary); font-size: 12px; }
.cost { stroke: var(--text-secondary); stroke-width: 2; }
.cost-label { fill: var(--text-secondary); font-size: 12px; }
.bar-hit { fill: transparent; outline: none; }
.bar-hit:focus-visible { stroke: var(--text-primary); stroke-width: 1; }
.tip { position: absolute; min-width: 160px; padding: 8px 10px; border-radius: 8px; pointer-events: none;
  background: var(--surface-1); border: 1px solid var(--border); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  font-size: 13px; }
.tip-date { color: var(--text-secondary); margin-bottom: 4px; }
.tip-row { display: flex; align-items: center; gap: 8px; }
.tip-row strong { font-variant-numeric: tabular-nums; }
.tip-row span:last-child { color: var(--text-secondary); }
.tip-key { display: inline-block; width: 12px; height: 2px; }
.table-wrap { overflow-x: auto; background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--grid); white-space: nowrap; }
th { color: var(--text-secondary); font-weight: 600; }
tr:last-child td { border-bottom: 0; }
.n { text-align: right; font-variant-numeric: tabular-nums; }
.bot { display: flex; align-items: flex-start; gap: 8px; }
.bot .line-key { flex: none; margin-top: 0.7em; }
.pair { white-space: nowrap; }
@media (max-width: 1000px) {  /* tablette et téléphone : le nom du bot reste visible quand on fait défiler */
  .bot-cell { position: sticky; left: 0; z-index: 1; background: var(--surface-1); white-space: normal;
    min-width: 150px; }
  .strat { display: block; color: var(--text-secondary); font-size: 12px; }
  .strat .sep { display: none; }
}
.verdict { font-weight: 600; margin: 8px 0 12px; }
footer { margin-top: 40px; }
"""

JS = """
(() => {
  const svg = document.getElementById('equity-chart');
  const dataEl = document.getElementById('chart-data');
  if (!svg || !dataEl) return;
  const data = JSON.parse(dataEl.textContent);
  const tip = document.getElementById('chart-tip');
  const cross = document.getElementById('crosshair');
  const times = [...new Set(data.series.flatMap(s => s.points.map(p => p[0])))].sort((a, b) => a - b);
  const plotW = data.w - data.ml - data.mr;
  const xOf = t => data.ml + (t - data.t0) / (data.t1 - data.t0) * plotW;
  const valueAt = (points, t) => { let v = null; for (const [ti, vi] of points) { if (ti <= t) v = vi; else break; } return v; };
  const pct = v => (v > 0 ? '+' : v < 0 ? '\\u2212' : '') + Math.abs(v).toFixed(2).replace('.', ',') + ' %';
  const when = t => new Date(t).toLocaleString('fr-FR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
  let index = times.length - 1;
  function show(i) {
    index = Math.max(0, Math.min(times.length - 1, i));
    const t = times[index], x = xOf(t);
    cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.style.visibility = 'visible';
    tip.replaceChildren();
    const head = document.createElement('div'); head.className = 'tip-date'; head.textContent = when(t); tip.append(head);
    for (const s of data.series) {
      const v = valueAt(s.points, t);
      if (v === null) continue;
      const row = document.createElement('div'); row.className = 'tip-row';
      const key = document.createElement('span'); key.className = 'tip-key'; key.style.background = 'var(--series-' + s.slot + ')';
      const value = document.createElement('strong'); value.textContent = pct(v);
      const name = document.createElement('span'); name.textContent = s.name;
      row.append(key, value, name); tip.append(row);
    }
    const box = svg.getBoundingClientRect(), host = svg.parentElement.getBoundingClientRect();
    const left = box.left - host.left + x / data.w * box.width;
    tip.hidden = false;
    const flip = left + tip.offsetWidth + 16 > host.width;
    tip.style.left = (flip ? left - tip.offsetWidth - 12 : left + 12) + 'px';
    tip.style.top = (box.top - host.top + 8) + 'px';
  }
  function hide() { cross.style.visibility = 'hidden'; tip.hidden = true; }
  function nearest(clientX) {
    const box = svg.getBoundingClientRect();
    const t = data.t0 + ((clientX - box.left) / box.width * data.w - data.ml) / plotW * (data.t1 - data.t0);
    let best = 0;
    for (let i = 1; i < times.length; i++) if (Math.abs(times[i] - t) < Math.abs(times[best] - t)) best = i;
    return best;
  }
  svg.addEventListener('pointermove', e => show(nearest(e.clientX)));
  svg.addEventListener('pointerleave', hide);
  svg.addEventListener('focus', () => show(index));
  svg.addEventListener('blur', hide);
  svg.addEventListener('keydown', e => {
    if (e.key === 'ArrowLeft') { show(index - 1); e.preventDefault(); }
    if (e.key === 'ArrowRight') { show(index + 1); e.preventDefault(); }
  });
})();
(() => {
  const tip = document.getElementById('cost-tip');
  const svg = document.getElementById('cost-chart');
  if (!tip || !svg) return;
  const host = svg.parentElement;
  function show(hit) {
    tip.replaceChildren();
    hit.dataset.tip.split('|').forEach((line, i) => {
      const row = document.createElement('div');
      row.className = i ? 'tip-row' : 'tip-date';
      row.textContent = line;
      tip.append(row);
    });
    const box = hit.getBoundingClientRect(), frame = host.getBoundingClientRect();
    tip.hidden = false;
    // À droite du graphique, à hauteur de la ligne : la bulle ne cache pas les autres barres.
    tip.style.left = host.scrollLeft + Math.max(8, frame.width - tip.offsetWidth - 12) + 'px';  // cadre qui défile
    tip.style.top = Math.max(4, box.top - frame.top + (box.height - tip.offsetHeight) / 2) + 'px';
  }
  function hide() { tip.hidden = true; }
  svg.querySelectorAll('.bar-hit').forEach(hit => {
    hit.addEventListener('pointerenter', () => show(hit));
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('focus', () => show(hit));
    hit.addEventListener('blur', hide);
  });
})();
(() => {
  const button = document.getElementById('theme-toggle');
  if (!button) return;
  button.addEventListener('click', () => {
    const root = document.documentElement;
    const next = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch (e) {}
  });
})();
"""
