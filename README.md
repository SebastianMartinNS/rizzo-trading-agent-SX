# Trading Agent
![](/img.jpg)

Fork del [Trading Agent](https://github.com/RizzoAI-Academy/trading-agent) sviluppato da [Rizzo AI Academy](https://www.youtube.com/@RizzoAI-Academy), progetto ispirato a [Alpha Arena](https://nof1.ai/).

## Contributi e Sperimentazioni

Questo repository contiene esperimenti e modifiche al progetto originale. L'obiettivo è esplorare approcci alternativi e condividere risultati con la community.

### Crediti Progetto Originale

Ringraziamenti a **Rizzo AI Academy** per:
- Architettura base e concept del trading agent
- Integrazione Hyperliquid DEX
- Documentazione e tutorial
- Approccio open source

### Modifiche Sperimentali

Questo fork include test su:
- Order flow analytics tramite WebSocket
- Gestione watchlist multipli
- Parametri scalping conservativi
- Monitoring posizioni
- Auto-reconnect connessioni

**Nota**: Queste modifiche sono sperimentali. La community è invitata a testare, migliorare e contribuire con feedback.

## Architettura

### Base (main.py.old)
Implementazione originale: 3 simboli, 4 data sources, cicli 15 minuti.

### Variante Sperimentale (advanced_trading_bot.py)
Test con:
- Order flow analytics WebSocket
- Watchlist 15 simboli
- Isolated margin 6x
- Cooldown 30 min
- Monitoring posizioni

## Features in Test

- Order flow analytics (bid/ask ratios, delta volume, depth imbalance)
- Analisi multi-sorgente (indicators, news, sentiment, forecasts, orderbook)
- Parametri scalping (leverage 6x, SL 2.5%, size 12%)
- WebSocket auto-reconnect
- Watchlist selection
- Cooldown system
- Architettura modulare

## Configurazione

### Environment Variables (.env)
```bash
PRIVATE_KEY=<Ethereum private key>
WALLET_ADDRESS=<Ethereum address>
OPENAI_API_KEY=<OpenAI API key per Claude 3.5 Sonnet via OpenRouter>
CMC_PRO_API_KEY=<CoinMarketCap API key>
DATABASE_URL=postgresql://user:password@localhost:5432/trading_db
```

### Default Config (advanced_trading_bot.py)
```python
TESTNET = True  # Sempre verificare prima di modificare
SYMBOLS = ['BTC', 'ETH', 'SOL', 'ARB', 'AVAX', 'MATIC', 'OP', 'DOGE', 'XRP', 'ADA', 'DOT', 'LINK', 'UNI', 'AAVE', 'LTC']
CYCLE_INTERVAL = 900  # 15 minuti

# Parametri Scalping Conservativo
LEVERAGE = 6  # Isolated margin
STOP_LOSS = 2.5  # Percentuale
POSITION_SIZE = 12  # Percentuale balance
TARGET_PROFIT = 2.00  # USD minimo
COOLDOWN = 30  # Minuti post-close
```

## Esecuzione

### Production
```powershell
python advanced_trading_bot.py
```

### Testing Isolato
```powershell
python test_trading.py
```

### Dashboard Standalone (opzionale)
```powershell
python dashboard_simple.py
python orderbook_dashboard.py
```

## File Principali

- `advanced_trading_bot.py`: Entry point produzione, loop principale con watchlist selection
- `hyperliquid_trader.py`: Exchange API wrapper, execution layer
- `trading_agent.py`: OpenRouter API client, structured output JSON schema
- `dashboard_simple.py`: OrderBookData class con WebSocket management
- `indicators.py`: Technical analysis (RSI, MACD, EMA, volume, funding)
- `news_feed.py`: RSS feed parser (CoinJournal)
- `sentiment.py`: Fear & Greed Index (CoinMarketCap)
- `forecaster.py`: Prophet-based price predictions
- `db_utils.py`: PostgreSQL logging (snapshots, operations, errors)
- `system_prompt.txt`: AI trading instructions template

## Strategia Trading

### Entry Requirements
- Order flow strength > 0.65 (required)
- Conferma indicatori tecnici
- Sentiment coerente
- Forecast allineato
- Nessun cooldown attivo (30 min)

### Position Management
- Hold time target: 45-90 minuti
- Close quando: target raggiunto O timeout+break-even
- NEVER close con PnL < $0 (salvo segnale critico)
- Un solo trade per simbolo contemporaneamente

### Risk Management
- Isolated margin 6x per trade
- Stop loss 2.5% (trigger effettivo 0.417% con leverage)
- Position size 12% del balance disponibile
- Target profit minimo $2.00 per coprire fee (0.07%) + slippage

## Documentazione

- `BUG_REPORT.md`: Bug rilevati e fix applicati
- `TIMING_ANALYSIS_REPORT.md`: Analisi timing e cicli
- `PROMPT_ALIGNMENT_REPORT.md`: Allineamento configurazioni
- `.github/copilot-instructions.md`: Istruzioni sviluppo

## Contribuire

Questo progetto è sperimentale e necessita di:
- Test su diverse condizioni di mercato
- Feedback su parametri e configurazioni
- Miglioramenti architetturali
- Bug fix e ottimizzazioni
- Documentazione e best practices

La community è invitata a contribuire con pull request, issue e discussioni per migliorare il progetto originale.

## Risorse

**Progetto Originale**
- Repository: [RizzoAI-Academy/trading-agent](https://github.com/RizzoAI-Academy/trading-agent)
- Video: [Trading Agent Tutorial](https://www.youtube.com/watch?v=Vrl2Ar_SvSo&t=45s)
- Autore: [Rizzo AI Academy](https://www.youtube.com/@RizzoAI-Academy)

**Ispirazione**
- [Alpha Arena](https://nof1.ai/) - AI-driven trading competition platform

## Licenza

Questo progetto è distribuito sotto licenza MIT.

---

> Fork sperimentale basato sul lavoro di Rizzo AI Academy
