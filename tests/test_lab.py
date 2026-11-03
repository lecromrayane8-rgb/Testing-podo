import json
import math

import numpy as np
import pytest

import main
import tradingbot.lab as lab
from tests.conftest import frame_from_closes
from tradingbot.execution import ExecutionParams
from tradingbot.lab import (
    PROMISING, VARIANTS, env_lines, evaluate_variant, format_lab, lab_verdict, load_lab,
    overall_lab_verdict, run_lab, save_lab,
)
from tradingbot.risk import RiskParams
from tradingbot.strategy import StrategyParams


def walk(seed, n=2500, drift=0.0003):
    rng = np.random.default_rng(seed)
    return frame_from_closes(100 * np.exp(np.cumsum(rng.normal(drift, 0.012, n))))


FAST = StrategyParams(strategy_type="cassure", breakout_period=10, breakout_exit_period=5, trend_period=0,
                      stop_atr_mult=2.0, max_bars_in_trade=0)


@pytest.mark.parametrize("args, expected", [
    ((10, 0.5, 0.5, 0.1, 3, 3), "trop peu de trades"),
    ((200, 0.5, -0.1, -0.3, 0, 3), "perd de l'argent"),
    ((200, -0.2, 0.3, 0.1, 3, 3), "instable"),
    ((200, 0.2, 0.3, -0.05, 3, 3), "à surveiller"),
    ((200, 0.2, 0.3, 0.05, 1, 3), "à surveiller"),  # positif sur trop peu de marchés
    ((200, 0.2, 0.3, 0.05, 2, 3), PROMISING),
])
def test_lab_verdicts(args, expected):
    assert lab_verdict(*args) == expected


def test_trades_are_split_between_study_and_validation():
    datasets = {"A": walk(1), "B": walk(2)}
    row = evaluate_variant("Cassure 10 / 5", FAST, "1h", datasets, ExecutionParams(), RiskParams(), n_tests=1)
    total = sum(len(main.run_backtest(df, FAST, lab.research_risk(RiskParams()), 10_000.0,
                                      ExecutionParams()).trades) for df in datasets.values())
    assert row.study_trades + row.trades == total
    assert row.study_trades > row.trades > 0  # 60 % de l'historique pour l'étude, 40 % pour la validation
    assert row.markets_judged == 2 and 0 <= row.markets_positive <= 2
    df = datasets["A"]
    cutoff = df.index[0] + (df.index[-1] - df.index[0]) * lab.STUDY_SHARE
    closes = df["close"][df.index >= cutoff]
    expected_bh = np.mean([d["close"][d.index >= cutoff].iloc[-1] / d["close"][d.index >= cutoff].iloc[0] - 1
                           for d in datasets.values()])
    assert closes.iloc[0] > 0 and row.buy_hold_return == pytest.approx(expected_bh)


def test_studies_run_without_the_live_safety_stops(monkeypatch):
    seen = []
    original = lab.run_backtest

    def spy(df, params, risk, *args):
        seen.append(risk)
        return original(df, params, risk, *args)

    monkeypatch.setattr(lab, "run_backtest", spy)
    evaluate_variant("x", FAST, "1h", {"A": walk(3)}, ExecutionParams(), RiskParams(), n_tests=1)
    assert seen and seen[0].max_drawdown == 1.0 and seen[0].daily_loss_limit == 1.0


def test_more_tests_mean_a_stricter_bar():
    datasets = {"A": walk(4), "B": walk(5)}
    one = evaluate_variant("x", FAST, "1h", datasets, ExecutionParams(), RiskParams(), n_tests=1)
    many = evaluate_variant("x", FAST, "1h", datasets, ExecutionParams(), RiskParams(), n_tests=100)
    assert many.ci_low_adjusted < one.ci_low_adjusted


def test_run_lab_covers_every_variant_and_timeframe_sorted_by_expectancy():
    variants = {"Cassure": FAST, "Retour": StrategyParams(trend_period=50, atr_period=5)}
    rows = run_lab({"1h": {"A": walk(6)}, "1d": {"A": walk(7)}}, ExecutionParams(), RiskParams(), variants)
    assert {(r.variant, r.timeframe) for r in rows} == {(v, tf) for v in variants for tf in ("1h", "1d")}
    exps = [r.expectancy_pct for r in rows if not math.isnan(r.expectancy_pct)]
    assert exps == sorted(exps, reverse=True)
    text = format_lab(rows)
    assert "Variante" in text and "Buy&hold" in text and "pour les 4 essais" in text


