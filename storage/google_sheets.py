# ============================================================
#  storage/google_sheets.py — Full upgrade from corrections_v2
#
#  Sheet structure (Antigravity Trades tab):
#  A=Trade_ID  B=Timestamp  C=Symbol  D=Entry_Price  E=Stop_Loss
#  F=Take_Profit  G=Size_USDT  H=Status  I=Exit_Price
#  J=Fees  K=Net_Profit  L=SMC_Signal  M=Sharia_Status
#
#  Additional tabs: "Active Trades", "Summary", "BotMeta"
# ============================================================
import json
import os
import uuid
from datetime import datetime
import config


BYBIT_FEE_RATE = 0.001   # 0.1% per side (buy + sell)

TRADE_HEADERS = [
    "Trade_ID", "Timestamp", "Symbol", "Entry_Price",
    "Stop_Loss", "Take_Profit", "Size_USDT", "Status",
    "Exit_Price", "Fees", "Net_Profit", "SMC_Signal", "Sharia_Status"
]

ACTIVE_HEADERS = [
    "Symbol", "Entry_Price", "Stop_Loss", "Take_Profit",
    "Size_USDT", "Qty", "Timestamp", "Trade_ID"
]

SUMMARY_FORMULAS = [
    ["Current Balance ($40 start)",
     "=40+IFERROR(SUM('Antigravity Trades'!K:K),0)"],
    ["Total Trades",
     "=COUNTA('Antigravity Trades'!A:A)-1"],
    ["Win Rate %",
     "=IFERROR(COUNTIF('Antigravity Trades'!K:K,\">0\")"
     "/MAX(1,COUNTA('Antigravity Trades'!K:K)-1),0)"],
    ["Total Gross Profit",
     "=IFERROR(SUMIF('Antigravity Trades'!K:K,\">0\","
     "'Antigravity Trades'!K:K),0)"],
    ["Total Gross Loss",
     "=IFERROR(SUMIF('Antigravity Trades'!K:K,\"<0\","
     "'Antigravity Trades'!K:K),0)"],
    ["Total Fees Paid (Ghost Cost)",
     "=IFERROR(SUM('Antigravity Trades'!J:J),0)"],
    ["Net P&L",
     "=IFERROR(SUM('Antigravity Trades'!K:K),0)"],
    ["Open Trades",
     "=COUNTA('Active Trades'!A:A)-1"],
]


