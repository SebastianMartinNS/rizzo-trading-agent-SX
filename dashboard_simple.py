"""
WORKING Order Book Dashboard - SIMPLE & FAST
"""
from hyperliquid.info import Info
from hyperliquid.utils import constants
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from collections import deque, defaultdict
from datetime import datetime, timedelta
import threading
import signal
import os
import numpy as np
from typing import Dict, List, Tuple
import time

# Connessione condivisa per evitare timeout multipli
_SHARED_INFO_CACHE = {}

class OrderBookData:
    def __init__(self, symbol="BTC", testnet=True, shared_info=None):
        self.symbol = symbol
        
        # Usa connessione condivisa se fornita, altrimenti crea nuova
        if shared_info:
            self.info = shared_info
        else:
            base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
            cache_key = f"{testnet}"
            if cache_key not in _SHARED_INFO_CACHE:
                print(f"[OrderBookData] Creating shared Info connection with WebSocket (testnet={testnet})")
                _SHARED_INFO_CACHE[cache_key] = Info(base_url, skip_ws=False)
            self.info = _SHARED_INFO_CACHE[cache_key]
        
        self.max_history = 100
        self.timestamps = deque(maxlen=self.max_history)
        self.spreads = deque(maxlen=self.max_history)
        self.bid_volumes = deque(maxlen=self.max_history)
        self.ask_volumes = deque(maxlen=self.max_history)
        self.best_bids = deque(maxlen=self.max_history)
        self.best_asks = deque(maxlen=self.max_history)
        
        self.current_bids = []
        self.current_asks = []
        self.update_count = 0
        self.last_update_time = None
        
        # Footprint Charts - Delta & Volume Analysis
        self.delta_volumes = deque(maxlen=self.max_history)
        self.buy_volumes = deque(maxlen=self.max_history)
        self.sell_volumes = deque(maxlen=self.max_history)
        self.volume_imbalances = deque(maxlen=self.max_history)
        
        # Volume Profile - Price level concentration
        self.volume_profile: Dict[float, float] = defaultdict(float)
        self.profile_window_start = datetime.now()
        self.profile_period = timedelta(hours=1)
        
        # Iceberg Detection - Order persistence tracking
        self.order_history: Dict[float, List[Tuple[float, datetime]]] = defaultdict(list)
        self.iceberg_levels: List[float] = []
        self.iceberg_detection_threshold = 3
        
        # Market Depth & Time & Sales
        self.depth_imbalance = deque(maxlen=self.max_history)
        self.trade_flow_score = deque(maxlen=self.max_history)
        self.aggressive_buy_ratio = deque(maxlen=self.max_history)
        
        # Previous state for delta calculation
        self.prev_best_bid = None
        self.prev_best_ask = None
        self.prev_timestamp = None
        
        # WebSocket reconnect tracking
        self.ws_connected = False
        self.ws_last_update = datetime.now()
        self.ws_reconnect_interval = 60  # Controlla ogni 60s
        
    def handle_update(self, update):
        if update["channel"] == "l2Book" and update['data']['coin'] == self.symbol:
            self.ws_connected = True
            self.ws_last_update = datetime.now()
            self.update_count += 1
            
            asks = update["data"]["levels"][0]
            bids = update["data"]["levels"][1]
            
            if not bids or not asks:
                return
            
            self.current_bids = bids[:15]
            self.current_asks = asks[:15]
            
            best_bid = float(bids[0]['px'])
            best_ask = float(asks[0]['px'])
            spread = best_ask - best_bid
            
            bid_vol = sum(float(b['px']) * float(b['sz']) for b in bids[:10])
            ask_vol = sum(float(a['px']) * float(a['sz']) for a in asks[:10])
            
            current_time = datetime.now()
            self.timestamps.append(current_time)
            self.spreads.append(spread)
            self.bid_volumes.append(bid_vol)
            self.ask_volumes.append(ask_vol)
            self.best_bids.append(best_bid)
            self.best_asks.append(best_ask)
            self.last_update_time = current_time
            
            # Calculate advanced metrics
            self._calculate_footprint_metrics(best_bid, best_ask, bid_vol, ask_vol, current_time)
            self._update_volume_profile(best_bid, best_ask, bid_vol, ask_vol)
            self._detect_icebergs(bids, asks, current_time)
            self._calculate_market_depth_metrics(bids, asks)
            
            self.prev_best_bid = best_bid
            self.prev_best_ask = best_ask
            self.prev_timestamp = current_time
    
    def _calculate_footprint_metrics(self, best_bid: float, best_ask: float, 
                                     bid_vol: float, ask_vol: float, current_time: datetime):
        """Calculate Delta Volume and Buy/Sell imbalance for footprint analysis"""
        if self.prev_best_bid is None or self.prev_best_ask is None:
            self.delta_volumes.append(0)
            self.buy_volumes.append(0)
            self.sell_volumes.append(0)
            self.volume_imbalances.append(0)
            return
        
        # Detect price movement direction
        price_change = (best_bid - self.prev_best_bid + best_ask - self.prev_best_ask) / 2
        
        # Estimate Buy/Sell volume based on price direction and volume changes
        if price_change > 0:
            buy_vol_est = bid_vol * 0.6 + ask_vol * 0.4
            sell_vol_est = bid_vol * 0.4 + ask_vol * 0.6
        elif price_change < 0:
            buy_vol_est = bid_vol * 0.4 + ask_vol * 0.6
            sell_vol_est = bid_vol * 0.6 + ask_vol * 0.4
        else:
            buy_vol_est = bid_vol * 0.5 + ask_vol * 0.5
            sell_vol_est = bid_vol * 0.5 + ask_vol * 0.5
        
        delta = buy_vol_est - sell_vol_est
        total_vol = buy_vol_est + sell_vol_est
        imbalance = delta / total_vol if total_vol > 0 else 0
        
        self.delta_volumes.append(delta)
        self.buy_volumes.append(buy_vol_est)
        self.sell_volumes.append(sell_vol_est)
        self.volume_imbalances.append(imbalance)
    
    def _update_volume_profile(self, best_bid: float, best_ask: float, 
                               bid_vol: float, ask_vol: float):
        """Build volume profile - concentration at price levels"""
        current_time = datetime.now()
        
        # Reset profile after period
        if current_time - self.profile_window_start > self.profile_period:
            self.volume_profile.clear()
            self.profile_window_start = current_time
        
        # Round prices to reasonable precision
        bid_price_key = round(best_bid, 0)
        ask_price_key = round(best_ask, 0)
        
        # Accumulate volume at price levels
        self.volume_profile[bid_price_key] += bid_vol
        self.volume_profile[ask_price_key] += ask_vol
    
    def _detect_icebergs(self, bids: List[dict], asks: List[dict], current_time: datetime):
        """Detect hidden orders through persistence pattern analysis"""
        self.iceberg_levels.clear()
        
        # Check top 5 levels for persistence
        for level in bids[:5] + asks[:5]:
            price = float(level['px'])
            size = float(level['sz'])
            
            # Track order at this level
            self.order_history[price].append((size, current_time))
            
            # Clean old history (keep last 30 seconds)
            cutoff = current_time - timedelta(seconds=30)
            self.order_history[price] = [(s, t) for s, t in self.order_history[price] if t > cutoff]
            
            # Detect iceberg: multiple appearances at same level with similar size
            if len(self.order_history[price]) >= self.iceberg_detection_threshold:
                sizes = [s for s, _ in self.order_history[price]]
                avg_size = np.mean(sizes)
                std_size = np.std(sizes)
                
                # Consistent size = likely iceberg
                if std_size / avg_size < 0.15 and avg_size > 1.0:
                    self.iceberg_levels.append(price)
    
    def _calculate_market_depth_metrics(self, bids: List[dict], asks: List[dict]):
        """Calculate market depth imbalance and aggressive flow metrics"""
        if not bids or not asks:
            self.depth_imbalance.append(0)
            self.trade_flow_score.append(0)
            self.aggressive_buy_ratio.append(0.5)
            return
        
        # Total depth in top 10 levels
        total_bid_depth = sum(float(b['sz']) for b in bids[:10])
        total_ask_depth = sum(float(a['sz']) for a in asks[:10])
        total_depth = total_bid_depth + total_ask_depth
        
        # Depth imbalance (-1 to 1)
        depth_imb = (total_bid_depth - total_ask_depth) / total_depth if total_depth > 0 else 0
        self.depth_imbalance.append(depth_imb)
        
        # Estimate aggressive buying pressure
        # Higher bid depth + tighter spread = aggressive buying
        best_bid = float(bids[0]['px'])
        best_ask = float(asks[0]['px'])
        spread_pct = (best_ask - best_bid) / best_bid if best_bid > 0 else 0
        
        # Aggressive buy ratio (0 to 1)
        if spread_pct < 0.0001:  # Tight spread
            agg_buy = 0.5 + depth_imb * 0.5
        else:
            agg_buy = 0.5 + depth_imb * 0.3
        
        self.aggressive_buy_ratio.append(max(0, min(1, agg_buy)))
        
        # Trade flow score: combines depth imbalance with recent delta
        recent_delta = np.mean(list(self.delta_volumes)[-5:]) if len(self.delta_volumes) >= 5 else 0
        flow_score = depth_imb * 0.6 + (recent_delta / 1000000) * 0.4  # Normalize delta
        self.trade_flow_score.append(flow_score)
    
    def get_volume_profile_levels(self) -> List[Tuple[float, float]]:
        """Get top volume concentration levels (price, volume)"""
        if not self.volume_profile:
            return []
        
        sorted_levels = sorted(self.volume_profile.items(), key=lambda x: x[1], reverse=True)
        return sorted_levels[:5]
    
    def get_trading_signal(self) -> Tuple[str, float, str]:
        """Generate trading signal from advanced metrics"""
        if len(self.delta_volumes) < 10:
            return "NEUTRAL", 0.0, "Insufficient data"
        
        # Recent metrics
        recent_delta = np.mean(list(self.delta_volumes)[-5:])
        recent_imbalance = np.mean(list(self.volume_imbalances)[-5:])
        recent_depth_imb = np.mean(list(self.depth_imbalance)[-5:])
        recent_agg_buy = np.mean(list(self.aggressive_buy_ratio)[-5:])
        
        # Signal strength
        signal_strength = abs(recent_imbalance) * 0.3 + abs(recent_depth_imb) * 0.4 + abs(recent_agg_buy - 0.5) * 0.3
        
        # Determine signal
        bullish_score = 0
        bearish_score = 0
        reasons = []
        
        if recent_delta > 100000:
            bullish_score += 1
            reasons.append("Positive delta")
        elif recent_delta < -100000:
            bearish_score += 1
            reasons.append("Negative delta")
        
        if recent_imbalance > 0.15:
            bullish_score += 1
            reasons.append("Buy imbalance")
        elif recent_imbalance < -0.15:
            bearish_score += 1
            reasons.append("Sell imbalance")
        
        if recent_depth_imb > 0.2:
            bullish_score += 1
            reasons.append("Bid depth dominance")
        elif recent_depth_imb < -0.2:
            bearish_score += 1
            reasons.append("Ask depth dominance")
        
        if recent_agg_buy > 0.65:
            bullish_score += 1
            reasons.append("Aggressive buying")
        elif recent_agg_buy < 0.35:
            bearish_score += 1
            reasons.append("Aggressive selling")
        
        # Iceberg detection adds context
        if len(self.iceberg_levels) > 0:
            best_bid = self.best_bids[-1] if self.best_bids else 0
            best_ask = self.best_asks[-1] if self.best_asks else 0
            
            for iceberg_price in self.iceberg_levels:
                if iceberg_price > best_ask:
                    reasons.append(f"Iceberg resistance at {iceberg_price:.0f}")
                    bearish_score += 0.5
                elif iceberg_price < best_bid:
                    reasons.append(f"Iceberg support at {iceberg_price:.0f}")
                    bullish_score += 0.5
        
        # Volume profile key levels
        pvp_levels = self.get_volume_profile_levels()
        if pvp_levels and self.best_bids:
            current_price = (self.best_bids[-1] + self.best_asks[-1]) / 2
            pvp_price = pvp_levels[0][0]
            
            if current_price < pvp_price * 0.995:
                reasons.append(f"Below PVP {pvp_price:.0f}")
                bullish_score += 0.5
            elif current_price > pvp_price * 1.005:
                reasons.append(f"Above PVP {pvp_price:.0f}")
                bearish_score += 0.5
        
        # Final signal
        if bullish_score >= bearish_score + 2:
            return "LONG", signal_strength, " | ".join(reasons)
        elif bearish_score >= bullish_score + 2:
            return "SHORT", signal_strength, " | ".join(reasons)
        else:
            return "NEUTRAL", signal_strength, " | ".join(reasons) if reasons else "No clear signal"
    
    def start_websocket(self):
        """Subscribe to WebSocket with auto-reconnect"""
        while True:
            try:
                if not self.ws_connected or (datetime.now() - self.ws_last_update).total_seconds() > 120:
                    self.info.subscribe({"type": "l2Book", "coin": self.symbol}, self.handle_update)
                    print(f"[OrderBookData] WebSocket (re)subscribed for {self.symbol}")
                    self.ws_connected = True
                    self.ws_last_update = datetime.now()
                time.sleep(self.ws_reconnect_interval)
            except Exception as e:
                print(f"[OrderBookData] WebSocket error {self.symbol}: {str(e)[:80]}")
                self.ws_connected = False
                time.sleep(10)

