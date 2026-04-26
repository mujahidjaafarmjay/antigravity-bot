# SKILL.md — Antigravity Trading Bot Design System
**Version:** 1.0  
**Author:** Mujahid Jaafar  
**Exchange:** Bybit Spot  
**Deployment:** Render (free tier) + GitHub + Google Sheets  
**Language:** Python 3.11+  
**Style:** Anthropic skill format — read this file before writing any trading bot code

---

## WHEN TO USE THIS SKILL

Trigger this skill whenever the task involves any of the following:

- Building or modifying a crypto trading bot
- Writing strategy logic (SMC, indicators, signals, confluence)
- Working on risk management, position sizing, or stop loss logic
- Bybit API integration (V5, spot category)
- Telegram bot command handling for a trading system
- Google Sheets persistence for trade logging
- Render deployment configuration for a Python bot
- Sharia compliance filtering for crypto pairs
- Candle data processing with pandas (Bybit format)
- Any file in: `exchange/`, `strategy/`, `risk/`, `notifications/`, `storage/`, `safety/`, `logger/`

Do NOT skip this file. Read it fully before writing any code.

---

## PROJECT IDENTITY

```
Bot name:     Antigravity SMC Bot
Trader:       Mujahid Jaafar (@mujahidjaafarmjay)
Account:      Bybit spot — $40 starting capital
Service ID:   srv-d7lptrvlk1mc7393e8n0
Render URL:   https://antigravity-bot-6gmr.onrender.com
Sheet ID:     1i8XBvUJVgp4ro13Waa3we1YdO4hNbQzO9Sc1nz1y7Z8
Sheet name:   Antigravity Trades
Telegram ID:  5643832174
```

---

## ARCHITECTURE — 7 LAYERS (READ BEFORE TOUCHING ANY FILE)

```
Layer 1  exchange/bybit_client.py   → Bybit V5 API (spot category only)
Layer 2  strategy/brain.py          → Triple Screen SMC signal engine
Layer 3  risk/manager.py            → Position sizing + daily halt logic
Layer 4  main.py                    → Async loop + order execution + Flask health
Layer 5  safety/sharia_filter.py    → Whitelist gate (runs before every trade)
Layer 6  notifications/             → Telegram alerts (notifier) + commands (handler)
Layer 7  storage/ + logger/         → Google Sheets persistence + CSV backup
```

**Dependency rule:** Lower layers must never import from higher layers.  
`brain.py` must never import `notifier.py`. `risk/` must never import `exchange/`.  
Only `main.py` is allowed to wire everything together.

---

## FILE STRUCTURE (EXACT — DO NOT DEVIATE)

```
render_bot/
├── main.py
├── config.py
├── requirements.txt
├── Procfile                         ← "web: python main.py"
├── runtime.txt                      ← "python-3.11.9"
├── .gitignore
├── exchange/
│   ├── __init__.py
│   └── bybit_client.py
├── strategy/
│   ├── __init__.py
│   └── brain.py
├── risk/
│   ├── __init__.py
│   └── manager.py
├── notifications/
│   ├── __init__.py
│   ├── notifier.py
│   └── command_handler.py
├── safety/
│   ├── __init__.py
│   └── sharia_filter.py
├── storage/
│   ├── __init__.py
│   └── google_sheets.py
├── logger/
│   ├── __init__.py
│   └── trade_logger.py
└── logs/
    └── trades.csv
```

Every package directory MUST have an `__init__.py` or imports will fail on Render.

---

## CONFIG RULES — ALL SECRETS FROM ENVIRONMENT VARIABLES

```python
# CORRECT
API_KEY = os.environ.get("BYBIT_API_KEY", "")

# FORBIDDEN — never do this
API_KEY = "BXxDbzKKSdAOpeCF8P"
```

**Every configurable value reads from `os.environ.get()`.**  
The default value (second argument) is the fallback for local development only.

