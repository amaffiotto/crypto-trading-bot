"""
Grid Trading Strategy - For sideways/ranging markets.

Grid trading works by placing buy and sell orders at regular intervals
within a price range. Profits from price oscillations without needing
to predict direction.

Best used when: Market is ranging/sideways with clear support/resistance.
Avoid when: Strong trending market (will hit one side of grid repeatedly).
"""

from typing import Any, Dict, List
import pandas as pd
import numpy as np

from src.strategies.base import BaseStrategy, Signal, TradeSignal


class GridTradingStrategy(BaseStrategy):
    """
    Grid Trading Strategy for ranging markets.
    
    Creates a grid of price levels and trades between them:
    - BUY when price drops to a lower grid level
    - SELL when price rises to a higher grid level
    
    The grid is dynamically calculated based on recent price range.
    
    Best used on: 1h, 4h timeframes
    Best markets: Sideways/ranging with clear bounds
    """
    
    name = "Grid Trading"
    description = "Trade between grid levels in ranging markets. Profits from oscillations."
    version = "1.0.0"
    
    def default_params(self) -> Dict[str, Any]:
        """Default parameters."""
        return {
            "grid_levels": 10,          # Number of grid levels
            "range_period": 48,         # Candles to calculate range (48h on 1h)
            "range_multiplier": 1.0,    # Multiply range by this factor
            "min_profit_pct": 0.5,      # Minimum profit % per grid level
            "use_dynamic_range": True,  # Recalculate range dynamically
        }
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Parameter schema for UI."""
        return {
            "grid_levels": {
                "type": "int",
                "min": 3,
                "max": 50,
                "description": "Number of grid levels"
            },
            "range_period": {
                "type": "int",
                "min": 12,
                "max": 200,
                "description": "Candles to determine price range"
            },
            "min_profit_pct": {
                "type": "float",
                "min": 0.1,
                "max": 5.0,
                "description": "Minimum profit % per level"
            },
        }
    
    def get_required_history(self) -> int:
        """Minimum candles required."""
        return self._params["range_period"] + 5
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate grid levels based on price range."""
        period = self._params["range_period"]
        num_levels = self._params["grid_levels"]
        multiplier = self._params["range_multiplier"]
        
        # Calculate rolling high and low for range
        df["range_high"] = df["high"].rolling(window=period).max()
        df["range_low"] = df["low"].rolling(window=period).min()
        df["range_mid"] = (df["range_high"] + df["range_low"]) / 2
        
        # Expand range by multiplier
        range_size = df["range_high"] - df["range_low"]
        df["grid_upper"] = df["range_mid"] + (range_size * multiplier / 2)
        df["grid_lower"] = df["range_mid"] - (range_size * multiplier / 2)
        
        # Calculate grid step size
        df["grid_step"] = (df["grid_upper"] - df["grid_lower"]) / num_levels
        
        # Determine current grid level (0 = lowest, num_levels = highest)
        df["grid_level"] = ((df["close"] - df["grid_lower"]) / df["grid_step"]).clip(0, num_levels)
        df["grid_level"] = df["grid_level"].round()
        
        # Calculate volatility for filtering
        df["volatility"] = df["close"].pct_change().rolling(window=20).std() * 100
        
        # RSI for additional filtering
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.inf)
        df["rsi"] = 100 - (100 / (1 + rs))
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Generate signals based on grid level changes.
        
        BUY: When price drops to lower grid level (and RSI confirms oversold)
        SELL: When price rises to higher grid level (and RSI confirms overbought)
        """
        if index < 2:
            return TradeSignal(Signal.HOLD)
        
        row = df.iloc[index]
        prev = df.iloc[index - 1]
        
        # Check for valid values
        if pd.isna(row["grid_level"]) or pd.isna(prev["grid_level"]):
            return TradeSignal(Signal.HOLD)
        
        curr_level = int(row["grid_level"])
        prev_level = int(prev["grid_level"])
        close = row["close"]
        rsi = row["rsi"]
        grid_lower = row["grid_lower"]
        grid_upper = row["grid_upper"]
        grid_step = row["grid_step"]
        num_levels = self._params["grid_levels"]
        min_profit = self._params["min_profit_pct"]
        
        # Check if price is within grid range
        if close < grid_lower * 0.95 or close > grid_upper * 1.05:
            # Price outside grid range - could be breakout
            return TradeSignal(Signal.HOLD)
        
        # BUY: Price dropped to lower grid level
        if curr_level < prev_level:
            levels_dropped = prev_level - curr_level
            
            # Stronger signal if dropped multiple levels and RSI oversold
            strength = 0.4 + (levels_dropped * 0.1)
            if rsi < 35:
                strength += 0.2
            if curr_level <= 2:  # Near bottom of grid
                strength += 0.2
            
            # Calculate target (next grid level up)
            target_price = grid_lower + (curr_level + 1) * grid_step
            profit_pct = ((target_price - close) / close) * 100
            
            if profit_pct >= min_profit:
                return TradeSignal(
                    signal=Signal.BUY,
                    strength=min(1.0, strength),
                    metadata={
                        "grid_level": curr_level,
                        "levels_dropped": levels_dropped,
                        "target_price": target_price,
                        "expected_profit_pct": profit_pct,
                        "grid_lower": grid_lower,
                        "grid_upper": grid_upper,
                        "rsi": rsi,
                        "reason": "grid_buy_level"
                    }
                )
        
        # SELL: Price rose to higher grid level
        if curr_level > prev_level:
            levels_risen = curr_level - prev_level
            
            strength = 0.4 + (levels_risen * 0.1)
            if rsi > 65:
                strength += 0.2
            if curr_level >= num_levels - 2:  # Near top of grid
                strength += 0.2
            
            return TradeSignal(
                signal=Signal.SELL,
                strength=min(1.0, strength),
                metadata={
                    "grid_level": curr_level,
                    "levels_risen": levels_risen,
                    "grid_lower": grid_lower,
                    "grid_upper": grid_upper,
                    "rsi": rsi,
                    "reason": "grid_sell_level"
                }
            )
        
        return TradeSignal(Signal.HOLD)
