import json

from tradingbot.explain import KINDS
from tradingbot.school import EXTRA_SOURCES, FIGURES, LESSONS, school
from tradingbot.knowledge import SOURCES


def test_every_lesson_teaches_one_idea_and_checks_it():
    assert len({lesson["id"] for lesson in LESSONS}) == len(LESSONS) >= 12
    for lesson in LESSONS:
        assert lesson["title"] and 2 <= lesson["minutes"] <= 8
        texts = [b for b in lesson["blocks"] if "text" in b or "example" in b]
        assert len(texts) >= 3, lesson["id"]
        figures = [b["figure"] for b in lesson["blocks"] if "figure" in b]
        assert len(figures) <= 1 and set(figures) <= set(FIGURES), lesson["id"]  # au plus un schéma par leçon
        assert len(lesson["remember"]) >= 2
        assert len(lesson["quiz"]) >= 2
        for q in lesson["quiz"]:
            assert 0 <= q["answer"] < len(q["choices"]) >= 2 and q["why"], q["q"]
        for key in lesson["sources"]:
            assert key in SOURCES or key in EXTRA_SOURCES, key


def test_the_school_links_its_lessons_and_shows_real_trades(tmp_path):
    page = school(tmp_path)
    lessons = page["lessons"]
    assert [l["number"] for l in lessons] == list(range(1, len(lessons) + 1))
    assert all(l["next"] == n["id"] for l, n in zip(lessons, lessons[1:])) and lessons[-1]["next"] is None
    assert all(s["url"].startswith("https://scispace.com/") for l in lessons for s in l["sources"])
    assert page["examples"] == [] and page["kinds"] == KINDS
    (tmp_path / "trader").mkdir()
    trades = [{"symbol": "SOL/USDT", "play": "Rebond sur support (4h)", "net": -0.012, "why": "rebond",
               "diagnosis": {"kind": "faux_depart", "title": "Faux départ", "text": "…", "lesson": "…"}},
              {"symbol": "BTC/USDT", "play": "Momentum 28 (1d)", "net": 0.05, "why": "tendance",
               "diagnosis": {"kind": "gagne", "title": "Scénario réussi", "text": "…", "lesson": "…"}},
              {"symbol": "ETH/USDT", "play": "Momentum 28 (1d)", "net": 0.02, "why": "tendance",
               "diagnosis": {"kind": "gagne", "title": "Scénario réussi", "text": "…", "lesson": "…"}}]
    (tmp_path / "trader" / "rejeu.json").write_text(json.dumps({"replay": True, "trades": trades}), encoding="utf-8")
    shown = school(tmp_path)["examples"]
    assert [e["diagnosis"]["kind"] for e in shown] == ["gagne", "faux_depart"]  # un exemple par diagnostic
    assert shown[0]["symbol"] == "ETH/USDT" and all(e["replay"] for e in shown)  # les plus récents d'abord
