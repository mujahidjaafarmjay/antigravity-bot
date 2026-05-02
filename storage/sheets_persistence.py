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
        self.meta_tab = None
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
        """Creates 'Trades', 'Performance', 'ActiveTrades', and 'BotMeta' tabs if they don't exist."""
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
                self.perf_tab = self.sheet.add_worksheet("Performance", rows=2000, cols=10)
                self.perf_tab.append_row([
                    "Timestamp", "Symbol", "Score", "Entry", "SL", "TP", "Outcome", "PnL", "Fees", "Mode"
                ])

            # Active Trades Tab (for recovery)
            try:
                self.active_tab = self.sheet.worksheet("ActiveTrades")
            except gspread.WorksheetNotFound:
                self.active_tab = self.sheet.add_worksheet("ActiveTrades", rows=100, cols=8)
                self.active_tab.append_row([
                    "Symbol", "Score", "Entry", "SL", "TP", "Qty", "Mode", "Timestamp"
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

    def log_outcome(self, symbol, score, entry, sl, tp, outcome, pnl, fees, mode):
        """Logs a finished trade outcome to the 'Performance' tab."""
        if not self.perf_tab: return
        try:
            self.perf_tab.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                score,
                entry,
                sl,
                tp,
                outcome,
                pnl,
                fees,
                mode
            ])
            # Also remove from ActiveTrades
            self.remove_active_trade(symbol)
        except Exception as e:
            self.logger.error(f"Error logging outcome to Sheets: {e}")

    def add_active_trade(self, trade):
        """Adds a trade to the ActiveTrades tab."""
        if not self.active_tab: return
        try:
            self.active_tab.append_row([
                trade['symbol'],
                trade['score'],
                trade['entry'],
                trade['stop_loss'],
                trade['take_profit'],
                trade['qty'],
                config.MODE,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
        except Exception as e:
            self.logger.error(f"Error adding active trade to Sheets: {e}")

    def remove_active_trade(self, symbol):
        """Removes a trade from the ActiveTrades tab."""
        if not self.active_tab: return
        try:
            cell = self.active_tab.find(symbol)
            if cell:
                self.active_tab.delete_rows(cell.row)
        except Exception as e:
            self.logger.error(f"Error removing active trade from Sheets: {e}")

    def get_active_trades(self):
        """Recovers active trades from Sheets."""
        if not self.active_tab: return {}
        try:
            records = self.active_tab.get_all_records()
            active = {}
            for r in records:
                active[r['Symbol']] = {
                    "symbol": r['Symbol'],
                    "score": r['Score'],
                    "entry": float(r['Entry']),
                    "stop_loss": float(r['SL']),
                    "take_profit": float(r['TP']),
                    "qty": float(r['Qty']),
                    "mode": r['Mode']
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

    def get_performance_summary(self):
        """Calculates performance metrics grouped by score."""
        data = self.get_all_performance_data()
        if not data:
            return {}

        summary = {} # {score: {metrics}}

        for row in data:
            try:
                score = row.get('Score')
                if score is None or score == "": continue
                score = int(score)

                if score not in summary:
                    summary[score] = {
                        "trades": 0, "wins": 0, "losses": 0,
                        "total_pnl": 0.0, "total_fees": 0.0,
                        "win_amounts": [], "loss_amounts": []
                    }

                s = summary[score]
                s["trades"] += 1
                pnl = float(row.get('PnL', 0))
                fees = float(row.get('Fees', 0))
                outcome = row.get('Outcome')

                s["total_pnl"] += pnl
                s["total_fees"] += fees

                if outcome == "WIN":
                    s["wins"] += 1
                    s["win_amounts"].append(pnl)
                elif outcome == "LOSS":
                    s["losses"] += 1
                    s["loss_amounts"].append(abs(pnl))
            except Exception as e:
                self.logger.error(f"Error processing row for performance summary: {e}")
                continue

        # Finalize calculations
        final_summary = {}
        for score, s in summary.items():
            win_rate = s["wins"] / s["trades"] if s["trades"] > 0 else 0

            # Correct Avg Win/Loss: only use data from corresponding outcomes
            avg_win = sum(s["win_amounts"]) / len(s["win_amounts"]) if s["win_amounts"] else 0.0
            avg_loss = sum(s["loss_amounts"]) / len(s["loss_amounts"]) if s["loss_amounts"] else 0.0

            # Expectancy = (WinRate * AvgWin) - (LossRate * AvgLoss)
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

            # Profit Factor = Total Win Amount / Total Loss Amount
            total_wins = sum(s["win_amounts"])
            total_losses = sum(s["loss_amounts"])
            profit_factor = total_wins / total_losses if total_losses > 0 else (float('inf') if total_wins > 0 else 1.0)

            final_summary[score] = {
                "score": score,
                "trades": s["trades"],
                "win_rate": win_rate,
                "net_pnl": s["total_pnl"],
                "expectancy": expectancy,
                "profit_factor": profit_factor,
                "avg_win": avg_win,
                "avg_loss": avg_loss
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

    def update_meta(self, daily_pnl, is_halted):
        """Updates bot metadata."""
        if not self.meta_tab: return
        try:
            self.meta_tab.update("B2", str(daily_pnl))
            self.meta_tab.update("B3", str(is_halted))
            self.meta_tab.update("B4", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            self.logger.error(f"Error updating BotMeta: {e}")

    def get_meta(self):
        """Retrieves bot metadata for startup recovery."""
        if not self.meta_tab: return {"daily_net_pnl": 0.0, "is_halted": False}
        try:
            data = self.meta_tab.get_all_records()
            meta = {}
            for row in data:
                meta[row['Key']] = row['Value']
            
            return {
                "daily_net_pnl": float(meta.get('daily_net_pnl', 0.0)),
                "is_halted": meta.get('is_halted', 'False').lower() == 'true'
            }
        except Exception as e:
            self.logger.error(f"Error reading BotMeta: {e}")
            return {"daily_net_pnl": 0.0, "is_halted": False}
