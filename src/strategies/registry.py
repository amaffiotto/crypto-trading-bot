"""Strategy registry for discovering and managing strategies."""

from pathlib import Path
from typing import Dict, List, Optional, Type
import importlib
import importlib.util

from src.strategies.base import BaseStrategy
from src.utils.logger import get_logger

logger = get_logger()


class StrategyRegistry:
    """
    Registry for discovering and managing trading strategies.
    
    Provides methods to register, discover, and instantiate strategies.
    """
    
    def __init__(self):
        """Initialize the strategy registry."""
        self._strategies: Dict[str, Type[BaseStrategy]] = {}
        self._loaded = False
    
    def register(self, strategy_class: Type[BaseStrategy]) -> None:
        """
        Register a strategy class.
        
        Args:
            strategy_class: Strategy class to register
        """
        if not issubclass(strategy_class, BaseStrategy):
            raise TypeError(f"{strategy_class} must be a subclass of BaseStrategy")
        
        name = strategy_class.name
        self._strategies[name] = strategy_class
        logger.debug(f"Registered strategy: {name}")
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a strategy by name.
        
        Args:
            name: Strategy name
            
        Returns:
            True if strategy was unregistered
        """
        if name in self._strategies:
            del self._strategies[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Type[BaseStrategy]]:
        """
        Get a strategy class by name.
        
        Args:
            name: Strategy name
            
        Returns:
            Strategy class or None if not found
        """
        self._ensure_loaded()
        return self._strategies.get(name)
    
    def get_instance(self, name: str, params: Optional[dict] = None) -> Optional[BaseStrategy]:
        """
        Get an instance of a strategy.
        
        Args:
            name: Strategy name
            params: Optional parameters for the strategy
            
        Returns:
            Strategy instance or None if not found
        """
        strategy_class = self.get(name)
        if strategy_class:
            return strategy_class(params)
        return None
    
    def list_strategies(self) -> List[Dict[str, str]]:
        """
        List all registered strategies.
        
        Returns:
            List of dictionaries with strategy info
        """
        self._ensure_loaded()
        return [
            {
                'name': cls.name,
                'description': cls.description,
                'version': cls.version
            }
            for cls in self._strategies.values()
        ]
    
    def get_names(self) -> List[str]:
        """Get list of registered strategy names."""
        self._ensure_loaded()
        return list(self._strategies.keys())
    
    def get_all(self) -> Dict[str, Type[BaseStrategy]]:
        """Get all registered strategies."""
        self._ensure_loaded()
        return self._strategies.copy()
    
    def _ensure_loaded(self) -> None:
        """Ensure built-in strategies are loaded."""
        if not self._loaded:
            self.load_builtin()
            self._loaded = True
    
    def load_builtin(self) -> int:
        """
        Load built-in strategies.
        
        Returns:
            Number of strategies loaded
        """
        from src.strategies.builtin import (
            # Simple proven strategies (BEST)
            SimpleTrendStrategy,
            MomentumRSIStrategy,
            # Basic strategies (educational)
            MACrossoverStrategy,
            RSIStrategy,
            MACDStrategy,
            BollingerStrategy,
            # Intermediate strategies
            TrendMomentumStrategy,
            MeanReversionStrategy,
            SuperTrendStrategy,
            GridTradingStrategy,
            DCAStrategy,
            TripleEMAStrategy,
            BreakoutStrategy,
            # Research-backed strategies (advanced)
            ADXBBTrendStrategy,
            DonchianBreakoutStrategy,
            RegimeFilterStrategy,
            MultiConfirmStrategy,
            VolatilityBreakoutStrategy,
        )
        
        builtin = [
            # Simple proven strategies (START HERE)
            SimpleTrendStrategy,
            MomentumRSIStrategy,
            # Basic strategies (educational - learn with these)
            MACrossoverStrategy,
            RSIStrategy,
            MACDStrategy,
            BollingerStrategy,
            # Intermediate strategies
            TrendMomentumStrategy,
            MeanReversionStrategy,
            SuperTrendStrategy,
            GridTradingStrategy,
            DCAStrategy,
            TripleEMAStrategy,
            BreakoutStrategy,
            # Research-backed strategies (advanced)
            ADXBBTrendStrategy,
            DonchianBreakoutStrategy,
            RegimeFilterStrategy,
            MultiConfirmStrategy,
            VolatilityBreakoutStrategy,
        ]
        
        for strategy_class in builtin:
            self.register(strategy_class)
        
        logger.info(f"Loaded {len(builtin)} built-in strategies")
        return len(builtin)
    
    def load_from_directory(self, directory: Path) -> int:
        """
        Load custom strategies from a directory.
        
        Args:
            directory: Path to directory containing strategy files
            
        Returns:
            Number of strategies loaded
        """
        if not directory.exists():
            logger.warning(f"Strategy directory not found: {directory}")
            return 0
        
        loaded = 0
        
        for file_path in directory.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            try:
                # Load module from file
                spec = importlib.util.spec_from_file_location(
                    file_path.stem, file_path
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find strategy classes in module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseStrategy) and 
                            attr is not BaseStrategy):
                            self.register(attr)
                            loaded += 1
                            
            except Exception as e:
                logger.error(f"Error loading strategy from {file_path}: {e}")
        
        if loaded:
            logger.info(f"Loaded {loaded} custom strategies from {directory}")
        
        return loaded
    
    def clear(self) -> None:
        """Clear all registered strategies."""
        self._strategies.clear()
        self._loaded = False


# Global registry instance
_registry: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry instance."""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry
