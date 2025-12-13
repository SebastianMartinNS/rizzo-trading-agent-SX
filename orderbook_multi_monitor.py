from hyperliquid.info import Info
from hyperliquid.utils import constants
import time
import signal
import sys
import os

def main():
    """
    Monitor multiple symbols simultaneously via WebSocket.
    Tracks order book for BTC, ETH, and SOL in real-time.
    """
    print("🚀 Starting Multi-Symbol Order Book Monitor (TESTNET)")
    print("="*60)
    
    info = Info(constants.TESTNET_API_URL, skip_ws=False)
    
    # Track updates per symbol
    symbol_updates = {"BTC": 0, "ETH": 0, "SOL": 0}
    running = True
    
    # Signal handler for immediate shutdown
    def signal_handler(sig, frame):
        print(f"\n\n🛑 STOPPING - Disconnecting from WebSocket...")
        print(f"\nTotal updates received:")
        for symbol, count in symbol_updates.items():
            print(f"  {symbol}: {count} updates")
        print("\nGoodbye!\n")
        # Force immediate exit, bypassing WebSocket cleanup
        os._exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    def handle_update(update):
        if update["channel"] == "l2Book":
            coin = update['data']['coin']
            symbol_updates[coin] = symbol_updates.get(coin, 0) + 1
            
            asks = update["data"]["levels"][0]
            bids = update["data"]["levels"][1]
            
            if bids and asks:
                best_bid = float(bids[0]['px'])
                best_ask = float(asks[0]['px'])
                spread = best_ask - best_bid
                
                # Calculate volumes
                bid_vol = sum(float(b['px']) * float(b['sz']) for b in bids[:5])
                ask_vol = sum(float(a['px']) * float(a['sz']) for a in asks[:5])
                ratio = bid_vol / ask_vol if ask_vol > 0 else 0
                
                # Determine sentiment
                sentiment = "🟢 BULLISH" if ratio > 1.2 else "🔴 BEARISH" if ratio < 0.8 else "⚪ NEUTRAL"
                
                print(f"\n[{coin} #{symbol_updates[coin]}] "
                      f"Bid: ${best_bid:,.2f} | Ask: ${best_ask:,.2f} | "
                      f"Spread: ${spread:.2f} | Ratio: {ratio:.2f} {sentiment}")
    
    # Subscribe to multiple symbols
    symbols = ["BTC", "ETH", "SOL"]
    print(f"\n📊 Monitoring: {', '.join(symbols)}")
    print("Press Ctrl+C to stop...\n")
    
    for symbol in symbols:
        info.subscribe({"type": "l2Book", "coin": symbol}, handle_update)
        time.sleep(0.1)  # Small delay between subscriptions
    
    print("\nMonitoring... (Press Ctrl+C to stop immediately)\n")
    try:
        while running:
            time.sleep(1)
    except Exception as e:
        print(f"\nError: {e}")
        os._exit(1)

if __name__ == "__main__":
    main()