# Initialize
data = OrderBookData(symbol="BTC")
ws_thread = threading.Thread(target=data.start_websocket, daemon=True)
ws_thread.start()

# Create app
app = dash.Dash(__name__)
app.title = "BTC Order Book - Live"

app.layout = html.Div([
    html.H1(f"{data.symbol} Advanced Order Flow Analytics (MAINNET)", 
            style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '10px'}),
    
    # Row 1: Basic Metrics
    html.Div([
        html.Div([
            html.H4("Updates"),
            html.H2(id='updates', style={'color': '#3498db'})
        ], style={'flex': 1, 'textAlign': 'center', 'padding': '15px', 'margin': '5px', 
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("Spread"),
            html.H2(id='spread', style={'color': '#e74c3c'})
        ], style={'flex': 1, 'textAlign': 'center', 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("Bid/Ask Ratio"),
            html.H2(id='ratio', style={'color': '#2ecc71'})
        ], style={'flex': 1, 'textAlign': 'center', 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
    ], style={'display': 'flex', 'margin': '10px'}),
    
    # Row 2: Advanced Metrics
    html.Div([
        html.Div([
            html.H4("Delta Volume"),
            html.H2(id='delta', style={'color': '#9b59b6'})
        ], style={'flex': 1, 'textAlign': 'center', 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("Volume Imbalance"),
            html.H2(id='imbalance', style={'color': '#f39c12'})
        ], style={'flex': 1, 'textAlign': 'center', 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("Depth Imbalance"),
            html.H2(id='depth-imb', style={'color': '#16a085'})
        ], style={'flex': 1, 'textAlign': 'center', 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("Aggressive Buy"),
            html.H2(id='agg-buy', style={'color': '#c0392b'})
        ], style={'flex': 1, 'textAlign': 'center', 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
    ], style={'display': 'flex', 'margin': '10px'}),
    
    # Trading Signal
    html.Div([
        html.H3("Trading Signal", style={'marginBottom': '5px'}),
        html.H2(id='signal', style={'margin': '0'}),
        html.P(id='signal-reason', style={'fontSize': '14px', 'color': '#7f8c8d', 'margin': '5px 0'})
    ], style={'textAlign': 'center', 'padding': '15px', 'margin': '10px',
              'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
    
    # Iceberg & Volume Profile
    html.Div([
        html.Div([
            html.H4("Iceberg Levels Detected"),
            html.Div(id='icebergs', style={'fontSize': '16px'})
        ], style={'flex': 1, 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4("Volume Profile (Top 5)"),
            html.Div(id='vol-profile', style={'fontSize': '16px'})
        ], style={'flex': 1, 'padding': '15px', 'margin': '5px',
                  'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
    ], style={'display': 'flex', 'margin': '10px'}),
    
    # Charts
    html.Div([dcc.Graph(id='orderbook')], style={'margin': '10px'}),
    html.Div([dcc.Graph(id='footprint')], style={'margin': '10px'}),
    html.Div([dcc.Graph(id='depth-flow')], style={'margin': '10px'}),
    
    html.Div(id='last-update', style={'textAlign': 'center', 'padding': '10px', 'color': '#7f8c8d'}),
    
    dcc.Interval(id='interval', interval=300, n_intervals=0)
], style={'backgroundColor': '#ecf0f1', 'padding': '15px', 'fontFamily': 'Arial, sans-serif'})

@app.callback(
    [Output('updates', 'children'),
     Output('spread', 'children'),
     Output('ratio', 'children'),
     Output('delta', 'children'),
     Output('imbalance', 'children'),
     Output('depth-imb', 'children'),
     Output('agg-buy', 'children'),
     Output('signal', 'children'),
     Output('signal-reason', 'children'),
     Output('icebergs', 'children'),
     Output('vol-profile', 'children'),
     Output('last-update', 'children'),
     Output('orderbook', 'figure'),
     Output('footprint', 'figure'),
     Output('depth-flow', 'figure')],
    [Input('interval', 'n_intervals')]
)
def update_all(n):
    # Basic Metrics
    updates_text = f"{data.update_count:,}"
    
    spread_text = "N/A"
    if len(data.spreads) > 0:
        spread_text = f"${data.spreads[-1]:.2f}"
    
    ratio_text = "N/A"
    if len(data.bid_volumes) > 0 and len(data.ask_volumes) > 0:
        ratio = data.bid_volumes[-1] / data.ask_volumes[-1] if data.ask_volumes[-1] > 0 else 0
        ratio_text = f"{ratio:.2f}x"
    
    # Advanced Metrics
    delta_text = "N/A"
    if len(data.delta_volumes) > 0:
        delta = data.delta_volumes[-1]
        delta_text = f"{delta/1000:.0f}K"
        if delta > 0:
            delta_text = f"+{delta_text}"
    
    imbalance_text = "N/A"
    if len(data.volume_imbalances) > 0:
        imb = data.volume_imbalances[-1]
        imbalance_text = f"{imb*100:.1f}%"
    
    depth_imb_text = "N/A"
    if len(data.depth_imbalance) > 0:
        depth = data.depth_imbalance[-1]
        depth_imb_text = f"{depth*100:.1f}%"
    
    agg_buy_text = "N/A"
    if len(data.aggressive_buy_ratio) > 0:
        agg = data.aggressive_buy_ratio[-1]
        agg_buy_text = f"{agg*100:.0f}%"
    
    # Trading Signal
    signal_type, signal_strength, signal_reason = data.get_trading_signal()
    signal_color = {'LONG': '#27ae60', 'SHORT': '#e74c3c', 'NEUTRAL': '#95a5a6'}
    signal_text = html.Span(f"{signal_type} ({signal_strength:.2f})", 
                            style={'color': signal_color.get(signal_type, '#95a5a6'), 'fontWeight': 'bold'})
    
    # Iceberg Levels
    iceberg_text = "None detected"
    if len(data.iceberg_levels) > 0:
        iceberg_text = html.Ul([html.Li(f"${lvl:.0f}") for lvl in data.iceberg_levels[:5]])
    
    # Volume Profile
    vol_profile_text = "Building..."
    pvp_levels = data.get_volume_profile_levels()
    if pvp_levels:
        vol_profile_text = html.Ul([html.Li(f"${price:.0f}: {volume/1e6:.2f}M") 
                                     for price, volume in pvp_levels])
    
    last_text = data.last_update_time.strftime('%H:%M:%S') if data.last_update_time else "Waiting..."
    
    # Order Book Chart
    ob_fig = go.Figure()
    if data.current_bids and data.current_asks:
        bid_prices = [float(b['px']) for b in data.current_bids]
        bid_sizes = [float(b['sz']) for b in data.current_bids]
        ask_prices = [float(a['px']) for a in data.current_asks]
        ask_sizes = [float(a['sz']) for a in data.current_asks]
        
        ob_fig.add_trace(go.Bar(x=bid_prices, y=bid_sizes, name='Bids', marker_color='#27ae60', opacity=0.7))
        ob_fig.add_trace(go.Bar(x=ask_prices, y=ask_sizes, name='Asks', marker_color='#e74c3c', opacity=0.7))
        
        # Mark iceberg levels
        for iceberg_price in data.iceberg_levels:
            ob_fig.add_vline(x=iceberg_price, line_dash="dash", line_color="orange", 
                           annotation_text="Iceberg", annotation_position="top")
    
    ob_fig.update_layout(title="Order Book Depth + Iceberg Detection", xaxis_title="Price", yaxis_title="Size",
                         barmode='group', height=400, template='plotly_white')
    
    # Footprint Chart (Delta, Buy/Sell Volume)
    footprint_fig = go.Figure()
    if len(data.timestamps) > 0:
        footprint_fig.add_trace(go.Scatter(x=list(data.timestamps), y=list(data.delta_volumes),
                                          name='Delta Volume', line=dict(color='#9b59b6', width=3),
                                          fill='tozeroy'))
        footprint_fig.add_trace(go.Scatter(x=list(data.timestamps), y=list(data.buy_volumes),
                                          name='Buy Volume', line=dict(color='#27ae60', width=2)))
        footprint_fig.add_trace(go.Scatter(x=list(data.timestamps), y=list(data.sell_volumes),
                                          name='Sell Volume', line=dict(color='#e74c3c', width=2)))
    
    footprint_fig.update_layout(title="Footprint Analysis - Delta & Buy/Sell Volume", height=400, 
                               template='plotly_white', hovermode='x unified')
    
    # Market Depth & Flow Chart
    depth_flow_fig = go.Figure()
    if len(data.timestamps) > 0:
        depth_flow_fig.add_trace(go.Scatter(x=list(data.timestamps), y=list(data.depth_imbalance),
                                           name='Depth Imbalance', line=dict(color='#16a085', width=2)))
        depth_flow_fig.add_trace(go.Scatter(x=list(data.timestamps), y=list(data.trade_flow_score),
                                           name='Trade Flow Score', line=dict(color='#f39c12', width=2)))
        
        # Normalize aggressive buy ratio to same scale
        norm_agg = [(x - 0.5) * 2 for x in data.aggressive_buy_ratio]  # Scale to -1 to 1
        depth_flow_fig.add_trace(go.Scatter(x=list(data.timestamps), y=norm_agg,
                                           name='Aggressive Buy (norm)', line=dict(color='#c0392b', width=2, dash='dot')))
    
    depth_flow_fig.update_layout(title="Market Depth & Order Flow Analysis", height=400,
                                template='plotly_white', hovermode='x unified')
    
    return (updates_text, spread_text, ratio_text, delta_text, imbalance_text, depth_imb_text, agg_buy_text,
            signal_text, signal_reason, iceberg_text, vol_profile_text, f"Last update: {last_text}",
            ob_fig, footprint_fig, depth_flow_fig)

def signal_handler(sig, frame):
    print("\n\n🛑 Shutting down...")
    os._exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    
    print("Starting BTC Advanced Order Flow Analytics")
    print("http://127.0.0.1:8055")
    print("300ms refresh - Press Ctrl+C to stop\n")
    
    app.run(debug=False, host='127.0.0.1', port=8055)
