"""La lecture du graphique (tradingbot/patterns.py) : chaque définition sur un petit graphique dessiné à la main, puis
les garanties communes (aucun regard vers le futur, le direct voit ce que voit le backtest, la vente à découvert lit
la même figure à l'envers)."""
import numpy as np
import pytest

from tradingbot import patterns
from tradingbot.data import ohlcv_to_frame
from tradingbot.explain import FAILURES, SUCCESSES, rule_sentence
from tests.test_fleet import fair_market
from tradingbot.fleet import EXITS, SIDES, Spec, lookback_for, mirror, overlays, signals_for, simulate, technique
from tradingbot.strategy import PATTERN_FAMILIES, StrategyParams, compute_signals, pattern_marks
from tradingbot.swarm import LIBRARY

NAMES = [name for name in LIBRARY if technique(name).strategy_type in PATTERN_FAMILIES]
NAN = float("nan")


def ohlc(rows):
    """Des bougies écrites à la main : (ouverture, plus haut, plus bas, clôture)."""
    return tuple(np.array(column, dtype=float) for column in zip(*rows))


def flat(n, value=1.0):
    return np.full(n, value)


def hits(signal):
    return [int(i) for i in np.flatnonzero(signal)]


def wicked_walk(n=1500, seed=11):
    """Une marche au hasard avec de vraies mèches : sans elles, un marteau ou un balayage n'apparaît jamais."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    open_ = np.r_[100.0, close[:-1]]
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    rows = [[1_700_000_000_000 + i * 60_000, o, h, lo, c, 1.0] for i, (o, h, lo, c) in
            enumerate(zip(open_, high, low, close))]
    return ohlcv_to_frame(rows)


# --- les sommets et les creux marquants ---------------------------------------------------------------------------

def test_a_swing_is_known_only_once_the_price_has_moved_away_and_is_forgotten_later():
    high = np.array([1, 2, 3, 2, 1, 2, 5, 2, 1, 1, 1], dtype=float)
    low = high - 0.5
    top, bottom = patterns.last_swings(high, low, window=2, lookback=3)
    # le sommet de la bougie 2 n'est connu qu'à la bougie 4 (deux bougies plus tard), et oublié après 3 bougies
    np.testing.assert_array_equal(top, [NAN, NAN, NAN, NAN, 3, 3, NAN, NAN, 5, 5, NAN])
    np.testing.assert_array_equal(bottom, [NAN, NAN, NAN, NAN, NAN, NAN, 0.5, 0.5, NAN, NAN, 0.5])
    known_top, _ = patterns.known_swings(high, low, window=2, lookback=3)
    np.testing.assert_array_equal(known_top, [NAN, NAN, NAN, NAN, NAN, 3, 3, NAN, NAN, 5, 5])  # celui de la veille


STRUCTURE = ohlc([
    (9.8, 10.0, 9.6, 9.9), (9.9, 11.0, 9.8, 10.9),
    (10.9, 12.0, 10.7, 10.9),  # 2 : le sommet marquant (12)
    (10.9, 11.0, 10.2, 10.3),
    (10.3, 10.5, 9.5, 10.0),  # 4 : le creux marquant (9,5)
    (10.0, 10.6, 9.9, 10.4), (10.4, 11.6, 10.3, 11.4),
    (11.4, 12.6, 11.3, 12.4),  # 7 : première clôture au-dessus de 12
    (12.4, 13.0, 12.2, 12.9),  # 8 : toujours au-dessus, pas un nouveau signal
    (12.9, 13.0, 8.9, 9.0),  # 9 : clôture sous le creux marquant
])


def test_a_structure_break_is_bought_once_and_sold_below_the_last_swing_low():
    _, high, low, close = STRUCTURE
    entry, exit_ = patterns.structure_break(high, low, close, window=2, lookback=20)
    assert hits(entry) == [7] and hits(exit_) == [9]


def test_a_liquidity_sweep_needs_the_wick_below_the_low_and_the_close_back_above():
    rows = [(10.0, 10.2, 9.8, 10.0), (10.0, 10.1, 9.5, 9.6),
            (9.6, 9.7, 9.0, 9.2),  # 2 : le creux marquant (9,0), connu à la bougie 4
            (9.2, 9.8, 9.1, 9.7), (9.7, 10.3, 9.6, 10.2), (10.2, 10.4, 9.9, 10.0)]
    swept = ohlc(rows + [(9.4, 9.6, 8.8, 9.5)])  # mèche à 8,8 sous le creux, clôture à 9,5 au-dessus, en hausse
    assert hits(patterns.liquidity_sweep(swept[1], swept[2], swept[0], swept[3], window=2, lookback=20)) == [6]
    broken = ohlc(rows + [(9.4, 9.6, 8.8, 8.9)])  # clôture sous le creux : une vraie cassure, pas un piège
    assert not patterns.liquidity_sweep(broken[1], broken[2], broken[0], broken[3], window=2, lookback=20).any()
    falling = ohlc(rows + [(10.0, 10.1, 8.8, 9.3)])  # revenue au-dessus mais bougie baissière : pas de signal
    assert not patterns.liquidity_sweep(falling[1], falling[2], falling[0], falling[3], window=2, lookback=20).any()
    untouched = ohlc(rows + [(9.4, 9.6, 9.1, 9.5)])  # la mèche n'est pas passée sous le creux
    assert not patterns.liquidity_sweep(untouched[1], untouched[2], untouched[0], untouched[3], 2, 20).any()


# --- les zones : zone à combler, order block, retracement ----------------------------------------------------------

GAP = [(10.0, 10.5, 9.5, 10.0), (10.0, 12.5, 10.0, 12.4),
       (12.4, 13.0, 11.5, 12.8),  # 2 : son plus bas (11,5) est au-dessus du plus haut de la bougie 0 (10,5) : un trou
       (12.8, 13.2, 12.0, 13.0)]


def test_a_fair_value_gap_is_the_hole_left_by_three_candles():
    _, high, low, _ = ohlc(GAP)
    top, bottom = patterns.fair_value_gaps(high, low, flat(4), min_size=0.25)
    np.testing.assert_array_equal(top, [NAN, NAN, 11.5, NAN])
    np.testing.assert_array_equal(bottom, [NAN, NAN, 10.5, NAN])
    top, _ = patterns.fair_value_gaps(high, low, flat(4, 5.0), min_size=0.25)  # trou de 1 pour des bougies de 5 :
    assert np.isnan(top).all()  # trop petit pour compter


def gap_entries(extra, valid=30):
    open_, high, low, close = ohlc(GAP + extra)
    top, bottom = patterns.fair_value_gaps(high, low, flat(len(low)), min_size=0.25)
    return hits(patterns.zone_retest(low, open_, close, top, bottom, valid))


def test_a_gap_is_bought_when_the_price_comes_back_into_it_and_closes_above():
    back = (13.0, 13.1, 11.2, 11.8)  # redescend à 11,2 dans le trou (10,5 à 11,5) et clôture au-dessus, à 11,8
    again = (11.8, 12.0, 11.0, 11.9)  # y revient encore : la zone a déjà servi
    assert gap_entries([back, again]) == [4]
    assert gap_entries([(13.0, 13.1, 11.6, 11.8)]) == []  # s'arrête à 11,6 : n'entre pas dans le trou
    assert gap_entries([(13.0, 13.1, 11.2, 11.3)]) == []  # clôture dans le trou : pas encore de rejet
    assert gap_entries([(13.0, 13.1, 11.2, 11.3), (11.3, 12.0, 11.1, 11.9)]) == [5]  # le rejet vient à la suivante


def test_a_gap_is_forgotten_once_filled_or_too_old():
    filled = (13.0, 13.1, 10.0, 10.2)  # clôture sous le bas du trou (10,5) : la zone est comblée, donc morte
    back = (10.2, 12.0, 10.1, 11.8)
    assert gap_entries([filled, back]) == []
    waits = [(13.0, 13.2, 12.6, 13.0)] * 3
    back = (13.0, 13.1, 11.2, 11.8)  # la zone est née à la bougie 2 ; le retour a lieu à la bougie 7, la cinquième
    assert gap_entries(waits + [back], valid=5) == [7]  # encore valable
    assert gap_entries(waits + [back], valid=4) == []  # une bougie trop tard


def test_the_newest_zone_replaces_the_old_one_and_the_chart_shows_the_waiting_zone():
    open_, high, low, close = ohlc(GAP + [(13.0, 13.1, 11.2, 11.8), (11.8, 12.0, 11.0, 11.9)])
    top, bottom = patterns.fair_value_gaps(high, low, flat(6), min_size=0.25)
    track = np.full(6, NAN), np.full(6, NAN)
    patterns.zone_retest(low, open_, close, top, bottom, 30, track=track)
    np.testing.assert_array_equal(track[0], [NAN, NAN, NAN, 11.5, 11.5, NAN])  # attendue dès la bougie suivante,
    np.testing.assert_array_equal(track[1], [NAN, NAN, NAN, 10.5, 10.5, NAN])  # jusqu'à la bougie qui s'en sert
    top[3], bottom[3] = 12.5, 12.0  # une zone plus récente naît à la bougie 3 : c'est elle qui compte
    assert hits(patterns.zone_retest(low, open_, close, top, bottom, 30)) == []  # clôture à 11,8 sous son bas : morte


def test_an_order_block_is_the_last_down_candle_before_a_surge():
    open_, high, low, close = ohlc([
        (10.2, 10.3, 9.9, 10.0), (10.0, 10.2, 9.9, 10.1),
        (10.1, 10.2, 9.9, 10.0),  # 2 : la dernière bougie baissière avant l'envolée
        (10.0, 11.1, 10.0, 11.0), (11.0, 11.7, 10.9, 11.6),
        (11.6, 12.3, 11.5, 12.2),  # 5 : +2,2 en trois bougies, pour des bougies de 1
        (12.2, 12.3, 11.5, 11.6),
        (11.6, 11.7, 10.1, 10.6),  # 7 : revient à 10,1 sur le bloc (9,9 à 10,2) et clôture au-dessus
    ])
    top, bottom = patterns.order_blocks(high, low, open_, close, flat(8), bars=3, strength=2.0)
    np.testing.assert_array_equal(top, [NAN, NAN, NAN, NAN, NAN, 10.2, NAN, NAN])
    np.testing.assert_array_equal(bottom, [NAN, NAN, NAN, NAN, NAN, 9.9, NAN, NAN])
    assert hits(patterns.zone_retest(low, open_, close, top, bottom, 30)) == [7]
    top, _ = patterns.order_blocks(high, low, open_, close, flat(8), bars=3, strength=3.0)  # envolée trop faible
    assert np.isnan(top).all()


LEG = [(10.2, 10.5, 10.0, 10.1), (10.1, 10.2, 9.6, 9.7),
       (9.7, 9.8, 9.0, 9.6),  # 2 : le creux d'où part la jambe (9,0)
       (9.6, 10.5, 9.7, 10.4), (10.4, 12.0, 10.4, 11.9), (11.9, 13.5, 11.9, 13.4),
       (13.4, 15.0, 13.4, 14.5),  # 6 : le sommet (15,0) ; la jambe vaut 6
       (14.5, 14.6, 13.8, 14.0),
       (14.0, 14.0, 13.0, 13.0)]  # 8 : le sommet est confirmé, la zone va de 12,0 (50 %) à 11,292 (61,8 %)


def test_a_fibonacci_zone_covers_half_to_618_of_the_leg_and_is_bought_on_a_rising_close():
    open_, high, low, close = ohlc(LEG + [
        (13.0, 13.1, 11.8, 12.3),  # 9 : entre dans la zone, mais bougie baissière
        (12.3, 12.9, 11.9, 12.8),  # 10 : dans la zone, clôture en hausse
    ])
    top, bottom = patterns.fib_zones(high, low, flat(11), window=2, lookback=20, low_ratio=0.5, high_ratio=0.618,
                                     min_leg=3.0)
    assert hits(~np.isnan(top)) == [8]
    assert top[8] == pytest.approx(12.0) and bottom[8] == pytest.approx(15.0 - 0.618 * 6.0)
    assert hits(patterns.zone_retest(low, open_, close, top, bottom, 30, "bottom")) == [10]
    short_leg = patterns.fib_zones(high, low, flat(11), 2, 20, 0.5, 0.618, min_leg=7.0)[0]  # jambe de 6 : trop courte
    assert np.isnan(short_leg).all()
    deep = ohlc(LEG + [(13.0, 13.1, 11.0, 11.1), (11.1, 12.9, 11.0, 12.8)])  # clôture sous 61,8 % : zone abandonnée
    top, bottom = patterns.fib_zones(deep[1], deep[2], flat(11), 2, 20, 0.5, 0.618, 3.0)
    assert hits(patterns.zone_retest(deep[2], deep[0], deep[3], top, bottom, 30, "bottom")) == []


# --- les bougies de retournement ----------------------------------------------------------------------------------

def test_an_engulfing_candle_covers_the_body_before_it_at_the_low_of_the_move():
    rows = [(10.0, 10.2, 9.8, 10.1), (10.1, 10.2, 9.6, 9.7),
            (9.7, 9.8, 9.2, 9.3),  # 2 : rouge
            (9.3, 9.9, 9.1, 9.8),  # 3 : verte, ouvre sous la clôture de la rouge et clôture au-dessus de son ouverture
            (9.8, 10.5, 9.7, 10.4)]  # 4 : verte après une verte : pas un avalement
    open_, high, low, close = ohlc(rows)
    assert hits(patterns.engulfing(high, low, open_, close, span=3)) == [3]
    rows[1] = (10.1, 10.2, 9.0, 9.7)  # un plus bas à 9,0 juste avant : la figure n'est plus au plus bas du mouvement
    open_, high, low, close = ohlc(rows)
    assert hits(patterns.engulfing(high, low, open_, close, span=3)) == []
    rows[1], rows[3] = (10.1, 10.2, 9.6, 9.7), (9.3, 9.7, 9.1, 9.6)  # ne recouvre pas l'ouverture de la rouge (9,7)
    open_, high, low, close = ohlc(rows)
    assert hits(patterns.engulfing(high, low, open_, close, span=3)) == []


def test_a_hammer_has_a_long_lower_wick_a_small_body_and_sits_at_the_low():
    rows = [(10.5, 10.6, 10.3, 10.4), (10.4, 10.5, 10.1, 10.2),
            (10.0, 10.15, 9.0, 10.1)]  # corps 0,1 en haut, mèche basse de 1,0, mèche haute de 0,05
    open_, high, low, close = ohlc(rows)
    assert hits(patterns.hammer(high, low, open_, close, flat(3), span=3, wick=2.0)) == [2]
    assert hits(patterns.hammer(high, low, open_, close, flat(3, 2.0), span=3, wick=2.0)) == []  # bougie trop petite
    assert hits(patterns.hammer(high, low, open_, close, flat(3), span=3, wick=12.0)) == []  # mèche pas assez longue
    open_, high, low, close = ohlc(rows[:2] + [(10.0, 10.9, 9.0, 10.1)])  # une grande mèche haute aussi : une toupie
    assert hits(patterns.hammer(high, low, open_, close, flat(3), span=3, wick=2.0)) == []
    open_, high, low, close = ohlc([(10.5, 10.6, 8.5, 10.4)] + rows[1:])  # un plus bas à 8,5 deux bougies avant
    assert hits(patterns.hammer(high, low, open_, close, flat(3), span=3, wick=2.0)) == []


def test_an_inside_bar_is_bought_when_the_close_leaves_its_mother_candle_by_the_top():
    open_, high, low, close = ohlc([
        (10.0, 11.0, 9.0, 10.5),  # 0 : la bougie mère
        (10.5, 10.6, 9.5, 10.0),  # 1 : contenue dans la mère
        (10.0, 11.3, 9.9, 11.2),  # 2 : clôture au-dessus du plus haut de la mère (11)
        (11.2, 11.4, 11.0, 11.3),  # 3 : la bougie 2 n'est pas contenue dans la 1
    ])
    assert hits(patterns.inside_break(high, low, close)) == [2]
    close[2] = 10.9  # reste dans la mère : pas de sortie
    assert hits(patterns.inside_break(high, low, close)) == []


# --- les figures --------------------------------------------------------------------------------------------------

def test_a_divergence_is_a_lower_low_in_price_with_a_higher_low_in_rsi():
    low = np.array([10, 9.5, 9.0, 9.4, 9.8, 9.6, 8.8, 9.3, 9.9, 10, 10])  # creux à 9,0 puis plus bas, à 8,8
    strength = np.full(11, 50.0)
    strength[2], strength[6] = 25.0, 35.0  # le RSI, lui, remonte de 25 à 35
    assert hits(patterns.rsi_divergence(low, strength, window=2, lookback=20, weak=40.0)) == [8]  # 2 bougies après
    strength[6] = 20.0  # le RSI baisse aussi : pas de divergence
    assert hits(patterns.rsi_divergence(low, strength, 2, 20, 40.0)) == []
    strength[2], strength[6] = 45.0, 55.0  # le marché n'était pas faible au premier creux
    assert hits(patterns.rsi_divergence(low, strength, 2, 20, 40.0)) == []
    strength[2], strength[6] = 25.0, 35.0
    assert hits(patterns.rsi_divergence(low, strength, 2, lookback=3, weak=40.0)) == []  # creux trop éloignés


DOUBLE = [(10.2, 10.5, 10.0, 10.2), (10.2, 10.2, 9.6, 9.7),
          (9.7, 9.8, 9.0, 9.5),  # 2 : premier creux (9,0)
          (9.5, 10.4, 9.5, 10.3),
          (10.3, 11.0, 10.2, 10.6),  # 4 : le sommet entre les deux (11,0), la ligne de cou
          (10.6, 10.7, 9.8, 9.9),
          (9.9, 10.0, 9.2, 9.6),  # 6 : second creux (9,2), au même prix à 0,2 près
          (9.6, 10.3, 9.5, 10.2),
          (10.2, 10.9, 10.1, 10.8),  # 8 : le second creux est confirmé, clôture encore sous la ligne de cou
          (10.8, 11.4, 10.7, 11.3),  # 9 : première clôture au-dessus de 11,0
          (11.3, 11.8, 11.2, 11.7)]


def test_a_double_bottom_is_bought_at_the_first_close_above_its_neckline():
    _, high, low, close = ohlc(DOUBLE)
    assert hits(patterns.double_bottom(high, low, close, flat(11), window=2, lookback=20, tol=0.5, valid=30)) == [9]
    assert hits(patterns.double_bottom(high, low, close, flat(11), 2, 20, tol=0.1, valid=30)) == []  # creux trop écartés
    assert hits(patterns.double_bottom(high, low, close, flat(11), 2, 20, tol=0.5, valid=0)) == []  # trop tard
    assert hits(patterns.double_bottom(high, low, close, flat(11), 2, lookback=3, tol=0.5, valid=30)) == []


# --- les garanties communes ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_no_chart_reading_looks_into_the_future(name):
    """Les signaux d'une bougie ne changent pas quand on ajoute les bougies suivantes."""
    df, p = wicked_walk(), technique(name)
    full = compute_signals(df, p)
    assert full["entry"].sum() > 0, "la technique ne se déclenche jamais sur ce marché : le test ne prouverait rien"
    for cut in (400, 777, 1203):
        part = compute_signals(df.iloc[:cut], p)
        for column in ("entry", "exit"):
            assert (part[column].to_numpy() == full[column].iloc[:cut].to_numpy()).all(), (column, cut)


