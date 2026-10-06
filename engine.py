"""Paper trading engine: portofolio virtual, TP/SL, exit rules. Tanpa uang asli."""
import json
import math
import os
import time
import uuid

import config
import dex
import safety

PORTFOLIO_FILE = os.path.join(config.DATA_DIR, 'portfolio.json')
TRADES_FILE = os.path.join(config.DATA_DIR, 'trades.json')
SNAPSHOT_FILE = os.path.join(config.DATA_DIR, 'snapshot.json')
SELL_REQUESTS_FILE = os.path.join(config.DATA_DIR, 'sell_requests.json')


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


class Engine:
    def __init__(self):
        pf = _load(PORTFOLIO_FILE, None)
        if pf is None:
            pf = {'cash': config.STARTING_CASH, 'positions': [], 'started_at': time.time()}
            _save(PORTFOLIO_FILE, pf)
        self.pf = pf
        self.trades = _load(TRADES_FILE, [])

    def save(self):
        _save(PORTFOLIO_FILE, self.pf)
        _save(TRADES_FILE, self.trades)

    # ---------- buka posisi ----------
    def open_position(self, pair):
        if len(self.pf['positions']) >= config.MAX_POSITIONS:
            return None, 'slot posisi penuh'
        if self.pf['cash'] < config.TRADE_SIZE_USD:
            return None, 'cash tidak cukup'
        token_addr = (pair.get('baseToken') or {}).get('address', '')
        if any(p['token_address'] == token_addr for p in self.pf['positions']):
            return None, 'sudah punya posisi token ini'

        price = dex.price_usd(pair)
        liq = dex.liquidity_usd(pair)
        # karakteristik entry — bahan analisa "token menguntungkan itu kaya gimana"
        entry = dex.entry_metrics(pair)
        entry.update(safety.rugcheck_metrics(token_addr))
        # simulasi slippage + fee saat beli
        eff_price = price * (1 + config.SLIPPAGE_PCT / 100)
        cost = config.TRADE_SIZE_USD
        fee = cost * config.FEE_PCT / 100
        amount = (cost - fee) / eff_price

        pos = {
            'id': uuid.uuid4().hex[:8],
            'symbol': (pair.get('baseToken') or {}).get('symbol', '?'),
            'name': (pair.get('baseToken') or {}).get('name', ''),
            'token_address': token_addr,
            'pair_address': pair.get('pairAddress', ''),
            'entry_price': eff_price,
            'entry_liq': liq,
            'amount': amount,
            'cost_usd': cost,
            'orig_cost_usd': cost,
            'opened_at': time.time(),
            'last_price': price,
            'entry': entry,
        }
        self.pf['cash'] -= cost
        self.pf['positions'].append(pos)
        self.trades.append({
            'ts': time.time(), 'side': 'BUY', 'symbol': pos['symbol'],
            'price': eff_price, 'amount': amount, 'usd': cost,
            'token_address': token_addr, 'pair_address': pair.get('pairAddress', ''),
            'entry': entry,
        })
        self.save()
        return pos, f"BUY {pos['symbol']} @ ${eff_price:.8f} (${cost:.2f})"

    # ---------- update posisi ----------
    def _close(self, pos, price, frac, reason):
        sell_amount = pos['amount'] * frac
        eff_price = price * (1 - config.SLIPPAGE_PCT / 100)
        gross = sell_amount * eff_price
        fee = gross * config.FEE_PCT / 100
        net = gross - fee
        self.pf['cash'] += net
        pos['amount'] -= sell_amount
        # pnl vs porsi cost; tapi % selalu thd modal awal posisi (biar intuitif:
        # "naro $5, untung $3 = +60%", bukan thd porsi yg dijual)
        cost_part = pos['cost_usd'] * frac
        pnl = net - cost_part
        pos['cost_usd'] -= cost_part  # kurangi basis biar trade berikut akurat
        denom = pos.get('orig_cost_usd') or cost_part
        closed = pos['amount'] <= 1e-12
        self.trades.append({
            'ts': time.time(), 'side': 'SELL', 'symbol': pos['symbol'],
            'price': eff_price, 'amount': sell_amount, 'usd': net,
            'pnl': pnl, 'reason': reason, 'closed': closed,
            'token_address': pos.get('token_address', ''),
            'pair_address': pos.get('pair_address', ''),
        })
        if closed:
            self.pf['positions'] = [p for p in self.pf['positions'] if p['id'] != pos['id']]
        self.save()
        return {
            'kind': 'sell', 'symbol': pos['symbol'], 'reason': reason,
            'price': eff_price, 'usd': net, 'pnl': pnl,
            'pnl_pct': pnl / denom * 100 if denom else 0,
            'closed': closed,
            'age_h': (time.time() - pos['opened_at']) / 3600,
        }

    def update_positions(self, price_fn=None):
        """Cek TP/SL/time-stop untuk tiap posisi. price_fn(pair_addr)->(price, liq)."""
        events = []
        for pos in list(self.pf['positions']):
            if price_fn:
                price, liq = price_fn(pos['pair_address'])
            else:
                pair = dex.pair_detail(config.CHAIN, pos['pair_address'])
                if not pair:
                    continue
                price, liq = dex.price_usd(pair), dex.liquidity_usd(pair)
            if price <= 0:
                continue
            pos['last_price'] = price
            mult = price / pos['entry_price']
            age_h = (time.time() - pos['opened_at']) / 3600
            liq_drop = (liq - pos['entry_liq']) / pos['entry_liq'] * 100 if pos['entry_liq'] else 0

            reason, frac = None, 1.0
            # trailing stop BERTINGKAT: tiap kelipatan +50% tercapai, level
            # itu jadi penahan (stop) dan TIDAK PERNAH TURUN. Di bawah +50%
            # pertama, stop di entry - gap sebagai pelindung awal.
            # Jual habis, tanpa sebagian.
            step = config.TRAIL_STEP_PCT / 100
            if mult >= 1.0 + step:
                lvl = 1.0 + math.floor((mult - 1.0) / step + 1e-9) * step
            else:
                lvl = 1.0 - config.TRAIL_GAP_PCT / 100
            prev = pos.get('penahan') or 0
            if not prev and (pos.get('peak') or 0) >= 1.0 + step:
                pk = pos['peak']
                prev = 1.0 + math.floor((pk - 1.0) / step + 1e-9) * step
            penahan = max(prev, lvl)
            pos['penahan'] = penahan
            if mult <= penahan:
                reason = (f'TRAILING STOP {mult:.2f}x '
                          f'(penahan {penahan:.2f}x)')
            elif liq_drop <= config.LIQ_DROP_EXIT_PCT:
                reason = f'LIKUIDITAS ANJLOK {liq_drop:.0f}%'
            elif age_h >= config.TIME_STOP_HOURS:
                reason = f'TIME STOP {age_h:.1f} jam'

            if reason:
                ev = self._close(pos, price, frac, reason)
                events.append(ev)
        self.save()
        return events

    def process_sell_requests(self):
        """Eksekusi permintaan jual manual dari dashboard (harga pasar terkini)."""
        reqs = _load(SELL_REQUESTS_FILE, [])
        if not reqs:
            return []
        done = []
        for r in reqs:
            pid = r.get('pos_id')
            pos = next((p for p in self.pf['positions'] if p['id'] == pid), None)
            if not pos:
                continue
            price = pos.get('last_price') or 0
            if price <= 0:  # fallback: ambil harga segar
                pair = dex.pair_detail(config.CHAIN, pos['pair_address'])
                price = dex.price_usd(pair) if pair else 0
            if price <= 0:
                continue
            ev = self._close(pos, price, 1.0, 'MANUAL SELL (user)')
            done.append(ev)
        _save(SELL_REQUESTS_FILE, [])  # kosongkan antrean
        self.save()
        return done

    # ---------- ringkasan ----------
    def summary(self, price_fn=None):
        coin_value = 0.0
        for pos in self.pf['positions']:
            if price_fn:
                price, _ = price_fn(pos['pair_address'])
            else:
                pair = dex.pair_detail(config.CHAIN, pos['pair_address'])
                price = dex.price_usd(pair) if pair else pos.get('last_price', 0)
            coin_value += pos['amount'] * price
            pos['last_price'] = price
        total = self.pf['cash'] + coin_value
        pnl = total - config.STARTING_CASH
        return {
            'cash': self.pf['cash'],
            'coin_value': coin_value,
            'total': total,
            'pnl': pnl,
            'pnl_pct': pnl / config.STARTING_CASH * 100,
            'n_open': len(self.pf['positions']),
            'n_closed': sum(1 for t in self.trades if t.get('closed')),
        }

    def snapshot(self):
        """Ringkasan dari harga terakhir yang diketahui (tanpa API call)."""
        positions = []
        for p in self.pf['positions']:
            price = p.get('last_price') or 0
            mult = price / p['entry_price'] if p['entry_price'] else 0
            positions.append({
                'id': p['id'],
                'symbol': p['symbol'],
                'entry': p['entry_price'],
                'now': price,
                'mult': mult,
                'age_h': (time.time() - p['opened_at']) / 3600,
                'value': p['amount'] * price,
                'pnl': p['amount'] * price - p['cost_usd'],
                'opened': time.strftime('%d %b %H:%M', time.localtime(p['opened_at'])),
            })
        coin_value = sum(p['value'] for p in positions)
        total = self.pf['cash'] + coin_value
        pnl = total - config.STARTING_CASH
        trades = sorted(self.trades, key=lambda t: t['ts'], reverse=True)[:30]
        for t in trades:
            t['when'] = time.strftime('%d %b %H:%M', time.localtime(t['ts']))
        return {
            'cash': self.pf['cash'],
            'coin_value': coin_value,
            'total': total,
            'pnl': pnl,
            'pnl_pct': pnl / config.STARTING_CASH * 100,
            'n_open': len(self.pf['positions']),
            'positions': positions,
            'trades': trades,
            'updated': time.strftime('%H:%M:%S'),
        }

    def write_snapshot(self):
        _save(SNAPSHOT_FILE, self.snapshot())
