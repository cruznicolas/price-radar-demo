# PriceRadar — Full Technical Documentation

**Repository:** `price_radar_demo`  
**Domain:** Chilean auto insurance market intelligence  
**Period covered by demo data:** August 2025  
**Audiences:** Technical engineers (systems / operations) and developers inheriting or extending the codebase.

---

## Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [System Architecture](#2-system-architecture)
3. [End-to-End Data Flow](#3-end-to-end-data-flow)
4. [Functional Logic by Module](#4-functional-logic-by-module)
5. [Important Functions and Classes](#5-important-functions-and-classes)
6. [Configuration and Environment](#6-configuration-and-environment)
7. [Business Logic Rules](#7-business-logic-rules)
8. [UI Logic](#8-ui-logic)
9. [Execution Lifecycle](#9-execution-lifecycle)
10. [Technical Risks and Weak Points](#10-technical-risks-and-weak-points)
11. [Extension Guide](#11-extension-guide)
12. [Plain Language Summary](#12-plain-language-summary)
13. [LLM Insight Layer](#13-llm-insight-layer)

---

## 1. Executive Overview

### What this repository does

PriceRadar is a price intelligence system for the Chilean auto insurance market. It ingests raw quote data scraped from two insurance comparison portals (Falabella and Santander), processes that data through two analytical layers (stream and batch), fires configurable alerts when prices change materially, and presents all findings in a self-contained web dashboard.

### Business purpose

Insurance prices on comparison portals change frequently — sometimes hourly — and the cheapest insurer on one portal may not be cheapest on another. An analyst or product team needs to answer questions like: Who is winning on price? When do insurers reprice? How volatile is each insurer? When did the market floor collapse? PriceRadar makes all of this immediately visible without requiring a database, a server, or a data analyst writing ad-hoc queries.

### Technical purpose

The system is a demonstration-grade ETL pipeline. Raw scraped quotes → normalized event streams → aggregated KPI tables → static dashboard. It is intentionally self-contained: Python, pandas, a single HTML file. No infrastructure is required to run it locally. The architecture mirrors production patterns (stream layer + batch layer + alerting) without requiring production infrastructure.

### Problem it solves

| Pain point | Solution |
|---|---|
| Prices change continuously; no one tracks all changes | `pipeline.py` detects and records every price delta with severity classification |
| Manual price comparisons are a snapshot in time | `snapshot_rankings.csv` captures who was cheapest in every scraping run |
| Large price moves go unnoticed | `alert_events.csv` + `notifications.py` fire structured alerts with deduplication |
| Win-rate and volatility patterns are invisible | `kpi_win_rates.csv`, `kpi_price_stats.csv` compute them across 1d/7d/30d windows |
| Analysis requires a database or BI tool | `dashboard.html` is a standalone file with all data embedded |

### Scale of demo data

| Metric | Value |
|---|---|
| Raw input rows | 20,418 |
| Portals | 2 (Falabella, Santander) |
| Insurers | 11 |
| Scraping runs | 2,845 (~30-min cadence, August 2025) |
| Price change events | 1,305 |
| Alerts fired | 284 (48 critical, 236 warning) |
| Total output rows across all tables | ~26,800 |

---

## 2. System Architecture

### File tree

```
price_radar_demo/
│
├── data/
│   └── quotes_collapsed.csv        ← INPUT: raw scrape output
│
├── output/                         ← GENERATED: all pipeline outputs
│   ├── scrape_runs.csv
│   ├── price_changes.csv
│   ├── snapshot_rankings.csv
│   ├── alert_events.csv
│   ├── market_floor_events.csv
│   ├── kpi_win_rates.csv
│   ├── kpi_price_stats.csv
│   ├── kpi_presence_rate.csv
│   ├── kpi_market_floor.csv
│   ├── kpi_volatility_summary.csv
│   ├── kpi_presence_summary.csv
│   ├── kpi_hourly_changes.csv
│   ├── kpi_dow_changes.csv
│   └── notification_state.json     ← GENERATED: dedup state (created at runtime)
│
├── pipeline.py                     ← ETL engine: produces all 13 output tables
├── build_dashboard.py              ← Reads output/ CSVs, rewrites data block in dashboard.html
├── notifications.py                ← Alert dispatcher: reads alert_events.csv
├── config.json                     ← Runtime config for notifications.py
└── dashboard.html                  ← Self-contained dashboard (data embedded inline)
```

### Responsibility of each file

| File | Role | Reads | Writes |
|---|---|---|---|
| `data/quotes_collapsed.csv` | Raw input. One row per insurer per scraping run. | — | — |
| `pipeline.py` | Full ETL. Transforms raw data into all nine analytics tables. | `data/quotes_collapsed.csv` | `output/*.csv` |
| `notifications.py` | Alert dispatch. Reads alerts, deduplicates, dispatches to configured channel. | `output/alert_events.csv`, `output/notification_state.json`, `config.json` | `output/notification_state.json` |
| `config.json` | Static configuration for `notifications.py`. | — | — |
| `dashboard.html` | Self-contained visualization. All data is embedded as JS constants. | Nothing at runtime | Nothing at runtime |
| `output/notification_state.json` | Deduplication state. Tracks what was sent and when. | Read by `notifications.py` | Written by `notifications.py` |

### Dependency graph

```
quotes_collapsed.csv
        │
        ▼
  pipeline.py
        │
   ┌────┴─────────────────────────────────────────────────────────┐
   │                                                              │
   ▼                                                              ▼
scrape_runs.csv           snapshot_rankings.csv
        │                           │
        │                     ┌─────┤
        │                     │     │
        ▼                     ▼     ▼
  presence_rate         kpi_market_floor    price_changes.csv
        │                market_floor_events        │
        │                                     ┌─────┤
        │                                     │     │
        ▼                                     ▼     ▼
  (no further deps)               alert_events.csv  kpi_win_rates.csv
                                       │             kpi_price_stats.csv
                                       ▼
                               notifications.py
                                       │
                         ┌─────────────┼──────────────┐
                         ▼             ▼               ▼
                      stdout       Slack API       SMTP server
```

**Dashboard is a separate branch:** `dashboard.html` is not generated by `pipeline.py`. The data it contains must be manually embedded (or scripted) after the pipeline runs. It reads no files at runtime.

### Implicit pipeline sequencing within pipeline.py

```
Step 0: normalize raw                    → df (in-memory DataFrame)
Step 1: scrape_runs.csv                  ← df
Step 2: price_changes.csv                ← df (sorted by portal/insurer/time)
Step 3: snapshot_rankings.csv            ← df
Step 4: alert_events.csv                 ← price_changes + snapshot_rankings (in-memory)
Step 5: kpi_win_rates.csv                ← snapshot_rankings
Step 6: kpi_price_stats.csv              ← snapshot_rankings
Step 7: kpi_presence_rate.csv            ← snapshot_rankings + scrape_runs
Step 8: kpi_market_floor.csv             ← snapshot_rankings
Step 8b: market_floor_events.csv         ← snapshot_rankings
```

All steps execute sequentially in a single Python process. There is no parallelism and no checkpointing. If any step raises an exception, subsequent output files will not be written.

---

## 3. End-to-End Data Flow

### Input schema

`data/quotes_collapsed.csv` — five columns:

| Column | Type | Example | Notes |
|---|---|---|---|
| `Portal` | string | `Falabella` | Name of the comparison portal |
| `updated_at` | datetime string | `2025-08-01 02:00:02` | Timestamp of the scraping run |
| `name` | string | `Cardif` | Insurer name as returned by the portal |
| `plan_type` | string | `Full Cobertura` | Insurance plan tier |
| `effective_price` | float | `34510.0` | Monthly premium in Chilean pesos (CLP) |

One row represents: at time `updated_at`, portal `Portal` listed insurer `name` for plan `plan_type` at price `effective_price`.

### Step-by-step transformation

**Phase 1 — Normalization (lines 11–23)**

```
raw CSV
  → strip whitespace from portal, insurer, plan_type
  → parse updated_at → scraped_at (datetime)
  → rename effective_price → price
  → drop rows where price is null
  → sort by (portal, insurer, scraped_at)
  → assign synthetic run_id: integer per unique (portal, scraped_at) pair
```

The run_id assignment is a `range(1, N+1)` applied after `drop_duplicates()` on `(portal, scraped_at)`. This means run_ids are stable within a single pipeline execution but are not meaningful across re-runs if input data changes.

**Phase 2 — Scrape run catalog (lines 28–35)**

Groups normalized data by `(run_id, portal, scraped_at)`. Counts distinct insurers and total rows per run. All runs are stamped `status = success`; there is no mechanism for recording partial or failed runs.

**Phase 3 — Price change detection (lines 38–70)**

For each `(portal, insurer)` pair, the data is processed as a time series. `pandas.shift(1)` retrieves the previous row's price within the group. Rows where `price == prev_price` are discarded. Only actual changes are kept.

Three derived columns:
- `abs_change = price - prev_price` (signed, CLP)
- `pct_change = (price - prev_price) / prev_price × 100` (signed, %)
- `direction = 'up' if pct_change > 0 else 'down'`
- `severity`: see Section 7 for exact thresholds

**Phase 4 — Snapshot rankings (lines 73–88)**

Within each `(run_id, portal)` group, insurers are ranked by price ascending using `pandas.rank(method='min', ascending=True)`. Ties receive the same rank. `is_cheapest = 1` for rank == 1. The gap to the cheapest price is computed both in absolute CLP and as a percentage.

**Phase 5 — Alert generation (lines 91–148)**

Three sub-processes build the alert table:

1. **Individual price spikes/drops**: iterates `price_changes` where `severity == 'critical'`. For each row, one alert record is created. `alert_type` is `price_spike` if direction is up, `price_drop` if down.

2. **Price warnings**: iterates `price_changes` where `severity == 'warning'`. One alert per row, `alert_type = price_move`.

3. **Market floor drops**: groups `snapshot_rankings` by `(portal, run_id, scraped_at)` to extract the minimum price per snapshot, sorts by `(portal, scraped_at)`, shifts to get the previous snapshot's floor, computes percentage change. Snapshots where `floor_pct_change <= -20` trigger a `market_floor_drop` alert with `insurer = 'ALL'`.

All three lists are concatenated into a single DataFrame. `alert_id` is a 1-based integer index assigned after concatenation. `acknowledged` is always `False` (no write-back mechanism exists in this codebase).

**Phase 6 — KPI: Win rates (lines 154–195)**

Daily win rate: straight `groupby` aggregation of `is_cheapest` (sum = wins, count = appearances).

7-day rolling: a Python loop over all calendar dates. For each date `d`, filters `snapshot_rankings` to the 7-day window `[d-6, d]` and aggregates. This is O(days × insurers × rows_per_window) — computationally heavier than needed but correct.

30-day: a single `groupby` over the entire dataset per `(portal, insurer)`. The date assigned is `max(all_dates)` — i.e., the last day of the dataset, not a true rolling window.

**Phase 7 — KPI: Price statistics (lines 198–215)**

Groups `snapshot_rankings` by `(date, portal, insurer)`. Applies multiple aggregation functions to `price` in one pass: mean, median, std, p10, p90, min, max, count. Coefficient of variation (CV) is computed as `std / mean × 100` after the aggregation.

**Phase 8 — KPI: Presence rate (lines 218–226)**

Joins the count of snapshots each insurer appeared in per day (`snapshot_rankings` grouped by date/portal/insurer) against the count of scraping runs per day (`scrape_runs`). Presence percentage = runs_present / runs_total × 100. `below_threshold = True` if presence_pct < 80.

**Phase 9 — KPI: Market floor, daily (lines 229–246)**

Groups `snapshot_rankings` by `(date, portal)`. Averages `min_price` (floor) and `max_price` (ceiling) across all runs in that day. Day-over-day floor change is computed with `shift(1)` within each portal group. Moves ≥ 20% (absolute) are flagged `is_market_event = True`.

**Phase 10 — Market floor events, snapshot-level (lines 252–264)**

Same logic as Phase 9, but computed on individual snapshots rather than daily averages. Groups `snapshot_rankings` by `(portal, scraped_at, run_id)`, takes the minimum price per snapshot, then shifts to compare consecutive snapshots. Events where `|floor_pct_chg| ≥ 20%` are written to `market_floor_events.csv`. This is the more accurate representation for detecting intra-day events.

### Decision points

| Location | Decision | Consequence |
|---|---|---|
| Step 0, line 17 | `dropna(subset=['price'])` | Rows with null `effective_price` are silently discarded |
| Step 2, lines 43–46 | `price != prev_price` filter | Only actual changes produce a `price_changes` row |
| Step 4, `severity()` function | 30% / 10% thresholds | Determines whether an event becomes an alert |
| Step 4, line 130 | `floor_pct_change <= -20` | Only floor *drops* ≥ 20% trigger a market alert; rises do not |
| Step 5, line 193 | `concat` of daily + 7d + 30d | `kpi_win_rates` is a single heterogeneous table with a `window` discriminator column |

---

## 4. Functional Logic by Module

### 4.1 `pipeline.py`

**Purpose:** The sole data transformation engine. Converts raw CSV input into nine analytics output files.

**Why it exists:** Centralizes all business logic for price analysis. Keeps the scraper (not part of this repo) separate from analysis. Everything downstream (dashboard, notifications) consumes the output files rather than the raw input.

**Inputs:**
- `data/quotes_collapsed.csv` — 5-column raw scrape file

**Outputs:**
- `output/scrape_runs.csv`
- `output/price_changes.csv`
- `output/snapshot_rankings.csv`
- `output/alert_events.csv`
- `output/market_floor_events.csv`
- `output/kpi_win_rates.csv`
- `output/kpi_price_stats.csv`
- `output/kpi_presence_rate.csv`
- `output/kpi_market_floor.csv`

**Internal logic summary:** Single linear Python script. No functions, no classes. Executes top to bottom. Uses pandas for all transformations. Intermediate DataFrames are kept in memory and reused by downstream steps. All output is written to CSV via `to_csv()`.

**Runtime dependencies:** `pandas`, `numpy`. Standard library: `datetime`, `json`, `os`.

---

### 4.2 `notifications.py`

**Purpose:** Alert dispatch module. Reads `alert_events.csv` after each pipeline run, filters and deduplicates alerts, and dispatches them to the configured channel.

**Why it exists:** Decoupled from the pipeline so it can be run independently, scheduled differently, or run multiple times without re-running the ETL. Also handles channels (Slack/email) that have no natural place in `pipeline.py`.

**Inputs:**
- `output/alert_events.csv` — all pipeline-generated alerts
- `output/notification_state.json` — deduplication state (created on first run)
- `config.json` — channel and threshold configuration

**Outputs:**
- Stdout (log channel)
- HTTP POST to Slack webhook (slack channel)
- SMTP email (email channel)
- Updated `output/notification_state.json`

**Internal logic summary:**
1. Load config (merge `config.json` over defaults)
2. Load dedup state from `notification_state.json`
3. Read all alert rows from CSV
4. Filter to unacknowledged + meets min_severity
5. For each alert, check dedup window; if not duplicate, dispatch and record
6. Prune dedup state entries older than 24 hours
7. Save updated state

**Runtime dependencies:** `os`, `json`, `csv`, `smtplib`, `sys`, `argparse`, `datetime`, `email.mime.text`, `pathlib`. For Slack: `urllib.request` (stdlib). No external packages.

---

### 4.3 `dashboard.html`

**Purpose:** Self-contained visualization of all pipeline outputs. Requires no server, no database, no internet connection after first load (Chart.js is loaded from CDN on first open).

**Why it exists:** Zero-deployment reporting. The entire analytical output can be shared as a single file attachment or opened directly from disk.

**Inputs:** None at runtime. All data is embedded in the `<script>` block as JavaScript constants.

**Outputs:** Rendered charts, tables, and alert feeds in the browser.

**Internal logic summary:** On page load, an IIFE initializes dynamic filter dropdowns (insurer list, alert type list), counts critical alerts for the badge, and renders the Overview tab. Each tab is a `<div class="page">` hidden by default; clicking a nav tab calls `nav()` which switches visibility and calls the tab's render function. Chart.js instances are tracked in a global `charts` object and destroyed before re-creation to prevent canvas memory leaks.

---

## 5. Important Functions and Classes

### `pipeline.py` — No named functions except `severity()`

---

#### `severity(pct)`

**Location:** `pipeline.py`, line 53  
**Purpose:** Classifies a percentage price change into a severity tier.  
**Parameters:** `pct` — float, the signed percentage change  
**Returns:** string — `'critical'`, `'warning'`, or `'info'`

**Logic:**
```
if |pct| >= 30 → 'critical'
if |pct| >= 10 → 'warning'
else           → 'info'
```

**Technical note:** Applied via `pandas.Series.apply()` which calls it row-by-row. This function is the sole source of severity classification for `price_changes.csv` and therefore controls which rows feed into alert generation. The function operates on the absolute value of `pct` to handle both spikes and drops with one ladder. There is no `'info'`-level alert generated — `info` rows are only in `price_changes.csv`, not `alert_events.csv`.

---

### `notifications.py`

---

#### `load_config()`

**Location:** `notifications.py`, line 46  
**Purpose:** Loads `config.json` and merges it over `DEFAULT_CONFIG`.  
**Parameters:** None  
**Returns:** dict — merged configuration  

**Logic:** `{**DEFAULT_CONFIG, **json.load(f)}` — shallow merge. Top-level keys in `config.json` override defaults; nested objects (e.g., `email`) are replaced entirely, not merged. If `config.json` is absent, returns `DEFAULT_CONFIG` unchanged.

**Technical note:** Because the merge is shallow, if you provide a partial `email` dict in `config.json` (e.g., only `to_addrs`), all other email keys will be lost unless they are also present in your file.

---

#### `load_state()` / `save_state(state)`

**Location:** `notifications.py`, lines 53–61  
**Purpose:** Persist deduplication state to disk between runs.  
**Format:** `{"sent": [{"key": str, "sent_at": ISO8601, "alert_id": int}, ...]}` 

**Logic:** `load_state` returns `{"sent": []}` if the file does not exist (first run). `save_state` serializes the entire state dict as JSON with `indent=2`.

---

#### `dedup_key(alert)`

**Location:** `notifications.py`, line 63  
**Purpose:** Produces the deduplication identifier for an alert.  
**Returns:** string — `"{alert_type}|{portal}|{insurer}"`

**Technical note:** The key does NOT include `severity` or `value`. A `warning` and a `critical` for the same alert_type/portal/insurer will share a key and will deduplicate against each other within the window. This means if a warning is sent first and a critical fires within 60 minutes for the same insurer, the critical will be suppressed.

---

#### `is_duplicate(alert, state, window_minutes)`

**Location:** `notifications.py`, line 66  
**Purpose:** Checks whether an equivalent alert was dispatched within the dedup window.  
**Returns:** bool

**Logic:** Iterates `state['sent']`, matches by `dedup_key`, parses `sent_at`, compares to `datetime.now() - timedelta(minutes=window_minutes)`. Returns `True` on the first match; returns `False` if no match found.

**Technical note:** `datetime.now()` uses local system time, not UTC. If the system clock changes or the process runs across a timezone change, dedup behavior will be incorrect.

---

#### `record_sent(alert, state)` 

**Location:** `notifications.py`, line 76  
**Purpose:** Appends a sent record to state and prunes entries older than 24 hours.

**Pruning logic:** `state['sent'] = [s for s in state['sent'] if s['sent_at'] > cutoff]` — string comparison on ISO8601 timestamps. This works because ISO8601 strings sort lexicographically in the same order as their datetime values, as long as no timezone offsets are mixed.

---

#### `format_alert_text(alert)` / `format_slack_payload(alert)`

**Location:** `notifications.py`, lines 90 and 100  
**Purpose:** Format an alert record for a specific channel.

`format_alert_text` returns a multi-line string with emoji, severity label, alert detail, and metadata.

`format_slack_payload` returns a dict in Slack attachment format with color coding:

| Severity | Hex color |
|---|---|
| critical | `#E24B4A` |
| warning | `#EF9F27` |
| info | `#378ADD` |

---

#### `dispatch(alert, cfg)`

**Location:** `notifications.py`, line 159  
**Purpose:** Sends an alert via the configured channel, with fallback to log on failure.

**Call chain:**
```
dispatch(alert, cfg)
  if channel == 'slack' and webhook_url exists:
    send_slack(alert, webhook_url)
      → urllib.request.urlopen(POST to webhook)
      → if fails: send_log(alert)
  elif channel == 'email' and to_addrs exists:
    send_email(alert, cfg)
      → smtplib.SMTP + starttls + login + sendmail
      → if fails: send_log(alert)
  else:
    send_log(alert)
      → print(format_alert_text(alert))
```

---

#### `meets_min_severity(alert, min_sev)`

**Location:** `notifications.py`, line 173  
**Purpose:** Returns `True` if the alert's severity rank ≥ min_severity rank.

**Rank map:** `{'info': 0, 'warning': 1, 'critical': 2}`

---

#### `run(args)`

**Location:** `notifications.py`, line 177  
**Purpose:** Main entry point. Orchestrates config loading, alert loading, filtering, dedup, dispatch, and state persistence.

**Parameters:** `args` — argparse Namespace with `.test` (bool) and `.channel` (str or None)

**Logic in order:**
1. Load config; optionally override channel from CLI arg
2. If `--test`: build a synthetic alert, dispatch, return
3. Load `alert_events.csv`; parse `value` as float, `acknowledged` as bool
4. Filter to unacknowledged rows
5. Filter by min_severity
6. Load dedup state
7. For each alert, skip if duplicate, else dispatch + record
8. Save dedup state
9. Print dispatch count

---

### `dashboard.html` — JavaScript functions

---

#### `nav(el, id)`

**Location:** `dashboard.html`, line 255  
**Purpose:** Switches the active tab.

**Logic:**
1. Hides all `.page` elements
2. Shows `#page-{id}`
3. Removes `.active` from all `.nav-tab` elements, adds to `el`
4. Calls the render function for `id` if it's not `overview` (overview is rendered on init)

**Note:** Overview is not in the render dispatch map `r`; it renders on IIFE initialization only. Switching back to Overview after visiting another tab does not re-render charts. If filter state changed on another tab, the floor chart on Overview may be stale (though the floor chart filter is independent).

---

#### `winBars(elId, portal)`

**Location:** `dashboard.html`, line 264  
**Purpose:** Renders horizontal win-rate bars for the 30d window.

**Data source:** `WIN30` — filtered by portal, sorted descending by `win_rate`.  
**Renders into:** `document.getElementById(elId).innerHTML`  
**Visual:** For each insurer, a bar whose width = `win_rate` percent of the container, filled with the insurer's color from `COLORS`. No Chart.js — pure inline HTML/CSS.

---

#### `renderFloor()`

**Location:** `dashboard.html`, line 273  
**Purpose:** Renders the market floor/ceiling line chart on the Overview tab.

**Data source:** `MF` filtered by the `#ov-portal` select value.  
**Chart type:** `line`  
**Series:** Floor (green `#1D9E75`, fill) and Ceiling (pink `#D4537E`, fill).  
**X-axis:** Date string sliced to `MM-DD` format (`d.date.slice(5)`).  
**Y-axis:** CLP formatted via `fmtCLP()`.

---

#### `renderCompetitive()`

**Location:** `dashboard.html`, line 287  
**Purpose:** Renders two charts on the Competitive tab: a 7-day rolling win-rate line chart, and a price-vs-win-rate bubble chart.

**Chart 1 (wr7) — 7d rolling win rate line:**
- Data source: `WR7` filtered by portal
- One line per insurer, colored by `COLORS`
- Missing dates filled with `null` (Chart.js `spanGaps: true` bridges gaps)

**Chart 2 (scat) — Competitive position bubble:**
- Data source: `WIN30` (30d win rate) and `PT` (daily median prices)
- X axis: average price premium over the cheapest insurer
  - Formula: `(avg_price - min_avg_price) / min_avg_price × 100`
  - `avg_price` = mean of all daily medians for that insurer/portal in `PT`
  - `min_avg_price` = minimum of such means across all insurers for that portal
- Y axis: 30d win rate from `WIN30`
- Bubble radius: fixed at 7
- Tooltip: `"InsureName: gap X.X% | win Y.Y%"`

**Implicit insight this chart reveals:** An insurer with a low x-value (priced near market minimum) and high y-value (wins often) is genuinely competitive. An insurer with high x and low y is expensive and not winning. The chart makes outliers immediately visible.

---

#### `renderTimeseries()`

**Location:** `dashboard.html`, line 316  
**Purpose:** Renders two charts on the Price Trends tab: absolute price time series per insurer, and market floor comparison across portals.

**Chart 1 (ts) — Absolute prices:**
- Data source: `PT`, filtered by portal
- One line per insurer showing daily median price
- Y-axis in CLP

**Chart 2 (floor2) — Floor comparison:**
- Data source: `MF`, both portals overlaid
- Colors: Falabella = `#1D9E75`, Santander = `#534AB7`
- Allows visual comparison of floor-level trends between portals

---

#### `renderTiming()`

**Location:** `dashboard.html`, line 342  
**Purpose:** Delegates to `renderHeatmap()` and `renderDowHeatmap()`.

---

#### `renderHeatmap()`

**Location:** `dashboard.html`, line 344  
**Purpose:** Renders the hour-of-day repricing heatmap.

**Data source:** `HM` — `{portal, insurer, hour, changes}`. If portal filter is `'all'`, all portals are included; changes for the same insurer/hour from different portals are summed.

**Aggregation:** `agg[insurer + ':' + hour] += changes` — sums all changes for that cell.

**Color function:**  
`t = value / maxVal` (normalized 0–1)  
`rgb(24 + t×139, 158 - t×113, 117 - t×81)`  
→ At t=0: `rgb(24, 158, 117)` (cool green)  
→ At t=1: `rgb(163, 45, 36)` (warm red/brown)  
Font color flips to white when `t > 0.4` for readability.

---

#### `renderDowHeatmap()`

**Location:** `dashboard.html`, line 366  
**Purpose:** Renders the day-of-week repricing heatmap.

**Data source:** `DOW` — `{insurer, dow, changes}`. Not filterable by portal.

**Day-of-week convention:** `0 = Monday` (Python weekday() convention). `DOW_LABELS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']`.

**Color function:**  
`t = value / maxVal`  
`rgb(83 - t×59, 91 + t×67, 183 - t×117)`  
→ At t=0: `rgb(83, 91, 183)` (blue)  
→ At t=1: `rgb(24, 158, 66)` (green)

---

#### `renderVolatility()`

**Location:** `dashboard.html`, line 385  
**Purpose:** Renders three displays on the Volatility tab: absolute standard deviation bars, CV bars, presence rate bars, and a price-vs-CV scatter chart.

**Data source:** `VOL` for std/CV, `PRES` for presence bars.

**Presence warning:** `avg_presence < 80` triggers amber color and bold font weight — mirrors the `below_threshold` logic from `kpi_presence_rate.csv`.

**Bubble chart:** X = mean price (CLP), Y = average CV (%). Bubble opacity: Falabella = `bb` (73% hex alpha), Santander = `66` (40% hex alpha). This visually separates portals on the same chart.

---

#### `renderAlerts()`

**Location:** `dashboard.html`, line 419  
**Purpose:** Renders the filtered alert feed on the Alerts tab.

**Filters applied in order:**
1. Severity: `'critical'` → exact match; `'warning'` → rank ≥ 1 (includes critical); `'all'` → no filter
2. Portal: exact string match
3. Insurer: exact string match
4. Alert type: exact string match

**Sorting:** Descending by `fired_at` string (lexicographic, valid because format is `YYYY-MM-DD HH:MM:SS`).

**Cap:** Only first 300 alerts rendered. Count displayed above list.

---

#### `renderTable()`

**Location:** `dashboard.html`, line 442  
**Purpose:** Renders a tabular view of the selected dataset.

**Supported datasets (`tbl-sel` select):**

| Value | Source | Cap |
|---|---|---|
| `win30` | `WIN30` | none |
| `mf` | `MF` | none |
| `ae` | `AE` | 300 |
| `pc` | `PC` | 500 |
| `snr` | `SNR` | none |
| `pres` | `PRES` | none |
| `vol` | `VOL` | none |

All table cells use `class="num"` which applies `font-variant-numeric: tabular-nums` for aligned number columns.

---

#### IIFE `(function(){ ... })()`

**Location:** `dashboard.html`, line 483  
**Purpose:** Initialization block that runs once on page load.

**Actions:**
1. Builds insurer filter options for Alerts tab from distinct values in `AE`
2. Builds alert type filter options from distinct values in `AE`
3. Counts critical alerts from `AE`; sets nav badge and KPI tile text
4. Calls `winBars('wr-f', 'Falabella')` and `winBars('wr-s', 'Santander')`
5. Calls `renderFloor()`

---

## 6. Configuration and Environment

### `config.json`

Read by `notifications.py` at startup. Merged shallowly over `DEFAULT_CONFIG`.

| Key | Type | Default | Effect |
|---|---|---|---|
| `channel` | string | `"log"` | Dispatch target: `"log"`, `"slack"`, `"email"` |
| `slack_webhook_url` | string | `""` | Full Slack incoming webhook URL |
| `email.smtp_host` | string | `"smtp.gmail.com"` | SMTP server hostname |
| `email.smtp_port` | int | `587` | SMTP port (STARTTLS) |
| `email.from_addr` | string | `""` | Sender address |
| `email.to_addrs` | list of string | `[]` | Recipient addresses |
| `email.password_env` | string | `"EMAIL_PASSWORD"` | Env var name holding the SMTP password |
| `dedup_window_minutes` | int | `60` | Suppress identical alert type/portal/insurer within this window |
| `min_severity` | string | `"warning"` | Minimum severity level to dispatch (`"info"`, `"warning"`, `"critical"`) |
| `thresholds.*` | float | see below | Reference values only — not used by `notifications.py` dispatch logic |

**Threshold reference values (informational, not enforced by notifications.py):**

| Key | Value |
|---|---|
| `price_spike_pct` | 30 |
| `price_drop_pct` | -30 |
| `market_floor_drop_pct` | -20 |
| `presence_warning_pct` | 80 |

### Environment variables

| Variable | Where used | Required for |
|---|---|---|
| `EMAIL_PASSWORD` | `notifications.py` → `send_email()` | Email dispatch |

The variable name is configurable via `config.json → email.password_env`.

### Runtime assumptions

- Python 3.10+ (uses `datetime.fromisoformat()` which became robust in 3.11; works in 3.10 with fixed-format strings)
- Working directory at pipeline invocation must be the project root (all paths are relative)
- `data/quotes_collapsed.csv` must exist before `pipeline.py` runs
- `output/` directory is created automatically by `pipeline.py` via `os.makedirs(OUT, exist_ok=True)`
- Dashboard requires a modern browser with ES6 support and access to `cdnjs.cloudflare.com` for Chart.js on first open; works offline if Chart.js is already cached

### External services

| Service | Module | Protocol | Required |
|---|---|---|---|
| Slack Incoming Webhooks | `notifications.py` | HTTPS POST | Only if `channel = "slack"` |
| Gmail SMTP | `notifications.py` | SMTP + STARTTLS port 587 | Only if `channel = "email"` |
| cdnjs.cloudflare.com | `dashboard.html` | HTTPS GET | Only on first browser open (cached thereafter) |

---

## 7. Business Logic Rules

All hardcoded thresholds, formulas, classification rules, and decision criteria:

### Price change severity (pipeline.py, lines 53–56)

```
|pct_change| >= 30  → critical
|pct_change| >= 10  → warning
|pct_change| <  10  → info
```

Applied to: every row in `price_changes.csv`. Critical and warning rows feed `alert_events.csv`. Info rows are recorded but never alerted.

### Alert type assignment (pipeline.py, lines 94–121)

```
price_changes where severity = 'critical' AND direction = 'up'   → alert_type = 'price_spike'
price_changes where severity = 'critical' AND direction = 'down' → alert_type = 'price_drop'
price_changes where severity = 'warning'                         → alert_type = 'price_move'
```

### Market floor alert threshold (pipeline.py, line 130)

```
floor_pct_change <= -20  → market_floor_drop alert (critical)
```

**Direction constraint:** Only floor *drops* ≥ 20% trigger this alert. A 20% floor *rise* does not trigger an alert. This is a hardcoded asymmetry. The corresponding event detection in step 8b uses `abs(floor_pct_chg) >= 20`, so the events file captures both directions while the alert only fires on drops.

### Win definition (pipeline.py, line 74)

```
is_cheapest = 1  iff  price_rank = 1
price_rank is computed with method='min', ascending=True
```

If two insurers have identical prices in the same run, both get rank 1 and both `is_cheapest = 1`. Win counts and win rates can exceed what a unique-winner assumption would produce.

### Presence rate threshold (pipeline.py, line 225)

```
presence_pct < 80  → below_threshold = True
```

This is an insurer availability warning. An insurer present in fewer than 80% of that day's scraping runs is considered underrepresented and may indicate scraper gaps or the insurer de-listing from the portal.

### Coefficient of variation formula (pipeline.py, line 213)

```
CV = (std / mean) × 100   (expressed as %)
```

Measures price volatility relative to the price level. An insurer with CV = 5% changes price by ~5% of its mean price as a typical fluctuation. CV is a normalized volatility measure that allows comparison across insurers at different absolute price levels.

### Daily market floor computation (pipeline.py, lines 232–234)

```
floor_price  = mean(min_price across all runs that day)
ceiling_price = mean(max_price across all runs that day)
```

This is a daily average of snapshot-level min/max, not the actual daily minimum or maximum. Intra-day extremes that occur in a single snapshot but revert may be smoothed out.

### Dashboard alert severity filter (dashboard.html, lines 420–428)

```
'critical' filter → exact match on severity == 'critical'
'warning' filter  → RANK[severity] >= 1  (i.e., warning OR critical)
'all' filter      → no filter
```

The 'warning+' option in the severity dropdown shows warnings and criticals combined, mimicking a "severity floor" pattern.

### Dashboard alert display cap

```
renderAlerts:  slice(0, 300)
renderTable (ae): slice(0, 300)
renderTable (pc): slice(0, 500)
```

The UI does not paginate. Rows beyond the cap are silently not shown.

### Insurer color mapping (dashboard.html, line 247)

```javascript
COLORS = {
  Bci:       '#378ADD',
  Cardif:    '#E85D24',
  Consorcio: '#1D9E75',
  Fid:       '#BA7517',
  Hdi:       '#534AB7',
  Sura:      '#D4537E',
  Zenit:     '#639922',   // truncated in source; full value ends after hash
  ...
}
```

Insurers not in the map receive color `#888` (grey) via `col(i) { return COLORS[i] || '#888' }`. This silently affects readability for new insurers added without updating the map.

### 30d win rate date assignment (pipeline.py, line 186)

```
date = max(all_dates)  # always the last day of the dataset
```

The 30d window in `kpi_win_rates.csv` is not a rolling 30-day window — it is the entire dataset computed once, anchored to the last date. This is a simplification appropriate for a single-month demo but would need rethinking for multi-month data.

---

## 8. UI Logic

### Architecture

`dashboard.html` is a single-file application. HTML structure, CSS variables, and JavaScript are all inline. No build step, no external files (except Chart.js CDN). All data is hardcoded in the `<script>` block as named JavaScript constants.

### Global state

| Variable | Type | Holds |
|---|---|---|
| `charts` | `{}` object | Live Chart.js instances keyed by string ID |
| DOM select elements | HTML elements | Current filter values per tab |

There is no reactive framework. State is read from DOM elements at the time each render function is called. Changing a filter triggers an `onchange` handler that calls the relevant render function directly.

### Data constants embedded in the script block

| Constant | Source table | Contents |
|---|---|---|
| `WIN30` | `kpi_win_rates` (window=30d) | Portal, insurer, wins, appearances, win_rate |
| `WR7` | `kpi_win_rates` (window=7d) | Date, portal, insurer, win_rate |
| `MF` | `kpi_market_floor` | Date, portal, floor_price, ceiling_price, floor_delta_pct |
| `AE` | `alert_events` | All alert fields |
| `HM` | `kpi_hourly_changes` | Portal, insurer, hour-of-day, change count |
| `PT` | `kpi_price_stats` | Date, portal, insurer, median price |
| `VOL` | `kpi_volatility_summary` | Portal, insurer, mean_price, avg_std, avg_cv |
| `DOW` | `kpi_dow_changes` | Insurer, day-of-week, change count |
| `PC` | `price_changes` (sample) | Recent price changes |
| `SNR` | `snapshot_rankings` (last run only) | Last snapshot's rankings |
| `PRES` | `kpi_presence_rate` aggregated | Portal, insurer, avg_presence, min_presence |

`HM`, `VOL`, `DOW`, and `PRES` are pre-aggregated summaries not directly corresponding to any single output CSV. They are computed separately when building the dashboard (not by `pipeline.py`).

### Tab rendering map

| Tab ID | Render function | Triggered by |
|---|---|---|
| `overview` | IIFE + `renderFloor()` | Page load |
| `competitive` | `renderCompetitive()` | nav click |
| `timeseries` | `renderTimeseries()` | nav click |
| `timing` | `renderTiming()` | nav click |
| `volatility` | `renderVolatility()` | nav click |
| `alerts` | `renderAlerts()` | nav click |
| `tables` | `renderTable()` | nav click |

### Chart lifecycle

Every chart is created with `new Chart(canvas, config)` and registered in `charts[id]`. Before re-rendering (e.g., after filter change), `destroyChart(id)` is called, which calls `chart.destroy()` and deletes the reference. Failure to destroy before re-creating causes a "Canvas is already in use" error and a memory leak.

### Filter interactions

| Tab | Filter element IDs | Re-render trigger |
|---|---|---|
| Overview | `ov-portal` | `onchange="renderFloor()"` |
| Competitive | `comp-portal` | `onchange="renderCompetitive()"` |
| Price trends | `ts-portal` | `onchange="renderTimeseries()"` |
| Timing | `hm-portal` | `onchange="renderTiming()"` |
| Volatility | `vol-portal` | `onchange="renderVolatility()"` |
| Alerts | `af-sev`, `af-portal`, `af-insurer`, `af-type` | `onchange="renderAlerts()"` |
| Tables | `tbl-sel`, `tbl-portal` | `onchange="renderTable()"` |

The `#af-insurer` and `#af-type` selects are dynamically populated during IIFE initialization from the actual values in `AE`. If `AE` is empty, these selects will only contain the `"All"` default option.

### Formatting utilities

| Function | Input | Output | Example |
|---|---|---|---|
| `fmtCLP(v)` | float | `toLocaleString('es-CL')` | `34510 → "34.510"` |
| `fmtPct(v, dec=1)` | float, decimals | signed percentage string | `-7.5 → "-7.5%"`, `3 → "+3.0%"` |
| `col(name)` | insurer name string | hex color | `"Cardif" → "#E85D24"` |

### CSS class-to-state mapping

| CSS class | Visual meaning | Applied by |
|---|---|---|
| `.s-critical` | Red dot (alert feed) | severity == 'critical' |
| `.s-warning` | Amber dot | severity == 'warning' |
| `.s-info` | Blue dot | severity == 'info' |
| `.tc` | Red tag background | critical tag |
| `.tw` | Amber tag background | warning tag |
| `.ti` | Blue tag background | info tag |
| `.tg` | Green tag background | "yes" cheapest tag |
| `.up` | Red text, bold | positive price change |
| `.dn` | Green text, bold | negative price change (drop = good for buyer) |

---

## 9. Execution Lifecycle

### Pipeline execution (`python pipeline.py`)

```
1. Import pandas, numpy, datetime, json, os
2. os.makedirs('output', exist_ok=True)
3. pd.read_csv('data/quotes_collapsed.csv')
   → FileNotFoundError if file missing
4. Column normalization (rename, strip, cast, drop nulls)
5. Sort by (portal, insurer, scraped_at)
6. Assign run_ids via drop_duplicates + merge
7. Write scrape_runs.csv
8. Compute price changes via groupby + shift
9. Apply severity() function row by row
10. Write price_changes.csv
11. Compute rankings via groupby rank()
12. Write snapshot_rankings.csv
13. Iterate critical price_changes → build alerts list
14. Iterate warning price_changes → build alerts list
15. Compute per-snapshot floor, shift, detect drops → build alerts list
16. Concatenate all alerts → assign alert_ids
17. Write alert_events.csv
18. Compute daily/7d/30d win rates
19. Write kpi_win_rates.csv
20. Compute daily price stats
21. Write kpi_price_stats.csv
22. Compute presence rates
23. Write kpi_presence_rate.csv
24. Compute daily market floor/ceiling
25. Write kpi_market_floor.csv
26. Compute snapshot-level floor events
27. Write market_floor_events.csv
28. Aggregate price_stats by insurer → write kpi_volatility_summary.csv
29. Aggregate presence_rate by insurer → write kpi_presence_summary.csv
30. Extract hour from price_changes, group → write kpi_hourly_changes.csv
31. Extract day-of-week from price_changes, group → write kpi_dow_changes.csv
32. Print summary to stdout
```

**What runs first:** pandas import, then immediate file I/O on line 11. If `data/quotes_collapsed.csv` is missing, the script fails immediately with no output files written.

**Error paths:** No try/except blocks anywhere in `pipeline.py`. Any exception (missing column, type error, file permission issue, memory error) terminates the script immediately. Output files written before the error retain whatever content was written; files not yet written will not exist. There is no cleanup or rollback.

### Notification execution (`python notifications.py`)

```
1. Parse CLI arguments
2. load_config() → merged config dict
3. If --test: dispatch test alert, exit
4. Check ALERTS_PATH exists; if not, print message, exit
5. Read alert_events.csv → list of dicts
6. Filter: acknowledged == False
7. Filter: meets_min_severity
8. load_state() → dedup state
9. For each alert:
   a. is_duplicate? → skip
   b. dispatch() → log / Slack / email
   c. record_sent() → append to state
10. save_state()
11. Print dispatch count
```

**First run:** `notification_state.json` does not exist → `load_state()` returns empty state → all matching alerts will be dispatched → state file is created.

**Subsequent runs within dedup window:** Same alerts suppressed. Running twice within 60 minutes (default) with no new alerts produces zero dispatches.

**Error paths:** 
- `ALERTS_PATH` missing: prints message and exits cleanly (no exception)
- Slack send failure: caught by `except Exception`, falls back to `send_log`
- Email send failure: caught by `except Exception`, falls back to `send_log`
- `notification_state.json` write failure: unhandled exception, state not persisted

### Dashboard lifecycle (browser)

```
1. Browser parses HTML
2. Chart.js loaded from CDN (or cache)
3. JavaScript executes in order:
   a. All const declarations (WIN30, WR7, MF, AE, HM, PT, VOL, DOW, PC, SNR, PRES, COLORS, DOW_LABELS)
   b. Utility functions defined (col, fmtCLP, fmtPct, destroyChart)
   c. nav(), winBars(), render*() functions defined
   d. IIFE executes:
      - Populates insurer/type dropdowns from AE
      - Sets critical alert badge and KPI tile
      - Renders winBars for both portals
      - Renders floor chart (Overview default)
4. User interaction → nav clicks → render functions called on demand
```

---

## 10. Technical Risks and Weak Points

### 1. No error handling in `pipeline.py`

The entire ETL runs in a single unguarded script. A type error on row 200 will leave five of nine output files unwritten. The dashboard will appear to work but will display stale or empty data for the unwritten tables.

### ~~2. Dashboard data is static and manually maintained~~ — RESOLVED

`build_dashboard.py` now regenerates the embedded data block in `dashboard.html` automatically after each pipeline run. Run the two scripts in sequence:

```bash
python pipeline.py
python build_dashboard.py
```

`dashboard.html` contains two marker comments — `// @@DATA_START` and `// @@DATA_END` — that delimit the eleven JS data constants (`WIN30`, `WR7`, `MF`, `AE`, `HM`, `PT`, `VOL`, `DOW`, `PC`, `SNR`, `PRES`). `build_dashboard.py` reads the relevant output CSVs, serialises each dataset, and replaces everything between those markers. All HTML structure, CSS, and JS logic outside the markers are untouched. If either marker is missing, the script exits with a clear error rather than silently corrupting the file.

### ~~3. Insurer name inconsistency between portals~~ — RESOLVED

`pipeline.py` now applies a canonical name map immediately after loading raw data (step 0), before any grouping or comparison:

```python
INSURER_CANONICAL = {
    'zurich': 'Zurich',   # Falabella → 'Zurich', Santander → 'ZURICH'
}
df['insurer'] = df['insurer'].apply(lambda x: INSURER_CANONICAL.get(x.lower(), x))
```

The lookup is case-insensitive (`.lower()`) so new scrapers returning `ZURICH`, `zurich`, or `Zurich` all resolve to `Zurich`. `REALE` is intentionally left as-is — it is a real brand name (REALE Seguros), not a casing artefact. To fix future mismatches, add one line to `INSURER_CANONICAL`; the rest of the pipeline is unaffected.

### 4. Shallow config merge for `email` object

`{**DEFAULT_CONFIG, **json.load(f)}` does a shallow merge. If `config.json` contains only `{"email": {"to_addrs": ["someone@x.com"]}}`, the merged config will have `email = {"to_addrs": ["someone@x.com"]}` with all other email keys missing (`smtp_host`, `smtp_port`, `from_addr`, `password_env`). Email dispatch will fail with a `KeyError`.

### 5. Deduplication key does not include severity

The dedup key is `{alert_type}|{portal}|{insurer}`. A warning sent first blocks a critical of the same type within the window. In a high-frequency repricing scenario, if warnings fire first, critical alerts may be systematically suppressed until the window expires.

### 6. `plan_type` is carried but never compared

All price comparisons in rankings, win rates, and alerts are cross-plan. If Insurer A's cheapest plan is a basic tier and Insurer B's cheapest is full coverage, ranking them together produces a misleading comparison. The `plan_type` column exists in `snapshot_rankings.csv` but no step filters or segments by it.

### 7. 30d win rate anchored to last date in dataset

`kpi_win_rates` has one row per portal/insurer for `window='30d'` anchored to `max(all_dates)`. If the dataset spans more than one month, this row represents the full period, not the last 30 days.

### ~~8. Market floor events vs. market floor KPI diverge~~ — DOCUMENTED (by design)

The divergence is intentional and is now explicitly documented in `pipeline.py` via an inline comment at step 8:

> `kpi_market_floor` averages `min_price` across all runs within a calendar day before computing the delta. An intra-day price drop that fully reverts before midnight will be smoothed out and may not reach the ±20 % threshold here, even though it appears in `market_floor_events.csv` which operates at per-snapshot granularity.

**Intended use of each table:**

| Table | Granularity | Use for |
|---|---|---|
| `kpi_market_floor.csv` | Daily average | Day-over-day trend charts, sustained shifts |
| `market_floor_events.csv` | Per snapshot (~30 min) | Precise event detection, intra-day alerts |

Both tables now carry this distinction in comments. The behaviour is not a bug — daily averaging intentionally suppresses noise from transient spikes. Consumers of both tables should be aware they answer different questions.

### 9. `acknowledged` field is always `False`

`alert_events.csv` has an `acknowledged` column but there is no mechanism to set it to `True`. The dashboard renders it but has no interaction for acknowledging alerts. Running `notifications.py` repeatedly will keep dispatching unacknowledged alerts (modulo dedup window). To acknowledge, one would need to edit the CSV manually.

### 10. run_id is not stable across pipeline re-runs

`run_id` is assigned as `range(1, N+1)` after sorting by `(portal, scraped_at)`. If the input data gains new rows, all run_ids shift. Any external system referencing run_ids will be invalidated on re-run.

### 11. 7d win rate computation is O(days × insurers × rows)

The 7d rolling computation uses a Python loop over all dates, filtering the full DataFrame each iteration. For one month of data this is fast enough (~15s total). At scale (12 months, more insurers), this becomes a bottleneck. The correct approach is a proper rolling window via `pandas.groupby().rolling()`.

### 12. `datetime.now()` in dedup without timezone

`notifications.py` uses `datetime.now()` throughout for the dedup window. On a server running UTC with local system time set to a different zone, or when the DST transition occurs, dedup windows will be incorrect by the offset.

---

## 11. Extension Guide

### Adding a new alert type

**Files to touch:**
1. `pipeline.py` — add a new iteration block in Section 4 (lines 91–148) that builds alert dicts and appends to the `alerts` list. Use the same dict schema as existing alerts.
2. `notifications.py` — no change required if you want default dispatch behavior. If the new type needs a different format, modify `format_alert_text()` and `format_slack_payload()`.
3. `dashboard.html` — the new `alert_type` value will appear automatically in the `#af-type` filter (populated dynamically from `AE`).

**Do not touch:** `scrape_runs.csv`, `snapshot_rankings.csv`, or `kpi_*` logic.

---

### Adding a new output KPI table

**Files to touch:**
1. `pipeline.py` — add a new step at the bottom. Read from `df`, `snapshot_rankings`, or another existing in-memory DataFrame. Write to `output/new_kpi.csv`.
2. `dashboard.html` — add a new `const NEWKPI = [...]` constant in the script block, a new `<option>` in `#tbl-sel`, and a new `else if(sel==='newkpi')` branch in `renderTable()`.

---

### Adding a new notification channel

**Files to touch:**
1. `notifications.py` — add a `send_newchannel(alert, cfg)` function. In `dispatch()`, add a new `elif channel == 'newchannel'` branch.
2. `config.json` — add any required config keys.
3. `DEFAULT_CONFIG` in `notifications.py` — add default values for the new keys.

---

### Adding a new portal

**Files to touch:**
1. `pipeline.py` — no code change needed; the portal name is derived from data. Ensure the new portal's data is in `quotes_collapsed.csv` with the correct `Portal` column value.
2. `dashboard.html` — add `<option>NewPortal</option>` to every portal `<select>` element (lines ~116, 128, 141, 151, 172, 201, 203, 233). Add a `winBars()` call and a card div in the Overview tab.
3. `COLORS` — if new insurers appear, add them to the color map.

**Do not touch:** alert logic, KPI computation logic — they are portal-agnostic.

---

### Replacing CSV with a database

**Files to touch:**
1. `pipeline.py` — replace all `df.to_csv(...)` calls with `df.to_sql(...)` using SQLAlchemy or direct psycopg2/duckdb calls. Replace `pd.read_csv(RAW)` with a query.
2. `notifications.py` — replace the `csv.DictReader` block with a database query for unacknowledged alerts. Add a write-back to set `acknowledged = True` after dispatch.
3. `dashboard.html` — replace embedded JS constants with `fetch('/api/endpoint')` calls. This requires a serving layer.

**Do not touch:** Core computation logic in `pipeline.py`, `severity()`, alert generation business rules.

---

### Making the dashboard auto-refresh

The dashboard is currently static. To make it live:
1. Create a server (Flask, FastAPI, or any static server) that serves the CSVs or exposes a JSON API.
2. In `dashboard.html`, replace each `const NAME = [...]` declaration with `const NAME = await fetch('/api/name').then(r => r.json())`.
3. Wrap initialization in an `async` IIFE.
4. Add a `setInterval(() => { renderCurrentTab(); }, 30000)` for auto-refresh.

---

## 12. Plain Language Summary

**For an engineer from a different discipline:**

Imagine you have two insurance comparison websites (Falabella and Santander) that you scrape every 30 minutes for an entire month. Each scrape gives you a list of insurance companies and the price each one is quoting at that moment.

PriceRadar takes that list of prices and answers these questions:

- **Who is cheapest, and how often?** Every time we scraped, we recorded which insurer had the lowest price. Over the month, Cardif won on Falabella 59% of the time; Sura won on Santander 76% of the time.

- **When did prices change, and by how much?** We compared each scraping run to the previous one. If the price was different, we recorded it as an event. Big changes (≥30%) are called critical; medium changes (10–30%) are warnings. In August, there were 1,305 price changes, 48 of which were large enough to trigger critical alerts.

- **Did the overall market get cheaper or more expensive?** The "market floor" is the cheapest price available at any moment. If that floor dropped by 20% or more between two consecutive scrapes, that's a major market event — it means all consumers could suddenly get insurance much cheaper, or a new insurer entered at a very aggressive price.

- **How reliable is each insurer's presence on the portal?** Some insurers appear in nearly every scrape. Others appear in only 70% of runs, meaning they intermittently de-list. We track this as "presence rate."

- **When do insurers reprice?** Looking at what hour and what day of week most price changes happen reveals each insurer's repricing schedule. Some reprice every night at 3 AM; others reprice mid-week.

**The system has three parts:**

1. `pipeline.py` is the calculator. It reads the raw price list and produces ten structured tables capturing all the above analysis.

2. `notifications.py` is the alert sender. After each pipeline run, it reads the list of significant price events and sends them to Slack, email, or just prints them — with logic to avoid sending the same alert twice in an hour.

3. `dashboard.html` is the display. It's a single web page with all the data baked in. You open it in a browser and can explore charts, heatmaps, and raw data tables without needing any server or database.

**The main limitation of the current implementation** is that the dashboard is a snapshot. The data in it was fixed when it was built. To see fresh data, you have to re-run `pipeline.py` and rebuild the dashboard. This is intentional for a demo — converting it to a live system would require a server and a database, which is described in the Extension Guide above.

---

## 13. LLM Insight Layer

The LLM layer adds qualitative insight on top of the quantitative KPI tables. It is an **opt-in, asynchronous, cache-first** layer that never affects the core pipeline. Full architecture contract: [`LLM_LAYER.md`](LLM_LAYER.md).

### Scripts

| Script | Purpose | When to run |
|--------|---------|-------------|
| `llm_client.py` | Anthropic SDK wrapper (Haiku model, 8s timeout, stub mode) | Imported by the two scripts below |
| `llm_briefing.py` | Generates a 3–5 sentence daily market summary from KPI tables | Once per day, after `pipeline.py` |
| `llm_enrichment.py` | Generates 2–4 sentence context paragraphs for critical alerts | After each batch of new alerts |

### Separation rules (non-negotiable)

1. LLM modules read **only** `output/kpi_*.csv` and `output/alert_events.csv` (for alert context only).
2. LLM modules **never** read `data/quotes_collapsed.csv` or `output/snapshot_rankings.csv`.
3. LLM modules **never** write to any operational table — only to `output/llm_cache/`.
4. `build_dashboard.py` and `notifications.py` are **cache readers only** — they never import `anthropic` and never make API calls.
5. Alerts must fire normally if `output/llm_cache/` is empty, missing, or if the API is unavailable.

### Cache layout

```
output/llm_cache/
  briefing_latest.md          ← read by build_dashboard.py → const BRIEFING
  briefing_2025-08-30.md      ← dated copies (one per run)
  alert_1.txt                 ← read by notifications.py for alert id=1
  alert_2.txt
  ...
```

### Configuration (`config.json`)

```json
"llm": {
  "enabled": false,            // flip to true before running llm_*.py scripts
  "model": "claude-haiku-4-5-20251001",
  "api_key_env": "ANTHROPIC_API_KEY",
  "timeout_seconds": 8,
  "stub_mode": false           // set true to bypass API (writes canned placeholder)
}
```

### Testing without API credits

```bash
python llm_briefing.py --stub    # write stub briefing
python llm_enrichment.py --stub  # write stub context for all critical alerts
python build_dashboard.py        # embed stub content in dashboard — zero API calls
```