### Required Render environment variables
```
BYBIT_API_KEY             → Bybit API key (Read + Spot Trade only)
BYBIT_API_SECRET          → Bybit API secret
TELEGRAM_TOKEN            → From @BotFather
TELEGRAM_CHAT_ID          → Numeric ID from @userinfobot (5643832174)
MODE                      → "paper" | "testnet" | "live"
GOOGLE_SHEETS_CREDENTIALS → Full single-line JSON of service account key
GOOGLE_SHEET_ID           → Sheet ID from URL (not name)
GOOGLE_SHEET_NAME         → "Antigravity Trades"
DAILY_LOSS_LIMIT          → Float, percent (e.g. "5.0")
RISK_PER_TRADE            → Float, percent (e.g. "2.0")
MAX_OPEN_TRADES           → Integer (e.g. "2")
REWARD_TO_RISK            → Float (e.g. "2.0")
```

### Config values (current production settings)
```python
MODE                       = "live"           # currently live
TESTNET                    = False            # derived from MODE
MAX_RISK_PER_TRADE_PERCENT = 2.0             # % of balance per trade
MAX_OPEN_TRADES            = 2               # never exceed this
DAILY_LOSS_LIMIT_PERCENT   = 1.0            # halt at 1% daily loss (conservative)
REWARD_TO_RISK_RATIO       = 2.0            # minimum 1:2 RR
TIMEFRAME_MAIN             = "60"           # 1H — entry signals
TIMEFRAME_TREND            = "240"          # 4H — trend filter
TIMEFRAME_DAILY            = "D"            # Daily — macro filter
MA_FAST                    = 50
MA_SLOW                    = 200            # requires 250+ candles to compute
RSI_PERIOD                 = 14
```

---

## BYBIT API — CRITICAL RULES

### Library
```python
from pybit.unified_trading import HTTP  # pybit>=5.0.0

session = HTTP(
    testnet=config.TESTNET,
    api_key=config.API_KEY,
    api_secret=config.API_SECRET,
    domain="bytick",    # NOT "bybit" — "bytick" is more stable
    timeout=30,
)
```

### Category
Always pass `category="spot"` on every V5 call. Never use futures endpoints.

### Balance — the account type problem
Bybit accounts have THREE possible locations for USDT balance.  
**Always try all three in order. Never break early.**

```python
for acc_type in ["UNIFIED", "SPOT", "FUND"]:
    resp = session.get_wallet_balance(accountType=acc_type, coin="USDT")
    if resp.get("retCode") != 0:
        continue
    list_data = resp["result"].get("list", [])
    if not list_data:
        continue          # ← MUST use continue, not break
    for item in list_data[0].get("coin", []):
        if item["coin"] == "USDT":
            val = float(item.get("walletBalance") or
                        item.get("availableToWithdraw") or
                        item.get("equity") or 0)  # ← or 0, never float("")
            if val > 0:
                return val
```

**Known bug to avoid:** `float(item.get("walletBalance", 0))` crashes when  
Bybit returns `""` for zero-balance coins. Always use `or 0` pattern.

### Candle direction
Bybit V5 `get_kline()` returns candles **newest-first**.  
Always sort ascending before any indicator calculation:

```python
df = df.sort_values("time").reset_index(drop=True)
```

### Candle limit
MA_SLOW = 200 requires minimum 250 candles. Always fetch `limit=250`.  
Never use `limit=100` — MA200 will always be NaN and trend filter will break.

### Closed candle rule — CRITICAL
Never evaluate signals on `iloc[-1]` (the live, still-forming candle).  
Always use `iloc[-2]` (last fully closed candle).

```python
def _last_closed(self, df):
    if len(df) < 2:
        return df.iloc[-1]   # edge case only
    return df.iloc[-2]       # always use this for signals
```

### Order precision
```python
# Fetch basePrecision from instruments_info, cache it
step_str = instruments_info["basePrecision"]
if "." in step_str:
    decimals = len(step_str.rstrip("0").split(".")[1])
    qty = math.floor(qty * 10**decimals) / 10**decimals
else:
    qty = int(qty)
```

### Paper mode
```python
if config.MODE == "paper":
    return {"retCode": 0, "result": {"orderId": f"paper_{int(time.time())}"}}
```
Paper mode must short-circuit ALL order placement. No real API calls for orders.

---

