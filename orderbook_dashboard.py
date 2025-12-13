"""
Real-time Order Book Dashboard with Dash
Run this for a live updating web dashboard
"""
from hyperliquid.info import Info
from hyperliquid.utils import constants
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from collections import deque
from datetime import datetime
import threading
import signal
import os
import numpy as np

# Global data storage
class OrderBookData:
    def __init__(self, symbol="BTC", testnet=False):
        self.symbol = symbol
        self.testnet = testnet
        self.info = Info(constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL, skip_ws=False)
        
        self.max_history = 100
        self.timestamps = deque(maxlen=self.max_history)
        self.spreads = deque(maxlen=self.max_history)
        self.spread_percents = deque(maxlen=self.max_history)
        self.bid_volumes = deque(maxlen=self.max_history)
        self.ask_volumes = deque(maxlen=self.max_history)
        self.best_bids = deque(maxlen=self.max_history)
        self.best_asks = deque(maxlen=self.max_history)
        self.mid_prices = deque(maxlen=self.max_history)
        self.total_bid_orders = deque(maxlen=self.max_history)
        self.total_ask_orders = deque(maxlen=self.max_history)
        self.price_changes = deque(maxlen=self.max_history)
        self.volatility = deque(maxlen=self.max_history)
        
        self.current_bids = []
        self.current_asks = []
        self.update_count = 0
        self.last_update_time = None
        self.updates_per_second = 0
        self.last_second_updates = deque(maxlen=100)
        
    def handle_update(self, update):
        if update["channel"] == "l2Book" and update['data']['coin'] == self.symbol:
            self.update_count += 1
            
            asks = update["data"]["levels"][0]
            bids = update["data"]["levels"][1]
            
            if not bids or not asks:
                return
            
            self.current_bids = bids[:20]
            self.current_asks = asks[:20]
            
            best_bid = float(bids[0]['px'])
            best_ask = float(asks[0]['px'])
            spread = best_ask - best_bid
            spread_percent = (spread / best_bid) * 100
            mid_price = (best_bid + best_ask) / 2
            
            bid_vol = sum(float(b['px']) * float(b['sz']) for b in bids[:15])
            ask_vol = sum(float(a['px']) * float(a['sz']) for a in asks[:15])
            
            total_bid_orders = sum(int(b['n']) for b in bids[:15])
            total_ask_orders = sum(int(a['n']) for a in asks[:15])
            
            current_time = datetime.now()
            
            # Calculate price change
            price_change = 0
            if len(self.mid_prices) > 0:
                price_change = ((mid_price - self.mid_prices[-1]) / self.mid_prices[-1]) * 100
            
            # Calculate volatility (rolling std of last 20 mid prices)
            vol = 0
            if len(self.mid_prices) >= 20:
                recent_prices = list(self.mid_prices)[-20:]
                vol = np.std(recent_prices)
            
            # Updates per second calculation
            self.last_second_updates.append(current_time)
            recent_updates = [t for t in self.last_second_updates if (current_time - t).total_seconds() <= 1]
            self.updates_per_second = len(recent_updates)
            
            self.timestamps.append(current_time)
            self.spreads.append(spread)
            self.spread_percents.append(spread_percent)
            self.bid_volumes.append(bid_vol)
            self.ask_volumes.append(ask_vol)
            self.best_bids.append(best_bid)
            self.best_asks.append(best_ask)
            self.mid_prices.append(mid_price)
            self.total_bid_orders.append(total_bid_orders)
            self.total_ask_orders.append(total_ask_orders)
            self.price_changes.append(price_change)
            self.volatility.append(vol)
            self.last_update_time = current_time
    
    def change_symbol(self, new_symbol):
        """Change the tracked symbol"""
        if new_symbol != self.symbol:
            self.symbol = new_symbol
            # Clear history
            self.timestamps.clear()
            self.spreads.clear()
            self.spread_percents.clear()
            self.bid_volumes.clear()
            self.ask_volumes.clear()
            self.best_bids.clear()
            self.best_asks.clear()
            self.mid_prices.clear()
            self.total_bid_orders.clear()
            self.total_ask_orders.clear()
            self.price_changes.clear()
            self.volatility.clear()
            self.current_bids = []
            self.current_asks = []
            self.update_count = 0
            return True
        return False
    
    def start_websocket(self):
        self.info.subscribe({"type": "l2Book", "coin": self.symbol}, self.handle_update)

