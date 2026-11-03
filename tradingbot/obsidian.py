"""Journal Obsidian : le bot écrit lui-même ses backtests, ses trades et ses événements.

Un coffre Obsidian est un simple dossier de fichiers Markdown : le bot y écrit directement, sans
connecteur. Les propriétés en tête de note (frontmatter) alimentent le tableau de bord, qui
utilise l'extension communautaire Dataview ; sans elle, les notes restent lisibles.
"""
from __future__ import annotations

import json
import logging
import math
import numbers
import re
from dataclasses import fields
from datetime import datetime
from pathlib import Path

from .robustness import ROBUST, RobustnessRow

ROOT = "Trading bot"
JOURNAL = {"journal": True}  # `extra=` d'un log à recopier dans la note du jour

DASHBOARD = """# Tableau de bord du bot

Le bot écrit ici tout seul : un **journal** par jour, une note par **trade** et par **backtest**,
et les **tests de robustesse**. À toi de compléter les sections « Mes observations ».
Pour une analyse, demande à Claude de lire ce dossier.

> Les tableaux ci-dessous utilisent l'extension communautaire **Dataview** :
> Réglages → Extensions communautaires → Parcourir → « Dataview » → Installer, puis Activer.

## Trades en direct, par mode et unité de temps

```dataview
TABLE WITHOUT ID key AS "Mode · unité", length(rows) AS "Trades",
  round(length(filter(rows.pnl, (p) => p > 0)) / length(rows) * 100, 1) AS "Réussite %",
  round(sum(rows.pnl), 2) AS "PnL total"
FROM "Trading bot/Trades"
GROUP BY mode + " · " + unite
```

## Derniers trades

```dataview
TABLE WITHOUT ID file.link AS "Trade", mode AS "Mode", paire AS "Paire", unite AS "Unité",
  raison AS "Sortie", round(pnl, 2) AS "PnL", round(rendement_pct, 2) AS "%"
FROM "Trading bot/Trades"
SORT sortie DESC
LIMIT 30
```

## Backtests

```dataview
TABLE WITHOUT ID file.link AS "Backtest", paire AS "Paire", unite AS "Unité", ordres AS "Ordres",
  trades AS "Trades", round(taux_reussite * 100, 1) AS "Réussite %",
  round(esperance_pct, 3) AS "Espérance %", round(rendement * 100, 1) AS "Rendement %"
FROM "Trading bot/Backtests"
SORT date DESC
```

## Tests de robustesse

```dataview
TABLE WITHOUT ID file.link AS "Test", marches_testes AS "Marchés testés", robustes AS "Robustes",
  marches_robustes AS "Lesquels"
FROM "Trading bot/Robustesse"
SORT date DESC
```

## Journal

```dataview
LIST FROM "Trading bot/Journal" SORT file.name DESC LIMIT 14
```
"""


def yaml_value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        x = float(value)
        if math.isnan(x):
            return "null"
        if math.isinf(x):
            return ".inf" if x > 0 else "-.inf"
        return repr(round(x, 8))
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(yaml_value(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)  # chaîne entre guillemets : YAML valide


def frontmatter(values: dict) -> str:
    return "\n".join(["---", *(f"{k}: {yaml_value(v)}" for k, v in values.items()), "---", ""])


def safe_name(name: str) -> str:
    """Nom de note valide pour Obsidian (pas de / : # ^ [ ] | etc.)."""
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "-", name).strip()


def settings_list(settings) -> str:
    lines = []
    for group in (settings.strategy, settings.risk, settings.execution):
        lines += [f"- `{f.name.upper()}` = {getattr(group, f.name)}" for f in fields(group)]
    return "\n".join(lines)


