"""Klien data market via DexScreener API (gratis, tanpa API key)."""
import time
import requests
import config

BASE = 'https://api.dexscreener.com'

_last_call = 0.0


def _session():
    # session baru tiap request + Connection: close
    # (keep-alive reuse macet dari jaringan ini)
    s = requests.Session()
    s.headers.update({'User-Agent': 'sniper-paper-bot/1.0', 'Connection': 'close'})
    return s


def _get(path, params=None, timeout=15):
    global _last_call
    # rate limit sederhana: maks ~2 req/detik
    dt = time.time() - _last_call
    if dt < 0.5:
        time.sleep(0.5 - dt)
    s = _session()
    try:
        r = s.get(BASE + path, params=params, timeout=timeout)
        _last_call = time.time()
        r.raise_for_status()
        return r.json()
    finally:
        s.close()


def latest_token_profiles():
    """Token-token yang baru dibuat/di-boost (kandidat snipe)."""
    try:
        return _get('/token-profiles/latest/v1') or []
    except Exception as e:
        print(f'[dex] latest profiles gagal: {e}')
        return []


def top_boosted():
    try:
        return _get('/token-boosts/top/v1') or []
    except Exception as e:
        print(f'[dex] boosted gagal: {e}')
        return []


def token_pairs(chain, token_address):
    """Daftar pair untuk sebuah token. Return list pair dicts."""
    return token_pairs_batch(chain, [token_address])


def token_pairs_batch(chain, token_addresses):
    """Ambil pair untuk banyak token sekaligus (maks 30 per request)."""
    out = []
    for i in range(0, len(token_addresses), 30):
        chunk = token_addresses[i:i + 30]
        for attempt in range(3):
            try:
                data = _get(f"/tokens/v1/{chain}/{','.join(chunk)}", timeout=30)
                out.extend(data or [])
                break
            except Exception as e:
                print(f'[dex] batch pairs gagal (coba {attempt+1}): {e}')
                time.sleep(2)
    return out


def pair_detail(chain, pair_address):
    try:
        data = _get(f'/latest/dex/pairs/{chain}/{pair_address}')
        pairs = (data or {}).get('pairs') or []
        return pairs[0] if pairs else None
    except Exception as e:
        print(f'[dex] pair detail gagal: {e}')
        return None


def best_solana_pair(token_address):
    """Pilih pair Solana dengan likuiditas terbesar untuk token ini."""
    pairs = [p for p in token_pairs(config.CHAIN, token_address)
             if (p.get('chainId') == 'solana')]
    if not pairs:
        return None
    pairs.sort(key=lambda p: (p.get('liquidity') or {}).get('usd') or 0, reverse=True)
    return pairs[0]


def pair_age_hours(pair):
    ts = pair.get('pairCreatedAt')
    if not ts:
        return 9999
    return (time.time() * 1000 - ts) / 3_600_000


def price_usd(pair):
    try:
        return float(pair.get('priceUsd') or 0)
    except (TypeError, ValueError):
        return 0.0


def liquidity_usd(pair):
    return float((pair.get('liquidity') or {}).get('usd') or 0)


def volume_h24(pair):
    return float((pair.get('volume') or {}).get('h24') or 0)


def txns_h24(pair):
    t = pair.get('txns') or {}
    h = t.get('h24') or {}
    return int(h.get('buys') or 0) + int(h.get('sells') or 0)


def entry_metrics(pair):
    """Ringkasan karakteristik pair TEPAT saat entry — bahan analisa winners vs losers."""
    tx = pair.get('txns') or {}
    h1 = tx.get('h1') or {}
    buys = int(h1.get('buys') or 0)
    sells = int(h1.get('sells') or 0)
    pc = pair.get('priceChange') or {}
    info = pair.get('info') or {}

    def f(x):
        try:
            return float(x) if x is not None else 0
        except (TypeError, ValueError):
            return 0

    return {
        'liq_usd': round(liquidity_usd(pair), 2),
        'vol_h24': round(volume_h24(pair), 2),
        'txns_h24': txns_h24(pair),
        'buys_h1': buys,
        'sells_h1': sells,
        'buy_ratio_h1': round(buys / (buys + sells), 3) if (buys + sells) else None,
        'pc_m5': f(pc.get('m5')),
        'pc_h1': f(pc.get('h1')),
        'pc_h6': f(pc.get('h6')),
        'pc_h24': f(pc.get('h24')),
        'fdv': f(pair.get('fdv')),
        'mcap': f(pair.get('marketCap')),
        'pair_age_h': round(pair_age_hours(pair), 2),
        'n_websites': len([w for w in (info.get('websites') or []) if w.get('url')]),
        'socials': sorted({s.get('type') for s in (info.get('socials') or []) if s.get('type')}),
    }
