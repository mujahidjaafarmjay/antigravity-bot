import time
import logging
import pytz
from datetime import datetime, timedelta
import config
from exchange.bybit_handler import BybitHandler
from logic.brain import Brain
from logic.risk_manager import RiskManager
from logic.optimizer import StrategyOptimizer
from logic.pair_ranker import PairRanker
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
        self.optimizer = StrategyOptimizer(min_trades_required=10) # Tier 5: Faster adaptation
        self.ranker = PairRanker(min_trades_required=5)
        self.sheets = SheetsPersistence()
        self.telegram = TelegramSender()
        self.cmd_handler = TelegramCommandHandler(self.telegram, self.bybit, self.sheets, self.risk)
        
        self.utc = pytz.UTC
        self.cooldowns = {}
        self.daily_pnl = 0.0
        self.is_halted = False
        self.starting_balance = 0.0
        self.last_recovery_state = False # For Telegram alerts
        self.reported_signals = {} # Track last score sent to Telegram
        self.execution_lock = {} # Prevent duplicate execution attempts
        self.daily_trade_count = 0 # Tier 7 Frequency Control
        self.active_trades = {} # Track open trades for P&L logging
        self.closed_trades_count = 0 # Counter to avoid aggressive optimization
        self.instance_id = datetime.now().strftime("%H%M%S") # Unique ID for this run
        
    def _recover_state(self):
        """Recovers state and reconciles Sheets with Exchange reality."""
        logger.info("Recovering state from Google Sheets...")
        meta = self.sheets.get_meta()
        self.risk.peak_balance = meta.get('peak_balance', 0.0)
        self.ranker.banned_until = self.sheets.recover_bans()

        # Daily PnL Reset Logic
        last_run_str = meta.get('last_trade_day', "")
        today_str = datetime.now().strftime("%Y-%m-%d")

        if last_run_str != today_str:
            logger.info(f"New day detected ({today_str}). Resetting daily PnL and trade count.")
            self.daily_pnl = 0.0
            self.daily_trade_count = 0
            self.is_halted = False
            self.starting_balance = self.bybit.get_balance() # Refresh baseline
            self.sheets.update_meta(0.0, False, self.risk.peak_balance, 0, today_str)
        else:
            self.daily_pnl = meta.get('daily_net_pnl', 0.0)
            self.daily_trade_count = meta.get('daily_trade_count', 0)
            self.is_halted = meta.get('is_halted', False)

        # 1. Fetch truth from exchange
        open_orders = self.bybit.get_open_orders()
        exchange_symbols = [o['symbol'] for o in open_orders]

        # 2. Recover from Sheets
        sheets_trades = self.sheets.get_active_trades()
        reconciled = {}

        for symbol, trade in sheets_trades.items():
            # In LIVE mode, Sheets MUST match Exchange
            if config.TRADING_MODE == "live":
                if symbol in exchange_symbols:
                    reconciled[symbol] = trade
                else:
                    logger.warning(f"Purging ghost trade from Sheets: {symbol} (Not open on Bybit)")
                    self.sheets.remove_active_trade(symbol)
            else:
                # In PAPER mode, we trust Sheets
                reconciled[symbol] = trade

        self.active_trades = reconciled

        # Run Initial Optimization
        self._run_optimization()

        # Get starting balance
        self.starting_balance = self.bybit.get_balance()
        logger.info(f"State recovered. Daily PnL: ${self.daily_pnl:.2f}, Halted: {self.is_halted}, Balance: ${self.starting_balance:.2f}, Active Trades: {len(self.active_trades)}")

    def _run_optimization(self):
        """Fetches data and runs strategy optimizer and pair ranker (Respects CALIBRATION_MODE)."""
        # 1. Fetch data
        all_perf = self.sheets.get_all_performance_data()

        # 2. Tier 6: Rolling Window Performance (Last 30 trades for adaptation)
        rolling_perf = all_perf[-30:] if len(all_perf) > 30 else all_perf
        summary = self.sheets.get_performance_summary(rolling_perf)

        # 3. Tier 8 Dashboard & Specialized Analytics
        self.sheets.update_analytics_tabs(summary)
        self.sheets.persist_bans(self.ranker.banned_until)

        if config.CALIBRATION_MODE:
            logger.info("Bot in CALIBRATION MODE. Tier 2 Engine (Optimizer/Ranker) suspended.")
            self.brain.set_disabled_scores(set())
            # We still run ranker update to track data, but don't apply filters
            self.ranker.update_rankings(all_perf)
            return

        logger.info("Running Tier 2 Strategy Optimization...")

        # Dashboard Update
        current_bal = self.bybit.get_balance()
        drawdown = (self.risk.peak_balance - current_bal) / self.risk.peak_balance if self.risk.peak_balance > 0 else 0
        self.sheets.update_dashboard(summary, drawdown, self.risk.in_recovery_mode, current_bal, self.risk.peak_balance)

        # 1. Score-Level Optimization
        disabled = self.optimizer.analyze_and_optimize(summary)

        if disabled:
            logger.warning(f"Strategy Optimizer has DISABLED scores: {disabled}")
            self.telegram.send_message(f"🔄 <b>Strategy Optimized</b>\nDisabled Scores: {list(disabled)}")

        # Pass disabled scores to brain
        self.brain.set_disabled_scores(disabled)

        # 2. Symbol-Level Ranking
        self.ranker.update_rankings(all_perf)

    def _monitor_active_trades(self):
        """Checks if active trades hit TP or SL."""
        if not self.active_trades:
            return

        logger.info(f"Monitoring {len(self.active_trades)} active trades...")
        for symbol, trade in list(self.active_trades.items()):
            try:
                current_price = self.bybit.get_ticker(symbol)
                if not current_price:
                    continue

                outcome = None
                exit_price = current_price

                if current_price >= trade['take_profit']:
                    outcome = "WIN"
                    exit_price = trade['take_profit']
                elif current_price <= trade['stop_loss']:
                    outcome = "LOSS"
                    exit_price = trade['stop_loss']
                else:
                    # Tier 8: Dead Trade Detection (Adaptive time-based exit)
                    if 'timestamp' in trade:
                        try:
                            start_time = datetime.strptime(trade['timestamp'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=self.utc)
                            duration_mins = int((datetime.now(self.utc) - start_time).total_seconds() / 60)

                            # Adaptive Timeout: Shorter in low volatility (3h), longer in high volatility (6h)
                            atr_perc = trade.get('atr_perc', 1.0)
                            timeout_mins = 360 if atr_perc > 2.0 else 180 # 6h if volatile, 3h if stagnant

                            if duration_mins >= timeout_mins:
                                # Tier 8: Don't kill slow winners
                                gross_pnl = (current_price - trade['entry']) * trade['qty']
                                if gross_pnl > 0:
                                    logger.info(f"⌛ Slow Winner: {symbol} in profit, extending timeout.")
                                else:
                                    outcome = "TIME_EXIT"
                                    logger.info(f"⌛ DEAD TRADE DETECTION: Closing {symbol} after {timeout_mins} mins.")
                        except: pass

                if outcome:
                    # Calculate PnL (Simplified Spot calculation)
                    # PnL = (Exit - Entry) * Qty
                    gross_pnl = (exit_price - trade['entry']) * trade['qty']

                    # Estimate Fees (Bybit Spot: 0.1% for both entry and exit)
                    entry_fee = (trade['entry'] * trade['qty']) * 0.001
                    exit_fee = (exit_price * trade['qty']) * 0.001
                    total_fees = entry_fee + exit_fee
                    net_pnl = gross_pnl - total_fees

                    # Update Daily PnL
                    self.daily_pnl += net_pnl
                    trade['exit_price'] = exit_price # Tier 8 Dashboard refinement
                    self.sheets.update_meta(self.daily_pnl, self.is_halted, self.risk.peak_balance) # Persist immediately

                    # Track Loss Streak for Kill Switch
                    self.risk.update_loss_streak(outcome)

                    # Tier 8: Context-aware Kill Switch check
                    all_perf = self.sheets.get_all_performance_data()
                    rolling_perf = all_perf[-30:] if len(all_perf) > 30 else all_perf
                    perf_summary = self.sheets.get_performance_summary(rolling_perf)

                    if self.risk.is_kill_switch_active(perf_summary, self.daily_pnl):
                        logger.critical(f"🚨 SMART KILL SWITCH TRIGGERED: {self.risk.consecutive_losses} consecutive losses. Bot halting.")
                        self.is_halted = True
                        self.telegram.alert_critical(f"Bot halted by Smart Kill Switch ({self.risk.consecutive_losses} consecutive losses).")

                    # Log to Sheets with High-Fidelity Data
                    slippage = abs(trade['entry'] - trade.get('expected_entry', trade['entry']))
                    self.sheets.log_outcome(trade, outcome, net_pnl, total_fees, slippage=slippage)

                    # Notify Telegram
                    emoji = "💰" if outcome == "WIN" else "📉"
                    self.telegram.send_message(
                        f"{emoji} <b>TRADE CLOSED: {symbol}</b>\n"
                        f"Outcome: {outcome}\n"
                        f"Net PnL: ${net_pnl:.2f}\n"
                        f"Score: {trade['score']}"
                    )

                    # Remove from local memory
                    del self.active_trades[symbol]

                    # Set mandatory cooldown (Timezone Aware)
                    self.cooldowns[symbol] = datetime.now(self.utc) + timedelta(minutes=config.COOLDOWN_MINUTES)

                    # Trigger Optimization periodically (every 10 trades)
                    self.closed_trades_count += 1
                    if self.closed_trades_count >= 10:
                        self._run_optimization()
                        self.closed_trades_count = 0

            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")

    def run(self):
        """Main bot loop."""
        logger.info("Antigravity Spot Bot Started.")
        
        while True:
            try:
                # 1. Safety Checks
                if self.is_halted:
                    # Check if Kill Switch can auto-recover
                    if not self.risk.is_kill_switch_active(perf_summary, self.daily_pnl):
                        logger.info("Bot auto-recovering from Smart Kill Switch...")
                        self.is_halted = False
                    else:
                        logger.warning("Bot is currently HALTED (Daily Loss or Kill Switch).")
                        time.sleep(3600) # Check every hour
                        continue

                # 1.5 Fetch Performance Snapshot (Tier 6 Rolling Window)
                all_perf = self.sheets.get_all_performance_data()
                rolling_perf = all_perf[-30:] if len(all_perf) > 30 else all_perf
                perf_summary = self.sheets.get_performance_summary(rolling_perf)

                # Tier 4 Market Toxicity Check
                if self.risk.is_market_toxic(perf_summary):
                    logger.critical("🚨 MARKET TOXIC: Total expectancy deeply negative. Pausing bot.")
                    self.telegram.alert_critical("Bot paused: Market conditions are toxic (Negative Expectancy).")
                    time.sleep(3600 * 4) # Pause for 4 hours
                    continue

                balance = self.bybit.get_balance()

                # Check Real Edge for Recovery Exit
                g = perf_summary.get("GLOBAL", {})
                real_edge_val = g.get('real_edge', 0)

                self.risk.update_peak_balance(balance)
                # Hard Tier 8 Guard: Stay in recovery if Real Edge is weak (< 5 bps)
                if self.risk.in_recovery_mode == False and real_edge_val < 0.0005:
                    self.risk.in_recovery_mode = True

                # Recovery Mode Alerts
                if self.risk.in_recovery_mode != self.last_recovery_state:
                    if self.risk.in_recovery_mode:
                        self.telegram.send_message("⚠️ <b>RECOVERY MODE ACTIVATED</b>\nSelectivity increased (Score 5+), Risk halved.")
                    else:
                        self.telegram.send_message("✅ <b>RECOVERY MODE EXITED</b>\nGrowth parameters restored.")
                    self.last_recovery_state = self.risk.in_recovery_mode
                if balance <= 0:
                    logger.error("Balance unreadable or 0. Skipping iteration.")
                    time.sleep(config.BALANCE_CACHE_SECONDS)
                    continue

                # Check Daily Loss (Hard USDT limit or Percentage)
                if self.risk.check_daily_loss(self.daily_pnl, self.starting_balance):
                    self.is_halted = True
                    self.sheets.update_meta(self.daily_pnl, self.is_halted, self.risk.peak_balance, self.daily_trade_count, datetime.now().strftime("%Y-%m-%d"))
                    self.telegram.alert_critical(f"Daily loss limit reached (${self.daily_pnl:.2f}). Trading halted.")
                    continue

                # 2. Monitor Active Trades (TP/SL) - ALWAYS run this
                self._monitor_active_trades()

                # Tier 7: Daily Trade Frequency Control (Adaptive)
                # Recovery Mode: 2 trades/day | Growth Mode: 5 trades/day
                max_daily = 2 if self.risk.in_recovery_mode else self.risk.max_trades_per_day
                if self.daily_trade_count >= max_daily:
                    logger.warning(f"Daily trade limit reached ({max_daily}). Scanning paused.")
                    self.sheets.update_meta(self.daily_pnl, self.is_halted, self.risk.peak_balance, self.daily_trade_count, datetime.now().strftime("%Y-%m-%d"))
                    time.sleep(3600)
                    continue

                # 3. Global Market Trend Filter
                btc_df, _, _ = self.bybit.get_market_data("BTCUSDT")
                market_trend = self.brain.get_market_trend(btc_df)
                self.brain.current_market_trend = market_trend # Pass to brain for soft filter

                if market_trend == "unknown":
                    logger.warning("Market Trend UNKNOWN. Skipping trade scanning.")
                    time.sleep(300)
                    continue

                # 4. Iterate through Halal Pairs (Sorted by Performance for Tier 8 Priority)
                sorted_pairs = sorted(
                    config.HALAL_PAIRS,
                    key=lambda s: self.ranker.symbol_performance.get(s, 0.0),
                    reverse=True
                )
                for symbol in sorted_pairs:
                    # Prevent multiple active trades for same symbol (Duplicate Guard)
                    if symbol in self.active_trades:
                        continue

                    # 1. Strict Timezone-Aware Cooldown Check
                    now = datetime.now(self.utc)
                    if symbol in self.cooldowns:
                        if now < self.cooldowns[symbol]:
                            continue
                        else:
                            del self.cooldowns[symbol]
                            
                    # Prevent re-attempting same trade too frequently
                    if symbol in self.execution_lock:
                        if datetime.now() < self.execution_lock[symbol]:
                            continue

                    logger.info(f"Analyzing {symbol}...")
                    df, bid, ask = self.bybit.get_market_data(symbol)
                    
                    if df is None:
                        continue

                    # Evaluate Trade
                    # Recovery Mode: Increase threshold to Score 5+
                    if getattr(self.risk, 'in_recovery_mode', False) and not config.CALIBRATION_MODE:
                        orig_threshold = self.brain.disabled_scores.copy()
                        # Temporarily disable lower scores (3, 4) in recovery mode
                        self.brain.disabled_scores.update({3, 4})
                        decision = self.brain.evaluate_trade(symbol, df, balance)
                        self.brain.disabled_scores = orig_threshold # Reset
                    else:
                        decision = self.brain.evaluate_trade(symbol, df, balance)

                    # Tier 4 Volatility Guard
                    if self.risk.is_volatility_too_high(df):
                        logger.warning(f"⚠️ Volatility Spike detected for {symbol}. Skipping entry.")
                        continue
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
                        # Tier 4 Equity Protection Check (Uses cached snapshot)
                        if self.risk.is_equity_under_pressure(perf_summary):
                            logger.warning(f"⚠️ Equity Protection: Recent PF < {config.EQUITY_PROTECT_THRESHOLD}. Skipping {symbol}.")
                            self.telegram.send_message(f"⚠️ <b>Equity Guard:</b> Skipping {symbol} due to recent performance pressure.")
                            continue

                        # Validate with Risk Manager
                        open_orders = self.bybit.get_open_orders()
                        valid, reason = self.risk.validate_trade(decision, balance, len(open_orders), bid, ask)
                        
                        if not valid:
                            logger.warning(f"⚠️ Trade Validation Failed for {symbol}: {reason}")
                            # Apply short cooldown for blocked trades to avoid log spam
                            self.cooldowns[symbol] = now + timedelta(minutes=5)
                            self.telegram.send_message(f"⚠️ <b>Trade Blocked: {symbol}</b>\nReason: {reason}")
                            continue

                        if valid:
                            # 1. Global Trade Limit Check (Exchange orders + Local tracking)
                            open_orders = self.bybit.get_open_orders()
                            total_active = len(open_orders) + len([s for s in self.active_trades if s not in [o['symbol'] for o in open_orders]])

                            if total_active >= config.MAX_OPEN_TRADES:
                                logger.warning(f"Max trades reached ({config.MAX_OPEN_TRADES}). Skipping {symbol}.")
                                continue

                            # 2. Per-Symbol Check (Secondary Guard)
                            symbol_orders = [o for o in open_orders if o['symbol'] == symbol]
                            if symbol_orders or symbol in self.active_trades:
                                logger.info(f"Skipping {symbol}: Already has active trades/orders.")
                                continue

                            # 3. Use LIVE Ticker for Execution Price (not candle data)
                            # We use 'ask' for Buying to ensure immediate placement
                            exec_price = ask
                            
                            # 4. Check Pair Ranker hard filter
                            if self.ranker.should_skip_symbol(symbol):
                                logger.warning(f"PairRanker: Skipping {symbol} due to toxic performance history.")
                                continue

                            # 5. Calculate Metrics for Logging
                            rr = abs((decision['take_profit'] - exec_price) / (exec_price - decision['stop_loss']))
                            atr = decision.get('atr', 0) # We might need Brain to return this
                            atr_perc = (atr / exec_price) * 100 if atr else 0

                            # Session Labeling
                            now_hour = datetime.now(pytz.UTC).hour
                            session = "ASIAN"
                            if 8 <= now_hour < 13: session = "LONDON"
                            elif 13 <= now_hour < 17: session = "NY/LONDON"
                            elif 17 <= now_hour < 21: session = "NY"

                            # 6. Calculate Qty with Risk Scaling (Respects CALIBRATION_MODE)
                            symbol_weight = 1.0 if config.CALIBRATION_MODE else self.ranker.get_symbol_weight(symbol)

                            # Use performance data for risk weighting if available
                            spread_val = (ask - bid) / bid if bid > 0 else 0
                            qty, qty_reason = self.risk.calculate_position(
                                balance,
                                exec_price,
                                decision['stop_loss'],
                                score=decision['score'],
                                symbol_weight=symbol_weight,
                                performance_summary=perf_summary,
                                spread=spread_val,
                                session=session
                            )
                            risk_usdt = qty * abs(exec_price - decision['stop_loss'])
                            if qty > 0:
                                # 5. Lock execution BEFORE attempt to prevent race conditions
                                self.execution_lock[symbol] = datetime.now() + timedelta(minutes=15)
                                
                                logger.info(f"🚀 ATTEMPTING HARDENED LIMIT TRADE: {symbol} | Qty: {qty} | Price: {exec_price}")
                                
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
                                    self.daily_trade_count += 1
                                    order_id = result['order_id']
                                    fill_price = result['price']

                                    # Tier 8: Slippage Guard (Bad Fill Detection)
                                    slippage_perc = abs(fill_price - exec_price) / exec_price
                                    slip_status = "GOOD"
                                    if slippage_perc > 0.003: # 0.3%
                                        slip_status = "BAD_FILL"
                                        logger.warning(f"⚠️ BAD FILL: {symbol} slippage {slippage_perc:.2%}")
                                        self.telegram.send_message(f"⚠️ <b>BAD FILL: {symbol}</b>\nSlippage: {slippage_perc:.2%}\nPrice: ${fill_price}")

                                    # Tier 8: "Terrible Fill" Emergency Exit (Hardened)
                                    if slippage_perc > 0.005: # 0.5%
                                        # Only emergency close if market conditions are also toxic (wide spread or spike)
                                        spread_val = (ask - bid) / bid if bid > 0 else 0
                                        if spread_val > 0.003 or self.risk.is_volatility_too_high(df):
                                            logger.critical(f"🚨 TERRIBLE FILL: {symbol} slippage {slippage_perc:.2%}. Emergency closing.")
                                            self.telegram.alert_critical(f"Emergency Exit: {symbol} filled with {slippage_perc:.2%} slippage in toxic conditions.")
                                            # Emergency close with market order
                                            self.bybit.emergency_market_sell(symbol, result['qty'])
                                            self.cooldowns[symbol] = now + timedelta(minutes=60)
                                            continue

                                    logger.info(f"✅ SUCCESS: Trade executed for {symbol} | ID: {order_id} | Slip: {slip_status}")
                                    self.telegram.send_message(
                                        f"✅ <b>ORDER PLACED: {symbol}</b>\n"
                                        f"Qty: {result['qty']}\n"
                                        f"Price: {fill_price}\n"
                                        f"Slip: {slip_status} ({slippage_perc:.2%})"
                                    )
                                    
                                    # Active Trade Tracking with Tier 4 metadata
                                    # Tier 8: Track expected price for slippage calculation
                                    new_trade = {
                                        "symbol": symbol,
                                        "score": decision['score'],
                                        "rr": rr,
                                        "risk_usdt": risk_usdt,
                                        "entry": result['price'],
                                        "expected_entry": exec_price,
                                        "stop_loss": decision['stop_loss'],
                                        "take_profit": decision['take_profit'],
                                        "qty": result['qty'],
                                        "session": session,
                                        "atr_perc": atr_perc,
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    }
                                    self.active_trades[symbol] = new_trade
                                    self.sheets.add_active_trade(new_trade)

                                    # Log to Sheets (Signal Log)
                                    trade_log = decision.copy()
                                    trade_log['qty'] = result['qty']
                                    trade_log['entry'] = result['price']
                                    self.sheets.log_trade(trade_log)
                                    
                                    # Set final cooldown (Timezone Aware)
                                    self.cooldowns[symbol] = datetime.now(self.utc) + timedelta(minutes=config.COOLDOWN_MINUTES)
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
                self.sheets.update_meta(self.daily_pnl, self.is_halted, self.risk.peak_balance)
                
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
    
    # 1. Component Initialization (Fast)
    bot = TradingBot()
    
    # 2. Start Telegram Listener IMMEDIATELY
    # It will respond to /ping even if recovery is slow
    def start_telegram():
        logger.info(f"Telegram Thread starting with PID {os.getpid()}...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.cmd_handler.run_listener())
        
    threading.Thread(target=start_telegram, daemon=True).start()
    
    # 3. Perform Heavy State Recovery
    logger.info("Starting institutional state recovery...")
    bot._recover_state()

    # 4. Final Milestone: Enter Main Loop
    logger.info("Bot components initialized and state recovered. Entering Main Engine Loop.")
    bot.run()
