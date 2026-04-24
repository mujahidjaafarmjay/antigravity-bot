# ============================================================
#  main.py — Render-ready. All 13 fixes applied.
#
#  Fix #4:  await notifier.notify_trade_entry() (async)
#  Fix #6:  fake backtest removed, honest message shown
#  Fix #7:  daily loss limit enforced every loop
#  Fix #9:  single BybitClient passed to all components
#  Fix #10: brain receives raw candles, sorts internally
#  Fix #11: zero-balance check with Telegram alert
#  Fix #12: Flask use_reloader=False + threaded=False
#  Fix #13: rate limit sleep between pairs
# ============================================================

import time
import asyncio
import os
import threading
from flask import Flask, jsonify
import config

from exchange.bybit_client         import BybitClient
from strategy.brain                import TradingBrain
from risk.manager                  import RiskManager
from notifications.notifier        import TelegramNotifier
from safety.sharia_filter          import ShariaFilter
from logger.trade_logger           import TradeLogger
from storage.google_sheets         import GoogleSheetsStorage

# ── Health server (Fix #12: use_reloader=False, threaded=False) ──
health_app  = Flask(__name__)
_start_time = time.time()
_bot_status = {"active_trades": 0, "mode": config.MODE, "status": "starting"}


@health_app.route("/")
@health_app.route("/ping")
def ping():
    return "OK", 200


@health_app.route("/status")
def status_endpoint():
    return jsonify({
        "bot":           "Antigravity SMC",
        "mode":          _bot_status["mode"],
        "status":        _bot_status["status"],
        "active_trades": _bot_status["active_trades"],
        "pairs":         len(config.WHITELIST_PAIRS),
        "uptime_sec":    int(time.time() - _start_time),
    })


def _run_health_server():
    port = int(os.environ.get("PORT", 8080))
    # Fix #12: threaded=False avoids event-loop conflicts with asyncio
    health_app.run(
        host="0.0.0.0", port=port,
        debug=False, use_reloader=False, threaded=False
    )


threading.Thread(target=_run_health_server, daemon=True).start()
print(f"[Health] Server on port {os.environ.get('PORT', 8080)}")


