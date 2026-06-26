# 🛒 SmartBasket

> **SmartBasket** makes cross-store grocery price matching calm, friendly, and effortless for everyday shoppers. Built as a monetizable B2C application, it eliminates the cognitive load of deal-hunting by calculating the absolute best shopping path across top UK supermarkets.

---

# 🚀 Hackathon Submission Dashboard

| Requirement                 | Submission Details                                                 |
| --------------------------- | ------------------------------------------------------------------ |
| **Track**                   | **Track 1: Monetizable B2C App** (Retail & E-commerce Side Hustle) |
| **Designated AWS Database** | **AWS Aurora PostgreSQL**                                          |
| **Published Frontend URL**  | https://smartbasket-tau.vercel.app                                 |
| **Vercel Team ID**          | `team_iMXd1IGMCa0kklHl8we9f0z6`                                    |

---

# 💡 The Problem & Opportunity

## The Problem

Grocery inflation has turned supermarket shopping into a stressful logistical puzzle. Everyday consumers know they could save money by splitting their basket across multiple retailers (e.g. buying staples at Aldi while catching promotions at Tesco), but manually comparing prices creates unnecessary cognitive load.

## Our Solution

SmartBasket does the heavy lifting quietly in the background. Users add items to a beautifully clean, minimalist interface inspired by Apple, Airbnb, and Monzo. The backend instantly generates a clear **Best Shopping Plan**, breaking down exactly what items to buy where and displaying transparent savings without requiring users to do the maths.

---

# ✨ Features

* 🛒 Build grocery lists in seconds
* 💷 Compare prices across major UK supermarkets
* 📊 Generate the optimal shopping plan automatically
* 💰 Display guaranteed basket savings
* ⚡ Real-time deal updates and price intelligence
* 📱 Minimalist, mobile-friendly experience
* 🔔 Live notifications powered by SSE streams

---

# ⏱️ Hackathon Timeline Development Updates

To support real-world consumer traffic and scale seamlessly under Track 1 constraints, the application infrastructure was completely overhauled and migrated during the hackathon window.

* **Database Re-architecting:** Migrated core repository states onto an **Amazon Aurora PostgreSQL** serverless cluster tier, implementing relational foreign-key integrity constraints across `price_history`, `master_items`, `receipts`, and `user_baskets`.
* **Asynchronous Decoupling:** Shifted the intensive, high-compute computer vision pipelines away from synchronous web runtimes. Designed an event-driven system offloading images directly to **Amazon S3** and dispatching job payloads into **Amazon SQS**.
* **Spot Instances Deployment:** Built a headless background Python daemon running on a highly cost-efficient **AWS EC2 Spot Instance**, engineered with explicit SQS message visibility safeties ensuring zero data loss during cloud compute reclamations.
* **Race Condition & Integrity Shields:** Programmed late-stage database constraint checks inside the ingestion loop to catch and drop duplicate receipt image hashes cleanly at the last possible millisecond.

---

# 🛠️ Technical Implementation & Architecture

SmartBasket is organized as a scalable full-stack monorepo designed for low operational cost and high responsiveness.

## Frontend

* **Next.js (React)**
* Serverless deployment on **Vercel**
* Edge delivery for fast page loads

## Backend

* **Python + FastAPI**
* Session state management
* Real-time Server-Sent Events (SSE)
* Shopping optimization engine

## Database

* **AWS Aurora PostgreSQL**
* Product catalogue storage
* Price maps and store relationships
* User basket persistence

---

# 🏗️ Why AWS Aurora PostgreSQL?

SmartBasket handles deeply relational, highly granular data structures. The application must resolve thousands of supermarket variations and category mappings in real time.

Aurora PostgreSQL was selected because it provides:

### 1. Relational Complexity

Efficient multi-table joins allow canonical product identifiers to map seamlessly to store-specific variants.

### 2. Serverless Scale

Aurora automatically scales capacity with demand while minimizing idle costs.

### 3. Low-Latency Aggregations

Background workers evaluate price drops and feed **Today's Best Deals** into the application.

### 4. PostgreSQL Trigram Indexing