## STRATEGY — TRIPLE SCREEN SMC

The bot uses three timeframes that must ALL agree before a trade fires.

### Screen 1 — Daily macro filter
```
Price > MA200(Daily) → daily_trend_up = True
Otherwise           → daily_trend_up = False → skip all entries
```

### Screen 2 — 4H trend confirmation
```
MA50(4H) > MA200(4H) → trend_4h_up = True  (Golden Cross structure)
MA50(4H) NaN         → return HOLD (not enough data)
MA50(4H) < MA200(4H) → trend_4h_up = False → no entries
```

### Screen 3 — 1H entry signals (all three required)
```
Condition A: near_ob = True
  → Current price is AT or WITHIN a Bullish Order Block
  → OB = last bearish candle before an impulsive bullish move (>2× avg body)
  → "Near" = ob["bottom"] <= price <= ob["top"] * 1.005

Condition B: fvgs = non-empty list
  → Fair Value Gap exists (df["high"].iloc[i-2] < df["low"].iloc[i])
  → Confirms price imbalance — institutional interest

Condition C: vol_surge = True
  → Current candle volume > 1.2× 20-period average volume
  → Confirms real participation, not noise
```

### Decision logic
```python
if daily_trend_up and trend_4h_up and near_ob and fvgs and vol_surge:
    return "BUY", None
elif approaching_ob:              # within 2% of OB but not yet inside
    return "POTENTIAL", data      # alert only, no trade
else:
    return "HOLD", None
```

### Stop loss placement
```python
# Last 10 closed 1H candles' lowest wick — below liquidity grab zone
closed = df_1h.iloc[:-1]          # drop live candle
stop   = float(closed["low"].tail(10).min())
```

**Validate before use:**
```python
if stop_loss <= 0 or stop_loss >= current_price:
    skip_trade()    # invalid — never place this order
```

### Take profit
```python
take_profit = current_price + (current_price - stop_loss) * config.REWARD_TO_RISK_RATIO
# Minimum 1:2 RR. With REWARD_TO_RISK=2.0, TP = entry + 2×(entry-SL)
```

### Break-even shield
```python
profit_pct = (current_price - trade["entry"]) / trade["entry"] * 100
if profit_pct >= 1.5 and trade["sl"] < trade["entry"]:
    active_trades[symbol]["sl"] = trade["entry"]
    # Trade is now risk-free. Notify Telegram.
```

---

## RISK MANAGEMENT — NON-NEGOTIABLE RULES

### Position sizing formula
```python
risk_amount = balance * (RISK_PER_TRADE_PERCENT / 100)  # e.g. $40 × 2% = $0.80
price_risk  = entry_price - stop_loss
qty         = risk_amount / price_risk
# Cap: never exceed 40% of balance in one trade
max_value   = balance * 0.40
if qty * entry_price > max_value:
    qty = max_value / entry_price
```

### Zero balance guard
```python
if balance <= 0:
    return -1.0    # signal to caller: balance unreadable, skip trade
```
Never return 0.0 for missing balance — caller must distinguish "zero qty" from "balance error".

### Daily loss limit
```python
# Check ONCE before the pair scan loop — not inside it
halted, msg = risk.is_daily_limit_hit(balance)
if halted:
    return balance   # stop scanning entirely

# Guard against zero-balance false halt
if balance <= 0:
    return False, "Balance unreadable — skipping daily limit check"

# Guard against 0 >= 0 = True
if limit > 0 and lost >= limit:
    halt()
```

### Daily limit resets
- Automatically on new UTC date (fresh `daily_stats.json`)
- Manually via `/resume` Telegram button → calls `risk.reset_daily_halt()`
- `reset_daily_halt()` sets both `halted=False` AND `loss_usdt=0.0`

### Current risk numbers ($40 account)
```
Max risk per trade:  $0.80  (2%)
Max position:        $16.00 (40%)
Daily loss halt:     $0.40  (1%)   ← very conservative, consider 5-6%
Max open trades:     2
Min reward:          $1.60  (2× risk)
```

---

## SHARIA COMPLIANCE — ALWAYS RUNS FIRST

