# PriceRadar — Chilean Auto Insurance Monitor

A self-contained price-intelligence system that ingests scraped insurance quotes, computes analytics tables in two processing layers (stream and batch), fires configurable alerts, and presents everything in a single-file dashboard. No database or server required for local use.

Friendly guide to the generated tables: [`DATA_TABLE_GUIDE.md`](DATA_TABLE_GUIDE.md)  
HTML docs viewer for the repo markdown files: `python build_docs.py` then open [`docs.html`](docs.html)  
LLM insight layer architecture: [`LLM_LAYER.md`](LLM_LAYER.md)

---

## Table of contents

1. [Architecture overview](#1-architecture-overview)
2. [Quick start](#2-quick-start)
3. [Data flow: pipeline.py](#3-data-flow-pipelinepy)
4. [Alert dispatch: notifications.py](#4-alert-dispatch-notificationspy)
5. [Dashboard](#5-dashboard)
6. [Output table reference](#6-output-table-reference)
7. [Configuration reference](#7-configuration-reference)
8. [Production path](#8-production-path)

---

## 1. Architecture overview

```
data/quotes_collapsed.csv          (raw scrape output — one row per insurer per run)
           │
           ▼
      pipeline.py
           │
     ┌─────┴──────────────────────────────────────────────────┐
     │  Stream layer (event-by-event)                         │
     │    scrape_runs.csv          — one row per scraping job  │
     │    price_changes.csv        — every price delta         │
     │    snapshot_rankings.csv    — per-run insurer ranking   │
     │    alert_events.csv         — fired alert records       │
     │    market_floor_events.csv  — snapshot floor events     │
     │                                                         │
     │  Batch layer (aggregated)                              │
     │    kpi_win_rates.csv        — 1d / 7d / 30d win rates  │
     │    kpi_price_stats.csv      — mean/median/CV per day    │
     │    kpi_presence_rate.csv    — insurer availability %    │
     │    kpi_market_floor.csv     — daily floor & ceiling     │
     └─────────────────────────────────────────────────────────┘
           │
           ▼
   notifications.py              (reads alert_events.csv, dispatches log / Slack / email)
           │
           ▼
     dashboard.html              (self-contained; data embedded as JS constants)
```

**Portals tracked:** Falabella, Santander  
**Period:** August 2025 (one month of 30-minute scrapes → ~2,845 snapshots)  
**Insurers:** 11 across both portals

---

## 2. Quick start

### Requirements

Python 3.10+, pandas, numpy — nothing else.

```bash
pip install pandas numpy
```

### Run the pipeline

```bash
python pipeline.py
```

Reads `data/quotes_collapsed.csv`, writes all nine tables to `output/`.  
Runtime: ~15 seconds on one month of data.

### Open the dashboard

```bash
# macOS
open dashboard.html

# Linux
xdg-open dashboard.html

# Windows — double-click or:
start dashboard.html
```

No server needed. All data is embedded in the HTML file as inline JavaScript constants.

### Run notifications

```bash
python notifications.py                   # check unacked alerts, print to terminal
python notifications.py --channel slack   # POST to Slack webhook
python notifications.py --channel email   # send via SMTP/Gmail
python notifications.py --test            # fire a synthetic test alert
```

### Generate LLM insights (optional)

The LLM layer requires `anthropic` and a valid `ANTHROPIC_API_KEY`. Set `llm.enabled: true` in `config.json` first.

```bash
# Generate today's daily market briefing (appears in the dashboard)
python llm_briefing.py

# Backfill LLM context paragraphs for all critical alerts (appended to Slack)
python llm_enrichment.py

# Test the full pipeline without API credits (writes canned placeholder text)
python llm_briefing.py --stub
python llm_enrichment.py --stub
python build_dashboard.py                 # embeds stub content — zero API calls
```

See [`LLM_LAYER.md`](LLM_LAYER.md) for the full architecture contract (separation rules, failure semantics, scheduling).

---

## 3. Data flow: pipeline.py

### Step 0 — Load & normalize

Reads `data/quotes_collapsed.csv`. Columns used:

| Raw column | Normalized as | Notes |
|---|---|---|
| `Portal` | `portal` | stripped |
| `name` | `insurer` | stripped |
| `updated_at` | `scraped_at` | parsed to datetime |
| `effective_price` | `price` | rows with null price are dropped |
| `plan_type` | `plan_type` | stripped |

A synthetic `run_id` (integer, 1-based) is assigned to every unique `(portal, scraped_at)` pair so downstream steps can group by scraping job without carrying a full timestamp.

---

### Step 1 — `scrape_runs.csv` (stream)

One row per `(run_id, portal, scraped_at)`. Aggregates the number of insurers returned and total rows for that run. All runs are marked `status = success` (failure detection would require a separate scraper heartbeat).

**Columns:** `run_id`, `portal`, `scraped_at`, `insurers_returned`, `rows`, `status`

---

### Step 2 — `price_changes.csv` (stream)

For each `(portal, insurer)` pair, compares each row's price to the immediately preceding row's price (ordered by `scraped_at`). Only rows where the price actually changed are kept.

**Severity thresholds:**

| Level | Condition |
|---|---|
| `critical` | `|pct_change| ≥ 30%` |
| `warning` | `10% ≤ |pct_change| < 30%` |
| `info` | `|pct_change| < 10%` |

**Columns:** `change_id`, `run_id`, `portal`, `insurer`, `scraped_at`, `prev_scraped_at`, `prev_price`, `price`, `abs_change`, `pct_change`, `direction` (up/down), `severity`

---

### Step 3 — `snapshot_rankings.csv` (stream)

For each `(run_id, portal)` snapshot, all insurers are ranked by price ascending (rank 1 = cheapest). Also computes the absolute and percentage gap to the cheapest insurer in that snapshot.

**Columns:** `run_id`, `portal`, `insurer`, `scraped_at`, `plan_type`, `price`, `price_rank`, `is_cheapest`, `gap_to_min`, `gap_to_min_pct`, `min_price`, `max_price`, `n_insurers`

---

### Step 4 — `alert_events.csv` (stream)

Three alert types are generated from the upstream tables:

| alert_type | Source | Condition | Severity |
|---|---|---|---|
| `price_spike` | price_changes | `pct_change ≥ +30%` | critical |
| `price_drop` | price_changes | `pct_change ≤ −30%` | critical |
| `price_move` | price_changes | `10% ≤ |pct_change| < 30%` | warning |
| `market_floor_drop` | snapshot_rankings | market floor drops `≥ 20%` in one snapshot | critical |

Every alert record carries: `alert_id`, `alert_type`, `severity`, `portal`, `insurer` (`ALL` for floor drops), `fired_at`, `run_id`, `value` (the triggering % change), `threshold`, `detail` (human-readable string), `acknowledged` (default `False`).

---

### Step 5 — `kpi_win_rates.csv` (batch)

Win = cheapest insurer in a snapshot (`is_cheapest == 1`). Computed at three time windows:

| `window` | Logic |
|---|---|
| `1d` | wins and appearances on that calendar day |
| `7d` | rolling 7-day window ending on each date |
| `30d` | whole dataset (one row per portal/insurer, date = last day) |

**Columns:** `date`, `portal`, `insurer`, `window`, `wins`, `appearances`, `win_rate`

---

### Step 6 — `kpi_price_stats.csv` (batch)

Daily descriptive statistics per `(portal, insurer)`.

**Columns:** `date`, `portal`, `insurer`, `mean`, `median`, `std`, `p10`, `p90`, `min_price`, `max_price`, `n_obs`, `cv` (coefficient of variation = std/mean × 100)

---

### Step 7 — `kpi_presence_rate.csv` (batch)

Measures how often each insurer appeared across the day's scraping runs. Presence below 80% is flagged (`below_threshold = True`), which may indicate scraping gaps or insurer-side availability issues.

**Columns:** `date`, `portal`, `insurer`, `runs_present`, `runs_total`, `presence_pct`, `below_threshold`

---

### Step 8 — `kpi_market_floor.csv` (batch)

Daily average of the market floor (cheapest insurer) and ceiling (most expensive insurer) per portal. Day-over-day % change of the floor is computed; moves ≥ 20% are flagged as `is_market_event`.

**Columns:** `date`, `portal`, `floor_price`, `ceiling_price`, `n_snapshots`, `floor_delta_pct`, `is_market_event`

---

### Step 8b — `market_floor_events.csv` (stream)

Same floor-drop logic as `kpi_market_floor`, but computed at **snapshot granularity** rather than daily averages. This catches intra-day floor moves that averaging would obscure. Only rows where `|floor_pct_chg| ≥ 20%` are written.

**Columns:** `portal`, `scraped_at`, `run_id`, `min_price`, `prev_floor`, `floor_pct_chg`, `is_event`

---

## 4. Alert dispatch: notifications.py

Runs after each pipeline execution. Reads `output/alert_events.csv` and dispatches unacknowledged alerts that meet the configured minimum severity.

### Dispatch channels

| Channel | Behavior |
|---|---|
| `log` (default) | Prints formatted text to stdout |
| `slack` | HTTP POST to the configured webhook URL; falls back to `log` on failure |
| `email` | SMTP via Gmail (port 587, STARTTLS); falls back to `log` on failure |

### Deduplication

State is persisted in `output/notification_state.json`. An alert is suppressed if an alert with the same `(alert_type, portal, insurer)` key was dispatched within the last `dedup_window_minutes` (default 60). Entries older than 24 hours are automatically pruned from the state file.

### Severity filter

Only alerts at or above `min_severity` are dispatched:

```
info (0) < warning (1) < critical (2)
```

Default `min_severity` is `warning`, so `info`-level changes are silenced unless the config is changed.

### CLI flags

```
--test             Send a synthetic critical alert to verify the channel works
--channel <name>   Override the channel set in config.json for this run
```

---

## 5. Dashboard

`dashboard.html` is a single self-contained file. All output table data is embedded as inline JavaScript constants at the bottom of the file — no HTTP requests at runtime. Rendered with Chart.js (loaded from CDN on first open).

### Tabs

| Tab | Contents |
|---|---|
| **Overview** | Month-level KPI tiles (snapshots, portals, insurers, change events, critical alerts); 30d win-rate bar charts for each portal; market floor & ceiling line chart with portal selector |
| **Competitive** | Per-snapshot win-rate bars filtered by portal; scatter/bar chart of current price spread across insurers |
| **Price trends** | Line chart of absolute prices over time; filter by portal and insurer |
| **Repricing timing** | Two heatmaps: (1) changes by hour-of-day × insurer; (2) changes by day-of-week × insurer — reveals when each insurer reprices |
| **Volatility** | CV (coefficient of variation) bar chart; p10–p90 price range bands per insurer; filter by portal |
| **Alerts** | Scrollable alert feed with filters for severity, portal, insurer, and alert type; badge in nav tab shows count of unacknowledged alerts |
| **Raw tables** | Pageable views of all output tables (alert events, price changes, snapshot rankings, presence rate, volatility); filter by portal |

---

## 6. Output table reference

| File | Layer | Rows (Aug 2025) | Description |
|---|---|---|---|
| `scrape_runs.csv` | Stream | ~2,845 | One row per scraping job |
| `price_changes.csv` | Stream | ~1,305 | Every price delta with severity |
| `snapshot_rankings.csv` | Stream | ~28,000 | Every insurer ranked per snapshot |
| `alert_events.csv` | Stream | varies | Fired alert records |
| `market_floor_events.csv` | Stream | small | Snapshot-level floor moves ≥ 20% |
| `kpi_win_rates.csv` | Batch | ~3,000 | Win rate per insurer/portal at 1d/7d/30d |
| `kpi_price_stats.csv` | Batch | ~600 | Mean/median/std/CV per insurer/portal/day |
| `kpi_presence_rate.csv` | Batch | ~600 | % of snapshots each insurer appeared in |
| `kpi_market_floor.csv` | Batch | ~62 | Daily floor & ceiling per portal |

---

## 7. Configuration reference

`config.json` is merged over the built-in defaults at startup. Only keys you want to override need to be present.

```jsonc
{
  "channel": "log",               // "log" | "slack" | "email"
  "slack_webhook_url": "",        // paste your https://hooks.slack.com/... URL

  "email": {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "from_addr": "you@gmail.com",
    "to_addrs": ["team@yourcompany.com"],
    "password_env": "EMAIL_PASSWORD"  // name of the env var holding the SMTP password
  },

  "dedup_window_minutes": 60,     // suppress duplicate alerts within this window
  "min_severity": "warning",      // "info" | "warning" | "critical"

  "thresholds": {
    "price_spike_pct": 30,        // alert threshold (mirrored from pipeline logic)
    "price_drop_pct": -30,
    "market_floor_drop_pct": -20,
    "presence_warning_pct": 80
  }
}
```

> Note: thresholds in `config.json` are **reference values** for the notification layer. The actual alert-firing logic lives in `pipeline.py` — changing config.json does not recompute `alert_events.csv`. Re-run `pipeline.py` after changing thresholds.

---

## 8. Production path

| Concern | Local (current) | Production |
|---|---|---|
| Input | `data/quotes_collapsed.csv` | Postgres `COPY` or DuckDB, triggered post-scrape |
| Pipeline execution | `python pipeline.py` manually | Cron job or post-scrape webhook |
| Notifications | `python notifications.py` manually | Daemon, Lambda, or scheduled task after each pipeline run |
| Dashboard data | Embedded JSON in HTML | `/api/kpis` endpoint; dashboard fetches on load |
| Alert acknowledgement | Edit CSV by hand | API endpoint that flips `acknowledged = true` in DB |
