"""Le moteur des bots (fleet.Book) : comptes, stop, objectif, liquidation, vente à découvert, textes et graphique."""
import math

import numpy as np
import pandas as pd
import pytest

from tests.conftest import HOUR_MS, T0
from tradingbot.data import ohlcv_to_frame
from tradingbot.execution import FUTURES
from tradingbot.fleet import (
    CAPITAL, EXITS, LIQ_SAFETY, MAINTENANCE, SIDES, Book, Spec, _position_view, chart_view, condition, entry_rule,
    exit_rule, judge, lookback_for, mirror, signals_for, simulate, spec_from, technique, with_security,
)
from tradingbot.lab import ALL_VARIANTS
from tradingbot.strategy import STRATEGY_TYPES
from tradingbot.swarm import LIBRARY, new_bot


def spec(name="Cassure 20/10", side="long", target=0.0, leverage=3.0, section="court", symbol="X/USDT", tf="1h",
         stop_mode="fixe", secure_r=0.0, secure_part=0.0):
    return Spec(section, symbol, tf, name, side, target, leverage, stop_mode, secure_r, secure_part)


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


def secured_trade(side, target=0.0, part=0.5, leverage=3.0, stop_mode="fixe", explain=False):
    """Un bot avec sécurisation à +1R, entré à 100 avec un stop à 2 $ (2 ATR) : le livre, l'entrée et le signe."""
    s = spec("Cassure 20/10", side, target, leverage, stop_mode=stop_mode, secure_r=1.0, secure_part=part)
    book = Book(s, 1000.0, FUTURES, explain=explain)
    book.close_bar(T0, 100.0, True, False, 1.0)
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    return book, entry, 1 if side == "long" else -1


def bar(book, k, open_, far, near):
    """La bougie k (en heures depuis T0) : `far` est l'extrême du côté du gain, `near` celui du côté du stop."""
    return book.range_bar(T0 + k * HOUR_MS, open_, max(far, near), min(far, near))


