import csv
import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_live import dip_scenario, settings
from tests.conftest import FakeBroker
from tradingbot.dashboard import (
    fmt, fmt_price, fmt_qty, fmt_signed, load_views, nice_ticks, render, tick_decimals, write_dashboard,
)
from tradingbot.lab import VARIANTS
from tradingbot.live import Bot, StateStore, bot_paths
from tradingbot.risk import RiskParams
from tradingbot.robustness import ROBUST, RobustnessRow, save_results

NOW = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
BOTS = (("BTC/USDT", "15m"), ("BTC/USDT", "1h"), ("BTC/USDT", "1d"))


def write_bot(s, symbol, timeframe, state, trades=()):
    state_path, journal_path = bot_paths(replace(s, symbol=symbol, timeframe=timeframe))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    if trades:
        with journal_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(trades[0]))
            writer.writeheader()
            writer.writerows(trades)


def trade(hours_ago, pnl, reason="rebond"):
    exit_time = NOW - timedelta(hours=hours_ago)
    return {
        "entree": (exit_time - timedelta(hours=2)).isoformat(), "sortie": exit_time.isoformat(),
        "prix_entree": 60000.0, "prix_sortie": 60000.0 + pnl * 10, "quantite": 0.1, "cout": 6000.0,
        "pnl": pnl, "raison": reason,
    }


@pytest.fixture
def three_bots(tmp_path):
    s = settings(tmp_path, bots=BOTS)
    fresh = (NOW - timedelta(minutes=1)).isoformat()
    write_bot(s, "BTC/USDT", "15m", {"capital": 10_030.0, "initial_capital": 10_000.0, "equity": 10_030.0,
                                     "updated_at": fresh}, [trade(5, 50.0), trade(3, -20.0, "stop")])
    write_bot(s, "BTC/USDT", "1h", {"capital": 10_000.0, "initial_capital": 10_000.0, "equity": 10_012.5,
                                    "updated_at": fresh, "position": {"qty": 0.1, "entry_price": 60000.0, "stop": 58500.0}})
    write_bot(s, "BTC/USDT", "1d", {"capital": 10_000.0, "initial_capital": 10_000.0, "equity": 10_000.0,
                                    "updated_at": (NOW - timedelta(hours=3)).isoformat()})
    return s


def test_french_number_format():
    assert fmt(1234.5) == "1 234,50"
    assert fmt_signed(-0.004) == "0,00" and fmt_signed(12.345, 1, " %") == "+12,3 %"


@pytest.mark.parametrize("lo, hi", [(-0.5, 0.5), (-3.2, 12.7), (0.0, 250.0), (-0.8, 0.4)])
def test_ticks_cover_the_range_with_zero(lo, hi):
    ticks = nice_ticks(lo, hi)
    assert ticks[0] <= lo and ticks[-1] >= hi
    assert any(abs(t) < 1e-9 for t in ticks)
    decimals = tick_decimals(ticks[1] - ticks[0])
    assert len({fmt_signed(t, decimals) for t in ticks}) == len(ticks)  # aucune graduation ne s'affiche en double


def test_tick_labels_show_their_true_value():
    assert tick_decimals(0.25) == 2 and tick_decimals(0.5) == 1 and tick_decimals(5.0) == 0


def test_quantities_drop_useless_zeros():
    assert fmt_qty(0.05) == "0,05" and fmt_qty(0.00672) == "0,00672" and fmt_qty(2.0) == "2"


def test_views_compute_results_per_bot(three_bots):
    scalp, hourly, daily = load_views(three_bots)
    assert scalp.pnl == pytest.approx(30.0) and scalp.win_rate == 0.5
    assert hourly.pnl == pytest.approx(12.5) and hourly.position["stop"] == 58500.0
    assert daily.trades == []


def test_dashboard_shows_every_bot_and_its_state(three_bots):
    page = render(load_views(three_bots), three_bots, None, NOW)
    for name in ("BTC/USDT 15m", "BTC/USDT 1h", "BTC/USDT 1d"):
        assert name in page
    assert "En position" in page and "58 500,00" in page
    assert "Arrêté ?" in page and "Aucune nouvelle depuis 3 h" in page  # le bot 1d ne donne plus signe de vie
    assert "+42,50" in page  # résultat total : 30 + 12,50
    assert page.count('class="line"') == 3 and "<svg" in page
    assert "Lance le test de robustesse" in page


