# AWS Deployment Guide

Deploy the Crypto Trading Bot on Amazon Web Services using EC2 or ECS.

---

## Table of Contents

1. [Architecture Options](#architecture-options)
2. [Option A: EC2 with Docker](#option-a-ec2-with-docker)
3. [Option B: ECS Fargate](#option-b-ecs-fargate)
4. [Secrets Management](#secrets-management)
5. [Monitoring with CloudWatch](#monitoring-with-cloudwatch)
6. [Backup with S3](#backup-with-s3)
7. [Cost Estimates](#cost-estimates)
8. [Security Best Practices](#security-best-practices)

---

## Architecture Options

| Approach        | Best for               | Monthly cost (approx.) |
| --------------- | ---------------------- | ---------------------- |
| EC2 + Docker    | Simplicity, full control | $5–20 (t3.small)     |
| ECS Fargate     | Managed, auto-scaling  | $15–40                 |

For most users running a single bot, **EC2 with Docker** is the simplest and cheapest option.

---

## Option A: EC2 with Docker

### Step 1: Launch an EC2 instance

1. Open the [EC2 Console](https://console.aws.amazon.com/ec2/).
2. Click **Launch Instance**.
3. Configure:
   - **Name:** `crypto-trading-bot`
   - **AMI:** Ubuntu Server 24.04 LTS (or Amazon Linux 2023)
   - **Instance type:** `t3.small` (2 vCPU, 2 GB RAM) — sufficient for 1-3 strategies
   - **Key pair:** Create or select an existing SSH key
   - **Storage:** 20 GB gp3
   - **Security group:** Allow SSH (port 22) from your IP, and optionally port 8765 for API access

4. Click **Launch Instance**.

### Step 2: Connect via SSH

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

### Step 3: Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Log out and back in for group changes
exit
```

Reconnect via SSH, then verify:

```bash
docker --version
docker compose version
```

### Step 4: Deploy the bot

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot

# Create config
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
# Add your exchange API keys and settings

# Create .env file
cat > .env << 'EOF'
TRADING_BOT_API_KEY=your_generated_api_key
LOG_LEVEL=INFO
TZ=UTC
EOF

# Start
docker compose up -d

# Verify
docker compose ps
curl http://localhost:8765/api/health
```

### Step 5: Set up a reverse proxy (optional, for HTTPS)

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Configure
sudo tee /etc/caddy/Caddyfile << 'EOF'
trading.yourdomain.com {
    reverse_proxy localhost:8765
}
EOF

sudo systemctl restart caddy
```

Point your domain's DNS A record to the EC2 public IP. Caddy handles HTTPS automatically.

### Step 6: Auto-start on boot

Docker Compose with `restart: unless-stopped` handles container restarts. For the Docker daemon:

```bash
sudo systemctl enable docker
```

---

## Option B: ECS Fargate

### Step 1: Push image to ECR

```bash
# Create ECR repository
aws ecr create-repository --repository-name crypto-trading-bot --region us-east-1

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t crypto-trading-bot .
docker tag crypto-trading-bot:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/crypto-trading-bot:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/crypto-trading-bot:latest
```

### Step 2: Create ECS cluster

```bash
aws ecs create-cluster --cluster-name trading-bot-cluster
```

### Step 3: Create task definition

Create `ecs-task-definition.json`:

```json
{
  "family": "crypto-trading-bot",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "trading-bot",
      "image": "YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/crypto-trading-bot:latest",
      "portMappings": [
        {
          "containerPort": 8765,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "LOG_LEVEL", "value": "INFO"}
      ],
      "secrets": [
        {
          "name": "TRADING_BOT_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:trading-bot-api-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/crypto-trading-bot",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8765/api/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3
      }
    }
  ]
}
```

Register it:

```bash
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
```

### Step 4: Create service

```bash
aws ecs create-service \
  --cluster trading-bot-cluster \
  --service-name trading-bot-service \
  --task-definition crypto-trading-bot \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

---

## Secrets Management

**Never hardcode API keys.** Use AWS Secrets Manager:

```bash
# Store your API key
aws secretsmanager create-secret \
  --name trading-bot-api-key \
  --secret-string "your_api_key_here"

# Store exchange credentials
aws secretsmanager create-secret \
  --name trading-bot-exchange-keys \
  --secret-string '{"binance_key":"xxx","binance_secret":"yyy"}'
```

For EC2 with Docker, read secrets at startup:

```bash
# In a startup script
export TRADING_BOT_API_KEY=$(aws secretsmanager get-secret-value \
  --secret-id trading-bot-api-key \
  --query SecretString --output text)
docker compose up -d
```

The EC2 instance needs an IAM role with `secretsmanager:GetSecretValue` permission.

---

## Monitoring with CloudWatch

### Container-level metrics

For ECS Fargate, metrics are automatic. For EC2, install the CloudWatch agent:

```bash
sudo apt install -y amazon-cloudwatch-agent
```

### Application-level alarms

```bash
# CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "trading-bot-high-cpu" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:alerts
```

### Log monitoring

```bash
# Create log group
aws logs create-log-group --log-group-name /trading-bot/api

# Stream Docker logs to CloudWatch
# Add to docker-compose.yml:
#   logging:
#     driver: awslogs
#     options:
#       awslogs-group: /trading-bot/api
#       awslogs-region: us-east-1
```

---

## Backup with S3

### Automated daily backup script

Create `/home/ubuntu/backup.sh`:

```bash
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/trading-bot-backup-$TIMESTAMP"
S3_BUCKET="your-backup-bucket"

mkdir -p "$BACKUP_DIR"

# Copy important files
cp -r /home/ubuntu/crypto-trading-bot/data "$BACKUP_DIR/"
cp /home/ubuntu/crypto-trading-bot/config/config.yaml "$BACKUP_DIR/"

# Compress
tar -czf "/tmp/trading-bot-$TIMESTAMP.tar.gz" -C "$BACKUP_DIR" .

# Upload to S3
aws s3 cp "/tmp/trading-bot-$TIMESTAMP.tar.gz" "s3://$S3_BUCKET/backups/"

# Cleanup old local backups
rm -rf "$BACKUP_DIR" "/tmp/trading-bot-$TIMESTAMP.tar.gz"

# Delete S3 backups older than 30 days
aws s3 ls "s3://$S3_BUCKET/backups/" | awk '{print $4}' | while read file; do
  file_date=$(echo "$file" | grep -oP '\d{8}')
  if [ -n "$file_date" ]; then
    days_old=$(( ($(date +%s) - $(date -d "$file_date" +%s)) / 86400 ))
    if [ "$days_old" -gt 30 ]; then
      aws s3 rm "s3://$S3_BUCKET/backups/$file"
    fi
  fi
done

echo "Backup completed: $TIMESTAMP"
```

Schedule with cron:

```bash
chmod +x /home/ubuntu/backup.sh
crontab -e
# Add: 0 2 * * * /home/ubuntu/backup.sh >> /var/log/trading-bot-backup.log 2>&1
```

---

## Cost Estimates

| Resource                | Monthly Cost (USD) |
| ----------------------- | ------------------ |
| t3.small EC2 (on-demand)| ~$15               |
| t3.small EC2 (reserved) | ~$8                |
| 20 GB gp3 EBS           | ~$1.60             |
| S3 backup (5 GB)         | ~$0.12             |
| Data transfer (10 GB)    | ~$0.90             |
| **Total (EC2)**          | **~$10–18/month**  |

Save up to 40% with Reserved Instances or Savings Plans for long-running bots.

---

## Security Best Practices

1. **Restrict SSH access** to your IP only in the security group
2. **Use Secrets Manager** for API keys and exchange credentials
3. **Enable API authentication** (`auth_enabled: true` in config)
4. **Keep the OS and Docker updated** — enable unattended upgrades:
   ```bash
   sudo apt install -y unattended-upgrades
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```
5. **Use a reverse proxy with HTTPS** — never expose the raw API port to the internet
6. **Monitor CloudWatch alarms** for unusual CPU/memory usage
7. **Rotate API keys** periodically
