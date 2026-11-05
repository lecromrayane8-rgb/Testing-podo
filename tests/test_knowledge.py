import json

from tradingbot.knowledge import ENTRIES, SOURCES, evidence, knowledge, lab_rows
from tradingbot.lab import VARIANTS
from tradingbot.strategy import STRATEGY_TYPES


def test_every_technique_of_the_bot_has_its_sourced_card():
    covered = {e["family"] for e in ENTRIES if e.get("family")}
    assert covered == set(STRATEGY_TYPES)  # aucune famille du bot sans sa fiche
    for entry in ENTRIES:
        assert entry["measures"] and entry["reading"] and entry["research"] and entry["sources"]
        for key in entry["sources"]:
            title, url = SOURCES[key]
            assert url.startswith("https://scispace.com/papers/") and title
    assert {"Momentum 7", "Momentum 28"} <= set(VARIANTS)  # l'idée tirée de la recherche entre dans le labo


def lab_file(path, rows):
    path.write_text(json.dumps({"date": "2026-11-05T02:00:00+00:00", "verdict": "VERDICT : x", "rows": rows}),
                    encoding="utf-8")


def test_each_card_says_what_the_users_own_labs_found(tmp_path):
    lab_file(tmp_path / "laboratoire.json", [
        {"variant": "Momentum 28", "timeframe": "1d", "trades": 80, "expectancy_pct": 0.42,
         "gross_expectancy_pct": 0.72, "verdict": "à surveiller"},
        {"variant": "Momentum 7", "timeframe": "4h", "trades": 300, "expectancy_pct": -0.1,
         "gross_expectancy_pct": 0.2, "verdict": "perd de l'argent"},
        {"variant": "Momentum 50", "timeframe": "15m", "trades": 5, "expectancy_pct": 2.0, "verdict": "trop peu de trades"},
        {"variant": "Inconnue", "timeframe": "1d", "trades": 80, "expectancy_pct": 9.0},
    ])
    lab_file(tmp_path / "laboratoire-court-terme.json", [
        {"variant": "Cassure 20/10 + volume x2", "timeframe": "5m", "trades": 400, "expectancy_pct": -0.2,
         "verdict": "perd de l'argent"},
    ])
    rows = lab_rows(tmp_path)
    assert len(rows) == 4  # une variante inconnue (ancienne version) est ignorée
    momentum = evidence(next(e for e in ENTRIES if e["key"] == "momentum"), rows)
    assert momentum["tested"] == 3 and momentum["judged"] == 2 and momentum["retained"] == 1
    assert momentum["best"] == {"variant": "Momentum 28", "timeframe": "1d", "lab": "Laboratoire long terme",
                                "net": 0.42, "gross": 0.72, "verdict": "à surveiller"}
    volume = evidence(next(e for e in ENTRIES if e["key"] == "volume"), rows)
    assert volume["tested"] == 1 and volume["best"]["variant"] == "Cassure 20/10 + volume x2"
    page = knowledge(tmp_path)
    figures = next(e for e in page["entries"] if e["key"] == "figures")
    assert figures["lab"] is None and figures["sources"][0]["url"].startswith("https://scispace.com/")
    supertrend = next(e for e in page["entries"] if e["key"] == "supertrend")
    assert supertrend["lab"] == {"tested": 0, "judged": 0, "retained": 0, "best": None}  # pas encore testée
