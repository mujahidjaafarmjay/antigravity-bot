# ============================================================
#  notifications/notifier.py
#  Fix #4: notify_trade_entry now awaitable (async)
#          All notifications use proper async pattern
# ============================================================
import asyncio
from telegram import Bot
import config


class TelegramNotifier:
    def __init__(self):
        self.bot     = Bot(token=config.TELEGRAM_TOKEN) if config.TELEGRAM_TOKEN else None
        self.chat_id = config.CHAT_ID

    async def send_message(self, text: str) -> bool:
        """Send HTML message to Telegram. Always awaitable."""
        if not self.bot:
            print(f"[Telegram] (no token) {text[:80]}")
            return False
        try:
            await asyncio.wait_for(
                self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode="HTML",
                ),
                timeout=10,
            )
            return True
        except asyncio.TimeoutError:
            print("[Telegram] send timed out")
            return False
        except Exception as e:
            print(f"[Telegram] send error: {e}")
            return False

    # Fix #4: was sync calling ensure_future — now properly async
    async def notify_trade_entry(
        self, symbol: str, side: str, qty: float,
        price: float, sl: float, tp: float
    ):
        msg = (
            f"🚀 <b>TRADE ENTRY</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>Pair:</b>       {symbol}\n"
            f"<b>Side:</b>       {side}\n"
            f"<b>Qty:</b>        {qty}\n"
            f"<b>Entry:</b>      ${price:.4f}\n"
            f"<b>Stop Loss:</b>  ${sl:.4f}\n"
            f"<b>Take Profit:</b>${tp:.4f}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Mode: {config.MODE.upper()}"
        )
        await self.send_message(msg)

    async def notify_error(self, error_msg: str):
        await self.send_message(f"⚠️ <b>BOT ERROR</b>\n{error_msg}")
