"""Fast-forward paper trading validator.

Replays historical OHLCV data through a strategy candle-by-candle,
simulating the full paper-trading loop. Results can be compared against
a standard backtest to detect discrepancies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.strategies.base import BaseStrategy, Signal, TradeSignal
from src.backtesting.engine import BacktestResult, Trade
from src.backtesting.metrics import MetricsCalculator, PerformanceMetrics
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class PaperTrade:
    """A single simulated paper trade."""
    entry_time: datetime
    exit_time: Optional[datetime]
    side: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    fee: float = 0.0
    exit_reason: str = ""


@dataclass
class ValidationReport:
    """Results from a paper-trading replay."""
    strategy_name: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    trades: List[PaperTrade]
    equity_curve: pd.DataFrame
    signals_log: List[Dict[str, Any]]
    metrics: Optional[PerformanceMetrics] = None

    @property
    def total_return_pct(self) -> float:
        if self.initial_balance == 0:
            return 0.0
        return (self.final_balance - self.initial_balance) / self.initial_balance * 100

    @property
    def num_trades(self) -> int:
        return len([t for t in self.trades if t.exit_time is not None])


class PaperTradingValidator:
    """Replays historical data through a strategy as if it were live."""

    def __init__(
        self,
        strategy: BaseStrategy,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        initial_balance: float = 10000.0,
        fee_percent: float = 0.1,
        slippage_percent: float = 0.05,
        position_size: float = 1.0,
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_balance = initial_balance
        self.fee_pct = fee_percent / 100
        self.slippage_pct = slippage_percent / 100
        self.position_size = min(1.0, max(0.01, position_size))

    def run(
        self,
        historical_data: pd.DataFrame,
        progress_callback=None,
    ) -> ValidationReport:
        """Replay *historical_data* bar-by-bar, simulating paper trading.

        The replay intentionally mirrors the behaviour of BacktestEngine
        so that both can be compared, but the data is fed incrementally
        as if it were arriving in real time.
        """
        balance = self.initial_balance
        position: Optional[Dict] = None
        trades: List[PaperTrade] = []
        equity_log: List[Dict] = []
        signals_log: List[Dict[str, Any]] = []

        df = self.strategy.calculate_indicators(historical_data.copy())
        min_hist = self.strategy.get_required_history()

        total = len(df) - min_hist
        for i in range(min_hist, len(df)):
            row = df.iloc[i]
            ts = row["timestamp"]
            close = row["close"]
            high = row["high"]
            low = row["low"]

            # --- check SL / TP on open position ---
            if position is not None:
                stopped = False
                sl = position.get("stop_loss")
                tp = position.get("take_profit")
                if sl and low <= sl:
                    exit_price = sl * (1 - self.slippage_pct)
                    balance, trade = self._close(position, ts, exit_price, balance, "stop_loss")
                    trades.append(trade)
                    position = None
                    stopped = True
                if not stopped and position is not None and tp and high >= tp:
                    exit_price = tp * (1 - self.slippage_pct)
                    balance, trade = self._close(position, ts, exit_price, balance, "take_profit")
                    trades.append(trade)
                    position = None
                    stopped = True

                if stopped:
                    equity = balance
                    equity_log.append({"timestamp": ts, "equity": equity})
                    if progress_callback and (i - min_hist) % 100 == 0:
                        progress_callback(i - min_hist, total)
                    continue

            # --- get strategy signal (only uses data up to current bar) ---
            signal = self.strategy.analyze(df, i)
            signals_log.append({
                "index": i,
                "timestamp": ts,
                "signal": signal.signal.value,
                "strength": signal.strength,
            })

            if signal.signal == Signal.BUY and position is None:
                exec_price = close * (1 + self.slippage_pct)
                trade_cap = balance * self.position_size
                fee = trade_cap * self.fee_pct
                qty = (trade_cap - fee) / exec_price
                position = {
                    "entry_time": ts,
                    "entry_price": exec_price,
                    "quantity": qty,
                    "entry_fee": fee,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                }

            elif signal.signal == Signal.SELL and position is not None:
                exec_price = close * (1 - self.slippage_pct)
                balance, trade = self._close(position, ts, exec_price, balance, "signal")
                trades.append(trade)
                position = None

            # equity
            if position is not None:
                unrealized = (close - position["entry_price"]) * position["quantity"]
                equity = balance + unrealized
            else:
                equity = balance
            equity_log.append({"timestamp": ts, "equity": equity})

            if progress_callback and (i - min_hist) % 100 == 0:
                progress_callback(i - min_hist, total)

        # close open position at end
        if position is not None:
            last = df.iloc[-1]
            exec_price = last["close"] * (1 - self.slippage_pct)
            balance, trade = self._close(position, last["timestamp"], exec_price, balance, "end_of_data")
            trades.append(trade)

        eq_df = pd.DataFrame(equity_log)
        report = ValidationReport(
            strategy_name=self.strategy.name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_date=df.iloc[min_hist]["timestamp"],
            end_date=df.iloc[-1]["timestamp"],
            initial_balance=self.initial_balance,
            final_balance=balance,
            trades=trades,
            equity_curve=eq_df,
            signals_log=signals_log,
        )

        # attach performance metrics
        if trades:
            bt_trades = [
                Trade(
                    entry_time=t.entry_time,
                    exit_time=t.exit_time or t.entry_time,
                    side=t.side,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price or t.entry_price,
                    quantity=t.quantity,
                    pnl=t.pnl or 0,
                    pnl_percent=t.pnl_percent or 0,
                    fee=t.fee,
                )
                for t in trades if t.exit_time is not None
            ]
            bt_result = BacktestResult(
                strategy_name=self.strategy.name,
                symbol=self.symbol,
                timeframe=self.timeframe,
                start_date=report.start_date,
                end_date=report.end_date,
                initial_capital=self.initial_balance,
                final_capital=balance,
                trades=bt_trades,
                equity_curve=eq_df,
                parameters=self.strategy.params,
            )
            report.metrics = MetricsCalculator().calculate(bt_result)

        return report

    # ------------------------------------------------------------------
    def _close(self, pos: Dict, ts, exit_price: float, balance: float, reason: str):
        gross_pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
        exit_value = pos["quantity"] * exit_price
        exit_fee = exit_value * self.fee_pct
        total_fee = pos["entry_fee"] + exit_fee
        net_pnl = gross_pnl - total_fee
        entry_value = pos["quantity"] * pos["entry_price"]
        pnl_pct = (net_pnl / entry_value) * 100 if entry_value else 0

        balance += net_pnl

        trade = PaperTrade(
            entry_time=pos["entry_time"],
            exit_time=ts,
            side="long",
            entry_price=pos["entry_price"],
            exit_price=exit_price,
            quantity=pos["quantity"],
            pnl=net_pnl,
            pnl_percent=pnl_pct,
            fee=total_fee,
            exit_reason=reason,
        )
        return balance, trade

    # ------------------------------------------------------------------
    @staticmethod
    def compare_with_backtest(
        report: ValidationReport,
        backtest_result: BacktestResult,
        tolerance_pct: float = 1.0,
    ) -> Dict[str, Any]:
        """Compare paper replay results against a standard backtest.

        Returns a dict with per-metric comparisons and a boolean ``match``
        indicating whether all values fall within *tolerance_pct*.
        """
        bt_return = backtest_result.total_return_pct
        pv_return = report.total_return_pct
        return_diff = abs(bt_return - pv_return)

        bt_trades = backtest_result.num_trades
        pv_trades = report.num_trades
        trades_diff = abs(bt_trades - pv_trades)

        bt_final = backtest_result.final_capital
        pv_final = report.final_balance
        capital_diff_pct = abs(bt_final - pv_final) / max(bt_final, 1) * 100

        match = (
            return_diff <= tolerance_pct
            and trades_diff <= 1
            and capital_diff_pct <= tolerance_pct
        )

        return {
            "match": match,
            "backtest_return_pct": bt_return,
            "paper_return_pct": pv_return,
            "return_diff_pct": return_diff,
            "backtest_trades": bt_trades,
            "paper_trades": pv_trades,
            "trades_diff": trades_diff,
            "backtest_final_capital": bt_final,
            "paper_final_balance": pv_final,
            "capital_diff_pct": capital_diff_pct,
        }
