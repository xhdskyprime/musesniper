"""Konfigurasi paper-trading sniper bot (akun demo, uang virtual)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ---- Akun demo ----
STARTING_CASH = 500.0        # modal virtual USD
TRADE_SIZE_USD = 10.0         # ukuran tiap snipe
MAX_POSITIONS = 20            # maks posisi terbuka bersamaan
SCAN_INTERVAL = 60            # detik antar scan

# ---- Mode degen: entry longgar, hit cepat di listing baru ----
# True = longgar (eksperimen atas permintaan user 2026-10-05),
# False = kembali ke filter ketat.
DEGEN_MODE = True
DEGEN_MAX_TRANSFER_FEE_PCT = 20.0  # di mode degen, hanya tolak pajak > ini

# ---- Gerbang kualitas (filter token baru) ----
CHAIN = 'solana'
MIN_LIQUIDITY_USD = 3000      # dulu 15000 — listing baru likuiditasnya kecil
MIN_VOLUME_H24_USD = 5000     # dulu 20000
MIN_TXNS_H24 = 20             # dulu 100
MAX_PAIR_AGE_HOURS = 72
MIN_LIQ_TO_MCAP = 0.01        # dulu 0.02

# ---- Analisa mendalam pra-beli (RugCheck + info DexScreener) ----
SAFETY_ENABLED = True
MAX_RUGCHECK_SCORE = 40       # skor risiko 0-100; tolak bila di atas ini
REQUIRE_MINT_REVOKED = True   # tolak bila dev masih bisa mencetak token
REQUIRE_FREEZE_REVOKED = True # tolak bila dev masih bisa membekukan token
MIN_LP_LOCKED_PCT = 80.0      # % LP terkunci/dibakar minimal (anti rug)
MAX_TOP10_HOLDERS_PCT = 60.0  # tolak bila 10 holder teratas kuasai > ini
MAX_TRANSFER_FEE_PCT = 5.0    # tolak pajak transfer tersembunyi > ini
REQUIRE_WEB_OR_SOCIALS = True # wajib ada website atau sosmed terdaftar
MIN_BUY_RATIO_H1 = 0.35       # rasio beli minimum vs total txn 1 jam
MAX_PUMP_H1_PCT = 300.0       # tolak bila sudah +x% dalam 1 jam (pucuk)
RUGCHECK_TIMEOUT = 20

# ---- Aturan exit (hit and run — mode degen: keluar cepat saat untung) ----
# Trailing stop BERTINGKAT dari entry (tanpa jual sebagian):
# tiap kelipatan TRAIL_STEP_PCT tercapai, level itu jadi penahan (stop).
# Di bawah +50% pertama, stop di entry - TRAIL_GAP_PCT (pelindung awal).
TRAIL_STEP_PCT = 50.0
TRAIL_GAP_PCT = 20.0
LIQ_DROP_EXIT_PCT = -40.0     # jual bila likuiditas anjlok 40% dari saat beli
TIME_STOP_HOURS = 24          # maks pegang 24 jam

# ---- Simulasi biaya ----
SLIPPAGE_PCT = 2.0            # slippage per transaksi (paper)
FEE_PCT = 0.3                 # fee dex per transaksi

# ---- Telegram (opsional, isi via environment) ----
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

DASHBOARD_PORT = 5001
