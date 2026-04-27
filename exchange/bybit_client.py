# ============================================================
#  exchange/bybit_client.py  — corrections_v3
#  Fix BALANCE: Try all account types (UNIFIED, SPOT, FUND).
#              Never break early on empty coin list.
#              SPOT accounts only have balance under "SPOT" type.
#  Fix v3: detailed per-account-type debug logging so Render
#          logs show exactly what Bybit returns, making it
#          trivial to diagnose API key permission issues.
# ============================================================
import time
import math
from pybit.unified_trading import HTTP
import config


class BybitClient:
    def __init__(self):
        self.session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET,
            domain="bytick",
            timeout=30,
            recv_window=20000,
        )
        self.category   = "spot"
        self.precisions = {}
        print(f"[Bybit] Mode: {config.MODE.upper()} | Testnet: {config.TESTNET}")

    # ── Balance ───────────────────────────────────────────────
    def get_balance(self, coin: str = "USDT") -> tuple[float, str]:
        """
        Fix BALANCE: Try UNIFIED, SPOT, FUND in order.
        v3: Returns (balance, error_message) so main.py can send the exact error to Telegram.
        """
        errors = []
        for acc_type in ["UNIFIED", "SPOT", "FUND"]:
            try:
                resp = self.session.get_wallet_balance(
                    accountType=acc_type, coin=coin
                )
                ret_code = resp.get("retCode", -1)
                ret_msg  = resp.get("retMsg", "unknown")

                if ret_code != 0:
                    errors.append(f"{acc_type}: {ret_msg}")
                    continue

                list_data = resp["result"].get("list", [])
                if not list_data:
                    errors.append(f"{acc_type}: empty list")
                    continue

                for item in list_data[0].get("coin", []):
                    if item["coin"] == coin:
                        val = float(item.get("walletBalance") or
                                    item.get("availableToWithdraw") or
                                    item.get("equity") or 0)
                        if val > 0:
                            return val, "OK"
                errors.append(f"{acc_type}: 0 balance")
                continue

            except Exception as e:
                errors.append(f"{acc_type} Exception: {str(e)[:50]}")
                continue

        err_str = " | ".join(errors) if errors else "Unknown API error"
        return 0.0, err_str

    # ── Candles ───────────────────────────────────────────────
    def get_candles(self, symbol: str, interval: str, limit: int = 250) -> list:
        """Fetch OHLCV. Returns newest-first (brain.py sorts ascending)."""
        try:
            resp = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            if resp.get("retCode") == 0:
                return resp["result"]["list"]
            return []
        except Exception as e:
            print(f"[Candles] {symbol}/{interval}: {e}")
            return []

    # ── Ticker ────────────────────────────────────────────────
    def get_ticker(self, symbol: str) -> float | None:
        try:
            resp = self.session.get_tickers(
                category=self.category, symbol=symbol
            )
            if resp.get("retCode") == 0:
                return float(resp["result"]["list"][0]["lastPrice"])
            return None
        except Exception as e:
            print(f"[Ticker] {symbol}: {e}")
            return None

    # ── Order placement ───────────────────────────────────────
    def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = None,
        order_type: str = "Market",
    ) -> dict:
        if config.MODE == "paper":
            fake_id = f"paper_{int(time.time())}"
            print(f"[PAPER] {side} {qty} {symbol} → {fake_id}")
            return {"retCode": 0, "result": {"orderId": fake_id}}

        try:
            if symbol not in self.precisions:
                r = self.session.get_instruments_info(
                    category=self.category, symbol=symbol
                )
                if r.get("retCode") == 0:
                    step = r["result"]["list"][0]["lotSizeFilter"]["basePrecision"]
                    self.precisions[symbol] = step
                else:
                    self.precisions[symbol] = "0.01"

            step_str = self.precisions[symbol]
            if "." in step_str:
                decimals = len(step_str.rstrip("0").split(".")[1])
                factor   = 10 ** decimals
                qty      = math.floor(qty * factor) / factor
            else:
                qty = int(qty)

            params = {
                "category":    self.category,
                "symbol":      symbol,
                "side":        side,
                "orderType":   order_type,
                "qty":         str(qty),
                "timeInForce": "GTC",
            }
            if price:
                params["price"] = str(price)

            result = self.session.place_order(**params)
            if result.get("retCode") == 0:
                print(f"[Order] {side} {qty} {symbol} placed ✓")
            else:
                print(f"[Order] {side} {symbol} failed: {result.get('retMsg')}")
            return result

        except Exception as e:
            print(f"[Order] {symbol}: {e}")
            return {"retCode": -1, "retMsg": str(e)}
