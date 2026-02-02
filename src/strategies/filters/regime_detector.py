"""Market regime detection filter."""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

try:
    import ta
except ImportError:
    ta = None

from src.strategies.base import TradeSignal, Signal
from src.strategies.filters import BaseFilter, FilterResult, MarketRegime
from src.utils.logger import get_logger

logger = get_logger()


class RegimeDetector:
    """
    Detects market regime based on technical indicators.
    
    Uses:
    - ADX for trend strength
    - ATR for volatility regime
    - Price action for trend direction
    
    Classifications:
    - trending_bullish: Strong uptrend (ADX > threshold, price above MA)
    - trending_bearish: Strong downtrend (ADX > threshold, price below MA)
    - ranging: Sideways market (ADX < threshold)
    - high_volatility: ATR significantly above average
    - low_volatility: ATR significantly below average
    """
    
    def __init__(
        self,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        ma_period: int = 50,
        atr_period: int = 14,
        volatility_lookback: int = 50,
        volatility_high_mult: float = 1.5,
        volatility_low_mult: float = 0.5
    ):
        """
        Initialize regime detector.
        
        Args:
            adx_period: Period for ADX calculation
            adx_threshold: ADX value above which market is trending
            ma_period: Period for moving average (trend direction)
            atr_period: Period for ATR calculation
            volatility_lookback: Lookback for average volatility
            volatility_high_mult: Multiplier for high volatility threshold
            volatility_low_mult: Multiplier for low volatility threshold
        """
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.ma_period = ma_period
        self.atr_period = atr_period
        self.volatility_lookback = volatility_lookback
        self.volatility_high_mult = volatility_high_mult
        self.volatility_low_mult = volatility_low_mult
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add regime detection indicators to DataFrame.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with regime indicators
        """
        df = df.copy()
        
        if ta is None:
            logger.warning("ta library not installed, using simple calculations")
            return self._calculate_simple(df)
        
        # ADX for trend strength
        adx_indicator = ta.trend.ADXIndicator(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=self.adx_period
        )
        df['regime_adx'] = adx_indicator.adx()
        df['regime_di_plus'] = adx_indicator.adx_pos()
        df['regime_di_minus'] = adx_indicator.adx_neg()
        
        # Moving average for trend direction
        df['regime_ma'] = df['close'].rolling(window=self.ma_period).mean()
        
        # ATR for volatility
        atr_indicator = ta.volatility.AverageTrueRange(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=self.atr_period
        )
        df['regime_atr'] = atr_indicator.average_true_range()
        
        # Average ATR for volatility comparison
        df['regime_avg_atr'] = df['regime_atr'].rolling(
            window=self.volatility_lookback
        ).mean()
        
        return df
    
    def _calculate_simple(self, df: pd.DataFrame) -> pd.DataFrame:
        """Simple fallback calculations without ta library."""
        df = df.copy()
        
        # Simple MA
        df['regime_ma'] = df['close'].rolling(window=self.ma_period).mean()
        
        # Simple ATR
        df['regime_tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['regime_atr'] = df['regime_tr'].rolling(window=self.atr_period).mean()
        df['regime_avg_atr'] = df['regime_atr'].rolling(
            window=self.volatility_lookback
        ).mean()
        
        # Simplified ADX (just use price momentum)
        momentum = df['close'].diff(self.adx_period).abs()
        df['regime_adx'] = (momentum / df['close'] * 100).rolling(
            window=self.adx_period
        ).mean()
        
        return df
    
    def detect(self, df: pd.DataFrame, index: int) -> MarketRegime:
        """
        Detect current market regime.
        
        Args:
            df: DataFrame with calculated regime indicators
            index: Current candle index
            
        Returns:
            MarketRegime classification
        """
        if index < self.get_required_history():
            return MarketRegime.UNKNOWN
        
        try:
            row = df.iloc[index]
            
            adx = row.get('regime_adx', 0)
            ma = row.get('regime_ma', 0)
            atr = row.get('regime_atr', 0)
            avg_atr = row.get('regime_avg_atr', 0)
            close = row['close']
            
            # Check for missing values
            if pd.isna(adx) or pd.isna(ma) or pd.isna(atr):
                return MarketRegime.UNKNOWN
            
            # Check volatility first
            if avg_atr > 0:
                if atr > avg_atr * self.volatility_high_mult:
                    return MarketRegime.HIGH_VOLATILITY
                elif atr < avg_atr * self.volatility_low_mult:
                    return MarketRegime.LOW_VOLATILITY
            
            # Check trend
            if adx >= self.adx_threshold:
                if close > ma:
                    return MarketRegime.TRENDING_BULLISH
                else:
                    return MarketRegime.TRENDING_BEARISH
            else:
                return MarketRegime.RANGING
                
        except Exception as e:
            logger.warning(f"Error detecting regime: {e}")
            return MarketRegime.UNKNOWN
    
    def get_regime_info(self, df: pd.DataFrame, index: int) -> Dict[str, Any]:
        """
        Get detailed regime information.
        
        Args:
            df: DataFrame with indicators
            index: Current index
            
        Returns:
            Dict with regime details
        """
        regime = self.detect(df, index)
        
        info = {
            "regime": regime.value,
            "is_trending": regime in (MarketRegime.TRENDING_BULLISH, MarketRegime.TRENDING_BEARISH),
            "is_bullish": regime == MarketRegime.TRENDING_BULLISH,
            "is_bearish": regime == MarketRegime.TRENDING_BEARISH,
            "is_ranging": regime == MarketRegime.RANGING,
            "is_high_volatility": regime == MarketRegime.HIGH_VOLATILITY,
        }
        
        try:
            row = df.iloc[index]
            info["adx"] = round(row.get('regime_adx', 0), 2)
            info["atr"] = round(row.get('regime_atr', 0), 4)
            info["ma"] = round(row.get('regime_ma', 0), 2)
        except Exception:
            pass
        
        return info
    
    def get_required_history(self) -> int:
        """Get minimum candles needed."""
        return max(self.adx_period, self.ma_period, self.volatility_lookback) + 10


class RegimeFilter(BaseFilter):
    """
    Filter that only allows signals during specified market regimes.
    
    Usage:
        # Only trade in trending markets
        filter = RegimeFilter(
            allowed_regimes=["trending_bullish", "trending_bearish"]
        )
        
        # Only long in bullish, only short in bearish
        filter = RegimeFilter(
            long_regimes=["trending_bullish"],
            short_regimes=["trending_bearish"]
        )
    """
    
    name = "Regime Filter"
    
    def __init__(
        self,
        allowed_regimes: Optional[List[str]] = None,
        long_regimes: Optional[List[str]] = None,
        short_regimes: Optional[List[str]] = None,
        adx_threshold: float = 25.0,
        enabled: bool = True
    ):
        """
        Initialize regime filter.
        
        Args:
            allowed_regimes: List of regimes to allow any signal
            long_regimes: List of regimes to allow BUY signals
            short_regimes: List of regimes to allow SELL signals
            adx_threshold: ADX threshold for trend detection
            enabled: Whether filter is active
        """
        super().__init__(enabled)
        
        self.allowed_regimes = allowed_regimes or []
        self.long_regimes = long_regimes or []
        self.short_regimes = short_regimes or []
        
        self.detector = RegimeDetector(adx_threshold=adx_threshold)
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add regime indicators to DataFrame."""
        return self.detector.calculate_indicators(df)
    
    def apply(
        self,
        signal: TradeSignal,
        df: pd.DataFrame,
        index: int,
        context: Optional[Dict[str, Any]] = None
    ) -> FilterResult:
        """
        Apply regime filter to signal.
        
        Args:
            signal: Signal from strategy
            df: DataFrame with data
            index: Current index
            context: Additional context
            
        Returns:
            FilterResult
        """
        if not self.enabled:
            return FilterResult(allow_signal=True)
        
        regime_info = self.detector.get_regime_info(df, index)
        regime = regime_info["regime"]
        
        # Check if regime is in allowed list
        if self.allowed_regimes and regime in self.allowed_regimes:
            return FilterResult(
                allow_signal=True,
                metadata=regime_info
            )
        
        # Check direction-specific regimes
        if signal.signal == Signal.BUY:
            if self.long_regimes and regime in self.long_regimes:
                return FilterResult(
                    allow_signal=True,
                    metadata=regime_info
                )
            if self.long_regimes:
                return FilterResult(
                    allow_signal=False,
                    reason=f"BUY not allowed in {regime} regime",
                    metadata=regime_info
                )
        
        if signal.signal == Signal.SELL:
            if self.short_regimes and regime in self.short_regimes:
                return FilterResult(
                    allow_signal=True,
                    metadata=regime_info
                )
            if self.short_regimes:
                return FilterResult(
                    allow_signal=False,
                    reason=f"SELL not allowed in {regime} regime",
                    metadata=regime_info
                )
        
        # If no specific restrictions set, allow
        if not self.allowed_regimes and not self.long_regimes and not self.short_regimes:
            return FilterResult(
                allow_signal=True,
                metadata=regime_info
            )
        
        # Default deny if restrictions are set but not met
        return FilterResult(
            allow_signal=False,
            reason=f"Signal not allowed in {regime} regime",
            metadata=regime_info
        )
    
    def get_required_history(self) -> int:
        """Get minimum candles needed."""
        return self.detector.get_required_history()