class GoogleSheetsStorage:

    def __init__(self):
        self.client       = None
        self.wb           = None          # workbook
        self.sheet        = None          # Antigravity Trades tab
        self.active_sheet = None          # Active Trades tab
        self.meta_sheet   = None          # BotMeta tab
        self._connect()

    # ── Connection ────────────────────────────────────────────

    def _connect(self):
        creds_json = config.GOOGLE_SHEETS_CREDENTIALS
        if not creds_json:
            print("[Sheets] GOOGLE_SHEETS_CREDENTIALS not set — persistence disabled.")
            return
        try:
            import gspread
            from oauth2client.service_account import ServiceAccountCredentials

            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]

            creds_dict = json.loads(creds_json)
            # Fix: escaped newlines in private_key when pasted into Render
            if "private_key" in creds_dict:
                creds_dict["private_key"] = (
                    creds_dict["private_key"].replace("\\n", "\n")
                )

            creds       = ServiceAccountCredentials.from_json_keyfile_dict(
                creds_dict, scope
            )
            self.client = gspread.authorize(creds)

            # Open by ID (most reliable), fall back to name
            sheet_id = config.GOOGLE_SHEET_ID
            if sheet_id:
                self.wb = self.client.open_by_key(sheet_id)
                print(f"[Sheets] Opened by ID: {sheet_id[:24]}...")
            else:
                self.wb = self.client.open(config.GOOGLE_SHEET_NAME)
                print(f"[Sheets] Opened by name: {config.GOOGLE_SHEET_NAME}")

            self._ensure_all_tabs()
            print("[Sheets] ✓ All tabs ready")

        except json.JSONDecodeError as e:
            print(f"[Sheets] Invalid JSON credentials: {e}")
        except Exception as e:
            print(f"[Sheets] Connection failed: {e}")
            self.client = self.wb = None

    def _get_or_create_tab(self, title: str, rows: int = 1000, cols: int = 15):
        try:
            return self.wb.worksheet(title)
        except Exception:
            tab = self.wb.add_worksheet(title=title, rows=rows, cols=cols)
            print(f"[Sheets] Created tab: {title}")
            return tab

    def _ensure_all_tabs(self):
        # ── Tab 1: Antigravity Trades (main log) ─────────────
        self.sheet = self.wb.sheet1
        if self.sheet.title != "Antigravity Trades":
            try:
                self.sheet = self.wb.worksheet("Antigravity Trades")
            except Exception:
                self.sheet.update_title("Antigravity Trades")
        if not self.sheet.row_values(1):
            self.sheet.insert_row(TRADE_HEADERS, 1)
            print("[Sheets] Trade headers written")

        # ── Tab 2: Active Trades ──────────────────────────────
        self.active_sheet = self._get_or_create_tab("Active Trades")
        if not self.active_sheet.row_values(1):
            self.active_sheet.insert_row(ACTIVE_HEADERS, 1)
            print("[Sheets] Active Trades headers written")

        # ── Tab 3: Summary ────────────────────────────────────
        summary = self._get_or_create_tab("Summary", rows=20, cols=2)
        if not summary.row_values(1):
            for i, (label, formula) in enumerate(SUMMARY_FORMULAS, start=1):
                summary.update(f"A{i}", [[label]])
                summary.update(f"B{i}", [[formula]])
            print("[Sheets] Summary formulas written")

        # ── Tab 4: BotMeta (pause state etc.) ─────────────────
        self.meta_sheet = self._get_or_create_tab("BotMeta", rows=50, cols=2)
        if not self.meta_sheet.row_values(1):
            self.meta_sheet.insert_row(["key", "value"], 1)

    # ── Fee calculation (from corrections_v2) ─────────────────

    @staticmethod
    def calculate_fees(entry_value: float, exit_value: float) -> float:
        """
        Standard Bybit Spot fee: 0.1% buy + 0.1% sell.
        This is the 'Ghost Cost' that eats real profit.
        """
        buy_fee  = entry_value * BYBIT_FEE_RATE
        sell_fee = exit_value  * BYBIT_FEE_RATE
        return round(buy_fee + sell_fee, 6)

    # ── Trade open ────────────────────────────────────────────

    def log_trade_open(self, trade: dict, smc_signal: str = "") -> str:
        """
        Log a new trade. Returns trade_id for reference.
        Writes to both Antigravity Trades and Active Trades tabs.
        """
        trade_id = str(uuid.uuid4())[:8].upper()
        now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        size_usdt = round(trade["qty"] * trade["entry"], 4)

        # Antigravity Trades tab (full log)
        if self.sheet:
            try:
                self.sheet.append_row([
                    trade_id,
                    now,
                    trade["symbol"],
                    trade["entry"],
                    trade["sl"],
                    trade["tp"],
                    size_usdt,
                    "OPEN",
                    "",   # Exit_Price — filled on close
                    "",   # Fees — filled on close
                    "",   # Net_Profit — filled on close
                    smc_signal or "OB+FVG+4H_TREND",
                    "Verified",  # Sharia_Status (from whitelist)
                ])
            except Exception as e:
                print(f"[Sheets] log_trade_open (trades tab): {e}")

        # Active Trades tab (for crash recovery)
        if self.active_sheet:
            try:
                self.active_sheet.append_row([
                    trade["symbol"],
                    trade["entry"],
                    trade["sl"],
                    trade["tp"],
                    size_usdt,
                    trade["qty"],
                    now,
                    trade_id,
                ])
            except Exception as e:
                print(f"[Sheets] log_trade_open (active tab): {e}")

        return trade_id

    # ── Trade close ───────────────────────────────────────────

    def log_trade_close(self, trade: dict, exit_price: float,
                        gross_pnl: float, pnl_pct: float):
        """
        Update Antigravity Trades row to CLOSED with real fees + net profit.
        Remove from Active Trades tab.
        """
        size_usdt  = round(trade.get("qty", 0) * trade.get("entry", 0), 4)
        exit_value = round(trade.get("qty", 0) * exit_price, 4)
        fees       = self.calculate_fees(size_usdt, exit_value)
        net_profit = round(gross_pnl - fees, 6)

        # Update Antigravity Trades tab
        if self.sheet:
            try:
                rows = self.sheet.get_all_values()
                for i, row in enumerate(rows[1:], start=2):
                    if (len(row) > 7
                            and row[2] == trade["symbol"]
                            and row[7] == "OPEN"):
                        self.sheet.update(
                            range_name=f"H{i}:K{i}",
                            values=[[
                                "CLOSED",
                                round(exit_price, 6),
                                round(fees, 6),
                                round(net_profit, 6),
                            ]]
                        )
                        break
            except Exception as e:
                print(f"[Sheets] log_trade_close (trades tab): {e}")

        # Remove from Active Trades tab
        if self.active_sheet:
            try:
                rows = self.active_sheet.get_all_values()
                for i, row in enumerate(rows[1:], start=2):
                    if row and row[0] == trade["symbol"]:
                        self.active_sheet.delete_rows(i)
                        break
            except Exception as e:
                print(f"[Sheets] log_trade_close (active tab): {e}")

        print(
            f"[Sheets] {trade['symbol']} closed | "
            f"Gross: ${gross_pnl:+.4f} | "
            f"Fees: ${fees:.4f} | "
            f"Net: ${net_profit:+.4f}"
        )
        return net_profit

    # ── Crash recovery ────────────────────────────────────────

    def get_open_trades(self) -> list:
        """
        Read Active Trades tab — used on bot restart.
        Cross-references with Bybit positions in main.py.
        """
        if not self.active_sheet:
            return []
        try:
            rows   = self.active_sheet.get_all_values()
            result = []
            for row in rows[1:]:
                if len(row) >= 6 and row[0]:
                    try:
                        result.append({
                            "symbol":   row[0],
                            "entry":    float(row[1] or 0),
                            "sl":       float(row[2] or 0),
                            "tp":       float(row[3] or 0),
                            "size_usdt":float(row[4] or 0),
                            "qty":      float(row[5] or 0),
                            "trade_id": row[7] if len(row) > 7 else "",
                        })
                    except ValueError:
                        continue
            return result
        except Exception as e:
            print(f"[Sheets] get_open_trades: {e}")
            return []

    def mark_closed_manually(self, symbol: str):
        """
        Step C from corrections_v2: if trade is in Sheet but not
        on Bybit, mark it as Closed_Manually.
        """
        if self.sheet:
            try:
                rows = self.sheet.get_all_values()
                for i, row in enumerate(rows[1:], start=2):
                    if len(row) > 7 and row[2] == symbol and row[7] == "OPEN":
                        self.sheet.update(
                            range_name=f"H{i}", values=[["Closed_Manually"]]
                        )
                        break
            except Exception as e:
                print(f"[Sheets] mark_closed_manually: {e}")

        if self.active_sheet:
            try:
                rows = self.active_sheet.get_all_values()
                for i, row in enumerate(rows[1:], start=2):
                    if row and row[0] == symbol:
                        self.active_sheet.delete_rows(i)
                        break
            except Exception as e:
                print(f"[Sheets] remove from active: {e}")

    # ── Bot meta ──────────────────────────────────────────────

    def get_bot_meta(self, key: str) -> str:
        if not self.meta_sheet:
            return ""
        try:
            rows = self.meta_sheet.get_all_values()
            for row in rows[1:]:
                if row and row[0] == key:
                    return row[1] if len(row) > 1 else ""
        except Exception as e:
            print(f"[Sheets] get_bot_meta({key}): {e}")
        return ""

    def set_bot_meta(self, key: str, value: str):
        if not self.meta_sheet:
            return
        try:
            rows = self.meta_sheet.get_all_values()
            for i, row in enumerate(rows[1:], start=2):
                if row and row[0] == key:
                    self.meta_sheet.update(range_name=f"B{i}", values=[[value]])
                    return
            self.meta_sheet.append_row([key, value])
        except Exception as e:
            print(f"[Sheets] set_bot_meta({key}): {e}")

    @property
    def is_connected(self) -> bool:
        return self.sheet is not None
