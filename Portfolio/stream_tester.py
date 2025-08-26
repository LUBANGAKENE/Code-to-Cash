import MetaTrader5 as mt5
import time

# 1. Connect to MT5
if not mt5.initialize():
    print("Failed to initialize MT5")
    quit()

while True:
    info = mt5.account_info()
    if info:
        print(f"Balance: {info.balance}, Equity: {info.equity}, Profit: {info.profit}")
    else:
        print("Could not fetch account info")
    time.sleep(5)  # fetch every 5 seconds

mt5.shutdown()
