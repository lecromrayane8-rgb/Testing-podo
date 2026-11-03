"""Tableau de bord : une page HTML autonome qui résume tous les bots.

Réécrite dans data/tableau-de-bord.html à chaque tour de la boucle (et par `python main.py tableau`),
elle se recharge toute seule chaque minute. Aucune ressource externe : elle s'ouvre hors ligne.
"""
from __future__ import annotations

import csv
import html
import json
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .broker import atomic_write
from .config import Settings
from .lab import LAB_FILE, PROMISING, load_lab
from .live import bot_paths
from .risk import RiskGuard
from .robustness import ROBUST, load_results

FILENAME = "tableau-de-bord.html"
ROBUSTNESS_FILE = "robustesse.json"
STALE_AFTER_S = 10 * 60
MAX_SERIES = 8  # couleurs de la palette ; au-delà, un bot reste dans les cartes et le tableau
MAX_TRADES = 30
W, H, ML, MR, MT, MB = 960, 320, 64, 176, 16, 36

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
    slot: int
    initial: float | None
    equity: float | None
    trades: list[dict]
    position: dict | None
    order: dict | None
    blocked: str | None
    updated_at: datetime | None

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


def load_views(settings: Settings, now: datetime | None = None) -> list[BotView]:
    now = now or datetime.now(timezone.utc)
    views = []
    for slot, (symbol, timeframe) in enumerate(settings.markets, start=1):
        state_path, journal_path = bot_paths(replace(settings, symbol=symbol, timeframe=timeframe))
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            state = {}
        trades = read_trades(journal_path)
        capital = num(state.get("capital"))
        initial = num(state.get("initial_capital"))
        if initial is None and capital is not None:
            initial = capital - sum(t["pnl"] for t in trades)
        guard = RiskGuard.from_dict(settings.risk, state.get("guard")) if state.get("guard") else None
        equity = num(state.get("equity"), capital)
        if guard and equity is not None:
            # Copie locale (rien n'est sauvegardé) : la limite journalière d'un jour passé expire, comme dans le bot.
            guard.update(equity, now.astimezone(timezone.utc).strftime("%Y-%m-%d"))
        views.append(BotView(
            name=f"{symbol} {timeframe}",
            slot=slot,
            initial=initial,
            equity=equity,
            trades=trades,
            position=state.get("position"),
            order=state.get("order"),
            blocked=guard.blocked_reason() if guard else None,
            updated_at=parse_time(state.get("updated_at")),
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
    if x is None:
        return "—"
    return fmt(x, 2 if x >= 1 else 6)


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


def status(view: BotView, now: datetime, stale_after_s: float = STALE_AFTER_S) -> tuple[str, str, str]:
    """(style, icône, libellé) de l'état d'un bot."""
    if not view.started:
        return "muted", "○", "Pas encore lancé"
    if view.updated_at and (now - view.updated_at).total_seconds() > stale_after_s:
        return "critical", "✕", f"Arrêté ? Aucune nouvelle depuis {duration((now - view.updated_at).total_seconds())}"
    if view.blocked:
        return "warning", "!", f"Achats bloqués : {view.blocked}"
    if view.order:
        side = "d'achat" if view.order.get("side") == "buy" else "de vente"
        return "neutral", "●", f"Ordre limite {side} en attente"
    if view.position:
        return "neutral", "●", "En position"
    return "neutral", "○", "En attente d'un signal"


def chip(style: str, icon: str, label: str) -> str:
    return f'<span class="chip chip-{style}"><span aria-hidden="true">{icon}</span> {esc(label)}</span>'


# --- graphique ---------------------------------------------------------------------------
def points(view: BotView) -> list[tuple[float, float]]:
    """Rendement cumulé (%) : 0 au départ, puis après chaque trade clôturé, puis la valeur actuelle."""
    if not view.started:
        return []
    first = view.trades[0] if view.trades else None
    start = (first["entree"] or first["sortie"]) if first else view.updated_at
    if start is None:
        return []
    pts = [(start.timestamp() * 1000, 0.0)]
    realized = 0.0
    for trade in view.trades:
        realized += trade["pnl"]
        pts.append((trade["sortie"].timestamp() * 1000, 100 * realized / view.initial))
    if view.updated_at and view.updated_at.timestamp() * 1000 >= pts[-1][0]:
        pts.append((view.updated_at.timestamp() * 1000, view.pnl_pct))
    return pts


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    raw = (hi - lo) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    first, last = math.floor(lo / step) * step, math.ceil(hi / step) * step
    return [first + i * step for i in range(int(round((last - first) / step)) + 1)]


def chart(views: list[BotView]) -> str:
    series = [(v, pts) for v in views[:MAX_SERIES] if len(pts := points(v)) >= 2]
    if not series:
        return '<p class="empty">La courbe apparaîtra quand un bot aura tourné quelques minutes.</p>'
    times = [t for _, pts in series for t, _ in pts]
    values = [v for _, pts in series for _, v in pts]
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
    for view, pts in series:
        d = f"M{x_of(pts[0][0]):.1f} {y_of(pts[0][1]):.1f}" + "".join(
            f"H{x_of(t):.1f}V{y_of(v):.1f}" for t, v in pts[1:]
        )
        parts.append(f'<path class="line" style="stroke: var(--series-{view.slot})" d="{d}"/>')
        ends.append((view, x_of(pts[-1][0]), y_of(pts[-1][1]), pts[-1][1]))
    # Étiquettes directes en bout de ligne, écartées d'au moins 16 px, reliées par un trait si déplacées.
    ends.sort(key=lambda e: e[2])
    label_y = []
    for _, _, y, _ in ends:
        label_y.append(max(y, label_y[-1] + 16) if label_y else max(y, MT + 8))
    overflow = label_y[-1] - (H - MB) if label_y else 0
    if overflow > 0:
        label_y = [y - overflow for y in label_y]
    for (view, x, y, value), ly in zip(ends, label_y):
        lx = W - MR + 14
        if abs(ly - y) > 2 or lx - x > 16:
            parts.append(f'<line class="leader" x1="{x:.1f}" y1="{y:.1f}" x2="{lx - 4}" y2="{ly:.1f}"/>')
        parts.append(f'<circle class="end" style="fill: var(--series-{view.slot})" cx="{x:.1f}" cy="{y:.1f}" r="4"/>')
        parts.append(
            f'<text class="end-label" x="{lx}" y="{ly + 4:.1f}">{esc(view.name)} '
            f'<tspan class="end-value">{fmt_signed(value, 2, " %")}</tspan></text>'
        )
    parts.append(f'<line id="crosshair" class="crosshair" x1="0" x2="0" y1="{MT}" y2="{H - MB}"/>')
    parts.append(f'<rect class="hit" x="{ML}" y="{MT}" width="{W - ML - MR}" height="{H - MT - MB}"/>')

    data = {
        "w": W, "ml": ML, "mr": MR, "t0": t0, "t1": t1,
        "series": [{"name": v.name, "slot": v.slot, "points": pts} for v, pts in series],
    }
    payload = json.dumps(data).replace("</", "<\\/")
    legend = "".join(
        f'<li><span class="line-key" style="background: var(--series-{v.slot})"></span>{esc(v.name)}</li>'
        for v, _ in series
    )
    return (
        f'<ul class="legend">{legend}</ul>'
        f'<div class="chart-box"><svg id="equity-chart" viewBox="0 0 {W} {H}" role="img" tabindex="0" '
        f'aria-label="Rendement cumulé de chaque bot depuis son départ, en pourcentage">{"".join(parts)}</svg>'
        f'<div id="chart-tip" class="tip" hidden></div></div>'
        f'<script type="application/json" id="chart-data">{payload}</script>'
    )


# --- sections ------------------------------------------------------------------------------
def bot_card(view: BotView, quote: str, now: datetime, stale_after_s: float) -> str:
    style, icon, label = status(view, now, stale_after_s)
    stats = []
    if view.started:
        stats.append(("Valeur", f"{fmt(view.equity)} {esc(quote)}"))
        stats.append(("Résultat", f"{delta(view.pnl)} ({fmt_signed(view.pnl_pct, 2, ' %')})"))
        rate = view.win_rate
        stats.append(("Trades", f"{len(view.trades)}" + (f" · {fmt(100 * rate, 0)} % gagnants" if rate is not None else "")))
        pos = view.position
        if pos:
            stats.append(("Position", f"{fmt_qty(num(pos.get('qty')))} à {fmt_price(num(pos.get('entry_price')))}"))
            stats.append(("Stop", fmt_price(num(pos.get("stop")))))
        else:
            stats.append(("Position", "aucune"))
    items = "".join(f"<div><dt>{name}</dt><dd>{value}</dd></div>" for name, value in stats)
    key = f'<span class="line-key" style="background: var(--series-{view.slot})"></span>' if view.slot <= MAX_SERIES else ""
    return (
        f'<article class="card"><h3>{key}{esc(view.name)}</h3>{chip(style, icon, label)}'
        f'<dl class="stats">{items}</dl></article>'
    )


def trades_table(views: list[BotView]) -> str:
    rows = sorted(((v, t) for v in views for t in v.trades), key=lambda vt: vt[1]["sortie"], reverse=True)
    if not rows:
        return '<p class="empty">Aucun trade clôturé pour l\'instant.</p>'
    body = "".join(
        "<tr>"
        f"<td>{local(t['sortie'])}</td>"
        f'<td class="bot"><span class="line-key" style="background: var(--series-{v.slot})"></span>{esc(v.name)}</td>'
        f"<td class=\"n\">{fmt_price(t['prix_entree'])}</td>"
        f"<td class=\"n\">{fmt_price(t['prix_sortie'])}</td>"
        f"<td class=\"n\">{delta(t['pnl'])}</td>"
        f"<td class=\"n\">{fmt_signed(t['pct'], 2, ' %') if t['pct'] is not None else '—'}</td>"
        f"<td>{esc(t['raison'])}</td>"
        "</tr>"
        for v, t in rows[:MAX_TRADES]
    )
    more = f'<p class="note">Les {MAX_TRADES} derniers sur {len(rows)}. Le détail complet est dans les fichiers trades_*.csv.</p>' if len(rows) > MAX_TRADES else ""
    return (
        '<div class="table-wrap"><table><thead><tr><th>Sortie</th><th>Bot</th><th class="n">Prix d\'entrée</th>'
        '<th class="n">Prix de sortie</th><th class="n">Résultat</th><th class="n">%</th><th>Raison</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>{more}"
    )


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


def lab_section(results: dict | None) -> str:
    if not results or not results.get("rows"):
        return '<p class="empty">Lance le laboratoire pour comparer les stratégies sur plusieurs marchés.</p>'
    when = parse_time(results.get("date"))
    meta = f"Test du {local(when, '%d/%m/%Y à %H:%M')}" if when else "Dernier test"
    markets = ", ".join(results.get("marches", []))
    rows = []
    for r in results["rows"]:
        low, high = num(r.get("ci_low")), num(r.get("ci_high"))
        exp, win = num(r.get("expectancy_pct")), num(r.get("win_rate"))
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
            f"<td class=\"n\">{fmt_signed(exp, 3, ' %') if exp is not None else '—'}</td>"
            f"<td class=\"n\">{ci}</td>"
            f"<td class=\"n\">{markets_label}</td>"
            f"<td class=\"n\">{fmt_signed(100 * ret, 1, ' %') if ret is not None else '—'}</td>"
            f"<td class=\"n\">{fmt_signed(100 * bh, 1, ' %') if bh is not None else '—'}</td>"
            f"<td>{chip(style, icon, r.get('verdict', ''))}</td>"
            "</tr>"
        )
    verdict = esc(results.get("verdict", "")).replace("\n", "<br>")
    return (
        f'<p class="meta">{esc(meta)} · marchés : {esc(markets)} · mesuré sur les 40 % les plus récents de chaque historique</p>'
        f'<p class="verdict">{verdict}</p>'
        '<div class="table-wrap"><table><thead><tr><th>Variante</th><th>Unité</th><th class="n">Trades</th>'
        '<th class="n">Réussite</th><th class="n">Espérance</th><th class="n">IC 95 %</th><th class="n">Marchés +</th>'
        '<th class="n">Rendement</th><th class="n">Buy &amp; hold</th><th>Verdict</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render(views: list[BotView], settings: Settings, robustness: dict | None, now: datetime,
           lab: dict | None = None) -> str:
    quotes = {name.split()[0].split("/")[-1] for name in (v.name for v in views)}
    quote = quotes.pop() if len(quotes) == 1 else ""
    started = [v for v in views if v.started]
    total_initial = sum(v.initial for v in started)
    total_equity = sum(v.equity for v in started)
    total_pnl = total_equity - total_initial
    total_pct = 100 * total_pnl / total_initial if total_initial else 0.0
    n_trades = sum(len(v.trades) for v in views)
    mode = MODE_LABELS.get(settings.mode, settings.mode)
    banner = (
        '<p class="banner">Argent réel : chaque trade engage ton argent. Vérifie que les stops sont surveillés '
        "(statut des bots ci-dessous).</p>"
        if settings.mode == "live" else ""
    )
    hero = (
        f'<p class="hero-label">Résultat total</p><p class="hero">{delta(total_pnl)} {esc(quote)}</p>'
        f'<p class="hero-sub">{fmt_signed(total_pct, 2, " %")} · valeur {fmt(total_equity)} {esc(quote)} · '
        f'{len(views)} bot{"s" if len(views) > 1 else ""} · {n_trades} trade{"s" if n_trades > 1 else ""}</p>'
        if started else '<p class="empty">Aucun bot n\'a encore tourné. Lance « 4 - Lancer le bot ».</p>'
    )
    stale_after_s = max(STALE_AFTER_S, 3 * settings.poll_seconds)  # trois tours manqués
    cards = "".join(bot_card(v, quote, now, stale_after_s) for v in views)
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="refresh" content="60"><title>Tableau de bord du bot</title>'
        f"<style>{CSS}</style></head><body><main>"
        f'<header><h1>Tableau de bord</h1><p class="meta">Mode {esc(mode)} · {esc(settings.exchange)} · '
        f"mis à jour le {local(now, '%d/%m/%Y à %H:%M')} · la page se recharge chaque minute</p></header>"
        f"{banner}<section>{hero}</section>"
        f'<section><h2>Les bots</h2><div class="cards">{cards}</div></section>'
        f"<section><h2>Rendement cumulé depuis le départ</h2>{chart(views)}</section>"
        f"<section><h2>Derniers trades</h2>{trades_table(views)}</section>"
        f"<section><h2>Laboratoire de stratégies</h2>{lab_section(lab)}</section>"
        f"<section><h2>Dernier test de robustesse</h2>{robustness_section(robustness)}</section>"
        '<footer><p class="note">Les performances passées ne garantissent rien. Un bot arrêté ne surveille plus '
        "ses stops : garde un œil sur le statut de chaque bot.</p></footer>"
        f"</main><script>{JS}</script></body></html>"
    )


