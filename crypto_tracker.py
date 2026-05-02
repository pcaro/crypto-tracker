import dearpygui.dearpygui as dpg
import requests
import threading
import time
from collections import deque

# ── crypto config ──────────────────────────────────────────────
COINS = {
    "bitcoin":  ("Bitcoin",  "BTC"),
    "ethereum": ("Ethereum", "ETH"),
    "ripple":   ("XRP",      "XRP"),
    "cardano":  ("Cardano",  "ADA"),
    "solana":   ("Solana",   "SOL"),
}

COIN_IDS = ",".join(COINS.keys())
API_URL = (
    f"https://api.coingecko.com/api/v3/simple/price"
    f"?ids={COIN_IDS}&vs_currencies=usd&include_24hr_change=true"
)

MAX_POINTS = 60  # 5 minutes of history at 5 s updates
COLORS = [
    (247, 147, 26),   # Bitcoin  – orange
    (60,  130, 246),  # Ethereum – blue
    (38,  196, 133),  # XRP      – green
    (0,   102, 255),  # Cardano  – royal blue
    (149, 69,  223),  # Solana   – purple
]

# ── state ──────────────────────────────────────────────────────
price_history = {coin_id: deque(maxlen=MAX_POINTS) for coin_id in COINS}
running = True
current_prices = {}


def normalize(val):
    """Return a float from a CoinGecko number (int/float/str)."""
    if isinstance(val, str):
        return float(val)
    return float(val)


def fetch_prices():
    """Thread target: polls CoinGecko every 5 seconds."""
    global running, current_prices
    while running:
        try:
            resp = requests.get(API_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for coin_id in COINS:
                    info = data.get(coin_id, {})
                    price = normalize(info.get("usd", 0))
                    change = float(info.get("usd_24h_change", 0)) * 100
                    current_prices[coin_id] = (price, change)
        except Exception:
            pass
        time.sleep(5)


def update_ui():
    """Called every frame by DPG render loop. Pushes latest data to UI."""
    for i, coin_id in enumerate(COINS):
        if coin_id not in current_prices:
            continue
        price, change = current_prices[coin_id]
        price_history[coin_id].append(price)

        # update text widgets
        name, ticker = COINS[coin_id]
        dpg.set_value(f"price_{coin_id}", f"  ${price:>10,.2f}")
        dpg.set_value(f"change_{coin_id}", f"    {change:+.2f}%")

        color = [*COLORS[i], 255] if change >= 0 else [255, 80, 80, 255]
        dpg.configure_item(f"change_{coin_id}", color=color)

        # update plot
        hist = list(price_history[coin_id])
        if len(hist) >= 2:
            xs = list(range(len(hist)))
            dpg.set_value(f"series_{coin_id}", [xs, hist])


# ── DPG setup ──────────────────────────────────────────────────
dpg.create_context()

# themes
with dpg.theme() as green_theme:
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_color(dpg.mvThemeCol_Text, [38, 196, 133, 255])

with dpg.theme() as red_theme:
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_color(dpg.mvThemeCol_Text, [255, 80, 80, 255])

with dpg.theme() as title_theme:
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_color(dpg.mvThemeCol_Text, [220, 220, 220, 255])
        dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)

# main window
with dpg.window(label="Crypto Tracker", tag="main_win", no_scrollbar=True):
    dpg.add_text("Crypto Price Tracker", color=[255, 255, 255, 255])
    dpg.bind_item_theme(dpg.last_item(), title_theme)
    dpg.add_spacer(height=6)

    # plot – one line series per coin
    with dpg.plot(label="Price (USD)", height=340, width=-1):
        dpg.add_plot_legend()
        dpg.add_plot_axis(dpg.mvXAxis, label="Time (samples)", no_tick_labels=True)
        y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="USD", tag="y_axis")

        for i, coin_id in enumerate(COINS):
            name, ticker = COINS[coin_id]
            dpg.add_line_series(
                [], [], label=f"{name} ({ticker})",
                parent="y_axis", tag=f"series_{coin_id}",
            )
            dpg.bind_item_theme(f"series_{coin_id}", f"line_theme_{i}")

    dpg.add_spacer(height=8)

    # table header
    with dpg.group(horizontal=True):
        dpg.add_text("    Coin             ", color=[140, 140, 140])
        dpg.add_text("           Price    ", color=[140, 140, 140])
        dpg.add_text("    24h Change", color=[140, 140, 140])

    dpg.add_separator()

    # one row per coin
    for i, coin_id in enumerate(COINS):
        name, ticker = COINS[coin_id]
        with dpg.group(horizontal=True, tag=f"row_{coin_id}"):
            dpg.add_text(f"  {name:<14} ({ticker})", color=[*COLORS[i], 255])
            dpg.add_text("     $---.--   ", tag=f"price_{coin_id}")
            dpg.add_text("      --.--%", tag=f"change_{coin_id}")


# line color themes
for i, c in enumerate(COLORS):
    with dpg.theme(tag=f"line_theme_{i}"):
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, [*c, 255], category=dpg.mvThemeCat_Plots)


# ── viewport ───────────────────────────────────────────────────
dpg.create_viewport(title="Crypto Price Tracker", width=750, height=600)
dpg.set_primary_window("main_win", True)
dpg.setup_dearpygui()
dpg.show_viewport()

# ── start threads ──────────────────────────────────────────────
fetch_thread = threading.Thread(target=fetch_prices, daemon=True)
fetch_thread.start()

# ── change metric to avoid warning about timing __init__ vs time ─
_ = time.time

# ── main loop ──────────────────────────────────────────────────
while dpg.is_dearpygui_running():
    update_ui()
    dpg.render_dearpygui_frame()

running = False
dpg.destroy_context()