def test_chart_data_is_valid_json_with_one_series_per_bot(three_bots):
    page = render(load_views(three_bots), three_bots, None, NOW)
    payload = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', page).group(1)
    data = json.loads(payload)
    assert [s["name"] for s in data["series"]] == ["BTC/USDT 15m", "BTC/USDT 1h", "BTC/USDT 1d"]
    assert data["series"][0]["points"][-1][1] == pytest.approx(0.3)


def test_untrusted_text_is_escaped(tmp_path):
    s = settings(tmp_path)
    write_bot(s, "BTC/USDT", "1h", {"capital": 100.0, "initial_capital": 100.0, "equity": 100.0},
              [trade(1, 1.0, "<script>alert(1)</script>")])
    page = render(load_views(s), s, None, NOW)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_dashboard_before_any_run(tmp_path):
    s = settings(tmp_path)
    page = render(load_views(s), s, None, NOW)
    assert "Pas encore lancé" in page and "La courbe apparaîtra" in page and "Aucun trade" in page


def test_live_mode_shows_a_warning_banner(three_bots):
    page = render(load_views(three_bots), replace(three_bots, mode="live"), None, NOW)
    assert "Argent réel" in page


def test_robustness_results_are_shown(three_bots):
    row = RobustnessRow("ETH/USDT 4h", 120, 0.61, 0.21, 0.05, 0.37, 0.01, (0.3, 0.1, float("nan"), -0.2), 0.08, ROBUST)
    path = three_bots.data_dir / "robustesse.json"
    save_results(path, [row], "VERDICT : 1 marché robuste", date=NOW.isoformat(), jours=730, ordres="market")
    page = render(load_views(three_bots), three_bots, json.loads(path.read_text(encoding="utf-8")), NOW)
    assert "ETH/USDT 4h" in page and "chip-good" in page and "2/3" in page and "VERDICT : 1 marché robuste" in page


def test_dashboard_reflects_a_real_bot_run(tmp_path):
    s = settings(tmp_path)
    df = dip_scenario([156.0, 159.0, 161.0, 162.0])
    broker = FakeBroker(df)
    state_path, journal_path = bot_paths(s)
    bot = Bot(broker, s, StateStore(state_path), journal_path)
    for i in range(95, 106):
        bot.step(broker.at_open(i))
    path = write_dashboard(s)
    page = path.read_text(encoding="utf-8")
    assert path.name == "tableau-de-bord.html" and page.endswith("</html>")
    assert "rebond" in page and 'class="line"' in page


def test_stale_alert_follows_the_poll_interval(three_bots):
    slow = replace(three_bots, poll_seconds=3600)  # un tour par heure : 3 h sans nouvelle = 3 tours manqués
    assert "Arrêté ?" not in render(load_views(slow, NOW), slow, None, NOW)
    assert "Arrêté ?" in render(load_views(three_bots, NOW), three_bots, None, NOW)


def test_yesterdays_daily_loss_limit_is_not_shown_as_blocking(tmp_path):
    s = settings(tmp_path, risk=RiskParams())  # limite journalière par défaut : 3 %
    guard = {"peak_equity": 10_000.0, "day": "2026-11-02", "day_start_equity": 10_000.0,
             "last_equity": 9_600.0, "halted": None}
    write_bot(s, "BTC/USDT", "1h", {"capital": 9_600.0, "initial_capital": 10_000.0, "equity": 9_600.0,
                                    "updated_at": NOW.isoformat(), "guard": guard})
    assert load_views(s, NOW)[0].blocked is None
    assert load_views(s, datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc))[0].blocked


def test_memecoin_prices_keep_their_digits():
    assert fmt_price(0.00001234) == "0,000012340" and fmt_price(0.3912) == "0,39120"
    assert fmt_price(187.43) == "187,43" and fmt_price(58_500.0) == "58 500,00" and fmt_price(None) == "—"


def tournament_bot(s, symbol, variant, state, trades=()):
    bs = replace(s, symbol=symbol, timeframe="1m", strategy=VARIANTS[variant], bot_label=variant)
    state_path, journal_path = bot_paths(bs)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"capital": 1000.0, "initial_capital": 1000.0, "equity": 1000.0,
                                      "updated_at": NOW.isoformat(), **state}), encoding="utf-8")
    if trades:
        with journal_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(trades[0]))
            writer.writeheader()
            writer.writerows(trades)
    return bs


