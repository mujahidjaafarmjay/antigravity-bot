# ============================================================
#  exchange/bybit_client.py
#  Fix #3: limit=250 so MA200 has enough data
#  Fix #9: removed duplicate BybitClient from command_handler
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
        )
        self.category  = "spot"
        self.precisions = {}

    # ── Balance ───────────────────────────────────────────────
    def get_balance(self, coin="USDT") -> float:
        for acc_type in ["UNIFIED", "FUND", "SPOT"]:
            for attempt in range(3):
                try:
                    resp = self.session.get_wallet_balance(
                        accountType=acc_type, coin=coin
                    )
                    if resp["retCode"] == 0:
                        list_data = resp["result"].get("list", [])
                        if not list_data:
                            break
                        for item in list_data[0].get("coin", []):
                            if item["coin"] == coin:
                                val = float(
                                    item.get("walletBalance", 0)
                                    or item.get("equity", 0)
                                )
                                if val > 0:
                                    return val
                        break
                except Exception as e:
                    err = str(e)
                    if "timed out" in err.lower() or "Connection" in err:
                        print(f"[Balance] timeout {acc_type} attempt {attempt+1}")
                        time.sleep(5)
                    else:
                        print(f"[Balance] {acc_type}: {e}")
                        break
        return 0.0

    # ── Candles ───────────────────────────────────────────────
    def get_candles(self, symbol: str, interval: str, limit: int = 250):
        """
        Fetch OHLCV candles.
        Fix #3: default limit=250 (was 100) so MA200 has enough history.
        Bybit returns newest-first — sorting is done in brain.py.
        """
        try:
            resp = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit,       # Fix #3
            )
            if resp["retCode"] == 0:
                return resp["result"]["list"]
            return []
        except Exception as e:
            print(f"[Candles] {symbol}: {e}")
            return []

    # ── Ticker ────────────────────────────────────────────────
    def get_ticker(self, symbol: str) -> float | None:
        try:
            resp = self.session.get_tickers(
                category=self.category, symbol=symbol
            )
            if resp["retCode"] == 0:
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
            print(f"[PAPER] {side} {qty} {symbol}")
            return {"retCode": 0, "result": {"orderId": f"paper_{int(time.time())}"}}

        try:
            # Get and cache precision
            if symbol not in self.precisions:
                r = self.session.get_instruments_info(
                    category=self.category, symbol=symbol
                )
                if r["retCode"] == 0:
                    step = r["result"]["list"][0]["lotSizeFilter"]["basePrecision"]
                    self.precisions[symbol] = step
                else:
                    self.precisions[symbol] = "0.01"

            step_str = self.precisions[symbol]
            if "." in step_str:
                decimals = len(step_str.split(".")[1])
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

            return self.session.place_order(**params)
        except Exception as e:
            print(f"[Order] {symbol}: {e}")
            return {"retCode": -1, "retMsg": str(e)}