# ── Main async bot ────────────────────────────────────────────
async def main():
    print("=" * 54)
    print("  ANTIGRAVITY SMC BOT — v3 (all fixes applied)")
    print("=" * 54)

    # ── Single shared BybitClient (Fix #9) ──────────────────
    bybit    = BybitClient()
    brain    = TradingBrain()
    risk     = RiskManager()
    notifier = TelegramNotifier()
    sharia   = ShariaFilter()
    logger   = TradeLogger()
    storage  = GoogleSheetsStorage()

    # ── Telegram handler — receives bybit + storage (Fix #9, #8) ─
    from notifications.command_handler import TelegramCommandHandler
    cmd_handler = TelegramCommandHandler(
        notifier=notifier,
        bybit=bybit,       # Fix #9: injected, not created inside handler
        storage=storage,   # Fix #8: for persistent pause state
    )
    asyncio.create_task(cmd_handler.run_listener())

    # ── Crash recovery ────────────────────────────────────────
    active_trades = {}
    recovered = storage.get_open_trades()
    if recovered:
        for t in recovered:
            active_trades[t["symbol"]] = t
        lines = "\n".join(
            f"• {t['symbol']} entry=${t['entry']} SL=${t['sl']} TP=${t['tp']}"
            for t in recovered
        )
        await notifier.send_message(
            f"🔄 <b>Bot Restarted on Render</b>\n"
            f"Mode: {config.MODE.upper()}\n"
            f"Recovered <b>{len(recovered)}</b> trade(s):\n{lines}"
        )
    else:
        await notifier.send_message(
            f"🟢 <b>Bot Started on Render</b>\n"
            f"Mode: <b>{config.MODE.upper()}</b>\n"
            f"Scanning: <b>{len(config.WHITELIST_PAIRS)}</b> pairs\n"
            f"Sheets: <b>{'connected' if storage.is_connected else 'not configured'}</b>"
        )

    cmd_handler.active_trades = active_trades
    _bot_status["mode"]   = config.MODE
    _bot_status["status"] = "running"

    # ── Market scanner ────────────────────────────────────────
    async def scan_markets(is_manual: bool = False):
        balance = bybit.get_balance("USDT")

        # Fix #11: alert and stop if balance is missing/zero
        if balance <= 0:
            await notifier.send_message(
                "⚠️ <b>Balance is $0 or unreadable.</b>\n"
                "Check your Bybit API key and account type in Render env vars.\n"
                "Bot will not trade until balance is confirmed."
            )
            return 0.0

        found = 0
        for symbol in config.WHITELIST_PAIRS:

            # Fix #10: sharia filter actually called before every trade
            if not sharia.is_compliant(symbol):
                continue

            if symbol in active_trades:
                continue

            if len(active_trades) >= config.MAX_OPEN_TRADES:
                break

            # Fix #13: rate limit sleep between each pair's API calls
            await asyncio.sleep(1.5)

            candles_1h    = bybit.get_candles(symbol, config.TIMEFRAME_MAIN)
            candles_4h    = bybit.get_candles(symbol, config.TIMEFRAME_TREND)
            candles_daily = bybit.get_candles(symbol, config.TIMEFRAME_DAILY)

            # Skip if not enough data for MA200
            if len(candles_1h) < 50 or len(candles_4h) < 210:
                continue

            decision, data = brain.analyze(candles_1h, candles_4h, candles_daily)

            if decision == "BUY":
                # Fix #10: brain already sorted — get_stop_loss uses sorted df
                import pandas as pd
                df_1h = pd.DataFrame(
                    candles_1h,
                    columns=["time","open","high","low","close","vol","turnover"]
                )
                for col in ["open","high","low","close","vol"]:
                    df_1h[col] = pd.to_numeric(df_1h[col])
                df_1h = df_1h.sort_values("time").reset_index(drop=True)

                current_price = bybit.get_ticker(symbol)
                if not current_price:
                    continue

                stop_loss = brain.get_stop_loss(df_1h)
                qty       = risk.calculate_position_size(
                    balance, current_price, stop_loss
                )

                # Fix #11: qty == -1 means zero balance
                if qty == -1:
                    await notifier.send_message(
                        "⚠️ <b>Zero balance detected mid-scan.</b> Stopping."
                    )
                    return 0.0

                if qty <= 0:
                    continue

                take_profit = current_price + (
                    (current_price - stop_loss) * config.REWARD_TO_RISK_RATIO
                )
                order = bybit.place_order(symbol, "Buy", qty)

                if order.get("retCode", -1) == 0:
                    trade = {
                        "symbol": symbol,
                        "qty":    qty,
                        "entry":  current_price,
                        "sl":     stop_loss,
                        "tp":     take_profit,
                    }
                    active_trades[symbol] = trade
                    _bot_status["active_trades"] = len(active_trades)

                    storage.log_trade_open(trade)
                    logger.log_trade(
                        symbol, "BUY", qty, current_price, stop_loss, take_profit
                    )

                    # Fix #4: await the async notifier
                    await notifier.notify_trade_entry(
                        symbol, "BUY", qty, current_price, stop_loss, take_profit
                    )
                    found += 1

            elif decision == "POTENTIAL" and data:
                await notifier.send_message(
                    f"⏳ <b>POTENTIAL SETUP: {symbol}</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"<b>Entry:</b>      ${data['entry']:.4f}\n"
                    f"<b>Stop Loss:</b>  ${data['sl']:.4f}\n"
                    f"<b>Take Profit:</b>${data['tp']:.4f}\n"
                    f"Reason: {data.get('reason','')}\n"
                    f"━━━━━━━━━━━━━━━"
                )
                found += 1

        if is_manual and found == 0:
            await notifier.send_message(
                "🔍 <b>Scan complete.</b> No high-probability setups right now."
            )
        return balance

    # ── Main loop ─────────────────────────────────────────────
    while True:
        try:
            _bot_status["active_trades"] = len(active_trades)

            # Fix #7: check daily loss limit every cycle
            balance = bybit.get_balance("USDT")
            halted, halt_msg = risk.is_daily_limit_hit(balance)
            if halted:
                await notifier.send_message(f"🛑 {halt_msg}")
                await asyncio.sleep(300)
                continue

            # Handle manual scan request
            if cmd_handler.scan_requested:
                cmd_handler.scan_requested = False
                await scan_markets(is_manual=True)

            # Fix #6: honest backtest message — no fake numbers
            if cmd_handler.backtest_requested:
                cmd_handler.backtest_requested = False
                await notifier.send_message(
                    "🧪 <b>Backtest</b>\n\n"
                    "Live backtesting is not yet implemented.\n"
                    "To backtest manually: review your <b>logs/trades.csv</b> "
                    "or Google Sheet trade history.\n\n"
                    "<i>Tip: Run the bot in paper mode for 2–4 weeks "
                    "and review the results before going live.</i>"
                )

            # Monitor open trades
            for symbol, trade in list(active_trades.items()):
                current_price = bybit.get_ticker(symbol)
                if not current_price:
                    continue

                profit_pct = (current_price - trade["entry"]) / trade["entry"] * 100
                pnl_usd    = (current_price - trade["entry"]) * trade["qty"]

                # Stop Loss
                if current_price <= trade["sl"]:
                    bybit.place_order(symbol, "Sell", trade["qty"])
                    storage.log_trade_close(trade, current_price, pnl_usd, profit_pct)
                    logger.update_trade_close(symbol, current_price, pnl_usd)
                    risk.record_pnl(pnl_usd)   # Fix #7: track P&L for daily limit
                    del active_trades[symbol]
                    _bot_status["active_trades"] = len(active_trades)
                    await notifier.send_message(
                        f"🛑 <b>STOP LOSS HIT — {symbol}</b>\n"
                        f"Exit: ${current_price:.4f} | P&L: {profit_pct:.2f}%"
                    )
                    continue

                # Take Profit
                if current_price >= trade["tp"]:
                    bybit.place_order(symbol, "Sell", trade["qty"])
                    storage.log_trade_close(trade, current_price, pnl_usd, profit_pct)
                    logger.update_trade_close(symbol, current_price, pnl_usd)
                    risk.record_pnl(pnl_usd)   # Fix #7
                    del active_trades[symbol]
                    _bot_status["active_trades"] = len(active_trades)
                    await notifier.send_message(
                        f"✅ <b>TAKE PROFIT HIT — {symbol}</b>\n"
                        f"Exit: ${current_price:.4f} | P&L: +{profit_pct:.2f}%"
                    )
                    continue

                # Break-even shield
                if profit_pct >= 1.5 and trade["sl"] < trade["entry"]:
                    active_trades[symbol]["sl"] = trade["entry"]
                    await notifier.send_message(
                        f"🛡️ <b>BREAK-EVEN SHIELD — {symbol}</b>\n"
                        f"Stop moved to entry. Trade is now risk-free."
                    )

            # Regular scan
            if not cmd_handler.paused:
                await scan_markets()
                print(f"[Loop] Scan done. Active trades: {len(active_trades)}. Sleeping 5m...")
                await asyncio.sleep(300)
            else:
                await asyncio.sleep(60)

        except Exception as e:
            err = str(e).encode("ascii", "ignore").decode("ascii")
            print(f"[Loop] Error: {err}")
            await notifier.send_message(f"⚠️ <b>Bot Error:</b> {err}")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