@pytest.mark.parametrize("side", SIDES)
def test_securing_cashes_half_the_position_at_one_r_and_moves_the_stop_to_the_entry_price(side):
    """Le compte d'un trade sécurisé, au centime : la moitié encaissée par un ordre limite à +1R (frais maker, pas de
    glissement, financement de cette moitié jusque-là), puis le reste sorti au stop passé au prix d'entrée."""
    book, entry, sign = secured_trade(side, explain=True)
    price, qty, fee_in = entry["price"], entry["qty"], 3000.0 * FUTURES.fee_rate
    level = price + sign * 2.0
    assert entry["secure"] == pytest.approx(level) and entry["part"] == 0.5 and entry["notional"] == pytest.approx(3000.0)
    assert bar(book, 1, 100.0, 100.0 + sign * 1.5, 100.0 - sign * 0.2) == []  # +0,75 R : rien
    book.close_bar(T0 + HOUR_MS, 100.0 + sign * 1.0, False, False, 1.0)
    assert book.position["stop"] == entry["stop"] and "left" not in book.position
    [event] = bar(book, 2, 100.0 + sign * 1.0, 100.0 + sign * 2.6, 100.0 + sign * 0.8)  # +1,3 R : le seuil est dépassé
    funding_a = 1500.0 * FUTURES.funding_rate_8h * 1 / 8  # une heure depuis l'entrée, sur la moitié
    half = sign * (qty / 2) * (level - price) - (qty / 2) * level * FUTURES.maker_fee_rate - funding_a - fee_in / 2
    assert event["kind"] == "secure" and event["part"] == 0.5 and event["price"] == pytest.approx(level)
    assert event["pnl"] == pytest.approx(half) and half > 0
    assert book.s["cash"] == pytest.approx(1000.0 - fee_in / 2 + half)  # la moitié des frais d'entrée reste à compter
    assert book.s["count"] == 0 and book.s["trades"] == []  # le trade n'est pas fini : rien n'est compté deux fois
    pos = book.position
    assert pos["left"] == 0.5 and pos["qty"] == pytest.approx(qty) and pos["notional"] == pytest.approx(3000.0)
    assert pos["stop"] == entry["stop"]  # le stop ne bouge qu'à la clôture de la bougie
    assert book.equity(level) == pytest.approx(book.s["cash"] + sign * (qty / 2) * (level - price))
    book.close_bar(T0 + 2 * HOUR_MS, 100.0 + sign * 2.2, False, False, 1.0)
    cost = 2 * FUTURES.fee_rate + FUTURES.slippage
    stop = price * (1 + sign * cost)
    assert pos["stop"] == pytest.approx(stop) and pos["moved"] == 1 and pos["stop_kind"] == "securise"
    assert bar(book, 2, 100.0 + sign * 2.3, 100.0 + sign * 2.6, 100.0 + sign * 2.2) == []  # jamais encaissée deux fois
    [exit_] = bar(book, 3, stop + sign * 0.3, stop + sign * 0.4, stop - sign * 0.5)
    fill = stop * (1 - sign * FUTURES.slippage)
    funding_b = 1500.0 * FUTURES.funding_rate_8h * 2 / 8  # deux heures, sur l'autre moitié
    rest = sign * (qty / 2) * (fill - price) - (qty / 2) * fill * FUTURES.fee_rate - funding_b - fee_in / 2
    assert exit_["kind"] == "exit" and exit_["reason"] == "stop sécurisé"
    assert abs(rest + funding_b) < 0.01  # sans le financement, le reste sort à zéro : « prix d'entrée, frais compris »
    assert exit_["pnl"] == pytest.approx(half + rest) and exit_["net"] == pytest.approx((half + rest) / 3000.0)
    assert exit_["roi"] == pytest.approx((half + rest) / 1000.0) and exit_["funding"] == pytest.approx(funding_a + funding_b)
    assert exit_["qty"] == pytest.approx(qty) and exit_["notional"] == pytest.approx(3000.0)  # la taille de l'entrée
    assert exit_["gross"] == pytest.approx(0.5 * sign * (level / 100.0 - 1) + 0.5 * sign * (stop / 100.0 - 1))
    assert exit_["secured"] == {"ts": T0 + 2 * HOUR_MS, "price": pytest.approx(level), "part": 0.5,
                                "pnl": pytest.approx(half)}
    assert exit_["diagnosis"]["kind"] == "encaisse"
    assert book.s["cash"] == pytest.approx(1000.0 + half + rest)  # le compte retombe sur ses pieds
    assert (book.s["count"], book.s["wins"]) == (1, 1) and book.s["pnl"] == pytest.approx(half + rest)
    assert book.position is None


@pytest.mark.parametrize("side", SIDES)
def test_a_secured_trade_reaching_its_target_is_one_trade_with_two_exits(side):
    book, entry, sign = secured_trade(side, target=2.0)
    price, qty, fee_in = entry["price"], entry["qty"], 3000.0 * FUTURES.fee_rate
    level, target = price + sign * 2.0, price + sign * 4.0
    assert entry["target"] == pytest.approx(target)
    # Une seule bougie dépasse le seuil puis l'objectif : la moitié au seuil, le reste à l'objectif, un seul trade.
    events = bar(book, 3, 100.0 + sign * 0.5, 100.0 + sign * 4.5, 100.0 + sign * 0.2)
    assert [e["kind"] for e in events] == ["secure", "exit"]
    funding = 1500.0 * FUTURES.funding_rate_8h * 2 / 8  # deux heures, pour chaque moitié
    half = sign * (qty / 2) * (level - price) - (qty / 2) * level * FUTURES.maker_fee_rate - funding - fee_in / 2
    rest = sign * (qty / 2) * (target - price) - (qty / 2) * target * FUTURES.maker_fee_rate - funding - fee_in / 2
    trade = events[1]
    assert trade["reason"] == "objectif" and trade["exit_price"] == pytest.approx(target)
    assert trade["pnl"] == pytest.approx(half + rest) and book.s["cash"] == pytest.approx(1000.0 + half + rest)
    assert trade["fees"] == pytest.approx((fee_in + (qty / 2) * (level + target) * FUTURES.maker_fee_rate
                                           + 2 * funding) / 3000.0)
    assert book.s["count"] == 1 and len(book.s["trades"]) == 1 and book.position is None


