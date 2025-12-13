from hyperliquid.info import Info
from hyperliquid.utils import constants
import json
import time
import signal
import sys
import threading
import os

def main():
    """
    Monitor real-time order book updates via WebSocket for specified symbols.
    Useful for analyzing market depth, spread, and liquidity.
    """
    # Initialize Info with skip_ws=False to enable WebSocket
    # Use TESTNET_API_URL for testing, MAINNET_API_URL for mainnet
    print("Connecting to Hyperliquid WebSocket (TESTNET)...")
    info = Info(constants.TESTNET_API_URL, skip_ws=False)
    
    # Counter for updates received
    update_count = 0
    running = True
    
    # Signal handler for immediate shutdown
    def signal_handler(sig, frame):
        print("\n\n🛑 STOPPING - Disconnecting from WebSocket...")
        print(f"Total updates received: {update_count}")
        print("Goodbye!\n")
        # Force immediate exit, bypassing WebSocket cleanup
        os._exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)

    # Define callback to handle received messages
    def handle_update(update):
        nonlocal update_count
        update_count += 1
        
        # Messages from WebSocket arrive as Python dictionary
        if update["channel"] == "l2Book":
            print(f"\n{'='*60}")
            print(f"--- Order Book Update #{update_count} ---")
            print(f"Symbol: {update['data']['coin']}")
            print(f"Time: {update['data']['time']}")

            # Lists are sorted: asks in ascending order, bids in descending order
            asks = update["data"]["levels"][0]  # Asks (sell orders)
            bids = update["data"]["levels"][1]  # Bids (buy orders)

            # Calculate spread
            if bids and asks:
                best_bid = float(bids[0]['px'])
                best_ask = float(asks[0]['px'])
                spread = best_ask - best_bid
                spread_percent = (spread / best_bid) * 100
                
                print(f"\n💰 Spread: ${spread:.2f} ({spread_percent:.4f}%)")
                print(f"   Best Bid: ${best_bid:,.2f}")
                print(f"   Best Ask: ${best_ask:,.2f}")

            print("\n📉 Top 5 Bids (Buy Orders):")
            total_bid_volume = 0
            for i, bid in enumerate(bids[:5], 1):
                volume = float(bid['px']) * float(bid['sz'])
                total_bid_volume += volume
                print(f"  {i}. Price: ${float(bid['px']):,.2f} | "
                      f"Size: {float(bid['sz']):.4f} | "
                      f"Orders: {bid['n']} | "
                      f"Volume: ${volume:,.2f}")
            
            print(f"\n📈 Top 5 Asks (Sell Orders):")
            total_ask_volume = 0
            for i, ask in enumerate(asks[:5], 1):
                volume = float(ask['px']) * float(ask['sz'])
                total_ask_volume += volume
                print(f"  {i}. Price: ${float(ask['px']):,.2f} | "
                      f"Size: {float(ask['sz']):.4f} | "
                      f"Orders: {ask['n']} | "
                      f"Volume: ${volume:,.2f}")
            
            # Volume analysis
            print(f"\n📊 Volume Summary (Top 5):")
            print(f"   Total Bid Volume: ${total_bid_volume:,.2f}")
            print(f"   Total Ask Volume: ${total_ask_volume:,.2f}")
            
            # Imbalance ratio
            if total_ask_volume > 0:
                imbalance = total_bid_volume / total_ask_volume
                print(f"   Bid/Ask Ratio: {imbalance:.2f} ", end="")
                if imbalance > 1.2:
                    print("(🟢 Bullish pressure)")
                elif imbalance < 0.8:
                    print("(🔴 Bearish pressure)")
                else:
                    print("(⚪ Balanced)")

    # Subscribe to order book updates for specific symbols
    # You can subscribe to multiple symbols simultaneously
    symbols = ["BTC", "ETH", "SOL"]
    print(f"Subscribing to order book for: {', '.join(symbols)}")
    print("Press Ctrl+C to stop...")
    
    info.subscribe({"type": "l2Book", "coin": symbols[0]}, handle_update)

    # Keep the program running to receive updates
    print("Monitoring... (Press Ctrl+C to stop immediately)\n")
    try:
        while running:
            time.sleep(0.1)  # Small sleep to prevent CPU spinning
    except Exception as e:
        print(f"\nError: {e}")
        os._exit(1)

if __name__ == "__main__":
    main()
