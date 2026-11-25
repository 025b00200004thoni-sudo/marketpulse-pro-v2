import asyncio, os
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
BINANCE_HOSTS = ["https://fapi.binance.com", "https://fapi1.binance.com", "https://fapi2.binance.com", "https://fapi3.binance.com"]
BYBIT_HOST = "https://api.bybit.com"
OKX_HOST = "https://www.okx.com"
TIMEFRAMES = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240"}
OKX_BARS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H"}

async def request_json(client, url, params=None):
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()

def okx_symbol(symbol):
    return symbol.replace("USDT", "-USDT") + "-SWAP"

async def get_candles(symbol, interval, limit=240):
    errors = []
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "MarketPulse/4.0"}) as client:
        # Primary: Binance USD-M Futures
        for host in BINANCE_HOSTS:
            try:
                rows = await request_json(client, host + "/fapi/v1/klines",
                    {"symbol": symbol, "interval": interval, "limit": limit})
                rows = rows[:-1]
                if not rows:
                    raise ValueError("Binance returned no candles")
                return pd.DataFrame([{"time": int(x[0]), "open": float(x[1]), "high": float(x[2]),
                    "low": float(x[3]), "close": float(x[4]), "volume": float(x[5])} for x in rows]), "Binance Futures"
            except Exception as exc:
                errors.append("Binance: " + str(exc)[:90])
        # Secondary: Bybit USDT linear perpetuals
        try:
            data = await request_json(client, BYBIT_HOST + "/v5/market/kline",
                {"category": "linear", "symbol": symbol, "interval": TIMEFRAMES[interval], "limit": min(limit, 1000)})
            if data.get("retCode") != 0:
                raise ValueError(data.get("retMsg", "Bybit API error"))
            rows = list(reversed(data.get("result", {}).get("list", [])))
            rows = rows[:-1]
            if not rows:
                raise ValueError("Bybit returned no candles")
            return pd.DataFrame([{"time": int(x[0]), "open": float(x[1]), "high": float(x[2]),
                "low": float(x[3]), "close": float(x[4]), "volume": float(x[5])} for x in rows]), "Bybit Linear"
        except Exception as exc:
            errors.append("Bybit: " + str(exc)[:90])
        # Tertiary: OKX USDT perpetual swaps
        try:
            data = await request_json(client, OKX_HOST + "/api/v5/market/candles",
                {"instId": okx_symbol(symbol), "bar": OKX_BARS[interval], "limit": str(min(limit, 300))})
            if data.get("code") != "0":
                raise ValueError(data.get("msg", "OKX API error"))
            rows = list(reversed(data.get("data", [])))
            rows = rows[:-1]
            if not rows:
                raise ValueError("OKX returned no candles")
            return pd.DataFrame([{"time": int(x[0]), "open": float(x[1]), "high": float(x[2]),
                "low": float(x[3]), "close": float(x[4]), "volume": float(x[5])} for x in rows]), "OKX Swap"
        except Exception as exc:
            errors.append("OKX: " + str(exc)[:90])
    raise RuntimeError("Semua sumber data gagal. " + " | ".join(errors))

async def get_orderbook(symbol):
    errors = []
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "MarketPulse/4.0"}) as client:
        for host in BINANCE_HOSTS:
            try:
                d = await request_json(client, host + "/fapi/v1/depth", {"symbol": symbol, "limit": 20})
                return {"bids": d["bids"][:12], "asks": d["asks"][:12]}, "Binance Futures"
            except Exception as exc:
                errors.append("Binance: " + str(exc)[:70])
        try:
            d = await request_json(client, BYBIT_HOST + "/v5/market/orderbook",
                {"category": "linear", "symbol": symbol, "limit": 25})
            if d.get("retCode") != 0: raise ValueError(d.get("retMsg", "Bybit API error"))
            result = d["result"]
            return {"bids": result["b"][:12], "asks": result["a"][:12]}, "Bybit Linear"
        except Exception as exc:
            errors.append("Bybit: " + str(exc)[:70])
        try:
            d = await request_json(client, OKX_HOST + "/api/v5/market/books",
                {"instId": okx_symbol(symbol), "sz": "20"})
            if d.get("code") != "0": raise ValueError(d.get("msg", "OKX API error"))
            result = d["data"][0]
            return {"bids": result["bids"][:12], "asks": result["asks"][:12]}, "OKX Swap"
        except Exception as exc:
            errors.append("OKX: " + str(exc)[:70])
    raise RuntimeError("Order book semua provider gagal. " + " | ".join(errors))

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
    bull = sum([ema9.iloc[-1] > ema21.iloc[-1], price > ema50.iloc[-1], macd.iloc[-1] > macd_signal.iloc[-1], 50 < rv < 72])
    bear = sum([ema9.iloc[-1] < ema21.iloc[-1], price < ema50.iloc[-1], macd.iloc[-1] < macd_signal.iloc[-1], 28 < rv < 50])
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
    return {"status": "ok", "service": "MarketPulse proxy", "providers": ["Binance Futures", "Bybit Linear", "OKX Swap"],
        "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/futures/dashboard")
async def futures_dashboard(interval: str = Query("5m")):
    if interval not in INTERVALS: return {"error": "Timeframe tidak didukung"}
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
    if symbol not in SYMBOLS or interval not in INTERVALS: return {"error": "Symbol atau timeframe tidak didukung"}
    async def candles_task():
        df, provider = await get_candles(symbol, interval, 160)
        return [{"time": int(r.time)//1000, "open": r.open, "high": r.high, "low": r.low, "close": r.close}
            for r in df.to_dict("records")], provider
    candles_result, book_result = await asyncio.gather(candles_task(), get_orderbook(symbol), return_exceptions=True)
    errors = []
    if isinstance(candles_result, Exception): errors.append("Candles: " + str(candles_result))
    if isinstance(book_result, Exception): errors.append("Order book: " + str(book_result))
    if errors: return {"error": " | ".join(errors)[:700]}
    candles, candle_provider = candles_result
    book, book_provider = book_result
    return {"symbol": symbol, "candles": candles, "orderbook": book,
        "providers": {"candles": candle_provider, "orderbook": book_provider},
        "server_time": datetime.now(timezone.utc).isoformat()}
