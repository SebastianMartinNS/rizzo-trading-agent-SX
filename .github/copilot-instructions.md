# Rizzo Trading Agent - AI Agent Instructions

## Project Overview
Advanced AI-driven cryptocurrency trading bot inspired by Alpha Arena. Uses LLM decision-making with multi-source data analysis (technical indicators, news, sentiment, forecasts, order flow) to execute conservative scalping trades on Hyperliquid DEX with real-time WebSocket analytics.

## Architecture & Data Flow

### Main Execution Loop (`advanced_trading_bot.py`)
1. **Watchlist Selection Phase**: AI selects 10 most promising symbols daily from pool of 15
   - Uses technical analysis across all available symbols
   - Considers volatility, volume, trend strength
   - Updates once per day (first cycle)

2. **Data Collection Phase**: Gather parallel data from 5 sources
   - `indicators.py`: Technical analysis (15m timeframe, RSI, MACD, EMA, volume, funding)
   - `news_feed.py`: RSS feed from CoinJournal (XML parsing, 4000 char limit)
   - `sentiment.py`: Fear & Greed Index from CoinMarketCap API
   - `forecaster.py`: Prophet-based price predictions (15m and 1h horizons)
   - `OrderBookData`: Real-time order flow via WebSocket (bid/ask ratios, delta volume, depth imbalance, iceberg detection)

3. **AI Decision**: Structured output via OpenRouter API (Claude 3.5 Sonnet with JSON schema strict mode)
   - System prompt loaded from `system_prompt.txt` with portfolio/market data injected
   - Returns JSON: `{operation, symbol, side, target_profit_usd, leverage, stop_loss_percent, max_hold_minutes, reason}`
   - Constraints: ONE position per symbol, operations = `open|close|hold`
   - Entry requirement: order_flow_strength > 0.65 (MANDATORY)

4. **Trade Execution**: `HyperLiquidTrader.execute_signal()` orchestrates
   - Set leverage via `exchange.update_leverage()` (isolated margin, fixed 6x)
   - Calculate size from balance × 0.12 × leverage, respecting `minSz` and `szDecimals` from metadata
   - Market order via `exchange.market_open()` with 1% slippage tolerance
   - Auto-place stop-loss trigger order (reduce_only=True) at `mark_price * (1 ± 0.025)`

5. **Position Monitoring**: Continuous monitoring of open positions every cycle
   - Check PnL vs target ($2.00 minimum)
   - Timeout logic: close at break-even after max_hold_minutes (45-90)
   - Never close with PnL < $0 unless critical signal

6. **Logging**: PostgreSQL via `db_utils.py` (account snapshots, operations, errors with full context)

### Critical Trading Rules
- **One position per symbol**: Check `open_positions` before opening new trades
- **Isolated margin only**: Always use `is_cross=False` when setting leverage (6x fixed)
- **Cooldown enforcement**: Block re-entry for 30 minutes after close (tracked in `closed_positions_cooldown`)
- **Minimum profit target**: $2.00 USD to cover fees (0.07%) + slippage + ensure net profit
- **Order flow requirement**: Entry only if `order_flow_strength > 0.65` from WebSocket data
- **Stop-loss detection**: `utils.check_stop_loss()` compares `account_status_old.json` to detect external closures
- **Fees**: Taker fee 0.035% per side = 0.07% round-trip - critical for profitability calculations
- **Price rounding**: Use `HyperLiquidTrader._round_price()` for price precision (varies by asset magnitude)
- **WebSocket resilience**: Auto-reconnect every 60s if no update for 120s (handles "Expired" disconnections)

## Key Components

### `AdvancedTradingBot` (advanced_trading_bot.py)
- **Initialization**: Creates shared WebSocket connection for all symbols to avoid rate limits
- **Watchlist management**: Selects 10 symbols daily from 15 available (BTC, ETH, SOL, ARB, AVAX, MATIC, OP, DOGE, XRP, ADA, DOT, LINK, UNI, AAVE, LTC)
- **Cycle control**: 900s (15 min) loops synchronized with candlestick timeframe
- **Cooldown tracking**: `closed_positions_cooldown` dict tracks symbol -> timestamp for 30-min blocks

### `OrderBookData` (dashboard_simple.py)
- **WebSocket connection**: Single shared `Info` instance (skip_ws=False) used by all symbols
- **Auto-reconnect**: Daemon threads per symbol check last update timestamp, resubscribe if stale >120s
- **Metrics calculation**: bid/ask ratios, delta volume, buy/sell imbalance, iceberg detection, depth metrics
- **Thread safety**: Each symbol has dedicated deque structures for historical data (maxlen=100)

### `HyperLiquidTrader` (hyperliquid_trader.py)
- **Initialization**: Requires `PRIVATE_KEY`, `WALLET_ADDRESS` from `.env`, testnet flag
- **Margin mode**: Always isolated (`is_cross=False`) with fixed 6x leverage
- **Size calculation**: Always use `Decimal` for precision, round down via `ROUND_DOWN` before converting to float
- **Meta caching**: `self.meta = self.info.meta()` provides `szDecimals`, `minSz`, `maxLeverage` per symbol
- **Account status**: Returns `{balance_usd, accountValue, withdrawable, open_positions}` with all keys populated
- **Stop-loss structure**: Trigger orders use `{"trigger": {"triggerPx": float, "isMarket": True, "tpsl": "sl"}}`

