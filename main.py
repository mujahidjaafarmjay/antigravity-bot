import time
import logging
from datetime import datetime, timedelta
import config
from exchange.bybit_handler import BybitHandler
from logic.brain import Brain
from logic.risk_manager import RiskManager
from storage.sheets_persistence import SheetsPersistence
from notifications.telegram_sender import TelegramSender
from notifications.command_handler import TelegramCommandHandler
import threading
import asyncio
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def health():
    return "Antigravity Bot is running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("AntigravityBot")

class TradingBot:
    def __init__(self):
        self.bybit = BybitHandler()
        self.brain = Brain()
        self.risk = RiskManager()
        self.sheets = SheetsPersistence()
        self.telegram = TelegramSender()
        self.cmd_handler = TelegramCommandHandler(self.telegram, self.bybit, self.sheets, self.risk)
        
        self.cooldowns = {}
        self.daily_pnl = 0.0
        self.is_halted = False
        self.starting_balance = 0.0
        self.reported_signals = {} # Track last score sent to Telegram
        self.execution_lock = {} # Prevent duplicate execution attempts
        self.instance_id = datetime.now().strftime("%H%M%S") # Unique ID for this run
        
        self._recover_state()

    def _recover_state(self):
        """Recovers state from Google Sheets on startup."""
        logger.info("Recovering state from Google Sheets...")
        meta = self.sheets.get_meta()
        self.daily_pnl = meta.get('daily_net_pnl', 0.0)
        self.is_halted = meta.get('is_halted', False)
        
        # Get starting balance
        self.starting_balance = self.bybit.get_balance()
        logger.info(f"State recovered. Daily PnL: ${self.daily_pnl:.2f}, Halted: {self.is_halted}, Balance: ${self.starting_balance:.2f}")

    def run(self):
        """Main bot loop."""
        logger.info("Antigravity Spot Bot Started.")
        
        while True:
            try:
                # 1. Safety Checks
                if self.is_halted:
                    logger.warning("Bot is currently HALTED due to daily loss limit.")
                    time.sleep(3600) # Check every hour if still halted
                    continue

                balance = self.bybit.get_balance()
                if balance <= 0:
                    logger.error("Balance unreadable or 0. Skipping iteration.")
                    time.sleep(config.BALANCE_CACHE_SECONDS)
                    continue

                # Check Daily Loss
                if self.risk.check_daily_loss(self.daily_pnl, self.starting_balance):
                    self.is_halted = True
                    self.sheets.update_meta(self.daily_pnl, self.is_halted)
                    self.telegram.alert_critical("Daily loss limit reached. Trading halted.")
                    continue

                # 2. Iterate through Halal Pairs
                for symbol in config.HALAL_PAIRS:
                    # Check Cooldown
                    if symbol in self.cooldowns:
                        if datetime.now() < self.cooldowns[symbol]:
                            continue
                            
                    # Prevent re-attempting same trade too frequently
                    if symbol in self.execution_lock:
                        if datetime.now() < self.execution_lock[symbol]:
                            continue

                    logger.info(f"Analyzing {symbol}...")
                    df, bid, ask = self.bybit.get_market_data(symbol)
                    
                    if df is None:
                        continue

                    # Evaluate Trade
                    decision = self.brain.evaluate_trade(symbol, df, balance)
                    logger.info(f"Decision for {symbol}: {decision['action']} (Score: {decision['score']}) - {decision['reason']}")

                    # Debug Telegram (Only if score is new or changed to avoid spam)
                    last_score = self.reported_signals.get(symbol, 0)
                    if decision['score'] >= 3 and decision['score'] != last_score:
                        self.telegram.send_message(
                            f"🔍 <b>{symbol} Analysis</b> (ID: {self.instance_id})\n"
                            f"Score: {decision['score']}\n"
                            f"Action: {decision['action']}\n"
                            f"Reason: {decision['reason']}"
                        )
                    
                    # Always update memory to detect the NEXT change
                    self.reported_signals[symbol] = decision['score']

                    if decision['action'] in ["BUY", "STRONG BUY"]:
                        # Validate with Risk Manager
                        open_orders = self.bybit.get_open_orders()
                        valid, reason = self.risk.validate_trade(decision, balance, len(open_orders), bid, ask)
                        
                        if not valid:
                            logger.warning(f"⚠️ Trade Validation Failed for {symbol}: {reason}")
                            self.telegram.send_message(f"⚠️ <b>Trade Blocked: {symbol}</b>\nReason: {reason}")
                            continue

                        if valid:
                            # 1. Global Trade Limit Check
                            open_orders = self.bybit.get_open_orders()
                            if len(open_orders) >= config.MAX_OPEN_TRADES:
                                logger.warning(f"Max trades reached ({config.MAX_OPEN_TRADES}). Skipping {symbol}.")
                                continue

                            # 2. Per-Symbol Check (Secondary Guard)
                            symbol_orders = [o for o in open_orders if o['symbol'] == symbol]
                            if symbol_orders:
                                logger.info(f"Skipping {symbol}: Already has open orders.")
                                continue

                            # 3. Use LIVE Ticker for Execution Price (not candle data)
                            # We use 'ask' for Buying to ensure immediate placement
                            exec_price = ask
                            
                            # 4. Calculate Qty
                            qty, qty_reason = self.risk.calculate_position(balance, exec_price, decision['stop_loss'])
                            if qty > 0:
                                # 5. Lock execution BEFORE attempt to prevent race conditions
                                self.execution_lock[symbol] = datetime.now() + timedelta(minutes=15)
                                
                                logger.info(f"🚀 ATTEMPTING HARDENED MARKET TRADE: {symbol} | Qty: {qty} | Estimated Price: {exec_price}")
                                
                                if (qty * exec_price) < 5.0:
                                    logger.warning(f"Trade too small for Bybit: {qty * exec_price:.2f} USDT")
                                    self.telegram.send_message(f"👀 <b>WATCH: {symbol}</b>\nSignal is VALID, but position size is below Bybit's $5 minimum.\nTracking for performance analysis.")
                                    continue

                                result = self.bybit.place_market_order(
                                    symbol=symbol,
                                    qty=qty,
                                    sl=decision['stop_loss'],
                                    tp=decision['take_profit']
                                )
                                
                                if result["success"]:
                                    # ✅ SUCCESS
                                    order_id = result['order_id']
                                    logger.info(f"✅ SUCCESS: Trade executed for {symbol} | ID: {order_id}")
                                    self.telegram.send_message(
                                        f"✅ <b>ORDER PLACED: {symbol}</b>\n"
                                        f"Qty: {result['qty']}\n"
                                        f"Price: {result['price']}\n"
                                        f"ID: {order_id}"
                                    )
                                    
                                    # Log to Sheets
                                    trade_log = decision.copy()
                                    trade_log['qty'] = result['qty']
                                    trade_log['entry'] = result['price']
                                    self.sheets.log_trade(trade_log)
                                    
                                    # Set final cooldown
                                    self.cooldowns[symbol] = datetime.now() + timedelta(minutes=config.COOLDOWN_MINUTES)
                                else:
                                    # ❌ FAILURE
                                    err_msg = result["error"]
                                    logger.error(f"❌ ORDER FAILED: {symbol} | {err_msg}")
                                    self.telegram.send_message(
                                        f"❌ <b>ORDER FAILED: {symbol}</b>\n"
                                        f"Reason: {err_msg}"
                                    )
                            else:
                                if qty_reason == "SMALL_TRADE_WATCH":
                                    logger.info(f"👀 WATCH: {symbol} signal is valid but position size is too small for Bybit ($5).")
                                    self.telegram.send_message(f"👀 <b>WATCH: {symbol}</b>\nSignal is VALID, but position size is below Bybit's $5 minimum.\nTracking for performance analysis.")
                                else:
                                    logger.warning(f"❌ Trade skipped for {symbol}: {qty_reason}")
                                    self.telegram.send_message(f"❌ <b>Qty Error: {symbol}</b>\n{qty_reason}")
                        else:
                            # This block is now handled above, but keeping for structure
                            pass

                    time.sleep(config.API_DELAY) # Avoid rate limits

                # Update Meta periodically
                self.sheets.update_meta(self.daily_pnl, self.is_halted)
                
                # Sleep before next scan (Check for manual scan request every second)
                logger.info("Scan complete. Sleeping...")
                for _ in range(60):
                    if getattr(self.cmd_handler, 'scan_requested', False):
                        logger.info("Manual scan requested via Telegram!")
                        self.cmd_handler.scan_requested = False
                        break
                    time.sleep(1)

            except Exception as e:
                err_msg = f"Unexpected error in main loop: {e}"
                logger.error(err_msg)
                self.telegram.send_message(f"🚨 <b>BOT ERROR</b>\n{err_msg}")
                time.sleep(30)

if __name__ == "__main__":
    # Start Flask heartbeat in background
    threading.Thread(target=run_flask, daemon=True).start()
    
    bot = TradingBot()
    
    # Start Telegram Listener in background
    def start_telegram():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.cmd_handler.run_listener())
        
    threading.Thread(target=start_telegram, daemon=True).start()
    
    bot.run()
