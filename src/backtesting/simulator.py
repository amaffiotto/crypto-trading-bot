"""Trade simulator for backtesting with advanced order types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class SimulatedOrder:
    """Represents a simulated order."""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market', 'limit', 'stop_loss', 'take_profit'
    quantity: float
    price: Optional[float]  # None for market orders
    stop_price: Optional[float]  # For stop orders
    status: str = "pending"  # pending, filled, cancelled
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = None


class TradeSimulator:
    """
    Simulates order execution with support for various order types.
    
    Provides realistic simulation of market, limit, stop-loss, and 
    take-profit orders.
    """
    
    def __init__(self, fee_percent: float = 0.1, slippage_percent: float = 0.05):
        """
        Initialize trade simulator.
        
        Args:
            fee_percent: Trading fee as percentage
            slippage_percent: Slippage as percentage
        """
        self.fee_percent = fee_percent / 100
        self.slippage_percent = slippage_percent / 100
        self.orders: List[SimulatedOrder] = []
        self._order_counter = 0
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        return f"SIM-{self._order_counter:06d}"
    
    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage based on order side."""
        if side == "buy":
            return price * (1 + self.slippage_percent)
        else:
            return price * (1 - self.slippage_percent)
    
    def create_market_order(self, symbol: str, side: str, 
                           quantity: float, current_price: float,
                           timestamp: datetime) -> SimulatedOrder:
        """
        Create and immediately fill a market order.
        
        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            quantity: Order quantity
            current_price: Current market price
            timestamp: Order timestamp
            
        Returns:
            Filled SimulatedOrder
        """
        filled_price = self._apply_slippage(current_price, side)
        
        order = SimulatedOrder(
            order_id=self._generate_order_id(),
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            price=None,
            stop_price=None,
            status="filled",
            created_at=timestamp,
            filled_at=timestamp,
            filled_price=filled_price
        )
        
        self.orders.append(order)
        return order
    
    def create_limit_order(self, symbol: str, side: str,
                          quantity: float, limit_price: float,
                          timestamp: datetime) -> SimulatedOrder:
        """
        Create a limit order.
        
        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            quantity: Order quantity
            limit_price: Limit price
            timestamp: Order timestamp
            
        Returns:
            Pending SimulatedOrder
        """
        order = SimulatedOrder(
            order_id=self._generate_order_id(),
            symbol=symbol,
            side=side,
            order_type="limit",
            quantity=quantity,
            price=limit_price,
            stop_price=None,
            status="pending",
            created_at=timestamp
        )
        
        self.orders.append(order)
        return order
    
    def create_stop_order(self, symbol: str, side: str,
                         quantity: float, stop_price: float,
                         timestamp: datetime,
                         order_type: str = "stop_loss") -> SimulatedOrder:
        """
        Create a stop order (stop-loss or take-profit).
        
        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            quantity: Order quantity
            stop_price: Trigger price
            timestamp: Order timestamp
            order_type: 'stop_loss' or 'take_profit'
            
        Returns:
            Pending SimulatedOrder
        """
        order = SimulatedOrder(
            order_id=self._generate_order_id(),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=None,
            stop_price=stop_price,
            status="pending",
            created_at=timestamp
        )
        
        self.orders.append(order)
        return order
    
    def check_pending_orders(self, candle: pd.Series, timestamp: datetime) -> List[SimulatedOrder]:
        """
        Check if any pending orders should be filled.
        
        Args:
            candle: OHLCV candle data
            timestamp: Current timestamp
            
        Returns:
            List of filled orders
        """
        filled = []
        high = candle["high"]
        low = candle["low"]
        
        for order in self.orders:
            if order.status != "pending":
                continue
            
            should_fill = False
            fill_price = None
            
            if order.order_type == "limit":
                # Limit buy fills if price drops to limit
                if order.side == "buy" and low <= order.price:
                    should_fill = True
                    fill_price = order.price
                # Limit sell fills if price rises to limit
                elif order.side == "sell" and high >= order.price:
                    should_fill = True
                    fill_price = order.price
            
            elif order.order_type in ["stop_loss", "take_profit"]:
                # Stop buy triggers if price rises to stop
                if order.side == "buy" and high >= order.stop_price:
                    should_fill = True
                    fill_price = self._apply_slippage(order.stop_price, "buy")
                # Stop sell triggers if price drops to stop
                elif order.side == "sell" and low <= order.stop_price:
                    should_fill = True
                    fill_price = self._apply_slippage(order.stop_price, "sell")
            
            if should_fill:
                order.status = "filled"
                order.filled_at = timestamp
                order.filled_price = fill_price
                filled.append(order)
        
        return filled
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        for order in self.orders:
            if order.order_id == order_id and order.status == "pending":
                order.status = "cancelled"
                return True
        return False
    
    def cancel_all_pending(self, symbol: Optional[str] = None) -> int:
        """Cancel all pending orders, optionally for a specific symbol."""
        cancelled = 0
        for order in self.orders:
            if order.status == "pending":
                if symbol is None or order.symbol == symbol:
                    order.status = "cancelled"
                    cancelled += 1
        return cancelled
    
    def get_pending_orders(self, symbol: Optional[str] = None) -> List[SimulatedOrder]:
        """Get all pending orders."""
        pending = [o for o in self.orders if o.status == "pending"]
        if symbol:
            pending = [o for o in pending if o.symbol == symbol]
        return pending
    
    def get_filled_orders(self, symbol: Optional[str] = None) -> List[SimulatedOrder]:
        """Get all filled orders."""
        filled = [o for o in self.orders if o.status == "filled"]
        if symbol:
            filled = [o for o in filled if o.symbol == symbol]
        return filled
    
    def calculate_fee(self, quantity: float, price: float) -> float:
        """Calculate fee for a trade."""
        return quantity * price * self.fee_percent
    
    def reset(self) -> None:
        """Reset simulator state."""
        self.orders.clear()
        self._order_counter = 0
