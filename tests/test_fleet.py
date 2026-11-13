"""Le moteur des bots (fleet.Book) : comptes, stop, objectif, liquidation, vente à découvert, textes et graphique."""
import math

import numpy as np
import pandas as pd
import pytest

from tests.conftest import HOUR_MS, T0
from tradingbot.data import ohlcv_to_frame
from tradingbot.execution import FUTURES
from tradingbot.fleet import (
    CAPITAL, EXITS, LIQ_SAFETY, MAINTENANCE, SIDES, Book, Spec, chart_view, condition, entry_rule, exit_rule, judge,
    lookback_for, mirror, signals_for, simulate, spec_from, technique,
)
from tradingbot.lab import ALL_VARIANTS
from tradingbot.strategy import STRATEGY_TYPES
from tradingbot.swarm import LIBRARY, new_bot


def spec(name="Cassure 20/10", side="long", target=0.0, leverage=3.0, section="court", symbol="X/USDT", tf="1h",
         stop_mode="fixe"):
    return Spec(section, symbol, tf, name, side, target, leverage, stop_mode)


def test_a_long_stopped_out_loses_its_leverage_times_the_move_plus_fees():
    s = spec("Cassure 20/10", "long", 0.0, 3.0)  # stop à 2 ATR
    book = Book(s, 1000.0, FUTURES)
    book.close_bar(T0, 100.0, True, False, 1.0)
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    price = 100.0 * (1 + FUTURES.slippage)
    assert entry["price"] == pytest.approx(price)
    assert entry["leverage"] == 3 and entry["notional"] == pytest.approx(3000.0)
    assert entry["stop"] == pytest.approx(price - 2.0)
    [exit_] = book.range_bar(T0 + HOUR_MS, 100.0, 100.5, 97.0)
    fill = (price - 2.0) * (1 - FUTURES.slippage)
    qty = 3000.0 / price
    pnl = qty * (fill - price) - qty * fill * FUTURES.fee_rate - 3000.0 * FUTURES.fee_rate
    assert exit_["reason"] == "stop"
    assert exit_["pnl"] == pytest.approx(pnl)
    assert exit_["roi"] == pytest.approx(pnl / 1000.0)
    assert book.s["cash"] == pytest.approx(1000.0 + pnl)
    assert book.s["count"] == 1 and book.s["wins"] == 0


def test_a_short_reaches_its_target_and_pays_maker_fees_and_funding():
    s = spec("Cassure 20/10", "short", 2.0, 5.0)
    book = Book(s, 1000.0, FUTURES)
    book.close_bar(T0, 100.0, True, False, 0.5)
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    price = 100.0 * (1 - FUTURES.slippage)  # le vendeur reçoit un peu moins que le graphique
    assert entry["side"] == "short" and entry["stop"] == pytest.approx(price + 1.0)
    assert entry["target"] == pytest.approx(price - 2.0) and entry["leverage"] == 5
    assert book.range_bar(T0 + HOUR_MS, 100.0, 100.2, 99.5) == []
    book.close_bar(T0 + HOUR_MS, 99.8, False, False, 0.5)
    [exit_] = book.range_bar(T0 + 17 * HOUR_MS, 99.0, 99.2, 97.0)  # 16 h après l'achat
    qty = 5000.0 / price
    target = price - 2.0
    funding = 5000.0 * FUTURES.funding_rate_8h * 2
    pnl = qty * (price - target) - qty * target * FUTURES.maker_fee_rate - funding - 5000.0 * FUTURES.fee_rate
    assert exit_["reason"] == "objectif" and exit_["exit_price"] == pytest.approx(target)
    assert exit_["funding"] == pytest.approx(funding)
    assert exit_["pnl"] == pytest.approx(pnl) and exit_["pnl"] > 0
    assert exit_["gross"] == pytest.approx(1 - target / 100.0)


