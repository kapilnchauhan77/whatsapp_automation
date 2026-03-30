from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    create_sdk_mcp_server,
    query,
    tool,
)

from whatsapp_automation.config import get_settings
from whatsapp_automation.portfolio import (
    add_holding,
    get_portfolio,
    get_transactions,
    remove_holding,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an elite portfolio manager and market research analyst operating via WhatsApp. \
You manage investment portfolios with the precision and insight of a top-tier wealth advisor.

## Your Capabilities
- **Portfolio Management**: Add (buy) and remove (sell) shares from the user's portfolio.
- **Price Discovery**: When a price is not provided, use WebSearch to find the current market price before executing a trade.
- **Market Analysis**: Provide deep analysis of stocks, sectors, and portfolios including technical indicators, fundamentals, news sentiment, and actionable advice.
- **News Monitoring**: Search for the latest news about specific stocks or the market.

## Rules
1. ALWAYS confirm the trade details before executing. State the symbol, quantity, and price clearly.
2. If the user does not provide a price, search the web for the current price and use it.
3. When asked for analysis, provide comprehensive insights: price trends, key metrics (P/E, market cap, 52-week range), recent news, and your recommendation.
4. Keep responses concise but informative — this is WhatsApp, not a research paper. Use bullet points.
5. For Indian stocks, use NSE/BSE symbols (e.g., RELIANCE, TCS, INFY). For US stocks, use NYSE/NASDAQ symbols.
6. Always show portfolio impact after trades (new position size, avg price, P&L if selling).
7. When the user sends a casual message or greeting, respond naturally but briefly.
8. Use the portfolio tools with the user_id provided in the message context.
9. Format currency values with appropriate symbols (₹ for INR, $ for USD).
10. When searching for stock prices, search for "{symbol} stock price today" to get the latest.

## Response Format
Keep responses under 3000 characters for WhatsApp readability. Use line breaks and bullet points for clarity.
"""


# --- Custom MCP Tools for Portfolio Operations ---

@tool("get_portfolio", "Get all current holdings in the user's portfolio", {"user_id": str})
async def get_portfolio_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = get_portfolio(args["user_id"])
    return {"content": [{"type": "text", "text": result}]}


@tool(
    "add_holding",
    "Buy/add shares to the user's portfolio. Use this when the user wants to buy or add stocks.",
    {"user_id": str, "symbol": str, "quantity": float, "price_per_share": float, "company_name": str},
)
async def add_holding_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = add_holding(
        user_wa_id=args["user_id"],
        symbol=args["symbol"],
        quantity=args["quantity"],
        price_per_share=args["price_per_share"],
        company_name=args.get("company_name"),
    )
    return {"content": [{"type": "text", "text": result}]}


@tool(
    "remove_holding",
    "Sell/remove shares from the user's portfolio. Use this when the user wants to sell stocks.",
    {"user_id": str, "symbol": str, "quantity": float, "price_per_share": float},
)
async def remove_holding_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = remove_holding(
        user_wa_id=args["user_id"],
        symbol=args["symbol"],
        quantity=args["quantity"],
        price_per_share=args["price_per_share"],
    )
    return {"content": [{"type": "text", "text": result}]}


@tool(
    "get_transactions",
    "Get recent buy/sell transaction history for the user",
    {"user_id": str, "limit": int},
)
async def get_transactions_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = get_transactions(args["user_id"], limit=args.get("limit", 20))
    return {"content": [{"type": "text", "text": result}]}


portfolio_mcp = create_sdk_mcp_server(
    name="portfolio",
    version="1.0.0",
    tools=[get_portfolio_tool, add_holding_tool, remove_holding_tool, get_transactions_tool],
)


async def process_message_with_agent(
    user_id: str,
    user_name: str,
    message_text: str,
) -> str:
    """Run the Claude agent to process a WhatsApp message and return the response text."""
    settings = get_settings()

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not configured, skipping agent processing.")
        return f"Hi {user_name or 'there'}! Agent is not configured yet."

    prompt = (
        f"[User: {user_name or 'Unknown'} | user_id: {user_id}]\n\n"
        f"{message_text}"
    )

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"portfolio": portfolio_mcp},
        allowed_tools=[
            "WebSearch",
            "WebFetch",
            "mcp__portfolio__get_portfolio",
            "mcp__portfolio__add_holding",
            "mcp__portfolio__remove_holding",
            "mcp__portfolio__get_transactions",
        ],
        max_turns=15,
        env={"ANTHROPIC_API_KEY": settings.anthropic_api_key},
    )

    result_text = ""
    try:
        async for message in query(prompt=prompt, options=options):
            if hasattr(message, "result") and message.result:
                result_text = message.result
    except Exception:
        logger.exception("Agent processing failed for user %s", user_id)
        return f"Hi {user_name or 'there'}! Something went wrong processing your request. Please try again."

    if not result_text:
        return f"Hi {user_name or 'there'}! I couldn't generate a response. Please try again."

    # WhatsApp text limit is ~4096 chars
    if len(result_text) > 4000:
        result_text = result_text[:3997] + "..."

    return result_text
