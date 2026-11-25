# MarketPulse — Twelve Data

Dashboard analisis pasar crypto berbasis web HTML dengan backend FastAPI dan Twelve Data API.

## Fitur
- Data candle BTC/USD, ETH/USD, SOL/USD melalui Twelve Data.
- Timeframe 1 menit, 5 menit, 15 menit, 1 jam, dan 4 jam (ketersediaan mengikuti paket/market access akun Twelve Data).
- Chart candlestick melalui Lightweight Charts.
- Indikator EMA 9/21/50, RSI 14, MACD, ATR.
- Sinyal analisis LONG / SHORT / WAIT beserta simulasi entry, stop loss, dan TP1–TP4.
- Browser hanya memanggil backend MarketPulse; API key tidak dikirim ke frontend.
- Notifikasi browser saat sinyal berubah arah.

## Menjalankan lokal
```bash
pip install -r requirements.txt
export TWELVE_DATA_API_KEY="API_KEY_ANDA"
uvicorn main:app --host 0.0.0.0 --port 8000
```
Di Windows PowerShell, gunakan:
```powershell
$env:TWELVE_DATA_API_KEY="API_KEY_ANDA"
uvicorn main:app --host 0.0.0.0 --port 8000
```
Buka http://localhost:8000

## Deploy ke Render
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Root directory: kosong (repository root)
- Tambahkan Environment Variable:
  - Key: `TWELVE_DATA_API_KEY`
  - Value: API key dari akun Twelve Data
- Simpan perubahan environment agar Render melakukan deploy ulang.

Jangan memasukkan API key ke `index.html`, JavaScript, atau repository GitHub. Gunakan Environment Variables di server.

## Endpoint backend
- `/api/health` — status aplikasi dan status konfigurasi API key.
- `/api/futures/dashboard?interval=5min` — ringkasan sinyal tiga aset.
- `/api/futures/market/BTCUSD?interval=5min` — candle BTC/USD untuk chart.

## Catatan integrasi
- Endpoint yang digunakan adalah Twelve Data REST `/time_series`.
- Autentikasi memakai header `Authorization: apikey YOUR_API_KEY`.
- Simbol internal BTCUSD, ETHUSD, SOLUSD dipetakan ke pair BTC/USD, ETH/USD, SOL/USD.
- Timeframe frontend dikirim dalam format Twelve Data: `1min`, `5min`, `15min`, `1h`, `4h`.
- Paket Twelve Data, market coverage, dan kredit API menentukan akses serta frekuensi request. Dashboard meminta data untuk tiga aset dan melakukan refresh berkala; pantau penggunaan kredit pada akun Twelve Data.
- Twelve Data `time_series` tidak menyediakan order book Level 2. Panel order book tidak diisi data palsu.
- Sinyal hanya untuk analisis/informasi, bukan jaminan profit atau nasihat investasi. Tidak ada order otomatis.

Dokumentasi: https://twelvedata.com/docs