@pytest.mark.parametrize("name", NAMES)
def test_the_live_window_reads_the_chart_like_the_whole_history(name):
    """Le direct ne lit que les dernières bougies : il doit voir les mêmes zones, sommets et figures que le backtest."""
    p = technique(name)
    look = lookback_for(p)
    df = wicked_walk(look + 500, seed=5)
    picks = np.random.default_rng(1).choice(np.arange(look - 1, len(df)), size=40, replace=False)
    for side in SIDES:
        full = signals_for(df, p, side)
        fired = hits(full.entry)[-25:]  # et surtout là où il y a un signal
        for i in list(picks) + [i for i in fired if i >= look - 1]:
            window = signals_for(df.iloc[i - look + 1:i + 1], p, side)
            assert (window.entry[-1], window.exit[-1]) == (full.entry[i], full.exit[i]), (side, i)


@pytest.mark.parametrize("name", NAMES)
def test_a_short_reads_the_same_figure_upside_down(name):
    df, p = wicked_walk(900, seed=2), technique(name)
    buyer, seller = signals_for(df, p, "long"), signals_for(mirror(df), p, "short")
    assert buyer.entry.sum() > 0
    assert (buyer.entry == seller.entry).all() and (buyer.exit == seller.exit).all()


def test_on_a_market_with_nothing_to_win_reading_the_chart_wins_nothing_either():
    """Le garde-fou du moteur (tests/test_fleet.py), pour les lectures du graphique : sur un prix tiré au hasard,
    aucune zone, aucune figure ne peut gagner. Avant frais, la moyenne d'un trade doit donc être nulle ; après frais,
    c'est le prix des frais. Une lecture qui regarderait la bougie suivante gagnerait ici plusieurs centièmes de pour
    cent par trade. (Le reste, environ +0,005 %, vient du marché fabriqué : un stop y est servi à son prix exact
    alors que le prix, tiré chaque seconde, saute un peu au-delà ; il fond quand le chemin est tiré plus finement.)"""
    gross, nets, per_name = [], [], {}
    for seed in (0, 1):
        df = fair_market(seed=seed)
        for name in NAMES:
            for side in SIDES:
                signals = signals_for(df, technique(name), side)
                for target, mode in EXITS:
                    book = simulate(df, Spec("scalping", "X/USDT", "1m", name, side, target, 5.0, mode), signals=signals)
                    assert book.s["dead"] != "liquidé"
                    done = [t for t in book.s["trades"] if t["reason"] != "fin du test"]
                    gross += [t["gross"] for t in done]
                    nets += [t["net"] for t in done]
                    per_name.setdefault(name, []).extend(t["gross"] for t in done)
    assert len(gross) > 30_000 and all(len(xs) > 1_000 for xs in per_name.values())
    assert abs(np.mean(gross)) < 0.0002  # rien à gagner avant frais (mesuré : +0,008 % ; les frais valent 0,14 %)
    assert all(abs(np.mean(xs)) < 0.0005 for xs in per_name.values()), {k: np.mean(v) for k, v in per_name.items()}
    assert -0.0015 < np.mean(nets) < -0.0011  # après frais : le prix des frais, rien d'autre