# Global variables
data_store = {}
current_symbol = "BTC"

def get_data(symbol):
    """Get or create data object for symbol"""
    if symbol not in data_store:
        data_store[symbol] = OrderBookData(symbol=symbol, testnet=False)
        ws_thread = threading.Thread(target=data_store[symbol].start_websocket, daemon=True)
        ws_thread.start()
    return data_store[symbol]

# Initialize with default symbol
data = get_data(current_symbol)

# Create Dash app
app = dash.Dash(__name__)
app.title = "Rizzo Order Book Monitor"

app.layout = html.Div([
    html.Div([
        html.Div([
            html.H1("🚀 Rizzo Trading Agent - Order Book Monitor", 
                    style={'textAlign': 'center', 'color': '#2c3e50', 'margin': '0'}),
            html.H3(id='symbol-display',
                    style={'textAlign': 'center', 'color': '#e74c3c', 'fontWeight': 'bold', 'margin': '10px 0'}),
        ], style={'flex': '1'}),
        
        html.Div([
            html.Label("Select Symbol:", style={'fontWeight': 'bold', 'marginRight': '10px'}),
            dcc.Dropdown(
                id='symbol-dropdown',
                options=[
                    {'label': '₿ BTC - Bitcoin', 'value': 'BTC'},
                    {'label': 'Ξ ETH - Ethereum', 'value': 'ETH'},
                    {'label': '◎ SOL - Solana', 'value': 'SOL'},
                    {'label': '🔺 AVAX - Avalanche', 'value': 'AVAX'},
                    {'label': '⬡ MATIC - Polygon', 'value': 'MATIC'},
                    {'label': '🔷 ARB - Arbitrum', 'value': 'ARB'},
                    {'label': '⚫ OP - Optimism', 'value': 'OP'},
                    {'label': '🔴 ATOM - Cosmos', 'value': 'ATOM'},
                ],
                value='BTC',
                clearable=False,
                style={'width': '250px'}
            ),
        ], style={'position': 'absolute', 'right': '20px', 'top': '20px'}),
    ], style={'backgroundColor': '#ecf0f1', 'padding': '20px', 'position': 'relative'}),
    
    html.Div([
        html.Div([
            html.H4("📊 Updates/sec", style={'textAlign': 'center', 'margin': '5px'}),
            html.H2(id='update-counter', style={'textAlign': 'center', 'color': '#3498db', 'margin': '5px'})
        ], className='metric-box', style={'flex': 1, 'margin': '10px', 'padding': '15px', 
                                          'backgroundColor': 'white', 'borderRadius': '10px',
                                          'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("💰 Mid Price", style={'textAlign': 'center', 'margin': '5px'}),
            html.H2(id='mid-price', style={'textAlign': 'center', 'color': '#9b59b6', 'margin': '5px'})
        ], className='metric-box', style={'flex': 1, 'margin': '10px', 'padding': '15px',
                                          'backgroundColor': 'white', 'borderRadius': '10px',
                                          'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("📏 Spread", style={'textAlign': 'center', 'margin': '5px'}),
            html.H2(id='current-spread', style={'textAlign': 'center', 'color': '#e74c3c', 'margin': '5px'})
        ], className='metric-box', style={'flex': 1, 'margin': '10px', 'padding': '15px',
                                          'backgroundColor': 'white', 'borderRadius': '10px',
                                          'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("📈 Bid/Ask Ratio", style={'textAlign': 'center', 'margin': '5px'}),
            html.H2(id='volume-ratio', style={'textAlign': 'center', 'color': '#2ecc71', 'margin': '5px'})
        ], className='metric-box', style={'flex': 1, 'margin': '10px', 'padding': '15px',
                                          'backgroundColor': 'white', 'borderRadius': '10px',
                                          'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("📊 Total Orders", style={'textAlign': 'center', 'margin': '5px'}),
            html.H2(id='total-orders', style={'textAlign': 'center', 'color': '#f39c12', 'margin': '5px'})
        ], className='metric-box', style={'flex': 1, 'margin': '10px', 'padding': '15px',
                                          'backgroundColor': 'white', 'borderRadius': '10px',
                                          'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("⚡ Price Change", style={'textAlign': 'center', 'margin': '5px'}),
            html.H2(id='price-change', style={'textAlign': 'center', 'margin': '5px'})
        ], className='metric-box', style={'flex': 1, 'margin': '10px', 'padding': '15px',
                                          'backgroundColor': 'white', 'borderRadius': '10px',
                                          'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'}),
    ], style={'display': 'flex', 'justifyContent': 'space-around', 'margin': '20px', 'flexWrap': 'wrap'}),
    
    dcc.Graph(id='orderbook-graph', style={'height': '400px'}),
    dcc.Graph(id='metrics-graph', style={'height': '600px'}),
    
    dcc.Interval(
        id='interval-component',
        interval=200,  # Update every 200ms for ultra-fast refresh
        n_intervals=0
    ),
    
    dcc.Store(id='current-symbol-store', data='BTC'),
    
    html.Div([
        html.P(f"Last update: ", style={'display': 'inline', 'color': '#95a5a6'}),
        html.Span(id='last-update', style={'display': 'inline', 'color': '#34495e', 'fontWeight': 'bold'})
    ], style={'textAlign': 'center', 'padding': '10px'})
    
], style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh', 'padding': '20px'})

@app.callback(
    Output('current-symbol-store', 'data'),
    Input('symbol-dropdown', 'value'),
    prevent_initial_call=True
)
def update_symbol_store(symbol):
    return symbol

@app.callback(
    [Output('symbol-display', 'children'),
     Output('update-counter', 'children'),
     Output('mid-price', 'children'),
     Output('current-spread', 'children'),
     Output('volume-ratio', 'children'),
     Output('total-orders', 'children'),
     Output('price-change', 'children'),
     Output('price-change', 'style'),
     Output('last-update', 'children'),
     Output('orderbook-graph', 'figure'),
     Output('metrics-graph', 'figure')],
    [Input('interval-component', 'n_intervals'),
     Input('current-symbol-store', 'data')]
)
def update_dashboard(n, selected_symbol):
    # Get data for selected symbol
    data = get_data(selected_symbol)
    # Symbol display
    symbol_text = f"{data.symbol} (🔴 MAINNET LIVE)"
    
    # Metrics
    update_text = f"{data.updates_per_second}/s"
    if data.update_count > 0:
        update_text += f"\n({data.update_count:,} total)"
    
    mid_price_text = "N/A"
    if len(data.mid_prices) > 0:
        mid_price_text = f"${data.mid_prices[-1]:,.2f}"
    
    spread_text = "N/A"
    if len(data.spreads) > 0 and len(data.spread_percents) > 0:
        current_spread = data.spreads[-1]
        spread_pct = data.spread_percents[-1]
        spread_text = f"${current_spread:.2f}\n({spread_pct:.4f}%)"
    
    ratio_text = "N/A"
    sentiment = ""
    if len(data.bid_volumes) > 0 and len(data.ask_volumes) > 0:
        ratio = data.bid_volumes[-1] / data.ask_volumes[-1] if data.ask_volumes[-1] > 0 else 0
        ratio_text = f"{ratio:.2f}x"
        if ratio > 1.2:
            sentiment = " 🟢"
        elif ratio < 0.8:
            sentiment = " 🔴"
        else:
            sentiment = " ⚪"
        ratio_text += sentiment
    
    orders_text = "N/A"
    if len(data.total_bid_orders) > 0 and len(data.total_ask_orders) > 0:
        bid_orders = data.total_bid_orders[-1]
        ask_orders = data.total_ask_orders[-1]
        orders_text = f"B:{bid_orders} A:{ask_orders}"
    
    price_change_text = "N/A"
    price_change_style = {'textAlign': 'center', 'margin': '5px', 'color': '#34495e'}
    if len(data.price_changes) > 0:
        change = data.price_changes[-1]
        price_change_text = f"{change:+.4f}%"
        if change > 0:
            price_change_style['color'] = '#27ae60'
        elif change < 0:
            price_change_style['color'] = '#e74c3c'
    
    last_update_text = data.last_update_time.strftime('%H:%M:%S.%f')[:-3] if data.last_update_time else "Waiting..."
    
    # Order Book Depth Chart
    orderbook_fig = go.Figure()
    
    if data.current_bids and data.current_asks:
        bid_prices = [float(b['px']) for b in data.current_bids]
        bid_sizes = [float(b['sz']) for b in data.current_bids]
        bid_orders = [int(b['n']) for b in data.current_bids]
        ask_prices = [float(a['px']) for a in data.current_asks]
        ask_sizes = [float(a['sz']) for a in data.current_asks]
        ask_orders = [int(a['n']) for a in data.current_asks]
        
        orderbook_fig.add_trace(go.Bar(
            x=bid_prices,
            y=bid_sizes,
            name='Bids',
            marker_color='rgba(46, 204, 113, 0.7)',
            hovertemplate='<b>Bid</b><br>Price: $%{x:,.2f}<br>Size: %{y:.4f}<br>Orders: ' + 
                         '<br>Orders: '.join([str(o) for o in bid_orders]) + '<extra></extra>',
            text=[f'{o}' for o in bid_orders],
            textposition='outside'
        ))
        
        orderbook_fig.add_trace(go.Bar(
            x=ask_prices,
            y=ask_sizes,
            name='Asks',
            marker_color='rgba(231, 76, 60, 0.7)',
            hovertemplate='<b>Ask</b><br>Price: $%{x:,.2f}<br>Size: %{y:.4f}<br>Orders: ' +
                         '<br>Orders: '.join([str(o) for o in ask_orders]) + '<extra></extra>',
            text=[f'{o}' for o in ask_orders],
            textposition='outside'
        ))
    
    orderbook_fig.update_layout(
        title=f"{data.symbol} Order Book Depth (Top 20 Levels)",
        xaxis_title="Price ($)",
        yaxis_title="Size",
        barmode='group',
        hovermode='closest',
        template='plotly_white',
        showlegend=True,
        height=450
    )
    
    # Metrics Charts
    metrics_fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=('Mid Price & Volatility', 'Spread & Spread %', 
                       'Bid vs Ask Volume', 'Volume Imbalance Ratio',
                       'Total Orders (Bid vs Ask)', 'Price Momentum'),
        vertical_spacing=0.10,
        horizontal_spacing=0.12,
        specs=[[{"secondary_y": True}, {"secondary_y": True}],
               [{"secondary_y": False}, {"secondary_y": False}],
               [{"secondary_y": False}, {"secondary_y": False}]]
    )
    
    if len(data.timestamps) > 0:
        # 1. Mid Price & Volatility
        metrics_fig.add_trace(
            go.Scatter(x=list(data.timestamps), y=list(data.mid_prices),
                      name='Mid Price', line=dict(color='#9b59b6', width=3)),
            row=1, col=1, secondary_y=False
        )
        if len(data.volatility) > 0:
            metrics_fig.add_trace(
                go.Scatter(x=list(data.timestamps), y=list(data.volatility),
                          name='Volatility', line=dict(color='orange', width=2, dash='dot'),
                          fill='tozeroy', opacity=0.3),
                row=1, col=1, secondary_y=True
            )
        
        # 2. Spread & Spread %
        metrics_fig.add_trace(
            go.Scatter(x=list(data.timestamps), y=list(data.spreads),
                      name='Spread ($)', line=dict(color='purple', width=2),
                      fill='tozeroy'),
            row=1, col=2, secondary_y=False
        )
        if len(data.spread_percents) > 0:
            metrics_fig.add_trace(
                go.Scatter(x=list(data.timestamps), y=list(data.spread_percents),
                          name='Spread %', line=dict(color='red', width=2, dash='dash')),
                row=1, col=2, secondary_y=True
            )
        
        # 3. Volume
        metrics_fig.add_trace(
            go.Scatter(x=list(data.timestamps), y=list(data.bid_volumes),
                      name='Bid Vol', line=dict(color='#27ae60', width=2),
                      fill='tozeroy'),
            row=2, col=1
        )
        metrics_fig.add_trace(
            go.Scatter(x=list(data.timestamps), y=list(data.ask_volumes),
                      name='Ask Vol', line=dict(color='#e74c3c', width=2),
                      fill='tozeroy'),
            row=2, col=1
        )
        
        # 4. Ratio
        ratios = [b/a if a > 0 else 0 for b, a in zip(data.bid_volumes, data.ask_volumes)]
        metrics_fig.add_trace(
            go.Scatter(x=list(data.timestamps), y=ratios,
                      name='Ratio', line=dict(color='#3498db', width=3),
                      fill='tozeroy'),
            row=2, col=2
        )
        metrics_fig.add_hline(y=1.2, line_dash="dash", line_color="green", 
                             annotation_text="Bullish", row=2, col=2)
        metrics_fig.add_hline(y=0.8, line_dash="dash", line_color="red",
                             annotation_text="Bearish", row=2, col=2)
        metrics_fig.add_hline(y=1.0, line_dash="dot", line_color="gray", row=2, col=2)
        
        # 5. Total Orders
        metrics_fig.add_trace(
            go.Scatter(x=list(data.timestamps), y=list(data.total_bid_orders),
                      name='Bid Orders', line=dict(color='#27ae60', width=2),
                      mode='lines+markers'),
            row=3, col=1
        )
        metrics_fig.add_trace(
            go.Scatter(x=list(data.timestamps), y=list(data.total_ask_orders),
                      name='Ask Orders', line=dict(color='#e74c3c', width=2),
                      mode='lines+markers'),
            row=3, col=1
        )
        
        # 6. Price Momentum
        if len(data.price_changes) > 0:
            colors = ['green' if x > 0 else 'red' for x in data.price_changes]
            metrics_fig.add_trace(
                go.Bar(x=list(data.timestamps), y=list(data.price_changes),
                      name='Price Change %', marker_color=colors),
                row=3, col=2
            )
            metrics_fig.add_hline(y=0, line_color="black", row=3, col=2)
    
    metrics_fig.update_xaxes(title_text="Time", row=1, col=1)
    metrics_fig.update_yaxes(title_text="Mid Price ($)", row=1, col=1, secondary_y=False)
    metrics_fig.update_yaxes(title_text="Volatility", row=1, col=1, secondary_y=True)
    
    metrics_fig.update_xaxes(title_text="Time", row=1, col=2)
    metrics_fig.update_yaxes(title_text="Spread ($)", row=1, col=2, secondary_y=False)
    metrics_fig.update_yaxes(title_text="Spread %", row=1, col=2, secondary_y=True)
    
    metrics_fig.update_xaxes(title_text="Time", row=2, col=1)
    metrics_fig.update_yaxes(title_text="Volume ($)", row=2, col=1)
    
    metrics_fig.update_xaxes(title_text="Time", row=2, col=2)
    metrics_fig.update_yaxes(title_text="Ratio", row=2, col=2)
    
    metrics_fig.update_xaxes(title_text="Time", row=3, col=1)
    metrics_fig.update_yaxes(title_text="Orders Count", row=3, col=1)
    
    metrics_fig.update_xaxes(title_text="Time", row=3, col=2)
    metrics_fig.update_yaxes(title_text="Change %", row=3, col=2)
    
    metrics_fig.update_layout(
        height=900,
        showlegend=True,
        hovermode='x unified',
        template='plotly_white'
    )
    
    return (symbol_text, update_text, mid_price_text, spread_text, ratio_text, 
            orders_text, price_change_text, price_change_style, last_update_text, 
            orderbook_fig, metrics_fig)

def signal_handler(sig, frame):
    print("\n\n🛑 Shutting down dashboard...")
    os._exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚀 Starting Rizzo Order Book Dashboard")
    print("📊 Opening dashboard at http://127.0.0.1:8050")
    print("Press Ctrl+C to stop\n")
    
    app.run(debug=False, host='127.0.0.1', port=8050)
