"""Tests for strategy filters (Regime, Multi-Timeframe, FilterChain)."""

import pandas as pd
import numpy as np
import pytest

from src.strategies.base import TradeSignal, Signal
from src.strategies.filters import (
    BaseFilter, FilterChain, FilteredStrategy, FilterResult, MarketRegime,
)
from src.strategies.filters.regime_detector import RegimeDetector, RegimeFilter
from src.strategies.filters.multi_timeframe import (
    MultiTimeframeAnalyzer, MultiTimeframeFilter, resample_to_higher_timeframe,
    get_timeframe_minutes,
)


class TestRegimeDetector:

    @pytest.fixture
    def detector(self):
        return RegimeDetector(adx_period=14, ma_period=50, atr_period=14)

    def test_calculate_indicators_adds_columns(self, detector, sample_ohlcv):
        df = detector.calculate_indicators(sample_ohlcv)
        assert "regime_adx" in df.columns or "regime_ma" in df.columns
        assert "regime_atr" in df.columns

    def test_detect_returns_regime(self, detector, sample_ohlcv):
        df = detector.calculate_indicators(sample_ohlcv)
        required = detector.get_required_history()
        regime = detector.detect(df, required + 10)
        assert isinstance(regime, MarketRegime)

    def test_detect_unknown_for_early_index(self, detector, sample_ohlcv):
        df = detector.calculate_indicators(sample_ohlcv)
        regime = detector.detect(df, 0)
        assert regime == MarketRegime.UNKNOWN

    def test_get_regime_info(self, detector, sample_ohlcv):
        df = detector.calculate_indicators(sample_ohlcv)
        info = detector.get_regime_info(df, detector.get_required_history() + 10)
        assert "regime" in info
        assert "is_trending" in info


class TestRegimeFilter:

    def test_allowed_regimes_pass(self, sample_ohlcv):
        filt = RegimeFilter(allowed_regimes=["trending_bullish", "trending_bearish", "ranging",
                                              "high_volatility", "low_volatility", "unknown"])
        df = filt.calculate_indicators(sample_ohlcv)
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        idx = filt.get_required_history() + 10
        result = filt.apply(sig, df, idx)
        assert result.allow_signal

    def test_disabled_filter_passes_all(self, sample_ohlcv):
        filt = RegimeFilter(allowed_regimes=[], enabled=False)
        df = filt.calculate_indicators(sample_ohlcv)
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        result = filt.apply(sig, df, filt.get_required_history() + 10)
        assert result.allow_signal

    def test_no_restrictions_passes(self, sample_ohlcv):
        filt = RegimeFilter()
        df = filt.calculate_indicators(sample_ohlcv)
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        result = filt.apply(sig, df, filt.get_required_history() + 10)
        assert result.allow_signal


class TestMultiTimeframeFilter:

    def test_no_context_passes(self, sample_ohlcv):
        filt = MultiTimeframeFilter(confirmation_timeframes=["4h"])
        df = filt.calculate_indicators(sample_ohlcv)
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        result = filt.apply(sig, df, len(df) - 1)
        assert result.allow_signal

    def test_with_confirming_data(self, sample_ohlcv, trending_up_ohlcv):
        filt = MultiTimeframeFilter(confirmation_timeframes=["4h"], min_confirmations=1)
        df = filt.calculate_indicators(sample_ohlcv)
        context = {"timeframe_data": {"4h": trending_up_ohlcv}}
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        result = filt.apply(sig, df, len(df) - 1, context)
        assert isinstance(result, FilterResult)

    def test_resample_to_higher_timeframe(self, sample_ohlcv):
        resampled = resample_to_higher_timeframe(sample_ohlcv, "1h", "4h")
        assert len(resampled) < len(sample_ohlcv)
        assert "close" in resampled.columns

    def test_get_timeframe_minutes(self):
        assert get_timeframe_minutes("1h") == 60
        assert get_timeframe_minutes("4h") == 240
        assert get_timeframe_minutes("1d") == 1440


class TestFilterChain:

    def test_empty_chain_passes(self, sample_ohlcv):
        chain = FilterChain([])
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        result = chain.apply(sig, sample_ohlcv, 100)
        assert result.allow_signal

    def test_chain_blocks_if_one_blocks(self, sample_ohlcv):
        class BlockAll(BaseFilter):
            name = "Block All"
            def apply(self, signal, df, index, context=None):
                return FilterResult(allow_signal=False, reason="blocked")

        chain = FilterChain([BlockAll()])
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        result = chain.apply(sig, sample_ohlcv, 100)
        assert not result.allow_signal

    def test_chain_passes_if_all_pass(self, sample_ohlcv):
        class PassAll(BaseFilter):
            name = "Pass All"
            def apply(self, signal, df, index, context=None):
                return FilterResult(allow_signal=True)

        chain = FilterChain([PassAll(), PassAll()])
        sig = TradeSignal(signal=Signal.BUY, strength=0.8)
        result = chain.apply(sig, sample_ohlcv, 100)
        assert result.allow_signal


class TestFilteredStrategy:

    def test_filtered_strategy_runs_backtest(self, sample_ohlcv, always_buy_strategy):
        from src.backtesting.engine import BacktestEngine
        filt = RegimeFilter(allowed_regimes=["trending_bullish", "trending_bearish",
                                              "ranging", "high_volatility", "low_volatility",
                                              "unknown"])
        filtered = FilteredStrategy(always_buy_strategy, filters=[filt])
        engine = BacktestEngine(initial_capital=10000)
        result = engine.run(filtered, sample_ohlcv)
        assert result.initial_capital == 10000

    def test_hold_signals_not_filtered(self, sample_ohlcv, never_trade_strategy):
        filt = RegimeFilter(allowed_regimes=[])
        filtered = FilteredStrategy(never_trade_strategy, filters=[filt])
        df = filtered.calculate_indicators(sample_ohlcv.copy())
        sig = filtered.analyze(df, filtered.get_required_history() + 10)
        assert sig.signal == Signal.HOLD
