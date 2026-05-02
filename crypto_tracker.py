"""Crypto Price Tracker — Dear PyGui desktop app."""

import dearpygui.dearpygui as dpg
import datetime
import os
import subprocess
import threading
import time
from pathlib import Path

import core


# ── XWayland auth ─────────────────────────────────────────────
def _fix_xauth():
    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        return
    xauth = os.environ.get("XAUTHORITY", "")
    if xauth and Path(xauth).exists():
        return
    try:
        out = subprocess.check_output(["ps", "-eo", "args"], text=True, timeout=3)
        for line in out.splitlines():
            if "Xwayland" in line and "-auth" in line:
                parts = line.split()
                idx = parts.index("-auth")
                p = parts[idx + 1]
                if Path(p).exists():
                    os.environ["XAUTHORITY"] = p
                    return
    except Exception:
        pass


_fix_xauth()
core.init()


# ── bg thread ─────────────────────────────────────────────────
def _fetch_loop():
    while True:
        core.fetch_all()
        time.sleep(core.FETCH_INTERVAL)


threading.Thread(target=_fetch_loop, daemon=True).start()

# ── UI state ──────────────────────────────────────────────────
selected = core.COINS[0][0]


def on_select(sender, app_data, user_data):
    global selected
    new = user_data
    if new == selected:
        return
    dpg.set_value(f"sel_{selected}", False)
    selected = new
    dpg.set_value(f"sel_{new}", True)


def on_currency(sender, app_data):
    core.set_currency(app_data)


# ── DPG setup ─────────────────────────────────────────────────
dpg.create_context()

with dpg.font_registry():
    font = dpg.add_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
dpg.bind_font(font)

for i, c in enumerate(core.COLORS):
    with dpg.theme(tag=f"theme_{i}"):
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(
                dpg.mvPlotCol_Line, [*c, 255], category=dpg.mvThemeCat_Plots
            )
    with dpg.theme(tag=f"scatter_theme_{i}"):
        with dpg.theme_component(dpg.mvScatterSeries):
            dpg.add_theme_color(
                dpg.mvPlotCol_Line, [*c, 255], category=dpg.mvThemeCat_Plots
            )
            dpg.add_theme_style(
                dpg.mvPlotStyleVar_Marker, dpg.mvPlotMarker_Circle, category=dpg.mvThemeCat_Plots
            )
            dpg.add_theme_style(
                dpg.mvPlotStyleVar_MarkerSize, 6, category=dpg.mvThemeCat_Plots
            )

with dpg.window(label="Crypto Tracker", tag="win", no_scrollbar=True):
    with dpg.group(horizontal=True):
        dpg.add_text("Crypto Price Tracker", color=[255, 255, 255, 255])
        dpg.add_spacer(width=20)
        dpg.add_text("Currency:", color=[140, 140, 140])
        dpg.add_combo(
            items=["USD", "EUR"], default_value="USD", callback=on_currency, width=80
        )
    dpg.add_spacer(height=6)

    with dpg.child_window(height=180, autosize_x=True, no_scrollbar=True, tag="table"):
        with dpg.table(header_row=True):
            dpg.add_table_column(
                label="Coin", width_fixed=True, init_width_or_weight=150
            )
            dpg.add_table_column(
                label="Price", width_fixed=True, init_width_or_weight=150
            )
            dpg.add_table_column(
                label="24h Change", width_fixed=True, init_width_or_weight=130
            )

            for coin_id, name, tick, _ in core.COINS:
                idx = [c[0] for c in core.COINS].index(coin_id)
                with dpg.table_row():
                    dpg.add_selectable(
                        label=f"  {name} ({tick})",
                        tag=f"sel_{coin_id}",
                        default_value=(coin_id == selected),
                        callback=on_select,
                        user_data=coin_id,
                    )
                    dpg.add_text("--.--", tag=f"price_{coin_id}")
                    dpg.add_text("--.--%", tag=f"change_{coin_id}")

    dpg.add_spacer(height=6)

    with dpg.child_window(height=-1, autosize_x=True, no_scrollbar=True, tag="plot"):
        with dpg.plot(label="Price", height=-1, width=-1):
            dpg.add_plot_legend()
            dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="xax", no_gridlines=False)
            dpg.add_plot_axis(dpg.mvYAxis, label="Price (USD)", tag="yax")
            dpg.add_line_series(
                [0], [0], label="Loading...", parent="yax", tag="series"
            )
            dpg.add_scatter_series(
                [], [], label="", parent="yax", tag="points"
            )
            dpg.add_plot_annotation(
                label="", tag="last_annot", default_value=(0, 0),
                color=[255, 255, 200, 255], clamped=True, offset=(15, -10),
            )

    dpg.bind_item_theme("series", "theme_0")
    dpg.bind_item_theme("points", "scatter_theme_0")


