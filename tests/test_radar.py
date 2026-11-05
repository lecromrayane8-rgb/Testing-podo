import pytest

from tradingbot.radar import Radar


def markets(*symbols):
    return {s: {"symbol": s, "spot": True, "active": True, "base": s.split("/")[0], "quote": s.split("/")[1]}
            for s in symbols}


def ticker(last, volume=1e7, change=1.0):
    return {"last": last, "quoteVolume": volume, "percentage": change}


MARKETS = markets("BTC/USDT", "PEPE/USDT", "WIF/USDT", "USDC/USDT", "BTCUP/USDT", "TINY/USDT", "ETH/BTC")


def fill(radar, minutes=15, pepe_jump_at=85, wif=lambda i: 2.0):
    """Un relevé toutes les 10 s pendant `minutes` : PEPE bondit de 3 % dans la dernière minute."""
    for i in range(minutes * 6 + 1):
        radar.update(MARKETS, {
            "BTC/USDT": ticker(68_000 * (1 + 0.0001 * i)),
            "PEPE/USDT": ticker(1.0 if i < pepe_jump_at else 1.03, change=12.0),
            "WIF/USDT": ticker(wif(i)),
            "USDC/USDT": ticker(1.0), "BTCUP/USDT": ticker(5.0), "TINY/USDT": ticker(2.0, volume=1e5),
            "ETH/BTC": ticker(0.05),
        }, 1_000.0 + 10 * i)


def test_the_radar_ranks_the_biggest_moves_of_the_tradable_coins():
    radar = Radar()
    fill(radar, wif=lambda i: 2.0 * (1 - 0.0005 * i))  # WIF glisse doucement
    moves = radar.moves(window=60)
    # Monnaies stables, tokens à levier, paires hors USDT et cryptos peu échangées : écartées.
    assert {m.symbol for m in moves} == {"BTC/USDT", "PEPE/USDT", "WIF/USDT"}
    assert moves[0].symbol == "PEPE/USDT" and moves[0].strong
    assert moves[0].changes[60] == pytest.approx(0.03) and moves[0].changes[900] == pytest.approx(0.03)
    assert moves[0].change_24h == pytest.approx(0.12) and moves[0].volume_24h == 1e7
    assert not [m for m in moves if m.symbol == "BTC/USDT"][0].strong
    assert radar.span == 900


def test_rising_only_keeps_the_coins_going_up():
    radar = Radar()
    fill(radar, wif=lambda i: 2.0 if i < 70 else 1.8)  # WIF chute de 10 % : un gros mouvement, mais vers le bas
    both = radar.moves(window=300)
    assert both[0].symbol == "WIF/USDT" and both[0].changes[300] == pytest.approx(-0.1)
    rising = radar.moves(window=300, rising_only=True)
    assert [m.symbol for m in rising] == ["PEPE/USDT", "BTC/USDT"]


def test_until_the_window_is_filled_the_radar_ranks_on_24_hours():
    radar = Radar()
    radar.update(MARKETS, {"BTC/USDT": ticker(68_000, change=1.0), "PEPE/USDT": ticker(1.0, change=-9.0)}, 0.0)
    radar.update(MARKETS, {"BTC/USDT": ticker(68_100, change=1.1), "PEPE/USDT": ticker(1.0, change=-9.5)}, 10.0)
    moves = radar.moves(window=300)
    assert [m.symbol for m in moves] == ["PEPE/USDT", "BTC/USDT"] and moves[0].changes[300] is None


def test_a_network_gap_never_turns_into_a_fake_one_minute_move():
    radar = Radar()
    radar.update(MARKETS, {"PEPE/USDT": ticker(1.0)}, 0.0)
    radar.update(MARKETS, {"PEPE/USDT": ticker(1.2)}, 700.0)  # 12 minutes sans relevé
    assert radar.reference(60) is None and radar.reference(300) is None
    assert radar.moves(window=60)[0].changes == {60: None, 300: None, 900: None}
    radar.update(MARKETS, {"PEPE/USDT": ticker(1.2)}, 2_000.0)
    assert len(radar.history) == 1  # les relevés trop vieux sont oubliés
