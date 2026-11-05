import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from tests.conftest import DAY0 as T0, DAY_MS as DAY, daily_frame as daily
from tradingbot.portfolio import (
    MIN_COINS, PORTFOLIO_VARIANTS, PaperPortfolio, PortfolioParams, align, evaluate, load, next_rotation,
    overall_verdict, portfolio_verdict, save, simulate, split,
)


def steady(growths, days=120):
    """Une crypto par taux de hausse journalier constant, de la plus lente à la plus rapide."""
    return {f"C{k}/USDT": daily(100 * (1 + g) ** np.arange(days)) for k, g in enumerate(growths)}


def noisy(drifts, days, seed=1, vol=0.01):
    rng = np.random.default_rng(seed)
    return {f"C{k}/USDT": daily(100 * np.exp(np.cumsum(rng.normal(d, vol, days)))) for k, d in enumerate(drifts)}


def test_each_week_keeps_the_coins_that_rose_the_most():
    opens, closes = align(steady([0.001 * k for k in range(8)]))
    weeks = simulate(opens, closes, PortfolioParams(7, 3), cost=0.0)
    assert len(weeks) > 10
    assert all(set(w.holdings) == {"C7/USDT", "C6/USDT", "C5/USDT"} for w in weeks)
    expected = np.mean([(1 + g) ** 7 - 1 for g in (0.007, 0.006, 0.005)])
    assert weeks[3].gross == pytest.approx(expected)
    assert weeks[3].basket == pytest.approx(np.mean([(1 + 0.001 * k) ** 7 - 1 for k in range(8)]))


def test_rotations_pay_their_costs_and_the_last_sale_too():
    opens, closes = align(steady([0.001 * k for k in range(8)]))
    weeks = simulate(opens, closes, PortfolioParams(7, 3), cost=0.01)
    first, middle, last = weeks[0], weeks[1], weeks[-1]
    assert first.turnover == 1 and first.ret == pytest.approx((1 + first.gross) * 0.99 - 1)  # tout est acheté
    assert middle.turnover == 0 and middle.ret == pytest.approx(middle.gross)  # rien ne change : aucun frais
    assert last.turnover == 1 and last.ret == pytest.approx((1 + last.gross) * 0.99 - 1)  # la vente finale


def test_a_decision_never_looks_at_the_future():
    opens, closes = align(noisy([0.0] * 8, 300, seed=3, vol=0.03))
    before = simulate(opens, closes, PortfolioParams(14, 3), cost=0.002)
    cut = 150
    changed_opens, changed_closes = opens.copy(), closes.copy()
    shock = np.random.default_rng(9).uniform(0.5, 2.0, size=(len(opens) - cut - 1, 8))
    changed_opens.iloc[cut + 1:] *= shock
    changed_closes.iloc[cut + 1:] *= shock[::-1]
    after = simulate(changed_opens, changed_closes, PortfolioParams(14, 3), cost=0.002)
    days = list(closes.index.strftime("%Y-%m-%d"))
    settled = [w for w in before[:-1] if days.index(w.start) + 14 <= cut]  # revendues avant le changement
    assert len(settled) >= 8
    assert after[:len(settled)] == settled


def test_no_ranking_until_enough_coins_are_listed():
    frames = noisy([0.0] * (MIN_COINS - 1), 200, seed=4)
    assert simulate(*align(frames), PortfolioParams(7, 3), cost=0.0) == []
    frames["LATE/USDT"] = daily(100 * np.ones(120), first_day=80)  # cotée au 80e jour
    weeks = simulate(*align(frames), PortfolioParams(7, 3), cost=0.0)
    start = datetime.fromtimestamp((T0 + (80 + 7) * DAY) / 1000, timezone.utc).date()
    assert weeks and datetime.fromisoformat(weeks[0].start).date() > start


def test_weeks_are_cut_in_time_like_the_lab():
    weeks = list(range(100))
    study, valid, test = split(weeks)
    assert (len(study), len(valid), len(test)) == (50, 30, 20) and test[-1] == 99