dpg.create_viewport(title="Crypto Price Tracker", width=900, height=700)

icon_path = Path(__file__).parent / "icon.png"
if icon_path.exists():
    try:
        w, h, _channels, data = dpg.load_image(str(icon_path))
        with dpg.texture_registry():
            dpg.add_static_texture(
                width=w, height=h, default_value=data, tag="icon_tex"
            )
        dpg.set_viewport_small_icon("icon_tex")
    except Exception:
        pass

dpg.set_primary_window("win", True)


def on_resize():
    vp_h = dpg.get_viewport_height()
    dpg.configure_item("table", height=190)
    dpg.configure_item("plot", height=vp_h - 290)


dpg.set_viewport_resize_callback(on_resize)

dpg.setup_dearpygui()
dpg.show_viewport()

# ── main loop ─────────────────────────────────────────────────
last_data_hash = 0
last_rebind = -1
while dpg.is_dearpygui_running():
    sym = core.currency_symbol()
    for coin_id, name, tick, _ in core.COINS:
        p = core.price_in_currency(coin_id)
        if p is not None:
            dpg.set_value(f"price_{coin_id}", f"{sym}{p:,.2f}")
        ch = core.change_pct(coin_id)
        if ch is not None:
            dpg.set_value(f"change_{coin_id}", f"{ch:+.2f}%")
            dpg.configure_item(f"change_{coin_id}", color=core.change_color(coin_id))

    xs, ys = core.series_data(selected)
    if xs is not None:
        indices = list(range(len(xs)))
        dpg.set_value("series", [indices, ys])
        dpg.set_value("points", [indices, ys])

    name, tick = core.coin_by_id(selected)
    p = core.price_in_currency(selected)
    label = f"{name} ({tick})"
    if p is not None:
        label += f"  —  {sym}{p:,.2f}"
    dpg.set_item_label("series", label)
    dpg.set_item_label("yax", f"Price ({'EUR' if sym == '€' else 'USD'})")

    if xs is not None and len(ys) >= 2:
        new_hash = hash((selected, xs[0], xs[-1], ys[0], ys[-1]))
        if new_hash != last_data_hash:
            last_data_hash = new_hash
            margin = (max(ys) - min(ys)) * 0.02 or 0.5
            dpg.set_axis_limits("yax", min(ys) - margin, max(ys) + margin)
            dpg.set_axis_limits("xax", -1, len(xs))
            # Ticks every ~10 min
            step = 10
            ticks = [
                (datetime.datetime.fromtimestamp(xs[i]).strftime("%H:%M"), i)
                for i in range(0, len(xs), step)
            ]
            dpg.set_axis_ticks("xax", tuple(ticks))
        # Annotation at the last point
        last_idx = len(xs) - 1
        last_time = datetime.datetime.fromtimestamp(xs[last_idx]).strftime("%H:%M")
        sym_cur = core.currency_symbol()
        dpg.set_value("last_annot", (last_idx, ys[last_idx]))
        dpg.set_item_label("last_annot", f"{sym_cur}{ys[last_idx]:,.2f} at {last_time}")

    idx = [c[0] for c in core.COINS].index(selected)
    if idx != last_rebind:
        dpg.bind_item_theme("series", f"theme_{idx}")
        dpg.bind_item_theme("points", f"scatter_theme_{idx}")
        last_rebind = idx

    dpg.render_dearpygui_frame()

dpg.destroy_context()
