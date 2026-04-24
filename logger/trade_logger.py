# ============================================================
#  logger/trade_logger.py
#  Fix #5: consistent path — always logs/trades.csv
# ============================================================
import csv
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "..", "logs", "trades.csv")


class TradeLogger:
    def __init__(self):
        self.filename = LOG_PATH
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        self._ensure_headers()

    def _ensure_headers(self):
        if not os.path.exists(self.filename):
            with open(self.filename, "w", newline="") as f:
                csv.writer(f).writerow([
                    "Timestamp", "Symbol", "Side", "Qty",
                    "Price", "SL", "TP", "Status", "P&L"
                ])

    def log_trade(self, symbol, side, qty, price, sl, tp,
                  status="OPEN", pnl=0.0):
        with open(self.filename, "a", newline="") as f:
            csv.writer(f).writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                symbol, side, qty, price, sl, tp, status, pnl
            ])

    def update_trade_close(self, symbol: str, exit_price: float, pnl: float):
        """Update the most recent OPEN row for symbol to CLOSED."""
        if not os.path.exists(self.filename):
            return
        rows = []
        updated = False
        with open(self.filename, "r", newline="") as f:
            reader = csv.reader(f)
            rows   = list(reader)

        for i in range(len(rows) - 1, 0, -1):
            if rows[i][1] == symbol and rows[i][7] == "OPEN":
                rows[i][7] = "CLOSED"
                rows[i][8] = str(round(pnl, 4))
                updated = True
                break

        if updated:
            with open(self.filename, "w", newline="") as f:
                csv.writer(f).writerows(rows)
