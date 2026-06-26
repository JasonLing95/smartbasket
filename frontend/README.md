# SmartBasket Frontend 💻

The user-facing client interface for SmartBasket, designed to help users optimize grocery lists, visualize spending trends, and discover multi-store shopping combinations that maximize savings.

This application is built with **Next.js (App Router)** and optimized for **Vercel Edge Deployment** to ensure ultra-low latency rendering.

## 🛠️ Tech Stack & UI Architecture

* **Framework:** Next.js (App Router)
* **Language:** TypeScript
* **Styling & Components:** Tailwind CSS, Shadcn UI, Radix Primitives
* **Data Visualizations:** Recharts (Area Charts & Stacked Bar Charts)
* **Icons:** Lucide React

### Advanced UX Implementations

To meet the rigorous demands of a modern B2C application, this frontend implements several advanced client-side patterns:

* **Client-Side Image Compression:** Utilizes `browser-image-compression` to resize and compress receipt images to under 1MB in the browser, drastically reducing upload latency and backend AWS bandwidth costs.
* **Non-Blocking Asynchronous Scanner:** Receipt processing is fully decoupled. The UI features a background polling mechanism (`setInterval` checking the `status` endpoint) that allows users to minimize the scanning animation and continue navigating the app while the backend EC2 worker parses the image.
* **Real-Time Price Streams:** Leverages Server-Sent Events (`EventSource`) to maintain an open connection with the FastAPI backend, pushing live price-drop alerts directly to the user's dashboard without requiring a page refresh.
* **Mobile-First Design:** Features a responsive layout with a dedicated fixed bottom navigation bar (`pb-safe`) for iOS and Android web-app experiences.

---

# 🚀 Local Quickstart Guide

## 1. Prerequisites

Ensure you have the following installed:

* **Node.js** (v18.0.0 or higher)
* A running **SmartBasket Backend** instance available on port `8000`

---

## 2. Environment Configuration

Create a `.env.local` file in the project root to link the client to your API:

```env
# Point this to your FastAPI backend (Local or Vercel Edge API)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 3. Install Dependencies

Install packages using your preferred package manager:

```bash
npm install

# or

pnpm install

# or

yarn install
```

## 4. Start the Development Server

Launch the Next.js development environment:

```bash
npm run dev

# or

pnpm dev

# or

yarn dev
```

Open your browser and navigate to:

```text
http://localhost:3000
```

---

# ✨ Core Features

* 📋 **Dynamic Shopping Plans:** Instantly toggle between **Split Trip** savings calculations and **Single Store** comparisons.
* 📈 **Interactive Dashboards:** Visualize historical spending patterns with Recharts.
* 🛒 **Cross-Store Catalog:** Search and compare granular price differences across multiple UK supermarkets.
* 🔔 **Live Alerts:** Receive instant notifications when a basket item drops in price.
* 📱 **Seamless Auth:** JWT-based bearer token authentication with secure local storage caching.
