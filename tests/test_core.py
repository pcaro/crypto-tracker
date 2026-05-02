"""Tests for core.py — pure data layer, no GPU."""

from unittest.mock import MagicMock, patch

import pytest
import requests

import core


@pytest.fixture(autouse=True)
def _reset():
    core.init()


# ── config ────────────────────────────────────────────────────


class TestConfig:
    def test_coins(self):
        assert len(core.COINS) == 5
        ids = [c[0] for c in core.COINS]
        assert len(set(ids)) == 5

    def test_colors(self):
        assert len(core.COLORS) == len(core.COINS)
        for c in core.COLORS:
            assert len(c) == 3
            assert all(0 <= v <= 255 for v in c)

    def test_binance_symbols(self):
        for _, _, _, bsym in core.COINS:
            assert bsym.endswith("USDT")


# ── apply_prices ──────────────────────────────────────────────


class TestApplyPrices:
    def test_parses_valid_tickers(self):
        tickers = [
            {
                "symbol": "BTCUSDT",
                "lastPrice": "78465.04",
                "priceChangePercent": "-0.054",
            },
            {
                "symbol": "ETHUSDT",
                "lastPrice": "2309.81",
                "priceChangePercent": "0.128",
            },
            {"symbol": "SOLUSDT", "lastPrice": "84.23", "priceChangePercent": "0.214"},
            {
                "symbol": "XRPUSDT",
                "lastPrice": "1.3939",
                "priceChangePercent": "-0.143",
            },
            {"symbol": "ADAUSDT", "lastPrice": "0.2506", "priceChangePercent": "0.160"},
        ]
        core.apply_prices(tickers)

        p, ch = core.price("bitcoin")
        assert p == 78465.04
        assert ch == -0.054

        p, ch = core.price("ethereum")
        assert p == 2309.81

    def test_ignores_unknown_symbols(self):
        core.apply_prices(
            [{"symbol": "DOGEUSDT", "lastPrice": "0.42", "priceChangePercent": "5.0"}]
        )
        p, ch = core.price("bitcoin")
        assert p is None


# ── apply_klines ──────────────────────────────────────────────


class TestApplyKlines:
    def test_stores_closes(self):
        klines = [
            [1714500000000, "0", "0", "0", "100.0", "0", 0, "0", 0, "0", "0", "0"],
            [1714500060000, "0", "0", "0", "200.0", "0", 0, "0", 0, "0", "0", "0"],
            [1714500120000, "0", "0", "0", "300.0", "0", 0, "0", 0, "0", "0", "0"],
        ]
        core.apply_klines("bitcoin", klines)
        xs, ys = core.series_data("bitcoin")
        assert xs == [1714500000.0, 1714500060.0, 1714500120.0]
        assert ys == [100.0, 200.0, 300.0]

    def test_max_points_enforced(self):
        klines = [
            [
                1714500000000 + i * 60000,
                "0",
                "0",
                "0",
                str(i * 10),
                "0",
                0,
                "0",
                0,
                "0",
                "0",
                "0",
            ]
            for i in range(100)
        ]
        core.apply_klines("bitcoin", klines)
        xs, ys = core.series_data("bitcoin")
        assert len(ys) == core.MAX_POINTS
        assert ys[0] == 400.0
        assert ys[-1] == 990.0


# ── currency conversion ───────────────────────────────────────


