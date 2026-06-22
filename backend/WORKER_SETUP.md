# SmartBasket Async OCR Worker (EC2 Setup)

This document outlines the deployment and configuration steps for the SmartBasket asynchronous OCR worker. This daemon runs 24/7 on an Amazon EC2 instance, polling AWS SQS for incoming receipt images routed from the Vercel edge network, processing them via EasyOCR (CPU), and committing the extracted data to PostgreSQL.

---

# 1. Prerequisites

Before setting up the worker, ensure your EC2 instance (Amazon Linux 2023 / Ubuntu) has the following installed:

- Python 3.9+ (3.10+ recommended per boto3 deprecation warnings)
- git
- pip and virtualenv

Your EC2 instance must also have an attached IAM Role (or configured `~/.aws/credentials`) with permissions for:

- `s3:GetObject` on the `smartbasket-receipts` bucket.
- `sqs:ReceiveMessage`
- `sqs:DeleteMessage` on the designated queue.

---

# 2. Installation

Clone the repository and set up the Python virtual environment specifically for the backend worker.

```bash
# Navigate to the home directory and clone
cd /home/ec2-user
git clone <your-repo-url> smartbasket
cd smartbasket/backend

# Initialize and activate the virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the heavy ML and infrastructure dependencies
pip install -r requirements.txt
```

**Note:** The EC2 `requirements.txt` must include:

- boto3
- easyocr
- torch
- python-dotenv
- psycopg2-binary
- fastapi

---

# 3. Environment Configuration

Create a `.env` file in the root of the backend directory. This is required for both the database pool engine and the AWS SDK.

```bash
nano /home/ec2-user/smartbasket/backend/.env
```

Add the following variables:

```env
APP_ENV=production

# Database
DATABASE_URL=postgresql://<user>:<password>@<rds-endpoint>:5432/<dbname>

# AWS Infrastructure
AWS_REGION=eu-west-2
AWS_STORAGE_BUCKET_NAME=smartbasket-receipts
AWS_SQS_QUEUE_URL=https://sqs.eu-west-2.amazonaws.com/<account-id>/<queue-name>
```

---

# 4. Systemd Daemon Setup

To ensure the worker runs continuously in the background and automatically restarts on server reboots or fatal crashes, configure it as a systemd service.

Create the service file:

```bash
sudo nano /etc/systemd/system/smartbasket-worker.service
```

Paste the following configuration (verify the paths match your EC2 user):

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

# Force Python to flush stdout to journalctl instantly
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start the daemon:

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable it to start on server boot
sudo systemctl enable smartbasket-worker

# Start the service immediately
sudo systemctl start smartbasket-worker
```

---

# 5. Operations & Debugging

Because the worker processes requests invisibly in the background, use `journalctl` to monitor its health and OCR execution logs.

## View live, tailing logs (recommended for debugging)

```bash
sudo journalctl -u smartbasket-worker -f
```

## Restart the worker

Required after pulling new code via git:

```bash
sudo systemctl restart smartbasket-worker
```

## Stop the worker

Useful for manual SQS debugging via AWS Console:

```bash
sudo systemctl stop smartbasket-worker
```

---

# Known Warnings

### PyTorch CPU Warning

```
UserWarning: 'pin_memory' argument is set as true but no accelerator is found
```

This is a standard PyTorch warning indicating that the script is utilizing the CPU rather than a GPU. It is expected behavior on this instance tier and can be safely ignored.