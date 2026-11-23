import os, asyncio
from datetime import datetime, timezone
import httpx
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app=FastAPI(title="MarketPulse Pro V2")
BASE=Path(__file__).parent
app.mount("/static",StaticFiles(directory=BASE/"static"),name="static")
KEY=os.getenv("TWELVE_DATA_API_KEY","")
FRAMES={"M1":"1min","M5":"5min","M15":"15min"}
ASSETS={"XAUUSD":"XAU/USD","NASDAQ":"NDX","BTCUSD":"BTC/USDT"}

async def candles(asset, interval):
    async with httpx.AsyncClient(timeout=15) as c:
        if asset=="BTCUSD":
            r=await c.get("https://api.binance.com/api/v3/klines",params={"symbol":"BTCUSDT","interval":interval.replace("min","m"),"limit":220})
            r.raise_for_status()
            rows=r.json()[:-1]
            d=pd.DataFrame([{"time":x[0],"open":float(x[1]),"high":float(x[2]),"low":float(x[3]),"close":float(x[4])} for x in rows])
        else:
            if not KEY: raise RuntimeError("TWELVE_DATA_API_KEY belum diatur di Render")
            r=await c.get("https://api.twelvedata.com/time_series",params={"symbol":ASSETS[asset],"interval":interval,"outputsize":220,"apikey":KEY,"timezone":"UTC"})
            r.raise_for_status(); p=r.json()
            if "values" not in p: raise RuntimeError(p.get("message","Data provider tidak tersedia"))
            d=pd.DataFrame(p["values"]).rename(columns={"datetime":"time"})
            for k in ("open","high","low","close"): d[k]=pd.to_numeric(d[k])
            d=d.sort_values("time").iloc[:-1].reset_index(drop=True)
    return d

def analyze(d,asset,tf):
    if len(d)<60: raise RuntimeError("Candle belum cukup")
    c=d.close
    e9=c.ewm(span=9,adjust=False).mean(); e21=c.ewm(span=21,adjust=False).mean(); e50=c.ewm(span=50,adjust=False).mean()
    delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean(); loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-100/(1+gain/loss.replace(0,1e-12))
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean(); ms=macd.ewm(span=9,adjust=False).mean()
    prev=c.shift(1); tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1); atr=tr.ewm(alpha=1/14,adjust=False).mean()
    p=float(c.iloc[-1]); a=float(atr.iloc[-1]); rv=float(rsi.iloc[-1])
    bull=sum([e9.iloc[-1]>e21.iloc[-1],52<=rv<=70,macd.iloc[-1]>ms.iloc[-1],p>e50.iloc[-1]])
    bear=sum([e9.iloc[-1]<e21.iloc[-1],30<=rv<=48,macd.iloc[-1]<ms.iloc[-1],p<e50.iloc[-1]])
    side="BUY" if bull>=3 else "SELL" if bear>=3 else "WAIT"
    dist=max(a*1.2,p*.0004)
    return {"asset":asset,"timeframe":tf,"signal":side,"price":p,"entry":p if side!="WAIT" else None,
      "sl":p-dist if side=="BUY" else p+dist if side=="SELL" else None,
      "tp":p+2*dist if side=="BUY" else p-2*dist if side=="SELL" else None,
      "rsi":rv,"ema9":float(e9.iloc[-1]),"ema21":float(e21.iloc[-1]),"atr":a,"bull_score":int(bull),"bear_score":int(bear)}

@app.get("/",response_class=HTMLResponse)
async def home(): return (BASE/"static"/"index.html").read_text()

@app.get("/api/health")
async def health(): return {"status":"ok","time":datetime.now(timezone.utc).isoformat()}

@app.get("/api/dashboard")
async def dashboard():
    out={"assets":{},"errors":{},"server_time":datetime.now(timezone.utc).isoformat(),"telegram_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))}
    async def one(asset,tf):
        try:
            d=await candles(asset,FRAMES[tf]); return asset,tf,analyze(d,asset,tf),None
        except Exception as e: return asset,tf,None,str(e)[:180]
    results=await asyncio.gather(*(one(a,t) for a in ASSETS for t in FRAMES))
    for a,t,x,e in results:
        out["assets"].setdefault(a,{})
        if x: out["assets"][a][t]=x
        if e: out["errors"].setdefault(a,{})[t]=e
    for a in ASSETS:
        x=out["assets"].get(a,{}); m1=x.get("M1"); m5=x.get("M5"); m15=x.get("M15")
        if m1:
            ok=m1["signal"] in ("BUY","SELL") and m5 and m5["signal"]==m1["signal"] and m15 and m15["signal"] in (m1["signal"],"WAIT")
            m1["confirmed"]=bool(ok)
            if not ok: m1["signal"]="WAIT"
            m1["strength"]="M1 + M5 confirmed" if ok else "Menunggu konfirmasi M5/M15"
        x["errors"]=out["errors"].get(a,{})
    return out
