from openai import OpenAI
from dotenv import load_dotenv
import os
import json 

load_dotenv()
# OpenRouter configuration
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY missing in .env")
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

def previsione_trading_agent(prompt):
    response = client.chat.completions.create(
    model="anthropic/claude-3.5-sonnet",
    messages=[{"role": "user", "content": prompt}],
    response_format={
        "type": "json_schema",
        "json_schema": {
        "name": "trade_operation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
            "operation": {
                "type": "string",
                "description": "Type of trading operation to perform",
                "enum": [
                "open",
                "close",
                "hold"
                ]
            },
            "symbol": {
                "type": "string",
                "description": "The cryptocurrency symbol to act on",
                "enum": [
                "BTC",
                "ETH",
                "SOL",
                "ARB",
                "AVAX",
                "MATIC",
                "OP",
                "DOGE",
                "XRP",
                "ADA",
                "DOT",
                "LINK",
                "UNI",
                "AAVE",
                "LTC"
                ]
            },
            "direction": {
                "type": "string",
                "description": "Trade direction: betting the price goes up (long) or down (short). For hold, may be omitted.",
                "enum": [
                "long",
                "short"
                ]
            },
            "target_portion_of_balance": {
                "type": "number",
                "description": "Fraction of (for open: balance, for close: position) to allocate/close; from 0.0 to 1.0 inclusive",
                "minimum": 0,
                "maximum": 1
            },
            "leverage": {
                "type": "number",
                "description": "Leverage multiplier (risk/reward, 1-10). Only applicable for 'open'.",
                "minimum": 1,
                "maximum": 10
            },
            "stop_loss_percent":{
                "type": "number",
                "description":"Stop loss percentage",
                "minimum": 1,
                "maximum": 3
            },
            "target_profit_usd": {
                "type": "number",
                "description": "Target profit in USD for scalping strategy (minimum 2.00 to cover fees)",
                "minimum": 2.00
            },
            "max_hold_minutes": {
                "type": "integer",
                "description": "Maximum minutes to hold position before timeout (45-90 for 15min cycles)",
                "minimum": 45,
                "maximum": 90
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of the trading decision",
                "minLength": 1,
                "maxLength": 500
            }
            },
            "required": [
            "operation",
            "symbol",
            "reasoning"
            ],
            "additionalProperties": False
        }
        }
    }
    )
    
    # Parse AI response
    raw_response = json.loads(response.choices[0].message.content)
    
    # Normalize response: handle "reason" vs "reasoning" inconsistency
    normalized = {
        "operation": raw_response.get("operation", "hold"),
        "symbol": raw_response.get("symbol", "BTC"),
        "reasoning": raw_response.get("reasoning") or raw_response.get("reason", "No reason provided")
    }
    
    # Add optional fields if present
    if "direction" in raw_response:
        normalized["direction"] = raw_response["direction"]
    if "target_portion_of_balance" in raw_response:
        normalized["target_portion_of_balance"] = raw_response["target_portion_of_balance"]
    if "leverage" in raw_response:
        normalized["leverage"] = raw_response["leverage"]
    if "stop_loss_percent" in raw_response:
        normalized["stop_loss_percent"] = raw_response["stop_loss_percent"]
    if "target_profit_usd" in raw_response:
        normalized["target_profit_usd"] = raw_response["target_profit_usd"]
    if "max_hold_minutes" in raw_response:
        normalized["max_hold_minutes"] = raw_response["max_hold_minutes"]
    
    return normalized