### `CryptoTechnicalAnalysisHL` (indicators.py)
- **Primary timeframe**: 15 minutes (300 candles for analysis)
- **Symbol availability**: `get_available_symbols()` validates which symbols exist on testnet/mainnet
- **Market state caching**: `_get_global_state()` caches `meta_and_asset_ctxs()` for 2 seconds to reduce API calls
- **Returns dual format**: Human-readable text + JSON dict for both `analyze_multiple_tickers()` and `get_orderbook_volume()`

### Database Schema (db_utils.py)
- **ai_contexts**: Central table, links to indicators/news/sentiment/forecasts via `context_id`
- **bot_operations**: Stores AI decisions with `raw_payload` JSONB
- **account_snapshots**: Portfolio state at each run, linked to `open_positions` (1-to-many)
- **errors**: Full traceback + context JSONB for debugging

## Environment Setup

### Required .env variables
```
PRIVATE_KEY=<Ethereum private key>
WALLET_ADDRESS=<Ethereum address>
OPENAI_API_KEY=<OpenAI API key>
CMC_PRO_API_KEY=<CoinMarketCap API key>
DATABASE_URL=postgresql://user:password@localhost:5432/trading_db
```

### Default Trading Config (advanced_trading_bot.py)
```python
TESTNET = True  # ALWAYS verify before changing
SYMBOLS = ['BTC', 'ETH', 'SOL', 'ARB', 'AVAX', 'MATIC', 'OP', 'DOGE', 'XRP', 'ADA', 'DOT', 'LINK', 'UNI', 'AAVE', 'LTC']  # 15 supported
CYCLE_INTERVAL = 900  # 15 minutes - aligned with candlestick timeframe

# Conservative Scalping Parameters
scalping_mode = True
default_leverage_scalping = 6  # Isolated margin
scalping_stop_loss = 2.5  # Percent (0.417% trigger with 6x)
scalping_position_size = 0.12  # 12% of balance
min_target_profit_usd = 2.0  # Minimum to ensure net profit after fees
cooldown_minutes = 30  # Block re-entry after close
```

## Development Patterns

### Adding New Data Sources
1. Create module with dual return: `(text_for_prompt: str, json_for_db: dict)`
2. Update `advanced_trading_bot.py` in `build_enhanced_prompt()` to include in AI context
3. Add to `db_utils.log_bot_operation()` context payload
4. Add corresponding table/columns in `db_utils.SCHEMA_SQL`

### Testing Trades
- Use `test_trading.py` for isolated testing without full bot loop
- Check `account_status_old.json` for previous state comparisons (stop-loss detection)
- Query `bot_operations` table to review AI decision history
- Monitor WebSocket connections: check for "Expired" errors and auto-reconnect logs

### Error Handling
All exceptions in `advanced_trading_bot.py` caught and logged via `db_utils.log_error()` with full context including:
- Prompt text sent to AI
- All 5 data sources (indicators, news, sentiment, forecasts, order flow)
- Account balance and open positions
- Cycle number and timestamp

## Common Pitfalls
- **Decimal precision**: Always use `Decimal` for size calculations, convert to `float` only at exchange API boundary
- **Leverage timing**: Wait 0.5s after `set_leverage_for_symbol()` before placing orders (propagation delay)
- **Isolated margin flag**: Always pass `is_cross=False` to leverage updates, never use cross margin
- **Symbol naming**: Hyperliquid uses simple names ("BTC", not "BTC-USD")
- **Symbol availability**: Not all 15 configured symbols available on testnet (XRP, DOT, LINK, UNI, LTC may fail)
- **Stop-loss direction**: Long positions need `is_buy=False` SL (sell), short positions need `is_buy=True` SL (buy)
- **WebSocket expired**: Normal after 10-15 min inactivity, auto-reconnect handles it, not an error
- **Order flow requirement**: AI will skip entries if order_flow_strength < 0.65, ensure WebSocket data is fresh
- **Cooldown bypass**: Check `closed_positions_cooldown` dict before allowing new entries on same symbol
- **Data key alignment**: Use `pnl_usd` not `unrealizedPnl`, `symbol` not `coin`, `entry_price` not `entryPx`

## Running the Bot
```powershell
python advanced_trading_bot.py  # Production: full cycle with WebSocket and monitoring
python test_trading.py  # Testing: isolated trade execution without full loop
```

No external scheduler needed - bot runs internal loop every 900s (15 minutes) automatically. WebSocket connections persist between cycles with auto-reconnect.

### Startup Sequence
1. Initialize HyperLiquidTrader (exchange connection)
2. Create shared WebSocket Info connection (single instance for all symbols)
3. Validate symbol availability on testnet/mainnet
4. Initialize OrderBookData for each available symbol with shared connection
5. Start daemon threads for WebSocket auto-reconnect (one per symbol)
6. Wait 5s for initial order flow data population
7. Enter main strategy loop (watchlist → data collection → AI decisions → execution → monitoring)