@pytest.mark.parametrize("side", SIDES)
def test_the_stop_comes_first_when_one_candle_touches_the_stop_and_the_securing_level(side):
    """Dans une bougie qui touche à la fois le stop et le seuil, on ne sait pas lequel est venu d'abord : le moteur
    compte le pire (le stop sur toute la position), comme pour l'objectif."""
    book, entry, sign = secured_trade(side)
    [exit_] = bar(book, 1, 100.0, 100.0 + sign * 3.0, 100.0 - sign * 2.5)
    assert exit_["reason"] == "stop" and "secured" not in exit_ and exit_["pnl"] < 0
    qty = entry["qty"]
    fill = entry["stop"] * (1 - sign * FUTURES.slippage)
    assert exit_["pnl"] == pytest.approx(sign * qty * (fill - entry["price"]) - qty * fill * FUTURES.fee_rate
                                         - 3000.0 * FUTURES.fee_rate)


def test_securing_without_a_part_only_moves_the_stop():
    book, entry, sign = secured_trade("long", part=0.0)
    cash = book.s["cash"]
    [event] = bar(book, 1, 100.0, 102.5, 99.9)
    assert event["kind"] == "secure" and event["part"] == 0.0 and event["pnl"] == 0.0
    assert book.s["cash"] == cash and "left" not in book.position and "banked" not in book.position
    book.close_bar(T0 + HOUR_MS, 102.0, False, False, 1.0)
    assert book.position["stop"] == pytest.approx(entry["price"] * (1 + 2 * FUTURES.fee_rate + FUTURES.slippage))
    [exit_] = bar(book, 2, 101.0, 101.2, 100.0)
    assert exit_["reason"] == "stop sécurisé" and exit_["secured"]["part"] == 0.0
    assert abs(exit_["net"]) < 3e-5  # zéro, au financement d'une heure près (0,00125 %)


def test_a_part_too_small_for_an_order_is_not_cashed():
    s = spec("Cassure 20/10", "long", 0.0, 1.0, secure_r=1.0, secure_part=0.5)
    book = Book(s, 15.0, FUTURES)  # 15 USDT en jeu : la moitié (7,5) est sous le plus petit ordre accepté (10)
    book.close_bar(T0, 100.0, True, False, 1.0)
    book.open_bar(T0 + HOUR_MS, 100.0)
    [event] = bar(book, 1, 100.0, 102.5, 99.9)
    assert event["part"] == 0.0 and "left" not in book.position and book.position["secured"]


@pytest.mark.parametrize("secure_r", [2.0, 3.0])
def test_no_securing_level_when_it_is_not_before_the_target(secure_r):
    s = spec("Cassure 20/10", "long", 2.0, 3.0, secure_r=secure_r, secure_part=0.5)
    book = Book(s, 1000.0, FUTURES)
    book.close_bar(T0, 100.0, True, False, 1.0)
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    assert "secure" not in entry  # l'objectif à 2R ferme tout avant (ou en même temps)
    [exit_] = bar(book, 1, 100.0, 104.5, 99.9)
    assert exit_["reason"] == "objectif" and "secured" not in exit_


def test_a_gap_through_liquidation_after_securing_loses_only_what_was_still_at_stake():
    book, entry, sign = secured_trade("long", leverage=5.0)
    assert entry["leverage"] == 5 and entry["notional"] == pytest.approx(5000.0)
    [event] = bar(book, 1, 100.0, 102.5, 99.9)
    book.close_bar(T0 + HOUR_MS, 102.2, False, False, 1.0)
    cash = book.s["cash"]
    fee_in = 5000.0 * FUTURES.fee_rate
    assert cash == pytest.approx(1000.0 - fee_in / 2 + event["pnl"])
    [exit_] = book.range_bar(T0 + 2 * HOUR_MS, 70.0, 71.0, 69.0)  # ouverture à −30 % : sous la liquidation
    assert exit_["reason"] == "liquidation" and book.s["dead"] == "liquidé"
    assert exit_["pnl"] == pytest.approx(-500.0 + event["pnl"])  # la moitié de la mise restait en jeu
    assert book.s["cash"] == pytest.approx(1000.0 + exit_["pnl"]) and book.s["cash"] > 400.0


