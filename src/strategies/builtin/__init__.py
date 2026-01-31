"""Built-in trading strategies."""

from .ma_crossover import MACrossoverStrategy
from .rsi_strategy import RSIStrategy
from .macd_strategy import MACDStrategy
from .bollinger import BollingerStrategy
from .trend_momentum import TrendMomentumStrategy
from .mean_reversion import MeanReversionStrategy
from .supertrend import SuperTrendStrategy
from .grid_strategy import GridTradingStrategy
from .dca_strategy import DCAStrategy
from .triple_ema import TripleEMAStrategy
from .breakout import BreakoutStrategy

# Research-backed strategies (higher probability)
from .adx_bb_trend import ADXBBTrendStrategy
from .donchian_breakout import DonchianBreakoutStrategy
from .regime_filter import RegimeFilterStrategy
from .multi_confirm import MultiConfirmStrategy
from .volatility_breakout import VolatilityBreakoutStrategy

# Simple proven strategies (BEST FOR BEGINNERS)
from .simple_trend import SimpleTrendStrategy
from .momentum_rsi import MomentumRSIStrategy

__all__ = [
    # Simple proven strategies (RECOMMENDED - START HERE)
    "SimpleTrendStrategy",
    "MomentumRSIStrategy",
    # Basic strategies (educational)
    "MACrossoverStrategy",
    "RSIStrategy", 
    "MACDStrategy",
    "BollingerStrategy",
    # Intermediate strategies
    "TrendMomentumStrategy",
    "MeanReversionStrategy",
    "SuperTrendStrategy",
    "GridTradingStrategy",
    "DCAStrategy",
    "TripleEMAStrategy",
    "BreakoutStrategy",
    # Research-backed strategies (advanced)
    "ADXBBTrendStrategy",
    "DonchianBreakoutStrategy",
    "RegimeFilterStrategy",
    "MultiConfirmStrategy",
    "VolatilityBreakoutStrategy",
]
