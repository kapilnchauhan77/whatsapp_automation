from __future__ import annotations

import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from whatsapp_automation.db import get_session_factory
from whatsapp_automation.models import PortfolioHolding, PortfolioTransaction


def get_portfolio(user_wa_id: str) -> str:
    """Return all holdings for a user as JSON."""
    factory = get_session_factory()
    with factory() as session:
        holdings = session.scalars(
            select(PortfolioHolding)
            .where(PortfolioHolding.user_wa_id == user_wa_id)
            .order_by(PortfolioHolding.symbol)
        ).all()

        if not holdings:
            return json.dumps({"holdings": [], "message": "Portfolio is empty."})

        total_invested = 0.0
        items = []
        for h in holdings:
            invested = h.quantity * h.avg_price
            total_invested += invested
            items.append({
                "symbol": h.symbol,
                "company_name": h.company_name,
                "quantity": h.quantity,
                "avg_price": round(h.avg_price, 2),
                "invested_value": round(invested, 2),
            })

        return json.dumps({
            "holdings": items,
            "total_invested": round(total_invested, 2),
            "total_stocks": len(items),
        })


def add_holding(
    user_wa_id: str,
    symbol: str,
    quantity: float,
    price_per_share: float,
    company_name: str | None = None,
) -> str:
    """Buy shares — creates or updates a holding and logs a transaction."""
    symbol = symbol.upper().strip()
    if quantity <= 0 or price_per_share <= 0:
        return json.dumps({"error": "Quantity and price must be positive."})

    factory = get_session_factory()
    with factory() as session:
        holding = session.scalar(
            select(PortfolioHolding).where(
                PortfolioHolding.user_wa_id == user_wa_id,
                PortfolioHolding.symbol == symbol,
            )
        )

        if holding is None:
            holding = PortfolioHolding(
                user_wa_id=user_wa_id,
                symbol=symbol,
                company_name=company_name,
                quantity=quantity,
                avg_price=price_per_share,
            )
            session.add(holding)
        else:
            total_cost = (holding.quantity * holding.avg_price) + (quantity * price_per_share)
            holding.quantity += quantity
            holding.avg_price = total_cost / holding.quantity
            if company_name:
                holding.company_name = company_name

        session.flush()

        txn = PortfolioTransaction(
            holding_id=holding.id,
            user_wa_id=user_wa_id,
            symbol=symbol,
            action="buy",
            quantity=quantity,
            price_per_share=price_per_share,
            total_value=round(quantity * price_per_share, 2),
        )
        session.add(txn)
        session.commit()

        return json.dumps({
            "status": "success",
            "action": "buy",
            "symbol": symbol,
            "quantity_added": quantity,
            "price_per_share": price_per_share,
            "total_cost": round(quantity * price_per_share, 2),
            "new_holding_quantity": holding.quantity,
            "new_avg_price": round(holding.avg_price, 2),
        })


def remove_holding(
    user_wa_id: str,
    symbol: str,
    quantity: float,
    price_per_share: float,
) -> str:
    """Sell shares — reduces holding quantity and logs a transaction."""
    symbol = symbol.upper().strip()
    if quantity <= 0 or price_per_share <= 0:
        return json.dumps({"error": "Quantity and price must be positive."})

    factory = get_session_factory()
    with factory() as session:
        holding = session.scalar(
            select(PortfolioHolding).where(
                PortfolioHolding.user_wa_id == user_wa_id,
                PortfolioHolding.symbol == symbol,
            )
        )

        if holding is None:
            return json.dumps({"error": f"No holding found for {symbol}."})

        if quantity > holding.quantity:
            return json.dumps({
                "error": f"Cannot sell {quantity} shares. You only hold {holding.quantity} of {symbol}."
            })

        txn = PortfolioTransaction(
            holding_id=holding.id,
            user_wa_id=user_wa_id,
            symbol=symbol,
            action="sell",
            quantity=quantity,
            price_per_share=price_per_share,
            total_value=round(quantity * price_per_share, 2),
        )
        session.add(txn)

        profit_per_share = price_per_share - holding.avg_price
        holding.quantity -= quantity

        if holding.quantity == 0:
            session.delete(holding)
            session.commit()
            return json.dumps({
                "status": "success",
                "action": "sell",
                "symbol": symbol,
                "quantity_sold": quantity,
                "price_per_share": price_per_share,
                "total_proceeds": round(quantity * price_per_share, 2),
                "profit_per_share": round(profit_per_share, 2),
                "total_profit": round(profit_per_share * quantity, 2),
                "remaining_quantity": 0,
                "note": f"Position in {symbol} fully closed.",
            })

        session.commit()
        return json.dumps({
            "status": "success",
            "action": "sell",
            "symbol": symbol,
            "quantity_sold": quantity,
            "price_per_share": price_per_share,
            "total_proceeds": round(quantity * price_per_share, 2),
            "profit_per_share": round(profit_per_share, 2),
            "total_profit": round(profit_per_share * quantity, 2),
            "remaining_quantity": holding.quantity,
            "remaining_avg_price": round(holding.avg_price, 2),
        })


def get_transactions(user_wa_id: str, limit: int = 20) -> str:
    """Return recent transactions for a user."""
    factory = get_session_factory()
    with factory() as session:
        txns = session.scalars(
            select(PortfolioTransaction)
            .where(PortfolioTransaction.user_wa_id == user_wa_id)
            .order_by(PortfolioTransaction.created_at.desc())
            .limit(limit)
        ).all()

        if not txns:
            return json.dumps({"transactions": [], "message": "No transactions yet."})

        items = []
        for t in txns:
            items.append({
                "symbol": t.symbol,
                "action": t.action,
                "quantity": t.quantity,
                "price_per_share": t.price_per_share,
                "total_value": t.total_value,
                "date": t.created_at.isoformat(),
            })

        return json.dumps({"transactions": items, "total": len(items)})
