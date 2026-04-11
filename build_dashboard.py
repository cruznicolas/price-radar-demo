#!/usr/bin/env python3
"""
build_dashboard.py  —  Regenerates the embedded data block in dashboard.html
                        from the current output/ CSV files.

Run this after pipeline.py:

    python pipeline.py
    python build_dashboard.py

The script replaces every line between the @@DATA_START and @@DATA_END
markers inside dashboard.html with fresh JS constants derived from the
output CSVs.  Everything outside that block (HTML, CSS, JS logic) is
untouched.

The connection: dashboard.html is the only output file; TECHNICAL_DOCUMENTATION.md
and this script are the source of truth for how data is embedded.
"""

import csv, json, re, sys
from pathlib import Path
from datetime import datetime, date, timedelta
import statistics

OUT  = Path("output")
DASH = Path("dashboard.html")

MARKER_START = "// @@DATA_START"
MARKER_END   = "// @@DATA_END"

# ── Helpers ──────────────────────────────────────────────────────────────────

def read_csv(name: str) -> list[dict]:
    path = OUT / name
    if not path.exists():
        print(f"  WARNING: {path} not found — run pipeline.py first")
        sys.exit(1)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cast(row: dict, ints: set = frozenset(), floats: set = frozenset(),
         bools: set = frozenset(), keep_str: set = frozenset()) -> dict:
    """
    Type-cast a CSV row (all-string) into a dict with proper JS-friendly types.

    - ints/floats/bools: cast those keys
    - keep_str: always keep as string (e.g. dates, timestamps)
    - everything else: attempt float → int if whole number, else float, else str
    """
    out = {}
    for k, v in row.items():
        if k in keep_str:
            out[k] = v
        elif k in bools:
            out[k] = v.lower() == "true"
        elif k in ints:
            out[k] = int(float(v)) if v not in ("", "nan", "None") else None
        elif k in floats:
            try:
                f = float(v)
                out[k] = round(f, 4)
            except (ValueError, TypeError):
                out[k] = None
        else:
            # auto-detect
            try:
                f = float(v)
                out[k] = int(f) if f == int(f) else round(f, 4)
            except (ValueError, TypeError):
                out[k] = v
    return out


def js_const(name: str, data: list) -> str:
    return f"const {name}={json.dumps(data, separators=(',', ':'))};"


# ── Build each constant ───────────────────────────────────────────────────────

def build_WIN30() -> str:
    rows = read_csv("kpi_win_rates.csv")
    data = [
        cast(r, ints={"wins", "appearances"}, floats={"win_rate"}, keep_str={"portal", "insurer"})
        for r in rows if r["window"] == "30d"
    ]
    # sort: portal asc, win_rate desc
    data.sort(key=lambda r: (r["portal"], -r["win_rate"]))
    return js_const("WIN30", data)


def _win_snapshot(window: str) -> list:
    """Return win-rate rows for the most recent date that has data for `window`."""
    rows = read_csv("kpi_win_rates.csv")
    last_date = max(r["date"] for r in rows if r["window"] == window)
    data = [
        cast(r, ints={"wins", "appearances"}, floats={"win_rate"},
             keep_str={"portal", "insurer"})
        for r in rows if r["window"] == window and r["date"] == last_date
    ]
    data.sort(key=lambda r: (r["portal"], -r["win_rate"]))
    return data


def build_WIN1D() -> str:
    """Most recent single-day win rates (window=1d)."""
    return js_const("WIN1D", _win_snapshot("1d"))


def build_WIN7D() -> str:
    """Most recent 7-day rolling win rates (window=7d)."""
    return js_const("WIN7D", _win_snapshot("7d"))


def _build_wr(window: str, const_name: str) -> str:
    rows = read_csv("kpi_win_rates.csv")
    data = [
        cast(r, ints={"wins", "appearances"}, floats={"win_rate"},
             keep_str={"date", "portal", "insurer"})
        for r in rows if r["window"] == window
    ]
    data.sort(key=lambda r: (r["date"], r["portal"], r["insurer"]))
    return js_const(const_name, [{"date": r["date"], "portal": r["portal"],
                                   "insurer": r["insurer"], "win_rate": r["win_rate"]}
                                  for r in data])


def build_WR1D() -> str:
    """Daily (1d) win rates over time — noisy, shows day-to-day swings."""
    return _build_wr("1d", "WR1D")


def build_WR7() -> str:
    """7-day rolling win rates over time — smoothed."""
    return _build_wr("7d", "WR7")


