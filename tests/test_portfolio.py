"""Tests for portfolio CRUD operations."""

from __future__ import annotations

import json

from whatsapp_automation.db import configure_engine, get_session_factory, reset_engine
from whatsapp_automation.config import get_settings
from whatsapp_automation.portfolio import (
    add_holding,
    get_portfolio,
    get_transactions,
    remove_holding,
)


def _setup_db(database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    configure_engine(database_url)


class TestAddHolding:
    def test_creates_new_holding(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        result = json.loads(add_holding("user1", "RELIANCE", 10, 2500.0, "Reliance Industries"))

        assert result["status"] == "success"
        assert result["action"] == "buy"
        assert result["symbol"] == "RELIANCE"
        assert result["quantity_added"] == 10
        assert result["price_per_share"] == 2500.0
        assert result["total_cost"] == 25000.0
        assert result["new_holding_quantity"] == 10
        assert result["new_avg_price"] == 2500.0

    def test_updates_avg_price_on_second_buy(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "TCS", 10, 3000.0, "TCS Ltd")
        result = json.loads(add_holding("user1", "TCS", 10, 4000.0))

        assert result["new_holding_quantity"] == 20
        assert result["new_avg_price"] == 3500.0  # (10*3000 + 10*4000) / 20

    def test_rejects_zero_quantity(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        result = json.loads(add_holding("user1", "INFY", 0, 1500.0))
        assert "error" in result

    def test_rejects_negative_price(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        result = json.loads(add_holding("user1", "INFY", 10, -100))
        assert "error" in result

    def test_normalizes_symbol_to_uppercase(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "reliance", 5, 2500.0)
        portfolio = json.loads(get_portfolio("user1"))
        assert portfolio["holdings"][0]["symbol"] == "RELIANCE"


class TestRemoveHolding:
    def test_sells_partial_position(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "RELIANCE", 10, 2500.0)
        result = json.loads(remove_holding("user1", "RELIANCE", 5, 2800.0))

        assert result["status"] == "success"
        assert result["action"] == "sell"
        assert result["quantity_sold"] == 5
        assert result["remaining_quantity"] == 5
        assert result["profit_per_share"] == 300.0
        assert result["total_profit"] == 1500.0

    def test_sells_full_position(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "TCS", 10, 3000.0)
        result = json.loads(remove_holding("user1", "TCS", 10, 3500.0))

        assert result["status"] == "success"
        assert result["remaining_quantity"] == 0
        assert "fully closed" in result["note"]

        # Portfolio should be empty now
        portfolio = json.loads(get_portfolio("user1"))
        assert portfolio["holdings"] == []

    def test_rejects_overselling(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "INFY", 5, 1500.0)
        result = json.loads(remove_holding("user1", "INFY", 10, 1600.0))
        assert "error" in result
        assert "only hold 5" in result["error"]

    def test_rejects_unknown_symbol(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        result = json.loads(remove_holding("user1", "UNKNOWN", 5, 100.0))
        assert "error" in result


class TestGetPortfolio:
    def test_empty_portfolio(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        result = json.loads(get_portfolio("user1"))
        assert result["holdings"] == []
        assert "empty" in result["message"].lower()

    def test_multiple_holdings(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "RELIANCE", 10, 2500.0, "Reliance Industries")
        add_holding("user1", "TCS", 5, 3000.0, "TCS Ltd")

        result = json.loads(get_portfolio("user1"))
        assert result["total_stocks"] == 2
        assert result["total_invested"] == 40000.0  # 25000 + 15000

        symbols = [h["symbol"] for h in result["holdings"]]
        assert "RELIANCE" in symbols
        assert "TCS" in symbols

    def test_portfolios_are_user_scoped(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "RELIANCE", 10, 2500.0)
        add_holding("user2", "TCS", 5, 3000.0)

        p1 = json.loads(get_portfolio("user1"))
        p2 = json.loads(get_portfolio("user2"))

        assert p1["total_stocks"] == 1
        assert p1["holdings"][0]["symbol"] == "RELIANCE"
        assert p2["total_stocks"] == 1
        assert p2["holdings"][0]["symbol"] == "TCS"


class TestGetTransactions:
    def test_empty_transactions(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        result = json.loads(get_transactions("user1"))
        assert result["transactions"] == []

    def test_records_buy_and_sell(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        add_holding("user1", "RELIANCE", 10, 2500.0)
        remove_holding("user1", "RELIANCE", 5, 2800.0)

        result = json.loads(get_transactions("user1"))
        assert result["total"] == 2

        actions = [t["action"] for t in result["transactions"]]
        assert "buy" in actions
        assert "sell" in actions

    def test_respects_limit(self, database_url, monkeypatch):
        _setup_db(database_url, monkeypatch)
        for i in range(5):
            add_holding("user1", f"STOCK{i}", 1, 100.0)

        result = json.loads(get_transactions("user1", limit=3))
        assert result["total"] == 3
