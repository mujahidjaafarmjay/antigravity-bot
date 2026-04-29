import time
from pybit.unified_trading import HTTP

api_key = "Rz6WNnNhGkaVhr6XkE"
api_secret = "sSfXEnAnb4moWCS1LELM83mszroSygPITnh0"

session = HTTP(
    testnet=False,
    api_key=api_key,
    api_secret=api_secret,
    domain="bytick",
    timeout=10,
)

print("Testing Bybit API Key...")

for acc_type in ["UNIFIED", "SPOT", "FUND"]:
    try:
        resp = session.get_wallet_balance(accountType=acc_type, coin="USDT")
        retCode = resp.get("retCode")
        retMsg = resp.get("retMsg")
        print(f"[{acc_type}] retCode: {retCode}, retMsg: {retMsg}")
        if retCode == 0:
            print("Response:", resp["result"].get("list", []))
    except Exception as e:
        print(f"[{acc_type}] Error:", e)

try:
    resp = session.get_api_key_information()
    print("API Key Info:")
    print(resp.get("result", {}))
except Exception as e:
    print("API Info Error:", e)
