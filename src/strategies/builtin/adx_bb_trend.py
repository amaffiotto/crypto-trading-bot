"""
ADX Trend Strategy with Bollinger Bands Filter.

Based on research showing 36%-182% profit improvement when combining:
- ADX for trend strength confirmation (>25 = strong trend)
- +DI/-DI for trend direction
- Bollinger Bands width filter to avoid ranging markets
- Signal confirmation delay to reduce whipsaws

This strategy ONLY trades when there's a confirmed strong trend.
"""

import pandas as pd
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

from src.strategies.base import BaseStrategy, TradeSignal, Signal


class ADXBBTrendStrategy(BaseStrategy):
    """
    ADX Trend Strategy with Bollinger Bands Filter.
    
    Trades only in strong trending markets, avoiding range-bound conditions.
    Uses ADX > 25 for trend strength and BB width for volatility filter.
    
    Research shows this approach achieves 36%-182% better returns than
    simple indicator strategies.
    """
    
    name = "ADX BB Trend"
    description = "Trend trading with ADX strength filter and Bollinger Bands volatility filter. Only trades strong trends."
    version = "1.0.0"
    
    def default_params(self):
        return {
            "adx_period": 14,           # ADX calculation period
            "adx_threshold": 25,        # Minimum ADX for trend (25 = strong)
            "bb_period": 20,            # Bollinger Bands period
            "bb_std": 2.0,              # Bollinger Bands standard deviation
            "bb_width_threshold": 0.02, # Min BB width as % of price (2%)
            "confirmation_bars": 2,     # Bars signal must persist
        }
    
    def get_param_schema(self):
        return {
            "adx_period": {
                "type": "int", "min": 7, "max": 30,
                "description": "ADX calculation period"
            },
            "adx_threshold": {
                "type": "int", "min": 15, "max": 40,
                "description": "Minimum ADX value for strong trend"
            },
            "bb_period": {
                "type": "int", "min": 10, "max": 50,
                "description": "Bollinger Bands period"
            },
            "bb_std": {
                "type": "float", "min": 1.0, "max": 3.0,
                "description": "Bollinger Bands standard deviation"
            },
            "bb_width_threshold": {
                "type": "float", "min": 0.01, "max": 0.05,
                "description": "Minimum BB width as fraction of price"
            },
            "confirmation_bars": {
                "type": "int", "min": 1, "max": 5,
                "description": "Bars signal must persist before entry"
            }
        }
    
    def get_required_history(self) -> int:
        return max(self._params["adx_period"], self._params["bb_period"]) + 10
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate ADX and Bollinger Bands indicators."""
        adx_period = self._params["adx_period"]
        bb_period = self._params["bb_period"]
        bb_std = self._params["bb_std"]
        
        # ADX Indicator (includes +DI and -DI)
        adx = ADXIndicator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=adx_period
        )
        df["adx"] = adx.adx()
        df["plus_di"] = adx.adx_pos()
        df["minus_di"] = adx.adx_neg()
        
        # Bollinger Bands
        bb = BollingerBands(
            close=df["close"],
            window=bb_period,
            window_dev=bb_std
        )
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        
        # Signal columns for confirmation
        df["raw_signal"] = 0  # 1 = buy, -1 = sell, 0 = neutral
        
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """Generate trading signal based on ADX trend and BB filter."""
        if index < self.get_required_history():
            return TradeSignal(signal=Signal.HOLD)
        
        params = self._params
        row = df.iloc[index]
        
        adx = row.get("adx", 0)
        plus_di = row.get("plus_di", 0)
        minus_di = row.get("minus_di", 0)
        bb_width = row.get("bb_width", 0)
        close = row["close"]
        
        # Check for valid indicator values
        if pd.isna(adx) or pd.isna(plus_di) or pd.isna(minus_di):
            return TradeSignal(signal=Signal.HOLD)
        
        # Filter 1: Is there a strong trend? (ADX > threshold)
        strong_trend = adx > params["adx_threshold"]
        
        # Filter 2: Is market volatile enough? (BB width > threshold)
        volatile_market = bb_width > params["bb_width_threshold"]
        
        # Only trade if both filters pass
        if not (strong_trend and volatile_market):
            return TradeSignal(
                signal=Signal.HOLD,
                metadata={"reason": "No strong trend or low volatility"}
            )
        
        # Determine trend direction from +DI/-DI
        bullish = plus_di > minus_di
        bearish = minus_di > plus_di
        
        # Check for signal confirmation (signal persisted for N bars)
        confirmation_bars = params["confirmation_bars"]
        if confirmation_bars > 1 and index >= confirmation_bars:
            try:
                confirmed_bullish = all(
                    df["plus_di"].iloc[index - i] > df["minus_di"].iloc[index - i]
                    for i in range(confirmation_bars)
                )
                confirmed_bearish = all(
                    df["minus_di"].iloc[index - i] > df["plus_di"].iloc[index - i]
                    for i in range(confirmation_bars)
                )
            except (IndexError, KeyError):
                confirmed_bullish = bullish
                confirmed_bearish = bearish
        else:
            confirmed_bullish = bullish
            confirmed_bearish = bearish
        
        # Generate signals
        if confirmed_bullish:
            # Calculate ATR-based stop loss
            atr = (row["high"] - row["low"])  # Simplified ATR
            stop_loss = close - (atr * 2)
            take_profit = close + (atr * 3)  # 1.5:1 R:R ratio
            
            return TradeSignal(
                signal=Signal.BUY,
                strength=min(adx / 50, 1.0),  # Higher ADX = stronger signal
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "adx": adx,
                    "plus_di": plus_di,
                    "minus_di": minus_di,
                    "bb_width": bb_width
                }
            )
        
        elif confirmed_bearish:
            return TradeSignal(
                signal=Signal.SELL,
                strength=min(adx / 50, 1.0),
                metadata={
                    "adx": adx,
                    "plus_di": plus_di,
                    "minus_di": minus_di,
                    "bb_width": bb_width
                }
            )
        
        return TradeSignal(signal=Signal.HOLD)
