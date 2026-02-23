# Crypto Trading Bot — Documentation

Step-by-step guides for setting up, deploying, and extending the trading bot.

---

## Guides

| # | Guide | Description |
|---|-------|-------------|
| 01 | [Getting Started](./01-GETTING-STARTED.md) | Installation on macOS, Linux, and Windows. All dependencies, first run, project structure. |
| 02 | [Configuration Reference](./02-CONFIGURATION.md) | Every setting in `config.yaml` explained: exchanges, strategies, filters, notifications, API, ML, sentiment, optimizer. |
| 03 | [Docker Deployment](./03-DOCKER-DEPLOYMENT.md) | Build the image, Docker Compose, persistent data, reverse proxy with HTTPS, production hardening, monitoring. |
| 04 | [AWS Deployment](./04-AWS-DEPLOYMENT.md) | EC2 with Docker, ECS Fargate, Secrets Manager, CloudWatch monitoring, S3 backups, cost estimates. |
| 05 | [GCP Deployment](./05-GCP-DEPLOYMENT.md) | Compute Engine VM, Cloud Run, Secret Manager, Cloud Monitoring, Cloud Storage backups. |
| 06 | [VPS Deployment](./06-VPS-DEPLOYMENT.md) | Generic guide for DigitalOcean, Hetzner, Linode, Vultr. Server setup, Caddy HTTPS, automated backups, security hardening. |
| 07 | [Strategy Development](./07-STRATEGY-GUIDE.md) | Create custom strategies, use filters (regime, multi-timeframe, ML, sentiment), backtesting, walk-forward optimization, OOS testing, paper trading validation, running tests. |

---

## Quick Links

- **First time?** Start with [01 Getting Started](./01-GETTING-STARTED.md)
- **Deploying to production?** Choose your platform: [Docker](./03-DOCKER-DEPLOYMENT.md) | [AWS](./04-AWS-DEPLOYMENT.md) | [GCP](./05-GCP-DEPLOYMENT.md) | [VPS](./06-VPS-DEPLOYMENT.md)
- **Building strategies?** Go to [07 Strategy Development](./07-STRATEGY-GUIDE.md)
- **Need to configure something?** See [02 Configuration Reference](./02-CONFIGURATION.md)