def test_overall_verdict_and_env_lines():
    rows = run_lab({"1h": {"A": walk(8)}}, ExecutionParams(), RiskParams(), {"Cassure": FAST})
    assert overall_lab_verdict(rows).startswith("VERDICT : ")
    promising = [r for r in rows]
    promising[0] = lab.LabRow(**{**promising[0].__dict__, "verdict": PROMISING})
    assert "La meilleure : Cassure" in overall_lab_verdict(promising)
    assert "STRATEGY_TYPE=cassure" in env_lines(VARIANTS["Cassure 55/20"])
    assert "BREAKOUT_PERIOD=55" in env_lines(VARIANTS["Cassure 55/20"])


def test_lab_results_roundtrip(tmp_path):
    rows = run_lab({"1h": {"A": walk(9)}}, ExecutionParams(), RiskParams(), {"Cassure": FAST})
    save_lab(tmp_path / "labo.json", rows, "VERDICT : test", date="2026-11-03T18:00:00+00:00", marches=["A"])
    saved = load_lab(tmp_path / "labo.json")
    assert saved["verdict"] == "VERDICT : test" and saved["rows"][0]["variant"] == "Cassure"
    assert load_lab(tmp_path / "absent.json") is None


def test_lab_command_tests_cryptos_and_stock_csvs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    stocks = tmp_path / "actions"
    stocks.mkdir()
    daily = walk(10, n=2600)
    lines = ["Date,Open,High,Low,Close,Volume"] + [
        f"{d:%Y-%m-%d},{o},{h},{lo},{c},1" for d, o, h, lo, c in
        zip(daily.index, daily["open"], daily["high"], daily["low"], daily["close"])
    ]
    (stocks / "AAPL.csv").write_text("\n".join(lines), encoding="utf-8")
    requested = []

    def fake_load(exchange_id, symbol, timeframe, days, cache_dir, exchange=None):
        requested.append((symbol, timeframe, days))
        return walk(len(requested), n=1500)

    monkeypatch.setattr(main, "load_or_fetch", fake_load)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    code = main.main(["labo", "--symbols", "BTC/USDT,PAXG/USDT", "--timeframes", "1h,1d", "--csv-dir", str(stocks)])

    assert code == 0
    assert ("PAXG/USDT", "1d", main.LONG_TERM_DAYS) in requested
    saved = json.loads((tmp_path / "data" / "laboratoire.json").read_text(encoding="utf-8"))
    assert saved["marches"] == ["AAPL", "BTC/USDT", "PAXG/USDT"]
    assert len(saved["rows"]) == len(VARIANTS) * 2
    page = (tmp_path / "data" / "tableau-de-bord.html").read_text(encoding="utf-8")
    assert "Laboratoire de stratégies" in page and "Cassure 55/20" in page


def test_short_term_combos_are_named_variants_with_filters():
    from tradingbot.lab import ALL_VARIANTS, COMBOS
    assert len(COMBOS) == 12 and not set(COMBOS) & set(VARIANTS)
    assert all(p.min_atr_pct > 0 or p.volume_mult > 0 for p in COMBOS.values())
    assert ALL_VARIANTS == {**VARIANTS, **COMBOS}
    assert "MIN_ATR_PCT=0.003" in env_lines(COMBOS["Cassure 20/10 + volatilité"])


def lab_row(name, gross, net, trades=200, verdict="perd de l'argent"):
    return lab.LabRow(name, "1m", trades, net, trades, 0.5, net, net - 0.1, net + 0.1, net - 0.2, 0, 3, -0.1, 0.0,
                      verdict, gross)


def test_cost_diagnosis_says_whether_fees_are_the_problem():
    from tradingbot.lab import cost_diagnosis
    nothing = cost_diagnosis([lab_row("A", -0.02, -0.32), lab_row("B", -0.05, -0.35)])
    assert "-0.020 %" in nothing and "0.300 %" in nothing and "Même sans aucun frais, rien ne gagne" in nothing
    fees = cost_diagnosis([lab_row("A", 0.12, -0.18), lab_row("B", -0.05, -0.35)])
    assert "Ce sont les frais qui la font perdre" in fees and "meilleure de 2 essais" in fees
    assert cost_diagnosis([lab_row("A", 0.5, 0.2, trades=3)]) == ""  # trop peu de trades pour juger


def test_lab_shows_results_before_and_after_costs():
    rows = run_lab({"1h": {"A": walk(1), "B": walk(2)}}, ExecutionParams(fee_rate=0.001, slippage=0.0005),
                   RiskParams(), {"Cassure rapide": FAST})
    row = rows[0]
    assert row.gross_expectancy_pct - row.expectancy_pct == pytest.approx(0.3, abs=0.02)  # aller-retour ~0,3 %
    assert "Avant frais" in format_lab(rows)
