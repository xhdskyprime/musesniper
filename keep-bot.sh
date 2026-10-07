#!/bin/bash
# keep-bot.sh — pastikan sniper bot (sniper-bot) hidup dan log-nya jalan; restart bila mati/macet.
# Pola pgrep memakai path proyek agar tidak tertukar dengan pump-sniper.
cd ~/workspace/sniper-bot || exit 1
# jeda manual oleh user — jangan restart
if [ -f data/PAUSED ]; then
  exit 0
fi
# Satu instance keeper saja dalam satu waktu (lihat penjelasan di
# ~/workspace/pump-sniper/keep-pump.sh): sniper-guardian dan
# sniper-tunnel-notifier sama-sama menjalankan script ini tiap 5 menit.
exec 9>"$PWD/data/.keep-bot.lock"
flock -n 9 || exit 0
# Pakai venv di home (persist antar-restart VM); JANGAN pakai system python3
# karena package system-wide (flask dsb.) hilang tiap VM diganti.
PY="$HOME/workspace/sniper-bot/venv/bin/python"
# Paksa WIB agar semua timestamp bot & dashboard selalu WIB,
# tidak tergantung timezone bawaan VM (pernah kejadian log tertulis UTC).
export TZ=Asia/Jakarta
# muat kredensial telegram (bila ada)
if [ -f .telegram.env ]; then
  set -a; . ./.telegram.env; set +a
fi

if pgrep -f "sniper-bot/main\.py" >/dev/null 2>&1; then
  if [ -n "$(find data/bot.log -mmin -6 2>/dev/null)" ]; then
    exit 0  # hidup dan sehat
  fi
  echo "$(date '+%H:%M:%S') bot macet (log tidak update) — restart..."
  pkill -f "sniper-bot/main\.py" 2>/dev/null
  sleep 3
else
  echo "$(date '+%H:%M:%S') bot mati — nyalakan ulang..."
fi

setsid nohup "$PY" -u "$PWD/main.py" >> data/bot.log 2>&1 < /dev/null &
sleep 8
if pgrep -f "sniper-bot/main\.py" >/dev/null 2>&1; then
  echo "$(date '+%H:%M:%S') bot OK"
else
  echo "$(date '+%H:%M:%S') bot GAGAL nyala"
  exit 1
fi

# --- dashboard (port 5001): tidak ada yang me-restart ini sebelumnya,
# padahal tunnel mengarah ke sini. Pastikan ikut hidup.
if timeout 10 curl -s -o /dev/null --max-time 8 "http://127.0.0.1:5001/" 2>/dev/null; then
  exit 0  # dashboard hidup
fi
echo "$(date '+%H:%M:%S') dashboard mati — nyalakan ulang..."
pkill -f "sniper-bot/dashboard\.py" 2>/dev/null
sleep 2
setsid nohup "$PY" -u "$PWD/dashboard.py" >> data/dashboard.log 2>&1 < /dev/null &
sleep 6
if timeout 10 curl -s -o /dev/null --max-time 8 "http://127.0.0.1:5001/" 2>/dev/null; then
  echo "$(date '+%H:%M:%S') dashboard OK"
else
  echo "$(date '+%H:%M:%S') dashboard GAGAL nyala"
  exit 1
fi
