import pytest

from tradingbot.data import load_csv


def test_load_bot_csv(tmp_path):
    path = tmp_path / "bot.csv"
    path.write_text("ts,open,high,low,close,volume\n1700000000000,1,2,0.5,1.5,10\n", encoding="utf-8")
    df = load_csv(path)
    assert int(df["ts"].iloc[0]) == 1_700_000_000_000 and df["close"].iloc[0] == 1.5


def test_load_classic_stock_export(tmp_path):
    path = tmp_path / "AAPL.csv"
    path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2024-01-03,184.2,185.9,183.4,184.3,183.7,58414500\n"
        "2024-01-02,187.2,188.4,183.9,185.6,185.0,82488700\n"
        "2024-01-04,null,null,null,null,null,null\n",
        encoding="utf-8",
    )
    df = load_csv(path)
    assert len(df) == 2  # ligne vide écartée
    assert list(df["close"]) == [185.6, 184.3]  # triées par date
    assert str(df.index[0].date()) == "2024-01-02"


def test_csv_without_prices_is_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Date,Price\n2024-01-02,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colonnes manquantes"):
        load_csv(path)
