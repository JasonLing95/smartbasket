# 🛒 SmartBasket

> **SmartBasket** makes cross-store grocery price matching calm, friendly, and effortless for everyday shoppers. Built as a monetizable B2C application, it eliminates the cognitive load of deal-hunting by calculating the absolute best shopping path across top UK supermarkets.

---

# 🚀 Hackathon Submission Dashboard

| Requirement                 | Submission Details                                                 |
| --------------------------- | ------------------------------------------------------------------ |
| **Track**                   | **Track 1: Monetizable B2C App** (Retail & E-commerce Side Hustle) |
| **Designated AWS Database** | **AWS Aurora PostgreSQL**                                          |
| **Published Frontend URL**  | https://smartbasket.vercel.app                                     |
| **Vercel Team ID**          | `team_xxxxxxxxxxxxxxxxxxxx`                                        |
| **Demo Video Link**         | https://youtube.com                                                |

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

# 🛠️ Technical Implementation & Architecture

SmartBasket is organized as a scalable full-stack monorepo designed for low operational cost and high responsiveness.

## Core Stack

### Frontend

* **Next.js (React)**
* Deployed serverlessly on **Vercel**
* Edge delivery for fast page loads

### Backend

* **Python + FastAPI**
* Session state management
* Real-time Server-Sent Events (SSE)
* Shopping optimization engine

### Database

* **AWS Aurora PostgreSQL**
* Product catalogue storage
* Price maps and store relationships
* User basket persistence

---

# 🏗️ Why AWS Aurora PostgreSQL?

SmartBasket handles deeply relational, highly granular data structures. The application must resolve thousands of supermarket variations and category mappings in real time.

AWS Aurora PostgreSQL was selected for:

### 1. Relational Complexity

Efficient multi-table joins allow canonical product identifiers to map seamlessly to store-specific variants.

### 2. Serverless Scale

Aurora automatically scales capacity with demand while minimizing idle costs.

### 3. Low-Latency Aggregations

Background workers evaluate price drops and feed "Today's Best Deals" into the application.

---

# 📊 System Architecture

```text
       ┌─────────────────────────────────────────────────────────┐
       │                 Vercel Edge Deployment                  │
       │  ┌───────────────────────────────────────────────────┐  │
       │  │             Next.js Frontend (v0 UI)              │  │
       │  └─────────────────────────┬─────────────────────────┘  │
       └────────────────────────────┼────────────────────────────┘
                                    │
                       Secure HTTPS │ API Requests
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │                Managed Host Environment                 │
       │  ┌───────────────────────────────────────────────────┐  │
       │  │               FastAPI Backend Engine              │  │
       │  └─────────────────────────┬─────────────────────────┘  │
       └────────────────────────────┼────────────────────────────┘
                                    │
                      IAM Auth Role │ Private VPC Connection
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │                     AWS Cloud Boundary                  │
       │  ┌───────────────────────────────────────────────────┐  │
       │  │              AWS Aurora PostgreSQL                │  │
       │  │  Product Catalogue • Price Map • User Data        │  │
       │  └───────────────────────────────────────────────────┘  │
       └─────────────────────────────────────────────────────────┘
```

---

# 📸 AWS Database Verification Proof

Below is the verified storage deployment profile confirming integration of the live database resource inside the Vercel project ecosystem.

> **Insert screenshot of either:**
>
> * AWS Aurora PostgreSQL Console
> * Vercel Storage Dashboard
> * Database connection configuration

```text
[ Add Screenshot Here ]
```

---

# 🔒 Security Practices

### Zero Exposed Credentials

No raw access keys, database passwords, or cluster connection strings exist within the repository.

### Environment Layering

All secrets are loaded securely using Vercel Environment Variables.

### Minimal Exposure

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

| Layer    | Technology            |
| -------- | --------------------- |
| Frontend | Next.js               |
| Backend  | FastAPI               |
| Database | AWS Aurora PostgreSQL |
| Hosting  | Vercel                |
| Language | TypeScript + Python   |
| Realtime | Server-Sent Events    |
| Cloud    | AWS                   |

---

# 📣 Hackathon Entry Notice

I created this project and its accompanying content for the purposes of entering this hackathon.

**#H0Hackathon**
