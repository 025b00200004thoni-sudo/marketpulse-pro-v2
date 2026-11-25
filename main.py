import asyncio, os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="MarketPulse Twelve Data")
BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

# Frontend aliases are mapped to Twelve Data digital-currency pairs.
SYMBOLS = {
    "BTCUSD": {"name": "Bitcoin", "td": "BTC/USD"},
    "ETHUSD": {"name": "Ethereum", "td": "ETH/USD"},
    "SOLUSD": {"name": "Solana", "td": "SOL/USD"},
}
INTERVALS = {"1min", "5min", "15min", "1h", "4h"}
TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"

def td_headers():
    key = os.getenv("TWELVE_DATA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY belum dipasang di environment server.")
    return {"Authorization": "apikey " + key, "Accept": "application/json",
            "User-Agent": "MarketPulse/6.0"}

async def get_candles(alias, interval, outputsize=240):
    if alias not in SYMBOLS:
        raise ValueError("Symbol tidak didukung.")
    params = {
        "symbol": SYMBOLS[alias]["td"],
        "interval": interval,
        "outputsize": min(outputsize, 5000),
        "timezone": "UTC",
        "order": "ASC",
        "format": "JSON",
    }
    async with httpx.AsyncClient(timeout=20, headers=td_headers()) as client:
        response = await client.get(TWELVE_DATA_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    if payload.get("status") == "error" or "values" not in payload:
        message = payload.get("message", payload.get("code", "Unknown Twelve Data error"))
        raise RuntimeError("Twelve Data: " + str(message))
    values = payload.get("values") or []
    if not values:
        raise RuntimeError("Twelve Data tidak mengembalikan candle untuk " + SYMBOLS[alias]["td"])
    rows = []
    for item in values:
        stamp = pd.to_datetime(item["datetime"], utc=True, errors="coerce")
        if pd.isna(stamp):
            continue
        rows.append({
            "time": int(stamp.timestamp() * 1000),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "volume": float(item.get("volume") or 0),
        })
    df = pd.DataFrame(rows).sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if len(df) < 55:
        raise RuntimeError("Data candle kurang dari 55 bar; indikator belum dapat dihitung.")
    return df, "Twelve Data"

def build_signal(df, alias, interval, provider):
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
    return {
        "symbol": alias, "name": SYMBOLS[alias]["name"], "timeframe": interval,
        "provider": provider, "signal": side, "price": price, "entry": entry,
        "sl": sl, "tp1": targets[0], "tp2": targets[1], "tp3": targets[2],
        "tp4": targets[3], "rsi": rv, "atr": av, "ema9": float(ema9.iloc[-1]),
        "ema21": float(ema21.iloc[-1]), "ema50": float(ema50.iloc[-1]),
        "bull_score": int(bull), "bear_score": int(bear),
        "confidence": int(max(bull, bear)*25),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "static" / "index.html").read_text()

@app.get("/api/health")
async def health():
    configured = bool(os.getenv("TWELVE_DATA_API_KEY", "").strip())
    return {
        "status": "ok" if configured else "needs_api_key",
        "service": "MarketPulse Twelve Data proxy",
        "provider": "Twelve Data REST API",
        "api_key_configured": configured,
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/futures/dashboard")
async def futures_dashboard(interval: str = Query("5min")):
    if interval not in INTERVALS:
        return {"error": "Timeframe tidak didukung"}
    async def one(alias):
        try:
            df, provider = await get_candles(alias, interval)
            return alias, build_signal(df, alias, interval, provider), None
        except Exception as exc:
            return alias, None, str(exc)[:350]
    results = await asyncio.gather(*(one(s) for s in SYMBOLS))
    assets, errors = {}, {}
    for alias, data, error in results:
        if data:
            assets[alias] = data
        if error:
            errors[alias] = error
    return {
        "assets": assets, "errors": errors, "providers": ["Twelve Data"] if assets else [],
        "interval": interval, "server_time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/futures/market/{symbol}")
async def futures_market(symbol: str, interval: str = Query("5min")):
    alias = symbol.upper()
    if alias not in SYMBOLS or interval not in INTERVALS:
        return {"error": "Symbol atau timeframe tidak didukung"}
    try:
        df, provider = await get_candles(alias, interval, 240)
        candles = [{
            "time": int(r["time"])//1000, "open": r["open"], "high": r["high"],
            "low": r["low"], "close": r["close"]
        } for r in df.to_dict("records")]
        return {
            "symbol": alias, "candles": candles,
            "orderbook": {"bids": [], "asks": []},
            "orderbook_note": "Twelve Data time_series tidak menyediakan order book L2.",
            "providers": {"candles": provider, "orderbook": "not available"},
            "server_time": datetime.now(timezone.utc).isoformat()
        }
    except Exception as exc:
        return {"error": str(exc)[:700]}
