# ============================================================
#  notifications/command_handler.py
#  Fix Bug 6: self.storage assigned BEFORE _load_pause_state()
#  Fix Bug 7: resume() calls risk.reset_daily_halt()
# ============================================================
import asyncio
import os
import csv
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    ContextTypes, MessageHandler, filters
)
import config


class TelegramCommandHandler:
    def __init__(self, notifier, bybit, storage, risk):
        """
        Fix Bug 6: self.storage assigned FIRST before _load_pause_state().
        Fix Bug 7: risk manager injected so resume can reset daily halt.
        """
        # CRITICAL ORDER: storage must be set before calling _load_pause_state()
        self.storage   = storage         # Fix Bug 6: FIRST
        self.notifier  = notifier
        self.bybit     = bybit
        self.risk      = risk            # Fix Bug 7
        self.paused    = self._load_pause_state()  # safe now — storage exists

        self.scan_requested     = False
        self.backtest_requested = False
        self.active_trades      = {}

        self.keyboard = [
            ["📊 Status",     "💰 Balance"],
            ["📈 Open Trades", "📅 Profit Report"],
            ["🔍 Scan Setups", "🛑 Pause Bot"],
            ["🚀 Resume Bot",  "❓ Help"],
        ]
        self.reply_markup = ReplyKeyboardMarkup(
            self.keyboard, resize_keyboard=True
        )

    # ── Pause state ───────────────────────────────────────────

    def _load_pause_state(self) -> bool:
        try:
            if self.storage and self.storage.is_connected:
                return self.storage.get_bot_meta("paused") == "true"
        except Exception:
            pass
        return False

    def _save_pause_state(self):
        try:
            if self.storage and self.storage.is_connected:
                self.storage.set_bot_meta(
                    "paused", "true" if self.paused else "false"
                )
        except Exception:
            pass

    # ── Handlers ─────────────────────────────────────────────

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 <b>Antigravity Bot Command Center</b>\n"
            "Use the buttons below to control your bot.",
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        balance = self.bybit.get_balance()
        status_text = "🟢 <b>ACTIVE</b>" if not self.paused else "🟡 <b>PAUSED</b>"
        bal_text    = f"${balance:.4f}" if balance > 0 else "⚠️ Unreadable — check API key"
        await update.message.reply_text(
            f"📊 <b>BOT STATUS</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>Status:</b>  {status_text}\n"
            f"<b>Balance:</b> {bal_text} USDT\n"
            f"<b>Mode:</b>    {config.MODE.upper()}\n"
            f"<b>Trades:</b>  {len(self.active_trades)} open\n"
            f"<b>Limit:</b>   {config.DAILY_LOSS_LIMIT_PERCENT}% daily\n"
            f"━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )

    async def open_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        orders = self.bybit.get_open_orders()
        if not orders:
            await update.message.reply_text(
                "📭 <b>No Open Trades</b> at the moment.", parse_mode="HTML"
            )
            return
        msg = "📈 <b>ACTIVE ORDERS</b>\n━━━━━━━━━━━━━━━\n"
        for order in orders:
            symbol = order['symbol']
            price = order.get('price', 'Market')
            qty = order.get('qty', '0')
            side = order.get('side', 'Buy')
            msg += (
                f"<b>{symbol}</b> ({side})\n"
                f"Qty: {qty} | Price: ${price}\n"
                f"━━━━━━━━━━━━━━━\n"
            )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def profit_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📅 <b>PROFIT REPORT</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "All trade history is now synced live to <b>Google Sheets</b> for production persistence.\n\n"
            f"🔗 <b>Sheet Name:</b> {config.GOOGLE_SHEET_NAME}\n"
            "Check your spreadsheet for the full P&amp;L audit trail.",
            parse_mode="HTML",
        )

    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.paused = True
        self._save_pause_state()
        await update.message.reply_text(
            "🛑 <b>Bot Paused.</b> No new trades until you resume.",
            parse_mode="HTML",
        )

    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Fix Bug 7: also resets daily halt so bot can trade again.
        """
        self.paused = False
        self._save_pause_state()
        # Fix Bug 7: clear the daily halt flag
        if self.risk:
            self.risk.reset_daily_halt()
        await update.message.reply_text(
            "🚀 <b>Bot Resumed.</b>\n"
            "Daily halt cleared. Scanning for signals now...",
            parse_mode="HTML",
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❓ <b>Commands</b>\n\n"
            "📊 Status       — bot health + balance\n"
            "💰 Balance       — USDT balance\n"
            "📈 Open Trades   — live positions\n"
            "📅 Profit Report — trade history\n"
            "🔍 Scan Setups   — manual scan now\n"
            "🛑 Pause Bot     — stop new entries\n"
            "🚀 Resume Bot    — resume + reset halt\n"
            "❓ Help          — this message",
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
                f"🔍 <b>Manual Scan started.</b> "
                f"Checking {len(config.HALAL_PAIRS)} pairs...",
                parse_mode="HTML",
            )
        elif text == "❓ Help":
            await self.help_cmd(update, context)

    async def run_listener(self):
        """Telegram polling with clean shutdown on retry."""
        app = None
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
                print(f"[Telegram] Listener Instance {os.getpid()} starting...")
                await app.initialize()
                # Fix Bug: drop_pending_updates=True to avoid Conflict Error
                await app.bot.delete_webhook(drop_pending_updates=True)
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True, stop_signals=None)
                while True:
                    await asyncio.sleep(3600)
            except Exception as e:
                print(f"[Telegram] Error: {e} — retrying in 30s")
                # Fix: clean shutdown before rebuilding app
                try:
                    if app:
                        await app.updater.stop()
                        await app.stop()
                        await app.shutdown()
                except Exception:
                    pass
                app = None
                await asyncio.sleep(30)
