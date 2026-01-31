"""Live trading engine for executing strategies in real-time."""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import pandas as pd

from src.core.config import ConfigManager
from src.core.exchange import ExchangeManager
from src.core.data_manager import DataManager
from src.strategies.base import BaseStrategy, Signal, TradeSignal
from src.notifications.telegram import TelegramNotifier, create_telegram_notifier
from src.notifications.discord import DiscordNotifier, create_discord_notifier
from src.utils.logger import get_logger

logger = get_logger()


class TradingMode(Enum):
    """Trading execution mode."""
    LIVE = "live"           # Real orders on exchange
    PAPER = "paper"         # Simulated orders (paper trading)
    DRY_RUN = "dry_run"     # Log signals but don't execute


@dataclass
class Position:
    """Represents an open trading position."""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperBalance:
    """Simulated balance for paper trading."""
    currency: str
    free: float
    used: float = 0.0
    
    @property
    def total(self) -> float:
        return self.free + self.used


@dataclass 
class TradeRecord:
    """Record of an executed trade."""
    timestamp: datetime
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    fee: float
    pnl: Optional[float] = None
    mode: str = "live"


class LiveTradingEngine:
    """
    Engine for executing trading strategies in real-time.
    
    Supports three modes:
    - LIVE: Execute real orders on the exchange
    - PAPER: Simulate orders with virtual balance
    - DRY_RUN: Only log signals without execution
    """
    
    def __init__(self, 
                 config: ConfigManager,
                 exchange_manager: Optional[ExchangeManager] = None,
                 mode: TradingMode = TradingMode.PAPER):
        """
        Initialize live trading engine.
        
        Args:
            config: Configuration manager
            exchange_manager: Exchange manager instance
            mode: Trading mode (LIVE, PAPER, DRY_RUN)
        """
        self.config = config
        self.exchange_manager = exchange_manager or ExchangeManager()
        self.data_manager = DataManager(exchange_manager=self.exchange_manager)
        self.mode = mode
        
        # State
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeRecord] = []
        self.paper_balances: Dict[str, PaperBalance] = {}
        
        # Running state
        self._running = False
        self._stop_event = asyncio.Event()
        
        # Callbacks
        self._on_trade_callback: Optional[Callable] = None
        self._on_signal_callback: Optional[Callable] = None
        
        # Notifications
        self.telegram: Optional[TelegramNotifier] = None
        self.discord: Optional[DiscordNotifier] = None
        self._setup_notifications()
        
        logger.info(f"Live trading engine initialized in {mode.value} mode")
    
    def _setup_notifications(self) -> None:
        """Setup notification services from config."""
        config_dict = {
            "notifications": self.config.notifications_config
        }
        self.telegram = create_telegram_notifier(config_dict)
        self.discord = create_discord_notifier(config_dict)
    
    def set_paper_balance(self, currency: str, amount: float) -> None:
        """
        Set paper trading balance for a currency.
        
        Args:
            currency: Currency code (e.g., 'USDT', 'BTC')
            amount: Balance amount
        """
        self.paper_balances[currency] = PaperBalance(currency=currency, free=amount)
        logger.info(f"Paper balance set: {amount} {currency}")
    
    def get_balance(self, exchange_id: str, currency: str) -> float:
        """
        Get balance for a currency.
        
        Args:
            exchange_id: Exchange identifier
            currency: Currency code
            
        Returns:
            Available balance
        """
        if self.mode == TradingMode.PAPER:
            balance = self.paper_balances.get(currency)
            return balance.free if balance else 0.0
        else:
            try:
                balances = self.exchange_manager.fetch_balance(exchange_id)
                return balances.get(currency, {}).get('free', 0.0)
            except Exception as e:
                logger.error(f"Error fetching balance: {e}")
                return 0.0
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol."""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Check if there's an open position for a symbol."""
        return symbol in self.positions
    
    async def _execute_order(self, exchange_id: str, symbol: str, 
                             side: str, quantity: float,
                             order_type: str = "market",
                             price: Optional[float] = None) -> Optional[Dict]:
        """
        Execute an order on the exchange.
        
        Args:
            exchange_id: Exchange identifier
            symbol: Trading pair
            side: 'buy' or 'sell'
            quantity: Order quantity
            order_type: 'market' or 'limit'
            price: Price for limit orders
            
        Returns:
            Order result or None if failed
        """
        if self.mode == TradingMode.DRY_RUN:
            logger.info(f"[DRY RUN] Would execute {side} {quantity} {symbol} @ {order_type}")
            return {"status": "dry_run", "price": price}
        
        if self.mode == TradingMode.PAPER:
            # Simulate order execution
            current_price = self._get_current_price(exchange_id, symbol)
            if current_price is None:
                logger.error(f"Could not get price for {symbol}")
                return None
            
            exec_price = current_price * (1.001 if side == "buy" else 0.999)  # Simulated slippage
            fee = quantity * exec_price * 0.001  # 0.1% fee
            
            # Update paper balances
            base, quote = symbol.split('/')
            
            if side == "buy":
                cost = quantity * exec_price + fee
                if self.paper_balances.get(quote, PaperBalance(quote, 0)).free < cost:
                    logger.error(f"Insufficient {quote} balance for buy")
                    return None
                
                self.paper_balances[quote].free -= cost
                if base not in self.paper_balances:
                    self.paper_balances[base] = PaperBalance(base, 0)
                self.paper_balances[base].free += quantity
                
            else:  # sell
                if self.paper_balances.get(base, PaperBalance(base, 0)).free < quantity:
                    logger.error(f"Insufficient {base} balance for sell")
                    return None
                
                self.paper_balances[base].free -= quantity
                if quote not in self.paper_balances:
                    self.paper_balances[quote] = PaperBalance(quote, 0)
                self.paper_balances[quote].free += (quantity * exec_price - fee)
            
            logger.info(f"[PAPER] Executed {side} {quantity} {symbol} @ {exec_price:.2f}")
            
            return {
                "status": "filled",
                "price": exec_price,
                "quantity": quantity,
                "fee": fee,
                "mode": "paper"
            }
        
        # LIVE mode
        try:
            order = self.exchange_manager.create_order(
                exchange_id, symbol, order_type, side, quantity, price
            )
            logger.info(f"[LIVE] Order executed: {order}")
            return order
        except Exception as e:
            logger.error(f"Error executing order: {e}")
            return None
    
    def _get_current_price(self, exchange_id: str, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            ticker = self.exchange_manager.fetch_ticker(exchange_id, symbol)
            return ticker.get('last') or ticker.get('close')
        except Exception as e:
            logger.error(f"Error fetching price: {e}")
            return None
    
    async def open_position(self, exchange_id: str, symbol: str,
                           side: str, quantity: float,
                           stop_loss: Optional[float] = None,
                           take_profit: Optional[float] = None) -> bool:
        """
        Open a new position.
        
        Args:
            exchange_id: Exchange identifier
            symbol: Trading pair
            side: 'long' or 'short'
            quantity: Position size
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            
        Returns:
            True if position opened successfully
        """
        if self.has_position(symbol):
            logger.warning(f"Already have position for {symbol}")
            return False
        
        order_side = "buy" if side == "long" else "sell"
        result = await self._execute_order(exchange_id, symbol, order_side, quantity)
        
        if result is None:
            return False
        
        price = result.get('price', 0)
        fee = result.get('fee', 0)
        
        # Record position
        self.positions[symbol] = Position(
            symbol=symbol,
            side=side,
            entry_price=price,
            quantity=quantity,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        # Record trade
        self.trade_history.append(TradeRecord(
            timestamp=datetime.now(),
            symbol=symbol,
            side=order_side,
            order_type="market",
            quantity=quantity,
            price=price,
            fee=fee,
            mode=self.mode.value
        ))
        
        logger.info(f"Opened {side} position: {quantity} {symbol} @ {price:.2f}")
        
        # Send notification
        await self._notify_trade(order_side, symbol, price, quantity)
        
        return True
    
    async def close_position(self, exchange_id: str, symbol: str,
                            reason: str = "signal") -> Optional[float]:
        """
        Close an existing position.
        
        Args:
            exchange_id: Exchange identifier
            symbol: Trading pair
            reason: Reason for closing
            
        Returns:
            Realized P&L or None if failed
        """
        position = self.positions.get(symbol)
        if not position:
            logger.warning(f"No position to close for {symbol}")
            return None
        
        order_side = "sell" if position.side == "long" else "buy"
        result = await self._execute_order(exchange_id, symbol, order_side, position.quantity)
        
        if result is None:
            return None
        
        exit_price = result.get('price', 0)
        fee = result.get('fee', 0)
        
        # Calculate P&L
        if position.side == "long":
            pnl = (exit_price - position.entry_price) * position.quantity - fee
        else:
            pnl = (position.entry_price - exit_price) * position.quantity - fee
        
        # Record trade
        self.trade_history.append(TradeRecord(
            timestamp=datetime.now(),
            symbol=symbol,
            side=order_side,
            order_type="market",
            quantity=position.quantity,
            price=exit_price,
            fee=fee,
            pnl=pnl,
            mode=self.mode.value
        ))
        
        # Remove position
        del self.positions[symbol]
        
        logger.info(f"Closed {position.side} position: {symbol} @ {exit_price:.2f}, P&L: {pnl:+.2f}")
        
        # Send notification
        await self._notify_trade(order_side, symbol, exit_price, position.quantity, pnl)
        
        return pnl
    
    async def _notify_trade(self, action: str, symbol: str, price: float,
                           quantity: float, pnl: Optional[float] = None) -> None:
        """Send trade notifications."""
        if self.telegram:
            try:
                await self.telegram.send_trade_alert(action, symbol, price, quantity, pnl)
            except Exception as e:
                logger.error(f"Telegram notification error: {e}")
        
        if self.discord:
            try:
                await self.discord.send_trade_alert(action, symbol, price, quantity, pnl)
            except Exception as e:
                logger.error(f"Discord notification error: {e}")
    
    async def run_strategy(self, strategy: BaseStrategy, exchange_id: str,
                          symbol: str, timeframe: str = "1h",
                          position_size: float = 0.1,
                          check_interval: int = 60) -> None:
        """
        Run a strategy in live mode.
        
        Args:
            strategy: Strategy instance to run
            exchange_id: Exchange identifier
            symbol: Trading pair
            timeframe: Candlestick timeframe
            position_size: Fraction of balance to use (0.0 to 1.0)
            check_interval: Seconds between strategy checks
        """
        self._running = True
        self._stop_event.clear()
        
        logger.info(f"Starting live trading: {strategy.name} on {symbol} ({timeframe})")
        logger.info(f"Mode: {self.mode.value}, Position size: {position_size*100}%")
        
        # Connect to exchange
        self.exchange_manager.connect(exchange_id)
        
        # Get quote currency for balance
        _, quote = symbol.split('/')
        
        while self._running:
            try:
                # Fetch recent candles
                candles = self.exchange_manager.fetch_ohlcv(
                    exchange_id, symbol, timeframe, limit=100
                )
                
                if not candles:
                    logger.warning("No candle data received")
                    await asyncio.sleep(check_interval)
                    continue
                
                # Convert to DataFrame
                df = pd.DataFrame(
                    candles,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Calculate indicators
                df = strategy.calculate_indicators(df)
                
                # Get signal for latest candle
                signal = strategy.analyze(df, len(df) - 1)
                
                if self._on_signal_callback:
                    self._on_signal_callback(signal, df.iloc[-1])
                
                # Process signal
                current_price = df.iloc[-1]['close']
                has_pos = self.has_position(symbol)
                
                if signal.signal == Signal.BUY and not has_pos:
                    # Calculate position size
                    balance = self.get_balance(exchange_id, quote)
                    trade_amount = balance * position_size
                    quantity = trade_amount / current_price
                    
                    if quantity > 0:
                        await self.open_position(
                            exchange_id, symbol, "long", quantity,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit
                        )
                
                elif signal.signal == Signal.SELL and has_pos:
                    await self.close_position(exchange_id, symbol, "signal")
                
                # Check stop loss / take profit
                if has_pos:
                    position = self.get_position(symbol)
                    if position:
                        if position.stop_loss and current_price <= position.stop_loss:
                            logger.info(f"Stop loss triggered at {current_price}")
                            await self.close_position(exchange_id, symbol, "stop_loss")
                        elif position.take_profit and current_price >= position.take_profit:
                            logger.info(f"Take profit triggered at {current_price}")
                            await self.close_position(exchange_id, symbol, "take_profit")
                
                # Log status
                logger.debug(f"Signal: {signal.signal.value}, Price: {current_price:.2f}, "
                           f"Position: {has_pos}")
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
            
            # Wait for next check
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), 
                    timeout=check_interval
                )
                break  # Stop event was set
            except asyncio.TimeoutError:
                pass  # Continue loop
        
        logger.info("Live trading stopped")
    
    def stop(self) -> None:
        """Stop the trading engine."""
        logger.info("Stopping trading engine...")
        self._running = False
        self._stop_event.set()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current trading status for UI display.
        
        Returns:
            Dictionary with current status information
        """
        # Calculate session PnL
        session_pnl = sum(t.pnl or 0 for t in self.trade_history)
        
        # Get current position if any
        position = None
        if self.positions:
            # Get first position (usually only one for simple strategies)
            pos_key = list(self.positions.keys())[0]
            pos = self.positions[pos_key]
            position = {
                "symbol": pos.symbol,
                "side": pos.side,
                "size": pos.quantity,
                "entry_price": pos.entry_price
            }
        
        return {
            "running": self._running,
            "mode": self.mode.value,
            "position": position,
            "session_pnl": session_pnl,
            "trades_count": len(self.trade_history),
            "open_positions": len(self.positions)
        }
    
    def on_trade(self, callback: Callable) -> None:
        """Set callback for trade events."""
        self._on_trade_callback = callback
    
    def on_signal(self, callback: Callable) -> None:
        """Set callback for signal events."""
        self._on_signal_callback = callback
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary of trading session.
        
        Returns:
            Dictionary with performance metrics
        """
        if not self.trade_history:
            return {"message": "No trades executed"}
        
        total_pnl = sum(t.pnl or 0 for t in self.trade_history)
        total_fees = sum(t.fee for t in self.trade_history)
        
        winning = [t for t in self.trade_history if t.pnl and t.pnl > 0]
        losing = [t for t in self.trade_history if t.pnl and t.pnl <= 0]
        
        return {
            "total_trades": len(self.trade_history),
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": len(winning) / len(self.trade_history) * 100 if self.trade_history else 0,
            "avg_win": sum(t.pnl for t in winning) / len(winning) if winning else 0,
            "avg_loss": sum(t.pnl for t in losing) / len(losing) if losing else 0,
            "open_positions": len(self.positions),
            "paper_balances": {k: v.total for k, v in self.paper_balances.items()}
        }


async def run_live_trading(config: ConfigManager, strategy: BaseStrategy,
                          exchange_id: str, symbol: str,
                          timeframe: str = "1h",
                          mode: TradingMode = TradingMode.PAPER,
                          initial_balance: float = 10000) -> None:
    """
    Convenience function to run live trading.
    
    Args:
        config: Configuration manager
        strategy: Strategy to run
        exchange_id: Exchange identifier
        symbol: Trading pair
        timeframe: Candlestick timeframe
        mode: Trading mode
        initial_balance: Initial paper balance (for paper mode)
    """
    engine = LiveTradingEngine(config, mode=mode)
    
    if mode == TradingMode.PAPER:
        _, quote = symbol.split('/')
        engine.set_paper_balance(quote, initial_balance)
    
    try:
        await engine.run_strategy(strategy, exchange_id, symbol, timeframe)
    except KeyboardInterrupt:
        engine.stop()
    finally:
        summary = engine.get_performance_summary()
        logger.info(f"Performance summary: {summary}")
