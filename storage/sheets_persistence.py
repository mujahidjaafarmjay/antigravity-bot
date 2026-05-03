import gspread
from google.oauth2.service_account import Credentials
import json
import logging
import config
from datetime import datetime

class SheetsPersistence:
    """
    Google Sheets persistence for Cloud (Render) state recovery.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.sheet = None
        self.trades_tab = None
        self.perf_tab = None
        self.active_tab = None
        self.meta_tab = None
        self.stats_tab = None
        self._connect()

    def _connect(self):
        """Connects to Google Sheets using credentials from env."""
        try:
            if not config.GOOGLE_SHEETS_CREDENTIALS:
                self.logger.warning("No Google Sheets credentials found. Persistence disabled.")
                return

            creds_dict = json.loads(config.GOOGLE_SHEETS_CREDENTIALS)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            client = gspread.authorize(creds)
            
            if config.GOOGLE_SHEET_ID:
                self.sheet = client.open_by_key(config.GOOGLE_SHEET_ID)
            else:
                self.sheet = client.open(config.GOOGLE_SHEET_NAME)

            # Ensure tabs exist
            self._setup_tabs()
            self.logger.info("Connected to Google Sheets persistence.")
        except Exception as e:
            self.logger.error(f"Error connecting to Google Sheets: {e}")

    def _setup_tabs(self):
        """Creates 'Trades', 'Performance', 'ActiveTrades', 'Stats', and 'BotMeta' tabs if they don't exist."""
        try:
            # Trades Tab (Signal Log)
            try:
                self.trades_tab = self.sheet.worksheet("Trades")
            except gspread.WorksheetNotFound:
                self.trades_tab = self.sheet.add_worksheet("Trades", rows=1000, cols=10)
                self.trades_tab.append_row([
                    "Timestamp", "Symbol", "Action", "Score", "Entry", "SL", "TP", "Qty", "Reason", "Sharia_Status"
                ])

            # Performance Tab (Outcome Log)
            try:
                self.perf_tab = self.sheet.worksheet("Performance")
            except gspread.WorksheetNotFound:
                self.perf_tab = self.sheet.add_worksheet("Performance", rows=2000, cols=15)
                self.perf_tab.append_row([
                    "Timestamp", "Symbol", "Score", "RR", "Risk_USDT", "Entry", "SL", "TP",
                "Outcome", "PnL", "Fees", "Duration_Mins", "Session", "ATR_Perc", "Slippage", "Mode"
                ])

            # Active Trades Tab (for recovery)
            try:
                self.active_tab = self.sheet.worksheet("ActiveTrades")
            except gspread.WorksheetNotFound:
                self.active_tab = self.sheet.add_worksheet("ActiveTrades", rows=100, cols=12)
                self.active_tab.append_row([
                    "Symbol", "Score", "RR", "Risk_USDT", "Entry", "SL", "TP", "Qty",
                    "Session", "ATR_Perc", "Mode", "Timestamp"
                ])

            # Stats Tab (High-Level Summary)
            try:
                self.stats_tab = self.sheet.worksheet("Stats")
            except gspread.WorksheetNotFound:
                self.stats_tab = self.sheet.add_worksheet("Stats", rows=100, cols=10)
                self.stats_tab.append_row([
                    "Metric_Type", "Key", "Trades", "WinRate", "NetPnL", "Expectancy", "ProfitFactor", "AvgWin", "AvgLoss", "LastUpdate"
                ])

            # BotMeta Tab
            try:
                self.meta_tab = self.sheet.worksheet("BotMeta")
            except gspread.WorksheetNotFound:
                self.meta_tab = self.sheet.add_worksheet("BotMeta", rows=100, cols=2)
                self.meta_tab.update("A1:B4", [
                    ["Key", "Value"],
                    ["daily_net_pnl", "0.0"],
                    ["is_halted", "False"],
                    ["peak_balance", "0.0"],
                    ["last_run", ""]
                ])
        except Exception as e:
            self.logger.error(f"Error setting up Sheets tabs: {e}")

    def log_trade(self, trade_data):
        """Logs a signal/entry to the 'Trades' tab."""
        if not self.trades_tab: return
        try:
            self.trades_tab.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                trade_data.get('symbol'),
                trade_data.get('action'),
                trade_data.get('score'),
                trade_data.get('entry'),
                trade_data.get('stop_loss'),
                trade_data.get('take_profit'),
                trade_data.get('qty'),
                trade_data.get('reason'),
                "Verified" # Sharia Status
            ])
        except Exception as e:
            self.logger.error(f"Error logging trade to Sheets: {e}")

    def log_outcome(self, trade, outcome, pnl, fees, slippage=0.0):
        """Logs a finished trade outcome with high-fidelity metrics."""
        if not self.perf_tab: return
        try:
            # Calculate duration
            duration = ""
            if 'timestamp' in trade:
                try:
                    start_time = datetime.strptime(trade['timestamp'], "%Y-%m-%d %H:%M:%S")
                    mins = int((datetime.now() - start_time).total_seconds() / 60)
                    duration = mins
                except: pass

            self.perf_tab.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                trade['symbol'],
                trade['score'],
                trade.get('rr', 0),
                trade.get('risk_usdt', 0),
                trade['entry'],
                trade['stop_loss'],
                trade['take_profit'],
                outcome,
                pnl,
                fees,
                duration,
                trade.get('session', ''),
                trade.get('atr_perc', 0),
                f"{slippage:.4f}",
                config.MODE
            ])
            # Also remove from ActiveTrades
            self.remove_active_trade(trade['symbol'])
        except Exception as e:
            self.logger.error(f"Error logging outcome to Sheets: {e}")

    def add_active_trade(self, trade):
        """Adds a trade to the ActiveTrades tab with extra metadata."""
        if not self.active_tab: return
        try:
            self.active_tab.append_row([
                trade['symbol'],
                trade['score'],
                trade.get('rr', 0),
                trade.get('risk_usdt', 0),
                trade['entry'],
                trade['stop_loss'],
                trade['take_profit'],
                trade['qty'],
                trade.get('session', ''),
                trade.get('atr_perc', 0),
                config.MODE,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
        except Exception as e:
            self.logger.error(f"Error adding active trade to Sheets: {e}")

    def remove_active_trade(self, symbol):
        """Removes all trades for a symbol from the ActiveTrades tab to ensure clean state."""
        if not self.active_tab: return
        try:
            # Delete in reverse to not affect row indices
            cells = self.active_tab.findall(symbol)
            if cells:
                rows_to_delete = sorted([c.row for c in cells], reverse=True)
                for row in rows_to_delete:
                    self.active_tab.delete_rows(row)
        except Exception as e:
            self.logger.error(f"Error removing active trade from Sheets: {e}")

    def get_active_trades(self):
        """Recovers active trades from Sheets with all metadata."""
        if not self.active_tab: return {}
        try:
            records = self.active_tab.get_all_records()
            active = {}
            for r in records:
                active[r['Symbol']] = {
                    "symbol": r['Symbol'],
                    "score": r['Score'],
                    "rr": r.get('RR', 0),
                    "risk_usdt": r.get('Risk_USDT', 0),
                    "entry": float(r['Entry']),
                    "stop_loss": float(r['SL']),
                    "take_profit": float(r['TP']),
                    "qty": float(r['Qty']),
                    "session": r.get('Session', ''),
                    "atr_perc": r.get('ATR_Perc', 0),
                    "mode": r['Mode'],
                    "timestamp": r.get('Timestamp', '')
                }
            return active
        except Exception as e:
            self.logger.error(f"Error getting active trades from Sheets: {e}")
            return {}

    def get_all_performance_data(self):
        """Fetches all raw performance data from Sheets."""
        if not self.perf_tab: return []
        try:
            return self.perf_tab.get_all_records()
        except Exception as e:
            self.logger.error(f"Error fetching performance data: {e}")
            return []

    def update_stats_tab(self, summary):
        """Updates the 'Stats' tab with the latest performance summary."""
        if not self.stats_tab: return
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []

            # 1. Global Stats
            g = summary.get("GLOBAL", {})
            rows.append([
                "GLOBAL", "ALL", g.get("trades", 0),
                f"{g.get('wins', 0)/g.get('trades', 1):.1%}" if g.get('trades', 0) > 0 else "0%",
                g.get("net_pnl", 0.0), 0, # Expectancy not defined for global here
                f"{g.get('gross_win_pnl', 0) / g.get('gross_loss_pnl', 1):.2f}" if g.get('gross_loss_pnl', 0) > 0 else "1.0",
                0, 0, now
            ])

            # 2. Score Stats
            for key in sorted(summary.keys()):
                if key == "GLOBAL": continue
                s = summary[key]
                rows.append([
                    "SCORE", key, s["trades"], f"{s['win_rate']:.1%}",
                    s["net_pnl"], s["expectancy"], s["profit_factor"],
                    s["avg_win"], s["avg_loss"], now
                ])

            # Clear and Update
            self.stats_tab.clear()
            self.stats_tab.append_row([
                "Metric_Type", "Key", "Trades", "WinRate", "NetPnL", "Expectancy", "ProfitFactor", "AvgWin", "AvgLoss", "LastUpdate"
            ])
            self.stats_tab.append_rows(rows)
        except Exception as e:
            self.logger.error(f"Error updating Stats tab: {e}")

    def get_performance_summary(self, data=None):
        """Calculates performance metrics grouped by score and global stats."""
        if data is None:
            data = self.get_all_performance_data()

        # Initialize summary with global stats container
        summary = {
            "GLOBAL": {
                "trades": 0, "wins": 0, "losses": 0,
                "gross_win_pnl": 0.0, "gross_loss_pnl": 0.0,
                "total_fees": 0.0, "net_pnl": 0.0
            }
        }

        if not data:
            return summary

        for row in data:
            try:
                # Use standardized lowercase keys if possible, but handle sheet headers
                score = row.get('Score')
                if score is None or score == "": continue
                score = int(score)

                if score not in summary:
                    summary[score] = {
                        "trades": 0, "wins": 0, "losses": 0,
                        "gross_win_pnl": 0.0, "gross_loss_pnl": 0.0,
                        "total_fees": 0.0,
                        "win_amounts": [], "loss_amounts": []
                    }

                # Standardize pnl field (handle 'PnL' from sheet or 'net_pnl' from code)
                pnl = float(row.get('PnL', row.get('net_pnl', 0)))
                fees = float(row.get('Fees', row.get('fees', 0)))
                outcome = row.get('Outcome', row.get('outcome', ''))

                # Update Score Stats
                s = summary[score]
                s["trades"] += 1
                s["total_fees"] += fees

                # Update Global Stats
                g = summary["GLOBAL"]
                g["trades"] += 1
                g["total_fees"] += fees
                g["net_pnl"] += pnl

                if outcome.upper() == "WIN":
                    s["wins"] += 1
                    s["gross_win_pnl"] += pnl
                    s["win_amounts"].append(pnl)

                    g["wins"] += 1
                    g["gross_win_pnl"] += pnl
                elif outcome.upper() == "LOSS":
                    s["losses"] += 1
                    s["gross_loss_pnl"] += abs(pnl)
                    s["loss_amounts"].append(abs(pnl))

                    g["losses"] += 1
                    g["gross_loss_pnl"] += abs(pnl)
            except Exception as e:
                self.logger.error(f"Error processing row for performance summary: {e}")
                continue

        # Finalize calculations
        final_summary = {}
        for key, s in summary.items():
            if key == "GLOBAL":
                final_summary["GLOBAL"] = s
                continue

            win_rate = s["wins"] / s["trades"] if s["trades"] > 0 else 0

            # Correct Avg Win/Loss: only use data from corresponding outcomes
            avg_win = s["gross_win_pnl"] / s["wins"] if s["wins"] > 0 else 0.0
            avg_loss = s["gross_loss_pnl"] / s["losses"] if s["losses"] > 0 else 0.0

            # Expectancy = (WinRate * AvgWin) - (LossRate * AvgLoss)
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

            # Profit Factor = Gross Wins / Gross Losses
            profit_factor = s["gross_win_pnl"] / s["gross_loss_pnl"] if s["gross_loss_pnl"] > 0 else (float('inf') if s["gross_win_pnl"] > 0 else 1.0)

            final_summary[key] = {
                "score": key,
                "trades": s["trades"],
                "win_rate": win_rate,
                "net_pnl": s["gross_win_pnl"] - s["gross_loss_pnl"] - s["total_fees"],
                "expectancy": expectancy,
                "profit_factor": profit_factor,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "gross_win_pnl": s["gross_win_pnl"],
                "gross_loss_pnl": s["gross_loss_pnl"]
            }

        return final_summary

    def get_bot_meta(self, key):
        """Retrieves a specific metadata value."""
        if not self.meta_tab: return None
        try:
            data = self.meta_tab.get_all_records()
            for row in data:
                if row['Key'] == key:
                    return row['Value']
            return None
        except Exception as e:
            self.logger.error(f"Error reading BotMeta key {key}: {e}")
            return None

    def set_bot_meta(self, key, value):
        """Sets a specific metadata value."""
        if not self.meta_tab: return
        try:
            # Find the row
            cell = self.meta_tab.find(key)
            if cell:
                self.meta_tab.update_cell(cell.row, cell.col + 1, str(value))
            else:
                self.meta_tab.append_row([key, str(value)])
        except Exception as e:
            self.logger.error(f"Error setting BotMeta key {key}: {e}")

    def update_meta(self, daily_pnl, is_halted, peak_balance=0.0):
        """Updates bot metadata."""
        if not self.meta_tab: return
        try:
            self.meta_tab.update("B2", str(daily_pnl))
            self.meta_tab.update("B3", str(is_halted))
            if peak_balance > 0:
                self.meta_tab.update("B4", str(peak_balance))
            self.meta_tab.update("B5", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            self.logger.error(f"Error updating BotMeta: {e}")

    def get_meta(self):
        """Retrieves bot metadata for startup recovery."""
        if not self.meta_tab: return {"daily_net_pnl": 0.0, "is_halted": False, "peak_balance": 0.0}
        try:
            data = self.meta_tab.get_all_records()
            meta = {}
            for row in data:
                meta[row['Key']] = row['Value']
            
            return {
                "daily_net_pnl": float(meta.get('daily_net_pnl', 0.0)),
                "is_halted": meta.get('is_halted', 'False').lower() == 'true',
                "peak_balance": float(meta.get('peak_balance', 0.0))
            }
        except Exception as e:
            self.logger.error(f"Error reading BotMeta: {e}")
            return {"daily_net_pnl": 0.0, "is_halted": False}
