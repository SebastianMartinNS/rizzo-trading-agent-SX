"""
Advanced Trading Bot with Integrated Order Flow Analytics
Combines OrderBookData metrics with AI agent decision-making
"""
from hyperliquid_trader import HyperLiquidTrader
from trading_agent import previsione_trading_agent
from dashboard_simple import OrderBookData
from indicators import analyze_multiple_tickers
from news_feed import fetch_latest_news
from sentiment import get_sentiment
from forecaster import get_crypto_forecasts
from utils import check_stop_loss
import db_utils
import threading
import time
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

class AdvancedTradingBot:
    def __init__(self, secret_key, account_address, symbols_to_monitor, testnet=True, cycle_interval=60):
        """
        Initialize Advanced Trading Bot with Order Flow Analytics
        
        Args:
            secret_key: Hyperliquid private key
            account_address: Wallet address
            symbols_to_monitor: List of symbols to trade (e.g. ['BTC', 'ETH', 'SOL'])
            testnet: Use testnet (True) or mainnet (False)
            cycle_interval: Seconds between trading cycles (default 60)
        """
        self.hyperliquid_trader = HyperLiquidTrader(secret_key, account_address, testnet=testnet)
        self.symbols_to_monitor = symbols_to_monitor
        self.order_book_analyzers = {}
        self.cycle_interval = cycle_interval
        self.testnet = testnet
        
        # Stato per strategia scalping
        self.daily_watchlist = None
        self.watchlist_updated_at = None
        self.active_trades = {}  # symbol → {entry_px, target_profit_usd, max_hold_minutes, opened_at, direction}
        
        # Configurazione scalping
        self.scalping_mode = True
        self.take_profit_percent = 3.0
        self.scalping_stop_loss = 2.5
        self.scalping_position_size = 0.12
        self.default_leverage_scalping = 6
        self.min_target_profit_usd = 2.0
        self.cooldown_minutes = 30
        self.closed_positions_cooldown = {}  # symbol → timestamp ultima chiusura
        
        # Filtra simboli disponibili PRIMA di inizializzare
        from indicators import CryptoTechnicalAnalysisHL
        temp_analyzer = CryptoTechnicalAnalysisHL(testnet=self.testnet)
        available_symbols = temp_analyzer.get_available_symbols()
        symbols_to_init = [s for s in symbols_to_monitor if s in available_symbols]
        
        print(f"[AdvancedTradingBot] Initializing for {len(symbols_to_init)}/{len(symbols_to_monitor)} available symbols: {symbols_to_init}")
        
        # Crea SINGOLA connessione Info condivisa con WebSocket per order flow
        print("[AdvancedTradingBot] Creating shared Info connection with WebSocket...")
        from hyperliquid.info import Info
        from hyperliquid.utils import constants
        base_url = constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL
        shared_info = Info(base_url, skip_ws=False)
        print("[AdvancedTradingBot] Shared WebSocket connection ready")
        
        # Initialize OrderBookData analyzer per ogni simbolo (con connessione condivisa)
        for symbol in symbols_to_init:
            try:
                analyzer = OrderBookData(symbol=symbol, testnet=self.testnet, shared_info=shared_info)
                self.order_book_analyzers[symbol] = analyzer
                
                # Start WebSocket thread con auto-reconnect
                ws_thread = threading.Thread(target=analyzer.start_websocket, daemon=True)
                ws_thread.start()
                print(f"[AdvancedTradingBot] Started auto-reconnect WebSocket thread for {symbol}")
            except Exception as e:
                print(f"[AdvancedTradingBot] Failed to init {symbol}: {e}")
        
        # Aspetta 5s per primi update WebSocket
        print("[AdvancedTradingBot] Waiting 5s for initial WebSocket order book data...")
        time.sleep(5)

    def _ensure_order_book_analyzer(self, symbol):
        """Inizializza OrderBookData analyzer se non esiste"""
        if symbol not in self.order_book_analyzers:
            print(f"[OrderBook] Inizializzazione analyzer per {symbol}...")
            analyzer = OrderBookData(symbol=symbol)
            self.order_book_analyzers[symbol] = analyzer
            ws_thread = threading.Thread(target=analyzer.start_websocket, daemon=True)
            ws_thread.start()
            time.sleep(2)  # Attesa dati iniziali

    def get_order_flow_summary(self, symbol):
        """
        Get comprehensive order flow summary for a symbol
        
        Returns:
            dict: Order flow metrics and signal
        """
        self._ensure_order_book_analyzer(symbol)
        analyzer = self.order_book_analyzers.get(symbol)
        if not analyzer or len(analyzer.timestamps) < 10:
            return None
        
        # Get trading signal from order flow analysis
        signal_type, signal_strength, signal_reason = analyzer.get_trading_signal()
        
        # Get latest metrics
        latest_metrics = {
            "spread": analyzer.spreads[-1] if len(analyzer.spreads) > 0 else 0,
            "bid_ask_ratio": analyzer.bid_volumes[-1] / analyzer.ask_volumes[-1] if len(analyzer.ask_volumes) > 0 and analyzer.ask_volumes[-1] > 0 else 1.0,
            "delta_volume": analyzer.delta_volumes[-1] if len(analyzer.delta_volumes) > 0 else 0,
            "volume_imbalance": analyzer.volume_imbalances[-1] if len(analyzer.volume_imbalances) > 0 else 0,
            "depth_imbalance": analyzer.depth_imbalance[-1] if len(analyzer.depth_imbalance) > 0 else 0,
            "aggressive_buy_ratio": analyzer.aggressive_buy_ratio[-1] if len(analyzer.aggressive_buy_ratio) > 0 else 0.5,
            "best_bid": analyzer.best_bids[-1] if len(analyzer.best_bids) > 0 else 0,
            "best_ask": analyzer.best_asks[-1] if len(analyzer.best_asks) > 0 else 0,
            "iceberg_levels": analyzer.iceberg_levels[:3],  # Top 3 iceberg levels
            "volume_profile_top": analyzer.get_volume_profile_levels()[:3],  # Top 3 volume concentrations
            "update_count": analyzer.update_count
        }
        
        return {
            "signal": signal_type,
            "strength": signal_strength,
            "reason": signal_reason,
            "metrics": latest_metrics
        }

    def _update_daily_watchlist(self):
        """Aggiornamento watchlist giornaliera tramite AI con validazione Hyperliquid"""
        from datetime import timedelta
        from openai import OpenAI
        import json
        
        # Verifica se serve aggiornare (ogni 1 ora per testing, non 24h)
        if self.watchlist_updated_at:
            elapsed_hours = (datetime.now() - self.watchlist_updated_at).total_seconds() / 3600
            if elapsed_hours < 1.0:
                return  # Watchlist ancora valida
        
        print("\n[WATCHLIST] Aggiornamento watchlist giornaliera via AI...")
        
        # Recupera simboli effettivamente disponibili su Hyperliquid
        from indicators import CryptoTechnicalAnalysisHL
        analyzer = CryptoTechnicalAnalysisHL(testnet=self.testnet)
        available_symbols = analyzer.get_available_symbols()
        print(f"[WATCHLIST] Simboli disponibili su Hyperliquid: {len(available_symbols)}")
        
        # Filtra solo quelli nella configurazione
        valid_symbols = [s for s in self.symbols_to_monitor if s in available_symbols]
        
        if len(valid_symbols) < 3:
            print(f"[WATCHLIST] ERRORE: Solo {len(valid_symbols)} simboli validi")
            self.daily_watchlist = valid_symbols
            self.watchlist_updated_at = datetime.now()
            return
        
        try:
            # Chiamata diretta OpenAI per watchlist (senza schema rigido)
            client = OpenAI(
                api_key=os.getenv('OPENROUTER_API_KEY'),
                base_url="https://openrouter.ai/api/v1"
            )
            
            available_str = ", ".join(valid_symbols)
            watchlist_prompt = f"""Seleziona esattamente 10 criptovalute adatte per SCALPING oggi.

Criteri:
- Alta liquidità su exchange (spread bassi, volumi elevati)
- Volatilità intraday 2-5% (opportunità rapide senza rischio eccessivo)
- Trend tecnici chiari su timeframe 15m-1h
- Sentiment di mercato positivo o neutrale

Disponibili SOLO: {available_str}

Restituisci SOLO un oggetto JSON valido:
{{"symbols": ["SYMBOL1", "SYMBOL2", ...]}}

MASSIMO 10 simboli dalla lista disponibile."""

            response = client.chat.completions.create(
                model="anthropic/claude-3.5-sonnet",
                messages=[{"role": "user", "content": watchlist_prompt}],
                temperature=0.3
            )
            
            raw_text = response.choices[0].message.content.strip()
            
            # Estrai JSON dalla risposta
            if raw_text.startswith("```json"):
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
            parsed = json.loads(raw_text)
            
            if "symbols" in parsed and isinstance(parsed["symbols"], list):
                # Filtra solo simboli validi
                symbols = [s for s in parsed["symbols"][:10] if s in valid_symbols]
                if len(symbols) < 3:
                    raise ValueError(f"AI restituito solo {len(symbols)} simboli validi")
                
                self.daily_watchlist = symbols
                self.watchlist_updated_at = datetime.now()
                print(f"[WATCHLIST] Aggiornata con {len(symbols)} simboli: {symbols}")
            else:
                raise ValueError("Formato risposta non valido")
            
        except Exception as e:
            print(f"[WATCHLIST] Errore aggiornamento: {e}")
            # Fallback: usa solo simboli validi disponibili (max 10)
            self.daily_watchlist = valid_symbols[:10]
            self.watchlist_updated_at = datetime.now()
            print(f"[WATCHLIST] Uso fallback con simboli validi: {self.daily_watchlist}")

    def _build_monitoring_prompt(self, symbol, position_data, order_flow_data):
        """Prompt specifico per monitoraggio posizione esistente"""
        side = position_data.get("side", "long")
        entry_px = float(position_data.get("entry_price", 0))
        size = float(position_data.get("size", 0))
        unrealized_pnl = float(position_data.get("pnl_usd", 0))
        
        trade_info = self.active_trades.get(symbol, {})
        target_profit = trade_info.get("target_profit_usd", 0.5)
        max_hold = trade_info.get("max_hold_minutes", 60)
        opened_at = trade_info.get("opened_at")
        
        minutes_held = 0
        if opened_at:
            from datetime import datetime
            minutes_held = (datetime.now() - opened_at).total_seconds() / 60
        
        # Indicatori, order flow, news, sentiment, forecast
        indicators_txt, _ = analyze_multiple_tickers([symbol])
        news_txt = fetch_latest_news()
        sentiment_txt, _ = get_sentiment()
        forecast_txt, _ = get_crypto_forecasts([symbol])
        
        of = order_flow_data
        of_signal = of["signal"]
        of_strength = of["strength"]
        
        prompt = f"""<monitoring>
Simbolo: {symbol}
Posizione: {side.upper()}
Entry Price: ${entry_px:.2f}
Size: {abs(size)}
PnL Attuale: ${unrealized_pnl:.2f}
Target Profit: ${target_profit:.2f}
Tempo Trascorso: {minutes_held:.0f}/{max_hold} minuti
Timeframe: 15-minute candlesticks

<order_flow>
Segnale: {of_signal}
Forza: {of_strength:.2f}
Best Bid: ${of['metrics']['best_bid']:.2f} | Best Ask: ${of['metrics']['best_ask']:.2f}
Delta Volume: {of['metrics']['delta_volume']/1000:.0f}K
Volume Imbalance: {of['metrics']['volume_imbalance']*100:.1f}%
</order_flow>

<indicatori_tecnici>
{indicators_txt}
</indicatori_tecnici>

<news_recenti>
{news_txt[:1000]}
</news_recenti>

<sentiment_mercato>
{sentiment_txt}
</sentiment_mercato>

<forecast>
{forecast_txt}
</forecast>

<istruzioni>
REGOLE FERREE:
1. NON chiudere MAI in perdita netta (PnL < 0)
2. Chiudi SOLO se PnL ≥ ${target_profit:.2f} E segnali tecnici confermano
3. Se timeout ({max_hold} min) raggiunto e PnL ≥ 0, chiudi in break-even
4. Altrimenti, HOLD fino a recupero

Operazioni consentite:
- "operation": "close", "direction": "{side}" → Chiudi posizione
- "operation": "hold" → Mantieni posizione

Restituisci JSON: {{"operation": "close|hold", "direction": "{side}", "reasoning": "..."}}
</istruzioni>
</monitoring>"""
        
        return prompt

    def build_enhanced_prompt(self, symbol, account_status, order_flow_data):
        """
        Build enhanced system prompt including order flow analytics
        
        Args:
            symbol: Trading symbol
            account_status: Current account state
            order_flow_data: Order flow metrics from OrderBookData
            
        Returns:
            str: Complete system prompt with all context
        """
        # Get traditional indicators
        indicators_txt, indicators_json = analyze_multiple_tickers([symbol])
        
        # Get news
        news_txt = fetch_latest_news()
        
        # Get sentiment
        sentiment_txt, sentiment_json = get_sentiment()
        
        # Get forecasts - ONLY for current symbol to avoid AI confusion
        forecasts_txt, forecasts_json = get_crypto_forecasts([symbol])
        
        # Format order flow data
        of = order_flow_data
        order_flow_txt = f"""
ORDER FLOW ANALYTICS FOR {symbol}:
Signal: {of['signal']} (Strength: {of['strength']:.2f})
Reason: {of['reason']}

Real-Time Metrics:
- Best Bid: ${of['metrics']['best_bid']:.2f} | Best Ask: ${of['metrics']['best_ask']:.2f}
- Spread: ${of['metrics']['spread']:.2f}
- Bid/Ask Volume Ratio: {of['metrics']['bid_ask_ratio']:.2f}x
- Delta Volume: {of['metrics']['delta_volume']/1000:.0f}K (Buy-Sell pressure)
- Volume Imbalance: {of['metrics']['volume_imbalance']*100:.1f}% (>0 = bullish, <0 = bearish)
- Depth Imbalance: {of['metrics']['depth_imbalance']*100:.1f}% (order book skew)
- Aggressive Buy Ratio: {of['metrics']['aggressive_buy_ratio']*100:.0f}%
- Total Updates: {of['metrics']['update_count']}

Iceberg Detection:
{', '.join([f'${lvl:.0f}' for lvl in of['metrics']['iceberg_levels']]) if of['metrics']['iceberg_levels'] else 'None detected'}

Volume Profile (High Concentration Zones):
{', '.join([f'${price:.0f} ({vol/1e6:.1f}M)' for price, vol in of['metrics']['volume_profile_top']]) if of['metrics']['volume_profile_top'] else 'Building...'}

INTERPRETATION GUIDE:
- Delta Volume: Positive = more buying pressure, Negative = more selling pressure
- Volume Imbalance >15%: Strong directional bias
- Depth Imbalance >20%: Significant order book skew (potential breakout/breakdown)
- Aggressive Buy >65%: Aggressive buyers stepping up (bullish)
- Aggressive Buy <35%: Aggressive sellers dominating (bearish)
- Iceberg Levels: Hidden large orders creating support/resistance
"""
        
        # Combine all data
        msg_info = f"""<indicatori>
{indicators_txt}
</indicatori>

<order_flow_analytics>
{order_flow_txt}
</order_flow_analytics>

<news>
{news_txt}
</news>

<sentiment>
{sentiment_txt}
</sentiment>

<forecast>
{forecasts_txt}
</forecast>
"""
        
        # Check stop losses
        stop_losses = check_stop_loss(account_status)
        
        # Filter portfolio to show only current symbol position
        symbol_position = None
        for pos in account_status.get("open_positions", []):
            if pos.get("symbol") == symbol:
                symbol_position = pos
                break
        
        # Portfolio data compatto (istruzioni già in system_prompt.txt)
        portfolio_data_filtered = {
            "accountValue": account_status.get("accountValue"),
            "withdrawable": account_status.get("withdrawable"),
            "current_symbol_position": symbol_position,
            "all_positions_count": len(account_status.get("open_positions", [])),
            "stop_losses_triggered": stop_losses
        }
        
        portfolio_data = f"{json.dumps(portfolio_data_filtered, indent=2)}"
        
        # Load system prompt template
        with open('system_prompt.txt', 'r') as f:
            system_prompt = f.read()
        
        # Header conciso con status posizione
        if symbol_position:
            side = symbol_position.get('side', 'unknown')
            pnl = symbol_position.get('pnl_usd', 0)
            position_status = f"ACTIVE {side.upper()} (PnL: ${pnl:.2f}) - close/hold only"
        else:
            position_status = "NO POSITION - can open new trade"
        
        symbol_header = f"\n{'='*80}\n>>> {symbol} | {position_status} | Timeframe: 15min <<<\n{'='*80}\n\n"
        
        system_prompt = system_prompt.format(portfolio_data, msg_info)
        system_prompt = symbol_header + system_prompt
        
        return system_prompt, indicators_json, news_txt, sentiment_json, forecasts_json, order_flow_data

    def merge_signals(self, symbol, ai_decision, order_flow_data, account_status):
        """
        Merge AI agent decision with order flow signals + SCALPING logic
        
        Args:
            symbol: Trading symbol
            ai_decision: Decision from AI agent
            order_flow_data: Order flow analytics
            account_status: Current account state
            
        Returns:
            dict: Final trading decision
        """
        # Check if position exists for this symbol
        open_position = None
        for pos in account_status.get("open_positions", []):
            if pos["symbol"] == symbol:
                open_position = pos
                break
        
        # Scalping: Auto-close check for profit target
        if self.scalping_mode and open_position:
            entry_price = float(open_position.get("entry_price", 0))
            size = float(open_position.get("size", 0))
            notional = size * entry_price
            pnl_usd = float(open_position.get("pnl_usd", 0))
            if notional > 0:
                pnl_pct = (pnl_usd / notional) * 100
                if pnl_pct >= self.take_profit_percent:
                    print(f"  SCALPING OVERRIDE: {pnl_pct:.2f}% profit - forcing close")
                    return {
                        "operation": "close",
                        "symbol": symbol,
                        "direction": open_position["side"].lower(),
                        "reasoning": f"SCALPING PROFIT TARGET: {pnl_pct:.2f}% profit reached"
                    }
        
        # Get order flow signal
        of_signal = order_flow_data["signal"]
        of_strength = order_flow_data["strength"]
        of_reason = order_flow_data["reason"]
        
        # Get AI signal
        ai_operation = ai_decision.get("operation", "hold")
        ai_direction = ai_decision.get("direction", "").lower() if ai_operation == "open" else None
        
        print(f"\n[SignalMerge] {symbol}")
        print(f"  Order Flow: {of_signal} (Strength: {of_strength:.2f})")
        print(f"  AI Agent: {ai_operation} {ai_direction or ''}")
        print(f"  Current Position: {open_position['side'] if open_position else 'None'}")
        
        # If AI says hold or close, respect that
        if ai_operation in ["hold", "close"]:
            print(f"  Decision: Following AI -> {ai_operation}")
            return ai_decision
        
        # CRITICAL: If AI says "open" but position exists, it means AI wants to reverse
        # We interpret this as: close current position if direction is opposite
        if ai_operation == "open" and open_position is not None:
            current_side = open_position['side'].lower()
            wanted_direction = ai_direction
            
            # If AI wants opposite direction, close current position
            if (current_side == "long" and wanted_direction == "short") or \
               (current_side == "short" and wanted_direction == "long"):
                print(f"  Decision: AI wants {wanted_direction} but has {current_side} -> CLOSING {current_side}")
                return {
                    "operation": "close",
                    "symbol": symbol,
                    "direction": current_side,
                    "reasoning": f"AI wants to reverse from {current_side} to {wanted_direction} - closing current position first"
                }
            else:
                # AI wants same direction - probably wants to add to position but we don't allow that
                print(f"  Decision: AI wants to add to {current_side} position -> HOLDING instead")
                return {
                    "operation": "hold",
                    "symbol": symbol,
                    "reasoning": f"Already have {current_side} position, cannot add more"
                }
        
        # If AI wants to open and no position exists, validate with order flow
        if ai_operation == "open":
            # Check if order flow confirms AI direction
            ai_is_long = ai_direction == "long"
            of_is_long = of_signal == "LONG"
            of_is_short = of_signal == "SHORT"
            
            # Strong confirmation: both signals align
            if (ai_is_long and of_is_long) or (not ai_is_long and of_is_short):
                # Threshold 0.5 = moderate confirmation (AI + order flow agreement sufficient)
                if of_strength > 0.5:
                    print(f"  Decision: STRONG CONFIRMATION - Both signals align with strength {of_strength:.2f}")
                    enhanced_decision = ai_decision.copy()
                    if self.scalping_mode:
                        enhanced_decision["target_portion_of_balance"] = self.scalping_position_size
                        enhanced_decision["leverage"] = self.default_leverage_scalping
                        enhanced_decision["stop_loss_percent"] = self.scalping_stop_loss
                        print(f"  [SCALPING] Fixed size={self.scalping_position_size}, leverage={self.default_leverage_scalping}x, SL={self.scalping_stop_loss}%")
                    else:
                        enhanced_decision["target_portion_of_balance"] = min(
                            ai_decision.get("target_portion_of_balance", 0.05) * 1.2,
                            0.1
                        )
                    enhanced_decision["reasoning"] = f"{ai_decision.get('reasoning', '')} + ORDER FLOW CONFIRMATION: {of_reason}"
                    return enhanced_decision
                else:
                    print(f"  Decision: Weak confirmation (strength {of_strength:.2f}), proceeding cautiously")
                    scalping_decision = ai_decision.copy()
                    if self.scalping_mode:
                        scalping_decision["target_portion_of_balance"] = self.scalping_position_size
                        scalping_decision["leverage"] = self.default_leverage_scalping
                        scalping_decision["stop_loss_percent"] = self.scalping_stop_loss
                    return scalping_decision
            
            # Contradiction: signals disagree
            elif (ai_is_long and of_is_short) or (not ai_is_long and of_is_long):
                # Threshold 0.7 = strong order flow overrides AI (safety mechanism)
                if of_strength > 0.7:
                    print(f"  Decision: STRONG CONTRADICTION - Order flow suggests opposite direction, BLOCKING trade")
                    return {
                        "operation": "hold",
                        "symbol": symbol,
                        "reasoning": f"Signal conflict: AI suggests {ai_direction} but order flow shows {of_signal} with strength {of_strength:.2f}"
                    }
                else:
                    print(f"  Decision: Weak contradiction, following AI but reducing position size")
                    reduced_decision = ai_decision.copy()
                    reduced_decision["target_portion_of_balance"] = ai_decision.get("target_portion_of_balance", 0.05) * 0.7
                    reduced_decision["reasoning"] = f"{ai_decision.get('reasoning', '')} (Order flow weak contradiction: {of_signal})"
                    return reduced_decision
            
            # Order flow neutral
            else:
                print(f"  Decision: Order flow neutral, following AI")
                neutral_decision = ai_decision.copy()
                if self.scalping_mode:
                    neutral_decision["target_portion_of_balance"] = self.scalping_position_size
                    neutral_decision["leverage"] = self.default_leverage_scalping
                    neutral_decision["stop_loss_percent"] = self.scalping_stop_loss
                return neutral_decision
        
        # Default: follow AI
        return ai_decision

    def run_strategy(self):
        """Main trading loop con strategia scalping"""
        print(f"\n[AdvancedTradingBot] Starting strategy loop (cycle every {self.cycle_interval}s)")
        print(f"[AdvancedTradingBot] Testnet: {self.testnet}")
        print(f"[AdvancedTradingBot] Scalping Mode: {self.scalping_mode}")
        print(f"[AdvancedTradingBot] Symbols: {self.symbols_to_monitor}\n")
        
        cycle_count = 0
        
        while True:
            cycle_count += 1
            cycle_start = time.time()
            print(f"\n{'='*80}")
            print(f"[CYCLE {cycle_count}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*80}")
            
            try:
                # Aggiorna watchlist giornaliera
                self._update_daily_watchlist()
                
                # Get current account status
                account_status = self.hyperliquid_trader.get_account_status()
                
                # Log account snapshot
                snapshot_id = db_utils.log_account_status(account_status)
                print(f"[DB] Account snapshot logged: ID={snapshot_id}")
                
                # Filtra simboli con watchlist
                symbols_to_process = self.symbols_to_monitor
                if self.daily_watchlist:
                    symbols_to_process = [s for s in self.symbols_to_monitor if s in self.daily_watchlist]
                    print(f"[WATCHLIST] Simboli filtrati: {symbols_to_process}")
                
                # Monitoraggio posizioni attive OGNI CICLO (ora allineato a 15min)
                if len(self.active_trades) > 0:
                    print(f"\n[MONITORING] Rivedo {len(self.active_trades)} posizioni attive...")
                    
                    for active_symbol in list(self.active_trades.keys()):
                        try:
                            # Trova posizione attuale
                            current_pos = None
                            for pos in account_status.get("open_positions", []):
                                if pos.get("symbol") == active_symbol:
                                    current_pos = pos
                                    break
                            
                            if not current_pos:
                                # Posizione chiusa esternamente (SL o altro)
                                print(f"[MONITORING] {active_symbol} posizione chiusa esternamente")
                                del self.active_trades[active_symbol]
                                continue
                            
                            # Calcola PnL e tempo
                            pnl_usd = float(current_pos.get("pnl_usd", 0))
                            trade_info = self.active_trades[active_symbol]
                            target_profit = trade_info.get("target_profit_usd", 0.5)
                            max_hold = trade_info.get("max_hold_minutes", 60)
                            opened_at = trade_info.get("opened_at")
                            
                            minutes_held = 0
                            if opened_at:
                                minutes_held = (datetime.now() - opened_at).total_seconds() / 60
                            
                            print(f"[MONITORING] {active_symbol}: PnL=${pnl_usd:.2f}, Target=${target_profit:.2f}, Tempo={minutes_held:.0f}/{max_hold}min")
                            
                            # Controllo timeout + break-even
                            if minutes_held >= max_hold and pnl_usd >= -0.01:
                                print(f"[MONITORING] {active_symbol} TIMEOUT RAGGIUNTO - Chiudo in break-even")
                                timeout_signal = {
                                    "operation": "close",
                                    "symbol": active_symbol,
                                    "direction": current_pos.get("side", "long").lower(),
                                    "reasoning": f"Timeout {max_hold}min raggiunto, chiusura break-even (PnL=${pnl_usd:.2f})"
                                }
                                result = self.hyperliquid_trader.execute_signal(timeout_signal)
                                print(f"[{active_symbol}] Timeout close: {result}")
                                del self.active_trades[active_symbol]
                                self.closed_positions_cooldown[active_symbol] = datetime.now()
                                
                                db_utils.log_bot_operation(
                                    timeout_signal,
                                    system_prompt="TIMEOUT_BREAKEVEN",
                                    indicators=None,
                                    news_text=None,
                                    sentiment=None,
                                    forecasts=None
                                )
                                continue
                            
                            # Chiusura automatica se target raggiunto
                            if pnl_usd >= target_profit:
                                print(f"[MONITORING] {active_symbol} TARGET RAGGIUNTO - Chiudo con profitto")
                                profit_signal = {
                                    "operation": "close",
                                    "symbol": active_symbol,
                                    "direction": current_pos.get("side", "long").lower(),
                                    "reasoning": f"Target profit ${target_profit:.2f} raggiunto (PnL=${pnl_usd:.2f})"
                                }
                                result = self.hyperliquid_trader.execute_signal(profit_signal)
                                print(f"[{active_symbol}] Profit close: {result}")
                                del self.active_trades[active_symbol]
                                self.closed_positions_cooldown[active_symbol] = datetime.now()
                                
                                db_utils.log_bot_operation(
                                    profit_signal,
                                    system_prompt="TARGET_PROFIT",
                                    indicators=None,
                                    news_text=None,
                                    sentiment=None,
                                    forecasts=None
                                )
                                continue
                            
                            # Valutazione AI per posizioni aperte
                            # Get order flow
                            order_flow_data = self.get_order_flow_summary(active_symbol)
                            if not order_flow_data:
                                print(f"[{active_symbol}] Order flow non disponibile, skip")
                                continue
                            
                            # Prompt specifico monitoring
                            monitoring_prompt = self._build_monitoring_prompt(
                                active_symbol,
                                current_pos,
                                order_flow_data
                            )
                            
                            # Chiamata AI
                            print(f"[{active_symbol}] Richiedo decisione AI per posizione...")
                            ai_decision = previsione_trading_agent(monitoring_prompt)
                            ai_decision["symbol"] = active_symbol
                            
                            # Normalizza chiavi
                            if "reason" in ai_decision:
                                ai_decision["reasoning"] = ai_decision.pop("reason")
                            
                            print(f"[{active_symbol}] AI Monitoring: {ai_decision.get('operation')}")
                            
                            # Controllo sicurezza - mai chiudere in perdita
                            if ai_decision.get("operation") == "close":
                                if pnl_usd < 0:
                                    print(f"[{active_symbol}] BLOCCO: AI vuole chiudere ma PnL negativo (${pnl_usd:.2f})")
                                    ai_decision["operation"] = "hold"
                                    ai_decision["reasoning"] = f"Bloccato: no chiusura in perdita (PnL=${pnl_usd:.2f})"
                                else:
                                    # Chiusura consentita
                                    result = self.hyperliquid_trader.execute_signal(ai_decision)
                                    print(f"[{active_symbol}] AI close: {result}")
                                    del self.active_trades[active_symbol]
                                    self.closed_positions_cooldown[active_symbol] = datetime.now()
                                    
                                    db_utils.log_bot_operation(
                                        ai_decision,
                                        system_prompt=monitoring_prompt,
                                        indicators=None,
                                        news_text=None,
                                        sentiment=None,
                                        forecasts=None
                                    )
                                    continue
                            
                            # Hold: log comunque
                            print(f"[{active_symbol}] HOLD - {ai_decision.get('reasoning', 'N/A')}")
                            
                        except Exception as e:
                            print(f"[ERROR] Monitoring {active_symbol}: {e}")
                            db_utils.log_error(e, context={"symbol": active_symbol, "monitoring": True}, source="advanced_trading_bot")
                
                # Process symbols (solo se NON hanno già posizione)
                for symbol in symbols_to_process:
                    try:
                        # Skip se posizione già aperta
                        if symbol in self.active_trades:
                            print(f"\n[{symbol}] SKIP - Posizione già aperta (monitorata ogni ciclo)")
                            continue
                        
                        # Check cooldown dopo chiusura
                        if symbol in self.closed_positions_cooldown:
                            cooldown_end = self.closed_positions_cooldown[symbol]
                            minutes_since_close = (datetime.now() - cooldown_end).total_seconds() / 60
                            if minutes_since_close < self.cooldown_minutes:
                                remaining = self.cooldown_minutes - minutes_since_close
                                print(f"\n[{symbol}] COOLDOWN - {remaining:.1f} min remaining")
                                continue
                        
                        print(f"\n[{symbol}] Processing...")
                        
                        # Get order flow data
                        order_flow_data = self.get_order_flow_summary(symbol)
                        if not order_flow_data:
                            print(f"[{symbol}] Insufficient order flow data, skipping")
                            continue
                        
                        print(f"[{symbol}] Order Flow Signal: {order_flow_data['signal']} (Strength: {order_flow_data['strength']:.2f})")
                        
                        # Build enhanced prompt with order flow
                        system_prompt, indicators_json, news_txt, sentiment_json, forecasts_json, of_data = \
                            self.build_enhanced_prompt(symbol, account_status, order_flow_data)
                        
                        # Get AI decision
                        print(f"[{symbol}] Requesting AI decision...")
                        ai_decision = previsione_trading_agent(system_prompt)
                        
                        # CRITICAL: Force correct symbol (AI sometimes returns wrong one)
                        ai_decision["symbol"] = symbol
                        
                        # CRITICAL: Normalize "reason" to "reasoning" if present
                        if "reason" in ai_decision and "reasoning" not in ai_decision:
                            ai_decision["reasoning"] = ai_decision.pop("reason")
                        
                        # Pre-validation: controlla target_profit_usd minimo ($2.00)
                        if ai_decision.get("operation") == "open":
                            target = ai_decision.get("target_profit_usd", 0)
                            if target < self.min_target_profit_usd:
                                print(f"[{symbol}] REJECTED: target_profit ${target:.2f} < ${self.min_target_profit_usd} (minimum required)")
                                ai_decision = {
                                    "operation": "hold",
                                    "symbol": symbol,
                                    "reasoning": f"Target profit too low (${target:.2f} < ${self.min_target_profit_usd})"
                                }
                        
                        print(f"[{symbol}] AI Decision: {ai_decision.get('operation')} {ai_decision.get('direction', '')} | Reasoning: {ai_decision.get('reasoning', 'N/A')[:80]}...")
                        
                        # Merge signals
                        final_decision = self.merge_signals(symbol, ai_decision, order_flow_data, account_status)
                        
                        # Validazione e tracking per aperture
                        if final_decision.get("operation") == "open":
                            # Valida target_profit_usd
                            target_profit = final_decision.get("target_profit_usd", 0)
                            max_hold = final_decision.get("max_hold_minutes", 60)
                            
                            if target_profit < self.min_target_profit_usd:
                                print(f"[{symbol}] SCARTATO - target_profit_usd={target_profit} < ${self.min_target_profit_usd}")
                                final_decision = {
                                    "operation": "hold",
                                    "symbol": symbol,
                                    "reasoning": f"Target profit troppo basso (${target_profit:.2f} < ${self.min_target_profit_usd})"
                                }
                            else:
                                # Esegui apertura
                                print(f"[{symbol}] EXECUTING OPEN: target=${target_profit:.2f}, max_hold={max_hold}min")
                                execution_result = self.hyperliquid_trader.execute_signal(final_decision)
                                print(f"[{symbol}] Execution Result: {execution_result}")
                                
                                # Registra in active_trades
                                if "error" not in str(execution_result).lower():
                                    # Recupera mark_price attuale per entry tracking
                                    mids = self.hyperliquid_trader.info.all_mids()
                                    mark_price = float(mids.get(symbol, 0))
                                    
                                    self.active_trades[symbol] = {
                                        "entry_px": mark_price,
                                        "target_profit_usd": target_profit,
                                        "max_hold_minutes": max_hold,
                                        "opened_at": datetime.now(),
                                        "direction": final_decision.get("direction", "long")
                                    }
                                    print(f"[{symbol}] Registrato in active_trades: {self.active_trades[symbol]}")
                                
                                # Update account status
                                account_status = self.hyperliquid_trader.get_account_status()
                        
                        elif final_decision.get("operation") == "close":
                            # Chiusura posizione
                            print(f"[{symbol}] EXECUTING CLOSE")
                            execution_result = self.hyperliquid_trader.execute_signal(final_decision)
                            print(f"[{symbol}] Execution Result: {execution_result}")
                            
                            # Rimuovi da active_trades se presente
                            if symbol in self.active_trades:
                                del self.active_trades[symbol]
                                print(f"[{symbol}] Rimosso da active_trades")
                            
                            # Registra cooldown per evitare re-entry immediato
                            self.closed_positions_cooldown[symbol] = datetime.now()
                            print(f"[{symbol}] Cooldown {self.cooldown_minutes} min attivato")
                            
                            # Update account status
                            account_status = self.hyperliquid_trader.get_account_status()
                        
                        else:
                            print(f"[{symbol}] HOLD - Reason: {final_decision.get('reasoning', 'N/A')}")
                        
                        # Log operation to database
                        op_id = db_utils.log_bot_operation(
                            final_decision,
                            system_prompt=system_prompt,
                            indicators=indicators_json,
                            news_text=news_txt,
                            sentiment=sentiment_json,
                            forecasts=forecasts_json
                        )
                        print(f"[DB] Operation logged: ID={op_id}")
                        
                    except Exception as e:
                        print(f"[ERROR] {symbol}: {e}")
                        db_utils.log_error(e, context={
                            "symbol": symbol,
                            "cycle": cycle_count,
                            "order_flow_data": order_flow_data if 'order_flow_data' in locals() else None
                        }, source="advanced_trading_bot")
                
                # Save final account status
                with open('account_status_old.json', 'w') as f:
                    json.dump(account_status.get('open_positions', []), f, indent=4)
                
                final_snapshot_id = db_utils.log_account_status(account_status)
                print(f"[DB] Final snapshot logged: ID={final_snapshot_id}")
                
            except Exception as e:
                print(f"[ERROR] Cycle {cycle_count} failed: {e}")
                db_utils.log_error(e, context={"cycle": cycle_count}, source="advanced_trading_bot")
            
            # Wait for next cycle
            cycle_elapsed = time.time() - cycle_start
            sleep_time = max(0, self.cycle_interval - cycle_elapsed)
            
            print(f"\n[CYCLE {cycle_count}] Completed in {cycle_elapsed:.1f}s")
            if sleep_time > 0:
                print(f"[CYCLE {cycle_count}] Sleeping {sleep_time:.1f}s until next cycle...")
                time.sleep(sleep_time)


