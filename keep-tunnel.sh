#!/bin/bash
# keep-tunnel.sh — pastikan tunnel dashboard hidup; restart bila mati.
# Dipanggil oleh cron tiap 5 menit. URL terbaru disimpan di data/tunnel_url.txt
cd ~/workspace/sniper-bot || exit 1

if pgrep -f "[l]ocalhost:5001" >/dev/null 2>&1; then
  url=$(grep -aoE 'https://[a-z0-9]+\.lhr\.life' /tmp/dash-tunnel.log 2>/dev/null | tail -1)
  if [ -n "$url" ] && timeout 20 curl -s --max-time 15 -w "%{http_code}" "$url/" -o /dev/null 2>/dev/null | grep -q '200'; then
    echo "$url" > data/tunnel_url.txt
    exit 0
  fi
fi

echo "$(date '+%H:%M:%S') tunnel mati/tidak sehat — restart..."
pkill -f "[l]ocalhost:5001" 2>/dev/null
sleep 2
rm -f /tmp/dash-tunnel.log
export PROXY_AUTH=$(printf '%s' "$http_proxy" | sed -E 's|http://([^:]+):([^@]+)@.*|\1:\2|')
if [ -z "$PROXY_AUTH" ]; then echo "PROXY_AUTH kosong"; exit 1; fi
setsid nohup ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -o ProxyCommand="socat STDIO PROXY:hatch-egress-proxy:%h:%p,proxyport=3128,proxyauth=$PROXY_AUTH" \
  -R 80:localhost:5001 nokey@localhost.run > /tmp/dash-tunnel.log 2>&1 < /dev/null &
sleep 16
url=$(grep -aoE 'https://[a-z0-9]+\.lhr\.life' /tmp/dash-tunnel.log 2>/dev/null | tail -1)
if [ -n "$url" ] && timeout 25 curl -s --max-time 20 -w "%{http_code}" "$url/" -o /dev/null 2>/dev/null | grep -q '200'; then
  echo "$url" > data/tunnel_url.txt
  echo "$(date '+%H:%M:%S') tunnel OK: $url"
else
  echo "$(date '+%H:%M:%S') tunnel gagal"
  exit 1
fi