```python
# In scan_markets() — before any API call or signal evaluation
if not sharia.is_compliant(symbol):
    continue    # skip immediately — no further processing
```

### Approved whitelist (25 pairs)
```python
WHITELIST_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT",
    "ATOMUSDT", "ADAUSDT", "DOTUSDT", "NEARUSDT", "INJUSDT",
    "SUIUSDT", "APTUSDT", "OPUSDT", "ARBUSDT", "TIAUSDT",
    "STXUSDT", "FILUSDT", "ARUSDT", "KASUSDT", "ICPUSDT",
    "TONUSDT", "QNTUSDT", "ENSUSDT", "GRTUSDT", "IMXUSDT",
]
```

### Screening criteria (from Islamic Finance reference)
A coin qualifies if and only if:
1. **Māl** — genuine benefit, retrievable, people have real inclination toward it
2. **Taqawwum** — lawful use case under Sharia
3. **Not riba-based** — no lending/borrowing with interest (excludes AAVE, Compound, JustLend)
4. **Not haram industry** — no gambling, adult content, alcohol, conventional finance
5. **Not pure speculation** — coin must be accepted somewhere as genuine medium or utility

Every trade logged with `Sharia_Status = "Verified"` in Google Sheets column M.

### Adding a new pair
1. Research the protocol's actual utility
2. Confirm no riba-based mechanism
3. Add to `WHITELIST_PAIRS` in `config.py`
4. Commit and push → Render auto-redeploys

---

## GOOGLE SHEETS — STRUCTURE AND RULES

### Four tabs (auto-created by bot on first run)
```
Tab 1: Antigravity Trades   ← main trade log (13 columns)
Tab 2: Active Trades        ← crash recovery source of truth
Tab 3: Summary              ← live formulas, no manual editing
Tab 4: BotMeta              ← pause state, key-value store
```

### Antigravity Trades — 13 column schema (EXACT ORDER)
```
A: Trade_ID        → UUID 8 chars e.g. "A3F7B2C1"
B: Timestamp       → "2026-04-07 23:28:00"
C: Symbol          → "SOLUSDT"
D: Entry_Price     → float
E: Stop_Loss       → float
F: Take_Profit     → float
G: Size_USDT       → qty × entry (float)
H: Status          → "OPEN" | "CLOSED" | "Closed_Manually"
I: Exit_Price      → float (blank while OPEN)
J: Fees            → buy_fee + sell_fee (0.1% each side)
K: Net_Profit      → gross_pnl - fees (THE REAL NUMBER)
L: SMC_Signal      → "1H_OB+FVG+4H_TREND+DAILY_MA200"
M: Sharia_Status   → "Verified" (always, from whitelist)
```

**Column K (Net_Profit) is the only number that matters.**  
Gross P&L is misleading — always show net after fees to the trader.

### Fee calculation
```python
BYBIT_FEE_RATE = 0.001  # 0.1% per side

buy_fee   = size_usdt   * BYBIT_FEE_RATE  # entry value
sell_fee  = exit_value  * BYBIT_FEE_RATE  # exit value
total_fees = buy_fee + sell_fee
net_profit = gross_pnl - total_fees
```

### Active Trades — crash recovery schema
```
A: Symbol          B: Entry_Price    C: Stop_Loss
D: Take_Profit     E: Size_USDT      F: Qty
G: Timestamp       H: Trade_ID
```

**On bot startup — Steps A through D (mandatory):**
```python
# A: Read Active Trades from Sheets
sheet_trades = storage.get_open_trades()

# B: Get live Bybit holdings (safe — wrapped in try/except)
bybit_holdings = set()  # {"SOLUSDT", "BTCUSDT", ...}

# C: Cross-reference — in Sheet but NOT in Bybit wallet
if sym not in bybit_holdings:
    storage.mark_closed_manually(sym)  # update Status column

# D: In both Sheet and Bybit → restore monitoring
active_trades[sym] = trade_data
```

