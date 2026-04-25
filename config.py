# ============================================================
#  config.py — All settings read from environment variables.
#  Fix Bug 5: DAILY_LOSS_LIMIT now reads from env var.
#  Fix: GOOGLE_SHEET_ID added so sheet can open by ID.
# ============================================================
import os

# ── Bybit API ────────────────────────────────────────────────
API_KEY    = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET", "")

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Mode ─────────────────────────────────────────────────────
MODE    = os.environ.get("MODE", "paper")
TESTNET = MODE == "testnet"

# ── Google Sheets ─────────────────────────────────────────────
GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "")
GOOGLE_SHEET_NAME         = os.environ.get("GOOGLE_SHEET_NAME", "Antigravity Trades")
GOOGLE_SHEET_ID           = os.environ.get("GOOGLE_SHEET_ID", "")  # Fix Bug 4

# ── Risk Management ──────────────────────────────────────────
MAX_RISK_PER_TRADE_PERCENT = float(os.environ.get("RISK_PER_TRADE", "2.0"))
MAX_OPEN_TRADES            = int(os.environ.get("MAX_OPEN_TRADES", "2"))
# Fix Bug 5: reads DAILY_LOSS_LIMIT from env var (user set 1.0 in Render)
DAILY_LOSS_LIMIT_PERCENT   = float(os.environ.get("DAILY_LOSS_LIMIT", "5.0"))
REWARD_TO_RISK_RATIO       = float(os.environ.get("REWARD_TO_RISK", "2.0"))

# ── Sharia-Compliant Whitelist ───────────────────────────────
WHITELIST_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT",
    "ATOMUSDT", "ADAUSDT", "DOTUSDT", "NEARUSDT", "INJUSDT",
    "SUIUSDT", "APTUSDT", "OPUSDT", "ARBUSDT", "TIAUSDT",
    "STXUSDT", "FILUSDT", "ARUSDT", "KASUSDT", "ICPUSDT",
    "TONUSDT", "QNTUSDT", "ENSUSDT", "GRTUSDT", "IMXUSDT",
]

# ── Strategy ─────────────────────────────────────────────────
TIMEFRAME_MAIN  = "60"
TIMEFRAME_TREND = "240"
TIMEFRAME_DAILY = "D"
RSI_PERIOD = 14
MA_FAST    = 50
MA_SLOW    = 200
