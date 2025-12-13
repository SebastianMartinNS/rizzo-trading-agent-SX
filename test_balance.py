from hyperliquid_trader import HyperLiquidTrader
import os
from dotenv import load_dotenv
import json

load_dotenv()

trader = HyperLiquidTrader(
    secret_key=os.getenv('PRIVATE_KEY'),
    account_address=os.getenv('WALLET_ADDRESS'),
    testnet=True
)

print("=== TESTING ACCOUNT BALANCE ===")
try:
    status = trader.get_account_status()
    print("\nFull account status:")
    print(json.dumps(status, indent=2))
except Exception as e:
    print(f"Error getting account status: {e}")
    import traceback
    traceback.print_exc()

print("\n=== DIRECT API CALL ===")
try:
    user_state = trader.info.user_state(trader.account_address)
    print("\nDirect user_state call:")
    print(json.dumps(user_state, indent=2)[:2000])
except Exception as e:
    print(f"Error with direct call: {e}")
    import traceback
    traceback.print_exc()
