"""Performance metrics calculation for backtesting."""

from dataclasses import dataclass
from typing import List, Optional
import numpy as np
import pandas as pd

from src.backtesting.engine import BacktestResult, Trade


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a backtest."""
    # Returns
    total_return: float
    total_return_pct: float
    annualized_return: float
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # in periods
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Profit metrics
    profit_factor: float
    avg_trade_pnl: float
    avg_winning_trade: float
    avg_losing_trade: float
    largest_win: float
    largest_loss: float
    
    # Other
    avg_holding_period: float  # in hours
    total_fees: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "Total Return": f"{self.total_return_pct:.2f}%",
            "Annualized Return": f"{self.annualized_return:.2f}%",
            "Sharpe Ratio": f"{self.sharpe_ratio:.2f}",
            "Sortino Ratio": f"{self.sortino_ratio:.2f}",
            "Max Drawdown": f"{self.max_drawdown:.2f}%",
            "Max Drawdown Duration": f"{self.max_drawdown_duration} periods",
            "Total Trades": self.total_trades,
            "Win Rate": f"{self.win_rate:.1f}%",
            "Profit Factor": f"{self.profit_factor:.2f}",
            "Avg Trade": f"${self.avg_trade_pnl:.2f}",
            "Avg Winner": f"${self.avg_winning_trade:.2f}",
            "Avg Loser": f"${self.avg_losing_trade:.2f}",
            "Largest Win": f"${self.largest_win:.2f}",
            "Largest Loss": f"${self.largest_loss:.2f}",
            "Avg Holding Period": f"{self.avg_holding_period:.1f}h",
            "Total Fees": f"${self.total_fees:.2f}"
        }


class MetricsCalculator:
    """Calculates performance metrics from backtest results."""
    
    def __init__(self, risk_free_rate: float = 0.0):
        """
        Initialize metrics calculator.
        
        Args:
            risk_free_rate: Annual risk-free rate (default 0)
        """
        self.risk_free_rate = risk_free_rate
    
    def calculate(self, result: BacktestResult) -> PerformanceMetrics:
        """
        Calculate all performance metrics.
        
        Args:
            result: BacktestResult from backtesting
            
        Returns:
            PerformanceMetrics with all calculated values
        """
        trades = result.trades
        equity_curve = result.equity_curve
        
        # Basic returns
        total_return = result.total_return
        total_return_pct = result.total_return_pct
        
        # Calculate annualized return
        if not equity_curve.empty:
            days = (result.end_date - result.start_date).days
            years = max(days / 365, 1/365)  # Avoid division by zero
            annualized_return = ((1 + total_return) ** (1 / years) - 1) * 100
        else:
            annualized_return = 0.0
        
        # Calculate risk metrics from equity curve
        sharpe = self._calculate_sharpe_ratio(equity_curve)
        sortino = self._calculate_sortino_ratio(equity_curve)
        max_dd, max_dd_duration = self._calculate_max_drawdown(equity_curve)
        
        # Trade statistics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.pnl > 0)
        losing_trades = sum(1 for t in trades if t.pnl <= 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Profit metrics
        pnls = [t.pnl for t in trades]
        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [t.pnl for t in trades if t.pnl <= 0]
        
        avg_trade_pnl = np.mean(pnls) if pnls else 0
        avg_winning = np.mean(wins) if wins else 0
        avg_losing = np.mean(losses) if losses else 0
        largest_win = max(pnls) if pnls else 0
        largest_loss = min(pnls) if pnls else 0
        
        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1  # Avoid div by zero
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Average holding period
        holding_periods = []
        for trade in trades:
            duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600
            holding_periods.append(duration)
        avg_holding = np.mean(holding_periods) if holding_periods else 0
        
        # Total fees
        total_fees = sum(t.fee for t in trades)
        
        return PerformanceMetrics(
            total_return=total_return,
            total_return_pct=total_return_pct,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_pnl=avg_trade_pnl,
            avg_winning_trade=avg_winning,
            avg_losing_trade=avg_losing,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period=avg_holding,
            total_fees=total_fees
        )
    
    def _calculate_sharpe_ratio(self, equity_curve: pd.DataFrame, 
                                periods_per_year: int = 252) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            equity_curve: DataFrame with equity column
            periods_per_year: Trading periods per year (252 for daily)
            
        Returns:
            Sharpe ratio
        """
        if equity_curve.empty or len(equity_curve) < 2:
            return 0.0
        
        returns = equity_curve["equity"].pct_change().dropna()
        
        if returns.std() == 0:
            return 0.0
        
        excess_returns = returns - (self.risk_free_rate / periods_per_year)
        sharpe = np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()
        
        return float(sharpe)
    
    def _calculate_sortino_ratio(self, equity_curve: pd.DataFrame,
                                  periods_per_year: int = 252) -> float:
        """
        Calculate Sortino ratio (only considers downside volatility).
        
        Args:
            equity_curve: DataFrame with equity column
            periods_per_year: Trading periods per year
            
        Returns:
            Sortino ratio
        """
        if equity_curve.empty or len(equity_curve) < 2:
            return 0.0
        
        returns = equity_curve["equity"].pct_change().dropna()
        
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std()
        
        if downside_std == 0 or np.isnan(downside_std):
            return 0.0 if returns.mean() <= 0 else float('inf')
        
        excess_returns = returns.mean() - (self.risk_free_rate / periods_per_year)
        sortino = np.sqrt(periods_per_year) * excess_returns / downside_std
        
        return float(sortino)
    
    def _calculate_max_drawdown(self, equity_curve: pd.DataFrame) -> tuple:
        """
        Calculate maximum drawdown and duration.
        
        Args:
            equity_curve: DataFrame with equity column
            
        Returns:
            Tuple of (max_drawdown_pct, max_duration_periods)
        """
        if equity_curve.empty or len(equity_curve) < 2:
            return 0.0, 0
        
        equity = equity_curve["equity"]
        
        # Calculate running maximum
        running_max = equity.expanding().max()
        
        # Calculate drawdown
        drawdown = (equity - running_max) / running_max * 100
        max_drawdown = abs(drawdown.min())
        
        # Calculate max drawdown duration
        is_drawdown = drawdown < 0
        drawdown_periods = []
        current_duration = 0
        
        for is_dd in is_drawdown:
            if is_dd:
                current_duration += 1
            else:
                if current_duration > 0:
                    drawdown_periods.append(current_duration)
                current_duration = 0
        
        if current_duration > 0:
            drawdown_periods.append(current_duration)
        
        max_duration = max(drawdown_periods) if drawdown_periods else 0
        
        return float(max_drawdown), int(max_duration)
    
    def calculate_monthly_returns(self, result: BacktestResult) -> pd.DataFrame:
        """
        Calculate monthly returns for heatmap.
        
        Args:
            result: BacktestResult
            
        Returns:
            DataFrame with year/month returns
        """
        equity_curve = result.equity_curve.copy()
        
        if equity_curve.empty:
            return pd.DataFrame()
        
        # Set timestamp as index
        equity_curve["timestamp"] = pd.to_datetime(equity_curve["timestamp"])
        equity_curve.set_index("timestamp", inplace=True)
        
        # Resample to monthly and calculate returns
        monthly = equity_curve["equity"].resample("ME").last()
        monthly_returns = monthly.pct_change() * 100
        
        # Create year/month pivot
        df = pd.DataFrame({
            "year": monthly_returns.index.year,
            "month": monthly_returns.index.month,
            "return": monthly_returns.values
        })
        
        pivot = df.pivot(index="year", columns="month", values="return")
        pivot.columns = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][:len(pivot.columns)]
        
        return pivot
    
    def get_trade_distribution(self, result: BacktestResult) -> pd.Series:
        """
        Get distribution of trade P&L.
        
        Args:
            result: BacktestResult
            
        Returns:
            Series with P&L values
        """
        pnls = [t.pnl for t in result.trades]
        return pd.Series(pnls, name="pnl")
