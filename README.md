# MarketPulse Crypto Futures

Dashboard analisis futures dengan sinyal LONG / SHORT / WAIT, candlestick, order book, dan indikator teknikal.

## Fitur
- Server-side market data proxy: browser hanya memanggil endpoint MarketPulse sendiri.
- Fallback provider berurutan: Binance USD-M Futures, Bybit Linear, lalu OKX USDT Swap.
- Live candlestick melalui polling backend (tidak membuka WebSocket bursa langsung dari browser).
- Sinyal berbasis EMA 9/21/50, RSI 14, MACD, ATR.
- Entry, Stop Loss, TP1–TP4 (1R, 1.5R, 2R, 3R).
- Refresh sinyal 15 detik, chart/order book 5 detik.
- Notifikasi browser saat sinyal berubah arah.

## Jalankan lokal
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```
Buka http://localhost:8000

## Deploy ke Render
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Region yang disarankan: Singapore
- Root directory: kosong (repository root)

Render akan menyediakan URL publik `onrender.com` setelah deploy berhasil. Deploy membutuhkan workspace Render yang dapat membuat Web Service.

## API proxy
- `/api/health` — status aplikasi
- `/api/futures/dashboard?interval=5m` — ringkasan sinyal
- `/api/futures/market/BTCUSDT?interval=5m` — candles dan order book

Sumber data market publik tidak memerlukan API key. Backend mencoba Binance, Bybit, lalu OKX; jika semua gagal, respons menyertakan pesan error provider. Tidak ada API key yang disimpan di browser dan tidak ada eksekusi order otomatis.

## Catatan risiko
Sinyal bersifat informasional, bukan jaminan profit atau nasihat investasi. Selalu uji strategi, hitung biaya transaksi, funding, slippage, leverage, dan risiko likuidasi sebelum trading.
