"""Display utilities for CLI output."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.backtesting.engine import BacktestResult
from src.backtesting.metrics import PerformanceMetrics


def display_backtest_results(result: BacktestResult, 
                             metrics: PerformanceMetrics,
                             console: Console) -> None:
    """
    Display backtest results in a formatted table.
    
    Args:
        result: BacktestResult from backtesting
        metrics: Calculated performance metrics
        console: Rich Console instance
    """
    # Create results panel
    title = f"BACKTEST RESULTS - {result.strategy_name} ({result.symbol})"
    
    # Main metrics table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    # Period info
    period = f"{result.start_date.strftime('%Y-%m-%d')} → {result.end_date.strftime('%Y-%m-%d')}"
    days = (result.end_date - result.start_date).days
    
    table.add_row("Period", f"{period} ({days} days)")
    table.add_row("Timeframe", result.timeframe)
    table.add_row("Initial Capital", f"${result.initial_capital:,.2f}")
    table.add_row("Final Capital", f"${result.final_capital:,.2f}")
    table.add_row("", "")  # Spacer
    
    # Performance metrics
    return_color = "green" if metrics.total_return_pct >= 0 else "red"
    table.add_row("Total Return", Text(f"{metrics.total_return_pct:+.2f}%", style=return_color))
    
    sharpe_color = "green" if metrics.sharpe_ratio >= 1 else ("yellow" if metrics.sharpe_ratio >= 0 else "red")
    table.add_row("Sharpe Ratio", Text(f"{metrics.sharpe_ratio:.2f}", style=sharpe_color))
    
    table.add_row("Sortino Ratio", f"{metrics.sortino_ratio:.2f}")
    table.add_row("Max Drawdown", Text(f"-{metrics.max_drawdown:.2f}%", style="red"))
    table.add_row("", "")  # Spacer
    
    # Trade statistics
    table.add_row("Total Trades", str(metrics.total_trades))
    win_color = "green" if metrics.win_rate >= 50 else "yellow"
    table.add_row("Win Rate", Text(f"{metrics.win_rate:.1f}% ({metrics.winning_trades}/{metrics.total_trades})", style=win_color))
    
    pf_color = "green" if metrics.profit_factor >= 1.5 else ("yellow" if metrics.profit_factor >= 1 else "red")
    table.add_row("Profit Factor", Text(f"{metrics.profit_factor:.2f}", style=pf_color))
    
    avg_color = "green" if metrics.avg_trade_pnl >= 0 else "red"
    table.add_row("Avg Trade", Text(f"${metrics.avg_trade_pnl:+.2f}", style=avg_color))
    table.add_row("Avg Winner", Text(f"${metrics.avg_winning_trade:.2f}", style="green"))
    table.add_row("Avg Loser", Text(f"${metrics.avg_losing_trade:.2f}", style="red"))
    table.add_row("", "")  # Spacer
    
    table.add_row("Largest Win", Text(f"${metrics.largest_win:.2f}", style="green"))
    table.add_row("Largest Loss", Text(f"${metrics.largest_loss:.2f}", style="red"))
    table.add_row("Avg Holding Period", f"{metrics.avg_holding_period:.1f}h")
    table.add_row("Total Fees", f"${metrics.total_fees:.2f}")
    
    # Create panel
    panel = Panel(
        table,
        title=f"[bold white]{title}[/]",
        border_style="cyan",
        padding=(1, 2)
    )
    
    console.print("\n")
    console.print(panel)
    
    # Strategy parameters
    if result.parameters:
        params_text = ", ".join(f"{k}={v}" for k, v in result.parameters.items())
        console.print(f"\n[dim]Strategy parameters: {params_text}[/]")


def display_quick_summary(result: BacktestResult, console: Console) -> None:
    """Display a quick one-line summary."""
    pnl = result.final_capital - result.initial_capital
    pct = (pnl / result.initial_capital) * 100
    
    color = "green" if pnl >= 0 else "red"
    
    console.print(
        f"[{color}]{result.strategy_name}[/] on {result.symbol}: "
        f"[{color}]{pct:+.2f}%[/] ({result.num_trades} trades, "
        f"{result.win_rate:.1f}% win rate)"
    )


def display_trade_list(result: BacktestResult, console: Console, 
                       max_trades: int = 10) -> None:
    """Display recent trades in a table."""
    if not result.trades:
        console.print("[yellow]No trades to display.[/]")
        return
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Entry")
    table.add_column("Exit")
    table.add_column("Side")
    table.add_column("Entry $", justify="right")
    table.add_column("Exit $", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("P&L %", justify="right")
    
    trades = result.trades[-max_trades:] if len(result.trades) > max_trades else result.trades
    
    for i, trade in enumerate(trades, 1):
        pnl_color = "green" if trade.pnl > 0 else "red"
        
        table.add_row(
            str(i),
            trade.entry_time.strftime("%m/%d %H:%M"),
            trade.exit_time.strftime("%m/%d %H:%M"),
            trade.side.upper(),
            f"${trade.entry_price:,.2f}",
            f"${trade.exit_price:,.2f}",
            Text(f"${trade.pnl:+.2f}", style=pnl_color),
            Text(f"{trade.pnl_percent:+.2f}%", style=pnl_color)
        )
    
    console.print(table)
    
    if len(result.trades) > max_trades:
        console.print(f"[dim]Showing last {max_trades} of {len(result.trades)} trades[/]")
