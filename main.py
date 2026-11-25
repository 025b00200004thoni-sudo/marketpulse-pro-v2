import os, asyncio
from datetime import datetime, timezone
from pathlib import Path
import httpx
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="MarketPulse Crypto Futures")
BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

SYMBOLS = {"BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana"}
INTERVALS = {"1m", "5m", "15m", "1h", "4h"}
FAPI = "https://fapi.binance.com"

async def get_json(path, params=None):
    async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "MarketPulse/3.0"}) as client:
        response = await client.get(FAPI + path, params=params)
        response.raise_for_status()
        return response.json()

async def futures_candles(symbol, interval, limit=240):
    rows = await get_json("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    # Exclude the still-forming candle to avoid premature signals.
    rows = rows[:-1]
    return pd.DataFrame([{
        "time": int(x[0]), "open": float(x[1]), "high": float(x[2]),
        "low": float(x[3]), "close": float(x[4]), "volume": float(x[5])
    } for x in rows])

def build_signal(df, symbol, interval):
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
    # ATR-based levels. Targets are staged at 1R, 1.5R, 2R and 3R.
    risk = max(av * 1.35, price * 0.0012)
    entry = price if side != "WAIT" else None
    if side == "LONG":
        sl = price-risk
        targets = [price+risk*k for k in (1, 1.5, 2, 3)]
    elif side == "SHORT":
        sl = price+risk
        targets = [price-risk*k for k in (1, 1.5, 2, 3)]
    else:
        sl, targets = None, [None]*4
    return {
        "symbol": symbol, "name": SYMBOLS[symbol], "timeframe": interval,
        "signal": side, "price": price, "entry": entry, "sl": sl,
        "tp1": targets[0], "tp2": targets[1], "tp3": targets[2], "tp4": targets[3],
        "rsi": rv, "atr": av, "ema9": float(ema9.iloc[-1]),
        "ema21": float(ema21.iloc[-1]), "ema50": float(ema50.iloc[-1]),
        "bull_score": int(bull), "bear_score": int(bear),
        "confidence": int(max(bull, bear) * 25),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "static" / "index.html").read_text()

@app.get("/api/health")
async def health():
    return {"status": "ok", "market": "Binance USD-M Futures", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/futures/dashboard")
async def futures_dashboard(interval: str = Query("5m")):
    if interval not in INTERVALS:
        return {"error": "Timeframe tidak didukung"}
    async def one(symbol):
        try:
            df = await futures_candles(symbol, interval)
            return symbol, build_signal(df, symbol, interval), None
        except Exception as exc:
            return symbol, None, str(exc)[:180]
    results = await asyncio.gather(*(one(s) for s in SYMBOLS))
    assets, errors = {}, {}
    for symbol, data, error in results:
        if data: assets[symbol] = data
        if error: errors[symbol] = error
    return {"assets": assets, "errors": errors, "interval": interval,
            "server_time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/futures/market/{symbol}")
async def futures_market(symbol: str, interval: str = Query("5m")):
    symbol = symbol.upper()
    if symbol not in SYMBOLS or interval not in INTERVALS:
        return {"error": "Symbol tidak didukung"}
    async def candles_task():
        rows = await futures_candles(symbol, interval, 160)
        return [{"time": int(r.time), "open": r.open, "high": r.high, "low": r.low, "close": r.close} for r in rows.to_dict("records")]
    async def book_task():
        data = await get_json("/fapi/v1/depth", {"symbol": symbol, "limit": 20})
        return {"bids": data["bids"][:12], "asks": data["asks"][:12]}
    candles, book = await asyncio.gather(candles_task(), book_task())
    return {"symbol": symbol, "candles": candles, "orderbook": book,
            "server_time": datetime.now(timezone.utc).isoformat()}
