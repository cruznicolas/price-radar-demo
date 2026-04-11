import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json, os

RAW = 'data/quotes_collapsed.csv'
OUT = 'output'
os.makedirs(OUT, exist_ok=True)

# Canonical insurer names — resolves case inconsistencies across portals.
# Add an entry whenever a scraper returns the same brand under different
# capitalisations on different portals.
INSURER_CANONICAL = {
    'zurich': 'Zurich',   # Falabella → 'Zurich', Santander → 'ZURICH'
}

# ── 0. Load & normalize raw ──────────────────────────────────────────────────
df = pd.read_csv(RAW)
# Source timestamps are recorded in CET. Convert them to America/Santiago for
# all downstream analytics, then drop timezone info so the existing CSV outputs
# and dashboard continue to work with local Santiago wall-clock time.
df['scraped_at'] = (
    pd.to_datetime(df['updated_at'])
    .dt.tz_localize('CET')
    .dt.tz_convert('America/Santiago')
    .dt.tz_localize(None)
)
df['insurer']   = df['name'].str.strip().apply(
    lambda x: INSURER_CANONICAL.get(x.lower(), x)
)
df['portal']    = df['Portal'].str.strip()
df['plan_type'] = df['plan_type'].str.strip()
df['price']     = df['effective_price']
df = df.dropna(subset=['price'])
df = df.sort_values(['portal', 'insurer', 'scraped_at']).reset_index(drop=True)

# Assign a run_id per (portal, scraped_at) pair.
# Sort by (portal, scraped_at) before assigning so that run_id is
# monotonically increasing with time within each portal. Without this
# explicit sort, drop_duplicates preserves the df's row order (sorted by
# portal/insurer/scraped_at), meaning a (portal, t) pair that only contains
# an insurer that sorts late alphabetically can appear last and receive the
# highest run_id — making max(run_id) != most-recent timestamp.
run_keys = (
    df[['portal','scraped_at']]
    .drop_duplicates()
    .sort_values(['portal','scraped_at'])
    .copy()
)
run_keys['run_id'] = range(1, len(run_keys)+1)
df = df.merge(run_keys, on=['portal','scraped_at'], how='left')

print(f"Raw rows: {len(df)}, Unique runs: {df['run_id'].nunique()}, Insurers: {df['insurer'].nunique()}")

# ── 1. scrape_runs ───────────────────────────────────────────────────────────
scrape_runs = (
    df.groupby(['run_id','portal','scraped_at'])
    .agg(insurers_returned=('insurer','nunique'), rows=('price','count'))
    .reset_index()
)
scrape_runs['status'] = 'success'
scrape_runs.to_csv(f'{OUT}/scrape_runs.csv', index=False)
print(f"scrape_runs: {len(scrape_runs)} rows")

# ── 2. price_changes (stream layer) ──────────────────────────────────────────
# For each (portal, insurer), compare each row to the prior row's price
df_sorted = df.sort_values(['portal','insurer','scraped_at']).copy()
df_sorted['prev_price']    = df_sorted.groupby(['portal','insurer'])['price'].shift(1)
df_sorted['prev_scraped_at'] = df_sorted.groupby(['portal','insurer'])['scraped_at'].shift(1)

changes = df_sorted[
    df_sorted['prev_price'].notna() &
    (df_sorted['price'] != df_sorted['prev_price'])
].copy()

changes['pct_change'] = ((changes['price'] - changes['prev_price']) / changes['prev_price'] * 100).round(4)
changes['abs_change'] = (changes['price'] - changes['prev_price']).round(2)
changes['direction']  = np.where(changes['pct_change'] > 0, 'up', 'down')

# Severity flag (for alert_events join)
def severity(pct):
    if abs(pct) >= 30: return 'critical'
    if abs(pct) >= 10: return 'warning'
    return 'info'

changes['severity'] = changes['pct_change'].apply(severity)

price_changes = changes[[
    'run_id','portal','insurer','scraped_at','prev_scraped_at',
    'prev_price','price','abs_change','pct_change','direction','severity'
]].reset_index(drop=True)
price_changes.index.name = 'change_id'
price_changes = price_changes.reset_index()
price_changes.to_csv(f'{OUT}/price_changes.csv', index=False)
print(f"price_changes: {len(price_changes)} rows")
print(f"  critical: {(price_changes['severity']=='critical').sum()}")
print(f"  warning:  {(price_changes['severity']=='warning').sum()}")
print(f"  info:     {(price_changes['severity']=='info').sum()}")

