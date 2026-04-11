# LLM Layer — Architecture Contract

This document defines the strict separation rules for the AI/LLM insight layer added to Price Radar. These rules are a design contract, not just guidelines — they must be maintained in all future changes to the codebase.

---

## Core principle

> The LLM reads only serialized KPI outputs. It never writes to operational tables. Alerts must still fire if the LLM fails or times out.

---

## What the LLM layer does

The LLM layer adds two qualitative insight features to the Price Radar demo:

1. **Daily briefing** — A 3–5 sentence market summary generated once per day from the latest KPI snapshot. Surfaced as a "Daily Briefing" card on the dashboard overview.

2. **Alert enrichment** — A 2–4 sentence paragraph appended to Slack alerts for critical events, providing historical context (7-day KPI history) and what to watch next.

---

## Files in this layer

| File | Role |
|------|------|
| `llm_client.py` | Thin Anthropic SDK wrapper. Only file that imports `anthropic`. |
| `llm_briefing.py` | One-shot generator: reads KPI CSVs → calls LLM → writes briefing markdown. |
| `llm_enrichment.py` | One-shot backfill: reads alert rows → calls LLM → writes per-alert context files. |

These are standalone scripts that the operator runs manually. They are **never** invoked automatically by `pipeline.py`, `build_dashboard.py`, or `notifications.py`.

---

## Data flow

```
OPERATIONAL DATA (never touched by LLM modules)
  data/quotes_collapsed.csv
  output/alert_events.csv       ← read by llm_enrichment.py for context ONLY
  output/price_changes.csv
  output/snapshot_rankings.csv

KPI TABLES (read-only for LLM)
  output/kpi_market_floor.csv        ┐
  output/kpi_price_stats.csv         │  read by llm_briefing.py
  output/kpi_win_rates.csv           │  and llm_enrichment.py
  output/kpi_presence_rate.csv       │
  output/kpi_volatility_summary.csv  ┘

LLM OUTPUT (write-only target)
  output/llm_cache/briefing_<DATE>.md
  output/llm_cache/briefing_latest.md
  output/llm_cache/alert_<ID>.txt

CONSUMERS (cache readers — zero API calls)
  build_dashboard.py  →  reads briefing_latest.md  →  const BRIEFING in dashboard.html
  notifications.py    →  reads alert_<ID>.txt       →  appends to Slack payload
```

---

## Hard rules

### 1. LLM modules NEVER write to operational tables

`llm_briefing.py` and `llm_enrichment.py` only write to `output/llm_cache/`. They must never open any file in `output/` for writing except under the `llm_cache/` subdirectory.

### 2. LLM modules NEVER read raw quote data or snapshot rankings

Input is limited to:
- `output/kpi_*.csv` (aggregated KPI tables)
- `output/alert_events.csv` (for the alert row context only — not for price-level reasoning)

`data/quotes_collapsed.csv` and `output/snapshot_rankings.csv` are off-limits because they contain row-level quote data that can be trivially misused to do the pipeline's job inside the LLM.

### 3. `build_dashboard.py` and `notifications.py` NEVER call the LLM

These two scripts are the "consumers" of LLM output. They read from `output/llm_cache/` and embed or append the pre-generated text. They do **not** import `anthropic`, do not make HTTP calls, and do not trigger LLM generation. Regenerating `dashboard.html` burns **zero API credits**.

### 4. Alerts must fire even if the LLM is unavailable

The `load_alert_context()` function in `notifications.py` wraps cache reads in a try/except and returns an empty string on any failure. The dispatch loop proceeds identically with or without enrichment context. LLM output is **additive only** — it appends a field to Slack; it does not gate alert delivery.

### 5. LLM output is one-shot, idempotent, and cacheable

Running `llm_briefing.py` twice for the same date overwrites the existing file — no duplicate entries, no append logic. Running `llm_enrichment.py` twice skips already-cached alerts (use `--force` to regenerate). There is no streaming, no database, no webhook.

---

## Failure modes and expected behaviour

| Failure | Effect |
|---------|--------|
| `ANTHROPIC_API_KEY` not set | `llm_client.summarize()` returns `None`; briefing/enrichment not written; no crash |
| API timeout (exceeds `timeout_seconds`) | `anthropic` raises; `llm_client` catches, logs, returns `None` |
| `briefing_latest.md` missing | `build_BRIEFING()` returns empty object; dashboard shows "No briefing yet" empty state |
| `alert_<ID>.txt` missing | `load_alert_context()` returns `''`; Slack alert dispatches without Context field |
| `llm_enrichment.py` not run | Same as above — all alerts dispatch normally |
| LLM returns garbled text | Text is stored as-is; it renders in Slack/dashboard but is not trusted for decisions |

---

## Security note: markdown rendering

`build_BRIEFING()` converts the cached markdown to HTML server-side and embeds it as a string in `dashboard.html`. This is safe **because we generate the markdown ourselves** via `llm_briefing.py`. The rendered HTML must never be derived from user-supplied input. Do not repurpose this path to render arbitrary external content.

---

## Scheduling (no automatic scheduler is installed)

`llm_briefing.py` and `llm_enrichment.py` are designed to be run manually or wired into the operator's existing scheduler:

**Windows Task Scheduler (daily at 07:00):**
```
schtasks /create /tn "PriceRadar LLM Briefing" ^
  /tr "python C:\path\to\price_radar_demo\llm_briefing.py" ^
  /sc daily /st 07:00
```

**Linux / macOS cron (07:00 every day):**
```
0 7 * * * cd /path/to/price_radar_demo && python llm_briefing.py >> logs/llm_briefing.log 2>&1
```

**Alert enrichment** is typically run once as a backfill after a batch of new critical alerts:
```
python llm_enrichment.py          # processes all uncached critical alerts
python llm_enrichment.py --force  # regenerate all
```

---

## Testing without API credits

Both scripts support `--stub` mode which bypasses the API and writes canned placeholder text:

```
python llm_briefing.py --stub    # writes stub briefing to output/llm_cache/
python llm_enrichment.py --stub  # writes stub context to all uncached critical alerts
python build_dashboard.py        # embeds stub content; zero API calls
python notifications.py          # reads stub context from cache; zero API calls
```

Model and API key in `config.json`:
```json
"llm": {
  "enabled": false,
  "model": "claude-haiku-4-5-20251001",
  "api_key_env": "ANTHROPIC_API_KEY",
  "timeout_seconds": 8,
  "stub_mode": false
}
```

Set `enabled: true` and export `ANTHROPIC_API_KEY` to use the real API.
