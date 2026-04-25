# ============================================================
#  logger/trade_logger.py — Updated to match new sheet columns
#  Tracks: fees, net_profit, smc_signal, sharia_status
# ============================================================
import csv
import os
import uuid
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "..", "logs", "trades.csv")

BYBIT_FEE_RATE = 0.001  # 0.1% per side

HEADERS = [
    "Trade_ID", "Timestamp", "Symbol", "Entry_Price",
    "Stop_Loss", "Take_Profit", "Size_USDT", "Status",
    "Exit_Price", "Fees", "Net_Profit", "SMC_Signal", "Sharia_Status"
]


class TradeLogger:
    def __init__(self):
        self.filename = LOG_PATH
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        self._ensure_headers()

    def _ensure_headers(self):
        if not os.path.exists(self.filename):
            with open(self.filename, "w", newline="") as f:
                csv.writer(f).writerow(HEADERS)

    def log_trade_open(self, symbol, entry, sl, tp, qty,
                       smc_signal="OB+FVG+4H_TREND") -> str:
        trade_id  = str(uuid.uuid4())[:8].upper()
        size_usdt = round(qty * entry, 4)
        with open(self.filename, "a", newline="") as f:
            csv.writer(f).writerow([
                trade_id,
                time.strftime("%Y-%m-%d %H:%M:%S"),
                symbol, entry, sl, tp,
                size_usdt, "OPEN",
                "", "", "",     # exit, fees, net_profit
                smc_signal, "Verified",
            ])
        return trade_id

    def log_trade_close(self, symbol: str, exit_price: float,
                        gross_pnl: float):
        """Update most recent OPEN row with exit, fees, net profit."""
        if not os.path.exists(self.filename):
            return

        rows = []
        with open(self.filename, "r", newline="") as f:
            rows = list(csv.reader(f))

        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 8 and row[2] == symbol and row[7] == "OPEN":
                size_usdt  = float(row[6] or 0)
                # qty = size_usdt / entry to get exit_value
                entry      = float(row[3] or 1)
                qty        = size_usdt / entry if entry > 0 else 0
                exit_value = qty * exit_price
                fees       = round(
                    (size_usdt * BYBIT_FEE_RATE) +
                    (exit_value * BYBIT_FEE_RATE), 6
                )
                net_profit = round(gross_pnl - fees, 6)

                rows[i][7]  = "CLOSED"
                rows[i][8]  = str(round(exit_price, 6))
                rows[i][9]  = str(fees)
                rows[i][10] = str(net_profit)
                break

        with open(self.filename, "w", newline="") as f:
            csv.writer(f).writerows(rows)