# ── 3. snapshot_rankings (stream layer) ──────────────────────────────────────
sr = df.copy()
sr['price_rank']   = sr.groupby(['run_id','portal'])['price'].rank(method='min', ascending=True).astype(int)
sr['is_cheapest']  = (sr['price_rank'] == 1).astype(int)
sr['min_price']    = sr.groupby(['run_id','portal'])['price'].transform('min')
sr['max_price']    = sr.groupby(['run_id','portal'])['price'].transform('max')
sr['gap_to_min']   = (sr['price'] - sr['min_price']).round(2)
sr['gap_to_min_pct'] = ((sr['gap_to_min'] / sr['min_price']) * 100).round(4)
sr['n_insurers']   = sr.groupby(['run_id','portal'])['insurer'].transform('count')

snapshot_rankings = sr[[
    'run_id','portal','insurer','scraped_at','plan_type',
    'price','price_rank','is_cheapest','gap_to_min','gap_to_min_pct',
    'min_price','max_price','n_insurers'
]].reset_index(drop=True)
snapshot_rankings.to_csv(f'{OUT}/snapshot_rankings.csv', index=False)
print(f"snapshot_rankings: {len(snapshot_rankings)} rows")

# ── 4. alert_events (stream layer) ───────────────────────────────────────────
alerts = []

# 4a. Price spike/drop >= 30% → critical
crit = price_changes[price_changes['severity'] == 'critical'].copy()
for _, row in crit.iterrows():
    alerts.append({
        'alert_type': 'price_spike' if row['direction'] == 'up' else 'price_drop',
        'severity': 'critical',
        'portal': row['portal'],
        'insurer': row['insurer'],
        'fired_at': row['scraped_at'],
        'run_id': row['run_id'],
        'value': round(row['pct_change'], 2),
        'threshold': 30.0 if row['direction'] == 'up' else -30.0,
        'detail': f"{row['insurer']} on {row['portal']}: {row['prev_price']:.0f} → {row['price']:.0f} ({row['pct_change']:+.1f}%)"
    })

# 4b. Price move 10–30% → warning
warn = price_changes[price_changes['severity'] == 'warning'].copy()
for _, row in warn.iterrows():
    alerts.append({
        'alert_type': 'price_move',
        'severity': 'warning',
        'portal': row['portal'],
        'insurer': row['insurer'],
        'fired_at': row['scraped_at'],
        'run_id': row['run_id'],
        'value': round(row['pct_change'], 2),
        'threshold': 10.0,
        'detail': f"{row['insurer']} on {row['portal']}: {row['prev_price']:.0f} → {row['price']:.0f} ({row['pct_change']:+.1f}%)"
    })

# 4c. Market floor drop >= 20% in one snapshot → critical
market_floor = (
    snapshot_rankings.groupby(['portal','run_id','scraped_at'])['min_price']
    .first().reset_index().sort_values(['portal','scraped_at'])
)
market_floor['prev_floor'] = market_floor.groupby('portal')['min_price'].shift(1)
market_floor['floor_pct_change'] = ((market_floor['min_price'] - market_floor['prev_floor']) / market_floor['prev_floor'] * 100)
floor_drops = market_floor[market_floor['floor_pct_change'] <= -20].dropna()
for _, row in floor_drops.iterrows():
    alerts.append({
        'alert_type': 'market_floor_drop',
        'severity': 'critical',
        'portal': row['portal'],
        'insurer': 'ALL',
        'fired_at': row['scraped_at'],
        'run_id': row['run_id'],
        'value': round(row['floor_pct_change'], 2),
        'threshold': -20.0,
        'detail': f"Market floor on {row['portal']} dropped {row['floor_pct_change']:.1f}%: {row['prev_floor']:.0f} → {row['min_price']:.0f}"
    })

alert_events = pd.DataFrame(alerts)
alert_events['alert_id'] = range(1, len(alert_events)+1)
alert_events['acknowledged'] = False
alert_events['fired_at'] = pd.to_datetime(alert_events['fired_at'])
alert_events.to_csv(f'{OUT}/alert_events.csv', index=False)
print(f"alert_events: {len(alert_events)} rows")
print(f"  critical: {(alert_events['severity']=='critical').sum()}")
print(f"  warning:  {(alert_events['severity']=='warning').sum()}")

# ── 5. kpi_win_rates (batch layer) ───────────────────────────────────────────
sr_daily = snapshot_rankings.copy()
sr_daily['date'] = pd.to_datetime(sr_daily['scraped_at']).dt.date

