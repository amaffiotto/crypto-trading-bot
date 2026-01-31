"""HTML report generator with Plotly charts."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd

from src.backtesting.engine import BacktestResult
from src.backtesting.metrics import MetricsCalculator, PerformanceMetrics
from src.utils.logger import get_logger

logger = get_logger()


class ReportGenerator:
    """Generates interactive HTML reports for backtest results."""
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize report generator.
        
        Args:
            output_dir: Directory for output files. Defaults to reports/
        """
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent.parent.parent / "reports"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, result: BacktestResult, 
                 metrics: Optional[PerformanceMetrics] = None,
                 filename: Optional[str] = None) -> str:
        """
        Generate HTML report.
        
        Args:
            result: BacktestResult from backtesting
            metrics: Pre-calculated metrics (or will be calculated)
            filename: Output filename (auto-generated if not provided)
            
        Returns:
            Path to generated HTML file
        """
        # Calculate metrics if not provided
        if metrics is None:
            calculator = MetricsCalculator()
            metrics = calculator.calculate(result)
        
        # Generate filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_symbol = result.symbol.replace("/", "_")
            filename = f"backtest_{safe_symbol}_{result.strategy_name}_{timestamp}.html"
        
        output_path = self.output_dir / filename
        
        # Generate HTML content
        html = self._generate_html(result, metrics)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Report generated: {output_path}")
        return str(output_path)
    
    def _generate_html(self, result: BacktestResult, 
                       metrics: PerformanceMetrics) -> str:
        """Generate the full HTML document."""
        
        # Generate chart data
        equity_chart = self._generate_equity_chart_data(result)
        drawdown_chart = self._generate_drawdown_chart_data(result)
        trade_dist_chart = self._generate_trade_distribution_data(result)
        
        # Generate trades table
        trades_table = self._generate_trades_table(result)
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report - {result.strategy_name}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 1px solid #333;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            color: #fff;
        }}
        .subtitle {{
            color: #888;
            font-size: 1.1em;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .metric-card {{
            background: #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            border: 1px solid #333;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .metric-label {{
            color: #888;
            font-size: 0.9em;
        }}
        .positive {{ color: #00c853; }}
        .negative {{ color: #ff5252; }}
        .neutral {{ color: #ffd600; }}
        .chart-container {{
            background: #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
            border: 1px solid #333;
        }}
        .chart-title {{
            font-size: 1.3em;
            margin-bottom: 15px;
            color: #fff;
        }}
        .trades-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        .trades-table th, .trades-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #333;
        }}
        .trades-table th {{
            background: #252525;
            color: #fff;
            font-weight: 600;
        }}
        .trades-table tr:hover {{
            background: #252525;
        }}
        .table-container {{
            max-height: 400px;
            overflow-y: auto;
        }}
        .info-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 30px;
            padding: 20px;
            background: #1a1a1a;
            border-radius: 12px;
            border: 1px solid #333;
        }}
        .info-item {{
            flex: 1;
            min-width: 150px;
        }}
        .info-label {{
            color: #888;
            font-size: 0.85em;
        }}
        .info-value {{
            font-size: 1.1em;
            color: #fff;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{result.strategy_name}</h1>
            <p class="subtitle">{result.symbol} | {result.timeframe} | {result.start_date.strftime("%Y-%m-%d")} to {result.end_date.strftime("%Y-%m-%d")}</p>
        </header>
        
        <div class="info-row">
            <div class="info-item">
                <div class="info-label">Initial Capital</div>
                <div class="info-value">${result.initial_capital:,.2f}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Final Capital</div>
                <div class="info-value">${result.final_capital:,.2f}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Total Trades</div>
                <div class="info-value">{metrics.total_trades}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Strategy Parameters</div>
                <div class="info-value" style="font-size: 0.9em;">{self._format_params(result.parameters)}</div>
            </div>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value {self._get_color_class(metrics.total_return_pct)}">{metrics.total_return_pct:+.2f}%</div>
                <div class="metric-label">Total Return</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {self._get_color_class(metrics.sharpe_ratio)}">{metrics.sharpe_ratio:.2f}</div>
                <div class="metric-label">Sharpe Ratio</div>
            </div>
            <div class="metric-card">
                <div class="metric-value negative">-{metrics.max_drawdown:.2f}%</div>
                <div class="metric-label">Max Drawdown</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.win_rate:.1f}%</div>
                <div class="metric-label">Win Rate</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {self._get_color_class(metrics.profit_factor - 1)}">{metrics.profit_factor:.2f}</div>
                <div class="metric-label">Profit Factor</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {self._get_color_class(metrics.avg_trade_pnl)}">${metrics.avg_trade_pnl:+.2f}</div>
                <div class="metric-label">Avg Trade</div>
            </div>
            <div class="metric-card">
                <div class="metric-value positive">${metrics.avg_winning_trade:.2f}</div>
                <div class="metric-label">Avg Winner</div>
            </div>
            <div class="metric-card">
                <div class="metric-value negative">${metrics.avg_losing_trade:.2f}</div>
                <div class="metric-label">Avg Loser</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h3 class="chart-title">Equity Curve</h3>
            <div id="equity-chart"></div>
        </div>
        
        <div class="chart-container">
            <h3 class="chart-title">Drawdown</h3>
            <div id="drawdown-chart"></div>
        </div>
        
        <div class="chart-container">
            <h3 class="chart-title">Trade P&L Distribution</h3>
            <div id="distribution-chart"></div>
        </div>
        
        <div class="chart-container">
            <h3 class="chart-title">Trade History</h3>
            <div class="table-container">
                {trades_table}
            </div>
        </div>
    </div>
    
    <script>
        // Chart configuration
        const chartConfig = {{
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            displaylogo: false
        }};
        
        const darkLayout = {{
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: {{ color: '#e0e0e0' }},
            xaxis: {{
                gridcolor: '#333',
                zerolinecolor: '#333'
            }},
            yaxis: {{
                gridcolor: '#333',
                zerolinecolor: '#333'
            }},
            margin: {{ l: 50, r: 30, t: 30, b: 50 }}
        }};
        
        // Equity Chart
        {equity_chart}
        
        // Drawdown Chart
        {drawdown_chart}
        
        // Distribution Chart
        {trade_dist_chart}
    </script>
</body>
</html>'''
        
        return html
    
    def _generate_equity_chart_data(self, result: BacktestResult) -> str:
        """Generate JavaScript for equity curve chart."""
        if result.equity_curve.empty:
            return "// No equity data"
        
        df = result.equity_curve
        timestamps = df["timestamp"].astype(str).tolist()
        equity = df["equity"].tolist()
        
        return f'''
        Plotly.newPlot('equity-chart', [{{
            x: {json.dumps(timestamps)},
            y: {json.dumps(equity)},
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            fillcolor: 'rgba(0, 200, 83, 0.1)',
            line: {{ color: '#00c853', width: 2 }},
            name: 'Equity'
        }}], {{
            ...darkLayout,
            yaxis: {{
                ...darkLayout.yaxis,
                title: 'Equity ($)',
                tickformat: '$,.0f'
            }},
            xaxis: {{
                ...darkLayout.xaxis,
                title: 'Date'
            }}
        }}, chartConfig);
        '''
    
    def _generate_drawdown_chart_data(self, result: BacktestResult) -> str:
        """Generate JavaScript for drawdown chart."""
        if result.equity_curve.empty:
            return "// No drawdown data"
        
        df = result.equity_curve
        equity = df["equity"]
        running_max = equity.expanding().max()
        drawdown = ((equity - running_max) / running_max * 100).tolist()
        timestamps = df["timestamp"].astype(str).tolist()
        
        return f'''
        Plotly.newPlot('drawdown-chart', [{{
            x: {json.dumps(timestamps)},
            y: {json.dumps(drawdown)},
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            fillcolor: 'rgba(255, 82, 82, 0.2)',
            line: {{ color: '#ff5252', width: 2 }},
            name: 'Drawdown'
        }}], {{
            ...darkLayout,
            yaxis: {{
                ...darkLayout.yaxis,
                title: 'Drawdown (%)',
                tickformat: '.1f'
            }},
            xaxis: {{
                ...darkLayout.xaxis,
                title: 'Date'
            }}
        }}, chartConfig);
        '''
    
    def _generate_trade_distribution_data(self, result: BacktestResult) -> str:
        """Generate JavaScript for trade distribution histogram."""
        if not result.trades:
            return "// No trades"
        
        pnls = [t.pnl for t in result.trades]
        
        return f'''
        Plotly.newPlot('distribution-chart', [{{
            x: {json.dumps(pnls)},
            type: 'histogram',
            marker: {{
                color: {json.dumps(pnls)}.map(p => p >= 0 ? '#00c853' : '#ff5252')
            }},
            nbinsx: 30,
            name: 'Trade P&L'
        }}], {{
            ...darkLayout,
            xaxis: {{
                ...darkLayout.xaxis,
                title: 'P&L ($)'
            }},
            yaxis: {{
                ...darkLayout.yaxis,
                title: 'Frequency'
            }},
            bargap: 0.05
        }}, chartConfig);
        '''
    
    def _generate_trades_table(self, result: BacktestResult) -> str:
        """Generate HTML table for trades."""
        if not result.trades:
            return "<p>No trades executed</p>"
        
        rows = []
        for i, trade in enumerate(result.trades, 1):
            pnl_class = "positive" if trade.pnl > 0 else "negative"
            rows.append(f'''
            <tr>
                <td>{i}</td>
                <td>{trade.entry_time.strftime("%Y-%m-%d %H:%M")}</td>
                <td>{trade.exit_time.strftime("%Y-%m-%d %H:%M")}</td>
                <td>{trade.side.upper()}</td>
                <td>${trade.entry_price:,.2f}</td>
                <td>${trade.exit_price:,.2f}</td>
                <td>{trade.quantity:.6f}</td>
                <td class="{pnl_class}">${trade.pnl:+,.2f}</td>
                <td class="{pnl_class}">{trade.pnl_percent:+.2f}%</td>
            </tr>
            ''')
        
        return f'''
        <table class="trades-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Entry Time</th>
                    <th>Exit Time</th>
                    <th>Side</th>
                    <th>Entry Price</th>
                    <th>Exit Price</th>
                    <th>Quantity</th>
                    <th>P&L</th>
                    <th>P&L %</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        '''
    
    def _format_params(self, params: dict) -> str:
        """Format strategy parameters for display."""
        return ", ".join(f"{k}={v}" for k, v in params.items())
    
    def _get_color_class(self, value: float) -> str:
        """Get CSS class based on value sign."""
        if value > 0:
            return "positive"
        elif value < 0:
            return "negative"
        return "neutral"
