# ============================================================
#  main.py — Render-ready. corrections_v3 applied.
#
#  v3 fixes:
#  - Sheets auth: oauth2client → gspread.service_account_from_dict
#  - requirements.txt: oauth2client → google-auth>=2.0.0
#  - Balance: enhanced per-account-type debug logging in Render
#  - TelegramCommandHandler import moved to module top (SKILL.md rule)
#  - Version banner updated to v3
# ============================================================
import time
import asyncio
import os
import threading
from flask import Flask, jsonify
import config
import pandas as pd

from exchange.bybit_client       import BybitClient
from strategy.brain              import TradingBrain
from risk.manager                import RiskManager
from notifications.notifier      import TelegramNotifier
from safety.sharia_filter        import ShariaFilter
from logger.trade_logger         import TradeLogger
from storage.google_sheets       import GoogleSheetsStorage
from notifications.command_handler import TelegramCommandHandler

# ── Health server ─────────────────────────────────────────────
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
        "sheets":        _bot_status.get("sheets", "unknown"),
    })


def _run_health_server():
    port = int(os.environ.get("PORT", 8080))
    health_app.run(
        host="0.0.0.0", port=port,
        debug=False, use_reloader=False, threaded=False,
    )


threading.Thread(target=_run_health_server, daemon=True).start()
print(f"[Health] Server on port {os.environ.get('PORT', 8080)}")


