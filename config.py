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
TRADING_MODE = "live" if MODE == "live" else "paper"

# ── Production Safety & Calibration ──────────────────────────
ENABLE_LIVE_TRADING  = os.environ.get("ENABLE_LIVE_TRADING", "False").lower() == "true"
CALIBRATION_MODE      = os.environ.get("CALIBRATION_MODE", "True").lower() == "true"
MAX_DAILY_LOSS_USDT   = float(os.environ.get("MAX_DAILY_LOSS_USDT", "2.0"))
KILL_SWITCH_COOLDOWN_HOURS = int(os.environ.get("KILL_SWITCH_COOLDOWN", "6"))

# ── Tier 4 Volatility & Equity Protection ────────────────────
VOLATILITY_LOOKBACK      = 14
VOLATILITY_LIMIT_MULT    = 2.5 # Skip trade if candle > 2.5x ATR
EQUITY_PROTECT_TRADES    = 20  # Lookback window for equity protection
EQUITY_PROTECT_THRESHOLD = 0.8 # PF must be > 0.8 over last window

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
MAX_OPEN_TRADES            = int(os.environ.get("MAX_OPEN_TRADES", "1")) # Capped to 1 for $40
DAILY_LOSS_LIMIT_PERCENT   = float(os.environ.get("DAILY_LOSS_LIMIT", "5.0"))
REWARD_TO_RISK_RATIO       = 2.2  # Gross RR to cover fees (1:2.0 net)
MAX_POSITION_SIZE_PERCENT  = 40.0 # Max 40% of balance per trade
MAX_POSITION_SIZE_USDT     = 10.0 # Hard cap for small accounts
MIN_TRADE_USDT             = 6.0  # Bybit minimum is ~$5, we use $6 for safety

# ── Strategy Constants ───────────────────────────────────────
MA_FAST    = 50
MA_SLOW    = 200
OB_WINDOW  = 10  # Lookback for Order Blocks
FVG_WINDOW = 3   # Lookback for Fair Value Gaps
VOL_MULTIPLIER = 1.2
VOL_WINDOW     = 20
SCORE_THRESHOLD = 4
MIN_SCORE_TO_TRADE = 3 # During Calibration, we log Score 3 but track separately
TEST_MODE_THRESHOLD = 3

# ── Execution ────────────────────────────────────────────────
TIMEFRAME = "60" # 1H Timeframe
COOLDOWN_MINUTES = 30
SPREAD_LIMIT = 0.0015 # 0.15% (Tighter spread for small accounts)
API_DELAY = 0.4 # 0.3-0.5s delay
RETRY_ATTEMPTS = 3
BALANCE_CACHE_SECONDS = 30
