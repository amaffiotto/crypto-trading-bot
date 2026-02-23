"""
Strategy filters for signal enhancement and filtering.

Filters can be applied to strategies to:
- Add multi-timeframe confirmation
- Filter signals based on market regime
- Apply ML-based filtering (future)
- Chain multiple filters together

Usage:
    from src.strategies.filters import FilteredStrategy, RegimeFilter, MultiTimeframeFilter
    from src.strategies.builtin.ma_crossover import MACrossover
    
    # Create base strategy
    strategy = MACrossover()
    
    # Apply filters
    filtered = FilteredStrategy(
        strategy,
        filters=[
            RegimeFilter(allowed_regimes=["trending_bullish", "trending_bearish"]),
            MultiTimeframeFilter(confirmation_timeframes=["4h", "1d"])
        ]
    )
    
    # Use like a normal strategy
    signal = filtered.analyze(df, index)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import pandas as pd

from src.strategies.base import BaseStrategy, TradeSignal, Signal
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.core.data_manager import DataManager

logger = get_logger()


class MarketRegime(Enum):
    """Market regime classifications."""
    TRENDING_BULLISH = "trending_bullish"
    TRENDING_BEARISH = "trending_bearish"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


@dataclass
class FilterResult:
    """Result from applying a filter."""
    allow_signal: bool
    modified_signal: Optional[TradeSignal] = None
    reason: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseFilter(ABC):
    """
    Base class for strategy filters.
    
    Filters can modify or block signals from a strategy based on
    various conditions (regime, timeframe confirmation, etc.)
    """
    
    name: str = "Base Filter"
    
    def __init__(self, enabled: bool = True):
        """
        Initialize filter.
        
        Args:
            enabled: Whether the filter is active
        """
        self.enabled = enabled
    
    @abstractmethod
    def apply(
        self,
        signal: TradeSignal,
        df: pd.DataFrame,
        index: int,
        context: Optional[Dict[str, Any]] = None
    ) -> FilterResult:
        """
        Apply the filter to a signal.
        
        Args:
            signal: The signal from the strategy
            df: DataFrame with OHLCV data and indicators
            index: Current candle index
            context: Optional additional context (multi-timeframe data, etc.)
            
        Returns:
            FilterResult indicating whether to allow the signal
        """
        pass
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate any indicators needed by the filter.
        
        Override to add filter-specific indicators.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        return df
    
    def get_required_history(self) -> int:
        """Get minimum candles needed by this filter."""
        return 0


class FilterChain:
    """
    Chains multiple filters together.
    
    Signals must pass ALL filters in the chain.
    """
    
    def __init__(self, filters: List[BaseFilter]):
        """
        Initialize filter chain.
        
        Args:
            filters: List of filters to apply in order
        """
        self.filters = filters
    
    def apply(
        self,
        signal: TradeSignal,
        df: pd.DataFrame,
        index: int,
        context: Optional[Dict[str, Any]] = None
    ) -> FilterResult:
        """
        Apply all filters in the chain.
        
        Args:
            signal: Original signal
            df: DataFrame with data
            index: Current index
            context: Additional context
            
        Returns:
            FilterResult - signal is allowed only if all filters pass
        """
        current_signal = signal
        combined_metadata = {}
        
        for filter_obj in self.filters:
            if not filter_obj.enabled:
                continue
            
            result = filter_obj.apply(current_signal, df, index, context)
            combined_metadata[filter_obj.name] = result.metadata
            
            if not result.allow_signal:
                return FilterResult(
                    allow_signal=False,
                    reason=f"{filter_obj.name}: {result.reason}",
                    metadata=combined_metadata
                )
            
            # Use modified signal if provided
            if result.modified_signal:
                current_signal = result.modified_signal
        
        return FilterResult(
            allow_signal=True,
            modified_signal=current_signal,
            metadata=combined_metadata
        )
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicators for all filters."""
        for filter_obj in self.filters:
            if filter_obj.enabled:
                df = filter_obj.calculate_indicators(df)
        return df
    
    def get_required_history(self) -> int:
        """Get max required history from all filters."""
        if not self.filters:
            return 0
        return max(f.get_required_history() for f in self.filters)


class FilteredStrategy(BaseStrategy):
    """
    Wrapper that applies filters to a base strategy.
    
    This allows any strategy to be enhanced with regime detection,
    multi-timeframe confirmation, or other filters.
    """
    
    def __init__(
        self,
        base_strategy: BaseStrategy,
        filters: Optional[List[BaseFilter]] = None,
        params: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize filtered strategy.
        
        Args:
            base_strategy: The underlying strategy
            filters: List of filters to apply
            params: Additional parameters
        """
        self.base_strategy = base_strategy
        self.filter_chain = FilterChain(filters or [])
        self._context: Dict[str, Any] = {}
        
        # Copy name/description from base
        self.name = f"Filtered {base_strategy.name}"
        self.description = f"{base_strategy.description} (with filters)"
        self.version = base_strategy.version
        
        super().__init__(params)
    
    def default_params(self) -> Dict[str, Any]:
        """Get combined params from base strategy."""
        return self.base_strategy.default_params()
    
    def set_context(self, context: Dict[str, Any]) -> None:
        """
        Set additional context for filters.
        
        Args:
            context: Dict with additional data (e.g., multi-timeframe DataFrames)
        """
        self._context = context
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicators for strategy and all filters."""
        df = self.base_strategy.calculate_indicators(df)
        df = self.filter_chain.calculate_indicators(df)
        return df
    
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze data and generate filtered signal.
        
        Args:
            df: DataFrame with OHLCV data
            index: Current candle index
            
        Returns:
            Filtered TradeSignal
        """
        # Get base strategy signal
        base_signal = self.base_strategy.analyze(df, index)
        
        # If it's a HOLD, don't need to filter
        if base_signal.signal == Signal.HOLD:
            return base_signal
        
        # Apply filters
        result = self.filter_chain.apply(base_signal, df, index, self._context)
        
        if not result.allow_signal:
            logger.debug(f"Signal blocked by filter: {result.reason}")
            return TradeSignal(
                signal=Signal.HOLD,
                strength=0.0,
                metadata={"filtered": True, "filter_reason": result.reason}
            )
        
        # Return modified signal or original
        if result.modified_signal:
            # Add filter metadata
            result.modified_signal.metadata["filter_data"] = result.metadata
            return result.modified_signal
        
        base_signal.metadata["filter_data"] = result.metadata
        return base_signal
    
    def get_required_history(self) -> int:
        """Get max required history from strategy and filters."""
        return max(
            self.base_strategy.get_required_history(),
            self.filter_chain.get_required_history()
        )
    
    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate data for base strategy."""
        return self.base_strategy.validate_data(df)
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """Get param schema from base strategy."""
        return self.base_strategy.get_param_schema()


# Import specific filters for convenience
from src.strategies.filters.regime_detector import RegimeFilter, RegimeDetector
from src.strategies.filters.multi_timeframe import MultiTimeframeFilter

try:
    from src.strategies.filters.ml_filter import MLSignalFilter, LSTMSignalFilter
except ImportError:
    MLSignalFilter = None
    LSTMSignalFilter = None

try:
    from src.strategies.filters.sentiment_filter import SentimentFilter
except ImportError:
    SentimentFilter = None

__all__ = [
    'BaseFilter',
    'FilterChain',
    'FilteredStrategy',
    'FilterResult',
    'MarketRegime',
    'RegimeFilter',
    'RegimeDetector',
    'MultiTimeframeFilter',
    'MLSignalFilter',
    'LSTMSignalFilter',
    'SentimentFilter',
]
