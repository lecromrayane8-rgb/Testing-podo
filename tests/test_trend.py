"""Le bot de tendance : la règle, l'argent (ordres, frais, parts), le « direct » qui est le backtest qui continue, le
test de robustesse et la relève des bougies. Les chiffres attendus sont refaits à la main dans chaque test."""
import inspect
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingbot import trend
from tradingbot.data import COLUMNS
from tradingbot.execution import FUTURES
from tradingbot.robustness import ROBUST

DAY = trend.DAY_MS
FEE, SLIP = trend.SPOT.fee_rate, trend.SPOT.slippage
NIGHT = 3 * FUTURES.funding_rate_8h  # les intérêts d'une nuit sur l'argent emprunté : 0,03 %
MARGIN = trend.MAINTENANCE


def days(closes, opens=None, start=0):
    """Des bougies d'un jour. Sans `opens` : chaque jour ouvre à la clôture de la veille (marché continu)."""
    closes = np.asarray(closes, dtype=float)
    opens = np.concatenate(([closes[0]], closes[:-1])) if opens is None else np.asarray(opens, dtype=float)
    return pd.DataFrame({"ts": start + np.arange(len(closes), dtype="int64") * DAY, "open": opens,
                         "high": np.maximum(opens, closes), "low": np.minimum(opens, closes), "close": closes,
                         "volume": 1.0})


def walk(seed, n, drift=0.0, vol=0.03):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))


# --- la règle -----------------------------------------------------------------------------------------------------

def test_an_average_is_made_of_its_own_closes_only():
    assert trend.average(np.array([1.0, 2.0, 3.0, 4.0]), 2).tolist()[1:] == [1.5, 2.5, 3.5]
    assert math.isnan(trend.average(np.array([1.0, 2.0, 3.0, 4.0]), 2)[0])
    assert np.isnan(trend.average(np.array([1.0, 2.0]), 3)).all()  # pas assez de jours : pas de moyenne
    closes = walk(1, 500)
    for n in trend.AVERAGES:  # la fenêtre du direct (les derniers jours seulement) voit exactement la même moyenne
        assert trend.average(closes[-n:], n)[-1] == trend.average(closes, n)[-1]


def test_the_rule_counts_the_averages_under_the_close():
    closes = [10, 10, 10, 10, 12, 11, 9, 9.5]
    # moyenne 2 jours : -, 10, 10, 10, 11, 11.5, 10, 9.25 ; moyenne 4 jours : -, -, -, 10, 10.5, 10.75, 10.5, 10.375
    assert trend.levels(closes, (2, 4)).tolist() == [-1, -1, -1, 0, 2, 1, 0, 1]
    # avant que la plus longue moyenne existe, le bot ne décide rien ; une clôture égale à sa moyenne ne compte pas
    assert trend.levels([5, 5, 5], (2, 3)).tolist() == [-1, -1, 0]


def test_tonight_threshold_is_the_price_the_close_must_beat():
    closes = walk(2, 320)
    marks = trend.thresholds(closes)
    assert len(marks) == 3 and all(m > 0 for m in marks)
    for price in [*np.linspace(0.5 * min(marks), 1.5 * max(marks), 41), *[m * (1 + e) for m in marks for e in (-1e-6, 1e-6)]]:
        assert trend.levels(np.append(closes, price))[-1] == sum(price > m for m in marks)
    assert trend.thresholds(closes[:60]) == [float(closes[11:60].mean()), None, None]  # pas assez de jours : pas de seuil


# --- l'argent : ordres, frais, parts ---------------------------------------------------------------------------------