def test_a_trailing_stop_with_securing_keeps_the_most_protective_stop():
    book, entry, sign = secured_trade("long", stop_mode="suiveur", leverage=1.0)
    price = entry["price"]
    [event] = bar(book, 1, 100.0, 102.1, 99.9)  # tout juste +1R : le stop suiveur (100,1) est sous le prix d'entrée
    assert event["kind"] == "secure"
    book.close_bar(T0 + HOUR_MS, 101.9, False, False, 1.0)
    pos = book.position
    assert pos["stop"] == pytest.approx(price * (1 + 2 * FUTURES.fee_rate + FUTURES.slippage)) and pos["stop_kind"] == "securise"
    assert bar(book, 2, 102.0, 106.0, 101.5) == []
    book.close_bar(T0 + 2 * HOUR_MS, 105.5, False, False, 1.0)
    assert pos["stop"] == pytest.approx(104.0) and pos["stop_kind"] == "suiveur" and pos["moved"] == 2
    [exit_] = bar(book, 3, 105.0, 105.2, 103.5)
    assert exit_["reason"] == "stop suiveur" and exit_["secured"]["part"] == 0.5 and exit_["pnl"] > event["pnl"]


def test_securing_belongs_to_the_settings_not_to_the_name_of_the_bot():
    plain, safe = spec("Cassure 20/10", "long", 2.0), spec("Cassure 20/10", "long", 2.0, secure_r=1.0, secure_part=0.5)
    assert safe.key == plain.key == "X/USDT|1h|Cassure 20/10|long|2"
    assert with_security(plain, 1.0, 0.5) == safe and with_security(safe, 0.0, 0.5) == plain
    old = {"section": "court", "symbol": "X/USDT", "timeframe": "1h", "technique": "Cassure 20/10", "side": "long",
           "target_r": 2.0, "leverage": 3.0}
    assert spec_from(old) == plain and spec_from({**old, "secure_r": 1.0, "secure_part": 0.5}) == safe
    assert "Sécurisation" not in exit_rule(plain)
    assert "il encaisse 50 % de sa position" in exit_rule(safe) and "1 fois la distance de son stop" in exit_rule(safe)
    assert "encaisse" not in exit_rule(spec(secure_r=1.5)) and "1,5 fois" in exit_rule(spec(secure_r=1.5))
    for bad in ({"secure_r": -1.0}, {"secure_part": 0.95}, {"secure_part": -0.1}, {"secure_r": math.inf}):
        with pytest.raises(ValueError):
            spec(**bad)


