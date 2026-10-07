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
PUMP_DATA = os.path.expanduser('~/workspace/pump-sniper/data')
BLACKLIST_FILE = os.path.join(PUMP_DATA, 'creator_blacklist.txt')
PUMP_SELL_REQ = os.path.join(PUMP_DATA, 'sell_requests.json')
ADDR_RE = None  # compiled lazily


def valid_addr(a):
    import re
    global ADDR_RE
    if ADDR_RE is None:
        ADDR_RE = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
    return bool(ADDR_RE.match(a))


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


def cmd_blacklist(args):
    entries = []
    try:
        with open(BLACKLIST_FILE) as f:
            entries = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    except OSError:
        pass
    if not args:
        if not entries:
            return ('⛔ Blacklist kreator kosong.\n'
                    'Kirim: /blacklist <alamat_creator>')
        shown = '\n'.join('• ' + e[:16] + '…' for e in entries[-15:])
        extra = '' if len(entries) <= 15 else f'\n… +{len(entries) - 15} lainnya'
        return f'⛔ Blacklist kreator ({len(entries)}):\n{shown}{extra}'
    addr = args[0].strip()
    if not valid_addr(addr):
        return '⛔ Alamat tidak valid. Kirim alamat Solana kreator (32–44 karakter).'
    if addr in entries:
        return f'⛔ Alamat {addr[:12]}… sudah ada di blacklist.'
    entries.append(addr)
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            for e in entries:
                f.write(e + '\n')
    except OSError as e:
        return f'⛔ Gagal menyimpan: {e}'
    return (f'✅ Kreator {addr[:12]}… masuk blacklist.\n'
            f'Bot pump menolak koin dari kreator ini mulai loop berikutnya '
            f'(total {len(entries)} alamat).')


def handle(text):
    parts = text.strip().split()
    cmd = parts[0].split('@')[0]
    if cmd == '/status':
        return cmd_status()
    if cmd == '/blacklist':
        return cmd_blacklist(parts[1:])
    if cmd == '/help':
        return ('Perintah:\n'
                '/status — saldo, posisi & PnL kedua bot\n'
                '/blacklist <alamat> — blacklist kreator (kosongkan untuk lihat daftar)\n'
                '/help — pesan ini\n\n'
                'Bot pump mode MANUAL: tiap ±25% ada notif + tombol '
                'JUAL/HOLD langsung di chat.')
    return None


def request_pump_sell(pos_id):
    """Tulis permintaan jual pump ke sell_requests.json (dibaca bot tiap loop).

    Return True bila permintaan baru ditulis, False bila sudah ada.
    """
    reqs = []
    try:
        with open(PUMP_SELL_REQ) as f:
            reqs = json.load(f)
    except (OSError, ValueError):
        reqs = []
    if any(r.get('pos_id') == pos_id for r in reqs):
        return False
    reqs.append({'pos_id': pos_id, 'ts': time.time(), 'via': 'telegram'})
    tmp = PUMP_SELL_REQ + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(reqs, f)
    os.replace(tmp, PUMP_SELL_REQ)
    return True


def answer_callback(cq_id, text):
    try:
        tg('answerCallbackQuery',
           {'callback_query_id': cq_id, 'text': text})
    except Exception as e:
        print(f'[listener] answerCallback gagal: {e}')


def strip_buttons(chat_id_, message_id):
    """Cabut tombol inline dari pesan (cegah double-tap)."""
    try:
        tg('editMessageReplyMarkup',
           {'chat_id': chat_id_, 'message_id': message_id,
            'reply_markup': {'inline_keyboard': []}})
    except Exception as e:
        print(f'[listener] strip buttons gagal: {e}')


def handle_callback(cq):
    data = cq.get('data') or ''
    cq_id = cq.get('id')
    msg = cq.get('message') or {}
    mid = msg.get('message_id')
    cid = (msg.get('chat') or {}).get('id')
    if data.startswith('pump_sell:'):
        pos_id = data.split(':', 1)[1]
        if request_pump_sell(pos_id):
            answer_callback(cq_id, '⏳ Jual diminta — dieksekusi loop berikutnya')
        else:
            answer_callback(cq_id, '⏳ Sudah diminta, tunggu eksekusi')
        if mid and cid:
            strip_buttons(cid, mid)
        print(f'[listener] tombol JUAL pos {pos_id}', flush=True)
    elif data.startswith('pump_hold:'):
        pos_id = data.split(':', 1)[1]
        answer_callback(cq_id, '✋ Hold — lanjut pantau')
        print(f'[listener] tombol HOLD pos {pos_id}', flush=True)


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
                cq = u.get('callback_query')
                if cq:
                    cchat = ((cq.get('message') or {}).get('chat') or {}).get('id')
                    if str(cchat) != me:
                        continue
                    try:
                        handle_callback(cq)
                    except Exception:
                        traceback.print_exc()
                    continue
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