### Sheets connection — JSON credentials
```python
# Private key newlines get escaped when pasted into Render env var
# ALWAYS apply this fix before parsing:
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

# Open by ID (most reliable) — fall back to name
if config.GOOGLE_SHEET_ID:
    wb = client.open_by_key(config.GOOGLE_SHEET_ID)
else:
    wb = client.open(config.GOOGLE_SHEET_NAME)
```

---

## TELEGRAM — ASYNC RULES

### Library
```python
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
# python-telegram-bot>=20.0  (async — v20 breaking change from v13)
```

### All sends MUST be awaited
```python
# CORRECT
await self.bot.send_message(chat_id=..., text=..., parse_mode="HTML")

# WRONG — was the original bug that dropped all trade entry alerts
asyncio.ensure_future(self.bot.send_message(...))
```

### Always use asyncio.wait_for with timeout
```python
await asyncio.wait_for(
    self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML"),
    timeout=10,
)
```

### parse_mode is always "HTML" — not "Markdown"
HTML is more predictable. Use `<b>`, `<i>`, `<code>` tags.  
Escape `&` as `&amp;` in message strings.

### Command handler init order — CRITICAL
```python
def __init__(self, notifier, bybit, storage, risk):
    self.storage = storage    # MUST be first — _load_pause_state() needs it
    self.notifier = notifier
    self.bybit   = bybit
    self.risk    = risk
    self.paused  = self._load_pause_state()   # safe now
```

### 8 Telegram buttons
```python
keyboard = [
    ["📊 Status",     "💰 Balance"],
    ["📈 Open Trades", "📅 Profit Report"],
    ["🔍 Scan Setups", "🛑 Pause Bot"],
    ["🚀 Resume Bot",  "❓ Help"],
]
```

### Resume must reset daily halt
```python
async def resume(self, update, context):
    self.paused = False
    self._save_pause_state()
    if self.risk:
        self.risk.reset_daily_halt()  # BOTH pause AND halt must clear
```

### Telegram retry — clean shutdown before rebuild
```python
except Exception:
    try:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
    except Exception:
        pass
    app = None
    await asyncio.sleep(30)
```

---

## MAIN LOOP — STRUCTURE AND RULES

### Flask health server
```python
# Start in daemon thread BEFORE asyncio.run(main())
threading.Thread(target=_run_health_server, daemon=True).start()

# Flask config for Render
health_app.run(
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    debug=False,
    use_reloader=False,    # CRITICAL — reloader breaks asyncio
    threaded=False,        # single-threaded Flask is safe here
)
```

### Health endpoints
```
GET /ping    → returns "OK" 200  (UptimeRobot keep-alive)
GET /status  → returns JSON with mode, active_trades, uptime, sheets
```

### Loop sleep — responsive to pause state
```python
if not cmd_handler.paused:
    await scan_markets()
    await asyncio.sleep(300)   # 5 min after scan
else:
    await asyncio.sleep(60)    # 1 min when paused — stay responsive to commands
```

### Daily limit gate — check ONCE before pair loop
```python
# CORRECT — one check, one disk read
halted, msg = risk.is_daily_limit_hit(balance)
if halted:
    return balance

for symbol in config.WHITELIST_PAIRS:
    ...  # no limit check inside the loop

# WRONG — 25 disk reads per scan
for symbol in config.WHITELIST_PAIRS:
    halted, msg = risk.is_daily_limit_hit(balance)  # never do this
```

### Import placement — no inline imports
```python
# CORRECT — all imports at top of file
import pandas as pd
from exchange.bybit_client import BybitClient

# WRONG — import inside function body
async def scan_markets():
    import pandas as pd   # works but misleading — never do this
```

### Trade close — always use the unified helper
```python
async def close_trade(symbol, exit_price, reason):
    trade      = active_trades[symbol]
    qty        = trade.get("qty", trade.get("size_usdt", 0) / trade["entry"])
    gross_pnl  = round((exit_price - trade["entry"]) * qty, 6)
    net_profit = storage.log_trade_close(trade, exit_price, gross_pnl, 0)
    logger.log_trade_close(symbol, exit_price, gross_pnl)
    risk.record_pnl(gross_pnl)
    del active_trades[symbol]
    await notifier.send_message(...)   # show gross, fees, net
```

---