class TestCurrency:
    def test_usd_default(self):
        core.apply_prices(
            [{"symbol": "BTCUSDT", "lastPrice": "100", "priceChangePercent": "0"}]
        )
        core.apply_klines(
            "bitcoin",
            [
                [0, "0", "0", "0", "100", "0", 0, "0", 0, "0", "0", "0"],
                [0, "0", "0", "0", "200", "0", 0, "0", 0, "0", "0", "0"],
            ],
        )
        assert core.price_in_currency("bitcoin") == 100.0
        _, ys = core.series_data("bitcoin")
        assert ys == [100.0, 200.0]
        assert core.currency_symbol() == "$"

    def test_eur_conversion(self):
        core.set_currency("EUR")
        core.set_eur_rate(0.85)
        core.apply_prices(
            [{"symbol": "BTCUSDT", "lastPrice": "100", "priceChangePercent": "0"}]
        )
        core.apply_klines(
            "bitcoin",
            [
                [0, "0", "0", "0", "100", "0", 0, "0", 0, "0", "0", "0"],
                [0, "0", "0", "0", "200", "0", 0, "0", 0, "0", "0", "0"],
            ],
        )
        assert core.price_in_currency("bitcoin") == 85.0
        _, ys = core.series_data("bitcoin")
        assert ys == [85.0, 170.0]
        assert core.currency_symbol() == "€"


# ── change_color ──────────────────────────────────────────────


class TestChangeColor:
    def test_positive(self):
        core.apply_prices(
            [{"symbol": "BTCUSDT", "lastPrice": "100", "priceChangePercent": "5.0"}]
        )
        assert core.change_color("bitcoin") == [247, 147, 26, 255]

    def test_negative(self):
        core.apply_prices(
            [{"symbol": "BTCUSDT", "lastPrice": "100", "priceChangePercent": "-3.0"}]
        )
        assert core.change_color("bitcoin") == [255, 80, 80, 255]

    def test_missing(self):
        assert core.change_color("bitcoin") == [255, 255, 255, 255]


# ── series_data edge cases ────────────────────────────────────


class TestSeriesData:
    def test_empty(self):
        xs, ys = core.series_data("bitcoin")
        assert xs is None

    def test_single_point(self):
        core.apply_klines(
            "bitcoin", [[0, "0", "0", "0", "100", "0", 0, "0", 0, "0", "0", "0"]]
        )
        xs, ys = core.series_data("bitcoin")
        assert xs is None  # need >= 2 points


# ── fetch_all orchestration ───────────────────────────────────


class TestFetchAll:
    @patch("core.requests.get")
    def test_full_cycle(self, mock_get):
        def side(url, params=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            if "currency-api" in url:
                resp.json.return_value = {"usd": {"eur": 0.85}}
            elif "ticker/24hr" in url:
                resp.json.return_value = [
                    {"symbol": c[3], "lastPrice": "100", "priceChangePercent": "1.5"}
                    for c in core.COINS
                ]
            else:
                resp.json.return_value = [
                    [0, "0", "0", "0", str(i * 10), "0", 0, "0", 0, "0", "0", "0"]
                    for i in range(3)
                ]
            return resp

        mock_get.side_effect = side
        ok = core.fetch_all()
        assert ok is True
        assert core.price_in_currency("bitcoin") == 100.0
        _, ys = core.series_data("bitcoin")
        assert len(ys) == 3

    @patch("core.requests.get")
    def test_ticker_failure(self, mock_get):
        def side(url, params=None, timeout=None):
            resp = MagicMock()
            if "ticker/24hr" in url:
                resp.status_code = 500
                resp.json.side_effect = ValueError
            else:
                resp.status_code = 200
                resp.json.return_value = (
                    {"usd": {"eur": 1.0}}
                    if "currency-api" in url
                    else [[0, "0", "0", "0", "10", "0", 0, "0", 0, "0", "0", "0"]]
                )
            return resp

        mock_get.side_effect = side
        ok = core.fetch_all()
        assert ok is False  # tickers failed
        # klines still succeeded (series_data needs >=2 points, we have 1)
        xs, ys = core.series_data("bitcoin")
        assert xs is None  # not enough points

    @patch("core.requests.get")
    def test_network_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout
        ok = core.fetch_all()
        assert ok is False
        assert core.price("bitcoin") == (None, None)


# ── coin_by_id ────────────────────────────────────────────────


class TestCoinById:
    def test_valid(self):
        name, tick = core.coin_by_id("bitcoin")
        assert name == "Bitcoin"
        assert tick == "BTC"

    def test_invalid(self):
        name, tick = core.coin_by_id("nonexistent")
        assert name == "?"
