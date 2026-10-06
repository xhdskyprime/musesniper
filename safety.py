"""Analisa mendalam token sebelum dibeli (paper).

Sumber:
- RugCheck API : otoritas mint/freeze, status LP (terkunci/dibakar),
                 konsentrasi holder, skor risiko, riwayat rugged.
- DexScreener   : website & sosmed terdaftar, verifikasi website hidup,
                 tekanan beli/jual, dan cek "beli di pucuk".
"""
import time
import requests

import config

RC_BASE = 'https://api.rugcheck.xyz/v1/tokens'
_cache = {}          # mint -> (timestamp, report)
_CACHE_TTL = 600     # detik


def fetch_report(mint):
    """Ambil laporan RugCheck (dengan cache 10 menit). None bila gagal."""
    now = time.time()
    hit = _cache.get(mint)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        s = requests.Session()
        s.headers.update({'User-Agent': 'sniper-paper-bot/1.0', 'Connection': 'close'})
        r = s.get(f'{RC_BASE}/{mint}/report', timeout=config.RUGCHECK_TIMEOUT)
        s.close()
        r.raise_for_status()
        rep = r.json()
        _cache[mint] = (now, rep)
        return rep
    except Exception as e:
        print(f'[safety] rugcheck gagal ({mint[:8]}…): {e}')
        return None


def _lp_status(rep):
    """Return (pct_terkunci_terbaik, ada_yang_dibakar)."""
    best, burned = 0.0, False
    for m in rep.get('markets') or []:
        lp = m.get('lp') or {}
        try:
            best = max(best, float(lp.get('lpLockedPct') or 0))
        except (TypeError, ValueError):
            pass
        if lp.get('lpBurned'):
            burned = True
    return best, burned


def _top10_pct(rep):
    try:
        return sum(float(h.get('pct') or 0) for h in (rep.get('topHolders') or [])[:10])
    except (TypeError, ValueError):
        return 0.0


def _website_hidup(url):
    """Cek cepat: website bisa dibuka (status 2xx/3xx)."""
    try:
        s = requests.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0', 'Connection': 'close'})
        r = s.get(url, timeout=6, allow_redirects=True)
        s.close()
        return 200 <= r.status_code < 400
    except Exception:
        return False