def build_MF() -> str:
    rows = read_csv("kpi_market_floor.csv")
    data = []
    for r in rows:
        d = cast(r, floats={"floor_price", "ceiling_price", "floor_delta_pct"},
                 ints={"n_snapshots"}, keep_str={"date", "portal"})
        # floor_delta_pct is NaN for first row of each portal
        if d.get("floor_delta_pct") is None or str(r["floor_delta_pct"]) in ("", "nan"):
            d["floor_delta_pct"] = None
        data.append(d)
    data.sort(key=lambda r: (r["portal"], r["date"]))
    return js_const("MF", data)


def build_AE() -> str:
    rows = read_csv("alert_events.csv")
    data = [
        cast(r, ints={"alert_id", "run_id"}, floats={"value", "threshold"},
             bools={"acknowledged"},
             keep_str={"alert_type", "severity", "portal", "insurer",
                       "fired_at", "detail"})
        for r in rows
    ]
    data.sort(key=lambda r: r["fired_at"], reverse=True)
    return js_const("AE", data)


def build_HM() -> str:
    rows = read_csv("kpi_hourly_changes.csv")
    data = [
        cast(r, ints={"dow", "hour", "changes"}, keep_str={"portal", "insurer"})
        for r in rows
    ]
    data.sort(key=lambda r: (r["portal"], r["insurer"], r["dow"], r["hour"]))
    return js_const("HM", data)


def build_PT() -> str:
    rows = read_csv("kpi_price_stats.csv")
    data = [
        {"date": r["date"], "portal": r["portal"], "insurer": r["insurer"],
         "median": round(float(r["median"]), 2)}
        for r in rows
    ]
    data.sort(key=lambda r: (r["portal"], r["insurer"], r["date"]))
    return js_const("PT", data)


def build_VOL() -> str:
    rows = read_csv("kpi_volatility_summary.csv")
    data = [
        cast(r, floats={"mean_price", "avg_std", "avg_cv"},
             keep_str={"portal", "insurer"})
        for r in rows
    ]
    data.sort(key=lambda r: (r["portal"], -r["avg_cv"]))
    return js_const("VOL", data)


def build_DOW() -> str:
    rows = read_csv("kpi_dow_changes.csv")
    data = [
        cast(r, ints={"dow", "changes"}, keep_str={"portal", "insurer"})
        for r in rows
    ]
    data.sort(key=lambda r: (r["portal"], r["insurer"], r["dow"]))
    return js_const("DOW", data)


def build_PC() -> str:
    """Most recent 500 price-change events (critical + warning first)."""
    rows = read_csv("price_changes.csv")
    RANK = {"critical": 2, "warning": 1, "info": 0}
    rows.sort(key=lambda r: (-RANK.get(r["severity"], 0), r["scraped_at"]), reverse=False)
    # keep critical/warning first, then fill up to 500
    prioritised = [r for r in rows if r["severity"] in ("critical", "warning")]
    rest        = [r for r in rows if r["severity"] == "info"]
    selected    = (prioritised + rest)[:500]
    data = [
        {"portal": r["portal"], "insurer": r["insurer"],
         "scraped_at": r["scraped_at"][:16],   # trim seconds
         "prev_price": int(float(r["prev_price"])),
         "price":      int(float(r["price"])),
         "pct_change": round(float(r["pct_change"]), 2),
         "direction":  r["direction"],
         "severity":   r["severity"]}
        for r in selected
    ]
    return js_const("PC", data)


def build_SNR() -> str:
    """Snapshot rankings for the single most-recent run per portal.

    Uses max(scraped_at) per portal as the anchor, not max(run_id).
    run_id is a synthetic key whose maximum does not always correspond to the
    most recent timestamp (e.g. if a partial run with only one insurer sorts
    last alphabetically and receives the highest run_id).
    """
    rows = read_csv("snapshot_rankings.csv")
    # find the latest scraped_at per portal
    latest_ts = {}
    for r in rows:
        p = r["portal"]
        ts = r["scraped_at"]
        if ts > latest_ts.get(p, ""):
            latest_ts[p] = ts
    data = []
    for r in rows:
        if r["scraped_at"] == latest_ts[r["portal"]]:
            data.append({
                "portal":       r["portal"],
                "insurer":      r["insurer"],
                "scraped_at":   r["scraped_at"][:16],
                "price":        round(float(r["price"]), 2),
                "price_rank":   int(r["price_rank"]),
                "is_cheapest":  int(r["is_cheapest"]),
                "gap_to_min":   round(float(r["gap_to_min"]), 2),
                "gap_to_min_pct": round(float(r["gap_to_min_pct"]), 4),
            })
    data.sort(key=lambda r: (r["portal"], r["price_rank"]))
    return js_const("SNR", data)


