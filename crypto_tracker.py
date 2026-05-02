import dearpygui.dearpygui as dpg
import os
import requests
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

# ── XWayland auth fix ─────────────────────────────────────────
def _setup_xwayland_auth():
    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        return
    xauth = os.environ.get("XAUTHORITY", "")
    if xauth and Path(xauth).exists():
        return
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "args"], text=True, timeout=3
        )
        for line in out.splitlines():
            if "Xwayland" in line and "-auth" in line:
                parts = line.split()
                idx = parts.index("-auth")
                xauth_path = parts[idx + 1]
                if Path(xauth_path).exists():
                    os.environ["XAUTHORITY"] = xauth_path
                    return
    except Exception:
        pass

_setup_xwayland_auth()

# ── config ────────────────────────────────────────────────────
BINANCE_SYMBOLS = {
    "bitcoin":  ("Bitcoin",  "BTC", "BTCUSDT"),
    "ethereum": ("Ethereum", "ETH", "ETHUSDT"),
    "ripple":   ("XRP",      "XRP", "XRPUSDT"),
    "cardano":  ("Cardano",  "ADA", "ADAUSDT"),
    "solana":   ("Solana",   "SOL", "SOLUSDT"),
}

SYMBOLS_PARAM = '["' + '","'.join(s["BTCUSDT"] if isinstance(s, dict) else s[2] for s in BINANCE_SYMBOLS.values()) + '"]'
BINANCE_URL = "https://api.binance.com/api/v3/ticker/24hr"
FX_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"

MAX_POINTS = 60
COLORS = [
    (247, 147, 26),   # Bitcoin  – orange
    (60,  130, 246),  # Ethereum – blue
    (38,  196, 133),  # XRP      – green
    (0,   102, 255),  # Cardano  – royal blue
    (149, 69,  223),  # Solana   – purple
]

# ── state ─────────────────────────────────────────────────────
price_history = {coin_id: deque(maxlen=MAX_POINTS) for coin_id in BINANCE_SYMBOLS}
running = True
current_prices = {}    # {coin_id: (price_usd, change_pct)}
eur_rate = 1.0          # USD to EUR conversion rate
display_currency = "USD"


def fetch_fx_rate():
    """Fetch USD→EUR rate from free CDN-hosted API."""
    global eur_rate
    try:
        r = requests.get(FX_URL, timeout=10)
        if r.status_code == 200:
            data = r.json()
            eur_rate = float(data["usd"]["eur"])
    except Exception:
        pass


def fetch_prices():
    """Thread target: polls Binance every 5s."""
    global running, current_prices
    fetch_fx_rate()
    while running:
        try:
            resp = requests.get(BINANCE_URL, params={"symbols": SYMBOLS_PARAM}, timeout=10)
            if resp.status_code == 200:
                for ticker in resp.json():
                    symbol = ticker["symbol"]
                    for coin_id, (name, tick, sym) in BINANCE_SYMBOLS.items():
                        if sym == symbol:
                            price = float(ticker["lastPrice"])
                            change = float(ticker["priceChangePercent"])
                            current_prices[coin_id] = (price, change)
                            break
        except Exception:
            pass
        time.sleep(5)


def update_ui():
    """Called every frame. Pushes latest data to UI."""
    for i, coin_id in enumerate(BINANCE_SYMBOLS):
        if coin_id not in current_prices:
            continue
        price_usd, change = current_prices[coin_id]

        if display_currency == "EUR":
            price = price_usd * eur_rate
            symbol = "€"
        else:
            price = price_usd
            symbol = "$"

        price_history[coin_id].append(price)

        name, ticker, _ = BINANCE_SYMBOLS[coin_id]
        dpg.set_value(f"price_{coin_id}", f"{symbol}{price:,.2f}")
        dpg.set_value(f"change_{coin_id}", f"{change:+.2f}%")

        color = [*COLORS[i], 255] if change >= 0 else [255, 80, 80, 255]
        dpg.configure_item(f"change_{coin_id}", color=color)

        hist = list(price_history[coin_id])
        if len(hist) >= 2:
            xs = list(range(len(hist)))
            dpg.set_value(f"series_{coin_id}", [xs, hist])


def on_currency_select(sender, app_data):
    global display_currency
    display_currency = app_data
    # clear history so old USD points don't mix with EUR
    for h in price_history.values():
        h.clear()
    # update axis label
    dpg.set_item_label("y_axis", f"Price ({display_currency})")


# ── DPG setup ─────────────────────────────────────────────────
dpg.create_context()
dpg.set_global_font_scale(1.4)

# main window
with dpg.window(label="Crypto Tracker", tag="main_win", no_scrollbar=True):
    # header row: title + currency selector
    with dpg.group(horizontal=True):
        dpg.add_text("Crypto Price Tracker", color=[255, 255, 255, 255])
        dpg.add_spacer(width=20)
        dpg.add_text("Currency:", color=[140, 140, 140])
        dpg.add_combo(
            items=["USD", "EUR"],
            default_value="USD",
            callback=on_currency_select,
            width=80,
        )
    dpg.add_spacer(height=6)

    # plot
    with dpg.plot(label="Price", height=-1, width=-1):
        dpg.add_plot_legend()
        dpg.add_plot_axis(dpg.mvXAxis, label="Time (samples)", no_tick_labels=True)
        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Price (USD)", tag="y_axis")

        for i, coin_id in enumerate(BINANCE_SYMBOLS):
            name, ticker, _ = BINANCE_SYMBOLS[coin_id]
            dpg.add_line_series(
                [], [], label=f"{name} ({ticker})",
                parent="y_axis", tag=f"series_{coin_id}",
            )

    dpg.add_spacer(height=10)

    # price table
    with dpg.child_window(height=170, autosize_x=True, no_scrollbar=True):
        with dpg.table(header_row=True):
            dpg.add_table_column(label="Coin", width_fixed=True, init_width_or_weight=140)
            dpg.add_table_column(label="Price", width_fixed=True, init_width_or_weight=150)
            dpg.add_table_column(label="24h Change", width_fixed=True, init_width_or_weight=120)

            for i, coin_id in enumerate(BINANCE_SYMBOLS):
                name, ticker, _ = BINANCE_SYMBOLS[coin_id]
                with dpg.table_row():
                    dpg.add_text(f"{name} ({ticker})", color=[*COLORS[i], 255])
                    dpg.add_text("--.--", tag=f"price_{coin_id}")
                    dpg.add_text("--.--%", tag=f"change_{coin_id}")


# line color themes
for i, c in enumerate(COLORS):
    with dpg.theme(tag=f"line_theme_{i}"):
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, [*c, 255], category=dpg.mvThemeCat_Plots)
    dpg.bind_item_theme(f"series_{list(BINANCE_SYMBOLS.keys())[i]}", f"line_theme_{i}")


# ── viewport ──────────────────────────────────────────────────
dpg.create_viewport(title="Crypto Price Tracker", width=900, height=700)
dpg.set_primary_window("main_win", True)
dpg.setup_dearpygui()
dpg.show_viewport()

# ── start fetch thread ────────────────────────────────────────
fetch_thread = threading.Thread(target=fetch_prices, daemon=True)
fetch_thread.start()

# ── main loop ─────────────────────────────────────────────────
while dpg.is_dearpygui_running():
    update_ui()
    dpg.render_dearpygui_frame()

running = False
dpg.destroy_context()
