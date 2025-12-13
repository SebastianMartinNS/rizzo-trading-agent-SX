from hyperliquid.info import Info
from hyperliquid.utils import constants
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import signal
import os
from collections import deque
from datetime import datetime

class OrderBookVisualizer:
    def __init__(self, symbol="BTC", testnet=True):
        self.symbol = symbol
        self.info = Info(constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL, skip_ws=False)
        
        # Store historical data
        self.max_history = 100
        self.timestamps = deque(maxlen=self.max_history)
        self.spreads = deque(maxlen=self.max_history)
        self.bid_volumes = deque(maxlen=self.max_history)
        self.ask_volumes = deque(maxlen=self.max_history)
        self.best_bids = deque(maxlen=self.max_history)
        self.best_asks = deque(maxlen=self.max_history)
        
        # Current order book state
        self.current_bids = []
        self.current_asks = []
        self.update_count = 0
        self.running = True
        
        # Create figure
        self.fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                'Order Book Depth (Real-time)', 'Spread History',
                'Bid vs Ask Volume', 'Best Bid/Ask Price',
                'Volume Imbalance Ratio', 'Order Book Updates'
            ),
            specs=[
                [{"type": "bar"}, {"type": "scatter"}],
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "scatter"}, {"type": "indicator"}]
            ],
            vertical_spacing=0.12,
            horizontal_spacing=0.12
        )
        
        # Setup signal handler
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, sig, frame):
        print(f"\n\n🛑 STOPPING - Closing visualization...")
        print(f"Total updates received: {self.update_count}")
        self.running = False
        os._exit(0)
    
    def handle_update(self, update):
        if update["channel"] == "l2Book" and update['data']['coin'] == self.symbol:
            self.update_count += 1
            
            asks = update["data"]["levels"][0]
            bids = update["data"]["levels"][1]
            
            if not bids or not asks:
                return
            
            # Store current order book
            self.current_bids = bids[:10]
            self.current_asks = asks[:10]
            
            # Calculate metrics
            best_bid = float(bids[0]['px'])
            best_ask = float(asks[0]['px'])
            spread = best_ask - best_bid
            
            bid_vol = sum(float(b['px']) * float(b['sz']) for b in bids[:10])
            ask_vol = sum(float(a['px']) * float(a['sz']) for a in asks[:10])
            
            # Store historical data
            current_time = datetime.now()
            self.timestamps.append(current_time)
            self.spreads.append(spread)
            self.bid_volumes.append(bid_vol)
            self.ask_volumes.append(ask_vol)
            self.best_bids.append(best_bid)
            self.best_asks.append(best_ask)
            
            # Update visualization every 5 updates to avoid lag
            if self.update_count % 5 == 0:
                self.update_plots()
    
    def update_plots(self):
        # Clear all traces
        self.fig.data = []
        
        # 1. Order Book Depth (Bar chart)
        bid_prices = [float(b['px']) for b in self.current_bids]
        bid_sizes = [float(b['sz']) for b in self.current_bids]
        ask_prices = [float(a['px']) for a in self.current_asks]
        ask_sizes = [float(a['sz']) for a in self.current_asks]
        
        self.fig.add_trace(
            go.Bar(x=bid_prices, y=bid_sizes, name='Bids', marker_color='green', orientation='v'),
            row=1, col=1
        )
        self.fig.add_trace(
            go.Bar(x=ask_prices, y=ask_sizes, name='Asks', marker_color='red', orientation='v'),
            row=1, col=1
        )
        
        # 2. Spread History
        if len(self.timestamps) > 0:
            self.fig.add_trace(
                go.Scatter(x=list(self.timestamps), y=list(self.spreads), 
                          name='Spread', line=dict(color='purple', width=2)),
                row=1, col=2
            )
        
        # 3. Bid vs Ask Volume
        if len(self.timestamps) > 0:
            self.fig.add_trace(
                go.Scatter(x=list(self.timestamps), y=list(self.bid_volumes), 
                          name='Bid Volume', line=dict(color='green', width=2)),
                row=2, col=1
            )
            self.fig.add_trace(
                go.Scatter(x=list(self.timestamps), y=list(self.ask_volumes), 
                          name='Ask Volume', line=dict(color='red', width=2)),
                row=2, col=1
            )
        
        # 4. Best Bid/Ask Price
        if len(self.timestamps) > 0:
            self.fig.add_trace(
                go.Scatter(x=list(self.timestamps), y=list(self.best_bids), 
                          name='Best Bid', line=dict(color='green', width=2)),
                row=2, col=2
            )
            self.fig.add_trace(
                go.Scatter(x=list(self.timestamps), y=list(self.best_asks), 
                          name='Best Ask', line=dict(color='red', width=2)),
                row=2, col=2
            )
        
        # 5. Volume Imbalance Ratio
        if len(self.timestamps) > 0:
            ratios = [b/a if a > 0 else 0 for b, a in zip(self.bid_volumes, self.ask_volumes)]
            self.fig.add_trace(
                go.Scatter(x=list(self.timestamps), y=ratios, 
                          name='Bid/Ask Ratio', line=dict(color='blue', width=2),
                          fill='tozeroy'),
                row=3, col=1
            )
            # Add threshold lines
            self.fig.add_hline(y=1.2, line_dash="dash", line_color="green", 
                             annotation_text="Bullish", row=3, col=1)
            self.fig.add_hline(y=0.8, line_dash="dash", line_color="red", 
                             annotation_text="Bearish", row=3, col=1)
        
        # 6. Update Counter (Indicator)
        self.fig.add_trace(
            go.Indicator(
                mode="number+delta",
                value=self.update_count,
                title={'text': f"{self.symbol} Updates"},
                delta={'reference': self.update_count - 1},
                domain={'x': [0, 1], 'y': [0, 1]}
            ),
            row=3, col=2
        )
        
        # Update layout
        self.fig.update_xaxes(title_text="Price ($)", row=1, col=1)
        self.fig.update_yaxes(title_text="Size", row=1, col=1)
        self.fig.update_xaxes(title_text="Time", row=1, col=2)
        self.fig.update_yaxes(title_text="Spread ($)", row=1, col=2)
        self.fig.update_xaxes(title_text="Time", row=2, col=1)
        self.fig.update_yaxes(title_text="Volume ($)", row=2, col=1)
        self.fig.update_xaxes(title_text="Time", row=2, col=2)
        self.fig.update_yaxes(title_text="Price ($)", row=2, col=2)
        self.fig.update_xaxes(title_text="Time", row=3, col=1)
        self.fig.update_yaxes(title_text="Ratio", row=3, col=1)
        
        self.fig.update_layout(
            title_text=f"{self.symbol} Order Book Live Monitor (TESTNET)",
            showlegend=True,
            height=1000,
            hovermode='x unified'
        )
    
    def start(self):
        print(f"🚀 Starting Order Book Visualizer for {self.symbol}")
        print("Opening browser window...")
        print("Press Ctrl+C to stop\n")
        
        # Subscribe to WebSocket
        self.info.subscribe({"type": "l2Book", "coin": self.symbol}, self.handle_update)
        
        # Initial plot
        time.sleep(2)  # Wait for some data
        
        # Open in browser with auto-refresh
        self.fig.show()
        
        # Keep updating
        try:
            while self.running:
                time.sleep(1)
        except Exception as e:
            print(f"\nError: {e}")
            os._exit(1)

def main():
    import sys
    
    # Get symbol from command line or use default
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    
    visualizer = OrderBookVisualizer(symbol=symbol, testnet=True)
    visualizer.start()

if __name__ == "__main__":
    main()
