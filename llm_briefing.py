"""
llm_briefing.py — One-shot daily market briefing generator.

Run once per day (manually or via Task Scheduler / cron) AFTER pipeline.py:

    python llm_briefing.py                    # uses latest date in KPIs
    python llm_briefing.py --date 2025-08-30  # specify a date
    python llm_briefing.py --stub             # skip API call, write canned text
    python llm_briefing.py --force            # overwrite even if cache exists

Output
------
    output/llm_cache/briefing_<DATE>.md
    output/llm_cache/briefing_latest.md   (always overwritten)

Architecture contract
---------------------
• Reads ONLY from output/kpi_*.csv — never from data/quotes_collapsed.csv
  or output/snapshot_rankings.csv.
• Writes ONLY to output/llm_cache/.
• build_dashboard.py reads the cache; it never calls this module.
• Running build_dashboard.py multiple times burns ZERO API credits.

Windows Task Scheduler (run daily at 07:00)
-------------------------------------------
    schtasks /create /tn "PriceRadar Briefing" /tr "python C:\\path\\to\\llm_briefing.py" /sc daily /st 07:00

Linux/macOS cron (07:00 every day)
------------------------------------
    0 7 * * * cd /path/to/price_radar_demo && python llm_briefing.py
"""

import argparse
import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT      = Path(__file__).parent
OUT       = ROOT / "output"
CACHE_DIR = ROOT / "output" / "llm_cache"

SYSTEM_PROMPT = (
    "You are a concise market analyst monitoring Chilean auto-insurance prices. "
    "Write in clear, plain English. Avoid bullet lists — use flowing prose."
)

BRIEFING_PROMPT_TEMPLATE = """\
Here are the KPI snapshots for {date} from a Chilean auto-insurance price monitor.
The data covers two portals (Falabella, Santander) and roughly 10 insurers.

{kpi_json}

Identify anything notable compared to the prior 7-day context included above, \
and write a 3 to 5 sentence market summary. Focus on: floor price movements, \
which insurer is leading, any unusual volatility, and overall market direction.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def read_csv(name: str) -> list[dict]:
    path = OUT / name
    if not path.exists():
        print(f"  WARNING: {path} not found — skipping")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_date_in_kpis() -> str:
    rows = read_csv("kpi_market_floor.csv")
    if not rows:
        return date.today().isoformat()
    return max(r["date"] for r in rows)


def build_kpi_context(target_date: str) -> dict:
    """Serialize KPI data for target_date + prior 7 days into a compact dict."""
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    since  = (target - timedelta(days=7)).isoformat()

    # Market floor (daily per portal)
    mf_rows = [
        {"date": r["date"], "portal": r["portal"],
         "floor": float(r["floor_price"]), "ceiling": float(r["ceiling_price"]),
         "floor_delta_pct": r["floor_delta_pct"] if r["floor_delta_pct"] not in ("", "nan") else None}
        for r in read_csv("kpi_market_floor.csv")
        if r["date"] >= since
    ]

    # Price stats (daily per insurer — median + CV as key signals)
    ps_rows = [
        {"date": r["date"], "portal": r["portal"], "insurer": r["insurer"],
         "median": float(r["median"]),
         "cv": float(r["cv"]) if r["cv"] not in ("", "nan") else None}
        for r in read_csv("kpi_price_stats.csv")
        if r["date"] >= since
    ]

    # Win rates (7d window)
    wr_rows = [
        {"date": r["date"], "portal": r["portal"], "insurer": r["insurer"],
         "win_rate": float(r["win_rate"])}
        for r in read_csv("kpi_win_rates.csv")
        if r["window"] == "7d" and r["date"] >= since
    ]

    # Volatility summary (full period — for reference)
    vol_rows = [
        {"portal": r["portal"], "insurer": r["insurer"],
         "mean_price": float(r["mean_price"]), "avg_cv": float(r["avg_cv"])}
        for r in read_csv("kpi_volatility_summary.csv")
    ]

    return {
        "target_date": target_date,
        "market_floor": mf_rows,
        "price_stats_daily": ps_rows,
        "win_rates_7d": wr_rows,
        "volatility_summary": vol_rows,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run(target_date: str, stub: bool, force: bool, cfg: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    dated_path  = CACHE_DIR / f"briefing_{target_date}.md"
    latest_path = CACHE_DIR / "briefing_latest.md"

    if dated_path.exists() and not force and not stub:
        print(f"  Briefing for {target_date} already cached at {dated_path}")
        print("  Use --force to regenerate.")
        # Still update latest pointer even if we skip the API call
        content = dated_path.read_text(encoding="utf-8")
        latest_path.write_text(content, encoding="utf-8")
        print(f"  Latest pointer updated: {latest_path}")
        return

    print(f"  Building KPI context for {target_date}…")
    ctx = build_kpi_context(target_date)
    kpi_json = json.dumps(ctx, indent=2, default=str)

    user_msg = BRIEFING_PROMPT_TEMPLATE.format(
        date=target_date,
        kpi_json=kpi_json,
    )

    from llm_client import summarize
    print(f"  Calling LLM (stub={stub or cfg.get('stub_mode', False)})…")
    text = summarize(SYSTEM_PROMPT, user_msg, cfg, stub=stub)

    if text is None:
        print("  LLM call returned None — no briefing written.")
        return

    content = f"# {target_date}\n\n{text}\n"
    dated_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    print(f"  Written: {dated_path}")
    print(f"  Updated: {latest_path}")
    print()
    print("  Run `python build_dashboard.py` to surface the briefing in the dashboard.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate daily LLM market briefing")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: latest in KPIs)")
    parser.add_argument("--stub", action="store_true", help="Skip API call, write canned text")
    parser.add_argument("--force", action="store_true", help="Overwrite existing cache file")
    args = parser.parse_args()

    config_path = ROOT / "config.json"
    cfg = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f).get("llm", {})

    # --stub flag overrides config enabled check
    if args.stub:
        cfg = {**cfg, "enabled": True, "stub_mode": True}

    if not cfg.get("enabled", False) and not args.stub:
        print("LLM layer is disabled (config.json llm.enabled = false).")
        print("Set llm.enabled to true, or run with --stub to test the pipeline.")
        raise SystemExit(0)

    target_date = args.date or latest_date_in_kpis()
    print(f"LLM briefing for {target_date}")
    run(target_date, stub=args.stub, force=args.force, cfg=cfg)
