import asyncio, os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="MarketPulse CoinGlass Futures")
BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

SYMBOLS = {"BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana"}
INTERVALS = {"1m", "5m", "15m", "1h", "4h"}
COINGLASS_HOST = "https://open-api-v4.coinglass.com"

def cg_headers():
    key = os.getenv("COINGLASS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("COINGLASS_API_KEY belum dipasang di environment server.")
    return {"CG-API-KEY": key, "accept": "application/json", "User-Agent": "MarketPulse/5.0"}

async def cg_get(path, params=None):
    async with httpx.AsyncClient(timeout=15, headers=cg_headers()) as client:
        response = await client.get(COINGLASS_HOST + path, params=params)
        response.raise_for_status()
        payload = response.json()
    # CoinGlass can return HTTP 200 even when its business-level request failed.
    if str(payload.get("code")) != "0":
        raise RuntimeError("CoinGlass: " + str(payload.get("msg", payload.get("code", "API error"))))
    return payload.get("data")

async def get_candles(symbol, interval, limit=240):
    rows = await cg_get("/api/futures/price/history", {
        "exchange": "Binance", "symbol": symbol, "interval": interval, "limit": min(limit, 1000)
    })
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("CoinGlass tidak mengembalikan candle untuk " + symbol +
                           ". Periksa pair, timeframe, dan hak akses paket API.")
    normalized = []
    for x in rows:
        normalized.append({
            "time": int(x["time"]),
            "open": float(x["open"]),
            "high": float(x["high"]),
            "low": float(x["low"]),
            "close": float(x["close"]),
            "volume": float(x.get("volume_usd", 0) or 0)
        })
    df = pd.DataFrame(normalized).sort_values("time").drop_duplicates("time").reset_index(drop=True)
    # Do not discard the newest CoinGlass bar: endpoint returns historical OHLC records.
    if len(df) < 55:
        raise RuntimeError("Data candle CoinGlass terlalu sedikit untuk menghitung indikator.")
    return df, "CoinGlass · Binance Futures"

def build_signal(df, symbol, interval, provider):
    close = df.close
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, 1e-12))
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    prev = close.shift(1)
    tr = pd.concat([df.high-df.low, (df.high-prev).abs(), (df.low-prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    price, av, rv = float(close.iloc[-1]), float(atr.iloc[-1]), float(rsi.iloc[-1])
    bull = sum([ema9.iloc[-1] > ema21.iloc[-1], price > ema50.iloc[-1],
                macd.iloc[-1] > macd_signal.iloc[-1], 50 < rv < 72])
    bear = sum([ema9.iloc[-1] < ema21.iloc[-1], price < ema50.iloc[-1],
                macd.iloc[-1] < macd_signal.iloc[-1], 28 < rv < 50])
    side = "LONG" if bull >= 3 and bull > bear else "SHORT" if bear >= 3 and bear > bull else "WAIT"
    risk = max(av * 1.35, price * 0.0012)
    entry = price if side != "WAIT" else None
    if side == "LONG":
        sl, targets = price-risk, [price+risk*k for k in (1, 1.5, 2, 3)]
    elif side == "SHORT":
        sl, targets = price+risk, [price-risk*k for k in (1, 1.5, 2, 3)]
    else:
        sl, targets = None, [None]*4
    return {"symbol": symbol, "name": SYMBOLS[symbol], "timeframe": interval, "provider": provider,
        "signal": side, "price": price, "entry": entry, "sl": sl, "tp1": targets[0], "tp2": targets[1],
        "tp3": targets[2], "tp4": targets[3], "rsi": rv, "atr": av, "ema9": float(ema9.iloc[-1]),
        "ema21": float(ema21.iloc[-1]), "ema50": float(ema50.iloc[-1]), "bull_score": int(bull),
        "bear_score": int(bear), "confidence": int(max(bull, bear)*25),
        "updated_at": datetime.now(timezone.utc).isoformat()}

@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "static" / "index.html").read_text()

@app.get("/api/health")
async def health():
    configured = bool(os.getenv("COINGLASS_API_KEY", "").strip())
    return {"status": "ok" if configured else "needs_api_key", "service": "MarketPulse CoinGlass proxy",
            "provider": "CoinGlass API V4", "exchange_data": "Binance Futures via CoinGlass",
            "api_key_configured": configured, "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/futures/dashboard")
async def futures_dashboard(interval: str = Query("5m")):
    if interval not in INTERVALS:
        return {"error": "Timeframe tidak didukung"}
    async def one(symbol):
        try:
            df, provider = await get_candles(symbol, interval)
            return symbol, build_signal(df, symbol, interval, provider), None
        except Exception as exc:
            return symbol, None, str(exc)[:350]
    results = await asyncio.gather(*(one(s) for s in SYMBOLS))
    assets, errors = {}, {}
    for symbol, data, error in results:
        if data: assets[symbol] = data
        if error: errors[symbol] = error
    providers = sorted({x["provider"] for x in assets.values()})
    return {"assets": assets, "errors": errors, "providers": providers, "interval": interval,
            "server_time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/futures/market/{symbol}")
async def futures_market(symbol: str, interval: str = Query("5m")):
    symbol = symbol.upper()
    if symbol not in SYMBOLS or interval not in INTERVALS:
        return {"error": "Symbol atau timeframe tidak didukung"}
    try:
        df, provider = await get_candles(symbol, interval, 240)
        candles = [{"time": int(r["time"])//1000, "open": r["open"], "high": r["high"],
                    "low": r["low"], "close": r["close"]} for r in df.to_dict("records")]
        # CoinGlass OHLC endpoint is used here. A live L2 order book is a separate endpoint/plan
        # and is intentionally not fabricated from candle data.
        return {"symbol": symbol, "candles": candles, "orderbook": {"bids": [], "asks": []},
                "orderbook_note": "Order book L2 belum diaktifkan pada integrasi ini.",
                "providers": {"candles": provider, "orderbook": "not configured"},
                "server_time": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"error": str(exc)[:700]}
