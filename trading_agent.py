from openai import OpenAI
from dotenv import load_dotenv
import os
import json 

load_dotenv()
# read api key
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

def previsione_trading_agent(prompt):
    response = client.chat.completions.create(
        model="openai/gpt-4o",  # o qualsiasi altro modello disponibile su OpenRouter
        messages=[
            {
                "role": "system",
                "content": "You are a trading agent. Always respond with valid JSON following the specified schema."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
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
                            "enum": ["open", "close", "hold"]
                        },
                        "symbol": {
                            "type": "string",
                            "description": "The cryptocurrency symbol to act on",
                            "enum": ["BTC", "ETH", "SOL"]
                        },
                        "direction": {
                            "type": "string",
                            "description": "Trade direction: betting the price goes up (long) or down (short). For hold, may be omitted.",
                            "enum": ["long", "short"]
                        },
                        "target_portion_of_balance": {
                            "type": "number",
                            "description": "Fraction of (for open: balance, for close: position) to allocate/close; from 0.0 to 1.0 inclusive"
                        },
                        "leverage": {
                            "type": "number",
                            "description": "Leverage multiplier (risk/reward, 1-10). Only applicable for 'open'."
                        },
                        "stop_loss_percent": {
                            "type": "number",
                            "description": "Stop loss percentage"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief explanation of the trading decision"
                        }
                    },
                    "required": [
                        "operation",
                        "symbol",
                        "direction",
                        "target_portion_of_balance",
                        "leverage",
                        "reason",
                        "stop_loss_percent"
                    ],
                    "additionalProperties": False
                }
            }
        },
        temperature=0.7
    )
    return json.loads(response.choices[0].message.content)