# 🪙📈 Crypto Trading Bot

A Python + Electron project I'm building with the help of AI to backtest and run algorithmic trading strategies on cryptocurrencies.

![Status](https://img.shields.io/badge/Status-Work%20In%20Progress-yellow)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Electron](https://img.shields.io/badge/GUI-Electron-47848F)

## What is it?

It's a trading bot with a modern GUI that:
- **Downloads historical market data** from major exchanges (Binance, Kraken, etc.)
- **Backtests trading strategies** to see if they would have made money
- **Runs live/paper trading** with real-time signals
- **Generates visual reports** with equity curves, drawdowns, and trade analysis

Currently includes **18 built-in strategies** ranging from simple (MA Crossover, RSI) to advanced (Regime Filter, Multi-Indicator Confirmation).

## Results (Screenshots)

### Backtest Report

The bot generates interactive HTML reports showing equity curves, drawdowns, and trade analysis.

![Backtest Results](images/backtest_report.png)
*Equity curve, price chart with buy/sell signals, and drawdown analysis*

### Trade Distribution

![Trade Distribution](images/trade_distribution.png)
*PnL distribution histogram and performance metrics*

*(Note: These are just simulations, not real money)*

### GUI Preview

Modern dark-themed interface built with Electron:

![GUI Preview](images/gui_preview.png)
*Backtest configuration and results display*

## How I built it

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.11 |
| **GUI** | Electron + Vanilla JS |
| **API Server** | FastAPI |
| **Exchange Data** | ccxt library |
| **Technical Analysis** | ta library |
| **Charting** | Plotly |
| **AI Assistance** | Cursor |

## How to try it

### Prerequisites

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **Git** - [Download](https://git-scm.com/)

---

### 🍎 macOS

```bash
# Clone the repo
git clone https://github.com/amaffiotto/crypto-trading-bot.git
cd crypto-trading-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
cd electron && npm install && cd ..

# Run the bot
python3 start.py
```

Or use the shell script:
```bash
chmod +x start.sh
./start.sh
```

---

### 🐧 Linux (Ubuntu/Debian)

```bash
# Install prerequisites (if needed)
sudo apt update
sudo apt install python3 python3-venv python3-pip nodejs npm git

# Clone the repo
git clone https://github.com/amaffiotto/crypto-trading-bot.git
cd crypto-trading-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
cd electron && npm install && cd ..

# Run the bot
python3 start.py
```

Or use the shell script:
```bash
chmod +x start.sh
./start.sh
```

---

### 🪟 Windows

**Option 1: Command Prompt / PowerShell**

```powershell
# Clone the repo
git clone https://github.com/amaffiotto/crypto-trading-bot.git
cd crypto-trading-bot

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
cd electron
npm install
cd ..

# Run the bot
python start.py
```

**Option 2: Double-click to run**

After installing dependencies, simply double-click `start.bat` to launch the bot.

---

### CLI Mode (All Platforms)

If you prefer a terminal-based interface:

```bash
# macOS/Linux
python3 -m src.main

# Windows
python -m src.main
```

Then select option 1 (CLI) when prompted.

## Project Structure

```
crypto-trading-bot/
├── src/
│   ├── strategies/      # 18 built-in trading strategies
│   ├── backtesting/     # Backtest engine & reports
│   ├── trading/         # Live trading engine
│   ├── core/            # Exchange & data management
│   └── api/             # FastAPI server for GUI
├── electron/            # Electron GUI
├── config/              # Configuration files
└── reports/             # Generated backtest reports
```

## Available Strategies

| Category | Strategies |
|----------|------------|
| **Simple (Recommended)** | Simple Trend ⭐, Momentum RSI ⭐ |
| **Basic** | MA Crossover, RSI, MACD, Bollinger Bands |
| **Intermediate** | Trend Momentum, Mean Reversion, SuperTrend, Grid Trading, DCA, Triple EMA, Breakout |
| **Advanced** | ADX BB Trend, Donchian Breakout, Regime Filter, Multi Confirm, Volatility Breakout |

## Important Notes

⚠️ **This is for educational purposes only.** Past performance does not guarantee future results.

💡 **Tip:** Use **1 Day timeframe** with **300+ days** of data for best backtest results. Lower timeframes (1h, 4h) tend to generate too many false signals.

## Why?

I'm working on this project because I really believe that AI can give the power to people who don't know how to code at a high level to build something meaningful.

This is a continuation of my journey with algorithmic trading, applying what I learned from the gold trading bot to the crypto markets.

---

*Created by Andrea Maffiotto for educational purposes.*