## RENDER DEPLOYMENT — CHECKLIST

### Files required for Render
```
Procfile     → "web: python main.py"
runtime.txt  → "python-3.11.9"
requirements.txt
.gitignore   → must exclude .env, __pycache__, daily_stats.json, open_trades.json
```

### requirements.txt (current)
```
pybit>=5.0.0
python-telegram-bot>=20.0
pandas
numpy
flask
gspread>=6.0.0
oauth2client>=4.1.3
python-dotenv
```

### UptimeRobot
Render free tier spins down after 15 min of no traffic.  
UptimeRobot must ping `/ping` every 5 minutes.  
Without this the bot stops scanning.

### Ephemeral filesystem warning
Render free tier has NO persistent disk.  
Files written to `logs/` are lost on every restart.  
`daily_stats.json` and `trades.csv` reset on restart.  
Google Sheets is the ONLY persistent storage.

### Push-to-deploy flow
```bash
git add .
git commit -m "describe change"
git push              # Render auto-detects push and redeploys in ~2 min
                      # Telegram startup message confirms new deploy
```

---

## TRADING PRINCIPLES — FROM THE TRADER

These are not suggestions. They are requirements built into the system.

### 1. Never trade without a stop loss
Every trade has SL set before order placement.  
Stop loss = below the liquidity grab wick of last 10 candles.  
If stop loss calculation fails validation → skip the trade.

### 2. Minimum 1:2 reward-to-risk always
Take profit must be at least 2× the stop distance.  
This means you can be wrong 40% of the time and still be profitable.

### 3. Maximum 2% capital at risk per trade
On $40 balance = max $0.80 at risk.  
Position sized by formula, not by gut.

### 4. Never average down
The bot does not add to losing positions.  
If SL is hit — trade closes. Full stop.

### 5. Daily loss limit enforces discipline
Bot halts automatically. Resume is manual.  
This prevents revenge trading after a bad day.

### 6. Sharia compliance is not optional
Every trade gated by `sharia.is_compliant()`.  
Every trade logged with `Sharia_Status = "Verified"`.  
This is a permanent audit trail, not a suggestion.

### 7. Only closed candles for signals
Live candle data changes every second.  
All signal logic uses `iloc[-2]` — the last completed candle.

### 8. Fees are real — always show net profit
`gross_pnl` is a lie. `net_profit = gross - fees` is reality.  
Column K in Google Sheets is the only number that matters.

---

## KNOWN BUGS — HISTORY (DO NOT REINTRODUCE)

| Bug | Location | Root cause | Fix applied |
|-----|----------|------------|-------------|
| Balance $0 | bybit_client.py | `break` instead of `continue` on empty account type | Try all 3 types with `continue` |
| Daily limit instant halt | risk/manager.py | `0 >= 0 = True` when balance=0 | Guard: `if balance <= 0: return False` |
| Sheets "not configured" | google_sheets.py | `\\n` in private_key + name-only open | `.replace("\\n","\n")` + open by ID |
| DAILY_LOSS_LIMIT ignored | config.py | Hardcoded 5.0, not reading env var | `os.environ.get("DAILY_LOSS_LIMIT")` |
| Storage before pause check | command_handler.py | `_load_pause_state()` before `self.storage` | Assign `self.storage` first in `__init__` |
| Resume didn't clear halt | command_handler.py | `resume()` only set `paused=False` | Call `risk.reset_daily_halt()` in resume |
| Trade alerts not sent | notifier.py | `ensure_future()` in async context | Proper `await` on all sends |
| Profit report always $0 | command_handler.py | Read `"P&L"` but column is `"Net_Profit"` | Use `row.get("Net_Profit")` |
| MA200 always NaN | bybit_client.py | `limit=100` but MA needs 200 candles | `limit=250` always |
| Signals on live candle | brain.py | `iloc[-1]` (open candle) | `iloc[-2]` (last closed) |
| MAs computed backwards | brain.py | Bybit newest-first not sorted | `sort_values("time")` ascending |
| Startup crash in recovery | main.py | `bybit.session.get_wallet_balance()` direct call | Wrap in `try/except`, safe method |

---

