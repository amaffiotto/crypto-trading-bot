# Docker Deployment Guide

Run the Crypto Trading Bot in Docker for consistent, isolated deployments — locally or on any server.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Building the Image](#building-the-image)
4. [Docker Compose](#docker-compose)
5. [Configuration](#configuration)
6. [Persistent Data](#persistent-data)
7. [Networking and Security](#networking-and-security)
8. [Production Hardening](#production-hardening)
9. [Monitoring and Logs](#monitoring-and-logs)
10. [Updating](#updating)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool            | Minimum Version | Install                                |
| --------------- | --------------- | -------------------------------------- |
| Docker Engine   | 20.10+          | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| Docker Compose  | 2.0+            | Included with Docker Desktop           |

**Verify installation:**

```bash
docker --version
docker compose version
```

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot

# 2. Create your config
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml with your exchange keys

# 3. Generate an API key
export TRADING_BOT_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Your API key: $TRADING_BOT_API_KEY"

# 4. Start
docker compose up -d

# 5. Check health
curl http://localhost:8765/api/health
```

The API server is now running on port 8765.

---

## Building the Image

### Standard build

```bash
docker build -t crypto-trading-bot:latest .
```

### Build with specific Python version

```bash
docker build --build-arg PYTHON_VERSION=3.13 -t crypto-trading-bot:latest .
```

### Multi-platform build (for ARM servers like AWS Graviton)

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t crypto-trading-bot:latest .
```

### Build details

The Dockerfile uses a multi-stage build:

- **Stage 1 (builder):** Installs build tools and Python dependencies into a virtual environment
- **Stage 2 (runtime):** Copies only the venv and application code, runs as non-root user

Final image size is approximately 400-500 MB.

---

## Docker Compose

The provided `docker-compose.yml` handles everything:

```bash
# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose build && docker compose up -d
```

### Compose file breakdown

```yaml
services:
  trading-bot:
    build: .
    container_name: crypto-trading-bot
    restart: unless-stopped          # Auto-restart on crash
    ports:
      - "8765:8765"                  # API port
    volumes:
      - ./data:/app/data             # SQLite DB + OHLCV cache
      - ./reports:/app/reports       # Backtest reports
      - ./config:/app/config:ro      # Config (read-only)
    environment:
      - TRADING_BOT_API_KEY=${TRADING_BOT_API_KEY:-}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TZ=${TZ:-UTC}
```

---

## Configuration

### Using environment variables

Create a `.env` file in the project root:

```bash
# .env
TRADING_BOT_API_KEY=your_api_key_here
LOG_LEVEL=INFO
TZ=UTC
```

Docker Compose reads `.env` automatically. Make sure `.env` is in your `.gitignore`.

### Using config file

Mount your config as a read-only volume (already configured in compose):

```bash
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml
```

The container reads from `/app/config/config.yaml`.

---

## Persistent Data

Three directories are mounted as volumes:

| Host Path    | Container Path  | Purpose                                       |
| ------------ | --------------- | --------------------------------------------- |
| `./data`     | `/app/data`     | SQLite database, OHLCV cache, ML models       |
| `./reports`  | `/app/reports`  | Generated HTML backtest reports                |
| `./config`   | `/app/config`   | Configuration file (mounted read-only)         |

**Backup these directories regularly.** See the [VPS guide](./06-VPS-DEPLOYMENT.md) for automated backup scripts.

### Named volumes (alternative)

For production, you may prefer named volumes:

```yaml
volumes:
  - bot-data:/app/data
  - bot-reports:/app/reports

volumes:
  bot-data:
  bot-reports:
```

---

## Networking and Security

### Bind to localhost only

For local-only access (recommended when using a reverse proxy):

```yaml
ports:
  - "127.0.0.1:8765:8765"
```

### Reverse proxy with Caddy (HTTPS)

Create `Caddyfile`:

```
trading.yourdomain.com {
    reverse_proxy localhost:8765
}
```

Add Caddy to your compose file:

```yaml
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    depends_on:
      - trading-bot
```

Caddy automatically provisions Let's Encrypt certificates.

### Reverse proxy with Nginx

```nginx
server {
    listen 443 ssl;
    server_name trading.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/trading.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/trading.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Production Hardening

### Resource limits

Already configured in `docker-compose.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
    reservations:
      cpus: '0.5'
      memory: 512M
```

Adjust based on your server capacity and how many strategies you run.

### Read-only filesystem

```yaml
services:
  trading-bot:
    read_only: true
    tmpfs:
      - /tmp
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports
      - ./config:/app/config:ro
```

### Security scanning

```bash
# Scan the image for vulnerabilities
docker scout cves crypto-trading-bot:latest

# Or use Trivy
trivy image crypto-trading-bot:latest
```

---

## Monitoring and Logs

### View logs

```bash
# Follow logs
docker compose logs -f trading-bot

# Last 100 lines
docker compose logs --tail=100 trading-bot

# Since a specific time
docker compose logs --since="2024-01-01T00:00:00" trading-bot
```

### Health check

The container has a built-in health check that pings `/api/health` every 30 seconds:

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' crypto-trading-bot

# View health check history
docker inspect --format='{{json .State.Health}}' crypto-trading-bot | python3 -m json.tool
```

### Detailed health endpoint

```bash
curl -H "X-API-Key: YOUR_KEY" http://localhost:8765/api/health/detailed
```

Returns system metrics (CPU, memory), exchange connectivity, trading status, and notification channel status.

---

## Updating

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose build
docker compose up -d

# Verify
docker compose logs -f --tail=20
curl http://localhost:8765/api/health
```

### Zero-downtime updates

```bash
# Build new image
docker compose build

# Rolling restart
docker compose up -d --no-deps --build trading-bot
```

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs trading-bot

# Common issues:
# - Port 8765 already in use: change port mapping
# - Config file missing: ensure config/config.yaml exists
# - Permission errors: check volume mount permissions
```

### Can't connect to API

```bash
# Check container is running
docker compose ps

# Check port binding
docker port crypto-trading-bot

# Test from inside container
docker exec crypto-trading-bot curl http://localhost:8765/api/health
```

### Out of memory

Increase memory limit in `docker-compose.yml`:

```yaml
deploy:
  resources:
    limits:
      memory: 4G
```

### Reset everything

```bash
docker compose down -v   # Remove containers AND volumes
docker compose up -d     # Fresh start
```

**Warning:** `-v` deletes all persisted data (database, cache, reports).
