#!/bin/bash
# keep-listener.sh — pastikan Telegram command listener hidup; restart bila mati/macet.
cd ~/workspace/sniper-bot || exit 1
PY="$HOME/workspace/sniper-bot/venv/bin/python"
export TZ=Asia/Jakarta

if pgrep -f "sniper-bot/tg_listener\.py" >/dev/null 2>&1; then
  hb=$(cat data/listener_heartbeat.txt 2>/dev/null)
  now=$(date +%s)
  if [ -n "$hb" ] && [ $((now - hb)) -lt 180 ]; then
    exit 0  # hidup dan sehat
  fi
  echo "$(date '+%H:%M:%S') listener macet — restart..."
  pkill -f "sniper-bot/tg_listener\.py" 2>/dev/null
  sleep 3
else
  echo "$(date '+%H:%M:%S') listener mati — nyalakan ulang..."
fi

setsid nohup "$PY" -u "$PWD/tg_listener.py" >> data/listener.log 2>&1 < /dev/null &
sleep 5
if pgrep -f "sniper-bot/tg_listener\.py" >/dev/null 2>&1; then
  echo "$(date '+%H:%M:%S') listener OK"
else
  echo "$(date '+%H:%M:%S') listener GAGAL nyala"
  exit 1
fi
