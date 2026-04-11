"""
llm_enrichment.py — One-shot backfill: generate LLM context paragraphs for
critical alerts in alert_events.csv and cache them to output/llm_cache/.

Run once (or after each batch of new alerts) AFTER pipeline.py:

    python llm_enrichment.py          # process all uncached critical alerts
    python llm_enrichment.py --stub   # skip API calls, write canned text
    python llm_enrichment.py --force  # regenerate even if cache exists

Output
------
    output/llm_cache/alert_<alert_id>.txt   (one file per critical alert)

Architecture contract
---------------------
• Reads ONLY from output/kpi_*.csv and output/alert_events.csv.
  Never reads data/quotes_collapsed.csv or output/snapshot_rankings.csv.
• Writes ONLY to output/llm_cache/.
• notifications.py reads the cache; it never calls this module or the LLM.
• Running notifications.py burns ZERO API credits.
• If this script fails for any alert, that alert still dispatches via
  notifications.py — just without the context paragraph.
"""

import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT      = Path(__file__).parent
OUT       = ROOT / "output"
CACHE_DIR = ROOT / "output" / "llm_cache"

SYSTEM_PROMPT = (
    "You are a concise market analyst monitoring Chilean auto-insurance prices. "
    "Write one short paragraph (2–4 sentences) in clear plain English."
)

ENRICHMENT_PROMPT_TEMPLATE = """\
A price alert has fired for the Chilean auto-insurance market.

Alert details:
{alert_json}

7-day KPI context for {insurer} on portal {portal}:
{kpi_json}

Based on the 7-day context, write a 2–4 sentence paragraph that explains:
1. Whether this event fits {insurer}'s prior pricing behaviour on {portal}.
2. The most likely explanation (e.g. catch-up after stable period, market-wide move, outlier).
3. What metric to watch next (e.g. whether the new price holds or reverts).

Be specific and concise. Do not repeat the alert numbers verbatim.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def read_csv(name: str) -> list[dict]:
    path = OUT / name
    if not path.exists():
        print(f"  WARNING: {path} not found — skipping")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_critical_alerts() -> list[dict]:
    rows = read_csv("alert_events.csv")
    return [r for r in rows if r.get("severity") == "critical"]


def build_alert_kpi_context(insurer: str, portal: str, fired_at: str) -> dict:
    """Return last 7 days of KPI data for a specific insurer+portal before fired_at."""
    try:
        fired_dt = datetime.fromisoformat(fired_at)
    except ValueError:
        fired_dt = datetime.now()
    since = (fired_dt - timedelta(days=7)).date().isoformat()
    fired_date = fired_dt.date().isoformat()

    # Price stats
    ps = [
        {"date": r["date"], "median": float(r["median"]),
         "std": float(r["std"]) if r["std"] not in ("", "nan") else None,
         "cv": float(r["cv"]) if r["cv"] not in ("", "nan") else None,
         "min": float(r["min_price"]), "max": float(r["max_price"])}
        for r in read_csv("kpi_price_stats.csv")
        if r["insurer"] == insurer and r["portal"] == portal
        and since <= r["date"] <= fired_date
    ]

    # Presence
    pr = [
        {"date": r["date"], "presence_pct": float(r["presence_pct"]),
         "below_threshold": r["below_threshold"].lower() == "true"}
        for r in read_csv("kpi_presence_rate.csv")
        if r["insurer"] == insurer and r["portal"] == portal
        and since <= r["date"] <= fired_date
    ]

    # Win rates (7d window)
    wr = [
        {"date": r["date"], "win_rate": float(r["win_rate"]),
         "wins": int(r["wins"]), "appearances": int(r["appearances"])}
        for r in read_csv("kpi_win_rates.csv")
        if r["insurer"] == insurer and r["portal"] == portal
        and r["window"] == "7d"
        and since <= r["date"] <= fired_date
    ]

    return {
        "insurer": insurer,
        "portal": portal,
        "period": {"from": since, "to": fired_date},
        "price_stats": ps,
        "presence_rate": pr,
        "win_rates_7d": wr,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run(stub: bool, force: bool, cfg: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    alerts = load_critical_alerts()
    if not alerts:
        print("  No critical alerts found in alert_events.csv.")
        return

    print(f"  Found {len(alerts)} critical alert(s).")

    from llm_client import summarize

    processed = skipped = failed = 0

    for alert in alerts:
        alert_id = alert.get("alert_id", "?")
        cache_path = CACHE_DIR / f"alert_{alert_id}.txt"

        if cache_path.exists() and not force and not stub:
            skipped += 1
            continue

        insurer  = alert.get("insurer", "")
        portal   = alert.get("portal", "")
        fired_at = alert.get("fired_at", "")

        # Market-floor alerts have insurer='ALL' — skip LLM enrichment
        if insurer == "ALL":
            skipped += 1
            continue

        print(f"  Processing alert #{alert_id}: {insurer} / {portal} at {fired_at[:16]}…")

        kpi_ctx = build_alert_kpi_context(insurer, portal, fired_at)
        alert_clean = {k: v for k, v in alert.items()
                       if k in ("alert_type", "severity", "portal", "insurer",
                                "fired_at", "value", "threshold", "detail")}

        user_msg = ENRICHMENT_PROMPT_TEMPLATE.format(
            alert_json=json.dumps(alert_clean, indent=2),
            insurer=insurer,
            portal=portal,
            kpi_json=json.dumps(kpi_ctx, indent=2, default=str),
        )

        text = summarize(SYSTEM_PROMPT, user_msg, cfg, stub=stub)

        if text is None:
            print(f"    LLM returned None for alert #{alert_id} — skipping.")
            failed += 1
            continue

        cache_path.write_text(text, encoding="utf-8")
        print(f"    Written: {cache_path}")
        processed += 1

    print()
    print(f"  Done. Processed: {processed} | Skipped (cached): {skipped} | Failed: {failed}")
    if processed > 0:
        print("  Alerts with context will now appear enriched in Slack via notifications.py.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate LLM context for critical alerts")
    parser.add_argument("--stub",  action="store_true", help="Skip API calls, write canned text")
    parser.add_argument("--force", action="store_true", help="Regenerate even if cache exists")
    args = parser.parse_args()

    import json as _json
    config_path = ROOT / "config.json"
    cfg = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg = _json.load(f).get("llm", {})

    if args.stub:
        cfg = {**cfg, "enabled": True, "stub_mode": True}

    if not cfg.get("enabled", False) and not args.stub:
        print("LLM layer is disabled (config.json llm.enabled = false).")
        print("Set llm.enabled to true, or run with --stub to test the pipeline.")
        raise SystemExit(0)

    print("LLM alert enrichment backfill")
    run(stub=args.stub, force=args.force, cfg=cfg)
