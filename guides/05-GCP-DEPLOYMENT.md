# Google Cloud Platform Deployment Guide

Deploy the Crypto Trading Bot on GCP using Compute Engine or Cloud Run.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Option A: Compute Engine VM](#option-a-compute-engine-vm)
3. [Option B: Cloud Run](#option-b-cloud-run)
4. [Secrets Management](#secrets-management)
5. [Monitoring](#monitoring)
6. [Backup with Cloud Storage](#backup-with-cloud-storage)
7. [Cost Estimates](#cost-estimates)

---

## Prerequisites

1. A GCP account with billing enabled
2. `gcloud` CLI installed: [cloud.google.com/sdk/install](https://cloud.google.com/sdk/docs/install)
3. A GCP project created

```bash
# Authenticate
gcloud auth login

# Set project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable compute.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

---

## Option A: Compute Engine VM

Best for: persistent, long-running bots with full control.

### Step 1: Create a VM

```bash
gcloud compute instances create crypto-trading-bot \
  --zone=us-central1-a \
  --machine-type=e2-small \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-balanced \
  --tags=trading-bot
```

### Step 2: Allow API access (optional)

```bash
gcloud compute firewall-rules create allow-trading-api \
  --allow=tcp:8765 \
  --target-tags=trading-bot \
  --source-ranges=YOUR_IP/32 \
  --description="Allow trading bot API access"
```

For production, use an HTTPS load balancer instead of exposing the port directly.

### Step 3: Connect and install Docker

```bash
gcloud compute ssh crypto-trading-bot --zone=us-central1-a
```

Inside the VM:

```bash
# Install Docker
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install -y docker-compose-plugin
exit
```

Reconnect:

```bash
gcloud compute ssh crypto-trading-bot --zone=us-central1-a
```

### Step 4: Deploy

```bash
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot

cp config/config.example.yaml config/config.yaml
nano config/config.yaml
# Configure exchange keys

# Create .env
echo "TRADING_BOT_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > .env

# Start
docker compose up -d
docker compose ps
curl http://localhost:8765/api/health
```

### Step 5: Auto-start on boot

```bash
sudo systemctl enable docker
```

Docker Compose with `restart: unless-stopped` ensures the container restarts automatically.

---

## Option B: Cloud Run

Best for: serverless, pay-per-use, automatic scaling. Note: Cloud Run is stateless, so persistent data needs external storage (Cloud SQL, Cloud Storage).

### Step 1: Create Artifact Registry repository

```bash
gcloud artifacts repositories create trading-bot \
  --repository-format=docker \
  --location=us-central1
```

### Step 2: Build and push image

```bash
# Configure Docker for Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT/trading-bot/crypto-bot:latest .
docker push us-central1-docker.pkg.dev/YOUR_PROJECT/trading-bot/crypto-bot:latest
```

### Step 3: Deploy to Cloud Run

```bash
gcloud run deploy crypto-trading-bot \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT/trading-bot/crypto-bot:latest \
  --port=8765 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=1 \
  --max-instances=1 \
  --region=us-central1 \
  --set-env-vars="LOG_LEVEL=INFO" \
  --set-secrets="TRADING_BOT_API_KEY=trading-bot-api-key:latest" \
  --allow-unauthenticated
```

The `--min-instances=1` keeps the container warm (important for a trading bot that needs to be always-on).

---

## Secrets Management

Use GCP Secret Manager:

```bash
# Create a secret
echo -n "your_api_key_here" | gcloud secrets create trading-bot-api-key --data-file=-

# Create exchange key secrets
echo -n '{"api_key":"xxx","api_secret":"yyy"}' | gcloud secrets create trading-bot-exchange --data-file=-

# Grant access to compute instance service account
gcloud secrets add-iam-policy-binding trading-bot-api-key \
  --member="serviceAccount:YOUR_COMPUTE_SA@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Read secrets in a startup script on Compute Engine:

```bash
export TRADING_BOT_API_KEY=$(gcloud secrets versions access latest --secret="trading-bot-api-key")
```

---

## Monitoring

### Cloud Monitoring (Compute Engine)

GCP automatically collects VM metrics (CPU, memory, disk). Add custom alerts:

1. Go to **Monitoring > Alerting** in the Console
2. Create an alerting policy:
   - Metric: `compute.googleapis.com/instance/cpu/utilization`
   - Threshold: > 80% for 5 minutes
   - Notification: email or Slack

### Cloud Logging

For Compute Engine with Docker:

```bash
# Install the Ops Agent
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install
```

View logs in the Console under **Logging > Logs Explorer**.

### Health check endpoint

Add an uptime check:

1. Go to **Monitoring > Uptime Checks**
2. Create check:
   - Protocol: HTTP
   - Host: your VM's external IP
   - Port: 8765
   - Path: `/api/health`

---

## Backup with Cloud Storage

### Create a bucket

```bash
gsutil mb gs://YOUR_PROJECT-trading-bot-backups
```

### Automated backup script

```bash
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Backup data directory
tar -czf "/tmp/backup-$TIMESTAMP.tar.gz" \
  -C /home/$USER/crypto-trading-bot data/ config/config.yaml

# Upload
gsutil cp "/tmp/backup-$TIMESTAMP.tar.gz" gs://YOUR_PROJECT-trading-bot-backups/

# Clean up local
rm "/tmp/backup-$TIMESTAMP.tar.gz"

# Set lifecycle policy to auto-delete after 30 days
gsutil lifecycle set <(echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}') \
  gs://YOUR_PROJECT-trading-bot-backups/
```

Schedule with cron:

```bash
crontab -e
# 0 3 * * * /home/ubuntu/backup.sh
```

---

## Cost Estimates

| Resource                | Monthly Cost (USD)  |
| ----------------------- | ------------------- |
| e2-small VM (on-demand) | ~$13                |
| e2-small VM (committed) | ~$8                 |
| 20 GB balanced disk     | ~$2                 |
| Cloud Storage (5 GB)    | ~$0.10              |
| Network egress (5 GB)   | ~$0.60              |
| **Total (Compute)**     | **~$10–16/month**   |

| Resource (Cloud Run)    | Monthly Cost (USD)  |
| ----------------------- | ------------------- |
| 1 vCPU always-on        | ~$25                |
| 1 GB memory always-on   | ~$7                 |
| **Total (Cloud Run)**   | **~$32/month**      |

Compute Engine is significantly cheaper for always-on workloads.