def test_a_trailing_stop_follows_the_best_price_and_never_goes_back():
    s = spec("Cassure 20/10", "long", 0.0, 1.0, stop_mode="suiveur")
    book = Book(s, 1000.0, FUTURES, explain=True)
    book.close_bar(T0, 100.0, True, False, 1.0)  # stop à 2 ATR = 2 $ sous l'achat
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    stops = [book.position["stop"]]
    for k, (high, low, close) in enumerate([(103.0, 100.5, 102.5), (106.0, 103.0, 105.0), (105.5, 104.5, 105.0)], 1):
        t = T0 + k * HOUR_MS
        assert book.range_bar(t, close - 0.5, high, low) == []
        book.close_bar(t, close, False, False, 1.0)
        stops.append(book.position["stop"])
    assert stops[1] == pytest.approx(103.0 - 2.0) and stops[2] == pytest.approx(106.0 - 2.0)
    assert stops[3] == stops[2]  # le prix recule : le stop ne recule jamais
    [exit_] = book.range_bar(T0 + 4 * HOUR_MS, 104.8, 105.0, 103.0)
    assert exit_["reason"] == "stop suiveur" and exit_["exit_mark"] == pytest.approx(104.0) and exit_["pnl"] > 0
    assert exit_["stop0"] == pytest.approx(entry["stop"]) and exit_["stop"] == pytest.approx(104.0)
    assert exit_["diagnosis"]["kind"] in ("gagne", "gain_partiel")  # le stop remonté a gardé une partie du gain


@pytest.mark.parametrize("side", SIDES)
def test_a_secured_stop_goes_to_the_entry_price_once_the_trade_has_gained_its_risk(side):
    s = spec("Cassure 20/10", side, 2.0, 3.0, stop_mode="securise")
    book = Book(s, 1000.0, FUTURES, explain=True)
    book.close_bar(T0, 100.0, True, False, 1.0)
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    up = side == "long"
    sign = 1 if up else -1
    first = book.position["stop"]
    book.range_bar(T0 + HOUR_MS, 100.0, *sorted([100.0 + sign * 1.5, 100.0])[::-1])  # +0,75 R : rien ne bouge
    book.close_bar(T0 + HOUR_MS, 100.0 + sign * 1.0, False, False, 1.0)
    assert book.position["stop"] == first
    book.range_bar(T0 + 2 * HOUR_MS, 101.0, *sorted([100.0 + sign * 2.5, 100.5 if up else 99.5])[::-1])  # +1,25 R
    book.close_bar(T0 + 2 * HOUR_MS, 100.0 + sign * 2.0, False, False, 1.0)
    cost = 2 * FUTURES.fee_rate + FUTURES.slippage
    assert book.position["stop"] == pytest.approx(entry["price"] * (1 + sign * cost))
    assert book.position["target"] == pytest.approx(entry["target"])  # l'objectif ne bouge pas
    level = book.position["stop"]
    [exit_] = book.range_bar(T0 + 3 * HOUR_MS, level + sign * 0.2, *sorted([level + sign * 0.3, level - sign * 0.5])[::-1])
    assert exit_["reason"] == "stop sécurisé" and abs(exit_["net"]) < 0.002  # presque zéro au lieu d'une perte
    assert exit_["diagnosis"]["kind"] == "securise"


