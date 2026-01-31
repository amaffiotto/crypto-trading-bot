"""
DCA (Dollar Cost Averaging) Strategy - For accumulation.

DCA bots work by buying more as price drops, lowering average entry.
Then selling when price rises above average cost + profit target.

Best used when: Bear market, accumulation phase, high conviction assets.
Avoid when: Asset in free-fall with no support levels.

Based on 3Commas DCA bot logic.
"""

from typing import Any, Dict, List
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class DCAStrategy(BaseStrategy):
    """
    Dollar Cost Averaging Strategy.
    
    Implements a DCA approach with safety orders:
    1. Initial buy (base order)
    2. Safety orders when price drops by X%
    3. Take profit when price rises above average + target%
    
    Features:
    - Configurable drop percentage for safety orders
    - Optional martingale multiplier for order sizes
    - Take profit based on average entry price
    
    Best used on: 4h, 1d timeframes
    Best markets: Accumulation in downtrends for quality assets
    """
    
    name = "DCA Strategy"
    description = "Buy on dips, average down, sell on recovery. Good for accumulation."
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters based on 3Commas defaults."""
        return {
            "price_drop_pct": 2.0,      # % drop to trigger safety order
            "take_profit_pct": 3.0,     # % above average for take profit
            "max_safety_orders": 5,     # Maximum safety orders
            "martingale_volume": 1.5,   # Volume multiplier for each safety order
            "martingale_step": 1.0,     # Step multiplier (increase drop % each order)
            "use_rsi_filter": True,     # Only buy when RSI < threshold
            "rsi_threshold": 40,        # RSI threshold for buys
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "price_drop_pct": {
                "type": "float",
                "min": 0.5,
                "max": 20.0,
                "description": "Price drop % to trigger safety order"
            },
            "take_profit_pct": {
                "type": "float",
                "min": 0.5,
                "max": 50.0,
                "description": "Take profit % above average entry"
            },
            "max_safety_orders": {
                "type": "int",
                "min": 1,
                "max": 20,
                "description": "Maximum number of safety orders"
            },
            "martingale_volume": {
                "type": "float",
                "min": 1.0,
                "max": 3.0,
                "description": "Volume multiplier for each safety order"
            },
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return 20
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicators for DCA strategy."""
        # RSI for entry filtering
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.inf)
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # Track price changes
        df["pct_change"] = df["close"].pct_change() * 100
        
        # Moving averages for trend context
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        
        # Volatility
        df["volatility"] = df["close"].pct_change().rolling(window=20).std() * 100
        
        # Track recent high for drop calculation
        df["recent_high"] = df["high"].rolling(window=10).max()
        df["drop_from_high"] = ((df["recent_high"] - df["close"]) / df["recent_high"]) * 100
        
        # Calculate consecutive down days
        df["is_down"] = df["close"] < df["close"].shift(1)
        df["consecutive_down"] = df["is_down"].groupby(
            (~df["is_down"]).cumsum()
        ).cumsum()
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Generate DCA signals.
        
        BUY: When price drops by X% from recent high and RSI confirms
        SELL: Would be handled by position tracker (% above average)
              For backtest, sell when RSI overbought after recovery
        """
        if index < 2:
            return TradeSignal(Signal.HOLD)
        
        row = df.iloc[index]
        prev = df.iloc[index - 1]
        
        # Check for valid values
        if pd.isna(row["rsi"]) or pd.isna(row["drop_from_high"]):
            return TradeSignal(Signal.HOLD)
        
        close = row["close"]
        rsi = row["rsi"]
        prev_rsi = prev["rsi"]
        drop_from_high = row["drop_from_high"]
        ema_20 = row["ema_20"]
        ema_50 = row["ema_50"]
        consecutive_down = row["consecutive_down"]
        
        price_drop = self._params["price_drop_pct"]
        take_profit = self._params["take_profit_pct"]
        rsi_threshold = self._params["rsi_threshold"]
        use_rsi = self._params["use_rsi_filter"]
        max_orders = self._params["max_safety_orders"]
        
        # BUY CONDITIONS
        # 1. Price dropped by threshold %
        # 2. RSI below threshold (if enabled)
        # 3. Not too many consecutive down days (avoid catching falling knife)
        
        should_buy = drop_from_high >= price_drop
        
        if use_rsi:
            should_buy = should_buy and rsi < rsi_threshold
        
        # Avoid buying in complete free-fall (more than 5 consecutive down candles)
        if consecutive_down > 5:
            should_buy = False
        
        if should_buy:
            # Calculate strength based on drop magnitude and RSI
            strength = 0.4
            
            # More drop = stronger signal
            strength += min(0.3, drop_from_high / 20)
            
            # Lower RSI = stronger signal
            if rsi < 30:
                strength += 0.2
            elif rsi < 40:
                strength += 0.1
            
            # Determine which safety order this would be based on drop
            order_number = min(max_orders, int(drop_from_high / price_drop))
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=min(1.0, strength),
                metadata={
                    "drop_from_high": drop_from_high,
                    "safety_order_number": order_number,
                    "rsi": rsi,
                    "consecutive_down": consecutive_down,
                    "target_profit_pct": take_profit,
                    "reason": "dca_safety_order"
                }
            )
        
        # SELL CONDITIONS
        # 1. RSI overbought (exit signal)
        # 2. Price recovered significantly above EMA
        
        rsi_overbought = rsi > 70
        rsi_crossed_up = prev_rsi <= 70 and rsi > 70
        price_above_ema = close > ema_20 * 1.02  # 2% above EMA20
        
        if rsi_crossed_up and price_above_ema:
            strength = 0.5
            
            if rsi > 80:
                strength += 0.3
            if close > ema_50:
                strength += 0.2
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=min(1.0, strength),
                metadata={
                    "rsi": rsi,
                    "price_vs_ema20": ((close / ema_20) - 1) * 100,
                    "reason": "dca_take_profit"
                }
            )
        
        return TradeSignal(Signal.HOLD)