def safety_gate(mint, pair):
    """Return (lolos: bool, catatan: list[str]) — analisa mendalam pra-beli."""
    notes = []
    rep = fetch_report(mint)
    if rep is None:
        # RugCheck down: jangan matikan bot, tapi catat
        return True, ['rugcheck tidak terjangkau — lolos dengan catatan']

    if rep.get('rugged'):
        return False, ['RUGGED: token pernah/sedang di-rug']

    if config.DEGEN_MODE:
        # Mode degen: hanya cegah yang bikin TIDAK BISA KELUAR.
        # Selebihnya lolos — filosofinya hit cepat di listing baru,
        # keluar cepat saat untung. Rug pelan ditangani stop-loss & exit cepat.
        fee = ((rep.get('transferFee') or {}).get('pct')) or 0
        try:
            fee = float(fee)
        except (TypeError, ValueError):
            fee = 0
        if fee > config.DEGEN_MAX_TRANSFER_FEE_PCT:
            return False, [f'pajak transfer {fee:.1f}% — tidak bisa keluar cepat']
        return True, ['mode degen: lolos (cek fatal saja)']

    # 1. Otoritas dev
    if config.REQUIRE_MINT_REVOKED and rep.get('mintAuthority'):
        return False, ['mint authority AKTIF — dev bisa mencetak token seenaknya']
    if config.REQUIRE_FREEZE_REVOKED and rep.get('freezeAuthority'):
        return False, ['freeze authority AKTIF — dev bisa membekukan tokenmu']

    # 2. Kesehatan likuiditas: LP harus terkunci / dibakar
    locked_pct, burned = _lp_status(rep)
    if not burned and locked_pct < config.MIN_LP_LOCKED_PCT:
        return False, [f'LP hanya terkunci {locked_pct:.0f}% — dev bisa tarik likuiditas (rug)']

    # 3. Konsentrasi holder (anti whale dump)
    top10 = _top10_pct(rep)
    if top10 > config.MAX_TOP10_HOLDERS_PCT:
        return False, [f'10 holder teratas kuasai {top10:.0f}% — rawan dump']

    # 4. Pajak transfer tersembunyi (Token-2022)
    fee = ((rep.get('transferFee') or {}).get('pct')) or 0
    try:
        fee = float(fee)
    except (TypeError, ValueError):
        fee = 0
    if fee > config.MAX_TRANSFER_FEE_PCT:
        return False, [f'pajak transfer {fee:.1f}% — token menggerogoti tiap transaksi']

    # 5. Skor risiko agregat RugCheck
    score = rep.get('score_normalised')
    try:
        score = float(score) if score is not None else 0
    except (TypeError, ValueError):
        score = 0
    if score > config.MAX_RUGCHECK_SCORE:
        return False, [f'skor risiko {score:.0f}/100 — terlalu berbahaya']
    dangers = [x.get('name') for x in (rep.get('risks') or [])
               if x.get('level') == 'danger' and x.get('name')]
    if dangers:
        return False, [f'temuan danger: {", ".join(dangers[:3])}']
    notes.append(f'rugcheck OK (skor {score:.0f}, LP lock {locked_pct:.0f}%, top10 {top10:.0f}%)')

    # 6. Website & sosmed: harus ada, dan websitenya harus bisa dibuka
    info = pair.get('info') or {}
    webs = [w.get('url') for w in (info.get('websites') or []) if w.get('url')]
    socials = sorted({s.get('type') for s in (info.get('socials') or []) if s.get('type')})
    if config.REQUIRE_WEB_OR_SOCIALS and not webs and not socials:
        return False, ['tidak ada website/sosmed terdaftar — proyek anonim total']
    if webs:
        hidup = any(_website_hidup(u) for u in webs[:2])
        if not hidup:
            return False, ['website terdaftar tapi tidak bisa dibuka']
        notes.append(f'website aktif ({len(webs)})')
    if socials:
        notes.append('sosmed: ' + ', '.join(socials[:3]))

    # 7. Tekanan beli vs jual (1 jam terakhir)
    h1 = ((pair.get('txns') or {}).get('h1') or {})
    buys = int(h1.get('buys') or 0)
    sells = int(h1.get('sells') or 0)
    if buys + sells > 0:
        ratio = buys / (buys + sells)
        if ratio < config.MIN_BUY_RATIO_H1:
            return False, [f'penjual dominan (rasio beli {ratio:.0%}/jam) — momentum mati']
        notes.append(f'rasio beli {ratio:.0%}/jam')

    # 8. Jangan beli di pucuk: tolak bila sudah pump gila dalam 1 jam
    pc = (pair.get('priceChange') or {}).get('h1')
    try:
        pc = float(pc) if pc is not None else 0
    except (TypeError, ValueError):
        pc = 0
    if pc > config.MAX_PUMP_H1_PCT:
        return False, [f'sudah +{pc:.0f}% dalam 1 jam — beli di pucuk']
    if pc:
        notes.append(f'h1 {pc:+.0f}%')

    return True, notes


def rugcheck_metrics(mint):
    """Metrik RugCheck terstruktur saat entry — untuk analisa, bukan untuk gating."""
    rep = fetch_report(mint)
    if rep is None:
        return {}
    locked_pct, burned = _lp_status(rep)
    fee = ((rep.get('transferFee') or {}).get('pct')) or 0
    try:
        fee = float(fee)
    except (TypeError, ValueError):
        fee = 0
    score = rep.get('score_normalised')
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    dangers = [x.get('name') for x in (rep.get('risks') or [])
               if x.get('level') == 'danger' and x.get('name')]
    return {
        'rc_score': score,
        'rc_mint_revoked': rep.get('mintAuthority') is None,
        'rc_freeze_revoked': rep.get('freezeAuthority') is None,
        'rc_lp_locked_pct': round(locked_pct, 1),
        'rc_lp_burned': bool(burned),
        'rc_top10_pct': round(_top10_pct(rep), 1),
        'rc_transfer_fee_pct': fee,
        'rc_dangers': dangers,
        'rc_rugged': bool(rep.get('rugged')),
    }