def test_an_order_goes_at_the_next_open_with_fee_and_slippage():
    closes = [10, 10, 10, 10, 12, 11, 9, 9.5]  # décisions : -, -, -, 0, 2, 1, 0, 1 (test de la règle ci-dessus)
    run = trend.replay(days(closes), capital=1000.0, averages=(2, 4))
    assert [(o["ts"] // DAY, o["side"], o["from"], o["to"], o["price"]) for o in run.orders] == [
        (5, "achat", 0, 2, 12.0),  # décidé à la clôture du jour 4, passé à l'ouverture du jour 5 (la clôture du 4)
        (6, "vente", 2, 1, 11.0),  # une moyenne repassée au-dessus du prix : la moitié est vendue
        (7, "vente", 1, 0, 9.0)]
    bought = 1000 * (1 - FEE) / (12 * (1 + SLIP))  # frais pris sur la somme, prix payé plus cher
    half = bought / 2
    cash = half * 11 * (1 - SLIP) * (1 - FEE)  # vendu moins cher, frais pris sur ce que la vente rapporte
    final = cash + half * 9 * (1 - SLIP) * (1 - FEE)
    assert run.orders[0]["units"] == pytest.approx(bought, rel=1e-12)
    assert run.orders[1]["units"] == pytest.approx(half, rel=1e-12)
    assert run.cash == pytest.approx(final, rel=1e-12) and run.qty == 0.0
    assert run.ts.tolist() == [4 * DAY, 5 * DAY, 6 * DAY, 7 * DAY]  # le compte ouvre quand toutes les moyennes existent
    assert run.value.tolist() == pytest.approx([1000.0, bought * 11, cash + half * 9, final], rel=1e-12)
    assert run.level.tolist() == [0, 2, 1, 0]
    assert run.decided == 1  # la dernière clôture décide : une part dès demain


def test_on_a_market_that_goes_nowhere_the_rule_gives_back_exactly_its_costs():
    closes = [100, 100] + [102, 98] * 10 + [98]  # la moyenne 2 jours est franchie chaque jour, dans un sens puis l'autre
    run = trend.replay(days(closes, opens=[100] * len(closes)), capital=1000.0, averages=(2,))
    assert [o["side"] for o in run.orders] == ["achat", "vente"] * 10  # 10 allers-retours, tous passés à 100
    round_trip = (1 - FEE) ** 2 * (1 - SLIP) / (1 + SLIP)
    assert run.cash == pytest.approx(1000 * round_trip ** 10, rel=1e-12)
    assert sum(o["cost"] for o in run.orders) == pytest.approx(1000 - run.cash, rel=1e-9)  # rien d'autre que les frais
    assert 1 - round_trip == pytest.approx(0.003, abs=1e-5)  # un aller-retour au comptant : 0,30 %
    assert run.hold[-1] == pytest.approx(1000 * (1 - FEE) / (1 + SLIP) * 0.98, rel=1e-12)  # garder : les frais de l'achat


def test_the_account_holds_one_share_per_average_and_never_borrows():
    df = days(walk(3, 500))
    run = trend.replay(df, averages=(5, 10, 20))
    assert len(run.orders) > 50
    for o in run.orders:
        assert 0 <= o["to"] <= 3 and o["to"] != o["from"] and o["cash"] >= 0 and o["qty"] >= 0 and o["cost"] > 0
        assert o["qty"] * o["price"] / o["value"] == pytest.approx(o["to"] / 3, abs=0.002)  # la part visée, aux frais près
        if o["to"] == 0:
            assert o["qty"] == 0.0  # dehors : plus aucune crypto
        if o["to"] == 3:
            assert o["cash"] == 0.0  # dedans en entier : tout l'argent, jamais plus (pas de levier)
    assert set(run.level.tolist()) <= {0, 1, 2, 3} and (run.value > 0).all()
    assert (np.diff(run.level) != 0).sum() + (run.level[0] != 0) == len(run.orders)  # un ordre seulement quand la part change


def test_growth_and_worst_drop_count_from_the_starting_money():
    g = trend.growth(np.array([110.0, 99.0, 120.0]), 100.0)
    assert g["total"] == pytest.approx(1.2) and g["worst"] == pytest.approx(99 / 110 - 1)
    assert g["yearly"] == pytest.approx(1.2 ** (365 / 3) - 1)
    assert trend.worst(np.array([90.0, 95.0]), 100.0) == pytest.approx(-0.10)  # la baisse depuis la mise de départ compte
    assert trend.worst(np.array([101.0, 102.0]), 100.0) == 0.0


def test_the_years_chain_up_to_the_whole_period():
    start = int(datetime(2020, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)
    run = trend.replay(days(walk(4, 900, drift=0.001), start=start), averages=(5, 10, 20))
    years = trend.by_year(run)
    assert [y["year"] for y in years] == [2020, 2021, 2022, 2023] and sum(y["days"] for y in years) == len(run)
    assert np.prod([1 + y["rule"] for y in years]) == pytest.approx(run.value[-1] / run.capital, rel=1e-12)
    assert np.prod([1 + y["hold"] for y in years]) == pytest.approx(run.hold[-1] / run.capital, rel=1e-12)
    assert all(y["rule_worst"] <= 0 and y["hold_worst"] <= 0 for y in years)


# --- le direct est le backtest qui continue -----------------------------------------------------------------------------

def test_adding_days_never_changes_an_order_already_passed():
    df = days(walk(5, 700))
    whole = trend.replay(df)
    assert len(whole.orders) > 20
    for k in (201, 260, 333, 480, 699):
        part = trend.replay(df.iloc[:k])
        assert part.orders == [o for o in whole.orders if o["ts"] < df["ts"].iloc[k]]
        assert part.value.tolist() == whole.value[:len(part)].tolist()
        assert part.level.tolist() == whole.level[:len(part)].tolist()


def test_the_paper_account_is_the_backtest_that_goes_on_day_after_day():
    df = days(walk(6, 520, drift=0.002))
    start = int(df["ts"].iloc[300]) + 5 * 3600_000  # compte créé dans la journée 300 : il ouvre au jour 301
    final = trend.replay(df, start_ts=start)
    assert final.ts[0] == df["ts"].iloc[301] and len(final) == 219
    for k in range(302, 521, 7):  # ce que le site a montré chaque semaine (redémarrages compris) : le même compte
        seen = trend.replay(df.iloc[:k], start_ts=start)
        assert seen.orders == [o for o in final.orders if o["ts"] < df["ts"].iloc[k - 1] + DAY]
        assert seen.value.tolist() == final.value[:len(seen)].tolist()
    assert final.hold[0] == pytest.approx(1000 * (1 - FEE) / (df["open"].iloc[301] * (1 + SLIP)) * df["close"].iloc[301])


def test_an_account_created_in_a_trend_buys_at_its_first_open_and_not_before():
    df = days(np.linspace(100, 400, 320))  # une hausse régulière : le prix est au-dessus de ses trois moyennes
    start = int(df["ts"].iloc[250]) + 1
    run = trend.replay(df, start_ts=start)
    assert run.orders[0]["ts"] == df["ts"].iloc[251] and (run.orders[0]["from"], run.orders[0]["to"]) == (0, 3)
    assert run.orders[0]["price"] == df["open"].iloc[251] and len(run.orders) == 1
    waiting = trend.replay(df, start_ts=int(df["ts"].iloc[-1]) + 1)  # créé aujourd'hui : il ouvre demain
    assert len(waiting) == 0 and waiting.orders == [] and waiting.cash == 1000.0 and waiting.decided == 3
    assert len(trend.replay(df.iloc[:200])) == 0  # sans tout son historique, le bot ne fait rien


def test_the_day_in_progress_never_decides_an_order():
    df = days(walk(7, 400))
    base = trend.replay(df)
    for factor in (0.5, 2.0):  # le prix du moment bouge : aucun ordre passé ne change, seule la décision du soir
        moved = df.copy()
        moved.loc[moved.index[-1], "close"] *= factor
        run = trend.replay(moved)
        assert run.orders == base.orders and run.level.tolist() == base.level.tolist()
        assert run.value[:-1].tolist() == base.value[:-1].tolist()
        assert run.decided == (0 if factor < 1 else 3)


# --- les comptes à risque : levier, intérêts, liquidation, stop suiveur ---------------------------------------------------

def test_without_leverage_or_stop_the_account_never_borrows_and_pays_no_interest():
    run = trend.replay(days(walk(20, 900)))
    assert len(run.orders) > 50 and all(o["cash"] >= 0 and o["why"] == "regle" for o in run.orders)
    assert run.paid == 0.0 and run.dead is None and run.allowed


def test_a_leveraged_account_holds_twice_the_share_and_pays_interest_on_what_it_borrows():
    closes = [100, 100, 110, 121, 121, 121]  # moyenne 2 jours : décisions -, 0, 1, 1, 0, 0
    run = trend.replay(days(closes), capital=1000.0, averages=(2,), leverage=2.0)
    assert [(o["ts"] // DAY, o["side"], o["why"], o["price"]) for o in run.orders] == [
        (3, "achat", "regle", 110.0), (5, "vente", "regle", 121.0)]
    units = 2000 * (1 - FEE) / (110 * (1 + SLIP))  # il achète pour le double de sa valeur : 1 000 à lui, 1 000 empruntés
    assert run.orders[0]["amount"] == pytest.approx(2000) and run.orders[0]["cash"] == pytest.approx(-1000)
    assert run.orders[0]["units"] == pytest.approx(units, rel=1e-12)
    debt = 1000 * (1 + NIGHT)  # une nuit d'intérêts avant l'ouverture du jour 4
    assert run.value.tolist() == pytest.approx([1000.0, units * 121 - 1000, units * 121 - debt,
                                                units * 121 * (1 - SLIP) * (1 - FEE) - debt * (1 + NIGHT)], rel=1e-12)
    assert run.paid == pytest.approx(1000 * NIGHT + debt * NIGHT, rel=1e-12) and run.cash == pytest.approx(run.value[-1])
    assert run.qty == 0.0 and run.dead is None
    plain = trend.replay(days(closes), capital=1000.0, averages=(2,))  # le compte normal, sur les mêmes jours
    assert run.value[1] - 1000 == pytest.approx(2 * (plain.value[1] - 1000), rel=1e-9)  # le double du gain, frais compris
    assert plain.paid == 0.0


def test_a_borrowing_account_is_brought_back_to_its_leverage_only_beyond_the_band():
    closes = [100, 100, 110, 130, 135, 150]  # le prix monte : la règle reste « dedans », la position dérive
    run = trend.replay(days(closes), capital=1000.0, averages=(2,), leverage=2.0)
    assert [(o["ts"] // DAY, o["why"]) for o in run.orders] == [(3, "regle"), (4, "levier")]  # rien au jour 5
    units = 2000 * (1 - FEE) / (110 * (1 + SLIP))
    value = units * 130 - 1000 * (1 + NIGHT)  # à l'ouverture du jour 4 : la position ne fait plus que 1,74 fois le compte
    assert units * 130 / value == pytest.approx(1.7356, abs=1e-4) and abs(units * 130 / value - 2) > 2 * trend.BAND
    again = run.orders[1]
    assert again["side"] == "achat" and again["amount"] == pytest.approx(2 * value - units * 130, rel=1e-12)
    assert again["qty"] * 130 / again["value"] == pytest.approx(2.0, abs=0.002)  # remis à ×2, aux frais près
    assert again["qty"] * 135 / (again["cash"] * (1 + NIGHT) + again["qty"] * 135) == pytest.approx(1.93, abs=0.01)  # dans la bande


def crash(low, open_=121.0):
    """Le compte à levier du test ci-dessus, puis un jour 4 dont le plus bas (ou l'ouverture) plonge."""
    df = days([100, 100, 110, 121, 100, 130, 140, 150])
    df.loc[df.index[4], ["open", "low"]] = [open_, min(low, open_)]
    return df, trend.replay(df, capital=1000.0, averages=(2,), leverage=2.0)


def test_a_leveraged_account_is_liquidated_when_its_value_no_longer_covers_its_position():
    units, debt = 2000 * (1 - FEE) / (110 * (1 + SLIP)), 1000 * (1 + NIGHT)
    limit = debt / (units * (1 - MARGIN))  # sous ce prix, ce qui reste au compte ne couvre plus la marge de maintenance
    assert limit == pytest.approx(55.37, abs=0.01)
    df, dead = crash(limit - 0.01)
    assert dead.dead == df["ts"].iloc[4] and dead.value.tolist()[2:] == [0.0] * 4  # liquidé : zéro, et pour toujours
    assert dead.orders[-1]["side"] == "liquidation" and dead.orders[-1]["price"] == pytest.approx(limit, rel=1e-12)
    assert len(dead.orders) == 2 and dead.cash == 0.0 and dead.qty == 0.0 and dead.level.tolist()[2:] == [0] * 4
    _, alive = crash(limit + 0.01)  # un centime au-dessus : il survit, et la règle continue
    assert alive.dead is None and alive.value[2] == pytest.approx(units * 100 - debt, rel=1e-12) and len(alive.orders) > 2
    _, gap = crash(60.0, open_=50.0)  # une ouverture déjà sous le prix de liquidation : liquidé à l'ouverture
    assert gap.dead is not None and gap.orders[-1]["price"] == 50.0 and gap.value[2] == 0.0
    growth = trend.growth(dead.value, dead.capital)
    assert growth["total"] == 0.0 and growth["worst"] == -1.0 and growth["yearly"] == -1.0


def test_on_a_market_that_goes_nowhere_a_leveraged_account_gives_back_its_costs_and_its_interest():
    closes = [100, 100] + [102, 98] * 10 + [98]
    run = trend.replay(days(closes, opens=[100] * len(closes)), capital=1000.0, averages=(2,), leverage=2.0)
    assert [o["side"] for o in run.orders] == ["achat", "vente"] * 10 and run.dead is None
    value, paid = 1000.0, 0.0
    for _ in range(10):  # acheter le double à 100, payer une nuit d'intérêts sur l'emprunt, tout revendre à 100
        units = 2 * value * (1 - FEE) / (100 * (1 + SLIP))
        paid += value * NIGHT
        value = units * 100 * (1 - SLIP) * (1 - FEE) - value * (1 + NIGHT)
    assert run.cash == pytest.approx(value, rel=1e-12) and run.paid == pytest.approx(paid, rel=1e-12)
    assert value / 1000 == pytest.approx((2 * (1 - FEE) ** 2 * (1 - SLIP) / (1 + SLIP) - 1 - NIGHT) ** 10, rel=1e-12)


def test_the_trailing_stop_sits_three_average_candles_under_the_high_of_the_last_22_days():
    closes = np.array([100.0] * 30 + [90.0] * 30)
    high, low = closes + 1, closes - 1
    line = trend.stop_line(high, low, closes)
    assert np.isnan(line[:22]).all() and line[22] == pytest.approx(101 - 3 * 2)  # bougie moyenne : 2 ; plus haut : 101
    assert line[30] == pytest.approx(101 - 3 * (21 * 2 + 11) / 22)  # le jour de la chute : une bougie de 11
    allows = trend.stop_allows(high, low, closes)
    assert allows[:30].all() and not allows[30:51].any()  # sous la ligne : dehors, tant que l'ancien sommet compte
    assert allows[52:].all() and line[59] == pytest.approx(91 - 3 * 2)  # 22 jours plus tard, la ligne est redescendue
    assert trend.stop_allows(high[:5], low[:5], closes[:5]).all()  # pas assez de jours : le stop ne dit rien
    wild = walk(21, 400)
    h, lo = wild * 1.02, wild * 0.97
    for k in (40, 150, 399):  # aucune valeur ne dépend de l'historique chargé avant ses 23 derniers jours
        assert trend.stop_line(h[k - 30:k + 1], lo[k - 30:k + 1], wild[k - 30:k + 1])[-1] == trend.stop_line(h, lo, wild)[k]
        assert trend.stop_allows(h[:k + 1], lo[:k + 1], wild[:k + 1]).tolist() == trend.stop_allows(h, lo, wild)[:k + 1].tolist()


def test_the_stop_takes_the_account_out_at_the_next_open_and_brings_it_back_when_the_line_allows():
    closes = np.concatenate([100 + 0.1 * np.arange(40), 85 + 0.1 * np.arange(40)])  # monte, chute de 19, remonte
    df = days(closes)
    plain = trend.replay(df, averages=(2,))
    stopped = trend.replay(df, averages=(2,), stop=True)
    assert [(o["ts"] // DAY, o["side"]) for o in plain.orders] == [(2, "achat"), (41, "vente"), (42, "achat")]
    # la règle revient dès le jour 42 (le prix remonte) ; le stop, lui, garde le compte dehors sous sa ligne
    assert [(o["ts"] // DAY, o["side"], o["why"]) for o in stopped.orders][:2] == [(2, "achat", "regle"), (41, "vente", "stop")]
    back = stopped.orders[2]
    allows = trend.stop_allows(df["high"], df["low"], df["close"])
    first_ok = int(np.flatnonzero(allows[41:])[0]) + 41  # la première clôture que le stop laisse passer après la chute
    assert first_ok > 50 and (back["ts"] // DAY, back["side"], back["why"]) == (first_ok + 1, "achat", "stop")
    assert back["price"] == df["open"].iloc[first_ok + 1] and (back["from"], back["to"]) == (0, 1)
    out = slice(41 - 2, first_ok + 1 - 2)  # le compte ouvre au jour 2 : du jour 41 au jour first_ok, il ne tient rien
    assert stopped.level[out].sum() == 0 and stopped.level[first_ok + 1 - 2] == 1 and plain.level[out].sum() > 0
    assert not allows[40] and stopped.allowed and len(stopped.orders) == 3


def wicked(seed, n):
    """Un marché au hasard avec de vraies mèches (le stop suiveur regarde les plus hauts et les plus bas)."""
    df = days(walk(seed, n))
    rng = np.random.default_rng(seed)
    df["high"] = df[["open", "close"]].max(axis=1) * (1 + rng.uniform(0, 0.02, n))
    df["low"] = df[["open", "close"]].min(axis=1) * (1 - rng.uniform(0, 0.02, n))
    return df


@pytest.mark.parametrize("variant", trend.VARIANTS, ids=lambda v: v.key)
def test_no_account_ever_rewrites_its_past_or_lets_the_day_in_progress_decide(variant):
    df = wicked(22, 700)
    play = lambda frame, **kw: trend.replay(frame, leverage=variant.leverage, stop=variant.stop, **kw)  # noqa: E731
    whole = play(df)
    assert len(whole.orders) > 20
    for k in (201, 333, 480, 699):  # ajouter des jours ne change aucun ordre déjà passé
        part = play(df.iloc[:k])
        assert part.orders == [o for o in whole.orders if o["ts"] < df["ts"].iloc[k]]
        assert part.value.tolist() == whole.value[:len(part)].tolist() and part.paid <= whole.paid
    start = int(df["ts"].iloc[400]) + 1  # le compte fictif créé au jour 400 : le même, vu jour après jour
    final = play(df, start_ts=start)
    assert play(df.iloc[:600], start_ts=start).value.tolist() == final.value[:199].tolist()
    moved = df.copy()  # le prix du moment bouge : aucun ordre passé ne change
    moved.loc[moved.index[-1], ["high", "close"]] *= 1.5
    assert play(moved).orders == whole.orders and play(moved).value[:-1].tolist() == whole.value[:-1].tolist()


def test_the_four_accounts_are_the_same_rule_with_or_without_leverage_and_stop():
    assert [(v.key, v.leverage, v.stop) for v in trend.VARIANTS] == [
        ("normal", 1.0, False), ("stop", 1.0, True), ("risque", 2.0, False), ("risque_stop", 2.0, True)]
    df = wicked(23, 900)
    runs = {v.key: trend.replay(df, leverage=v.leverage, stop=v.stop) for v in trend.VARIANTS}
    assert runs["normal"].paid == runs["stop"].paid == 0.0 and runs["risque"].paid > 0
    assert (runs["stop"].level <= runs["normal"].level).all()  # le stop ne fait jamais tenir plus que la règle
    assert {o["why"] for o in runs["risque_stop"].orders} <= {"regle", "stop", "levier", "liquidation"}
    assert {o["why"] for o in runs["normal"].orders} == {"regle"}


# --- le test de robustesse : chaque sortie contre « garder » ----------------------------------------------------------

def test_an_exit_is_judged_in_coins_against_holding():
    closes = [100, 100, 110, 100, 80, 85, 90, 80, 95, 96]  # moyenne 2 jours : décisions -, 0, 1, 0, 0, 1, 1, 0, 1, 1
    opens = [100, 100, 100, 110, 100, 80, 80, 90, 80, 96]
    run = trend.replay(days(closes, opens), averages=(2,))
    assert [(o["ts"] // DAY, o["side"], o["price"]) for o in run.orders] == [
        (3, "achat", 110.0), (4, "vente", 100.0), (6, "achat", 80.0), (8, "vente", 80.0), (9, "achat", 96.0)]
    won, lost = trend.exits(run)
    cost = (1 - SLIP) * (1 - FEE) ** 2 / (1 + SLIP)  # une vente puis un rachat
    assert won["ret"] == pytest.approx(100 / 80 * cost - 1, rel=1e-12) and not won["open"]  # racheté 20 % moins cher
    assert lost["ret"] == pytest.approx(80 / 96 * cost - 1, rel=1e-12)  # racheté plus cher : garder aurait mieux fait
    result = trend.as_backtest(run)
    assert [t.return_pct for t in result.trades] == pytest.approx([math.log1p(won["ret"]), math.log1p(lost["ret"])])
    assert result.metrics["taux_reussite"] == 0.5
    assert result.metrics["rendement_total"] == pytest.approx(run.value[-1] / run.hold[-1] - 1)
    # la sortie en cours est comptée au prix du moment, frais du rachat compris
    out = trend.replay(days([100, 100, 110, 100, 80, 85, 90, 80, 80, 76], [100, 100, 100, 110, 100, 80, 80, 90, 80, 80]),
                       averages=(2,))
    last = trend.exits(out)[-1]
    assert last["open"] and last["ret"] == pytest.approx(80 / 76 * cost - 1, rel=1e-12)
    with pytest.raises(ValueError, match="moyenne par moyenne"):
        trend.exits(trend.replay(days(closes, opens), averages=(2, 3)))


def test_on_a_market_without_edge_the_exits_give_back_their_costs_and_nothing_is_called_robust():
    logs, plain, frames = [], [], {}
    for seed in range(60):  # des marches au hasard sans dérive : sortir puis revenir ne peut rien rapporter
        df = days(walk(seed, 12_000, vol=0.035))
        if seed < 2:
            frames[f"X{seed}/USDT"] = df.iloc[:3400]
        for n in trend.AVERAGES:
            rets = np.array([e["ret"] for e in trend.exits(trend.replay(df, averages=(n,)))])
            logs.append(np.log1p(rets))
            plain.append(rets)
    logs, plain = np.concatenate(logs), np.concatenate(plain)
    assert len(logs) > 50_000
    assert -0.006 < logs.mean() < 0  # les frais d'une vente et d'un rachat (−0,30 %), au hasard près (± 0,1 %)
    assert plain.mean() > 0.005  # la moyenne simple, elle, annonce un gain qui n'existe pas : elle ne sert pas de juge
    rows = trend.robustness_rows(frames)
    assert [r.market for r in rows] == ["X0 moy. 50 j", "X0 moy. 100 j", "X0 moy. 200 j",
                                        "X1 moy. 50 j", "X1 moy. 100 j", "X1 moy. 200 j"]
    assert all(r.verdict != ROBUST for r in rows)
    assert trend.verdict(rows).startswith("Aucune des 6 lignes n'est « robuste »") and "Argent fictif seulement" in trend.verdict(rows)
    proven = [rows[0].__class__(**{**rows[0].__dict__, "verdict": ROBUST}), *rows[1:]]
    assert trend.verdict(proven).startswith("1 ligne(s) sur 6 sont « robustes » : X0 moy. 50 j") and "fictif" in trend.verdict(proven)
    assert trend.verdict([]) == "Pas assez d'historique pour juger la règle."
    first = trend.as_backtest(trend.replay(frames["X0/USDT"], averages=(50,)))
    assert rows[0].nb_trades == len(first.trades) and rows[0].expectancy_pct == pytest.approx(first.metrics["esperance_pct"])


# --- la relève des bougies ---------------------------------------------------------------------------------------------

class DailyExchange:
    """Une plateforme fictive : `n` bougies d'un jour visibles, dont la dernière est celle du jour en cours (sa clôture
    provisoire bouge encore). `page` : le nombre de bougies qu'elle rend au plus par demande."""

    def __init__(self, frames, n, page=1000):
        self.frames, self.n, self.page, self.calls, self.down, self.wobble = frames, n, page, [], False, 1.0

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        assert timeframe == "1d"
        if self.down:
            raise ConnectionError("hors ligne")
        self.calls.append((symbol, since))
        df = self.frames[symbol].iloc[:self.n]
        rows = df[df["ts"] >= (since or 0)].iloc[:min(limit or self.page, self.page)][COLUMNS].values.tolist()
        if rows and rows[-1][0] == df["ts"].iloc[-1]:
            rows[-1][4] *= self.wobble  # le jour n'est pas fini : son dernier prix n'est pas sa clôture
        return rows


def feed_on(tmp_path, exchange, **kwargs):
    return trend.Feed(lambda exchange_id: exchange, "fictive", tmp_path / "tendance", every=0.0, since_ms=0, **kwargs)


def test_the_feed_keeps_finished_days_and_never_takes_the_day_in_progress_for_a_close(tmp_path):
    df = days(walk(8, 300))
    exchange = DailyExchange({"BTC/USDT": df}, n=250)
    exchange.wobble = 1.5
    feed = feed_on(tmp_path, exchange)
    got = feed.get("BTC/USDT")
    assert got.live and got.error is None and len(got.df) == 250
    assert got.df["close"].iloc[-1] == pytest.approx(1.5 * df["close"].iloc[249])  # le prix du moment
    saved = pd.read_csv(feed.path("BTC/USDT"), float_precision="round_trip")
    assert len(saved) == 249 and saved["close"].tolist() == df["close"].iloc[:249].tolist()  # seulement les jours finis
    exchange.n = 252  # deux jours plus tard : seuls les derniers jours sont redemandés
    exchange.calls.clear()
    got = feed.get("BTC/USDT")
    assert exchange.calls == [("BTC/USDT", int(df["ts"].iloc[248]))]
    assert len(got.df) == 252 and got.df["close"].iloc[249] == df["close"].iloc[249]  # la vraie clôture a remplacé le prix
    saved = pd.read_csv(feed.path("BTC/USDT"), float_precision="round_trip")
    assert saved["close"].tolist() == df["close"].iloc[:251].tolist()


def test_the_feed_survives_a_restart_without_network_and_says_so(tmp_path):
    df = days(walk(9, 300))
    exchange = DailyExchange({"ETH/USDT": df}, n=280)
    assert feed_on(tmp_path, exchange).get("ETH/USDT").live
    exchange.down = True
    again = feed_on(tmp_path, exchange).get("ETH/USDT")  # un autre lancement, réseau coupé : les jours finis sont là
    assert not again.live and "hors ligne" in again.error and len(again.df) == 279 and again.asof is None
    assert again.df["close"].tolist() == df["close"].iloc[:279].tolist()
    nothing = feed_on(tmp_path / "vide", exchange).get("ETH/USDT")  # jamais rien reçu : rien à montrer, pas de plantage
    assert nothing.df is None and not nothing.live and nothing.error


def test_the_feed_reads_the_whole_history_from_a_platform_that_gives_it_page_by_page(tmp_path):
    df = days(walk(10, 2300))
    exchange = DailyExchange({"BTC/USDT": df}, n=2300, page=300)
    got = feed_on(tmp_path, exchange).get("BTC/USDT")
    assert len(got.df) == 2300 and got.df["ts"].tolist() == df["ts"].tolist()
    assert len(exchange.calls) == 9  # 8 pages, puis une demande vide : la plateforme n'a plus rien
    quiet = feed_on(tmp_path, exchange)
    exchange.calls.clear()
    assert len(quiet.get("BTC/USDT").df) == 2300 and len(exchange.calls) == 1  # ensuite : une seule petite demande
    assert len(quiet.get("BTC/USDT").df) == 2300  # et rien ne rétrécit quand la plateforme ne donne rien de nouveau


# --- le compte fictif et la page du site --------------------------------------------------------------------------------

def test_the_account_start_is_written_once_and_never_moves(tmp_path):
    first = trend.account_since(tmp_path, datetime(2026, 11, 14, 15, 2, tzinfo=timezone.utc))
    assert first == int(datetime(2026, 11, 14, 15, 2, tzinfo=timezone.utc).timestamp() * 1000)
    assert trend.account_since(tmp_path, datetime(2027, 1, 1, tzinfo=timezone.utc)) == first
    (tmp_path / trend.ACCOUNT_FILE).write_text("{abîmé", encoding="utf-8")  # illisible : un nouveau compte, daté d'aujourd'hui
    assert trend.account_since(tmp_path, datetime(2027, 1, 1, tzinfo=timezone.utc)) > first


def page(tmp_path, exchange):
    folder = tmp_path / "tendance"
    return trend.view(feed_on(tmp_path, exchange), folder, cache={})


def test_the_page_shows_where_the_rule_stands_and_an_account_that_opens_the_next_day(tmp_path):
    start = trend.EARLY_MS
    frames = {"BTC/USDT": days(np.linspace(100, 900, 420), start=start), "ETH/USDT": days(walk(11, 420), start=start)}
    exchange = DailyExchange(frames, n=400)
    created = datetime.fromtimestamp((start + 399 * DAY + 3600_000) / 1000, timezone.utc)  # créé pendant le jour 399
    trend.account_since(tmp_path / "tendance", created)
    data = page(tmp_path, exchange)
    json.dumps(data, allow_nan=False)  # lisible par la page : ni NaN ni types numpy
    btc, eth = data["coins"]
    assert (btc["coin"], btc["name"], eth["name"]) == ("BTC", "Bitcoin", "Ether") and btc["ready"] and btc["live"]
    assert btc["level"] == 3 and btc["tonight"] == 3 and btc["since"] == start + 200 * DAY  # dedans depuis le premier jour possible
    assert [a["days"] for a in btc["averages"]] == [50, 100, 200] and all(a["above"] and a["gap"] > 0 for a in btc["averages"])
    assert btc["averages"][0]["threshold"] == pytest.approx(frames["BTC/USDT"]["close"].iloc[350:399].mean())
    assert btc["price"] == frames["BTC/USDT"]["close"].iloc[399] and btc["next_open"] == start + 400 * DAY
    assert not btc["account"]["started"] and btc["account"]["value"] == 1000.0 and btc["account"]["orders"] == []
    assert btc["history"]["orders"] == 1 and btc["history"]["rule"]["total"] > 1 and btc["history"]["inside"] == 1.0
    chart = trend.chart_view("BTC/USDT", feed_on(tmp_path, exchange).get("BTC/USDT"))
    json.dumps(chart, allow_nan=False)
    assert len(chart["candles"]) == 400 and [ln["label"] for ln in chart["lines"]] == [
        "Moyenne 50 jours", "Moyenne 100 jours", "Moyenne 200 jours", "Stop suiveur (pointillés)"]
    assert chart["lines"][3]["dash"] and chart["lines"][3]["values"][-1] < frames["BTC/USDT"]["close"].iloc[399]
    assert chart["lines"][2]["values"][:199] == [None] * 199 and chart["lines"][2]["values"][199] > 0
    assert [(o["side"], o["ts"]) for o in chart["orders"]] == [("achat", start + 200 * DAY)]
    assert data["cost"] == pytest.approx(0.0015) and data["averages"] == [50, 100, 200]
    # les quatre comptes fictifs, côte à côte : normal, avec stop suiveur, à risque, à risque avec stop
    assert [a["key"] for a in btc["accounts"]] == ["normal", "stop", "risque", "risque_stop"]
    assert btc["account"] == btc["accounts"][0] and all(not a["started"] and a["value"] == 1000.0 for a in btc["accounts"])
    assert [a["short"] for a in btc["accounts"]] == ["Normal", "Normal + stop", "Risque ×2", "Risque ×2 + stop"]
    past = {v["key"]: v for v in btc["history"]["variants"]}
    assert past["normal"]["total"] == btc["history"]["rule"]["total"] and past["normal"]["paid"] == 0.0
    assert past["risque"]["paid"] > 0 and past["risque"]["liquidated"] is None  # une hausse régulière : le levier paie, ici
    assert past["risque"]["total"] > past["normal"]["total"] > 1 and btc["stop"]["allowed"] and btc["stop"]["line"] < btc["price"]
    assert len(data["robustness"]["rows"]) == 6 and "Argent fictif seulement" in data["robustness"]["verdict"]
    exchange.n = 402  # deux jours plus tard : le compte a ouvert au jour 400, au prix d'ouverture de ce jour
    later = page(tmp_path, exchange)["coins"][0]["account"]
    assert later["started"] and later["start"] == start + 400 * DAY and later["days"] == 2 and later["level"] == 3
    (order,) = later["orders"]
    assert (order["side"], order["from"], order["to"], order["price"]) == ("achat", 0, 3, frames["BTC/USDT"]["open"].iloc[400])
    assert later["value"] == pytest.approx(1000 * (1 - FEE) / (order["price"] * (1 + SLIP)) * frames["BTC/USDT"]["close"].iloc[401])
    assert later["value"] == pytest.approx(later["hold"])  # dedans en entier dès l'ouverture : comme « acheter et garder »
    assert later["costs"] == pytest.approx(order["cost"]) and order["cost"] == pytest.approx(1000 * (1 - (1 - FEE) / (1 + SLIP)))
    risky = page(tmp_path, exchange)["coins"][0]["accounts"][2]  # le compte à risque : le double, et une nuit d'intérêts
    assert risky["started"] and risky["leverage"] == 2.0 and risky["orders"][0]["why"] == "regle" and risky["count"] == 1
    assert risky["orders"][0]["amount"] == pytest.approx(2000) and risky["paid"] == pytest.approx(1000 * NIGHT)
    assert risky["value"] - 1000 == pytest.approx(2 * (later["value"] - 1000) - 1000 * NIGHT, rel=1e-6)


def test_the_page_says_when_the_history_is_too_short_or_the_platform_silent(tmp_path):
    exchange = DailyExchange({"BTC/USDT": days(walk(12, 150)), "ETH/USDT": days(walk(13, 150))}, n=150)
    data = page(tmp_path, exchange)
    assert [c["ready"] for c in data["coins"]] == [False, False] and data["coins"][0]["days"] == 150
    assert data["robustness"]["rows"] == [] or all(r["verdict"] != ROBUST for r in data["robustness"]["rows"])
    exchange.down = True
    silent = trend.view(feed_on(tmp_path / "autre", exchange), tmp_path / "autre" / "tendance", cache={})
    assert all(not c["ready"] and "hors ligne" in c["error"] for c in silent["coins"])
    assert "pas assez de bougies" in trend.report(silent)
    with pytest.raises(ValueError, match="Pas assez de bougies"):
        trend.chart_view("BTC/USDT", feed_on(tmp_path, exchange).get("BTC/USDT"))


def test_the_console_report_tells_the_same_story_as_the_page(tmp_path):
    start = trend.EARLY_MS
    frames = {"BTC/USDT": days(walk(14, 900, drift=0.002), start=start), "ETH/USDT": days(walk(15, 900), start=start)}
    trend.account_since(tmp_path / "tendance", datetime.fromtimestamp((start + 700 * DAY) / 1000, timezone.utc))
    text = trend.report(page(tmp_path, DailyExchange(frames, n=900)))
    for words in ("Bitcoin à", "Ether à", "moyenne  50 jours : à dépasser ce soir", "Compte fictif depuis le", "acheter et garder",
                  "pire baisse", "Argent fictif : aucun ordre ne part sur une plateforme", "robustesse --tendance",
                  "Les autres comptes fictifs : Normal + stop", "Risque ×2 + stop", "À risque : levier ×2 : ×"):
        assert words in text


def test_the_trend_bot_has_no_way_to_place_an_order_or_read_a_key():
    source = inspect.getsource(trend)
    for forbidden in ("create_order", "apiKey", "API_KEY", "secret", "CcxtBroker", "CONFIRM_LIVE"):
        assert forbidden not in source
