import json
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI

from config.settings import settings
from mcp_server.server import run_scalp_backtest, get_hourly_breakdown, optimize_scalp_parameters

logger = logging.getLogger("StrategyAgent")


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_scalp_backtest",
            "description": "Run a micro-scalping backtest for Nifty options with specified lookback seconds, sampling checks, and trigger sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lookback_seconds": {
                        "type": "integer",
                        "description": "How many seconds to look back (e.g. 5, 10, 15, 30)"
                    },
                    "check_count": {
                        "type": "integer",
                        "description": "Number of price checks in the lookback window"
                    },
                    "trigger_diff": {
                        "type": "number",
                        "description": "Price displacement in rupees to trigger entry (e.g. 2.0, 2.5, 3.0)"
                    },
                    "target_diff": {
                        "type": "number",
                        "description": "Target profit in rupees (e.g. 2.5)"
                    },
                    "sl_diff": {
                        "type": "number",
                        "description": "Stop loss in rupees (e.g. 1.5)"
                    },
                    "start_hour": {
                        "type": "string",
                        "description": "Start time in HH:MM (e.g. 09:15 or 11:00)"
                    },
                    "end_hour": {
                        "type": "string",
                        "description": "End time in HH:MM (e.g. 15:30 or 14:00)"
                    },
                    "trade_instrument": {
                        "type": "string",
                        "enum": ["CE", "PE", "BOTH"],
                        "description": "Which option to scalp"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hourly_breakdown",
            "description": "Get performance breakdown segmented across each 1-hour session from 09:15 to 15:30.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lookback_seconds": {"type": "integer"},
                    "trigger_diff": {"type": "number"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_scalp_parameters",
            "description": "Perform parameter grid search to find the top performing combinations of lookback seconds and trigger diffs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top parameter sets to return"
                    }
                }
            }
        }
    }
]


SYSTEM_PROMPT = """You are an elite Indian Quantitative Trading & Options Scalping Assistant powered by Gemini.
Your core expertise is backtesting and optimizing Nifty 50 Options scalping strategies in sideways / range-bound market regimes.

You understand the mechanics of:
1. Micro-movements (₹2.00 to ₹3.00 oscillations in CE/PE premiums during sideways markets).
2. Time-of-day market personality:
   - 09:15 - 10:15: High volatility opening whipsaws (scalping here is dangerous).
   - 10:15 - 11:15: Settling phase.
   - 11:15 - 14:00: Golden range-bound sweet spot (ideal for ₹2-₹3 mean-reversion scalping!).
   - 14:15 - 15:30: Afternoon gamma moves and close-out trends (risk of rapid adverse trend).
3. Capital: ₹1,00,000 with strict risk management, Indian taxes (STT, GST, Exchange turnover, SEBI), brokerage, and slippage.

When answering the user:
- You can explain results in friendly Hinglish or English as per user preference.
- Proactively call available tools to run backtests, analyze hourly performance, or optimize parameters.
- Provide crisp, data-backed insights with clear recommendations on best lookback seconds, trigger size, and optimal trading hours.
"""


class StrategyAgent:
    """
    AI Quant Research Agent that connects to Gemini via the custom endpoint proxy
    and autonomously orchestrates backtesting and parameter optimization.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.base_url = base_url or settings.llm.base_url
        self.api_key = api_key or settings.llm.api_key
        self.model = model or settings.llm.model
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            default_headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )

    def chat(self, user_message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Processes user query with autonomous tool execution.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            # First LLM call
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=AGENT_TOOLS,
                tool_choice="auto",
                temperature=0.2
            )
            msg = response.choices[0].message

            # Check if model made tool calls
            if msg.tool_calls:
                messages.append(msg)
                for tool_call in msg.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments or "{}")

                    # Dispatch tool
                    if fn_name == "run_scalp_backtest":
                        tool_result = run_scalp_backtest(**fn_args)
                    elif fn_name == "get_hourly_breakdown":
                        tool_result = get_hourly_breakdown(**fn_args)
                    elif fn_name == "optimize_scalp_parameters":
                        tool_result = optimize_scalp_parameters(**fn_args)
                    else:
                        tool_result = json.dumps({"error": f"Unknown tool: {fn_name}"})

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })

                # Second LLM call with tool results
                second_resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.2
                )
                second_msg = second_resp.choices[0].message
                content = second_msg.content or getattr(second_msg, "reasoning_content", "")
                return content or "Analysis complete."

            final_content = msg.content or getattr(msg, "reasoning_content", "")
            return final_content or "No response received."

        except Exception as e:
            logger.error(f"Error in Gemini agent: {e}")
            return f"Agent encountered an error calling endpoint: {e}"
