"""Tests for ConfigManager."""

import pytest
from src.core.config import ConfigManager


class TestConfigManager:

    def test_defaults_applied(self, tmp_config):
        assert tmp_config.get("log_level") == "INFO"
        assert tmp_config.get("backtesting.default_capital") == 10000

    def test_set_and_get(self, tmp_config):
        tmp_config.set("backtesting.default_capital", 50000)
        assert tmp_config.get("backtesting.default_capital") == 50000

    def test_dot_notation_nested(self, tmp_config):
        tmp_config.set("custom.nested.key", "value")
        assert tmp_config.get("custom.nested.key") == "value"

    def test_get_missing_returns_default(self, tmp_config):
        assert tmp_config.get("nonexistent.key", "fallback") == "fallback"

    def test_save_and_reload(self, tmp_config):
        tmp_config.set("log_level", "DEBUG")
        tmp_config.save()
        reloaded = ConfigManager(config_path=str(tmp_config.config_path))
        assert reloaded.get("log_level") == "DEBUG"

    def test_add_exchange(self, tmp_config):
        tmp_config.add_exchange("binance", "key1", "secret1", sandbox=True)
        exchanges = tmp_config.get_exchanges()
        assert len(exchanges) == 1
        assert exchanges[0]["name"] == "binance"
        assert exchanges[0]["sandbox"] is True

    def test_add_exchange_updates_existing(self, tmp_config):
        tmp_config.add_exchange("binance", "key1", "secret1")
        tmp_config.add_exchange("binance", "key2", "secret2")
        exchanges = tmp_config.get_exchanges()
        assert len(exchanges) == 1
        assert exchanges[0]["api_key"] == "key2"

    def test_remove_exchange(self, tmp_config):
        tmp_config.add_exchange("binance", "key1", "secret1")
        assert tmp_config.remove_exchange("binance")
        assert len(tmp_config.get_exchanges()) == 0

    def test_remove_nonexistent_exchange(self, tmp_config):
        assert not tmp_config.remove_exchange("kraken")

    def test_get_exchanges_dict_format(self, tmp_config):
        """ConfigManager should normalize dict-format exchanges to list."""
        tmp_config.set("exchanges", {
            "binance": {"api_key": "k", "api_secret": "s", "sandbox": False}
        })
        exchanges = tmp_config.get_exchanges()
        assert isinstance(exchanges, list)
        assert len(exchanges) == 1
        assert exchanges[0]["name"] == "binance"

    def test_strategy_params(self, tmp_config):
        tmp_config.set_strategy_params("rsi", {"period": 21, "overbought": 75})
        params = tmp_config.get_strategy_params("rsi")
        assert params["period"] == 21

    def test_config_exists(self, tmp_config):
        assert not tmp_config.config_exists()
        tmp_config.save()
        assert tmp_config.config_exists()

    def test_properties(self, tmp_config):
        assert tmp_config.log_level == "INFO"
        assert isinstance(tmp_config.backtesting_config, dict)
        assert isinstance(tmp_config.notifications_config, dict)