def test_the_stop_mode_is_part_of_the_bot_and_old_bots_keep_their_name():
    fixed, trailing = spec("Cassure 20/10", "long", 2.0), spec("Cassure 20/10", "long", 0.0, stop_mode="suiveur")
    assert fixed.key == "X/USDT|1h|Cassure 20/10|long|2" and trailing.key.endswith("|0|suiveur")
    old = {"section": "court", "symbol": "X/USDT", "timeframe": "1h", "technique": "Cassure 20/10", "side": "long",
           "target_r": 2.0, "leverage": 3.0}
    assert spec_from(old).stop_mode == "fixe" and spec_from(old).key == fixed.key
    assert "suiveur" in exit_rule(trailing) and "sécurisé" in exit_rule(spec(stop_mode="securise", target=2.0))
    with pytest.raises(ValueError):
        spec(stop_mode="magique")


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("risk", [0.002, 0.03, 0.12, 0.25, 0.6])
def test_leverage_is_reduced_so_the_stop_always_comes_before_liquidation(side, risk):
    s = spec("Cassure 20/10", side, 0.0, 10.0)
    book = Book(s, 1000.0, FUTURES)
    atr_value = risk * 100.0 / 2.0  # stop à 2 ATR
    book.close_bar(T0, 100.0, True, False, atr_value)
    [pos] = book.open_bar(T0 + HOUR_MS, 100.0)
    assert 1 <= pos["leverage"] <= 10
    assert pos["leverage"] <= max(1.0, LIQ_SAFETY / (pos["risk"] + MAINTENANCE))
    if pos["leverage"] > 1:
        assert pos["stop"] > pos["liquidation"] if side == "long" else pos["stop"] < pos["liquidation"]


def test_a_gap_through_the_liquidation_price_loses_the_whole_capital():
    s = spec("Cassure 20/10", "long", 0.0, 5.0)
    book = Book(s, 1000.0, FUTURES)
    book.close_bar(T0, 100.0, True, False, 1.0)  # stop à 2 %, liquidation vers −19,5 %
    book.open_bar(T0 + HOUR_MS, 100.0)
    [exit_] = book.range_bar(T0 + 2 * HOUR_MS, 70.0, 71.0, 69.0)  # ouverture à −30 %
    assert exit_["reason"] == "liquidation" and exit_["pnl"] == pytest.approx(-1000.0)
    assert book.s["cash"] == 0.0 and book.s["dead"] == "liquidé"
    book.close_bar(T0 + 2 * HOUR_MS, 70.0, True, False, 1.0)
    assert book.s["pending"] is None  # un bot liquidé ne trade plus


def fair_market(seed: int = 0, minutes: int = 20_000, sigma: float = 0.001, steps: int = 60) -> pd.DataFrame:
    """Un marché où il n'y a rien à gagner : un prix qui avance au hasard chaque seconde, et ses bougies de 1 min. Les
    plus hauts et les plus bas viennent du chemin du prix lui-même (aucune mèche ajoutée : elle avantagerait les
    objectifs et pénaliserait les stops)."""
    r = np.random.default_rng(seed)
    path = 100 * np.exp(np.cumsum(r.normal(0, sigma / math.sqrt(steps), minutes * steps))).reshape(minutes, steps)
    close = path[:, -1]
    opens = np.r_[100.0, close[:-1]]
    rows = np.c_[T0 + np.arange(minutes) * 60_000, opens, np.maximum(path.max(1), opens), np.minimum(path.min(1), opens),
                 close, np.ones(minutes)]
    return ohlcv_to_frame(rows.tolist())


