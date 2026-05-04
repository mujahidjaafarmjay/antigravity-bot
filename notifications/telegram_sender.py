import requests
import config
import logging

class TelegramSender:
    """Sends alerts and notifications to Telegram."""
    
    def __init__(self):
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.CHAT_ID
        self.logger = logging.getLogger(__name__)

    def send_message(self, message):
        """Sends a simple text message with robust retry logic."""
        if not self.token or not self.chat_id:
            self.logger.warning("Telegram token or chat_id missing.")
            return

        for attempt in range(3):
            try:
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    import time
                    time.sleep(2 * (attempt + 1))
            except Exception as e:
                self.logger.error(f"Error sending Telegram message (Attempt {attempt+1}): {e}")
        return None

    def alert_trade(self, trade_data):
        """Sends a formatted trade alert."""
        msg = (
            f"🚀 <b>NEW TRADE: {trade_data['symbol']}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Action: <b>{trade_data['action']}</b> (Score: {trade_data['score']})\n"
            f"Entry: {trade_data['entry']:.4f}\n"
            f"SL: {trade_data['stop_loss']:.4f}\n"
            f"TP: {trade_data['take_profit']:.4f}\n"
            f"Qty: {trade_data['qty']:.6f}\n"
            f"Reason: <i>{trade_data['reason']}</i>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✅ Sharia_Status = Verified"
        )
        self.send_message(msg)

    def alert_critical(self, message):
        """Sends a critical alert."""
        self.send_message(f"⚠️ <b>CRITICAL:</b> {message}")
