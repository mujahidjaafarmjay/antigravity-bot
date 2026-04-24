# Antigravity SMC Trading Bot

Bybit spot trading bot — SMC strategy, Sharia-compliant filter,
2% risk rule, Telegram dashboard, Google Sheets persistence.
Designed to run 24/7 on Render free tier.

---

## Deploy to Render (step by step)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Step 2 — Create Render Web Service
1. Go to https://render.com → New → Web Service
2. Connect your GitHub repo
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Instance Type:** Free

### Step 3 — Set Environment Variables in Render
Go to your service → Environment → Add these:

| Key | Value |
|-----|-------|
| `BYBIT_API_KEY` | Your Bybit API key |
| `BYBIT_API_SECRET` | Your Bybit API secret |
| `TELEGRAM_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `MODE` | `paper` (start here), then `live` |
| `GOOGLE_SHEETS_CREDENTIALS` | Full JSON content of service account key |
| `GOOGLE_SHEET_NAME` | `Antigravity Trades` |

### Step 4 — Set up Google Sheets (for persistence)
1. Go to https://console.cloud.google.com
2. Create project → Enable Google Sheets API
3. Credentials → Service Account → Create → Download JSON key
4. Create a Google Sheet named `Antigravity Trades`
5. Share the sheet with the service account email (Editor)
6. Paste the entire JSON content as `GOOGLE_SHEETS_CREDENTIALS` in Render

### Step 5 — Keep-alive with UptimeRobot
1. Sign up at https://uptimerobot.com (free)
2. Add New Monitor → HTTP(s)
3. URL: `https://YOUR-BOT-NAME.onrender.com/ping`
4. Interval: every 5 minutes
5. Save

### Step 6 — Deploy
Click **Deploy** in Render. Watch the logs.
You should receive a Telegram startup message within 30 seconds.

---

## Monitoring endpoints
| URL | Purpose |
|-----|---------|
| `/ping` | Returns `OK` — used by UptimeRobot |
| `/status` | Returns JSON with bot state, mode, active trades |

---

## Telegram commands (buttons on your phone)
| Button | Action |
|--------|--------|
| 📊 Status | Bot status + balance |
| 💰 Balance | USDT balance |
| 📈 Open Trades | Active trades + P&L |
| 📅 Profit Report | Trade history summary |
| 🔍 Scan Setups | Trigger manual scan |
| 🛑 Pause Bot | Stop new entries |
| 🚀 Resume Bot | Resume scanning |

---

## What happens on Render restart
1. Bot starts and sends "🔄 Bot Restarted" to Telegram
2. Reads open trades from Google Sheets
3. Restores virtual SL/TP for all recovered trades
4. Resumes monitoring immediately

Without Google Sheets configured, open trades are lost on restart.

---

## File structure
```
├── main.py                    ← Entry point + health server
├── config.py                  ← Settings (reads env vars)
├── requirements.txt
├── Procfile                   ← Render start command
├── .gitignore
├── exchange/bybit_client.py   ← Bybit V5 API
├── strategy/brain.py          ← SMC signal logic
├── risk/manager.py            ← Position sizing
├── notifications/
│   ├── notifier.py            ← Telegram alerts
│   └── command_handler.py     ← Telegram buttons
├── safety/sharia_filter.py    ← Pair whitelist
├── logger/trade_logger.py     ← Local CSV backup
├── storage/google_sheets.py   ← Cloud persistence
└── logs/trades.csv            ← Local trade log
```

---

## Security rules
- API keys are NEVER in the code — only in Render environment variables
- .gitignore excludes all secret files
- Never enable withdrawal permissions on your Bybit API key
- Set IP restrictions on your API key to Render's IP range
