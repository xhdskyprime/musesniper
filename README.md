# Sniper Paper Bot (Demo)

Bot paper-trading meniru "memecoin sniper" gaya hit-and-run — **uang 100% virtual**,
pakai data harga market asli dari DexScreener (gratis, tanpa API key).

## Cara jalan

```bash
cd ~/workspace/sniper-bot
python3 main.py        # loop scan + trade (paper)
python3 dashboard.py   # dashboard web di 127.0.0.1:5001
```

## Strategi

- **Scan**: token Solana terbaru dari DexScreener tiap 60 detik.
- **Gerbang kualitas**: likuiditas ≥ $15rb, volume h24 ≥ $20rb, ≥100 tx/hari,
  umur pair ≤ 72 jam, rasio liq/mcap ≥ 2%.
- **Entry**: $10 per snipe, maks 5 posisi, simulasi slippage 2% + fee 0.3%.
- **Exit (hit and run)**: TP1 +50% (jual separuh), TP2 +100% (jual semua),
  stop-loss -25%, jual bila likuiditas anjlok 40%, time-stop 24 jam.

## Telegram (opsional)

```bash
export TELEGRAM_TOKEN='token-dari-BotFather'
export TELEGRAM_CHAT_ID='id-chat-kamu'
python3 main.py
```

Tanpa token, bot tetap jalan — notifikasi hanya tampil di log.

## Catatan jujur

- Paper trading ≠ jaminan profit. Hasil simulasi tidak memprediksi hasil asli.
- Data DexScreener gratis ada delay & rate-limit; ini bukan kecepatan snipe asli.
- Bot ini edukasi/simulasi, bukan nasihat finansial.
