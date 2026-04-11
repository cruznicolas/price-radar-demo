# PriceRadar Data Table Guide

This guide explains the generated CSV tables in plain language:

- what each table represents
- what one row means
- the columns you should expect
- where the table is used
- a real sample of the first rows

It is intentionally friendlier than `TECHNICAL_DOCUMENTATION.md`. If you want code-level detail, read that file next.

---

## 1. Big picture

The repository starts from one raw file:

- `data/quotes_collapsed.csv`

`pipeline.py` turns that raw scrape output into a set of intermediate and final CSV tables inside `output/`.

Those generated tables are then used in three ways:

1. `build_dashboard.py` reads selected CSVs and embeds them into `dashboard.html`.
2. `notifications.py` reads `output/alert_events.csv` and dispatches alerts.
3. Analysts can inspect the CSVs directly for QA, debugging, or ad hoc analysis.

---

## 2. Fast map of the tables

| File | What one row means | Used by |
|---|---|---|
| `output/scrape_runs.csv` | One scrape run for one portal at one timestamp | QA / operations |
| `output/price_changes.csv` | One detected price change for one insurer | Dashboard tables, alert generation |
| `output/snapshot_rankings.csv` | One insurer ranked inside one snapshot | Dashboard latest rankings, win rates, market floor |
| `output/alert_events.csv` | One fired alert | Dashboard alert views, notifications |
| `output/market_floor_events.csv` | One large snapshot-level market floor move | QA / analysis |
| `output/kpi_win_rates.csv` | One insurer win-rate KPI for one date/window | Dashboard competitive views |
| `output/kpi_price_stats.csv` | One insurer daily price summary | Dashboard price trends, volatility inputs |
| `output/kpi_presence_rate.csv` | One insurer daily presence summary | QA / presence rollups |
| `output/kpi_market_floor.csv` | One portal daily floor/ceiling summary | Dashboard overview and trends |
| `output/kpi_volatility_summary.csv` | One insurer volatility summary over the full period | Dashboard volatility views |
| `output/kpi_presence_summary.csv` | One insurer presence summary over the full period | Dashboard presence view |
| `output/kpi_hourly_changes.csv` | One insurer count of price changes by day-of-week and hour | Dashboard repricing timing heatmap |
| `output/kpi_dow_changes.csv` | One insurer count of price changes by day of week | Dashboard repricing timing heatmap |

---

## 3. How the dashboard uses them

`build_dashboard.py` converts some CSVs into JavaScript constants inside `dashboard.html`.

| Dashboard constant | Source CSV | How it is used |
|---|---|---|
| `WIN30` | `kpi_win_rates.csv` filtered to `window = 30d` | 30-day win-rate bars |
| `WR7` | `kpi_win_rates.csv` filtered to `window = 7d` | 7-day rolling win-rate lines |
| `MF` | `kpi_market_floor.csv` | Market floor and ceiling charts, overview KPIs |
| `AE` | `alert_events.csv` | Main alerts page, overview alert cards |
| `HM` | `kpi_hourly_changes.csv` | Hour-of-day repricing heatmap |
| `PT` | `kpi_price_stats.csv` using only `median` | Daily insurer price trend lines |
| `VOL` | `kpi_volatility_summary.csv` | Volatility bars and scatter |
| `DOW` | `kpi_dow_changes.csv` | Day-of-week repricing heatmap |
| `PC` | `price_changes.csv` trimmed to a recent/prioritized subset | Raw tables tab |
| `SNR` | `snapshot_rankings.csv` filtered to the most recent snapshot per portal | Latest ranking tables and overview cards |
| `PRES` | `kpi_presence_summary.csv` | Presence bars and overview support |

These output tables are currently not embedded into the dashboard directly:

- `scrape_runs.csv`
- `market_floor_events.csv`
- `kpi_presence_rate.csv`

They still matter because they support QA, summaries, and other downstream tables.