# daily win rate
daily_wr = (
    sr_daily.groupby(['date','portal','insurer'])
    .agg(wins=('is_cheapest','sum'), appearances=('is_cheapest','count'))
    .reset_index()
)
daily_wr['win_rate'] = (daily_wr['wins'] / daily_wr['appearances'] * 100).round(4)

# 7d rolling — compute from daily
all_dates = sorted(sr_daily['date'].unique())
rows_7d = []
for d in all_dates:
    window_start = d - timedelta(days=6)
    w = sr_daily[(sr_daily['date'] >= window_start) & (sr_daily['date'] <= d)]
    for (portal, insurer), g in w.groupby(['portal','insurer']):
        rows_7d.append({
            'date': d, 'portal': portal, 'insurer': insurer, 'window': '7d',
            'wins': g['is_cheapest'].sum(),
            'appearances': len(g),
            'win_rate': round(g['is_cheapest'].mean() * 100, 4)
        })
kpi_7d = pd.DataFrame(rows_7d)

# 30d (whole month)
rows_30d = []
for (portal, insurer), g in sr_daily.groupby(['portal','insurer']):
    rows_30d.append({
        'date': max(all_dates), 'portal': portal, 'insurer': insurer, 'window': '30d',
        'wins': g['is_cheapest'].sum(),
        'appearances': len(g),
        'win_rate': round(g['is_cheapest'].mean() * 100, 4)
    })
kpi_30d = pd.DataFrame(rows_30d)

# tag daily
daily_wr['window'] = '1d'
kpi_win_rates = pd.concat([daily_wr, kpi_7d, kpi_30d], ignore_index=True)
kpi_win_rates.to_csv(f'{OUT}/kpi_win_rates.csv', index=False)
print(f"kpi_win_rates: {len(kpi_win_rates)} rows")

# ── 6. kpi_price_stats (batch layer) ─────────────────────────────────────────
ps = sr_daily.copy()
price_stats = (
    ps.groupby(['date','portal','insurer'])['price']
    .agg(
        mean=lambda x: round(x.mean(), 2),
        median=lambda x: round(x.median(), 2),
        std=lambda x: round(x.std(), 2),
        p10=lambda x: round(x.quantile(0.10), 2),
        p90=lambda x: round(x.quantile(0.90), 2),
        min_price='min',
        max_price='max',
        n_obs='count'
    )
    .reset_index()
)
price_stats['cv'] = (price_stats['std'] / price_stats['mean'] * 100).round(4)
price_stats.to_csv(f'{OUT}/kpi_price_stats.csv', index=False)
print(f"kpi_price_stats: {len(price_stats)} rows")

# ── 7. kpi_presence_rate (batch layer) ───────────────────────────────────────
daily_runs = scrape_runs.copy()
daily_runs['date'] = pd.to_datetime(daily_runs['scraped_at']).dt.date
runs_per_day = daily_runs.groupby(['date','portal'])['run_id'].count().reset_index(name='runs_total')

presence = sr_daily.groupby(['date','portal','insurer']).size().reset_index(name='runs_present')
presence = presence.merge(runs_per_day, on=['date','portal'], how='left')
presence['presence_pct'] = (presence['runs_present'] / presence['runs_total'] * 100).round(4)
presence['below_threshold'] = presence['presence_pct'] < 80
presence.to_csv(f'{OUT}/kpi_presence_rate.csv', index=False)
print(f"kpi_presence_rate: {len(presence)} rows")

# ── 8. kpi_market_floor (batch layer) ────────────────────────────────────────
# NOTE: this table averages min/max prices across all runs within each calendar
# day before computing the floor delta.  An intra-day price drop that fully
# reverts before midnight will be smoothed out and may not reach the ±20 %
# threshold here even though it triggers an event in market_floor_events.csv
# (step 8b), which operates at per-snapshot granularity.
# Use kpi_market_floor for day-over-day trend analysis; use market_floor_events
# for precise event detection.
mf_daily = (
    sr_daily.groupby(['date','portal'])
    .agg(
        floor_price=('min_price', 'mean'),
        ceiling_price=('max_price', 'mean'),
        n_snapshots=('run_id', 'nunique')
    ).reset_index()
)
mf_daily['floor_price'] = mf_daily['floor_price'].round(2)
mf_daily['ceiling_price'] = mf_daily['ceiling_price'].round(2)
mf_daily = mf_daily.sort_values(['portal','date'])
mf_daily['prev_floor'] = mf_daily.groupby('portal')['floor_price'].shift(1)
mf_daily['floor_delta_pct'] = ((mf_daily['floor_price'] - mf_daily['prev_floor']) / mf_daily['prev_floor'] * 100).round(4)
mf_daily['is_market_event'] = mf_daily['floor_delta_pct'].abs() >= 20
mf_daily.drop(columns=['prev_floor'], inplace=True)
mf_daily.to_csv(f'{OUT}/kpi_market_floor.csv', index=False)
print(f"kpi_market_floor: {len(mf_daily)} rows")
print(f"  market events flagged: {mf_daily['is_market_event'].sum()}")

