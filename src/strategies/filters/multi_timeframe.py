"""Multi-timeframe confirmation filter."""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

try:
    import ta
except ImportError:
    ta = None

from src.strategies.base import TradeSignal, Signal
from src.strategies.filters import BaseFilter, FilterResult
from src.utils.logger import get_logger

logger = get_logger()


class MultiTimeframeAnalyzer:
    """
    Analyzes trend direction across multiple timeframes.
    
    Uses simple trend detection (MA direction, price vs MA) to
    determine if higher timeframes confirm the signal direction.
    """
    
    def __init__(
        self,
        ma_period: int = 20,
        trend_strength_period: int = 10
    ):
        """
        Initialize analyzer.
        
        Args:
            ma_period: Period for moving average
            trend_strength_period: Period for measuring trend strength
        """
        self.ma_period = ma_period
        self.trend_strength_period = trend_strength_period
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add trend indicators to DataFrame.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with trend indicators
        """
        df = df.copy()
        
        # Simple moving average
        df['mtf_ma'] = df['close'].rolling(window=self.ma_period).mean()
        
        # MA slope (trend direction)
        df['mtf_ma_slope'] = df['mtf_ma'].diff(self.trend_strength_period)
        
        # Price position relative to MA
        df['mtf_price_vs_ma'] = (df['close'] - df['mtf_ma']) / df['mtf_ma'] * 100
        
        # Higher highs / lower lows detection
        df['mtf_hh'] = df['high'].rolling(window=self.trend_strength_period).max()
        df['mtf_ll'] = df['low'].rolling(window=self.trend_strength_period).min()
        
        return df
    
    def get_trend(self, df: pd.DataFrame, index: int) -> Dict[str, Any]:
        """
        Get trend information at given index.
        
        Args:
            df: DataFrame with indicators
            index: Current index
            
        Returns:
            Dict with trend info
        """
        if index < self.get_required_history():
            return {
                "direction": "unknown",
                "strength": 0.0,
                "is_bullish": False,
                "is_bearish": False
            }
        
        try:
            row = df.iloc[index]
            
            ma = row.get('mtf_ma', 0)
            ma_slope = row.get('mtf_ma_slope', 0)
            price_vs_ma = row.get('mtf_price_vs_ma', 0)
            close = row['close']
            
            # Determine trend direction
            bullish_signals = 0
            bearish_signals = 0
            
            # Price above/below MA
            if close > ma:
                bullish_signals += 1
            else:
                bearish_signals += 1
            
            # MA slope
            if ma_slope > 0:
                bullish_signals += 1
            elif ma_slope < 0:
                bearish_signals += 1
            
            # Determine direction
            if bullish_signals > bearish_signals:
                direction = "bullish"
                is_bullish = True
                is_bearish = False
            elif bearish_signals > bullish_signals:
                direction = "bearish"
                is_bullish = False
                is_bearish = True
            else:
                direction = "neutral"
                is_bullish = False
                is_bearish = False
            
            # Calculate strength (0-1)
            strength = abs(price_vs_ma) / 10  # Normalize
            strength = min(1.0, max(0.0, strength))
            
            return {
                "direction": direction,
                "strength": round(strength, 2),
                "is_bullish": is_bullish,
                "is_bearish": is_bearish,
                "price_vs_ma_pct": round(price_vs_ma, 2),
                "ma_slope": round(ma_slope, 4) if not pd.isna(ma_slope) else 0
            }
            
        except Exception as e:
            logger.warning(f"Error getting trend: {e}")
            return {
                "direction": "unknown",
                "strength": 0.0,
                "is_bullish": False,
                "is_bearish": False
            }
    
    def get_required_history(self) -> int:
        """Get minimum candles needed."""
        return self.ma_period + self.trend_strength_period + 5


class MultiTimeframeFilter(BaseFilter):
    """
    Filter that requires higher timeframe trend confirmation.
    
    For a BUY signal to pass, higher timeframes should also be bullish.
    For a SELL signal to pass, higher timeframes should also be bearish.
    
    Usage:
        # Basic usage - provide higher TF data in context
        filter = MultiTimeframeFilter(
            confirmation_timeframes=["4h", "1d"],
            require_all=False  # At least one must confirm
        )
        
        # In your strategy/engine:
        context = {
            "timeframe_data": {
                "4h": df_4h,
                "1d": df_1d
            }
        }
        result = filter.apply(signal, df, index, context)
    """
    
    name = "Multi-Timeframe Filter"
    
    def __init__(
        self,
        confirmation_timeframes: Optional[List[str]] = None,
        require_all: bool = False,
        min_confirmations: int = 1,
        ma_period: int = 20,
        enabled: bool = True
    ):
        """
        Initialize multi-timeframe filter.
        
        Args:
            confirmation_timeframes: List of higher timeframes to check
            require_all: If True, ALL timeframes must confirm
            min_confirmations: Minimum number of confirmations needed
            ma_period: MA period for trend detection
            enabled: Whether filter is active
        """
        super().__init__(enabled)
        
        self.confirmation_timeframes = confirmation_timeframes or ["4h", "1d"]
        self.require_all = require_all
        self.min_confirmations = min_confirmations
        
        self.analyzer = MultiTimeframeAnalyzer(ma_period=ma_period)
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add trend indicators to DataFrame."""
        return self.analyzer.calculate_indicators(df)
    
    def apply(
        self,
        signal: TradeSignal,
        df: pd.DataFrame,
        index: int,
        context: Optional[Dict[str, Any]] = None
    ) -> FilterResult:
        """
        Apply multi-timeframe filter to signal.
        
        Args:
            signal: Signal from strategy
            df: DataFrame with data (current timeframe)
            index: Current index
            context: Must contain "timeframe_data" dict with higher TF DataFrames
            
        Returns:
            FilterResult
        """
        if not self.enabled:
            return FilterResult(allow_signal=True)
        
        # Get higher timeframe data from context
        timeframe_data = {}
        if context:
            timeframe_data = context.get("timeframe_data", {})
        
        if not timeframe_data:
            # No higher TF data provided - allow signal but warn
            logger.debug("No higher timeframe data provided to MTF filter")
            return FilterResult(
                allow_signal=True,
                metadata={"warning": "No higher TF data provided"}
            )
        
        # Analyze each higher timeframe
        confirmations = 0
        tf_analysis = {}
        
        for tf in self.confirmation_timeframes:
            tf_df = timeframe_data.get(tf)
            
            if tf_df is None or tf_df.empty:
                logger.debug(f"No data for timeframe {tf}")
                tf_analysis[tf] = {"status": "no_data"}
                continue
            
            # Calculate indicators if not present
            if 'mtf_ma' not in tf_df.columns:
                tf_df = self.analyzer.calculate_indicators(tf_df)
            
            # Get trend at latest candle
            trend = self.analyzer.get_trend(tf_df, len(tf_df) - 1)
            tf_analysis[tf] = trend
            
            # Check if trend confirms signal
            if signal.signal == Signal.BUY and trend["is_bullish"]:
                confirmations += 1
            elif signal.signal == Signal.SELL and trend["is_bearish"]:
                confirmations += 1
        
        # Build result metadata
        metadata = {
            "confirmations": confirmations,
            "required": len(self.confirmation_timeframes) if self.require_all else self.min_confirmations,
            "timeframe_analysis": tf_analysis
        }
        
        # Check confirmation requirements
        if self.require_all:
            # All timeframes must confirm
            required = len(self.confirmation_timeframes)
            if confirmations >= required:
                return FilterResult(
                    allow_signal=True,
                    metadata=metadata
                )
            else:
                return FilterResult(
                    allow_signal=False,
                    reason=f"Only {confirmations}/{required} timeframes confirm",
                    metadata=metadata
                )
        else:
            # Need minimum confirmations
            if confirmations >= self.min_confirmations:
                return FilterResult(
                    allow_signal=True,
                    metadata=metadata
                )
            else:
                return FilterResult(
                    allow_signal=False,
                    reason=f"Only {confirmations}/{self.min_confirmations} timeframes confirm",
                    metadata=metadata
                )
    
    def get_required_history(self) -> int:
        """Get minimum candles needed."""
        return self.analyzer.get_required_history()


