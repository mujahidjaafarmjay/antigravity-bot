import time
import logging
from pybit.unified_trading import HTTP
import config

class BybitHandler:
    """
    Production-ready Bybit Spot Handler.
    Enforces Spot only, Limit orders, and OCO behavior.
    """

    def __init__(self):
        self.session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET,
        )
        self.category = "spot"
        self.logger = logging.getLogger(__name__)

    def format_quantity(self, qty, step=0.01):
        """Ensures quantity matches Bybit's precision rules."""
        return float(int(float(qty) / step) * step)

    def get_balance(self):
        """Fetches USDT balance across possible account types (Unified, Funding, Spot)."""
        total_balance = 0.0
        account_types = ["UNIFIED", "FUNDING", "SPOT"]
        
        for acc_type in account_types:
            try:
                res = self.session.get_wallet_balance(accountType=acc_type, coin="USDT")
                list_data = res.get('result', {}).get('list', [])
                if not list_data:
                    continue
                
                for coin_data in list_data[0].get('coin', []):
                    if coin_data['coin'] == "USDT":
                        bal = float(coin_data.get('walletBalance', 0) or coin_data.get('equity', 0))
                        total_balance += bal
                        self.logger.info(f"Found {bal} USDT in {acc_type} account.")
            except Exception as e:
                # Silently skip if account type is not supported for this API key
                continue
                
        if total_balance == 0.0:
            self.logger.warning("Total balance is 0.0. Please ensure funds are in Unified, Funding, or Spot account and API key has permissions.")
            
        return total_balance

    def get_ticker(self, symbol):
        """Fetches the latest price for a symbol."""
        try:
            res = self.session.get_tickers(category=self.category, symbol=symbol)
            return float(res['result']['list'][0]['lastPrice'])
        except Exception as e:
            self.logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None

    def get_market_data(self, symbol):
        """Fetches OHLCV and Orderbook data."""
        try:
            # OHLCV
            kline = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=config.TIMEFRAME,
                limit=250
            )
            
            # Orderbook for spread check
            tickers = self.session.get_tickers(category=self.category, symbol=symbol)
            
            import pandas as pd
            self.logger.info(f"DEBUG: First kline candle for {symbol}: {kline['result']['list'][0]}")
            
            df = pd.DataFrame(kline['result']['list'], columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            df = df.astype(float)
            df = df.iloc[::-1] # Reverse to chronological order
            
            ticker = tickers['result']['list'][0]
            bid = float(ticker['bid1Price'])
            ask = float(ticker['ask1Price'])
            
            return df, bid, ask
        except Exception as e:
            self.logger.error(f"Error fetching market data for {symbol}: {e}")
            return None, 0, 0

    def place_market_order(self, symbol, qty, sl, tp):
        """
        Hardened Market Order Execution (Production Debug Version).
        Bypasses price mismatch issues to confirm API and balance connectivity.
        """
        try:
            # 1. Fetch live ticker for metadata (even if Market order doesn't need it for entry)
            tickers = self.session.get_tickers(category=self.category, symbol=symbol)
            ticker = tickers['result']['list'][0]
            price = float(ticker['ask1Price'])

            # 2. Safety Formatting
            qty = self.format_quantity(qty, step=0.01) # Default step for most spot pairs
            
            if qty <= 0:
                return {"success": False, "error": "Invalid formatted qty (0)"}

            # 3. Place LIMIT Order (Hardened)
            res = self.session.place_order(
                category=self.category,
                symbol=symbol,
                side="Buy",
                orderType="Limit",
                qty=str(qty),
                price=str(price),
                timeInForce="GTC", # Good Till Cancelled
                isLeverage=0,
                takeProfit=str(tp),
                stopLoss=str(sl),
                tpOrderType="Limit",
                slOrderType="Market"
            )

            self.logger.info(f"BYBIT RAW RESPONSE: {res}")

            if res.get("retCode") == 0:
                return {
                    "success": True,
                    "order_id": res['result']['orderId'],
                    "price": price,
                    "qty": qty
                }
            else:
                return {
                    "success": False,
                    "error": res.get("retMsg", "Unknown Exchange Error")
                }

        except Exception as e:
            self.logger.error(f"🚨 BYBIT EXCEPTION for {symbol}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_open_orders(self, symbol=None):
        """Fetches active orders."""
        try:
            res = self.session.get_open_orders(category=self.category, symbol=symbol)
            return res.get('result', {}).get('list', [])
        except Exception as e:
            self.logger.error(f"Error fetching open orders: {e}")
            return []

    def cancel_all_orders(self, symbol):
        """Cancels all open orders for a symbol."""
        try:
            self.session.cancel_all_orders(category=self.category, symbol=symbol)
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling orders for {symbol}: {e}")
            return False
