# ============================================================
#  storage/google_sheets.py
#  Fix #8: added get_bot_meta / set_bot_meta for pause state
# ============================================================
import json
import os
from datetime import datetime
import config


class GoogleSheetsStorage:

    TRADE_HEADERS = [
        "timestamp", "symbol", "side", "entry", "qty",
        "sl", "tp", "status", "exit_price", "pnl_usd", "pnl_pct"
    ]
    META_SHEET_NAME = "BotMeta"

    def __init__(self):
        self.client      = None
        self.sheet       = None
        self.meta_sheet  = None
        self._connect()

    def _connect(self):
        creds_json = config.GOOGLE_SHEETS_CREDENTIALS
        if not creds_json:
            print("[Sheets] No credentials — persistence disabled.")
            return
        try:
            import gspread
            from oauth2client.service_account import ServiceAccountCredentials
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds       = ServiceAccountCredentials.from_json_keyfile_dict(
                json.loads(creds_json), scope
            )
            self.client = gspread.authorize(creds)
            wb          = self.client.open(config.GOOGLE_SHEET_NAME)
            self.sheet  = wb.sheet1
            self._ensure_headers()

            # Meta sheet for bot state (Fix #8)
            try:
                self.meta_sheet = wb.worksheet(self.META_SHEET_NAME)
            except Exception:
                self.meta_sheet = wb.add_worksheet(
                    title=self.META_SHEET_NAME, rows=50, cols=2
                )
                self.meta_sheet.insert_row(["key", "value"], 1)

            print(f"[Sheets] Connected to '{config.GOOGLE_SHEET_NAME}'")
        except Exception as e:
            print(f"[Sheets] Connection failed: {e}")
            self.client = self.sheet = self.meta_sheet = None

    def _ensure_headers(self):
        try:
            if not self.sheet.row_values(1):
                self.sheet.insert_row(self.TRADE_HEADERS, 1)
        except Exception:
            pass

    # ── Trade persistence ─────────────────────────────────────

    def log_trade_open(self, trade: dict):
        if not self.sheet:
            return
        try:
            self.sheet.append_row([
                datetime.now().isoformat(),
                trade["symbol"], "BUY",
                trade["entry"], trade["qty"],
                trade["sl"],    trade["tp"],
                "OPEN", "", "", "",
            ])
        except Exception as e:
            print(f"[Sheets] log_trade_open: {e}")

    def log_trade_close(self, trade: dict, exit_price: float,
                        pnl_usd: float, pnl_pct: float):
        if not self.sheet:
            return
        try:
            rows = self.sheet.get_all_values()
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > 7 and row[1] == trade["symbol"] and row[7] == "OPEN":
                    self.sheet.update(
                        f"H{i}:K{i}",
                        [["CLOSED", exit_price,
                          round(pnl_usd, 4), round(pnl_pct, 2)]]
                    )
                    break
        except Exception as e:
            print(f"[Sheets] log_trade_close: {e}")

    def get_open_trades(self) -> list:
        if not self.sheet:
            return []
        try:
            rows = self.sheet.get_all_values()
            result = []
            for row in rows[1:]:
                if len(row) > 7 and row[7] == "OPEN":
                    result.append({
                        "symbol": row[1],
                        "entry":  float(row[3]),
                        "qty":    float(row[4]),
                        "sl":     float(row[5]),
                        "tp":     float(row[6]),
                    })
            return result
        except Exception as e:
            print(f"[Sheets] get_open_trades: {e}")
            return []

    # ── Bot meta (Fix #8 — pause state) ──────────────────────

    def get_bot_meta(self, key: str) -> str:
        """Read a key from the BotMeta sheet."""
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
        """Write a key/value to the BotMeta sheet."""
        if not self.meta_sheet:
            return
        try:
            rows = self.meta_sheet.get_all_values()
            for i, row in enumerate(rows[1:], start=2):
                if row and row[0] == key:
                    self.meta_sheet.update(f"B{i}", [[value]])
                    return
            # Key not found — append new row
            self.meta_sheet.append_row([key, value])
        except Exception as e:
            print(f"[Sheets] set_bot_meta({key}): {e}")

    @property
    def is_connected(self) -> bool:
        return self.sheet is not None
