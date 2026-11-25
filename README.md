# MarketPulse Crypto Futures

Dashboard analisis futures dengan sinyal LONG / SHORT / WAIT, candlestick, order book, dan indikator teknikal.

## Fitur
- Server-side market data proxy: browser hanya memanggil endpoint MarketPulse sendiri.
- Sumber data candle: CoinGlass API V4, dengan data exchange Binance Futures.
- Candlestick melalui polling backend CoinGlass (tidak mengakses API bursa langsung dari browser).
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
- `/api/health` — status aplikasi dan konfigurasi API key
- `/api/futures/dashboard?interval=5m` — ringkasan sinyal
- `/api/futures/market/BTCUSDT?interval=5m` — candles dan order book

Sumber data memakai CoinGlass API V4 dan membutuhkan paket API serta API key. Atur environment variable `COINGLASS_API_KEY` di server Render (Environment). Jangan menaruh API key di file kode, frontend, atau repository GitHub. Endpoint candle futures yang digunakan adalah `/api/futures/price/history` dengan `exchange=Binance`. Paket CoinGlass menentukan interval terendah dan batas request. Integrasi order book L2 belum diaktifkan pada versi ini; dashboard menampilkan status, bukan data order book palsu. Tidak ada API key yang dikirim ke browser dan tidak ada eksekusi order otomatis.

## Catatan risiko
Sinyal bersifat informasional, bukan jaminan profit atau nasihat investasi. Selalu uji strategi, hitung biaya transaksi, funding, slippage, leverage, dan risiko likuidasi sebelum trading.


## Menyiapkan CoinGlass API
1. Buat/aktifkan API key di akun CoinGlass dan pastikan paket API memiliki akses ke Futures Price History.
2. Di Render, buka service MarketPulse → Environment → Add Environment Variable.
3. Isi Key `COINGLASS_API_KEY` dan Value dengan API key CoinGlass Anda, lalu simpan agar service melakukan deploy ulang.
4. Periksa `/api/health`; `api_key_configured` harus bernilai `true`.

Catatan: API CoinGlass memerlukan header `CG-API-KEY`. Respons HTTP 200 belum tentu berarti sukses; backend juga memeriksa field `code` bernilai `0`.
