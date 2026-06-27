# SmartBasket Backend Services (EC2 Setup)

This document outlines the deployment and configuration for the SmartBasket FastAPI Web Server and the Async OCR Worker. Both services run as background daemons on your EC2 instance.

---

# 1. Environment Configuration

Ensure your `.env` file at:

```bash
/home/ec2-user/smartbasket/backend/.env
```

contains:

```env
APP_ENV=production
DATABASE_URL=postgresql://<user>:<password>@<rds-endpoint>:5432/<dbname>
GROQ_API_KEY=
AWS_REGION=eu-west-2
AWS_STORAGE_BUCKET_NAME=smartbasket-receipts
AWS_SQS_QUEUE_URL=https://sqs.eu-west-2.amazonaws.com/<account-id>/<queue-name>
```

---

# 2. FastAPI Web Server Service

Create the service file:

```bash
sudo nano /etc/systemd/system/smartbasket-api.service
```

Paste:

```ini
[Unit]
Description=SmartBasket FastAPI Web Server
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/smartbasket/backend
ExecStart=/home/ec2-user/smartbasket/backend/venv/bin/uvicorn api.index:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/home/ec2-user/smartbasket/backend/.env

[Install]
WantedBy=multi-user.target
```

---

# 3. Async OCR Worker Service

Create the service file:

```bash
sudo nano /etc/systemd/system/smartbasket-worker.service
```

Paste:

```ini
[Unit]
Description=SmartBasket Async OCR Worker
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/smartbasket/backend
ExecStart=/home/ec2-user/smartbasket/backend/venv/bin/python worker.py
Restart=always
RestartSec=5
EnvironmentFile=/home/ec2-user/smartbasket/backend/.env
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

# 4. Activation

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Enable services:

```bash
sudo systemctl enable smartbasket-api
sudo systemctl enable smartbasket-worker
```

Start services:

```bash
sudo systemctl start smartbasket-api
sudo systemctl start smartbasket-worker
```

---

# 5. Operations & Debugging

## Deployment Workflow

After pulling new code:

```bash
git pull
```

Restart both services:

```bash
sudo systemctl restart smartbasket-api smartbasket-worker
```

---

## Monitoring Logs

API logs:

```bash
sudo journalctl -u smartbasket-api -f
```

Worker logs:

```bash
sudo journalctl -u smartbasket-worker -f
```

---

## Status Check

Verify both services are running:

```bash
systemctl status smartbasket-api smartbasket-worker
```