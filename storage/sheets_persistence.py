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