def test_a_bearish_gap_is_sold_short_when_the_price_climbs_back_into_it():
    """De bout en bout, par la technique du bot : la figure de GAP retournée, précédée de bougies calmes."""
    calm = [(10.0, 10.1, 9.9, 10.0)] * 30
    rows = calm + GAP + [(13.0, 13.1, 11.2, 11.8), (11.8, 12.0, 11.0, 11.9)]
    df = ohlcv_to_frame([[60_000 * i, o, h, lo, c, 1.0] for i, (o, h, lo, c) in enumerate(rows)])
    p = technique("Zone à combler (FVG)")
    assert hits(signals_for(df, p, "long").entry) == [34]
    assert hits(signals_for(mirror(df), p, "short").entry) == [34]
    assert not signals_for(df, p, "short").entry.any()  # sur le graphique d'origine, rien à vendre


def test_the_chart_shows_what_each_reading_looked_at():
    df = wicked_walk(700, seed=3)
    for name in NAMES:
        p = technique(name)
        for side in SIDES:
            lines = {ln["key"]: ln for ln in overlays(df, p, side)}
            assert lines and all(len(ln["values"]) == len(df) for ln in lines.values()), name
            if p.strategy_type in ("fvg", "order_block", "fibonacci"):
                pairs = [(a, b) for a, b in zip(lines["zone-up"]["values"], lines["zone-low"]["values"]) if a is not None]
                assert pairs and all(a > b > 0 for a, b in pairs), (name, side)  # sur le vrai prix, bord haut en haut
            if p.strategy_type == "structure":
                assert ("sommet" if side == "long" else "creux") in lines["in"]["label"]
    # les repères sont ceux des signaux : une zone est affichée à la bougie qui s'en sert
    p = technique("Zone à combler (FVG)")
    marks, entry = pattern_marks(df, p), compute_signals(df, p)["entry"].to_numpy()
    assert entry.any() and not np.isnan(marks["zone_top"][entry]).any()
    assert (df["low"].to_numpy()[entry] <= marks["zone_top"][entry]).all()
    assert (df["close"].to_numpy()[entry] > marks["zone_top"][entry]).all()


