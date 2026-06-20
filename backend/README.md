# SmartBasket Backend 🛒

The core data processing engine and REST API for SmartBasket, a crowd-sourced platform built to combat grocery inflation. This service manages multi-supermarket SKU data ingestion, schema normalization via a local LLM, trigram-based fuzzy text matching, and background event-driven price change alerts.

## 🛠️ Tech Stack

* **Framework:** FastAPI (Python)
* **Environment Manager:** `uv` by Astral
* **Database Driver:** `psycopg` (PostgreSQL / Amazon Aurora compatible)
* **Text Processing Layer:** Ollama (`gemma2:2b`) with Few-Shot Normalization Templates
* **Fuzzy Engine:** PostgreSQL `pg_trgm` GIN Inverted String Indices

---

# 🚀 Local Quickstart Guide

## 1. Prerequisites

Ensure you have the following installed and running:

* **Python 3.12+**
* **PostgreSQL** running locally on port `5432`
* **Ollama** running locally with the `gemma2:2b` model loaded:

```bash
ollama run gemma2:2b
```

---

## 2. Environment Configuration

Create a `.env` file in the project root:

```env
PGHOST=localhost
PGUSER=postgres
PGPASSWORD=your_secure_password
PGDATABASE=smartbasket
PGPORT=5432
```

---

## 3. Install Dependencies

Initialize the virtual environment and install packages using `uv`:

```bash
uv sync
```

---

## 4. Database Setup

Create the database and apply the schema (including trigram extensions):

```bash
# Create database
createdb smartbasket

# Apply schema
psql -h localhost -U postgres -d smartbasket -f schema.sql
```

---

## 5. Run the Data Pipeline

Populate the database with supermarket catalog data.

### Phase 1: Build Normalization Dictionary

```bash
uv run python seed/build_dict.py
```

### Phase 2: Seed PostgreSQL with Store Data

```bash
uv run python seed/seed.py
```

---

## 6. Start the API Server

Run the development server with hot reloading enabled:

```bash
uv run uvicorn api.index:app --reload
```

The API will be available at:

* **Base URL:** `http://localhost:8000`
* **Swagger Docs:** `http://localhost:8000/api/docs`

---

## Architecture Overview

SmartBasket uses:

1. **Local supermarket scrapers** to collect raw product data.
2. **Ollama + Gemma 2B** to normalize inconsistent product names.
3. **PostgreSQL + `pg_trgm`** for fuzzy SKU matching.
4. **FastAPI** to expose REST endpoints.
5. **Background event processing** for price-change notifications.
