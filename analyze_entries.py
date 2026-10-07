"""Winners-vs-losers entry-characteristic analysis for the sniper bot.

Joins closed SELL trades to their profiled BUY (by token_address, latest buy
before the sell) and compares entry metrics distributions: winners vs losers.
Run:  python3 analyze_entries.py [--json]
"""
import json, sys, statistics
from collections import defaultdict

DATA = '/home/hatch/workspace/sniper-bot/data/trades.json'

METRICS = [
    'liq_usd', 'vol_h24', 'txns_h24', 'buys_h1', 'sells_h1', 'buy_ratio_h1',
    'pc_m5', 'pc_h1', 'pc_h6', 'pc_h24', 'fdv', 'mcap', 'pair_age_h',
    'n_websites', 'socials',
]

def load():
    with open(DATA) as f:
        trades = json.load(f)
    buys = [t for t in trades
            if t.get('side') == 'BUY' and isinstance(t.get('entry'), dict)
            and t['entry'] and t.get('token_address')]
    sells = [t for t in trades if t.get('side') == 'SELL' and t.get('closed')]
    # latest profiled buy at/before each sell, per token; each buy used once
    by_addr = defaultdict(list)
    for b in buys:
        by_addr[b['token_address']].append(b)
    for v in by_addr.values():
        v.sort(key=lambda b: b['ts'])
    used = set()
    recs = []
    for s in sorted(sells, key=lambda s: s['ts']):
        cands = [b for b in by_addr.get(s.get('token_address', ''), [])
                 if b['ts'] <= s['ts'] and id(b) not in used]
        if not cands:
            continue
        b = cands[-1]
        used.add(id(b))
        recs.append({
            'symbol': s['symbol'], 'pnl': s['pnl'], 'reason': s.get('reason', ''),
            'buy_ts': b['ts'], 'sell_ts': s['ts'], 'entry': b['entry'],
        })
    return recs

def pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)

def main():
    recs = load()
    wins = [r for r in recs if r['pnl'] > 0]
    loss = [r for r in recs if r['pnl'] <= 0]
    out = {'n_total': len(recs), 'n_win': len(wins), 'n_loss': len(loss),
           'metrics': {}, 'win_reasons': defaultdict(int),
           'loss_reasons': defaultdict(int)}
    for r in wins:
        out['win_reasons'][r['reason']] += 1
    for r in loss:
        out['loss_reasons'][r['reason']] += 1
    for m in METRICS:
        wv = [r['entry'][m] for r in wins if isinstance(r['entry'].get(m), (int, float))]
        lv = [r['entry'][m] for r in loss if isinstance(r['entry'].get(m), (int, float))]
        if not wv or not lv:
            continue
        out['metrics'][m] = {
            'win':  {'n': len(wv), 'median': pct(wv, .5), 'p25': pct(wv, .25),
                     'p75': pct(wv, .75), 'mean': statistics.fmean(wv)},
            'loss': {'n': len(lv), 'median': pct(lv, .5), 'p25': pct(lv, .25),
                     'p75': pct(lv, .75), 'mean': statistics.fmean(lv)},
        }
    out['win_reasons'] = dict(out['win_reasons'])
    out['loss_reasons'] = dict(out['loss_reasons'])
    if '--json' in sys.argv:
        print(json.dumps(out, indent=1, default=str))
        return
    print(f"Profiled closed: {len(recs)}  ({len(wins)}W / {len(loss)}L)")
    print(f"{'metric':14} {'win_med':>12} {'loss_med':>12} {'win_mean':>12} {'loss_mean':>12}")
    for m, d in out['metrics'].items():
        w, l = d['win'], d['loss']
        print(f"{m:14} {w['median']:>12.2f} {l['median']:>12.2f} "
              f"{w['mean']:>12.2f} {l['mean']:>12.2f}")
    print("\nwin reasons:", out['win_reasons'])
    print("loss reasons:", out['loss_reasons'])

if __name__ == '__main__':
    main()