def test_every_reading_has_its_words_and_its_fixed_settings():
    assert len(NAMES) == 12 and {technique(n).strategy_type for n in NAMES} == set(PATTERN_FAMILIES)
    for family in PATTERN_FAMILIES:
        p = StrategyParams(strategy_type=family)
        assert rule_sentence(p).endswith(".") and FAILURES[family] and SUCCESSES[family]
        assert p.warmup_bars >= p.swing_lookback + p.zone_valid + 2 * p.level_window + p.atr_period
        assert p.exit_label == ("retour sous le dernier creux" if family == "structure" else "essoufflement")


@pytest.mark.parametrize("kwargs", [{"swing_lookback": 1}, {"zone_valid": 0}, {"gap_min_atr": 0.0}, {"surge_bars": 1},
                                    {"surge_atr": -1.0}, {"pattern_span": 1}, {"wick_ratio": 0.0},
                                    {"fib_low": 0.7, "fib_high": 0.6}, {"fib_high": 1.2}, {"divergence_weak": 100.0},
                                    {"leg_min_atr": 0.0}, {"double_tol": 0.0}, {"divergence_period": 1}])
def test_chart_reading_settings_are_validated(kwargs):
    with pytest.raises(ValueError, match="lecture du graphique"):
        StrategyParams(strategy_type="fvg", **kwargs)