def test_an_open_position_is_shown_at_what_closing_it_now_would_give():
    """La valeur affichée d'une position compte les frais de sa sortie : elle ne paraît pas plus belle qu'elle n'est."""
    book, entry, sign = secured_trade("long")
    qty, price = entry["qty"], entry["price"]
    view = _position_view(book, 101.0)
    exit_cost = qty * 101.0 * (FUTURES.fee_rate + FUTURES.slippage)
    assert view["pnl"] == pytest.approx(qty * (101.0 - price) - 3000.0 * FUTURES.fee_rate - exit_cost)
    assert book.value(101.0) == pytest.approx(book.equity(101.0) - exit_cost) and book.value(None) == book.s["cash"]
    assert (view["secure"], view["part"], view["secured"], view["left"], view["banked"]) == (
        pytest.approx(price + 2.0), 0.5, False, 1.0, None)
    [event] = bar(book, 1, 100.0, 102.5, 99.9)
    view = _position_view(book, 102.4)
    assert view["secured"] and view["left"] == 0.5 and view["banked"] == pytest.approx(event["pnl"])
    assert view["pnl"] == pytest.approx(event["pnl"] + (qty / 2) * (102.4 - price) - 3000.0 * FUTURES.fee_rate / 2
                                        - (qty / 2) * 102.4 * (FUTURES.fee_rate + FUTURES.slippage))
    assert view["notional"] == pytest.approx(3000.0)  # la taille de l'entrée ; `left` dit ce qui reste ouvert


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("exit_", EXITS)
def test_with_securing_the_account_still_adds_up_trade_by_trade(random_walk, side, exit_):
    """Sur des milliers de bougies : le capital final est le capital de départ plus la somme des trades, chaque trade
    sécurisé est compté une fois, et sa taille reste celle de l'entrée."""
    target, mode = exit_
    for name in ("Cassure 20/10", "Croisement MM 20/100", "Repli RSI(2) < 10 sans filtre"):
        s = spec(name, side, target, 3.0, stop_mode=mode, secure_r=1.0, secure_part=0.5)
        book = simulate(random_walk, s)
        trades = book.s["trades"]
        assert book.s["cash"] == pytest.approx(CAPITAL + sum(t["pnl"] for t in trades))
        assert book.s["count"] == len(trades) and book.position is None
        assert all(t["net"] == pytest.approx(t["pnl"] / t["notional"]) for t in trades)
        assert all(t["notional"] == pytest.approx(t["qty"] * t["price"]) for t in trades)
        plain = simulate(random_walk, with_security(s, 0.0, 0.0))
        assert all("secured" not in t for t in plain.s["trades"])
    assert any((t.get("secured") or {}).get("part") for t in trades)  # RSI(2) : beaucoup de trades, certains sécurisés


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
    un stop ou un objectif mal compté la ferait sortir de la fourchette. La sécurisation des gains ne crée aucun
    avantage : elle remplace seulement, pour la part encaissée, une sortie au marché par un ordre limite moins cher."""
    df = fair_market()
    names = ("Cassure 20/10", "Repli RSI(2) < 10 sans filtre", "Bollinger rebond 20/2 sans filtre", "Supertrend 10/3",
             "EMA 9/21", "MACD 12/26/9", "Stochastique 14/3", "Keltner 20/2", "Parabolic SAR", "Heikin-Ashi 2 bougies",
             "Momentum 28", "Écart à la moyenne 20/2")
    nets = {(exit_, secured): [] for exit_ in EXITS for secured in (False, True)}
    gross = {False: [], True: []}
    cashed = 0
    for name in names:
        for side in SIDES:
            signals = signals_for(df, technique(name), side)
            for target, mode in EXITS:
                for secured in (False, True):
                    bot = Spec("scalping", "X/USDT", "1m", name, side, target, 5.0, mode, *((1.0, 0.5) if secured else ()))
                    book = simulate(df, bot, signals=signals)
                    assert book.s["dead"] != "liquidé"  # le stop passe avant la liquidation (mais les frais ruinent)
                    done = [t for t in book.s["trades"] if t["reason"] != "fin du test"]
                    nets[((target, mode), secured)] += [t["net"] for t in done]
                    gross[secured] += [t["gross"] for t in done]
                    cashed += sum(1 for t in done if (t.get("secured") or {}).get("part"))
    plain = [x for (_, secured), xs in nets.items() if not secured for x in xs]
    safe = [x for (_, secured), xs in nets.items() if secured for x in xs]
    assert len(plain) > 30_000 and len(safe) > 30_000 and all(len(xs) > 8_000 for xs in nets.values())
    assert cashed > 5_000  # la sécurisation a vraiment joué
    assert -0.00143 < np.mean(plain) < -0.00131  # le prix des frais, à 0,006 % près
    by_rule = np.mean(nets[((0.0, "fixe"), False)])  # sortie par la règle ou par le stop : toujours au marché
    assert -0.00145 < by_rule < -0.00132
    for key, xs in nets.items():  # aucune façon de sortir ne gagne ni ne perd plus que ses frais
        assert -0.00146 < np.mean(xs) < -0.00118, key
    # Avant frais, rien à gagner avec ou sans sécurisation : le hasard ne se laisse pas « sécuriser ».
    assert abs(np.mean(gross[False])) < 0.00008 and abs(np.mean(gross[True])) < 0.00008
    # Après frais, la sécurisation coûte un peu moins cher (une demi-sortie en ordre limite), jamais plus : au mieux
    # la moitié de l'écart entre une sortie au marché (0,07 %) et un ordre limite (0,02 %).
    assert 0 < np.mean(safe) - np.mean(plain) < 0.00025
    assert 0.2 < np.mean(np.array(plain) > 0) < 0.45  # et bien moins d'un trade sur deux est gagnant
    assert np.mean(np.array(safe) > 0) > np.mean(np.array(plain) > 0)  # plus de petits gains, pas plus d'argent


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
