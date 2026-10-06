"""Telegram command listener: /status (saldo + rincian), /help.

Long-poll getUpdates, hanya layani chat user yang terdaftar.
Dijalankan sebagai proses terpisah, dijaga keep-listener.sh.
"""
import json
import os
import subprocess
import time
import traceback

BASE = os.path.expanduser('~/workspace/sniper-bot')
DATA = os.path.join(BASE, 'data')
TG = os.path.expanduser('~/workspace/skills/telegram/bin/tg')
OFFSET_FILE = os.path.join(DATA, 'tg_offset.txt')
HEARTBEAT_FILE = os.path.join(DATA, 'listener_heartbeat.txt')


def chat_id():
    try:
        with open(os.path.join(DATA, 'telegram_chat_id.txt')) as f:
            return f.read().strip()
    except OSError:
        return ''


def tg(method, payload=None):
    cmd = [TG, method]
    if payload is not None:
        cmd.append(json.dumps(payload))
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=70)
    return json.loads(p.stdout or '{}')


def send(text):
    cid = chat_id()
    if not cid:
        print('[listener] chat id kosong, batal kirim')
        return False
    try:
        res = tg('sendMessage', {'chat_id': cid, 'text': text})
        if res.get('ok'):
            return True
        print(f"[listener] telegram menolak: {str(res)[:200]}")
        return False
    except Exception as e:
        print(f'[listener] kirim gagal: {e}')
        return False


def load_offset():
    try:
        with open(OFFSET_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def save_offset(n):
    with open(OFFSET_FILE, 'w') as f:
        f.write(str(n))


def heartbeat():
    with open(HEARTBEAT_FILE, 'w') as f:
        f.write(str(int(time.time())))


def load_snap(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def fmt_bot(tag, name, snap):
    if not snap:
        return f'{tag} {name}: data tidak ada'
    pos = snap.get('positions') or []
    pos = sorted(pos, key=lambda p: p.get('pnl', 0), reverse=True)
    lines = [
        f'{tag} {name}',
        f"Total ${snap.get('total', 0):,.2f} | Cash ${snap.get('cash', 0):,.2f}",
        f"PnL ${snap.get('pnl', 0):+.2f} ({snap.get('pnl_pct', 0):+.1f}%)",
        f'{len(pos)} posisi:',
    ]
    shown = pos[:40]
    for p in shown:
        mult = p.get('mult') or 0
        lines.append(f"  {p.get('symbol', '?')[:12]:12s} {mult:.2f}x "
                     f"${p.get('pnl', 0):+.2f}")
    if len(pos) > len(shown):
        lines.append(f'  ... +{len(pos) - len(shown)} lainnya')
    return '\n'.join(lines)


def cmd_status():
    s1 = load_snap(os.path.join(DATA, 'snapshot.json'))
    s2 = load_snap(os.path.expanduser('~/workspace/pump-sniper/data/snapshot.json'))
    parts = [fmt_bot('🎯', 'UTAMA', s1), '', fmt_bot('🔥', 'PUMP', s2)]
    t1 = (s1 or {}).get('total', 0)
    t2 = (s2 or {}).get('total', 0)
    parts += ['', f'🧮 GABUNGAN: ${t1 + t2:,.2f}']
    msg = '\n'.join(parts)
    if len(msg) > 4000:
        msg = msg[:3990] + '\n…(dipotong)'
    return msg


def handle(text):
    cmd = text.strip().split()[0].split('@')[0]
    if cmd == '/status':
        return cmd_status()
    if cmd == '/help':
        return ('Perintah:\n'
                '/status — saldo, posisi & PnL kedua bot\n'
                '/help — pesan ini')
    return None


def main():
    me = chat_id()
    print(f'[listener] mulai, chat_id={me[:4]}****', flush=True)
    offset = load_offset()
    while True:
        try:
            heartbeat()
            data = tg('getUpdates', {'offset': offset, 'timeout': 30})
            for u in data.get('result', []):
                offset = max(offset, u.get('update_id', 0) + 1)
                msg = u.get('message') or {}
                if str((msg.get('chat') or {}).get('id')) != me:
                    continue
                text = msg.get('text') or ''
                if not text.startswith('/'):
                    continue
                reply = handle(text)
                if reply:
                    ok = send(reply)
                    print(f"[listener] {text.split()[0]} -> {'terkirim' if ok else 'GAGAL'}",
                          flush=True)
            save_offset(offset)
        except Exception:
            traceback.print_exc()
            time.sleep(5)


if __name__ == '__main__':
    main()