if __name__ == "__main__":
    # Load credentials
    PRIVATE_KEY = os.getenv("PRIVATE_KEY")
    WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
    
    if not PRIVATE_KEY or not WALLET_ADDRESS:
        raise RuntimeError("PRIVATE_KEY or WALLET_ADDRESS missing in .env")
    
    # Configuration
    TESTNET = True
    # Lista completa simboli da monitorare (watchlist AI sceglierà da questa pool)
    SYMBOLS = ['BTC', 'ETH', 'SOL', 'ARB', 'AVAX', 'MATIC', 'OP', 'DOGE', 'XRP', 'ADA', 'DOT', 'LINK', 'UNI', 'AAVE', 'LTC']
    CYCLE_INTERVAL = 900  # 15 minutes - aligned with analysis timeframe
    
    # Create and run bot
    bot = AdvancedTradingBot(
        secret_key=PRIVATE_KEY,
        account_address=WALLET_ADDRESS,
        symbols_to_monitor=SYMBOLS,
        testnet=TESTNET,
        cycle_interval=CYCLE_INTERVAL
    )
    
    # Configurazione scalping ottimizzata per profittabilità
    bot.scalping_mode = True
    bot.take_profit_percent = 3.0  # 3% per coprire fee e generare profitto netto
    bot.scalping_stop_loss = 2.5  # 2.5% per evitare trigger su noise con leverage 6x
    bot.scalping_position_size = 0.12  # 12% per gestione rischio
    bot.default_leverage_scalping = 6  # 6x leverage per rischio bilanciato
    bot.min_target_profit_usd = 2.0  # Minimo $2 per coprire fee (0.7%) + slippage
    bot.cooldown_minutes = 30  # 30 min cooldown dopo chiusura per evitare overtrading
    
    print("\n" + "="*80)
    print("ADVANCED TRADING BOT WITH ORDER FLOW ANALYTICS")
    print("="*80)
    print(f"Mode: {'TESTNET' if TESTNET else 'MAINNET'}")
    print(f"Symbols: {SYMBOLS}")
    print(f"Cycle Interval: {CYCLE_INTERVAL}s")
    print(f"Dashboard: http://127.0.0.1:8055 (run dashboard_simple.py separately)")
    print("="*80 + "\n")
    
    try:
        bot.run_strategy()
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        print("Goodbye!")
    except Exception as e:
        print(f"\n\n[FATAL ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