@pytest.fixture
def tournament(tmp_path):
    s = replace(settings(tmp_path), data_dir=tmp_path / "tournoi")
    steady = [trade(40 - i, 60.0 + (i % 3)) for i in range(30)]  # +1 % par trade, très régulier
    bots = [
        tournament_bot(s, "PEPE/USDT", "Supertrend 10/3", {"equity": 2_830.0}, steady),
        tournament_bot(s, "DOGE/USDT", "Supertrend 10/3", {}),
        tournament_bot(s, "PEPE/USDT", "Momentum 100", {"eliminated": "perd nettement après 25 trades (−0,61 % par trade)",
                                                         "equity": 900.0}, [trade(2, -100.0, "stop")]),
        tournament_bot(s, "DOGE/USDT", "Momentum 100", {"position": {"qty": 1000.0, "entry_price": 0.3912,
                                                                     "stop": 0.3795, "entry_time": NOW.isoformat()},
                                                        "last_price": 0.3931}),
    ]
    registry = {"started": (NOW - timedelta(hours=6)).isoformat(), "capital": 1000.0,
                "markets": [{"symbol": "PEPE/USDT", "amplitude": 0.21, "volume": 3e7, "change": 0.05},
                            {"symbol": "<b>DOGE</b>/USDT", "amplitude": 0.09, "volume": 5e8, "change": 0.02}],
                "strategies": []}
    return s, bots, registry


def test_tournament_page_ranks_bots_and_groups_them_by_strategy(tournament):
    s, bots, registry = tournament
    page = render(load_views(s, NOW, bots), s, None, NOW, registry=registry)
    assert "Tournoi en argent fictif" in page and "Par stratégie" in page and "en course depuis 6 h" in page
    assert "Laboratoire de stratégies" not in page  # le tournoi a sa propre page, sans les études
    assert "Éliminée" in page and "perd nettement après 25 trades" in page
    # 30 trades réguliers et positifs : le bot, et sa stratégie (trades de ses cryptos réunis), pas les autres
    assert page.count("candidate au testnet") == 2
    board = page.split("<h2>Par stratégie</h2>")
    assert board[0].count("candidate au testnet") == 1 and board[1].count("candidate au testnet") == 1
    assert "0,39120" in page and "&lt;b&gt;DOGE" in page and "<b>DOGE" not in page
    data = json.loads(re.search(r'id="chart-data">(.*?)</script>', page).group(1))
    assert [sr["name"] for sr in data["series"]] == ["Supertrend 10/3", "Momentum 100"]
    keys = re.findall(r'var\(--series-(\d)\)"></span><span><span class="pair">[^<]+</span>'
                      r'<span class="strat"><span class="sep"> · </span>([^<]+)</span>', page)
    assert keys and all(slot == {"Supertrend 10/3": "1", "Momentum 100": "2"}[name] for slot, name in keys)


def test_tournament_dashboard_is_written_in_its_own_folder(tournament):
    s, bots, registry = tournament
    path = write_dashboard(s, NOW, bots=bots, registry=registry)
    assert path.parent == s.data_dir and "PEPE/USDT 1m" in path.read_text(encoding="utf-8")


def test_lab_chart_compares_the_best_gain_before_costs_to_the_cost_of_a_round_trip():
    from tradingbot.dashboard import cost_chart, lab_section

    def row(variant, tf, gross, net, trades=500):
        return {"variant": variant, "timeframe": tf, "trades": trades, "gross_expectancy_pct": gross,
                "expectancy_pct": net, "verdict": "perd de l'argent"}

    rows = [row("Cassure 20/10", "5m", 0.12, -0.18), row("Supertrend 10/3", "1m", 0.04, -0.26),
            row("Momentum 50", "1m", 0.01, -0.29), row("Rare", "15m", 0.9, 0.6, trades=12),
            row("<b>Piège</b>", "15m", 0.21, -0.09)]
    chart = cost_chart(rows)
    assert chart.count('class="bar"') == 3  # une barre par unité de temps : la meilleure de chacune
    assert chart.index("1 min") < chart.index("5 min") < chart.index("15 min")  # de la plus courte à la plus longue
    assert "coût d'un aller-retour : 0,30 %" in chart and "+0,12 %" in chart
    assert "Rare" not in chart  # trop peu de trades pour compter
    assert "&lt;b&gt;Piège" in chart and "<b>Piège" not in chart
    assert cost_chart([row("Rare", "1m", 0.9, 0.6, trades=3)]) == ""
    assert 'id="cost-chart"' in lab_section({"rows": rows, "verdict": "VERDICT", "marches": ["BTC/USDT"]})
