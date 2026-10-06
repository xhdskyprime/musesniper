"""Gerbang kualitas: filter token baru sebelum di-snipe (paper)."""
import config
import dex
import safety

# blacklist kata kasar penipu umum
SCAM_WORDS = ('honeypot', 'test', 'scam', 'rug')


def quality_gate(pair):
    """Return (lolos: bool, alasan: str)."""
    if not pair:
        return False, 'pair tidak ditemukan'
    if pair.get('chainId') != 'solana':
        return False, 'bukan jaringan solana'

    base = (pair.get('baseToken') or {})
    symbol = (base.get('symbol') or '').upper()
    name = (base.get('name') or '').lower()
    if any(w in name for w in SCAM_WORDS):
        return False, f'nama mencurigakan ({name[:20]})'

    liq = dex.liquidity_usd(pair)
    if liq < config.MIN_LIQUIDITY_USD:
        return False, f'likuiditas ${liq:,.0f} < ${config.MIN_LIQUIDITY_USD:,.0f}'

    vol = dex.volume_h24(pair)
    if vol < config.MIN_VOLUME_H24_USD:
        return False, f'volume h24 ${vol:,.0f} terlalu kecil'

    tx = dex.txns_h24(pair)
    if tx < config.MIN_TXNS_H24:
        return False, f'transaksi h24 {tx} < {config.MIN_TXNS_H24}'

    age = dex.pair_age_hours(pair)
    if age > config.MAX_PAIR_AGE_HOURS:
        return False, f'umur pair {age:.1f} jam terlalu tua'

    mcap = float(pair.get('marketCap') or pair.get('fdv') or 0)
    if mcap > 0 and liq / mcap < config.MIN_LIQ_TO_MCAP:
        return False, 'rasio likuiditas/mcap terlalu kecil'

    price = dex.price_usd(pair)
    if price <= 0:
        return False, 'harga tidak valid'

    # Analisa mendalam: rugcheck + website/sosmed + momentum
    if config.SAFETY_ENABLED:
        mint = (base.get('address') or '')
        if mint:
            ok2, notes = safety.safety_gate(mint, pair)
            if not ok2:
                return False, ' | '.join(notes)
            detail = '; '.join(notes)
            return True, f'{symbol} lolos (liq ${liq:,.0f}, vol ${vol:,.0f}, umur {age:.1f}j | {detail})'

    return True, f'{symbol} lolos (liq ${liq:,.0f}, vol ${vol:,.0f}, umur {age:.1f}j)'
