"""Loop utama sniper bot (paper trading). Jalankan: python3 main.py"""
import time
import traceback

import config
import dex
import strategy
from engine import Engine
import notifier

seen_tokens = set()


def scan_once(eng):
    fresh = dex.latest_token_profiles()
    addrs = [p['tokenAddress'] for p in fresh
             if p.get('chainId') == 'solana'
             and p.get('tokenAddress') not in seen_tokens][:30]
    if not addrs:
        print('  tidak ada kandidat baru')
        return
    pairs = dex.token_pairs_batch(config.CHAIN, addrs)
    # kelompokkan per token, pilih likuiditas terbesar
    by_token = {}
    for p in pairs:
        if p.get('chainId') != 'solana':
            continue
        t = (p.get('baseToken') or {}).get('address', '')
        by_token.setdefault(t, []).append(p)
    for addr in addrs:
        seen_tokens.add(addr)
        plist = sorted(by_token.get(addr, []),
                       key=lambda p: dex.liquidity_usd(p), reverse=True)
        pair = plist[0] if plist else None
        ok, why = strategy.quality_gate(pair)
        sym = (pair.get('baseToken', {}) or {}).get('symbol') if pair else '?'
        if not ok:
            print(f'  [skip] {sym}: {why}')
            continue
        pos, msg = eng.open_position(pair)
        print(f'  [{msg}]')
        if pos:
            notifier.send(notifier.fmt_buy(pos))
        if len(eng.pf['positions']) >= config.MAX_POSITIONS:
            break


def main():
    eng = Engine()
    print(f'=== SNIPER PAPER BOT mulai | modal virtual ${config.STARTING_CASH:.2f} ===')
    notifier.send(f'🤖 <b>Sniper paper-bot mulai</b>\nModal virtual ${config.STARTING_CASH:.0f}. Mode demo, tanpa uang asli.')
    while True:
        try:
            print(f'--- scan {time.strftime("%H:%M:%S")} ---')
            scan_once(eng)
            events = eng.update_positions()
            for ev in events:
                tag = 'CLOSED' if ev['closed'] else 'PARTIAL'
                print(f"  {tag} {ev['symbol']}: {ev['reason']} | PnL ${ev['pnl']:+.2f}")
                notifier.send(notifier.fmt_sell(ev))
            manual = eng.process_sell_requests()
            for ev in manual:
                print(f"  MANUAL SELL {ev['symbol']}: PnL ${ev['pnl']:+.2f}")
                notifier.send(notifier.fmt_sell(ev))
            s = eng.summary()
            print(f'  aset ${s["total"]:.2f} (cash ${s["cash"]:.2f} + coin ${s["coin_value"]:.2f}) '
                  f'PnL ${s["pnl"]:+.2f} | open {s["n_open"]}')
            eng.write_snapshot()
        except Exception:
            traceback.print_exc()
        time.sleep(config.SCAN_INTERVAL)


if __name__ == '__main__':
    main()