class ObsidianJournal:
    def __init__(self, vault: Path, clock=None):
        self.root = Path(vault).expanduser() / ROOT
        self.clock = clock or (lambda: datetime.now().astimezone())
        dashboard = self.root / "Tableau de bord.md"
        if not dashboard.exists():  # jamais écrasé : l'utilisateur peut le modifier
            dashboard.parent.mkdir(parents=True, exist_ok=True)
            dashboard.write_text(DASHBOARD, encoding="utf-8")

    def _new_note(self, folder: str, name: str, content: str) -> Path:
        directory = self.root / folder
        directory.mkdir(parents=True, exist_ok=True)
        base = safe_name(name)
        path = directory / f"{base}.md"
        n = 2
        while path.exists():
            path = directory / f"{base} ({n}).md"
            n += 1
        path.write_text(content, encoding="utf-8")
        return path

    def backtest(self, settings, metrics: dict, report: str, comparison: str) -> Path:
        now = self.clock()
        values = {
            "type": "backtest",
            "date": now.isoformat(timespec="seconds"),
            "plateforme": settings.exchange,
            "paire": settings.symbol,
            "unite": settings.timeframe,
            "ordres": metrics.get("type_ordres"),
            "periode": metrics["periode"],
            "trades": metrics["nb_trades"],
            "taux_reussite": metrics["taux_reussite"],
            "esperance_pct": metrics["esperance_pct"],
            "profit_factor": metrics["profit_factor"],
            "rendement": metrics["rendement_total"],
            "buy_and_hold": metrics["rendement_buy_and_hold"],
            "drawdown_max": metrics["drawdown_max"],
            "tags": ["backtest"],
        }
        body = (
            f"# Backtest {settings.symbol} {settings.timeframe}\n\n"
            f"## Résultat\n\n```text\n{report}\n```\n\n"
            f"## Ordres au marché ou limites\n\n```text\n{comparison}\n```\n\n"
            f"## Réglages\n\n{settings_list(settings)}\n\n"
            "## Mes observations\n\n- \n"
        )
        name = f"{now:%Y-%m-%d %Hh%M} {settings.symbol} {settings.timeframe}"
        return self._new_note("Backtests", name, frontmatter(values) + body)

    def robustness(self, settings, rows: list[RobustnessRow], table: str, verdict: str, days: int) -> Path:
        now = self.clock()
        robust = [r.market for r in rows if r.verdict == ROBUST]
        values = {
            "type": "robustesse",
            "date": now.isoformat(timespec="seconds"),
            "plateforme": settings.exchange,
            "jours": days,
            "ordres": settings.execution.order_type,
            "marches_testes": len(rows),
            "robustes": len(robust),
            "marches_robustes": robust,
            "tags": ["robustesse"],
        }
        quoted = "> " + verdict.replace("\n", "\n> ")
        body = (
            f"# Test de robustesse du {now:%d/%m/%Y}\n\n"
            f"```text\n{table}\n```\n\n{quoted}\n\n"
            f"## Réglages\n\n{settings_list(settings)}\n\n"
            "## Mes observations\n\n- \n"
        )
        return self._new_note("Robustesse", f"{now:%Y-%m-%d %Hh%M} robustesse", frontmatter(values) + body)

    def trade(self, mode: str, symbol: str, timeframe: str, record: dict, cost: float) -> Path:
        exit_time = datetime.fromisoformat(record["sortie"]).astimezone()
        return_pct = 100 * record["pnl"] / cost
        values = {
            "type": "trade", "mode": mode, "paire": symbol, "unite": timeframe,
            **record, "rendement_pct": return_pct, "tags": ["trade"],
        }
        outcome = "gagnant" if record["pnl"] > 0 else "perdant"
        body = (
            f"# Trade {symbol} du {exit_time:%d/%m/%Y %H:%M}\n\n"
            f"Trade **{outcome}** : {record['pnl']:+.2f} ({return_pct:+.2f} %), sortie « {record['raison']} ».\n\n"
            "## Ce que je retiens\n\n- \n"
        )
        return self._new_note("Trades", f"{exit_time:%Y-%m-%d %Hh%M} {symbol} {timeframe}", frontmatter(values) + body)

    def event(self, message: str, alert: bool = False) -> None:
        now = self.clock()
        path = self.root / "Journal" / f"{now:%Y-%m-%d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(f"# Journal du {now:%d/%m/%Y}\n\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {now:%H:%M} {'**ALERTE** ' if alert else ''}{message}\n")


class ObsidianHandler(logging.Handler):
    """Recopie dans la note du jour les alertes et les logs marqués `extra=JOURNAL`."""

    def __init__(self, journal: ObsidianJournal):
        super().__init__(logging.INFO)
        self.journal = journal

    def emit(self, record: logging.LogRecord) -> None:
        alert = record.levelno >= logging.WARNING
        if not alert and not getattr(record, "journal", False):
            return
        try:
            self.journal.event(record.getMessage().replace("\n", " "), alert=alert)
        except Exception:
            self.handleError(record)
