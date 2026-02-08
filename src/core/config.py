"""Configuration management module."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from src.utils.logger import get_logger

logger = get_logger()


class ConfigManager:
    """Manages application configuration with YAML support."""
    
    DEFAULT_CONFIG = {
        "log_level": "INFO",
        "exchanges": [],
        "backtesting": {
            "default_capital": 10000,
            "fee_percent": 0.1,
            "slippage_percent": 0.05,
            "default_timeframe": "1h"
        },
        "strategies": {
            "ma_crossover": {"fast_period": 9, "slow_period": 21},
            "rsi": {"period": 14, "overbought": 70, "oversold": 30},
            "macd": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            "bollinger": {"period": 20, "std_dev": 2.0}
        },
        "notifications": {
            "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
            "discord": {"enabled": False, "webhook_url": ""}
        },
        "data": {
            "cache_directory": "data/ohlcv",
            "max_cache_age_days": 7
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to config file. Defaults to config/config.yaml
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info(f"Configuration loaded from {self.config_path}")
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                self._config = {}
        else:
            logger.warning(f"Config file not found at {self.config_path}")
            self._config = {}
        
        # Merge with defaults
        self._config = self._deep_merge(self.DEFAULT_CONFIG.copy(), self._config)
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def config_exists(self) -> bool:
        """Check if configuration file exists."""
        return self.config_path.exists()
    
    def save(self) -> None:
        """Save current configuration to YAML file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Configuration saved to {self.config_path}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "backtesting.default_capital")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "backtesting.default_capital")
            value: Value to set
        """
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def get_exchanges(self) -> List[Dict[str, Any]]:
        """Get list of configured exchanges (each with 'name', 'api_key', 'api_secret', 'sandbox')."""
        raw = self.get("exchanges", [])
        if isinstance(raw, dict):
            return [{"name": k, "api_key": v.get("api_key", ""), "api_secret": v.get("api_secret", ""), "sandbox": v.get("sandbox", False)} for k, v in raw.items()]
        return raw if isinstance(raw, list) else []
    
    def add_exchange(self, name: str, api_key: str, api_secret: str, 
                     sandbox: bool = False) -> None:
        """Add a new exchange configuration."""
        exchanges = self.get_exchanges()
        
        # Check if exchange already exists
        for ex in exchanges:
            if ex.get("name") == name:
                ex["api_key"] = api_key
                ex["api_secret"] = api_secret
                ex["sandbox"] = sandbox
                logger.info(f"Updated exchange configuration: {name}")
                return
        
        # Add new exchange
        exchanges.append({
            "name": name,
            "api_key": api_key,
            "api_secret": api_secret,
            "sandbox": sandbox
        })
        self.set("exchanges", exchanges)
        logger.info(f"Added exchange configuration: {name}")
    
    def remove_exchange(self, name: str) -> bool:
        """Remove an exchange configuration."""
        exchanges = self.get_exchanges()
        original_len = len(exchanges)
        exchanges = [ex for ex in exchanges if ex.get("name") != name]
        
        if len(exchanges) < original_len:
            self.set("exchanges", exchanges)
            logger.info(f"Removed exchange configuration: {name}")
            return True
        return False
    
    def get_strategy_params(self, strategy_name: str) -> Dict[str, Any]:
        """Get parameters for a specific strategy."""
        return self.get(f"strategies.{strategy_name}", {})
    
    def set_strategy_params(self, strategy_name: str, params: Dict[str, Any]) -> None:
        """Set parameters for a specific strategy."""
        self.set(f"strategies.{strategy_name}", params)
    
    @property
    def log_level(self) -> str:
        """Get logging level."""
        return self.get("log_level", "INFO")
    
    @property
    def backtesting_config(self) -> Dict[str, Any]:
        """Get backtesting configuration."""
        return self.get("backtesting", self.DEFAULT_CONFIG["backtesting"])
    
    @property
    def notifications_config(self) -> Dict[str, Any]:
        """Get notifications configuration."""
        return self.get("notifications", self.DEFAULT_CONFIG["notifications"])