def build_GLOBAL_RANK() -> str:
    """Top-2 cheapest insurers across ALL portals at the most recent snapshot.

    Strategy: find the global max(scraped_at). Then include the latest snapshot
    per portal within ±15 minutes of that global max (handles portals scraped at
    slightly different times). Sort all rows in that window by price ascending,
    return the cheapest 2 (deduplicated by insurer so the same name can't appear
    twice if they appear on both portals).
    """
    rows = read_csv("snapshot_rankings.csv")
    if not rows:
        return js_const("GLOBAL_RANK", [])

    # Global latest timestamp
    global_latest = max(r["scraped_at"] for r in rows)
    # Allow ±15 min so portals scraped a few minutes apart all qualify
    latest_dt = datetime.fromisoformat(global_latest)
    window_start = (latest_dt - timedelta(minutes=15)).isoformat(sep=" ")

    # Candidate rows: latest per portal within the window
    latest_per_portal: dict[str, str] = {}
    for r in rows:
        if r["scraped_at"] >= window_start:
            p = r["portal"]
            if r["scraped_at"] > latest_per_portal.get(p, ""):
                latest_per_portal[p] = r["scraped_at"]

    candidates = [
        r for r in rows
        if r["portal"] in latest_per_portal
        and r["scraped_at"] == latest_per_portal[r["portal"]]
    ]

    # Sort by price ascending; deduplicate by insurer name
    candidates.sort(key=lambda r: float(r["price"]))
    seen_insurers: set[str] = set()
    top2 = []
    for r in candidates:
        if r["insurer"] not in seen_insurers:
            seen_insurers.add(r["insurer"])
            top2.append({
                "rank":       len(top2) + 1,
                "insurer":    r["insurer"],
                "portal":     r["portal"],
                "price":      round(float(r["price"]), 2),
                "scraped_at": r["scraped_at"][:16],
                "plan_type":  r.get("plan_type", ""),
            })
        if len(top2) == 2:
            break

    return js_const("GLOBAL_RANK", top2)


def build_MF6H() -> str:
    """Last-6-hours market floor + median, sampled from snapshot_rankings.csv.

    Returns both an aggregated (all-portals) series and per-portal series so
    the dashboard toggle can switch views without a second constant.
    """
    rows = read_csv("snapshot_rankings.csv")
    if not rows:
        return js_const("MF6H", {"aggregated": [], "byPortal": {}, "windowHours": 6})

    global_latest = max(r["scraped_at"] for r in rows)
    latest_dt = datetime.fromisoformat(global_latest)
    cutoff = (latest_dt - timedelta(hours=6)).isoformat(sep=" ")

    recent = [r for r in rows if r["scraped_at"] >= cutoff]
    if not recent:
        return js_const("MF6H", {"aggregated": [], "byPortal": {}, "windowHours": 6})

    # Collect all unique scraped_at timestamps (sorted)
    timestamps = sorted({r["scraped_at"] for r in recent})

    def series_for(subset: list[dict]) -> list[dict]:
        """Build {t, floor, median} for a slice of rows, grouping by scraped_at."""
        by_ts: dict[str, list[float]] = {}
        for r in subset:
            ts = r["scraped_at"]
            by_ts.setdefault(ts, []).append(float(r["price"]))
        result = []
        for ts in sorted(by_ts):
            prices = by_ts[ts]
            result.append({
                "t":      ts[11:16],   # HH:MM
                "floor":  round(min(prices), 2),
                "median": round(statistics.median(prices), 2),
                "n":      len(prices),
            })
        return result

    # Aggregated across all portals
    aggregated = series_for(recent)

    # Per-portal
    portals = sorted({r["portal"] for r in recent})
    by_portal = {p: series_for([r for r in recent if r["portal"] == p]) for p in portals}

    return js_const("MF6H", {
        "aggregated":  aggregated,
        "byPortal":    by_portal,
        "windowHours": 6,
    })


