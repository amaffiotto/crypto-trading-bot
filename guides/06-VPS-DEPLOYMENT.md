# VPS Deployment Guide

Deploy the Crypto Trading Bot on any VPS provider: DigitalOcean, Hetzner, Linode, Vultr, or any Linux server you can SSH into.

---

## Table of Contents

1. [Choosing a VPS Provider](#choosing-a-vps-provider)
2. [Server Setup](#server-setup)
3. [Deploy the Bot](#deploy-the-bot)
4. [HTTPS with Caddy](#https-with-caddy)
5. [Automated Backups](#automated-backups)
6. [System Monitoring](#system-monitoring)
7. [Auto-Updates](#auto-updates)
8. [Security Hardening](#security-hardening)
9. [Troubleshooting](#troubleshooting)

---

## Choosing a VPS Provider

| Provider       | Minimum plan            | Monthly cost | Notes                  |
| -------------- | ----------------------- | ------------ | ---------------------- |
| DigitalOcean   | Basic Droplet, 2GB RAM  | $12          | Simple, good docs      |
| Hetzner        | CX22, 2 vCPU / 4GB     | $4.50 (EU)   | Best value in Europe   |
| Linode (Akamai)| Nanode 2GB              | $12          | Good US/EU coverage    |
| Vultr           | Cloud Compute 2GB      | $12          | Many locations         |
| OVH            | VPS Starter             | $6 (EU)      | Cheapest EU option     |

**Minimum requirements:** 1 vCPU, 2 GB RAM, 20 GB SSD, Ubuntu 22.04+.

**Recommended:** 2 vCPU, 4 GB RAM for running ML filters.

---

## Server Setup

These instructions use Ubuntu 24.04. Adapt package manager commands for other distros.

### Step 1: SSH into your server

```bash
ssh root@YOUR_SERVER_IP
```

### Step 2: Create a non-root user

```bash
adduser botuser
usermod -aG sudo botuser
```

Copy your SSH key:

```bash
mkdir -p /home/botuser/.ssh
cp ~/.ssh/authorized_keys /home/botuser/.ssh/
chown -R botuser:botuser /home/botuser/.ssh
chmod 700 /home/botuser/.ssh
chmod 600 /home/botuser/.ssh/authorized_keys
```

Switch to the new user:

```bash
su - botuser
```

### Step 3: Update and install essentials

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw
```

### Step 4: Configure firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Do NOT open port 8765 publicly — the API will be behind a reverse proxy.

### Step 5: Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Install Compose plugin
sudo apt install -y docker-compose-plugin

# Logout and back in
exit
ssh botuser@YOUR_SERVER_IP

# Verify
docker --version
docker compose version
```

---

## Deploy the Bot

### Step 1: Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot

cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```

Edit your exchange API keys, notification settings, etc.

### Step 2: Set up environment

```bash
# Generate an API key
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "TRADING_BOT_API_KEY=$API_KEY" > .env
echo "LOG_LEVEL=INFO" >> .env

echo "Save this API key: $API_KEY"
```

### Step 3: Start

```bash
docker compose up -d
```

### Step 4: Verify

```bash
docker compose ps
curl http://localhost:8765/api/health
```

---

## HTTPS with Caddy

Caddy is the easiest way to get automatic HTTPS.

### Step 1: Install Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

### Step 2: Configure

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
trading.yourdomain.com {
    reverse_proxy localhost:8765

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }
}
EOF

sudo systemctl restart caddy
```

### Step 3: Point DNS

Create an A record pointing `trading.yourdomain.com` to your server's IP address. Caddy automatically provisions a Let's Encrypt certificate.

---

## Automated Backups

### Local + remote backup script

Create `~/backup.sh`:

```bash
#!/bin/bash
set -e

BOT_DIR="$HOME/crypto-trading-bot"
BACKUP_DIR="$HOME/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

# Create backup archive
tar -czf "$BACKUP_DIR/bot-backup-$TIMESTAMP.tar.gz" \
  -C "$BOT_DIR" data/ config/config.yaml

# Delete backups older than KEEP_DAYS
find "$BACKUP_DIR" -name "bot-backup-*.tar.gz" -mtime +$KEEP_DAYS -delete

echo "[$(date)] Backup completed: bot-backup-$TIMESTAMP.tar.gz"
```

### Schedule

```bash
chmod +x ~/backup.sh
crontab -e
```

Add:

```
# Daily backup at 3 AM
0 3 * * * /home/botuser/backup.sh >> /home/botuser/backup.log 2>&1
```

### Optional: sync to remote storage

Add to the backup script:

```bash
# rsync to another server
rsync -az "$BACKUP_DIR/" backupuser@backup-server:/backups/trading-bot/

# Or upload to S3-compatible storage (DigitalOcean Spaces, Backblaze B2, etc.)
# s3cmd put "$BACKUP_DIR/bot-backup-$TIMESTAMP.tar.gz" s3://your-bucket/backups/
```

### Restore from backup

```bash
cd ~/crypto-trading-bot
docker compose down

tar -xzf ~/backups/bot-backup-YYYYMMDD_HHMMSS.tar.gz -C .

docker compose up -d
```

---

## System Monitoring

### Basic monitoring with htop

```bash
sudo apt install -y htop
htop
```

### Docker stats

```bash
# Real-time container resource usage
docker stats crypto-trading-bot
```

### Health check script

Create `~/healthcheck.sh`:

```bash
#!/bin/bash
RESPONSE=$(curl -sf http://localhost:8765/api/health)
if [ $? -ne 0 ]; then
  echo "[$(date)] ALERT: Trading bot health check FAILED"
  # Optional: send notification via curl to webhook
  # curl -X POST "https://hooks.slack.com/..." -d '{"text":"Trading bot is down!"}'
  
  # Attempt auto-recovery
  cd ~/crypto-trading-bot && docker compose restart
fi
```

Schedule every 5 minutes:

```bash
chmod +x ~/healthcheck.sh
crontab -e
# */5 * * * * /home/botuser/healthcheck.sh >> /home/botuser/healthcheck.log 2>&1
```

### Log rotation

Docker logs can grow large. Configure rotation in `/etc/docker/daemon.json`:

```bash
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

sudo systemctl restart docker
```

---

## Auto-Updates

### Manual update process

```bash
cd ~/crypto-trading-bot
git pull origin main
docker compose build
docker compose up -d
docker compose logs --tail=20
```

### Automated update script (use with caution)

```bash
#!/bin/bash
cd ~/crypto-trading-bot

# Pull latest
git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
  echo "[$(date)] New version available, updating..."
  git pull origin main
  docker compose build --quiet
  docker compose up -d
  echo "[$(date)] Update complete"
else
  echo "[$(date)] Already up to date"
fi
```

---

## Security Hardening

### 1. Disable root SSH login

```bash
sudo nano /etc/ssh/sshd_config
# Set: PermitRootLogin no
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

### 2. Fail2ban (brute-force protection)

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
```

### 3. Automatic security updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 4. Keep Docker updated

```bash
sudo apt update && sudo apt upgrade -y docker-ce docker-ce-cli
```

---

## Troubleshooting

### Bot won't start

```bash
docker compose logs trading-bot
# Check for import errors, missing config, etc.
```

### API unreachable externally

```bash
# Check Caddy status
sudo systemctl status caddy

# Check Caddy logs
sudo journalctl -u caddy --no-pager --since "1 hour ago"

# Check DNS
dig trading.yourdomain.com

# Check firewall
sudo ufw status
```

### High memory usage

```bash
# Check container stats
docker stats --no-stream

# Increase swap (emergency)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Container restarting in a loop

```bash
# Check exit code
docker inspect --format='{{.State.ExitCode}}' crypto-trading-bot

# Check last logs before crash
docker compose logs --tail=50 trading-bot
```
