import json

import numpy as np
import pandas as pd
import pytest

from tradingbot.news import (
    FEEDS, FNG_URL, NewsSource, fng_study, mentions, merge, parse_feed, parse_fng, reaction, study_text, zone,
)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>CoinDesk</title>
<item><title>Bitcoin climbs above $70,000 as ETF inflows return</title><link>https://example.com/a</link>
<pubDate>Thu, 06 Nov 2026 08:30:00 +0000</pubDate><description><![CDATA[<p>BTC and <b>Solana</b> rose.</p>]]></description></item>
<item><title>SEC chair speaks about crypto rules</title><link>https://example.com/b</link>
<pubDate>Thu, 06 Nov 2026 07:00:00 +0000</pubDate></item>
<item><title>Lien douteux</title><link>javascript:alert(1)</link></item>
</channel></rss>"""
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Decrypt</title>
<entry><title>Dogecoin and $PEPE rally while ETH stalls</title><link href="https://example.com/c"/>
<updated>2026-11-06T09:15:00Z</updated><summary>Memecoins up.</summary></entry></feed>"""


def test_feeds_are_read_whether_rss_or_atom_and_unsafe_links_are_dropped():
    rss = parse_feed(RSS, "CoinDesk")
    assert [i["title"][:7] for i in rss] == ["Bitcoin", "SEC cha"]  # le lien javascript: est écarté
    assert rss[0]["published"].isoformat() == "2026-11-06T08:30:00+00:00" and rss[0]["summary"] == "BTC and Solana rose."
    atom = parse_feed(ATOM, "Decrypt")
    assert atom[0]["link"] == "https://example.com/c" and atom[0]["published"].hour == 9
    assert parse_feed("<pas du xml", "X") == []


def test_coins_are_found_by_name_or_ticker_but_not_acronyms():
    assert mentions("Bitcoin climbs as ETF inflows return; SEC and the CEO comment") == ["BTC"]
    assert mentions("Dogecoin and $PEPE rally while ETH stalls") == ["DOGE", "PEPE", "ETH"]  # dans l'ordre du titre
    assert mentions("XYZ token surges", known={"BTC"}) == []  # un ticker inconnu du radar est ignoré
    assert mentions("Ethereum's upgrade, ether price") == ["ETH"]


def test_news_are_merged_newest_first_without_duplicates():
    items = parse_feed(RSS, "CoinDesk") + parse_feed(ATOM, "Decrypt") + parse_feed(RSS, "Copie")
    news = merge(items)
    assert [n["source"] for n in news] == ["Decrypt", "CoinDesk", "CoinDesk"]
    assert news[0]["coins"] == ["DOGE", "PEPE", "ETH"] and news[1]["coins"] == ["BTC", "SOL"]


def fng_payload(values, start="2018-02-01"):
    days = pd.date_range(start, periods=len(values), freq="D", tz="UTC")
    return {"data": [{"value": str(int(v)), "timestamp": str(int(d.timestamp()))} for d, v in zip(days, values)][::-1]}


def test_the_fear_and_greed_index_is_read_and_zoned():
    series = parse_fng(fng_payload([10, 50, 90]))
    assert list(series.values) == [10, 50, 90] and series.index[0].isoformat().startswith("2018-02-01")
    assert [zone(v) for v in (10, 30, 50, 60, 80)] == ["peur extrême", "peur", "neutre", "avidité", "avidité extrême"]
    assert parse_fng({}).empty


def test_the_study_compares_what_followed_the_extremes_with_any_day():
    n = 600
    rng = np.random.default_rng(1)
    values = np.clip(50 + 40 * np.sin(np.arange(n) / 20) + rng.normal(0, 5, n), 0, 100)
    fng = parse_fng(fng_payload(values))
    days = pd.date_range("2018-02-01", periods=n, freq="D", tz="UTC")
    closes = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))), index=days)
    study = fng_study(fng, closes, days=30)
    assert study["fear"]["days"] > 20 and study["greed"]["days"] > 20 and study["all"]["days"] == n - 30
    assert 1 <= study["fear"]["episodes"] <= study["fear"]["days"]
    text = study_text(study)
    assert "peur extrême" in text and "pas une règle testée" in text and "épisodes" in text
    assert fng_study(fng.iloc[:50], closes) is None and study_text(None).startswith("Pas assez")


def test_the_news_source_survives_a_site_down_and_caches_the_index(tmp_path):
    pages = {FEEDS[0][1]: RSS, FEEDS[2][1]: ATOM, FNG_URL: json.dumps(fng_payload([30] * 300 + [12]))}

    def get(url):
        if url not in pages:
            raise ConnectionError("site en panne")
        return pages[url]

    source = NewsSource(tmp_path, get=get, known=lambda: {"BTC", "ETH", "SOL", "DOGE", "PEPE"})
    page = source.fetch()
    assert len(page["news"]) == 3 and page["errors"] == ["Cointelegraph : site en panne"]
    assert page["fng"]["value"] == 12 and page["fng"]["zone"] == "peur extrême" and len(page["fng"]["history"]) == 301
    assert (tmp_path / "peur-avidite.json").exists()
    reaction(page["news"], lambda base, when: 100.0 if base == "BTC" else None, lambda base: 103.0)
    btc = next(n for n in page["news"] if "BTC" in n["coins"])
    assert btc["moves"][0] == {"coin": "BTC", "change": pytest.approx(0.03)}
    assert next(m for m in btc["moves"] if m["coin"] == "SOL")["change"] is None