def test_on_a_market_with_nothing_to_win_the_engine_gives_back_the_costs_and_nothing_else():
    """Le garde-fou contre un moteur trop optimiste : sur un prix tiré au hasard, aucune technique ne peut gagner, donc
    le résultat moyen d'un trade doit être le prix des frais, ni plus ni moins. Un aller-retour au marché coûte
    2 × (0,05 % de frais + 0,02 % de glissement) = 0,14 % ; un peu moins quand la sortie est un objectif (ordre
    limite : 0,02 %, sans glissement). Des frais oubliés ou une exécution trop belle feraient remonter cette moyenne ;
    un stop ou un objectif mal compté la ferait sortir de la fourchette."""
    df = fair_market()
    names = ("Cassure 20/10", "Repli RSI(2) < 10 sans filtre", "Bollinger rebond 20/2 sans filtre", "Supertrend 10/3",
             "EMA 9/21", "MACD 12/26/9", "Stochastique 14/3", "Keltner 20/2", "Parabolic SAR", "Heikin-Ashi 2 bougies",
             "Momentum 28", "Écart à la moyenne 20/2")
    nets = {exit_: [] for exit_ in EXITS}
    for name in names:
        for side in SIDES:
            signals = signals_for(df, technique(name), side)
            for target, mode in EXITS:
                book = simulate(df, Spec("scalping", "X/USDT", "1m", name, side, target, 5.0, mode), signals=signals)
                assert book.s["dead"] != "liquidé"  # le stop passe avant la liquidation (mais les frais ruinent)
                nets[(target, mode)] += [t["net"] for t in book.s["trades"] if t["reason"] != "fin du test"]
    everything = [x for xs in nets.values() for x in xs]
    assert len(everything) > 40_000 and all(len(xs) > 8_000 for xs in nets.values())
    assert -0.00143 < np.mean(everything) < -0.00131  # le prix des frais, à 0,006 % près
    by_rule = np.mean(nets[(0.0, "fixe")])  # sortie par la règle ou par le stop : toujours au marché
    assert -0.00145 < by_rule < -0.00132
    for exit_, xs in nets.items():  # aucune façon de sortir ne gagne ni ne perd plus que ses frais
        assert -0.00146 < np.mean(xs) < -0.00128, exit_
    assert 0.2 < np.mean(np.array(everything) > 0) < 0.45  # et bien moins d'un trade sur deux est gagnant


def test_a_short_sees_the_chart_upside_down(random_walk):
    p = technique("Cassure 20/10")
    short = signals_for(random_walk, p, "short")
    low = random_walk["low"].rolling(p.breakout_period).min().shift(1)
    high = random_walk["high"].rolling(p.breakout_exit_period).max().shift(1)
    close = random_walk["close"]
    assert short.entry.sum() > 10
    assert np.array_equal(short.entry[50:], (close < low).to_numpy()[50:])
    assert np.array_equal(short.exit[50:], (close > high).to_numpy()[50:])
    flipped = mirror(random_walk)
    assert (flipped["high"] >= flipped["low"]).all()


def test_the_backtest_respects_the_warm_up_and_closes_what_is_left(random_walk):
    s = spec("Croisement MM 20/100", "long", 0.0, 3.0)
    book = simulate(random_walk, s)
    warm = s.params.warmup_bars
    first = int(random_walk["ts"].iloc[warm])
    assert book.s["trades"] and all(t["entry_ts"] >= first for t in book.s["trades"])
    assert book.position is None
    assert book.s["cash"] == pytest.approx(CAPITAL + sum(t["pnl"] for t in book.s["trades"]))


def test_judge_cuts_the_history_like_the_lab(random_walk):
    s = spec("Cassure 20/10", "long", 2.0, 3.0)
    book = simulate(random_walk, s)
    start, end = int(random_walk["ts"].iloc[0]), int(random_walk["ts"].iloc[-1])
    r = judge(book, start, end)
    assert r["trades"] == len(book.s["trades"])
    assert r["trades"] - (r["study_n"] + r["valid_n"] + r["test_n"]) in (0, 1)  # au plus un trade à cheval sur le test final
    assert r["sv_n"] == r["study_n"] + r["valid_n"] and r["key"] == s.key
    assert r["total_return"] == pytest.approx(book.s["cash"] / 1000.0 - 1)
    assert r["drawdown"] <= 0