def get_timeframe_minutes(timeframe: str) -> int:
    """
    Convert timeframe string to minutes.
    
    Args:
        timeframe: Timeframe string (1m, 5m, 1h, 4h, 1d, 1w)
        
    Returns:
        Number of minutes
    """
    mappings = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '2h': 120,
        '4h': 240,
        '6h': 360,
        '8h': 480,
        '12h': 720,
        '1d': 1440,
        '1w': 10080,
    }
    return mappings.get(timeframe, 60)


def resample_to_higher_timeframe(
    df: pd.DataFrame,
    source_tf: str,
    target_tf: str
) -> pd.DataFrame:
    """
    Resample OHLCV data from lower to higher timeframe.
    
    Args:
        df: DataFrame with OHLCV data
        source_tf: Source timeframe string
        target_tf: Target timeframe string
        
    Returns:
        Resampled DataFrame
    """
    source_mins = get_timeframe_minutes(source_tf)
    target_mins = get_timeframe_minutes(target_tf)
    
    if target_mins <= source_mins:
        logger.warning(f"Target TF {target_tf} not higher than source {source_tf}")
        return df
    
    df = df.copy()
    
    # Ensure timestamp is datetime
    if 'timestamp' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Set timestamp as index
    if 'timestamp' in df.columns:
        df.set_index('timestamp', inplace=True)
    
    # Resample
    resampled = df.resample(f'{target_mins}min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    resampled.reset_index(inplace=True)
    
    return resampled
