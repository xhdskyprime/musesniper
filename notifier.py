"""Notifikasi Telegram (opsional). Diam bila token belum diisi."""
import requests
import config


def send(text):
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
            json={'chat_id': config.TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=15,
        )
        return r.ok
    except Exception as e:
        print(f'[tg] gagal kirim: {e}')
        return False


def fmt_buy(pos):
    return (f"🎯 <b>BELI {pos['symbol']}</b>\n"
            f"Harga: ${pos['entry_price']:.8f}\n"
            f"Modal: ${pos['cost_usd']:.2f}")


def fmt_sell(ev):
    emo = "💰" if ev['pnl'] >= 0 else "📉"
    status = "TUTUP" if ev['closed'] else "SEBAGIAN"
    return (f"{emo} <b>JUAL {ev['symbol']}</b> [{status}]\n"
            f"{ev['reason']}\n"
            f"Harga: ${ev['price']:.8f}\n"
            f"PnL: ${ev['pnl']:+.2f} ({ev['pnl_pct']:+.1f}%)\n"
            f"Di-pegang: {ev['age_h']:.1f} jam")