def test_the_final_test_is_kept_apart_from_what_chooses_a_bot():
    """Étude 50 %, validation 30 %, test final 20 %. Un trade ouvert avant le test final et fermé pendant ne compte
    ni d'un côté ni de l'autre : son résultat dépend des deux périodes."""
    book = Book(spec("Cassure 20/10", "long", 2.0, 3.0))

    def trade(entry, exit_, net, reason="stop"):
        return {"entry_ts": entry, "exit_ts": exit_, "net": net, "gross": net + 0.0014, "reason": reason}

    book.s["trades"] = [trade(100, 200, 0.01), trade(300, 400, -0.02), trade(550, 700, 0.03), trade(750, 790, 0.01),
                        trade(790, 850, 0.50),  # à cheval : ouvert pendant la validation, fermé pendant le test final
                        trade(800, 900, -0.04), trade(910, 990, 0.02), trade(995, 1000, -0.2, "liquidation")]
    r = judge(book, 0, 1000)
    assert (r["study_n"], r["valid_n"], r["test_n"]) == (2, 2, 3) and r["trades"] == 8
    assert r["study_mean"] == pytest.approx(-0.005) and r["valid_mean"] == pytest.approx(0.02)
    assert r["sv_mean"] == pytest.approx(0.0075)  # le +50 % à cheval n'embellit pas le choix
    assert r["test_mean"] == pytest.approx((-0.04 + 0.02 - 0.2) / 3)  # ni la mesure
    assert r["test_total"] == pytest.approx(-0.22) and r["test_wins"] == 1
    assert r["test_sq"] == pytest.approx(0.04 ** 2 + 0.02 ** 2 + 0.2 ** 2)
    assert not r["liquidated_early"]  # la liquidation a eu lieu pendant le test final : le choix ne la voit pas
    book.s["trades"].insert(1, trade(210, 250, -0.2, "liquidation"))
    assert judge(book, 0, 1000)["liquidated_early"]


@pytest.mark.parametrize("name", LIBRARY)
def test_the_live_window_gives_the_signals_of_the_whole_history(random_walk, name):
    """Le direct ne lit que les dernières bougies (lookback_for) : ses signaux doivent être ceux du backtest, qui lit
    tout l'historique. Comparé sur des bougies tirées au hasard, pour chaque technique et dans les deux sens."""
    p = technique(name)
    look = lookback_for(p)
    df = random_walk.iloc[:look + 400]
    picks = np.random.default_rng(3).choice(np.arange(look - 1, len(df)), size=12, replace=False)
    for side in SIDES:
        full = signals_for(df, p, side)
        for i in picks:
            window = signals_for(df.iloc[i - look + 1:i + 1], p, side)
            assert (window.entry[-1], window.exit[-1]) == (full.entry[i], full.exit[i]), (side, i)
            assert window.atr[-1] == pytest.approx(full.atr[i], rel=1e-6)


@pytest.mark.parametrize("family", STRATEGY_TYPES)
@pytest.mark.parametrize("side", SIDES)
def test_every_rule_is_explained_in_both_directions(family, side):
    name = next(n for n in LIBRARY if technique(n).strategy_type == family)
    s = spec(name, side, 2.0)
    text = entry_rule(s) + " " + exit_rule(s)
    assert ("achète" if side == "long" else "vend à découvert") in text
    assert "de le " not in text and "  " not in text and "objectif" in text
    assert condition(s.params, side)


def test_the_library_covers_every_family_and_every_name_is_known():
    assert len(LIBRARY) == len(set(LIBRARY)) >= 39
    assert {technique(n).strategy_type for n in LIBRARY} == set(STRATEGY_TYPES)
    assert all(n in ALL_VARIANTS or technique(n) for n in LIBRARY)


@pytest.mark.parametrize("name", ["Cassure 20/10", "Bollinger rebond 20/2 + MM200", "Keltner 20/2", "Ichimoku 9/26/52",
                                  "Écart à la moyenne 20/2", "Parabolic SAR", "VWAP + EMA 9/21"])
def test_the_chart_shows_the_rule_lines_trades_and_position(random_walk, name):
    s = spec(name, "short", 2.0)
    bot = new_bot({**s.__dict__, "label": "2", "label_text": "test"}, 1000.0, int(random_walk["ts"].iloc[500]))
    view = chart_view(random_walk.iloc[:602], {"slot": bot["id"], "bot": bot}, FUTURES)
    assert len(view["candles"]) == 150
    assert view["lines"] and all(len(ln["values"]) == 150 for ln in view["lines"])
    assert all(t["side"] == "short" for t in view["rule_trades"])
    assert view["position"] is None and view["symbol"] == "X/USDT"