def write_dashboard(settings: Settings, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    path = settings.data_dir / FILENAME
    page = render(
        load_views(settings, now), settings, load_results(settings.data_dir / ROBUSTNESS_FILE), now,
        load_lab(settings.data_dir / LAB_FILE),
    )
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
h3 { font-size: 15px; margin: 0 0 8px; display: flex; align-items: center; gap: 8px; }
section { margin-top: 32px; }
.meta, .note, .hero-label, .hero-sub, .empty { color: var(--text-secondary); margin: 0; }
.note { font-size: 13px; margin-top: 8px; }
.hero { font-size: 48px; font-weight: 600; margin: 0; line-height: 1.15; }
.hero .up, .hero .down { font-size: 0.5em; vertical-align: 0.25em; }
.banner { margin-top: 16px; padding: 12px 16px; border-radius: 8px; border: 2px solid var(--critical);
  font-weight: 600; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; margin: 16px 0 0; }
.stats dt { color: var(--text-secondary); font-size: 13px; }
.stats dd { margin: 0; font-weight: 600; }
.chip { display: inline-flex; gap: 6px; align-items: baseline; padding: 2px 10px; border-radius: 999px;
  border: 1px solid var(--border); font-size: 13px; color: var(--text-primary); }
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
svg { display: block; width: 100%; min-width: 760px; height: auto; font-size: 13px; outline-offset: 4px; }
@media (max-width: 600px) {
  .hero { font-size: 36px; }
}
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
td.bot { display: flex; align-items: center; gap: 8px; }
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
"""
