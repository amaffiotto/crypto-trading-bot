# Getting Started

Complete setup guide for the Crypto Trading Bot on macOS, Linux, and Windows.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [macOS Setup](#macos-setup)
3. [Ubuntu / Debian Linux Setup](#ubuntu--debian-linux-setup)
4. [Windows Setup](#windows-setup)
5. [First Run](#first-run)
6. [Project Structure Overview](#project-structure-overview)

---

## Prerequisites

The bot consists of two parts:

| Component      | Purpose                          | Requires             |
| -------------- | -------------------------------- | -------------------- |
| Python backend | API server, strategies, backtesting | Python 3.11+         |
| Electron GUI   | Desktop interface                | Node.js 18+, npm     |

**Hardware recommendations:**

- 2+ CPU cores
- 4 GB RAM minimum (8 GB recommended for ML features)
- 1 GB free disk space

---

## macOS Setup

### 1. Install Homebrew (if not installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. Install Python 3.11+

```bash
brew install python@3.13
```

Verify:

```bash
python3 --version
# Python 3.13.x
```

### 3. Install Node.js

```bash
brew install node
```

Verify:

```bash
node --version   # v18+ required
npm --version
```

### 4. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot
```

### 5. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

If you get a permission error, use:

```bash
pip3 install --user -r requirements.txt
```

Or use a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 6. Install Electron dependencies

```bash
cd electron
npm install
cd ..
```

### 7. Create your config file

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` with your exchange API keys and preferences.

### 8. Run

```bash
python3 start.py
```

---

## Ubuntu / Debian Linux Setup

### 1. Update system packages

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Python 3.11+

Ubuntu 22.04+ ships with Python 3.10+. For 3.11+:

```bash
sudo apt install -y python3 python3-pip python3-venv
```

If your distro has an older Python, use the deadsnakes PPA:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.13 python3.13-venv python3.13-dev
```

Verify:

```bash
python3 --version
```

### 3. Install Node.js 18+

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Verify:

```bash
node --version
npm --version
```

### 4. Install system dependencies

Some Python packages need C compilers:

```bash
sudo apt install -y build-essential libffi-dev libssl-dev
```

### 5. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd electron && npm install && cd ..
```

### 6. Configure and run

```bash
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml with your settings

python3 start.py
```

**Headless mode** (no GUI, API only):

```bash
python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 8765
```

---

## Windows Setup

### 1. Install Python 3.11+

Download from [python.org](https://www.python.org/downloads/). During installation:

- Check "Add Python to PATH"
- Check "Install pip"

Verify in Command Prompt or PowerShell:

```powershell
python --version
pip --version
```

### 2. Install Node.js

Download the LTS version from [nodejs.org](https://nodejs.org/). The installer adds `node` and `npm` to PATH automatically.

Verify:

```powershell
node --version
npm --version
```

### 3. Install Git (if not installed)

Download from [git-scm.com](https://git-scm.com/download/win).

### 4. Clone and install

```powershell
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

cd electron
npm install
cd ..
```

### 5. Configure and run

```powershell
copy config\config.example.yaml config\config.yaml
# Edit config\config.yaml with your editor

python start.py
```

Or use the provided batch file:

```powershell
start.bat
```

---

## First Run

1. **Start the bot** with `python3 start.py` (or `start.bat` on Windows, `start.sh` on Linux/macOS).
2. The **API server** starts on `http://127.0.0.1:8765`.
3. The **Electron GUI** opens automatically.
4. Go to **Settings** and configure your exchange API keys.
5. Try a **Backtest** first before doing any live/paper trading.

### Quick health check

Open a browser or run:

```bash
curl http://127.0.0.1:8765/api/health
```

You should see:

```json
{"status": "ok", "version": "1.0.0"}
```

---

## Project Structure Overview

```
crypto-trading-bot/
├── config/                  # Configuration files
│   ├── config.example.yaml  # Template (copy to config.yaml)
│   └── config.yaml          # Your settings (git-ignored)
├── data/                    # Cached OHLCV data + SQLite database
├── electron/                # Electron desktop GUI
│   ├── index.html           # Main UI
│   ├── main.js              # Electron main process
│   ├── scripts/             # Frontend JavaScript
│   └── styles/              # CSS
├── guides/                  # Documentation (you are here)
├── reports/                 # Generated backtest HTML reports
├── src/                     # Python backend
│   ├── api/                 # FastAPI REST server
│   ├── backtesting/         # Backtest engine, metrics, walk-forward, OOS
│   ├── cli/                 # Command-line interface
│   ├── core/                # Config, exchange manager, data manager, database
│   ├── notifications/       # Telegram, Discord, Email, WhatsApp, manager
│   ├── strategies/          # Trading strategies + filters + optimizer
│   ├── trading/             # Live/paper trading engine, paper validator
│   └── utils/               # Logger, supervisor
├── tests/                   # Pytest test suite
├── Dockerfile               # Docker container definition
├── docker-compose.yml       # Docker Compose orchestration
├── requirements.txt         # Python dependencies
├── start.py                 # One-click launcher
├── start.sh                 # Linux/macOS launcher script
└── start.bat                # Windows launcher script
```

---

## Next Steps

- [Configuration Reference](./02-CONFIGURATION.md) — every setting explained
- [Docker Deployment](./03-DOCKER-DEPLOYMENT.md) — containerized deployment
- [AWS Deployment](./04-AWS-DEPLOYMENT.md) — deploy on Amazon Web Services
- [GCP Deployment](./05-GCP-DEPLOYMENT.md) — deploy on Google Cloud
- [VPS Deployment](./06-VPS-DEPLOYMENT.md) — deploy on any VPS provider
- [Strategy Development](./07-STRATEGY-GUIDE.md) — build and test your own strategies
