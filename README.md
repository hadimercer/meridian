# Meridian — Workstream Portfolio Health Dashboard

> **BA Portfolio Project 3** | Hadi Mercer | February 2026

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Streamlit-4DB6AC?style=flat-square)](https://meridian-hadimercer.streamlit.app)
[![Status](https://img.shields.io/badge/Status-In%20Build-F39C12?style=flat-square)]()

---

## What It Is

Meridian is a workstream health tracking tool for professionals who manage 3–8 concurrent pieces of work — business analysts, consultants, ops leads, HR managers — but don't think of themselves as project managers and won't adopt PM tools built for someone else.

The core idea is simple: **health status is calculated, not declared.** A user never selects a RAG colour. They enter objective data — milestone completions, spend figures, open blockers — and Meridian tells them what the data means. A 9-question context wizard at workstream creation tunes the scoring logic to the nature of the work. A hard-deadline client engagement is scored differently from a self-imposed internal initiative.

---

## The Problem It Solves

The fallback for most professionals managing multi-stream work is a spreadsheet. A spreadsheet that doesn't alert them when a workstream is drifting. One that shows them whatever they last typed, with a RAG column updated when they remember, coloured with optimism bias on a Friday afternoon.

Meridian replaces that spreadsheet with calculated, continuous health signals — and extends it with a collaboration model so contributors update their own areas directly, without bottlenecking status through one person.

---

## Key Features

| Feature | Description |
|---|---|
| **Auto-calculated RAG** | Green / Amber / Red derived from Schedule, Budget, and Blocker health. Never manually selected. |
| **9-question context wizard** | Tunes scoring thresholds at creation. Hard deadlines, client-billable work, and external dependencies all produce tighter scoring profiles. |
| **Three-role collaboration** | Owner, Contributor, Viewer. Open invite link → new users land as Viewer → Owner promotes selectively. |
| **Three-layer communication** | Contextual comment threads, pinned notes, and a structured Updates tab (Decision Made, Risk Raised, etc.) |
| **Staleness detection** | Flags workstreams that haven't been updated within the cadence set in the wizard. |
| **Workstream archive** | Full history preserved, removed from active view when work closes. |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Python / Streamlit |
| Database | PostgreSQL via Supabase |
| Auth | Supabase Auth (email/password) |
| Charts | Plotly (plotly.express) |
| Deployment | Streamlit Community Cloud |

---

## Project Structure

```
meridian/
├── app.py                    # Entry point — routing and session init
├── pages/
│   ├── login.py              # Login and registration
│   ├── dashboard.py          # Portfolio card grid
│   └── workstream.py         # Workstream detail (6-tab view)
├── pipeline/
│   ├── __init__.py
│   ├── db.py                 # Supabase connection helpers
│   ├── auth.py               # Session management and role helpers
│   ├── scoring.py            # RAG scoring engine (core logic)
│   └── invite.py             # Invite link generation and resolution
├── .streamlit/
│   └── config.toml           # Dark theme configuration
├── docs/
│   ├── FRD-MERIDIAN-001.docx # BABOK-aligned Functional Requirements Document
│   ├── UML-MERIDIAN-001.html # UML Class Diagram (data model)
│   ├── BPMN-MERIDIAN-001.html# BPMN Process Diagrams
│   ├── meridian_schema.sql   # PostgreSQL schema (Supabase-ready)
│   └── screenshots/          # Dashboard screenshots
├── requirements.txt
├── .env.example              # Environment variable template
└── README.md
```

---

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/hadimercer/meridian.git
cd meridian
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your Supabase credentials:

```
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DB_HOST=db.your-project-ref.supabase.co
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-db-password
```

> **Where to find these:** Supabase dashboard → Project Settings → API (for URL and keys) and → Database (for DB credentials).

### 5. Set up the database

1. Open your [Supabase project](https://app.supabase.com)
2. Go to **SQL Editor**
3. Paste the contents of `docs/meridian_schema.sql` and run it
4. All 13 tables, triggers, indexes, and RLS policies will be created

### 6. Run the app

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## Deploying to Streamlit Community Cloud

1. Push the repo to GitHub (this repo)
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo
3. Set `app.py` as the entry point
4. Add secrets in the Streamlit Cloud dashboard (**Settings → Secrets**):

```toml
SUPABASE_URL          = "https://your-project-ref.supabase.co"
SUPABASE_ANON_KEY     = "your-anon-key"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
DB_HOST               = "db.your-project-ref.supabase.co"
DB_PORT               = "5432"
DB_NAME               = "postgres"
DB_USER               = "postgres"
DB_PASSWORD           = "your-db-password"
```

> **Important:** Secret key names are case-sensitive and must match exactly. After adding secrets, click **Reboot app**.

---

## BA Documentation

All requirements and design artifacts are in the `docs/` folder:

| Artifact | Document |
|---|---|
| Functional Requirements Document | `FRD-MERIDIAN-001.docx` — BABOK v3 aligned, 8 sections, 35 FRs, 10 NFRs |
| UML Class Diagram | `UML-MERIDIAN-001.html` — 12 entities with relationships and design decisions |
| BPMN Diagrams | `BPMN-MERIDIAN-001.html` — Workstream lifecycle + invite sub-process |
| Database Schema | `meridian_schema.sql` — 13 tables, 32 RLS policies, 6 triggers |

---

## RAG Scoring Logic (summary)

Health status is a weighted composite of three dimensions:

| Dimension | Input | Default Weight |
|---|---|---|
| Schedule Health | Milestone completion % vs time elapsed % | 40% |
| Budget Health | Actual spend vs planned spend to date | 35% |
| Blocker Health | Open blocker count and age in days | 25% |

Composite score ≥ 70 = 🟢 Green &nbsp;|&nbsp; 40–69 = 🟡 Amber &nbsp;|&nbsp; < 40 = 🔴 Red

The 9-question wizard adjusts thresholds and weights per workstream. Full logic documented in FRD Section 5.

---

## Screenshots

*Coming soon — dashboard and workstream detail screenshots will be added after deployment.*

---

## Portfolio Context

This project is part of a 6-project BA career transition portfolio demonstrating end-to-end business analysis capability — from requirements elicitation and documentation through to technical implementation and deployment.

**Portfolio:** [github.com/hadimercer](https://github.com/hadimercer)
**S2 (live):** [Comp & Benchmarking Dashboard](https://comp-benchmarking-hadimercer-ps2.streamlit.app/)

---

*Built with Python, Streamlit, and Supabase. Documented to BABOK v3 standard.*
