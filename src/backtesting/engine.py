"""Backtesting engine for strategy evaluation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class Trade:
    """Represents a completed trade."""
    entry_time: datetime
    exit_time: datetime
    side: str  # 'long' or 'short'
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    fee: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    """Represents an open position."""
    side: str  # 'long' or 'short'
    entry_time: datetime
    entry_price: float
    quantity: float
    entry_fee: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    strategy_name: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    trades: List[Trade]
    equity_curve: pd.DataFrame
    parameters: Dict[str, Any]
    
    @property
    def total_return(self) -> float:
        """Total return as a decimal."""
        return (self.final_capital - self.initial_capital) / self.initial_capital
    
    @property
    def total_return_pct(self) -> float:
        """Total return as percentage."""
        return self.total_return * 100
    
    @property
    def num_trades(self) -> int:
        """Total number of trades."""
        return len(self.trades)
    
    @property
    def winning_trades(self) -> int:
        """Number of winning trades."""
        return sum(1 for t in self.trades if t.pnl > 0)
    
    @property
    def losing_trades(self) -> int:
        """Number of losing trades."""
        return sum(1 for t in self.trades if t.pnl <= 0)
    
    @property
    def win_rate(self) -> float:
        """Win rate as percentage."""
        if not self.trades:
            return 0.0
        return (self.winning_trades / len(self.trades)) * 100


class BacktestEngine:
    """
    Engine for backtesting trading strategies.
    
    Simulates strategy execution on historical data with realistic
    order execution, fees, and slippage.
    """
    
    def __init__(self, 
                 initial_capital: float = 10000.0,
                 fee_percent: float = 0.1,
                 slippage_percent: float = 0.05,
                 position_size: float = 1.0):
        """
        Initialize backtesting engine.
        
        Args:
            initial_capital: Starting capital in quote currency
            fee_percent: Trading fee as percentage (e.g., 0.1 = 0.1%)
            slippage_percent: Simulated slippage as percentage
            position_size: Fraction of capital to use per trade (0.0 to 1.0)
        """
        self.initial_capital = initial_capital
        self.fee_percent = fee_percent / 100  # Convert to decimal
        self.slippage_percent = slippage_percent / 100
        self.position_size = min(1.0, max(0.01, position_size))
        
        self._reset()
    
    def _reset(self) -> None:
        """Reset engine state."""
        self.capital = self.initial_capital
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []
    
    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to execution price."""
        if side == "buy":
            return price * (1 + self.slippage_percent)
        else:
            return price * (1 - self.slippage_percent)
    
    def _calculate_fee(self, amount: float) -> float:
        """Calculate fee for a trade."""
        return amount * self.fee_percent
    
    def _open_position(self, timestamp: datetime, price: float, 
                       side: str, signal: TradeSignal) -> None:
        """Open a new position."""
        # Apply slippage
        exec_price = self._apply_slippage(price, "buy" if side == "long" else "sell")
        
        # Calculate position size
        trade_capital = self.capital * self.position_size
        fee = self._calculate_fee(trade_capital)
        available = trade_capital - fee
        quantity = available / exec_price
        
        self.position = Position(
            side=side,
            entry_time=timestamp,
            entry_price=exec_price,
            quantity=quantity,
            entry_fee=fee,
            metadata=signal.metadata.copy()
        )
        
        logger.debug(f"Opened {side} position: {quantity:.6f} @ {exec_price:.2f}")
    
    def _close_position(self, timestamp: datetime, price: float,
                        signal: Optional[TradeSignal] = None) -> Trade:
        """Close the current position."""
        if not self.position:
            raise ValueError("No position to close")
        
        # Apply slippage
        side = "sell" if self.position.side == "long" else "buy"
        exec_price = self._apply_slippage(price, side)
        
        # Calculate P&L
        if self.position.side == "long":
            gross_pnl = (exec_price - self.position.entry_price) * self.position.quantity
        else:
            gross_pnl = (self.position.entry_price - exec_price) * self.position.quantity
        
        exit_value = self.position.quantity * exec_price
        exit_fee = self._calculate_fee(exit_value)
        total_fee = self.position.entry_fee + exit_fee
        net_pnl = gross_pnl - total_fee
        
        entry_value = self.position.quantity * self.position.entry_price
        pnl_percent = (net_pnl / entry_value) * 100
        
        # Update capital
        self.capital += net_pnl
        
        trade = Trade(
            entry_time=self.position.entry_time,
            exit_time=timestamp,
            side=self.position.side,
            entry_price=self.position.entry_price,
            exit_price=exec_price,
            quantity=self.position.quantity,
            pnl=net_pnl,
            pnl_percent=pnl_percent,
            fee=total_fee,
            metadata={
                **self.position.metadata,
                "exit_signal": signal.metadata if signal else {}
            }
        )
        
        self.trades.append(trade)
        self.position = None
        
        logger.debug(f"Closed position: PnL = {net_pnl:.2f} ({pnl_percent:.2f}%)")
        
        return trade
    
    def _calculate_equity(self, price: float) -> float:
        """Calculate current equity including unrealized P&L."""
        if not self.position:
            return self.capital
        
        if self.position.side == "long":
            unrealized = (price - self.position.entry_price) * self.position.quantity
        else:
            unrealized = (self.position.entry_price - price) * self.position.quantity
        
        return self.capital + unrealized
    
    def run(self, strategy: BaseStrategy, data: pd.DataFrame,
            symbol: str = "UNKNOWN", timeframe: str = "1h",
            progress_callback: Optional[Callable[[int, int], None]] = None) -> BacktestResult:
        """
        Run backtest on historical data.
        
        Args:
            strategy: Strategy instance to test
            data: DataFrame with OHLCV data
            symbol: Trading pair symbol
            timeframe: Data timeframe
            progress_callback: Optional callback(current, total) for progress
            
        Returns:
            BacktestResult with performance metrics and trades
        """
        self._reset()
        
        # Validate data
        strategy.validate_data(data)
        
        # Calculate indicators
        df = strategy.calculate_indicators(data.copy())
        
        # Get required history
        min_history = strategy.get_required_history()
        
        logger.info(f"Starting backtest: {strategy.name} on {symbol} ({len(df)} candles)")
        
        # Iterate through each candle
        for i in range(min_history, len(df)):
            row = df.iloc[i]
            timestamp = row["timestamp"]
            close_price = row["close"]
            high_price = row["high"]
            low_price = row["low"]
            
            # Check stop loss and take profit FIRST (before new signals)
            if self.position:
                stopped_out = False
                
                # Check stop loss (use low price for long positions)
                if self.position.side == "long" and self.position.metadata.get("stop_loss"):
                    stop_loss = self.position.metadata["stop_loss"]
                    if low_price <= stop_loss:
                        self._close_position(timestamp, stop_loss, None)
                        stopped_out = True
                        logger.debug(f"Stop loss hit at {stop_loss:.2f}")
                
                # Check take profit (use high price for long positions)
                if not stopped_out and self.position and self.position.metadata.get("take_profit"):
                    take_profit = self.position.metadata["take_profit"]
                    if high_price >= take_profit:
                        self._close_position(timestamp, take_profit, None)
                        stopped_out = True
                        logger.debug(f"Take profit hit at {take_profit:.2f}")
                
                if stopped_out:
                    # Record equity after stop/TP and continue
                    equity = self._calculate_equity(close_price)
                    self.equity_curve.append({
                        "timestamp": timestamp,
                        "equity": equity,
                        "capital": self.capital,
                        "price": close_price,
                        "position": None
                    })
                    if progress_callback and i % 100 == 0:
                        progress_callback(i - min_history, len(df) - min_history)
                    continue
            
            # Get signal from strategy
            signal = strategy.analyze(df, i)
            
            # Process signal
            if signal.signal == Signal.BUY and not self.position:
                self._open_position(timestamp, close_price, "long", signal)
                # Store stop loss and take profit in position metadata
                if self.position:
                    if signal.stop_loss:
                        self.position.metadata["stop_loss"] = signal.stop_loss
                    if signal.take_profit:
                        self.position.metadata["take_profit"] = signal.take_profit
            
            elif signal.signal == Signal.SELL and self.position:
                self._close_position(timestamp, close_price, signal)
            
            # Record equity
            equity = self._calculate_equity(close_price)
            self.equity_curve.append({
                "timestamp": timestamp,
                "equity": equity,
                "capital": self.capital,
                "price": close_price,
                "position": self.position.side if self.position else None
            })
            
            # Progress callback
            if progress_callback and i % 100 == 0:
                progress_callback(i - min_history, len(df) - min_history)
        
        # Close any open position at the end
        if self.position:
            self._close_position(
                df.iloc[-1]["timestamp"],
                df.iloc[-1]["close"]
            )
        
        # Build result
        equity_df = pd.DataFrame(self.equity_curve)
        
        result = BacktestResult(
            strategy_name=strategy.name,
            symbol=symbol,
            timeframe=timeframe,
            start_date=df.iloc[min_history]["timestamp"],
            end_date=df.iloc[-1]["timestamp"],
            initial_capital=self.initial_capital,
            final_capital=self.capital,
            trades=self.trades.copy(),
            equity_curve=equity_df,
            parameters=strategy.params
        )
        
        logger.info(f"Backtest complete: {result.num_trades} trades, "
                   f"Return: {result.total_return_pct:.2f}%")
        
        return result
