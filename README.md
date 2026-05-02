# Crypto Tracker

Live desktop app that displays real-time prices for 5 cryptocurrencies with GPU-accelerated charts.

Built with [Dear PyGui](https://github.com/hoffstadt/DearPyGui) and the free [CoinGecko API](https://www.coingecko.com/en/api).

## Tracked coins

| Coin | Ticker |
|------|--------|
| Bitcoin | BTC |
| Ethereum | ETH |
| XRP | XRP |
| Cardano | ADA |
| Solana | SOL |

## Features

- **Live line chart** — price history for all 5 coins, updating every 5 seconds
- **Price table** — current USD price + 24h change (green up, red down)
- **Color-coded** — each coin has a distinct color in both chart and table
- **Zero config** — no API key required, uses CoinGecko's free tier

## Requirements

- Python ≥ 3.14
- [uv](https://docs.astral.sh/uv/) (package manager)
- A display server (X11/Wayland) — Dear PyGui needs a windowing context

## Quick start

```bash
git clone https://github.com/pcaro/crypto-tracker.git
cd crypto-tracker
uv run python3 crypto_tracker.py
```

## How it works

A background thread fetches prices from CoinGecko every 5 seconds. The DPG render loop consumes the latest data each frame, pushing it to the chart and table widgets.

## License

MIT
