# SmartBasket Frontend 💻

The user-facing client interface for SmartBasket, designed to help users optimize grocery lists, visualize spending trends, and discover multi-store shopping combinations that maximize savings.

## 🛠️ Tech Stack

* **Framework:** Next.js (App Router)
* **Language:** TypeScript
* **Styling & Components:** Tailwind CSS, Shadcn UI, Radix Primitives
* **Data Visualizations:** Recharts (Area Charts & Stacked Bar Charts)
* **Icons:** Lucide React

---

# 🚀 Local Quickstart Guide

## 1. Prerequisites

Ensure you have the following installed:

* **Node.js** (v18.0.0 or higher)
* A running **SmartBasket Backend** instance available on port `8000`

---

## 2. Environment Configuration

Create a `.env.local` file in the project root:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 3. Install Dependencies

Install packages using your preferred package manager:

### npm

```bash
npm install
```

### pnpm

```bash
pnpm install
```

### yarn

```bash
yarn install
```

---

## 4. Start the Development Server

Launch the Next.js development environment:

### npm

```bash
npm run dev
```

### pnpm

```bash
pnpm dev
```

### yarn

```bash
yarn dev
```

Open your browser and navigate to:

* **Application:** `http://localhost:3000`

---

## Features

* 📋 Build and manage grocery lists
* 📈 Visualize historical spending patterns
* 🛒 Compare prices across multiple supermarkets
* 💰 Discover optimal store combinations for maximum savings
* 📊 Interactive charts powered by Recharts
* 🎨 Responsive UI built with Tailwind CSS and Shadcn UI

---

## Development Stack

* **Next.js App Router** for server and client components
* **TypeScript** for type safety
* **Tailwind CSS** for utility-first styling
* **Shadcn UI + Radix** for accessible components
* **Recharts** for interactive analytics
* **Lucide React** for iconography
