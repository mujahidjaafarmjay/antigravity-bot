# ============================================================
#  risk/manager.py
#  Fix Bug 2: daily limit guard against zero balance.
#  Fix Bug 7: reset_daily_halt exposed for resume command.
# ============================================================
import os
import json
from datetime import date
import config

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DAILY_FILE = os.path.join(BASE_DIR, "..", "logs", "daily_stats.json")


class RiskManager:
    def __init__(self):
        self.risk_per_trade  = config.MAX_RISK_PER_TRADE_PERCENT / 100.0
        self.max_open_trades = config.MAX_OPEN_TRADES
        # Reads from env var via config (Fix Bug 5)
        self.daily_loss_pct  = config.DAILY_LOSS_LIMIT_PERCENT / 100.0
        os.makedirs(os.path.join(BASE_DIR, "..", "logs"), exist_ok=True)

    # ── Position sizing ───────────────────────────────────────

    def calculate_position_size(self, balance: float, entry_price: float,
                                 stop_loss: float) -> float:
        if balance <= 0:
            return -1.0  # signal: balance missing

        if entry_price <= stop_loss or stop_loss <= 0:
            return 0.0

        # Safety: stop must be below entry
        if stop_loss >= entry_price:
            return 0.0

        risk_amount = balance * self.risk_per_trade
        price_risk  = entry_price - stop_loss
        qty         = risk_amount / price_risk

        # Cap at 40% of balance
        max_value = balance * 0.40
        if qty * entry_price > max_value:
            qty = max_value / entry_price

        return round(qty, 6)

    # ── Daily loss tracking ───────────────────────────────────

    def _load_daily(self) -> dict:
        today = str(date.today())
        if os.path.exists(DAILY_FILE):
            try:
                with open(DAILY_FILE) as f:
                    data = json.load(f)
                if data.get("date") == today:
                    return data
            except Exception:
                pass
        fresh = {"date": today, "loss_usdt": 0.0, "trades": 0, "halted": False}
        self._save_daily(fresh)
        return fresh

    def _save_daily(self, data: dict):
        try:
            with open(DAILY_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Risk] Could not save daily stats: {e}")

    def record_pnl(self, pnl_usdt: float):
        data = self._load_daily()
        data["trades"] += 1
        if pnl_usdt < 0:
            data["loss_usdt"] += abs(pnl_usdt)
        self._save_daily(data)

    def is_daily_limit_hit(self, balance: float) -> tuple[bool, str]:
        """
        Fix Bug 2: if balance is 0, return False with a warning.
        Never trigger halt when balance cannot be read —
        that would lock the bot permanently after every restart.
        """
        # Fix Bug 2: guard against zero balance causing false halt
        if balance <= 0:
            return False, "Balance unreadable — skipping daily limit check."

        data  = self._load_daily()
        if data.get("halted"):
            return True, "Daily loss limit already hit. Send /resume to reset."

        limit = balance * self.daily_loss_pct
        lost  = data["loss_usdt"]

        # Only halt if limit > 0 (avoids 0 >= 0 = True bug)
        if limit > 0 and lost >= limit:
            data["halted"] = True
            self._save_daily(data)
            return True, (
                f"Daily loss limit hit: -${lost:.2f} "
                f"(limit ${limit:.2f}). Bot halted for today."
            )

        remaining = max(0.0, limit - lost)
        return False, f"Daily loss: ${lost:.2f} / ${limit:.2f} (${remaining:.2f} remaining)"

    def reset_daily_halt(self):
        """Fix Bug 7: called by resume command to clear halt flag."""
        data = self._load_daily()
        data["halted"]    = False
        data["loss_usdt"] = 0.0
        self._save_daily(data)
        print("[Risk] Daily halt reset.")