---

## 4. Table-by-table reference

Read this section from top to bottom. The order below is the recommended reading order and the table-of-contents order for understanding the project.

### Table reading order

1. [`output/scrape_runs.csv`](#1-outputscrape_runscsv)
2. [`output/snapshot_rankings.csv`](#2-outputsnapshot_rankingscsv)
3. [`output/price_changes.csv`](#3-outputprice_changescsv)
4. [`output/alert_events.csv`](#4-outputalert_eventscsv)
5. [`output/kpi_win_rates.csv`](#5-outputkpi_win_ratescsv)
6. [`output/kpi_market_floor.csv`](#6-outputkpi_market_floorcsv)
7. [`output/market_floor_events.csv`](#7-outputmarket_floor_eventscsv)
8. [`output/kpi_price_stats.csv`](#8-outputkpi_price_statscsv)
9. [`output/kpi_volatility_summary.csv`](#9-outputkpi_volatility_summarycsv)
10. [`output/kpi_presence_rate.csv`](#10-outputkpi_presence_ratecsv)
11. [`output/kpi_presence_summary.csv`](#11-outputkpi_presence_summarycsv)
12. [`output/kpi_hourly_changes.csv`](#12-outputkpi_hourly_changescsv)
13. [`output/kpi_dow_changes.csv`](#13-outputkpi_dow_changescsv)

### 1. `output/scrape_runs.csv`

What it is:
One row per `(run_id, portal, scraped_at)`. This is the clean run log for the pipeline.

Why it exists:
- Lets you verify scrape cadence
- Lets you count how many insurers came back in each run
- Feeds daily run totals used by presence calculations

Main columns:
- `run_id`: synthetic ID for one portal snapshot
- `portal`: portal name
- `scraped_at`: local Santiago timestamp used across downstream tables
- `insurers_returned`: number of unique insurers in that run
- `rows`: total rows returned
- `status`: currently always `success`

Sample head:

| run_id | portal | scraped_at | insurers_returned | rows | status |
|---|---|---|---:|---:|---|
| 1 | Falabella | 2025-07-31 20:00:02 | 8 | 8 | success |
| 2 | Falabella | 2025-07-31 20:30:02 | 8 | 8 | success |

Used by:
- `kpi_presence_rate.csv`
- operations / sanity checking

### 2. `output/snapshot_rankings.csv`

What it is:
One row per insurer inside one portal snapshot, with rank and gap-to-cheapest.

Why it exists:
- This is the canonical "who was cheapest in each run?" table
- Win-rate calculations are based on this
- The latest rankings shown in the dashboard come from this

Main columns:
- `run_id`, `portal`, `insurer`, `scraped_at`
- `plan_type`
- `price`
- `price_rank`
- `is_cheapest`
- `gap_to_min`, `gap_to_min_pct`
- `min_price`, `max_price`
- `n_insurers`

Sample head:

| run_id | portal | insurer | scraped_at | plan_type | price | price_rank | is_cheapest | gap_to_min | gap_to_min_pct | min_price | max_price | n_insurers |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Falabella | Bci | 2025-07-31 20:00:02 | Full Cobertura | 44223.0 | 8 | 0 | 16337.0 | 58.585 | 27886.0 | 44223.0 | 8 |
| 2 | Falabella | Bci | 2025-07-31 20:30:02 | Full Cobertura | 44223.0 | 8 | 0 | 16337.0 | 58.585 | 27886.0 | 44223.0 | 8 |

Used by:
- `kpi_win_rates.csv`
- `kpi_market_floor.csv`
- `market_floor_events.csv`
- dashboard latest ranking slice (`SNR`)

### 3. `output/price_changes.csv`

What it is:
One row per actual price change for one insurer on one portal.

Why it exists:
- This is the event stream of repricing
- Alerts are derived from this table
- Timing heatmaps are derived from this table

Main columns:
- `change_id`: row ID
- `run_id`: run where the new price was seen
- `portal`, `insurer`
- `scraped_at`: timestamp of the new price
- `prev_scraped_at`: previous timestamp for that insurer/portal
- `prev_price`, `price`
- `abs_change`, `pct_change`
- `direction`: `up` or `down`
- `severity`: `info`, `warning`, `critical`

Sample head:

| change_id | run_id | portal | insurer | scraped_at | prev_scraped_at | prev_price | price | abs_change | pct_change | direction | severity |
|---|---:|---|---|---|---|---:|---:|---:|---:|---|---|
| 0 | 4 | Falabella | Bci | 2025-07-31 21:30:02 | 2025-07-31 21:00:02 | 44223.0 | 47382.0 | 3159.0 | 7.1433 | up | info |
| 1 | 10 | Falabella | Bci | 2025-08-01 00:30:01 | 2025-08-01 00:00:01 | 47382.0 | 47376.0 | -6.0 | -0.0127 | down | info |

Used by:
- `alert_events.csv`
- `kpi_hourly_changes.csv`
- `kpi_dow_changes.csv`
- dashboard raw tables (`PC`)

### 4. `output/alert_events.csv`

What it is:
One fired alert, already classified and ready for UI or notifications.

Why it exists:
- It turns raw price-change math into product-ready alert records
- This is the source for the alerts tab and notifications

Alert types today:
- `price_spike`: critical upward move of at least 30%
- `price_drop`: critical downward move of at least 30%
- `price_move`: warning move between 10% and less than 30%
- `market_floor_drop`: critical drop of at least 20% in portal floor between consecutive snapshots

Main columns:
- `alert_type`
- `severity`
- `portal`, `insurer`
- `fired_at`
- `run_id`
- `value`: actual percent move
- `threshold`: rule threshold
- `detail`: original plain-text detail
- `alert_id`
- `acknowledged`

Sample head:

| alert_type | severity | portal | insurer | fired_at | run_id | value | threshold | detail | alert_id | acknowledged |
|---|---|---|---|---|---:|---:|---:|---|---:|---|
| price_spike | critical | Falabella | Bci | 2025-08-14 21:30:01 | 676 | 63.41 | 30.0 | Bci on Falabella: 32397 -> 52939 (+63.4%) | 1 | False |
| price_spike | critical | Falabella | Bci | 2025-08-25 21:30:01 | 1199 | 36.18 | 30.0 | Bci on Falabella: 35678 -> 48586 (+36.2%) | 2 | False |

Used by:
- `dashboard.html` alert cards, alerts page, alert tables
- `notifications.py`

### 5. `output/kpi_win_rates.csv`

What it is:
Win-rate KPIs at three windows inside the same file: `1d`, `7d`, and `30d`.

Why it exists:
- Tells you how often an insurer was the cheapest option
- Powers both the 30-day ranking view and the 7-day rolling trend view

Main columns:
- `date`
- `portal`
- `insurer`
- `wins`
- `appearances`
- `win_rate`
- `window`

Sample head:

| date | portal | insurer | wins | appearances | win_rate | window |
|---|---|---|---:|---:|---:|---|
| 2025-07-31 | Falabella | Bci | 0 | 8 | 0.0 | 1d |
| 2025-07-31 | Falabella | Cardif | 5 | 8 | 62.5 | 1d |

Used by:
- dashboard `WIN30`
- dashboard `WR7`

### 6. `output/kpi_market_floor.csv`

What it is:
Daily average floor and ceiling by portal.

Why it exists:
- This is the clean day-over-day market positioning view
- It smooths many snapshots into one daily summary

Important nuance:
- `floor_price` is the average of snapshot-level cheapest prices within the day
- `ceiling_price` is the average of snapshot-level max prices within the day
- `floor_delta_pct` is day-over-day, not snapshot-over-snapshot

Main columns:
- `date`
- `portal`
- `floor_price`
- `ceiling_price`
- `n_snapshots`
- `floor_delta_pct`
- `is_market_event`

Sample head:

| date | portal | floor_price | ceiling_price | n_snapshots | floor_delta_pct | is_market_event |
|---|---|---:|---:|---:|---:|---|
| 2025-07-31 | Falabella | 29769.81 | 46228.71 | 8 |  | False |
| 2025-08-01 | Falabella | 31041.72 | 47366.25 | 48 | 4.2725 | False |

Used by:
- dashboard overview floor chart
- dashboard market floor trend chart
- overview KPIs derived from `MF`

### 7. `output/market_floor_events.csv`

What it is:
One large snapshot-level change in the cheapest available price for a portal.

Why it exists:
- It captures sharp floor moves at full snapshot granularity
- It is more precise than the daily market-floor table

Important nuance:
`kpi_market_floor.csv` is daily and smoothed.
`market_floor_events.csv` is snapshot-level and event-focused.

Main columns:
- `portal`
- `scraped_at`
- `run_id`
- `min_price`
- `prev_floor`
- `floor_pct_chg`
- `is_event`

Sample head:

| portal | scraped_at | run_id | min_price | prev_floor | floor_pct_chg | is_event |
|---|---|---:|---:|---:|---:|---|
| Falabella | 2025-08-11 05:30:02 | 500 | 25726.0 | 35240.0 | -26.9977 | True |
| Falabella | 2025-08-14 21:30:01 | 676 | 22501.0 | 17015.0 | 32.2421 | True |

Used by:
- mainly QA / analysis
- not currently embedded in the dashboard

### 8. `output/kpi_price_stats.csv`

What it is:
Daily descriptive statistics for each insurer on each portal.

Why it exists:
- Gives a daily price profile, not just one point
- Median feeds the daily price trend lines
- Standard deviation and CV feed volatility summaries

Main columns:
- `date`, `portal`, `insurer`
- `mean`, `median`, `std`
- `p10`, `p90`
- `min_price`, `max_price`
- `n_obs`
- `cv`

Sample head:

| date | portal | insurer | mean | median | std | p10 | p90 | min_price | max_price | n_obs | cv |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-07-31 | Falabella | Bci | 46197.38 | 47382.0 | 1634.94 | 44223.0 | 47382.0 | 44223.0 | 47382.0 | 8 | 3.539 |
| 2025-07-31 | Falabella | Cardif | 31310.12 | 30853.0 | 1292.94 | 30853.0 | 31950.1 | 30853.0 | 34510.0 | 8 | 4.1295 |

Used by:
- dashboard daily median price series (`PT`)
- `kpi_volatility_summary.csv`

### 9. `output/kpi_volatility_summary.csv`

What it is:
One row per insurer summarizing volatility across the full demo period.

Why it exists:
- Converts many daily rows into one easy ranking
- Helps identify dynamic repricers

Main columns:
- `portal`
- `insurer`
- `mean_price`
- `avg_std`
- `avg_cv`

Sample head:

| portal | insurer | mean_price | avg_std | avg_cv |
|---|---|---:|---:|---:|
| Falabella | Bci | 40882.99 | 1026.89 | 2.59 |
| Falabella | Cardif | 26076.12 | 678.8 | 2.72 |

Used by:
- dashboard volatility bars
- dashboard volatility scatter plot

### 10. `output/kpi_presence_rate.csv`

What it is:
Daily availability of each insurer as a percentage of runs for that day and portal.

Why it exists:
- Helps interpret whether a low win rate is real or just low visibility
- Feeds the summary presence table

Main columns:
- `date`, `portal`, `insurer`
- `runs_present`
- `runs_total`
- `presence_pct`
- `below_threshold`

Sample head:

| date | portal | insurer | runs_present | runs_total | presence_pct | below_threshold |
|---|---|---|---:|---:|---:|---|
| 2025-07-31 | Falabella | Bci | 8 | 8 | 100.0 | False |
| 2025-07-31 | Falabella | Cardif | 8 | 8 | 100.0 | False |

Used by:
- `kpi_presence_summary.csv`
- QA / data quality checks

### 11. `output/kpi_presence_summary.csv`

What it is:
One row per insurer summarizing presence across the full period.

Why it exists:
- Makes the presence view compact and easy to read
- Highlights insurers with partial availability

Main columns:
- `portal`
- `insurer`
- `avg_presence`
- `min_presence`

Sample head:

| portal | insurer | avg_presence | min_presence |
|---|---|---:|---:|
| Falabella | Bci | 95.22 | 77.08 |
| Falabella | Cardif | 99.33 | 95.83 |

Used by:
- dashboard presence bars (`PRES`)

### 12. `output/kpi_hourly_changes.csv`

What it is:
Count of price changes by insurer, portal, day-of-week, and hour.

Why it exists:
- Shows when repricing tends to happen
- Supports the hour heatmap plus the weekday filter

Main columns:
- `portal`
- `insurer`
- `dow`: Python weekday convention (`0 = Monday`, `6 = Sunday`)
- `hour`
- `changes`

Sample head:

| portal | insurer | dow | hour | changes |
|---|---|---:|---:|---:|
| Falabella | Bci | 0 | 0 | 4 |
| Falabella | Bci | 0 | 5 | 1 |

Used by:
- dashboard hour-of-day repricing heatmap (`HM`)

### 13. `output/kpi_dow_changes.csv`

What it is:
Count of price changes by insurer, portal, and day of week.

Why it exists:
- Gives a weekly timing summary without the hour detail
- Powers the day-of-week heatmap

Main columns:
- `portal`
- `insurer`
- `dow`
- `changes`

Sample head:

| portal | insurer | dow | changes |
|---|---|---:|---:|
| Falabella | Bci | 0 | 8 |
| Falabella | Bci | 1 | 6 |

Used by:
- dashboard day-of-week repricing heatmap (`DOW`)

---

## 5. Which tables are "raw events" vs "summaries"?

If you are trying to orient yourself quickly:

Raw-ish event tables:
- `scrape_runs.csv`
- `snapshot_rankings.csv`
- `price_changes.csv`
- `alert_events.csv`
- `market_floor_events.csv`

Daily summary tables:
- `kpi_win_rates.csv`
- `kpi_market_floor.csv`
- `kpi_price_stats.csv`
- `kpi_presence_rate.csv`

Period summary tables:
- `kpi_volatility_summary.csv`
- `kpi_presence_summary.csv`
- `kpi_hourly_changes.csv`
- `kpi_dow_changes.csv`

---

## 6. Recommended reading order

This now matches the table order above:

1. `scrape_runs.csv`
2. `snapshot_rankings.csv`
3. `price_changes.csv`
4. `alert_events.csv`
5. `kpi_win_rates.csv`
6. `kpi_market_floor.csv`
7. `market_floor_events.csv`
8. `kpi_price_stats.csv`
9. `kpi_volatility_summary.csv`
10. `kpi_presence_rate.csv`
11. `kpi_presence_summary.csv`
12. `kpi_hourly_changes.csv`
13. `kpi_dow_changes.csv`

---

## 7. One mental model that helps

You can think of the generated data in four layers:

1. Raw quotes
   One row = one insurer quote returned by one scrape.

2. Snapshot state
   One row = one insurer positioned inside one portal snapshot.
   Main table: `snapshot_rankings.csv`

3. Events
   One row = something changed.
   Main tables: `price_changes.csv`, `alert_events.csv`, `market_floor_events.csv`

4. KPIs
   One row = an aggregate for a day, week-pattern, or full period.
   Main tables: all `kpi_*.csv` files

Once that clicks, the whole repository becomes much easier to navigate.