# (semaines, moyenne, écart avec le panier, écart sur l'étude, borne basse durcie de l'écart, semaines de test,
#  moyenne du test, écart du test)
@pytest.mark.parametrize("args, verdict", [
    ((10, 1.0, 0.5, 0.5, 0.2, 5, 1.0, 0.5), "trop peu de semaines"),
    ((40, -0.1, 0.5, 0.5, 0.2, 20, 1.0, 0.5), "perd de l'argent"),
    ((40, 1.0, -0.1, 0.5, -0.3, 20, 1.0, 0.5), "ne bat pas le panier"),  # gagne, mais moins que tout garder
    ((40, 1.0, 0.5, -0.2, 0.2, 20, 1.0, 0.5), "instable"),  # ne battait pas le panier sur l'étude
    ((40, 1.0, 0.5, 0.5, 0.2, 20, 1.0, -0.1), "instable"),  # ne le bat plus sur le test final
    ((40, 1.0, 0.5, 0.5, 0.2, 20, 1.0, 0.5), "prometteur"),
    ((40, 1.0, 0.5, 0.5, -0.1, 20, 1.0, 0.5), "à surveiller"),  # écart pas assez net, seuil durci compris
    ((40, 1.0, 0.5, 0.5, 0.2, 5, 1.0, 0.5), "à surveiller"),  # test final trop court pour confirmer
    ((40, 1.0, 0.5, 0.5, 0.2, 20, -0.3, 0.5), "à surveiller"),  # bat le panier mais perd dans un marché qui baisse
])
def test_the_verdict_needs_validation_a_final_test_and_to_beat_the_basket(args, verdict):
    assert portfolio_verdict(*args) == verdict


def test_a_real_momentum_is_found_and_noise_is_not():
    drifts = np.linspace(-0.002, 0.004, 10)
    rng = np.random.default_rng(5)
    frames = {f"C{k}/USDT": daily(100 * np.exp(np.cumsum(rng.normal(d, 0.01, 1500)))) for k, d in enumerate(drifts)}
    rows = evaluate(*align(frames), cost=0.0015)
    assert [r.mean_pct for r in rows] == sorted((r.mean_pct for r in rows), reverse=True)
    assert all(r.ci_low_adjusted < r.ci_low for r in rows)  # seuil durci par le nombre de variantes
    best = rows[0]
    assert best.excess_pct > 0 and best.excess_ci_low_adjusted < best.excess_pct and best.study_excess_pct > 0
    assert any(r.verdict == "prometteur" for r in rows)
    noise = evaluate(*align(noisy([0.0] * 10, 1500, seed=6, vol=0.03)), cost=0.0015)
    assert not any(r.verdict == "prometteur" for r in noise)


def test_the_overall_verdict_warns_about_survivors(tmp_path):
    rows = evaluate(*align(noisy([0.0] * 8, 400, seed=7)), cost=0.0015)
    verdict = overall_verdict(rows, 8)
    assert verdict.startswith("VERDICT") and "disparu" in verdict
    save(tmp_path / "lab.json", rows, verdict, univers=["A/USDT"])
    saved = load(tmp_path / "lab.json")
    assert saved["univers"] == ["A/USDT"] and len(saved["rows"]) == len(PORTFOLIO_VARIANTS)
    assert isinstance(saved["rows"][0]["holdings"], list)
    assert load(tmp_path / "absent.json") is None


NOW = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)


def book(tmp_path, fee=0.001, slip=0.0005):
    return PaperPortfolio(tmp_path / "pf.json", "Momentum croisé 7 j, 3 cryptos", PortfolioParams(7, 3), fee, slip, 1000)


