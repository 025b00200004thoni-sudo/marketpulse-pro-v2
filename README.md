# MarketPulse Crypto Futures

Dashboard analisis futures Binance USDⓈ-M untuk BTCUSDT, ETHUSDT, dan SOLUSDT.

## Fitur
- Live candlestick chart dan order book dari Binance Futures public REST API.
- Sinyal LONG / SHORT / WAIT berbasis EMA 9/21/50, RSI 14, MACD, ATR.
- Entry, Stop Loss, TP1, TP2, TP3, TP4 (target 1R, 1.5R, 2R, 3R).
- Refresh sinyal 15 detik, order book dan chart 5 detik.
- Notifikasi browser saat sinyal berubah arah.

## Jalankan lokal
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```
Buka http://localhost:8000

## Render
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Runtime: Python 3

Data market memakai endpoint publik Binance USDⓈ-M Futures. Tidak ada API key dan tidak ada eksekusi order otomatis.

## Catatan
Sinyal bersifat informasional, bukan jaminan profit. Selalu uji strategi, hitung biaya transaksi, funding, slippage, leverage, dan risiko likuidasi sebelum trading.
