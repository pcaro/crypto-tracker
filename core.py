"""Core data layer — pure Python, no UI, fully testable."""

import threading
from collections import deque

import requests

# ── config ────────────────────────────────────────────────────
COINS = [
    ("bitcoin", "Bitcoin", "BTC", "BTCUSDT"),
    ("ethereum", "Ethereum", "ETH", "ETHUSDT"),
    ("solana", "Solana", "SOL", "SOLUSDT"),
    ("ripple", "XRP", "XRP", "XRPUSDT"),
    ("cardano", "Cardano", "ADA", "ADAUSDT"),
]

COLORS = [
    (247, 147, 26),
    (60, 130, 246),
    (149, 69, 223),
    (38, 196, 133),
    (0, 102, 255),
]

MAX_POINTS = 60
FETCH_INTERVAL = 30

# ── state ─────────────────────────────────────────────────────
_lock = threading.Lock()
_prices = {}  # coin_id -> (usd_price, change_pct)
_history = {}  # coin_id -> deque of USD closes
_eur_rate = 1.0
_currency = "USD"


def init():
    """Reset state for a fresh start."""
    global _prices, _history, _eur_rate, _currency
    with _lock:
        _prices = {}
        _history = {c[0]: deque(maxlen=MAX_POINTS) for c in COINS}
        _eur_rate = 1.0
        _currency = "USD"


def apply_prices(ticker_list):
    """Parse a Binance 24hr ticker JSON list into state.

    ticker_list: list of dicts with 'symbol', 'lastPrice', 'priceChangePercent'
    """
    with _lock:
        for t in ticker_list:
            sym = t["symbol"]
            for cid, _, _, bsym in COINS:
                if sym == bsym:
                    _prices[cid] = (
                        float(t["lastPrice"]),
                        float(t["priceChangePercent"]),
                    )
                    break


def apply_klines(coin_id, kline_list):
    """Store 1m kline closes for a coin.

    kline_list: list of Binance kline lists; open_time is index 0, close is index 4.
    """
    points = [(int(k[0]) / 1000, float(k[4])) for k in kline_list]  # ms -> s
    with _lock:
        _history[coin_id] = deque(points, maxlen=MAX_POINTS)


def set_eur_rate(rate):
    global _eur_rate
    with _lock:
        _eur_rate = float(rate)


def set_currency(cur):
    global _currency
    with _lock:
        _currency = cur


# ── queries (thread-safe) ─────────────────────────────────────


def price(coin_id):
    """Return (usd_price, change_pct) or (None, None)."""
    with _lock:
        p = _prices.get(coin_id)
    if p is None:
        return None, None
    return p


def price_in_currency(coin_id):
    """Return price converted to current display currency, or None."""
    p, _ = price(coin_id)
    if p is None:
        return None
    with _lock:
        cur = _currency
        rate = _eur_rate
    if cur == "EUR":
        return p * rate
    return p


def series_data(coin_id):
    """Return (timestamps, prices) in display currency, or (None, None)."""
    with _lock:
        h = list(_history.get(coin_id, []))
        cur = _currency
        rate = _eur_rate
    if len(h) < 2:
        return None, None
    ts = [t for t, _ in h]
    ys = [p * rate if cur == "EUR" else p for _, p in h]
    return ts, ys


def currency_symbol():
    return "€" if _currency == "EUR" else "$"


def change_pct(coin_id):
    """Return 24h change percentage or None."""
    _, ch = price(coin_id)
    return ch


def change_color(coin_id):
    """RGBA: coin color if change >= 0, red otherwise."""
    _, ch = price(coin_id)
    if ch is None:
        return [255, 255, 255, 255]
    idx = [c[0] for c in COINS].index(coin_id)
    if ch >= 0:
        return [*COLORS[idx], 255]
    return [255, 80, 80, 255]


def coin_by_id(coin_id):
    """Return (name, tick) for a coin_id."""
    for cid, name, tick, _ in COINS:
        if cid == coin_id:
            return name, tick
    return "?", "?"


# ── fetchers ──────────────────────────────────────────────────


def fetch_eur_rate():
    """Return EUR/USD rate from CDN, or None on failure."""
    try:
        r = requests.get(
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            timeout=10,
        )
        if r.status_code == 200:
            return float(r.json()["usd"]["eur"])
    except Exception:
        pass
    return None


def fetch_tickers():
    """Return list of Binance 24h ticker dicts, or None on failure."""
    syms = '["' + '","'.join(c[3] for c in COINS) + '"]'
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbols": syms},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def fetch_klines(symbol):
    """Return list of kline lists from Binance, or None on failure."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": "1m", "limit": MAX_POINTS},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ── orchestration ─────────────────────────────────────────────


def fetch_all():
    """Fetch everything and update state. Returns True if tickers succeeded."""
    rate = fetch_eur_rate()
    if rate is not None:
        set_eur_rate(rate)

    tickers = fetch_tickers()
    ok = tickers is not None
    if tickers is not None:
        apply_prices(tickers)

    for cid, _, _, bsym in COINS:
        klines = fetch_klines(bsym)
        if klines is not None:
            apply_klines(cid, klines)

    return ok
