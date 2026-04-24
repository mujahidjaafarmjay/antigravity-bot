# ============================================================
#  notifications/command_handler.py
#  Fix #5:  profit_report reads correct file (logs/trades.csv)
#  Fix #8:  pause state saved to Google Sheets, not disk file
#  Fix #9:  no second BybitClient — receives bybit from main
# ============================================================
import asyncio
import os
import csv
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import config


class TelegramCommandHandler:
    def __init__(self, notifier, bybit, storage):
        """
        Fix #9: bybit is passed in from main — no duplicate client.
        storage is passed in so pause state can survive restarts.
        """
        self.notifier      = notifier
        self.bybit         = bybit         # Fix #9: injected, not created here
        self.storage       = storage       # Fix #8: for persistent pause state
        self.paused        = self._load_pause_state()
        self.scan_requested    = False
        self.backtest_requested= False
        self.active_trades = {}

        self.keyboard = [
            ["📊 Status",    "💰 Balance"],
            ["📈 Open Trades","📅 Profit Report"],
            ["🔍 Scan Setups","🛑 Pause Bot"],
            ["🚀 Resume Bot", "❓ Help"],
        ]
        self.reply_markup = ReplyKeyboardMarkup(
            self.keyboard, resize_keyboard=True
        )

    # ── Pause state persistence (Fix #8) ─────────────────────
    def _load_pause_state(self) -> bool:
        """Read pause state from Google Sheets meta, not disk file."""
        try:
            if self.storage and self.storage.is_connected:
                return self.storage.get_bot_meta("paused") == "true"
        except Exception:
            pass
        return False

    def _save_pause_state(self):
        """Persist pause state to Google Sheets (Fix #8)."""
        try:
            if self.storage and self.storage.is_connected:
                self.storage.set_bot_meta("paused", "true" if self.paused else "false")
        except Exception:
            pass

    # ── Command handlers ──────────────────────────────────────

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 <b>Antigravity Bot Command Center</b>\n"
            "Use the buttons below to control your bot.",
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        balance     = self.bybit.get_balance("USDT")
        status_text = "🟢 <b>ACTIVE</b>" if not self.paused else "🟡 <b>PAUSED</b>"
        n_trades    = len(self.active_trades)
        await update.message.reply_text(
            f"📊 <b>BOT STATUS</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>Status:</b>  {status_text}\n"
            f"<b>Balance:</b> ${balance:.4f} USDT\n"
            f"<b>Mode:</b>    {config.MODE.upper()}\n"
            f"<b>Trades:</b>  {n_trades} open\n"
            f"━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )

    async def open_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.active_trades:
            await update.message.reply_text(
                "📭 <b>No Open Trades</b> at the moment.", parse_mode="HTML"
            )
            return
        msg = "📈 <b>ACTIVE TRADES</b>\n━━━━━━━━━━━━━━━\n"
        for symbol, data in self.active_trades.items():
            price = self.bybit.get_ticker(symbol) or data["entry"]
            pnl   = (price - data["entry"]) / data["entry"] * 100
            icon  = "🟢" if pnl >= 0 else "🔴"
            msg  += (
                f"{icon} <b>{symbol}</b>\n"
                f"Entry: ${data['entry']:.4f} | Now: ${price:.4f}\n"
                f"SL: ${data['sl']:.4f} | TP: ${data['tp']:.4f}\n"
                f"P&L: <b>{pnl:+.2f}%</b>\n"
                f"━━━━━━━━━━━━━━━\n"
            )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def profit_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fix #5: reads from logs/trades.csv (correct path)."""
        log_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "logs", "trades.csv"
        )
        if not os.path.exists(log_file):
            await update.message.reply_text(
                "📅 <b>No trade history yet.</b>", parse_mode="HTML"
            )
            return
        try:
            trades, wins, total_pnl = [], 0, 0.0
            with open(log_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append(row)
                    pnl = float(row.get("P&L", 0) or 0)
                    total_pnl += pnl
                    if pnl > 0:
                        wins += 1

            closed = [t for t in trades if t.get("Status") == "CLOSED"]
            wr     = round(wins / len(closed) * 100) if closed else 0
            sign   = "+" if total_pnl >= 0 else ""

            await update.message.reply_text(
                f"📅 <b>PROFIT REPORT</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"<b>Total Trades:</b>  {len(trades)}\n"
                f"<b>Closed:</b>        {len(closed)}\n"
                f"<b>Win Rate:</b>      {wr}%\n"
                f"<b>Total P&L:</b>     {sign}${total_pnl:.4f} USDT\n"
                f"━━━━━━━━━━━━━━━",
                parse_mode="HTML",
            )
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ Error reading trade log: {e}", parse_mode="HTML"
            )

    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.paused = True
        self._save_pause_state()   # Fix #8
        await update.message.reply_text(
            "🛑 <b>Bot Paused.</b> No new trades until you resume.",
            parse_mode="HTML",
        )

    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.paused = False
        self._save_pause_state()   # Fix #8
        await update.message.reply_text(
            "🚀 <b>Bot Resumed.</b> Scanning for signals now...",
            parse_mode="HTML",
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❓ <b>Commands</b>\n\n"
            "📊 Status       — bot health + balance\n"
            "💰 Balance       — USDT balance\n"
            "📈 Open Trades   — live trade monitor\n"
            "📅 Profit Report — trade history\n"
            "🔍 Scan Setups   — manual market scan\n"
            "🛑 Pause Bot     — stop new entries\n"
            "🚀 Resume Bot    — resume scanning\n",
            parse_mode="HTML",
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text in ("📊 Status", "💰 Balance"):
            await self.status(update, context)
        elif text == "📈 Open Trades":
            await self.open_trades(update, context)
        elif text == "📅 Profit Report":
            await self.profit_report(update, context)
        elif text == "🛑 Pause Bot":
            await self.pause(update, context)
        elif text == "🚀 Resume Bot":
            await self.resume(update, context)
        elif text == "🔍 Scan Setups":
            self.scan_requested = True
            await update.message.reply_text(
                f"🔍 <b>Manual Scan started.</b> Checking {len(config.WHITELIST_PAIRS)} pairs...",
                parse_mode="HTML",
            )
        elif text == "❓ Help":
            await self.help_cmd(update, context)

    async def run_listener(self):
        """Start Telegram polling with auto-retry."""
        while True:
            try:
                app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()
                app.add_handler(CommandHandler("start",  self.start))
                app.add_handler(CommandHandler("status", self.status))
                app.add_handler(CommandHandler("pause",  self.pause))
                app.add_handler(CommandHandler("resume", self.resume))
                app.add_handler(CommandHandler("help",   self.help_cmd))
                app.add_handler(
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_message
                    )
                )
                print("[Telegram] Listener started")
                await app.initialize()
                await app.start()
                await app.updater.start_polling()
                while True:
                    await asyncio.sleep(3600)
            except Exception as e:
                print(f"[Telegram] Listener error: {e} — retrying in 30s")
                await asyncio.sleep(30)
