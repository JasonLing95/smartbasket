# SmartBasket Backend 🛒

The core data processing engine, REST API, and asynchronous worker daemon for SmartBasket. This service manages multi-supermarket SKU data ingestion, computer vision receipt parsing, schema normalization via LLMs, trigram-based fuzzy text matching, and background event-driven price change alerts.

## 🛠️ Tech Stack & Infrastructure

* **API Framework:** FastAPI (Python)
* **Database Driver:** `psycopg2` (Threaded Connection Pooling)
* **Target Database:** Amazon Aurora PostgreSQL (Serverless)
* **Cloud Architecture:** Amazon S3 (Blob Storage) & Amazon SQS (Event Queues)
* **Compute:** AWS EC2 Spot Instances (Background Worker Daemon)
* **ML Extraction Layer:** EasyOCR (Image Flattening) + Groq Llama-3.3-70B (Structural Parsing)
* **Fuzzy Engine:** PostgreSQL `pg_trgm` GIN Inverted String Indices

---

# 🚀 Architecture Overview

To ensure the Next.js edge frontend never times out during heavy machine learning workloads, the SmartBasket backend is strictly decoupled into two separate execution environments.

## 1. API Web Runtime (`api/index.py`)

Handles:

* JWT authentication
* Database querying
* Receipt uploads

Instead of processing images inline, the API:

1. Uploads receipt images to **Amazon S3**
2. Pushes a lightweight job payload into an **Amazon SQS queue**
3. Returns immediately to the frontend

## 2. Asynchronous Worker (`worker.py`)

A headless polling daemon designed to run on low-cost **AWS EC2 Spot Instances**.

The worker:

* Pulls jobs from Amazon SQS
* Executes the EasyOCR + Llama 3.3 extraction pipeline
* Normalizes receipt data
* Writes structured records directly into **Amazon Aurora PostgreSQL**

---

# 💻 Local Development Setup

## 1. Prerequisites

Ensure you have the following installed:

* **Python 3.9+**
* An active **Amazon Aurora PostgreSQL** database instance (or a local PostgreSQL installation with the `pg_trgm` extension enabled)

---

## 2. Environment Configuration

Create a `.env` file in the project root:

```env
APP_ENV=development

# Database Connection
DATABASE_URL=postgresql://<user>:<password>@<aurora-endpoint>:5432/<dbname>

# AWS Infrastructure
AWS_REGION=eu-west-2
AWS_STORAGE_BUCKET_NAME=smartbasket-receipts
AWS_SQS_QUEUE_URL=https://sqs.eu-west-2.amazonaws.com/<account-id>/<queue-name>

# AI & LLM Providers
GROQ_API_KEY=gsk_your_api_key_here
```

## 3. Install Dependencies

Create a virtual environment and install the required packages:

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

---

# ⚙️ Running the Application

Because of the decoupled architecture, running the full pipeline locally requires **two terminal windows**.

## Terminal 1 — Start the API Server

Run the FastAPI server:

```bash
uvicorn api.index:app --reload --port 8000
```

API Base URL:

```text
http://localhost:8000
```

Swagger Documentation:

```text
http://localhost:8000/docs
```

---

## Terminal 2 — Start the Async Worker

Run the background worker:

```bash
python worker.py
```

The worker will:

* Verify AWS credentials
* Begin long-polling the Amazon SQS queue
* Process receipt ingestion jobs as they arrive

---

# 🛡️ Data Integrity & Fault Tolerance

The `worker.py` daemon is designed for volatile cloud environments such as **AWS EC2 Spot Instances**.

Key reliability features include:

* **Duplicate Detection:** Performs late-stage database checks (`SELECT id FROM receipts WHERE image_hash = ...`) during ingestion to prevent duplicate uploads.
* **At-Least-Once Processing:** SQS messages are only deleted after the transaction has been successfully committed to Amazon Aurora PostgreSQL.
* **Crash Recovery:** If a Spot Instance is reclaimed during processing, the SQS message becomes visible again and is safely reprocessed, preventing data loss.
