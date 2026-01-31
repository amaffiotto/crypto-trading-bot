"""Interactive CLI menu system."""

import asyncio
import sys
import webbrowser
from datetime import datetime, timedelta
from typing import Optional

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.live import Live
from rich import print as rprint

from src.core.config import ConfigManager
from src.core.exchange import ExchangeManager, SUPPORTED_EXCHANGES
from src.core.data_manager import DataManager
from src.strategies.registry import get_registry
from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import MetricsCalculator
from src.backtesting.report import ReportGenerator
from src.trading.live_engine import LiveTradingEngine, TradingMode
from src.cli.display import display_backtest_results
from src.utils.logger import get_logger

logger = get_logger()
console = Console()


class CLIMenu:
    """Interactive command-line interface menu."""
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize CLI menu.
        
        Args:
            config_manager: ConfigManager instance
        """
        self.config = config_manager
        self.exchange_manager = ExchangeManager()
        self.data_manager = DataManager()
        self.strategy_registry = get_registry()
    
    def run(self) -> None:
        """Run the main menu loop."""
        self._show_banner()
        
        # Check if first run
        if not self.config.config_exists():
            self._run_setup_wizard()
        
        while True:
            choice = self._show_main_menu()
            
            if choice == "backtest":
                self._run_backtest_menu()
            elif choice == "live":
                self._run_live_trading_menu()
            elif choice == "strategies":
                self._show_strategies_menu()
            elif choice == "exchanges":
                self._manage_exchanges()
            elif choice == "reports":
                self._show_reports()
            elif choice == "settings":
                self._show_settings()
            elif choice == "exit":
                console.print("\nExiting. Goodbye.")
                break
    
    def _show_banner(self) -> None:
        """Display welcome banner."""
        banner = """