def test_the_paper_portfolio_buys_the_leaders_at_equal_weights(tmp_path):
    _, closes = align(steady([0.001 * k for k in range(8)], days=30))
    prices = {s: float(closes[s].iloc[-1]) for s in closes}
    pf = book(tmp_path)
    assert pf.due(NOW)
    rotation = pf.rotate(closes, prices, NOW)
    assert rotation["chosen"] == ["C7/USDT", "C6/USDT", "C5/USDT"] and rotation["sold"] == []
    worth = [q * prices[s] for s, q in pf.state["holdings"].items()]
    assert len(worth) == 3 and max(worth) - min(worth) < 1e-6
    assert pf.state["cash"] == pytest.approx(0, abs=1e-9)
    assert pf.value(prices) == pytest.approx(1000 - rotation["costs"])
    assert 1000 * 0.0014 < rotation["costs"] < 1000 * 0.0016  # frais et glissement d'un achat
    assert pf.state["next"] == "2026-11-16T00:10:00+00:00"  # le lendemain à 00 h 10, puis une semaine
    assert not pf.due(NOW + timedelta(days=6)) and pf.due(datetime(2026, 11, 16, 0, 10, tzinfo=timezone.utc))


def test_a_rotation_sells_what_left_the_ranking(tmp_path):
    _, closes = align(steady([0.001 * k for k in range(8)], days=30))
    prices = {s: float(closes[s].iloc[-1]) for s in closes}
    pf = book(tmp_path)
    pf.rotate(closes, prices, NOW)
    closes["C0/USDT"] = closes["C0/USDT"] * (1.5 ** np.arange(len(closes)) / 1.5 ** (len(closes) - 1))
    before = pf.value(prices)
    rotation = pf.rotate(closes, prices, NOW + timedelta(days=7))
    assert rotation["chosen"][0] == "C0/USDT" and rotation["sold"] == ["C5/USDT"]
    assert set(pf.state["holdings"]) == {"C0/USDT", "C7/USDT", "C6/USDT"}
    assert pf.value(prices) == pytest.approx(before - rotation["costs"])
    assert pf.state["cash"] >= 0


def test_the_paper_portfolio_survives_a_restart_and_a_silent_platform(tmp_path):
    _, closes = align(steady([0.001 * k for k in range(8)], days=30))
    prices = {s: float(closes[s].iloc[-1]) for s in closes}
    pf = book(tmp_path)
    pf.rotate(closes, prices, NOW)
    value = pf.value(prices)
    again = book(tmp_path)  # redémarrage : l'état est relu
    assert again.state["holdings"] == pf.state["holdings"] and again.state["next"] == pf.state["next"]
    assert again.value({}) == pytest.approx(value)  # plus aucun prix : les derniers connus servent
    again.mark({}, NOW + timedelta(hours=2))
    assert again.state["value"] == pytest.approx(value)


def test_the_value_is_noted_at_most_once_an_hour(tmp_path):
    pf = book(tmp_path)
    for minutes in (0, 20, 50, 61, 90, 125):
        pf.mark({}, NOW + timedelta(minutes=minutes))
    assert [h["t"][11:16] for h in pf.state["history"]] == ["15:00", "16:01", "17:05"]


def test_a_rotation_waits_when_a_held_coin_has_no_price_at_all(tmp_path):
    _, closes = align(steady([0.001 * k for k in range(8)], days=30))
    prices = {s: float(closes[s].iloc[-1]) for s in closes}
    pf = book(tmp_path)
    pf.rotate(closes, prices, NOW)
    pf.state["prices"] = {}
    with pytest.raises(ValueError, match="rotation reportée"):
        pf.rotate(closes, {s: p for s, p in prices.items() if s != "C7/USDT"}, NOW + timedelta(days=7))


def test_a_new_variant_starts_a_fresh_portfolio(tmp_path):
    (tmp_path / "pf.json").write_text(json.dumps({"variant": "autre", "cash": 5}), encoding="utf-8")
    assert book(tmp_path).state["cash"] == 1000


def test_the_next_rotation_is_ten_past_midnight_utc():
    assert next_rotation(datetime(2026, 11, 9, 0, 5, tzinfo=timezone.utc)).isoformat() == "2026-11-09T00:10:00+00:00"
    assert next_rotation(datetime(2026, 11, 9, 0, 10, tzinfo=timezone.utc)).isoformat() == "2026-11-10T00:10:00+00:00"