## CODE QUALITY STANDARDS

### Error handling pattern
```python
try:
    result = api_call()
except Exception as e:
    print(f"[ModuleName] context: {e}")
    return safe_default_value
```
Never let exceptions propagate to the main loop unhandled.  
Always log with `[ModuleName]` prefix for Render log readability.

### Async pattern
```python
# All Telegram sends: always await, always timeout
await asyncio.wait_for(coro, timeout=10)

# All tasks: use asyncio.create_task() not ensure_future()
asyncio.create_task(cmd_handler.run_listener())
```

### String formatting in Telegram messages
```python
# Use f-strings with HTML tags
f"<b>Balance:</b> ${balance:.4f} USDT"

# Escape ampersands
f"P&amp;L: {pnl:+.4f}"

# Never use Markdown — HTML only
```

### Numeric precision
```python
round(value, 4)   # prices
round(value, 6)   # quantities and P&L  
round(value, 2)   # percentages
float(x or 0)     # safe conversion — never float("") or float(None)
```

---

## TESTING PROGRESSION — MANDATORY ORDER

```
1. paper mode   → real prices, zero real orders, 2+ weeks minimum
2. testnet mode → real orders on Bybit Testnet with fake money
3. live mode    → real money, start small, never skip paper/testnet
```

**Never jump from paper to live.**  
**Never deploy a change to live without testing in paper first.**

---

## QUICK REFERENCE — COMMON PATTERNS

### Adding a new indicator to brain.py
```python
def _add_new_indicator(self, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()                          # never mutate input
    # compute on sorted df
    df["new_col"] = ...
    return df

# Use in analyze():
df_1h = self._add_new_indicator(df_1h)
last  = self._last_closed(df_1h)           # always last closed
value = last["new_col"]
```

### Adding a new Telegram command
```python
# In command_handler.py:
async def my_command(self, update, context):
    await update.message.reply_text("text", parse_mode="HTML")

# Register in run_listener():
app.add_handler(CommandHandler("mycommand", self.my_command))

# Add to handle_message():
elif text == "🆕 New Button":
    await self.my_command(update, context)

# Add to keyboard:
self.keyboard.append(["🆕 New Button"])
```

### Adding a new pair to the whitelist
```python
# 1. Research: does it have genuine Māl? No riba? No haram?
# 2. Edit config.py:
WHITELIST_PAIRS = [..., "NEWUSDT"]
# 3. git add . && git commit -m "add NEWUSDT" && git push
```

### Logging a new field to Google Sheets
```python
# 1. Add column header to TRADE_HEADERS list in google_sheets.py
# 2. Add value to sheet.append_row() call in log_trade_open()
# 3. Update log_trade_close() if value changes on exit
# 4. Update trade_logger.py HEADERS to match
# 5. Update command_handler.py profit_report if field is needed there
```

---

## FINAL CHECKLIST — BEFORE EVERY PUSH TO GITHUB

- [ ] No hardcoded API keys or secrets in any `.py` file
- [ ] `config.py` uses `os.environ.get()` for every secret
- [ ] All Telegram sends are `await`ed
- [ ] Candles sorted ascending before indicator computation
- [ ] Signals use `_last_closed()` not `iloc[-1]`
- [ ] Sharia filter called before every trade
- [ ] Stop loss validated before position sizing
- [ ] Daily limit checked once before the pair loop
- [ ] `__init__.py` exists in every package directory
- [ ] `Procfile`, `runtime.txt`, `requirements.txt` present
- [ ] No `import` statements inside functions
- [ ] `float(x or 0)` used for all Bybit numeric fields
- [ ] `storage.log_trade_open()` AND `logger.log_trade_open()` both called on entry
- [ ] `storage.log_trade_close()` AND `logger.log_trade_close()` both called on exit
- [ ] Python syntax: `python3 -c "import ast; ast.parse(open('file.py').read())"` on every changed file

---

*This skill was built from a real trading bot — the Antigravity SMC Bot — deployed on Render and trading live on Bybit. Every rule in this document was learned from a real bug, a real failure, or a real principle from Islamic Finance. Treat it with the same respect.*