def build_PROFILE() -> str:
    """Monitored profile from config.json.

    Uses an EXPLICIT ALLOWLIST so that sensitive fields (e.g. rut) are never
    serialised into dashboard.html even if someone adds them to config.json.
    """
    ALLOWED = {"birthdate", "gender", "brand", "model", "year"}
    config_path = Path("config.json")
    if not config_path.exists():
        return js_const("PROFILE", {})

    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f).get("monitored_profile", {})

    profile: dict = {k: raw[k] for k in ALLOWED if k in raw}

    # Compute age from birthdate
    if "birthdate" in profile:
        try:
            bd = date.fromisoformat(profile["birthdate"])
            today = date.today()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            profile["ageYears"] = age
        except ValueError:
            profile["ageYears"] = None

    return js_const("PROFILE", profile)


def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML converter for trusted briefing text."""
    import html as _html
    # Escape first, then apply inline formatting
    text = _html.escape(text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Split into paragraphs on blank lines
    paras = re.split(r'\n\s*\n', text.strip())
    return ''.join(f'<p>{p.strip()}</p>' for p in paras if p.strip())


def build_BRIEFING() -> str:
    """Read cached briefing markdown and pre-render to HTML.

    This function NEVER calls the LLM.  It reads the file written by
    llm_briefing.py and embeds the rendered HTML so dashboard.html stays
    self-contained.  Missing cache → empty object, no error.
    """
    latest = Path("output/llm_cache/briefing_latest.md")
    if not latest.exists():
        return js_const("BRIEFING", {"date": None, "html": ""})

    content = latest.read_text(encoding="utf-8").strip()
    lines = content.splitlines()

    # First line may be "# YYYY-MM-DD"
    briefing_date = None
    body_lines = lines
    if lines and re.match(r'^#\s*\d{4}-\d{2}-\d{2}', lines[0]):
        m = re.search(r'\d{4}-\d{2}-\d{2}', lines[0])
        if m:
            briefing_date = m.group()
        body_lines = lines[1:]

    body = "\n".join(body_lines).strip()
    html_body = _md_to_html(body) if body else ""

    return js_const("BRIEFING", {"date": briefing_date, "html": html_body})


def build_PRES() -> str:
    rows = read_csv("kpi_presence_summary.csv")
    data = [
        cast(r, floats={"avg_presence", "min_presence"}, keep_str={"portal", "insurer"})
        for r in rows
    ]
    data.sort(key=lambda r: (r["portal"], -r["avg_presence"]))
    return js_const("PRES", data)


# ── Inject into dashboard.html ────────────────────────────────────────────────

def inject(html: str, block: str) -> str:
    """Replace the content between @@DATA_START and @@DATA_END markers."""
    start_marker = MARKER_START
    end_marker   = MARKER_END

    start_idx = html.find(start_marker)
    end_idx   = html.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("ERROR: markers not found in dashboard.html")
        print(f"  Expected: '{start_marker}' and '{end_marker}'")
        sys.exit(1)

    # keep the marker lines themselves; replace only what's between them
    start_end    = html.index("\n", start_idx) + 1   # character after the start-marker line
    end_begin    = html.rindex("\n", 0, end_idx) + 1  # start of the end-marker line

    return html[:start_end] + block + "\n" + html[end_begin:]


def main():
    if not DASH.exists():
        print(f"ERROR: {DASH} not found.")
        sys.exit(1)

    print(f"Building data block from output/ CSVs …")
    builders = [
        ("WIN30",       build_WIN30),
        ("WIN1D",       build_WIN1D),
        ("WIN7D",       build_WIN7D),
        ("WR1D",        build_WR1D),
        ("WR7",         build_WR7),
        ("MF",          build_MF),
        ("AE",          build_AE),
        ("HM",          build_HM),
        ("PT",          build_PT),
        ("VOL",         build_VOL),
        ("DOW",         build_DOW),
        ("PC",          build_PC),
        ("SNR",         build_SNR),
        ("PRES",        build_PRES),
        ("GLOBAL_RANK", build_GLOBAL_RANK),
        ("MF6H",        build_MF6H),
        ("PROFILE",     build_PROFILE),
        ("BRIEFING",    build_BRIEFING),
    ]

    lines = []
    for name, fn in builders:
        line = fn()
        lines.append(line)
        # quick size report
        n = line.count("},{") + 1 if "}," in line else (1 if "[{" in line else 0)
        print(f"  {name:<8} {n:>5} records")

    block = "\n".join(lines)

    html = DASH.read_text(encoding="utf-8")
    new_html = inject(html, block)

    DASH.write_text(new_html, encoding="utf-8")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\ndashboard.html updated  [{ts}]")
    print(f"  Hint: open via a local server:")
    print(f"    python -m http.server 8000")
    print(f"    then visit http://localhost:8000/dashboard.html")


if __name__ == "__main__":
    main()