crypto-trading-bot v1.0.0
-------------------------
Backtest and trade cryptocurrency strategies
Type 'help' in any menu for more information
"""
        console.print(banner, style="bold")
    
    def _show_main_menu(self) -> str:
        """Display main menu and get user choice."""
        console.print("\n[bold]MAIN MENU[/]")
        choices = [
            {"name": "[1] Backtest      - Test strategies on historical data", "value": "backtest"},
            {"name": "[2] Live Trading  - Run strategies in real-time", "value": "live"},
            {"name": "[3] Strategies    - View and configure strategies", "value": "strategies"},
            {"name": "[4] Exchanges     - Manage exchange connections", "value": "exchanges"},
            {"name": "[5] Reports       - View previous backtest reports", "value": "reports"},
            {"name": "[6] Settings      - Configure bot settings", "value": "settings"},
            {"name": "[q] Exit", "value": "exit"}
        ]
        
        return questionary.select(
            "Select option:",
            choices=choices,
            style=self._get_style()
        ).ask()
    
    def _run_setup_wizard(self) -> None:
        """Run first-time setup wizard."""
        console.print("\n[bold yellow]Welcome! Let's set up your trading bot.[/]\n")
        
        # Ask about exchanges
        if questionary.confirm("Would you like to configure an exchange now?").ask():
            self._add_exchange()
        
        # Save config
        self.config.save()
        console.print("\n[bold green]Setup complete! You can always change settings later.[/]\n")
    
    def _run_backtest_menu(self) -> None:
        """Run backtesting workflow."""
        console.print("\n[bold cyan]═══ BACKTESTING ═══[/]\n")
        
        # 1. Select strategy
        strategies = self.strategy_registry.list_strategies()
        if not strategies:
            console.print("[red]No strategies available![/]")
            return
        
        strategy_choices = [
            {"name": f"{s['name']} - {s['description']}", "value": s['name']}
            for s in strategies
        ]
        
        strategy_name = questionary.select(
            "Select a strategy:",
            choices=strategy_choices,
            style=self._get_style()
        ).ask()
        
        if not strategy_name:
            return
        
        # Get strategy instance
        strategy = self.strategy_registry.get_instance(strategy_name)
        
        # 2. Configure strategy parameters
        if questionary.confirm(f"Configure {strategy_name} parameters? (default values otherwise)").ask():
            params = self._configure_strategy_params(strategy)
            strategy.set_params(**params)
        
        # 3. Select exchange
        exchange_name = questionary.select(
            "Select exchange for data:",
            choices=SUPPORTED_EXCHANGES,
            style=self._get_style()
        ).ask()
        
        if not exchange_name:
            return
        
        # Connect to exchange
        with console.status(f"Connecting to {exchange_name}..."):
            try:
                self.exchange_manager.connect(exchange_name)
            except Exception as e:
                console.print(f"[red]Error connecting: {e}[/]")
                return
        
        # 4. Select trading pair
        symbol = questionary.text(
            "Enter trading pair (e.g., BTC/USDT):",
            default="BTC/USDT"
        ).ask()
        
        if not symbol:
            return
        
        # 5. Select timeframe
        timeframe = questionary.select(
            "Select timeframe:",
            choices=['1m', '5m', '15m', '1h', '4h', '1d', '1w'],
            default='1h',
            style=self._get_style()
        ).ask()
        
        if not timeframe:
            return
        
        # 6. Select period
        period_choices = [
            {"name": "Last 30 days", "value": 30},
            {"name": "Last 90 days", "value": 90},
            {"name": "Last 180 days", "value": 180},
            {"name": "Last 365 days", "value": 365},
            {"name": "Custom", "value": "custom"}
        ]
        
        period = questionary.select(
            "Select data period:",
            choices=period_choices,
            style=self._get_style()
        ).ask()
        
        if period == "custom":
            days = int(questionary.text("Enter number of days:", default="365").ask())
        else:
            days = period
        
        # 7. Backtest settings
        initial_capital = float(questionary.text(
            "Initial capital ($):",
            default=str(self.config.get("backtesting.default_capital", 10000))
        ).ask())
        
        fee_percent = float(questionary.text(
            "Fee percentage:",
            default=str(self.config.get("backtesting.fee_percent", 0.1))
        ).ask())
        
        # 8. Download data
        console.print(f"\n[cyan]Downloading {symbol} data from {exchange_name}...[/]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("Downloading...", total=100)
            
            def update_progress(pct, fetched, total):
                progress.update(task, completed=pct, 
                               description=f"Downloaded {fetched}/{total} candles")
            
            data, msg = self.data_manager.download_for_backtest(
                exchange_name, symbol, timeframe, days, update_progress
            )
        
        if data.empty:
            console.print(f"[red]{msg}[/]")
            return
        
        console.print(f"[green]{msg}[/]\n")
        
        # 9. Run backtest
        console.print("[cyan]Running backtest...[/]")
        
        engine = BacktestEngine(
            initial_capital=initial_capital,
            fee_percent=fee_percent,
            slippage_percent=self.config.get("backtesting.slippage_percent", 0.05)
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Processing...", total=len(data))
            
            def progress_callback(current, total):
                progress.update(task, completed=current, description=f"Candle {current}/{total}")
            
            result = engine.run(strategy, data, symbol, timeframe, progress_callback)
        
        # 10. Calculate metrics
        calculator = MetricsCalculator()
        metrics = calculator.calculate(result)
        
        # 11. Display results
        display_backtest_results(result, metrics, console)
        
        # 12. Generate report
        if questionary.confirm("Generate HTML report?", default=True).ask():
            generator = ReportGenerator()
            report_path = generator.generate(result, metrics)
            console.print(f"\n[green]Report saved to: {report_path}[/]")
            
            if questionary.confirm("Open in browser?", default=True).ask():
                webbrowser.open(f"file://{report_path}")
        
        input("\nPress Enter to continue...")
    
    def _run_live_trading_menu(self) -> None:
        """Run live trading workflow."""
        console.print("\n[bold cyan]═══ LIVE TRADING ═══[/]\n")
        
        # Warning message
        console.print(Panel(
            "[bold yellow]WARNING[/]\n\n"
            "Live trading involves real money and significant risk.\n"
            "Start with PAPER mode to test your strategy first.\n"
            "Never trade with money you cannot afford to lose.",
            title="Risk Warning",
            border_style="yellow"
        ))
        
        if not questionary.confirm("Do you understand the risks and want to continue?").ask():
            return
        
        # 1. Select trading mode
        mode_choices = [
            {"name": "[p] Paper Trading  - Simulate with virtual balance (recommended)", "value": "paper"},
            {"name": "[d] Dry Run        - Only log signals, no execution", "value": "dry_run"},
            {"name": "[!] Live Trading   - Real orders (requires API keys)", "value": "live"},
        ]
        
        mode_str = questionary.select(
            "Select trading mode:",
            choices=mode_choices,
            style=self._get_style()
        ).ask()
        
        if not mode_str:
            return
        
        mode = {
            "paper": TradingMode.PAPER,
            "dry_run": TradingMode.DRY_RUN,
            "live": TradingMode.LIVE
        }[mode_str]
        
        # 2. Select strategy
        strategies = self.strategy_registry.list_strategies()
        if not strategies:
            console.print("[red]No strategies available![/]")
            return
        
        strategy_choices = [
            {"name": f"{s['name']} - {s['description']}", "value": s['name']}
            for s in strategies
        ]
        
        strategy_name = questionary.select(
            "Select a strategy:",
            choices=strategy_choices,
            style=self._get_style()
        ).ask()
        
        if not strategy_name:
            return
        
        strategy = self.strategy_registry.get_instance(strategy_name)
        
        # 3. Configure strategy parameters
        if questionary.confirm(f"Configure {strategy_name} parameters?", default=False).ask():
            params = self._configure_strategy_params(strategy)
            strategy.set_params(**params)
        
        # 4. Select exchange
        if mode == TradingMode.LIVE:
            # For live mode, only show configured exchanges with API keys
            configured = [ex['name'] for ex in self.config.get_exchanges() if ex.get('api_key')]
            if not configured:
                console.print("[red]No exchanges configured with API keys![/]")
                console.print("Please add an exchange with API keys first.")
                return
            exchange_choices = configured
        else:
            exchange_choices = SUPPORTED_EXCHANGES
        
        exchange_name = questionary.select(
            "Select exchange:",
            choices=exchange_choices,
            style=self._get_style()
        ).ask()
        
        if not exchange_name:
            return
        
        # 5. Get exchange config
        exchange_config = None
        for ex in self.config.get_exchanges():
            if ex['name'] == exchange_name:
                exchange_config = ex
                break
        
        # Connect to exchange
        with console.status(f"Connecting to {exchange_name}..."):
            try:
                if exchange_config and exchange_config.get('api_key'):
                    self.exchange_manager.connect(
                        exchange_name,
                        exchange_config['api_key'],
                        exchange_config['api_secret'],
                        exchange_config.get('sandbox', False)
                    )
                else:
                    self.exchange_manager.connect(exchange_name)
            except Exception as e:
                console.print(f"[red]Error connecting: {e}[/]")
                return
        
        # 6. Select trading pair
        symbol = questionary.text(
            "Enter trading pair (e.g., BTC/USDT):",
            default="BTC/USDT"
        ).ask()
        
        if not symbol:
            return
        
        # 7. Select timeframe
        timeframe = questionary.select(
            "Select timeframe:",
            choices=['1m', '5m', '15m', '1h', '4h'],
            default='1h',
            style=self._get_style()
        ).ask()
        
        if not timeframe:
            return
        
        # 8. Position size
        position_size = float(questionary.text(
            "Position size (% of balance, e.g., 10 for 10%):",
            default="10"
        ).ask()) / 100
        
        # 9. Paper trading balance
        initial_balance = 10000.0
        if mode == TradingMode.PAPER:
            initial_balance = float(questionary.text(
                "Initial paper balance ($):",
                default="10000"
            ).ask())
        
        # 10. Check interval
        check_interval = int(questionary.text(
            "Check interval (seconds):",
            default="60"
        ).ask())
        
        # Create engine
        engine = LiveTradingEngine(self.config, self.exchange_manager, mode)
        
        if mode == TradingMode.PAPER:
            _, quote = symbol.split('/')
            engine.set_paper_balance(quote, initial_balance)
        
        # Show trading info
        console.print("\n")
        console.print(Panel(
            f"[bold]Strategy:[/] {strategy.name}\n"
            f"[bold]Exchange:[/] {exchange_name}\n"
            f"[bold]Symbol:[/] {symbol}\n"
            f"[bold]Timeframe:[/] {timeframe}\n"
            f"[bold]Mode:[/] {mode.value.upper()}\n"
            f"[bold]Position Size:[/] {position_size*100}%\n"
            f"[bold]Check Interval:[/] {check_interval}s",
            title="Trading Configuration",
            border_style="green"
        ))
        
        if not questionary.confirm("\nStart trading?", default=True).ask():
            return
        
        console.print("\n[bold green]Starting live trading...[/]")
        console.print("[dim]Press Ctrl+C to stop[/]\n")
        
        # Run trading loop
        try:
            asyncio.run(engine.run_strategy(
                strategy=strategy,
                exchange_id=exchange_name,
                symbol=symbol,
                timeframe=timeframe,
                position_size=position_size,
                check_interval=check_interval
            ))
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping trading...[/]")
            engine.stop()
        
        # Show summary
        summary = engine.get_performance_summary()
        
        console.print("\n")
        console.print(Panel(
            f"[bold]Total Trades:[/] {summary.get('total_trades', 0)}\n"
            f"[bold]Total P&L:[/] ${summary.get('total_pnl', 0):+.2f}\n"
            f"[bold]Win Rate:[/] {summary.get('win_rate', 0):.1f}%\n"
            f"[bold]Open Positions:[/] {summary.get('open_positions', 0)}",
            title="Trading Summary",
            border_style="cyan"
        ))
        
        input("\nPress Enter to continue...")
    
    def _configure_strategy_params(self, strategy) -> dict:
        """Interactive parameter configuration."""
        params = {}
        defaults = strategy.params
        
        for key, value in defaults.items():
            if isinstance(value, bool):
                params[key] = questionary.confirm(
                    f"{key}:",
                    default=value
                ).ask()
            elif isinstance(value, int):
                params[key] = int(questionary.text(
                    f"{key}:",
                    default=str(value)
                ).ask())
            elif isinstance(value, float):
                params[key] = float(questionary.text(
                    f"{key}:",
                    default=str(value)
                ).ask())
            else:
                params[key] = questionary.text(
                    f"{key}:",
                    default=str(value)
                ).ask()
        
        return params
    
    def _show_strategies_menu(self) -> None:
        """Display strategies information."""
        console.print("\n[bold cyan]═══ AVAILABLE STRATEGIES ═══[/]\n")
        
        strategies = self.strategy_registry.list_strategies()
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Version", justify="right")
        
        for s in strategies:
            table.add_row(s['name'], s['description'], s['version'])
        
        console.print(table)
        
        # Show details
        if questionary.confirm("\nView strategy details?").ask():
            strategy_name = questionary.select(
                "Select strategy:",
                choices=[s['name'] for s in strategies]
            ).ask()
            
            strategy = self.strategy_registry.get_instance(strategy_name)
            
            console.print(f"\n[bold]{strategy.name}[/]")
            console.print(f"Description: {strategy.description}")
            console.print(f"Version: {strategy.version}")
            console.print("\n[bold]Default Parameters:[/]")
            
            for key, value in strategy.params.items():
                console.print(f"  • {key}: {value}")
        
        input("\nPress Enter to continue...")
    
    def _manage_exchanges(self) -> None:
        """Manage exchange configurations."""
        console.print("\n[bold cyan]═══ EXCHANGE MANAGEMENT ═══[/]\n")
        
        while True:
            choices = [
                {"name": "[a] Add exchange", "value": "add"},
                {"name": "[l] List configured exchanges", "value": "list"},
                {"name": "[r] Remove exchange", "value": "remove"},
                {"name": "[b] Back to main menu", "value": "back"}
            ]
            
            choice = questionary.select(
                "Select action:",
                choices=choices,
                style=self._get_style()
            ).ask()
            
            if choice == "add":
                self._add_exchange()
            elif choice == "list":
                self._list_exchanges()
            elif choice == "remove":
                self._remove_exchange()
            elif choice == "back":
                break
    
    def _add_exchange(self) -> None:
        """Add a new exchange configuration."""
        exchange = questionary.select(
            "Select exchange:",
            choices=SUPPORTED_EXCHANGES,
            style=self._get_style()
        ).ask()
        
        if not exchange:
            return
        
        api_key = questionary.text("API Key (leave empty for public data only):").ask()
        api_secret = questionary.password("API Secret:").ask() if api_key else ""
        sandbox = questionary.confirm("Use sandbox/testnet mode?", default=False).ask()
        
        self.config.add_exchange(exchange, api_key, api_secret, sandbox)
        self.config.save()
        
        console.print(f"[green]Exchange {exchange} configured successfully![/]")
    
    def _list_exchanges(self) -> None:
        """List configured exchanges."""
        exchanges = self.config.get_exchanges()
        
        if not exchanges:
            console.print("[yellow]No exchanges configured yet.[/]")
            return
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Exchange", style="cyan")
        table.add_column("API Key")
        table.add_column("Sandbox")
        
        for ex in exchanges:
            api_key = ex.get('api_key', '')
            masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "(not set)"
            sandbox = "Yes" if ex.get('sandbox') else "No"
            table.add_row(ex['name'], masked_key, sandbox)
        
        console.print(table)
    
    def _remove_exchange(self) -> None:
        """Remove an exchange configuration."""
        exchanges = self.config.get_exchanges()
        
        if not exchanges:
            console.print("[yellow]No exchanges to remove.[/]")
            return
        
        exchange = questionary.select(
            "Select exchange to remove:",
            choices=[ex['name'] for ex in exchanges]
        ).ask()
        
        if exchange and questionary.confirm(f"Remove {exchange}?").ask():
            self.config.remove_exchange(exchange)
            self.config.save()
            console.print(f"[green]Exchange {exchange} removed.[/]")
    
    def _show_reports(self) -> None:
        """Show available reports."""
        from pathlib import Path
        
        reports_dir = Path(__file__).parent.parent.parent / "reports"
        
        if not reports_dir.exists():
            console.print("[yellow]No reports found.[/]")
            return
        
        reports = list(reports_dir.glob("*.html"))
        
        if not reports:
            console.print("[yellow]No reports found.[/]")
            return
        
        console.print("\n[bold cyan]═══ BACKTEST REPORTS ═══[/]\n")
        
        report_choices = [
            {"name": f.name, "value": str(f)}
            for f in sorted(reports, key=lambda x: x.stat().st_mtime, reverse=True)[:10]
        ]
        report_choices.append({"name": "Back", "value": None})
        
        report_path = questionary.select(
            "Select report to open:",
            choices=report_choices
        ).ask()
        
        if report_path:
            webbrowser.open(f"file://{report_path}")
    
    def _show_settings(self) -> None:
        """Show and modify settings."""
        console.print("\n[bold cyan]═══ SETTINGS ═══[/]\n")
        
        settings = [
            ("Log Level", "log_level", ["DEBUG", "INFO", "WARNING", "ERROR"]),
            ("Default Capital", "backtesting.default_capital", None),
            ("Fee Percent", "backtesting.fee_percent", None),
            ("Slippage Percent", "backtesting.slippage_percent", None),
        ]
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Setting")
        table.add_column("Current Value")
        
        for name, key, _ in settings:
            value = self.config.get(key)
            table.add_row(name, str(value))
        
        console.print(table)
        
        if questionary.confirm("\nModify settings?").ask():
            for name, key, options in settings:
                current = self.config.get(key)
                
                if options:
                    new_value = questionary.select(
                        f"{name}:",
                        choices=options,
                        default=current
                    ).ask()
                else:
                    new_value = questionary.text(
                        f"{name}:",
                        default=str(current)
                    ).ask()
                    
                    # Convert to appropriate type
                    if isinstance(current, float):
                        new_value = float(new_value)
                    elif isinstance(current, int):
                        new_value = int(new_value)
                
                self.config.set(key, new_value)
            
            self.config.save()
            console.print("[green]Settings saved![/]")
    
    def _get_style(self):
        """Get questionary style."""
        return questionary.Style([
            ('qmark', 'fg:#673ab7 bold'),
            ('question', 'bold'),
            ('answer', 'fg:#f44336 bold'),
            ('pointer', 'fg:#673ab7 bold'),
            ('highlighted', 'fg:#673ab7 bold'),
            ('selected', 'fg:#cc5454'),
        ])
