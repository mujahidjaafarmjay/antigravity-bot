# ============================================================
#  config.py — All settings. Secrets from environment vars.
#  NEVER put real API keys in this file.
# ============================================================
import os

# ── API Keys (set in Render Environment Variables) ──────────
API_KEY    = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET", "")

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Mode: "paper" | "testnet" | "live" ───────────────────────
MODE    = os.environ.get("MODE", "paper")
TESTNET = MODE == "testnet"

# ── Google Sheets persistence ────────────────────────────────
GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "")
GOOGLE_SHEET_NAME         = os.environ.get("GOOGLE_SHEET_NAME", "Antigravity Trades")

# ── Risk Management ──────────────────────────────────────────
MAX_RISK_PER_TRADE_PERCENT = 2.0
MAX_OPEN_TRADES            = 2
DAILY_LOSS_LIMIT_PERCENT   = 5.0
REWARD_TO_RISK_RATIO       = 2.0

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