# ── 8b. market_floor_events using per-snapshot, not daily ────────────────────
snap_floor = (
    snapshot_rankings.groupby(['portal','scraped_at','run_id'])['min_price']
    .min().reset_index()
    .sort_values(['portal','scraped_at'])
)
snap_floor['prev_floor']  = snap_floor.groupby('portal')['min_price'].shift(1)
snap_floor['floor_pct_chg'] = ((snap_floor['min_price'] - snap_floor['prev_floor']) / snap_floor['prev_floor'] * 100).round(4)
snap_floor['is_event'] = snap_floor['floor_pct_chg'].abs() >= 20

floor_events = snap_floor[snap_floor['is_event']].copy()
floor_events.to_csv(f'{OUT}/market_floor_events.csv', index=False)
print(f"\nmarket_floor_events (snapshot-level, >=20% move): {len(floor_events)} rows")
print(floor_events[['portal','scraped_at','prev_floor','min_price','floor_pct_chg']].to_string())

# ── 9. kpi_volatility_summary (batch layer) ───────────────────────────────────
# Per-insurer aggregation of kpi_price_stats across all days.
# Consumed by the dashboard Volatility tab (VOL constant).
vol_summary = (
    price_stats.groupby(['portal','insurer'])
    .agg(
        mean_price=('mean',   'mean'),
        avg_std=   ('std',    'mean'),
        avg_cv=    ('cv',     'mean'),
    )
    .reset_index()
)
vol_summary['mean_price'] = vol_summary['mean_price'].round(2)
vol_summary['avg_std']    = vol_summary['avg_std'].round(2)
vol_summary['avg_cv']     = vol_summary['avg_cv'].round(2)
vol_summary.to_csv(f'{OUT}/kpi_volatility_summary.csv', index=False)
print(f"kpi_volatility_summary: {len(vol_summary)} rows")

# ── 10. kpi_presence_summary (batch layer) ────────────────────────────────────
# Per-insurer summary of presence_pct across all days.
# Consumed by the dashboard Volatility tab (PRES constant).
pres_summary = (
    presence.groupby(['portal','insurer'])
    .agg(
        avg_presence=('presence_pct', 'mean'),
        min_presence=('presence_pct', 'min'),
    )
    .reset_index()
)
pres_summary['avg_presence'] = pres_summary['avg_presence'].round(2)
pres_summary['min_presence'] = pres_summary['min_presence'].round(2)
pres_summary.to_csv(f'{OUT}/kpi_presence_summary.csv', index=False)
print(f"kpi_presence_summary: {len(pres_summary)} rows")

# ── 11. kpi_hourly_changes (stream layer) ─────────────────────────────────────
# Count of price-change events by (portal, insurer, hour-of-day).
# Consumed by the dashboard Repricing Timing tab (HM constant).
hourly = price_changes.copy()
hourly['hour'] = pd.to_datetime(hourly['scraped_at']).dt.hour
hourly['dow'] = pd.to_datetime(hourly['scraped_at']).dt.dayofweek
kpi_hourly = (
    hourly.groupby(['portal','insurer','dow','hour'])
    .size()
    .reset_index(name='changes')
)
kpi_hourly.to_csv(f'{OUT}/kpi_hourly_changes.csv', index=False)
print(f"kpi_hourly_changes: {len(kpi_hourly)} rows")

# ── 12. kpi_dow_changes (stream layer) ────────────────────────────────────────
# Count of price-change events by (insurer, day-of-week).
# day-of-week follows Python convention: 0=Monday … 6=Sunday.
# Consumed by the dashboard Repricing Timing tab (DOW constant).
dow_ch = price_changes.copy()
dow_ch['dow'] = pd.to_datetime(dow_ch['scraped_at']).dt.dayofweek
kpi_dow = (
    dow_ch.groupby(['portal','insurer','dow'])
    .size()
    .reset_index(name='changes')
)
kpi_dow.to_csv(f'{OUT}/kpi_dow_changes.csv', index=False)
print(f"kpi_dow_changes: {len(kpi_dow)} rows")

print("\nAll tables written to", OUT)