# ── Main async bot ────────────────────────────────────────────
async def main():
    print("=" * 54)
    print("  ANTIGRAVITY SMC BOT — Render + corrections_v3")
    print("=" * 54)

    bybit    = BybitClient()
    brain    = TradingBrain()
    risk     = RiskManager()
    notifier = TelegramNotifier()
    sharia   = ShariaFilter()
    logger   = TradeLogger()
    storage  = GoogleSheetsStorage()

    _bot_status["sheets"] = "connected" if storage.is_connected else "not configured"

    # ── Telegram command handler ──────────────────────────────
    cmd_handler = TelegramCommandHandler(
        notifier=notifier,
        bybit=bybit,
        storage=storage,
        risk=risk,
    )
    asyncio.create_task(cmd_handler.run_listener())

    # ── Crash recovery: Steps A–D from corrections_v2 ─────────
    active_trades = {}
    sheet_trades  = storage.get_open_trades()

    if sheet_trades:
        print(f"[Recovery] Found {len(sheet_trades)} trade(s) in Sheets...")

        # Step B: get actual Bybit live positions (safe method)
        try:
            bybit_holdings = set()
            for acc_type in ["UNIFIED", "SPOT", "FUND"]:
                resp = bybit.session.get_wallet_balance(accountType=acc_type)
                if resp.get("retCode") != 0:
                    continue
                list_data = resp["result"].get("list", [])
                if not list_data:
                    continue
                for item in list_data[0].get("coin", []):
                    qty = float(item.get("walletBalance") or 0)
                    if item["coin"] != "USDT" and qty > 0.0001:
                        bybit_holdings.add(item["coin"] + "USDT")
                if bybit_holdings:
                    break
        except Exception as e:
            print(f"[Recovery] Could not fetch Bybit holdings: {e}")
            bybit_holdings = set()

        recovery_lines = []
        for t in sheet_trades:
            sym = t["symbol"]
            # Step C: in Sheet but NOT on Bybit → mark Closed_Manually
            if bybit_holdings and sym not in bybit_holdings:
                storage.mark_closed_manually(sym)
                recovery_lines.append(f"• {sym} — not on Bybit, marked Closed_Manually")
                print(f"[Recovery] {sym} not held on Bybit — marked Closed_Manually")
            else:
                # Step D: exists on both → restore monitoring
                active_trades[sym] = t
                recovery_lines.append(
                    f"• {sym} entry=${t['entry']} "
                    f"SL=${t['sl']} TP=${t['tp']}"
                )
                print(f"[Recovery] Restored {sym}")

        msg = (
            f"🔄 <b>Bot Restarted — {len(active_trades)} trade(s) recovered</b>\n"
            + "\n".join(recovery_lines)
        )
        await notifier.send_message(msg)
    else:
        mode_icon = {"paper": "📋", "testnet": "🧪", "live": "🔴"}.get(config.MODE, "🤖")
        await notifier.send_message(
            f"{mode_icon} <b>Bot Started on Render</b>\n"
            f"Mode:   <b>{config.MODE.upper()}</b>\n"
            f"Pairs:  <b>{len(config.WHITELIST_PAIRS)}</b>\n"
            f"Limit:  <b>{config.DAILY_LOSS_LIMIT_PERCENT}% daily</b>\n"
            f"Sheets: <b>{'✅ connected' if storage.is_connected else '❌ not configured'}</b>"
        )

    # Check balance on startup
    startup_balance = bybit.get_balance("USDT")
    if startup_balance <= 0:
        await notifier.send_message(
            "⚠️ <b>Balance Unreadable</b>\n"
            "Bot cannot see your USDT balance.\n"
            "Check: Bybit API key has Read + Spot Trade permissions.\n"
            "Bot will still start but cannot size positions correctly."
        )
    else:
        await notifier.send_message(
            f"💰 <b>Balance:</b> ${startup_balance:.4f} USDT"
        )

    cmd_handler.active_trades = active_trades
    _bot_status["mode"]   = config.MODE
    _bot_status["status"] = "running"

    # ── Helpers ───────────────────────────────────────────────

    async def close_trade(symbol: str, exit_price: float, reason: str):
        """Unified trade close: updates Sheet, CSV, daily loss, alerts."""
        trade = active_trades.get(symbol)
        if not trade:
            return

        entry      = trade["entry"]
        qty        = trade.get("qty", trade.get("size_usdt", 0) / entry)
        gross_pnl  = round((exit_price - entry) * qty, 6)

        # Sheets: calculates fees + net profit internally
        net_profit = storage.log_trade_close(trade, exit_price, gross_pnl, 0)

        # CSV backup
        logger.log_trade_close(symbol, exit_price, gross_pnl)

        # Daily loss tracking (use gross for simplicity)
        risk.record_pnl(gross_pnl)

        del active_trades[symbol]
        _bot_status["active_trades"] = len(active_trades)

        icon = "✅" if gross_pnl >= 0 else "🛑"
        sign = "+" if gross_pnl >= 0 else ""
        await notifier.send_message(
            f"{icon} <b>{reason} — {symbol}</b>\n"
            f"Exit:       ${exit_price:.4f}\n"
            f"Gross P&amp;L: {sign}${gross_pnl:.4f}\n"
            f"Fees:       -${abs(gross_pnl - (net_profit or gross_pnl)):.4f}\n"
            f"Net P&amp;L:   {sign}${(net_profit or gross_pnl):.4f}"
        )

    # ── Market scanner ────────────────────────────────────────

    async def scan_markets(is_manual: bool = False):
        balance = bybit.get_balance("USDT")
        if balance <= 0 and config.MODE != "paper":
            print("[Scan] Balance unreadable — skipping scan")
            return 0.0

        if config.MODE == "paper" and balance <= 0:
            balance = 40.0  # paper default

        # Daily loss gate — check ONCE before the loop (not 25x)
        halted, halt_msg = risk.is_daily_limit_hit(balance)
        if halted:
            print(f"[Scan] {halt_msg}")
            if is_manual:
                await notifier.send_message(f"⚠️ {halt_msg}")
            return balance

        found = 0
        for symbol in config.WHITELIST_PAIRS:
            if symbol in active_trades:
                continue
            if len(active_trades) >= config.MAX_OPEN_TRADES:
                break

            # Sharia gate
            if not sharia.is_compliant(symbol):
                continue

            # Fetch candles
            c1h    = bybit.get_candles(symbol, config.TIMEFRAME_MAIN)
            c4h    = bybit.get_candles(symbol, config.TIMEFRAME_TREND)
            c_daily= bybit.get_candles(symbol, config.TIMEFRAME_DAILY)

            if not c1h or not c4h or len(c1h) < 52:
                await asyncio.sleep(1.5)
                continue

            decision, data = brain.analyze(c1h, c4h, c_daily)

            if decision == "BUY":
                df1h = brain._to_df(c1h)
                current_price = brain._last_closed(df1h)["close"]
                stop_loss     = brain.get_stop_loss(df1h)

                # Validate stop loss
                if stop_loss <= 0 or stop_loss >= current_price:
                    print(f"[{symbol}] Invalid stop loss ${stop_loss:.4f} — skip")
                    await asyncio.sleep(1.5)
                    continue

                qty = risk.calculate_position_size(
                    balance, current_price, stop_loss
                )

                if qty == -1.0:
                    await notifier.send_message(
                        "⚠️ <b>Balance Missing</b> — cannot size position. "
                        "Check Bybit API permissions."
                    )
                    break

                if qty <= 0:
                    await asyncio.sleep(1.5)
                    continue

                take_profit = current_price + (
                    (current_price - stop_loss) * config.REWARD_TO_RISK_RATIO
                )
                size_usdt = round(qty * current_price, 4)

                order = bybit.place_order(symbol, "Buy", qty)

                if order.get("retCode", -1) == 0:
                    trade = {
                        "symbol":     symbol,
                        "qty":        qty,
                        "entry":      current_price,
                        "sl":         stop_loss,
                        "tp":         take_profit,
                        "size_usdt":  size_usdt,
                    }
                    active_trades[symbol] = trade
                    _bot_status["active_trades"] = len(active_trades)

                    smc_signal = "1H_OB+FVG+4H_TREND+DAILY_MA200"
                    storage.log_trade_open(trade, smc_signal)
                    logger.log_trade_open(
                        symbol, current_price, stop_loss,
                        take_profit, qty, smc_signal
                    )

                    await notifier.notify_trade_entry(
                        symbol, "BUY", qty, current_price, stop_loss, take_profit
                    )
                    found += 1

            elif decision == "POTENTIAL" and data:
                await notifier.send_message(
                    f"⏳ <b>POTENTIAL SETUP — {symbol}</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"<b>Entry:</b>  ${data['entry']:.4f}\n"
                    f"<b>SL:</b>     ${data['sl']:.4f}\n"
                    f"<b>TP:</b>     ${data['tp']:.4f}\n"
                    f"<b>Reason:</b> {data.get('reason','')}\n"
                    f"━━━━━━━━━━━━━━━"
                )
                found += 1

            await asyncio.sleep(1.5)  # rate limit

        if is_manual and found == 0:
            await notifier.send_message(
                "🔍 <b>Scan Complete.</b> No setups right now."
            )
        return balance

    # ── Main loop ─────────────────────────────────────────────
    while True:
        try:
            _bot_status["active_trades"] = len(active_trades)

            # Manual commands
            if cmd_handler.scan_requested:
                cmd_handler.scan_requested = False
                await scan_markets(is_manual=True)

            # Monitor open trades
            for symbol in list(active_trades.keys()):
                trade = active_trades.get(symbol)
                if not trade:
                    continue

                current_price = bybit.get_ticker(symbol)
                if not current_price:
                    continue

                # Stop loss hit
                if current_price <= trade["sl"]:
                    bybit.place_order(symbol, "Sell", trade["qty"])
                    await close_trade(symbol, current_price, "🛑 STOP LOSS HIT")
                    continue

                # Take profit hit
                if current_price >= trade["tp"]:
                    bybit.place_order(symbol, "Sell", trade["qty"])
                    await close_trade(symbol, current_price, "✅ TAKE PROFIT HIT")
                    continue

                # Break-even shield
                profit_pct = (current_price - trade["entry"]) / trade["entry"] * 100
                if profit_pct >= 1.5 and trade["sl"] < trade["entry"]:
                    active_trades[symbol]["sl"] = trade["entry"]
                    await notifier.send_message(
                        f"🛡️ <b>BREAK-EVEN SHIELD — {symbol}</b>\n"
                        f"Stop moved to entry ${trade['entry']:.4f}. "
                        f"Trade is now risk-free."
                    )

            # Scan (if not paused)
            if not cmd_handler.paused:
                await scan_markets()
                print(
                    f"[Loop] Done. Trades: {len(active_trades)}. "
                    f"Sheets: {_bot_status['sheets']}. Sleep 5min..."
                )
                await asyncio.sleep(300)  # 5 min after scan
            else:
                await asyncio.sleep(60)   # 1 min when paused — stay responsive

        except KeyboardInterrupt:
            print("[Bot] Stopped.")
            await notifier.send_message("🤖 Bot stopped manually.")
            break
        except Exception as e:
            err = str(e)[:200]
            print(f"[Loop] Error: {err}")
            await notifier.send_message(f"⚠️ <b>Bot Error:</b> {err}")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
