"""Tests for TradeSimulator."""

from datetime import datetime

import pandas as pd
import pytest

from src.backtesting.simulator import TradeSimulator, SimulatedOrder


class TestTradeSimulator:

    @pytest.fixture
    def sim(self):
        return TradeSimulator(fee_percent=0.1, slippage_percent=0.05)

    def test_market_order_filled_immediately(self, sim):
        order = sim.create_market_order("BTC/USDT", "buy", 1.0, 50000.0,
                                        datetime(2024, 1, 1))
        assert order.status == "filled"
        assert order.filled_price is not None

    def test_buy_slippage_increases_price(self, sim):
        order = sim.create_market_order("BTC/USDT", "buy", 1.0, 50000.0,
                                        datetime(2024, 1, 1))
        assert order.filled_price > 50000.0

    def test_sell_slippage_decreases_price(self, sim):
        order = sim.create_market_order("BTC/USDT", "sell", 1.0, 50000.0,
                                        datetime(2024, 1, 1))
        assert order.filled_price < 50000.0

    def test_limit_order_pending(self, sim):
        order = sim.create_limit_order("BTC/USDT", "buy", 1.0, 49000.0,
                                       datetime(2024, 1, 1))
        assert order.status == "pending"
        assert order.filled_price is None

    def test_limit_buy_fills_on_dip(self, sim):
        sim.create_limit_order("BTC/USDT", "buy", 1.0, 49000.0,
                               datetime(2024, 1, 1))
        candle = pd.Series({"open": 50000, "high": 50500, "low": 48500, "close": 49500})
        filled = sim.check_pending_orders(candle, datetime(2024, 1, 1, 1))
        assert len(filled) == 1
        assert filled[0].filled_price == 49000.0

    def test_limit_sell_fills_on_pump(self, sim):
        sim.create_limit_order("BTC/USDT", "sell", 1.0, 52000.0,
                               datetime(2024, 1, 1))
        candle = pd.Series({"open": 50000, "high": 53000, "low": 49500, "close": 52500})
        filled = sim.check_pending_orders(candle, datetime(2024, 1, 1, 1))
        assert len(filled) == 1

    def test_stop_loss_triggers(self, sim):
        sim.create_stop_order("BTC/USDT", "sell", 1.0, 48000.0,
                              datetime(2024, 1, 1), "stop_loss")
        candle = pd.Series({"open": 50000, "high": 50500, "low": 47000, "close": 48500})
        filled = sim.check_pending_orders(candle, datetime(2024, 1, 1, 1))
        assert len(filled) == 1
        assert filled[0].order_type == "stop_loss"

    def test_cancel_order(self, sim):
        order = sim.create_limit_order("BTC/USDT", "buy", 1.0, 49000.0,
                                       datetime(2024, 1, 1))
        assert sim.cancel_order(order.order_id)
        assert order.status == "cancelled"

    def test_cancel_all_pending(self, sim):
        sim.create_limit_order("BTC/USDT", "buy", 1.0, 49000.0, datetime(2024, 1, 1))
        sim.create_limit_order("ETH/USDT", "buy", 10.0, 3000.0, datetime(2024, 1, 1))
        cancelled = sim.cancel_all_pending()
        assert cancelled == 2

    def test_cancel_all_by_symbol(self, sim):
        sim.create_limit_order("BTC/USDT", "buy", 1.0, 49000.0, datetime(2024, 1, 1))
        sim.create_limit_order("ETH/USDT", "buy", 10.0, 3000.0, datetime(2024, 1, 1))
        cancelled = sim.cancel_all_pending(symbol="BTC/USDT")
        assert cancelled == 1
        assert len(sim.get_pending_orders()) == 1

    def test_fee_calculation(self, sim):
        fee = sim.calculate_fee(1.0, 50000.0)
        assert abs(fee - 50.0) < 0.01  # 0.1% of 50000

    def test_reset_clears_state(self, sim):
        sim.create_market_order("BTC/USDT", "buy", 1.0, 50000.0, datetime(2024, 1, 1))
        sim.reset()
        assert len(sim.orders) == 0

    def test_unique_order_ids(self, sim):
        o1 = sim.create_market_order("BTC/USDT", "buy", 1.0, 50000.0, datetime(2024, 1, 1))
        o2 = sim.create_market_order("BTC/USDT", "buy", 1.0, 50000.0, datetime(2024, 1, 1))
        assert o1.order_id != o2.order_id

    def test_get_filled_orders(self, sim):
        sim.create_market_order("BTC/USDT", "buy", 1.0, 50000.0, datetime(2024, 1, 1))
        sim.create_limit_order("BTC/USDT", "buy", 1.0, 49000.0, datetime(2024, 1, 1))
        filled = sim.get_filled_orders()
        assert len(filled) == 1
