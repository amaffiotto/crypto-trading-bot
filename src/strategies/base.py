"""Base strategy class and trading signals."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
import pandas as pd


class Signal(Enum):
    """Trading signal types."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradeSignal:
    """
    Represents a trading signal from a strategy.
    
    Attributes:
        signal: The trading action (BUY, SELL, HOLD)
        strength: Signal confidence from 0.0 to 1.0
        stop_loss: Optional stop loss price
        take_profit: Optional take profit price
        metadata: Additional signal metadata
    """
    signal: Signal
    strength: float = 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate signal strength."""
        self.strength = max(0.0, min(1.0, self.strength))


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All custom strategies must inherit from this class and implement
    the required abstract methods.
    
    Attributes:
        name: Human-readable strategy name
        description: Brief description of the strategy
        version: Strategy version
    """
    
    name: str = "Base Strategy"
    description: str = "Abstract base strategy"
    version: str = "1.0.0"
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with parameters.
        
        Args:
            params: Strategy parameters. Uses defaults if not provided.
        """
        self._params = self.default_params()
        if params:
            self._params.update(params)
    
    @property
    def params(self) -> Dict[str, Any]:
        """Get current strategy parameters."""
        return self._params.copy()
    
    def set_params(self, **kwargs) -> None:
        """Update strategy parameters."""
        self._params.update(kwargs)
    
    @abstractmethod
    def default_params(self) -> Dict[str, Any]:
        """
        Get default parameters for the strategy.
        
        Returns:
            Dictionary of parameter names to default values
        """
        pass
    
    @abstractmethod
    def analyze(self, df: pd.DataFrame, index: int) -> TradeSignal:
        """
        Analyze market data and generate a trading signal.
        
        IMPORTANT: This method should only use data up to and including
        the given index to avoid look-ahead bias.
        
        Args:
            df: DataFrame with OHLCV data and calculated indicators
            index: Current candle index (0-based)
            
        Returns:
            TradeSignal with BUY, SELL, or HOLD action
        """
        pass
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators needed by the strategy.
        
        Override this method to add custom indicators to the DataFrame.
        The default implementation returns the DataFrame unchanged.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        return df
    
    def validate_data(self, df: pd.DataFrame) -> bool:
        """
        Validate that the DataFrame has required columns.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            True if valid, raises ValueError otherwise
        """
        required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing = [col for col in required if col not in df.columns]
        
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        if df.empty:
            raise ValueError("DataFrame is empty")
        
        return True
    
    def get_required_history(self) -> int:
        """
        Get the minimum number of candles required for the strategy.
        
        Override this to specify how many historical candles are needed
        before the strategy can generate valid signals.
        
        Returns:
            Number of candles required
        """
        return 1
    
    def get_param_schema(self) -> Dict[str, Dict[str, Any]]:
        """
        Get schema for strategy parameters (for UI generation).
        
        Override to provide parameter metadata for GUI forms.
        
        Returns:
            Dictionary mapping param names to their schema:
            {
                'param_name': {
                    'type': 'int' | 'float' | 'bool' | 'str',
                    'min': minimum value (optional),
                    'max': maximum value (optional),
                    'description': 'Parameter description'
                }
            }
        """
        return {}
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(params={self._params})"
    
    def __str__(self) -> str:
        return f"{self.name} v{self.version}"
