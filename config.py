# ============================================================
#  config.py — Final Optimized Settings
# ============================================================
import os

# ── Bybit API ────────────────────────────────────────────────
API_KEY    = os.environ.get("BYBIT_API_KEY", "").strip()
API_SECRET = os.environ.get("BYBIT_API_SECRET", "").strip()

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# ── Mode ─────────────────────────────────────────────────────
MODE    = os.environ.get("MODE", "paper").strip().lower()
TESTNET = MODE == "testnet"

# ── Google Sheets ─────────────────────────────────────────────
GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "").strip()
GOOGLE_SHEET_NAME         = os.environ.get("GOOGLE_SHEET_NAME", "Antigravity Trades").strip()
GOOGLE_SHEET_ID           = os.environ.get("GOOGLE_SHEET_ID", "").strip()

# ── Sharia-Compliant Whitelist (25 Vetted Pairs) ──────────────
HALAL_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT",
    "ATOMUSDT", "ADAUSDT", "DOTUSDT", "NEARUSDT", "INJUSDT",
    "SUIUSDT", "APTUSDT", "OPUSDT", "ARBUSDT", "TIAUSDT",
    "STXUSDT", "FILUSDT", "ARUSDT", "KASUSDT", "ICPUSDT",
    "TONUSDT", "QNTUSDT", "ENSUSDT", "GRTUSDT", "IMXUSDT"
]

# ── Risk Management ──────────────────────────────────────────
# Risk per trade is dynamic (calculated in risk_manager.py)
MAX_OPEN_TRADES            = int(os.environ.get("MAX_OPEN_TRADES", "2"))
DAILY_LOSS_LIMIT_PERCENT   = float(os.environ.get("DAILY_LOSS_LIMIT", "5.0"))
REWARD_TO_RISK_RATIO       = 2.2  # Gross RR to cover fees (1:2.0 net)
MAX_POSITION_SIZE_PERCENT  = 40.0 # Max 40% of balance per trade

# ── Strategy Constants ───────────────────────────────────────
MA_FAST    = 50
MA_SLOW    = 200
OB_WINDOW  = 10  # Lookback for Order Blocks
FVG_WINDOW = 3   # Lookback for Fair Value Gaps
VOL_MULTIPLIER = 1.2
VOL_WINDOW     = 20
SCORE_THRESHOLD = 3
TEST_MODE_THRESHOLD = 3

# ── Execution ────────────────────────────────────────────────
TIMEFRAME = "60" # 1H Timeframe
COOLDOWN_MINUTES = 30
SPREAD_LIMIT = 0.002 # 0.2% (Balanced: Execution vs Cost)
API_DELAY = 0.4 # 0.3-0.5s delay
RETRY_ATTEMPTS = 3
BALANCE_CACHE_SECONDS = 30
