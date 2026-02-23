# Configuration Reference

Complete reference for every setting in `config/config.yaml`.

---

## Table of Contents

1. [File Location](#file-location)
2. [General Settings](#general-settings)
3. [Exchange Configuration](#exchange-configuration)
4. [Backtesting Settings](#backtesting-settings)
5. [Strategy Parameters](#strategy-parameters)
6. [Strategy Filters](#strategy-filters)
7. [Notifications](#notifications)
8. [API Server](#api-server)
9. [Database](#database)
10. [ML Filter](#ml-filter)
11. [Sentiment Analysis](#sentiment-analysis)
12. [Optimizer](#optimizer)
13. [Supervisor](#supervisor)
14. [Environment Variables](#environment-variables)

---

## File Location

```
config/config.yaml          # Active config (create from example)
config/config.example.yaml  # Template with defaults and comments
```

Create your config:

```bash
cp config/config.example.yaml config/config.yaml
```

The config file is YAML format. Values support dot-notation access in code (e.g., `backtesting.default_capital`).

---

## General Settings

```yaml
log_level: INFO   # DEBUG, INFO, WARNING, ERROR
```

| Setting     | Type   | Default | Description                     |
| ----------- | ------ | ------- | ------------------------------- |
| `log_level` | string | `INFO`  | Controls console log verbosity  |

---

## Exchange Configuration

```yaml
exchanges:
  binance:
    api_key: "your_api_key_here"
    api_secret: "your_api_secret_here"
    sandbox: false
```

| Field        | Type    | Required | Description                                   |
| ------------ | ------- | -------- | --------------------------------------------- |
| `api_key`    | string  | Yes      | Exchange API key                               |
| `api_secret` | string  | Yes      | Exchange API secret                            |
| `sandbox`    | boolean | No       | Use testnet/sandbox mode (default: `false`)    |

**Supported exchanges:** binance, kraken, coinbase, kucoin, bybit, okx, bitfinex, huobi, gate, mexc (and any exchange supported by ccxt).

Multiple exchanges can be configured:

```yaml
exchanges:
  binance:
    api_key: "..."
    api_secret: "..."
  kraken:
    api_key: "..."
    api_secret: "..."
```

**Security:** Never commit your `config.yaml` to git. The `.gitignore` already excludes it. For production, use environment variables instead.

---

## Backtesting Settings

```yaml
backtesting:
  default_capital: 10000       # Starting capital in quote currency (USDT)
  fee_percent: 0.1             # Trading fee as percentage (0.1 = 0.1%)
  slippage_percent: 0.05       # Simulated slippage percentage
  default_timeframe: "1h"      # Default candlestick timeframe
```

| Setting              | Type  | Default  | Description                        |
| -------------------- | ----- | -------- | ---------------------------------- |
| `default_capital`    | float | `10000`  | Starting capital for backtests     |
| `fee_percent`        | float | `0.1`    | Trading fee percentage             |
| `slippage_percent`   | float | `0.05`   | Simulated price slippage           |
| `default_timeframe`  | string| `1h`     | Default timeframe for data         |

---

## Strategy Parameters

Each built-in strategy has default parameters that can be overridden:

```yaml
strategies:
  ma_crossover:
    fast_period: 9
    slow_period: 21
  rsi:
    period: 14
    overbought: 70
    oversold: 30
  macd:
    fast_period: 12
    slow_period: 26
    signal_period: 9
  bollinger:
    period: 20
    std_dev: 2.0
```

Run a backtest to see the full parameter schema for each strategy.

---

## Strategy Filters

```yaml
strategy_filters:
  multi_timeframe:
    enabled: false
    confirmation_timeframes: ["4h", "1d"]
    require_all: false
    min_confirmations: 1

  regime_detection:
    enabled: false
    adx_threshold: 25
    allowed_regimes:
      - trending_bullish
      - trending_bearish
```

| Setting                      | Type    | Default | Description                                   |
| ---------------------------- | ------- | ------- | --------------------------------------------- |
| `multi_timeframe.enabled`    | boolean | `false` | Enable higher-timeframe trend confirmation     |
| `confirmation_timeframes`    | list    | `["4h", "1d"]` | Timeframes to check for confirmation   |
| `require_all`                | boolean | `false` | Require ALL timeframes to confirm              |
| `min_confirmations`          | int     | `1`     | Minimum confirming timeframes                  |
| `regime_detection.enabled`   | boolean | `false` | Enable market regime filtering                 |
| `adx_threshold`              | float   | `25`    | ADX value above which market is trending       |
| `allowed_regimes`            | list    | see above | Regimes in which trading is allowed          |

Available regimes: `trending_bullish`, `trending_bearish`, `ranging`, `high_volatility`, `low_volatility`.

---

## Notifications

### Telegram

```yaml
notifications:
  telegram:
    enabled: false
    bot_token: "123456:ABC-DEF"    # From @BotFather
    chat_id: "987654321"           # From @userinfobot
```

**Setup:** Message [@BotFather](https://t.me/BotFather) on Telegram, create a bot, copy the token. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID.

### Discord

```yaml
  discord:
    enabled: false
    webhook_url: "https://discord.com/api/webhooks/..."
```

**Setup:** In your Discord server, go to Channel Settings > Integrations > Webhooks > New Webhook. Copy the URL.

### Email (SMTP)

```yaml
  email:
    enabled: false
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "your_email@gmail.com"
    password: "your_app_password"
    from_address: "your_email@gmail.com"
    to_addresses:
      - "recipient@example.com"
    use_tls: true
```

**Gmail setup:** Enable 2FA on your Google account, then create an App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). Use that as the `password` value.

### WhatsApp (Twilio)

```yaml
  whatsapp:
    enabled: false
    twilio_account_sid: "ACxxxxxxxxxxxx"
    twilio_auth_token: "your_auth_token"
    from_number: "whatsapp:+14155238886"
    to_numbers:
      - "whatsapp:+1234567890"
```

**Setup:** Create a [Twilio account](https://www.twilio.com/), activate the WhatsApp Sandbox, and follow the instructions to connect your number.

### Alert Routing

```yaml
  routing:
    trades: ["telegram", "discord"]
    errors: ["telegram", "discord", "email", "whatsapp"]
    daily_summary: ["email", "discord"]
    backtest: ["telegram", "discord"]
```

Controls which channels receive which alert types. Only channels that are `enabled: true` will actually send.

---

## API Server

```yaml
api:
  host: "127.0.0.1"
  port: 8765
  auth_enabled: false
  api_key: ""
```

| Setting        | Type    | Default       | Description                              |
| -------------- | ------- | ------------- | ---------------------------------------- |
| `host`         | string  | `127.0.0.1`   | Bind address (`0.0.0.0` for all interfaces) |
| `port`         | int     | `8765`        | API port                                 |
| `auth_enabled` | boolean | `false`       | Require `X-API-Key` header               |
| `api_key`      | string  | `""`          | API key value (or use env var)           |

**Generate an API key:**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

The API key can also be set via the `TRADING_BOT_API_KEY` environment variable, which takes precedence over the config file.

---

## Database

```yaml
database:
  path: "data/trading.db"
```

SQLite database storing trade history, journal entries, and alert logs. The file is created automatically on first run.

---

## ML Filter

```yaml
ml_filter:
  enabled: false
  model_type: "gradient_boosting"    # "gradient_boosting", "random_forest", or "lstm"
  model_path: "data/models/"
  confidence_threshold: 0.55
  retrain_interval_hours: 168
```

| Setting                 | Type   | Default              | Description                        |
| ----------------------- | ------ | -------------------- | ---------------------------------- |
| `enabled`               | boolean| `false`              | Enable ML signal filtering         |
| `model_type`            | string | `gradient_boosting`  | ML model to use                    |
| `model_path`            | string | `data/models/`       | Directory for saved models         |
| `confidence_threshold`  | float  | `0.55`               | Minimum confidence to allow signal |
| `retrain_interval_hours`| int    | `168`                | Hours between automatic retraining |

Requires: `scikit-learn` for classical ML, `torch` for LSTM.

---

## Sentiment Analysis

```yaml
sentiment:
  enabled: false
  fear_greed_threshold: 25
  greed_threshold: 75
  news_api_key: ""
  news_sentiment_weight: 0.3
  contrarian: false
  cache_ttl_minutes: 30
```

| Setting                | Type    | Default | Description                             |
| ---------------------- | ------- | ------- | --------------------------------------- |
| `enabled`              | boolean | `false` | Enable sentiment filtering              |
| `fear_greed_threshold` | int     | `25`    | FNG below this blocks BUY signals       |
| `greed_threshold`      | int     | `75`    | FNG above this blocks SELL signals      |
| `news_api_key`         | string  | `""`    | CryptoCompare API key (optional)        |
| `news_sentiment_weight`| float   | `0.3`   | Weight of news vs FNG (0=FNG only)      |
| `contrarian`           | boolean | `false` | Invert logic (buy in fear, sell in greed) |
| `cache_ttl_minutes`    | int     | `30`    | Cache duration for API responses        |

---

## Optimizer

```yaml
optimizer:
  enabled: false
  metric: "sharpe_ratio"
  n_trials: 100
  retrain_every_bars: 168
```

| Setting             | Type   | Default        | Description                                |
| ------------------- | ------ | -------------- | ------------------------------------------ |
| `enabled`           | boolean| `false`        | Enable dynamic parameter optimization      |
| `metric`            | string | `sharpe_ratio` | Metric to maximize                         |
| `n_trials`          | int    | `100`          | Optuna trials per optimization run         |
| `retrain_every_bars`| int    | `168`          | Bars between re-optimization               |

Available metrics: `sharpe_ratio`, `total_return_pct`, `profit_factor`, `win_rate`, `sortino_ratio`.

---

## Supervisor

```yaml
supervisor:
  enabled: false
  max_restarts: 5
  restart_window: 300
  initial_delay: 1.0
  max_delay: 60.0
```

Auto-restarts the bot on crashes with exponential backoff.

---

## Environment Variables

These override config file values:

| Variable                  | Overrides              | Description                    |
| ------------------------- | ---------------------- | ------------------------------ |
| `TRADING_BOT_API_KEY`     | `api.api_key`          | API authentication key         |
| `LOG_LEVEL`               | `log_level`            | Logging verbosity              |
| `TZ`                      | —                      | Timezone (e.g., `US/Eastern`)  |

In Docker, set these in `docker-compose.yml` or pass with `docker run -e`.