Supermarket receipts frequently contain truncated OCR text such as:

```text
JS STRAWBS 40OG
SHRNEBS HooG
```

SmartBasket leverages PostgreSQL's native **Trigram Similarity Indexes** (`similarity(raw_name, %s)`) directly inside Aurora to map noisy OCR output back to canonical products without expensive application-side processing.

### 5. Threaded Connection Pooling

Worker processes utilize:

```python
psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10)
```

to maintain efficient concurrent access while preventing database connection starvation during heavy SQS workloads.

---

# 📊 System Architecture

```text
       ┌─────────────────────────────────────────────────────────┐
       │                 Vercel Edge Deployment                  │
       │  ┌───────────────────────────────────────────────────┐  │
       │  │             Next.js Frontend (v0 UI)              │  │
       │  └─────────────────────────┬─────────────────────────┘  │
       └────────────────────────────┼────────────────────────────┘
                       Secure HTTPS │ API / Multipart Form Upload
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │                Managed Host Environment                 │
       │  ┌───────────────────────────────────────────────────┐  │
       │  │               FastAPI Backend Engine              │  │
       │  └───────┬─────────────────────────────────────┬─────┘  │
       └──────────┼─────────────────────────────────────┼────────┘
                  │                                     │
     Binary Stream│ (Direct Upload)          Job Payload│ (JSON Task)
                  ▼                                     ▼
       ┌────────────────────────┐            ┌──────────────────┐
       │     Amazon S3 Bucket   │            │  Amazon SQS Task │
       │ (smartbasket-receipts) │            │  Execution Queue │
       └──────────┬─────────────┘            └──────────┬───────┘
                  │                                     │
                  │ Object Get                          │ Long Poll (20s)
                  └───────────────┐     ┌───────────────┘
                                  ▼     ▼
       ┌─────────────────────────────────────────────────────────┐
       │          AWS EC2 Compute Cluster (Spot Pricing)         │
       │  ┌───────────────────────────────────────────────────┐  │
       │  │     Python Async OCR Daemon (worker.py Process)   │  │
       │  │   EasyOCR Engine (CPU) • Llama 3.3 Text Healing   │  │
       │  └─────────────────────────┬─────────────────────────┘  │
       └────────────────────────────┼────────────────────────────┘
                                    │ Secure VPC Write
                      IAM Auth Role │ Threaded Conn Pool
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │                     AWS Cloud Boundary                  │
       │  ┌───────────────────────────────────────────────────┐  │
       │  │              AWS Aurora PostgreSQL                │  │
       │  │   Product Catalogue • Price Map • User Ledger    │  │
       │  └───────────────────────────────────────────────────┘  │
       └─────────────────────────────────────────────────────────┘
```

---

# 🔒 Security Practices

## Zero Exposed Credentials

No raw access keys, database passwords, or cluster connection strings exist within the repository.

## Environment Layering

All secrets are loaded securely using Vercel Environment Variables.

## Minimal Exposure

Only runtime environment parameters such as:

```env
NEXT_PUBLIC_API_URL=
DATABASE_URL=
```

are consumed by the application, keeping production infrastructure private.

---

# 📂 Project Structure

```text
smartbasket/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── public/
│   └── styles/
│
├── backend/
│   ├── api/
│   ├── services/
│   ├── models/
│   └── workers/
│
├── database/
│   ├── migrations/
│   └── seed/
│
└── README.md
```

---

# 🚀 Tech Stack

| Layer     | Technology            |
| --------- | --------------------- |
| Frontend  | Next.js               |
| Backend   | FastAPI               |
| Database  | AWS Aurora PostgreSQL |
| Hosting   | Vercel                |
| Languages | TypeScript + Python   |
| Realtime  | Server-Sent Events    |
| Cloud     | AWS                   |

---

# 📣 Hackathon Entry Notice

This project was created for submission to the **H0 Hackathon** under **Track 1: Monetizable B2C App**, demonstrating a scalable grocery price comparison platform powered by AWS Aurora PostgreSQL and modern cloud infrastructure.

**#H0Hackathon**
