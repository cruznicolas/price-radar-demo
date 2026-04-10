"""
notifications.py — Alert dispatch module for the price monitoring platform.

This runs AFTER each scrape + stream layer job completes.
It reads alert_events.csv, finds unacknowledged alerts, and dispatches them.

Usage:
    python notifications.py                      # check and send unacked alerts
    python notifications.py --test               # send a test notification
    python notifications.py --channel slack      # override channel

Channels supported: slack, email, log (default: log, i.e. just print)
Configure via environment variables or config.json.
"""

import os, json, csv, smtplib, sys, argparse
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / 'config.json'
ALERTS_PATH = Path(__file__).parent / 'output/alert_events.csv'
STATE_PATH  = Path(__file__).parent / 'output/notification_state.json'

DEFAULT_CONFIG = {
    "channel": "log",           # "log" | "slack" | "email"
    "slack_webhook_url": "",    # https://hooks.slack.com/services/...
    "email": {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "from_addr": "",
        "to_addrs": [],
        "password_env": "EMAIL_PASSWORD"
    },
    "dedup_window_minutes": 60,  # suppress same alert_type+portal+insurer within this window
    "min_severity": "warning",   # "info" | "warning" | "critical" — filter below this level
    "thresholds": {
        "price_spike_pct": 30,
        "price_drop_pct": -30,
        "market_floor_drop_pct": -20,
        "presence_warning_pct": 80
    }
}

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG

# ── Deduplication state ───────────────────────────────────────────────────────
def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"sent": []}   # list of {key, sent_at}

def save_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def dedup_key(alert):
    return f"{alert['alert_type']}|{alert['portal']}|{alert['insurer']}"

def is_duplicate(alert, state, window_minutes):
    key = dedup_key(alert)
    cutoff = datetime.now() - timedelta(minutes=window_minutes)
    for sent in state['sent']:
        if sent['key'] == key:
            sent_at = datetime.fromisoformat(sent['sent_at'])
            if sent_at > cutoff:
                return True
    return False

def record_sent(alert, state):
    state['sent'].append({
        'key': dedup_key(alert),
        'sent_at': datetime.now().isoformat(),
        'alert_id': alert['alert_id']
    })
    # prune entries older than 24h
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    state['sent'] = [s for s in state['sent'] if s['sent_at'] > cutoff]

# ── Alert formatting ──────────────────────────────────────────────────────────
SEVERITY_EMOJI = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}
SEVERITY_LABEL = {'critical': 'CRITICAL', 'warning': 'WARNING', 'info': 'INFO'}

def format_alert_text(alert):
    emoji  = SEVERITY_EMOJI.get(alert['severity'], '⚪')
    label  = SEVERITY_LABEL.get(alert['severity'], alert['severity'].upper())
    return (
        f"{emoji} [{label}] {alert['alert_type'].upper().replace('_',' ')}\n"
        f"   {alert['detail']}\n"
        f"   Portal: {alert['portal']} | Insurer: {alert['insurer']}\n"
        f"   Fired at: {alert['fired_at']} | Δ {alert['value']:+.1f}%"
    )

def format_slack_payload(alert):
    color = {'critical': '#E24B4A', 'warning': '#EF9F27', 'info': '#378ADD'}.get(alert['severity'], '#888')
    return {
        "attachments": [{
            "color": color,
            "title": f"{SEVERITY_EMOJI[alert['severity']]} {alert['alert_type'].replace('_',' ').title()}",
            "text": alert['detail'],
            "fields": [
                {"title": "Portal",   "value": alert['portal'],  "short": True},
                {"title": "Insurer",  "value": alert['insurer'], "short": True},
                {"title": "Change",   "value": f"{alert['value']:+.1f}%",       "short": True},
                {"title": "Fired at", "value": alert['fired_at'],               "short": True},
            ],
            "footer": "Price Monitor",
            "ts": int(datetime.now().timestamp())
        }]
    }

# ── Dispatch channels ─────────────────────────────────────────────────────────
def send_log(alert):
    print(format_alert_text(alert))

def send_slack(alert, webhook_url):
    import urllib.request
    payload = json.dumps(format_slack_payload(alert)).encode()
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  Slack send failed: {e}")
        return False

def send_email(alert, cfg):
    password = os.environ.get(cfg['email']['password_env'], '')
    if not password:
        print("  Email skipped — no password in env")
        return False
    subject = f"[{alert['severity'].upper()}] Price Alert: {alert['portal']} / {alert['insurer']}"
    body    = format_alert_text(alert)
    msg     = MIMEText(body)
    msg['Subject'] = subject
    msg['From']    = cfg['email']['from_addr']
    msg['To']      = ', '.join(cfg['email']['to_addrs'])
    try:
        with smtplib.SMTP(cfg['email']['smtp_host'], cfg['email']['smtp_port']) as s:
            s.starttls()
            s.login(cfg['email']['from_addr'], password)
            s.sendmail(cfg['email']['from_addr'], cfg['email']['to_addrs'], msg.as_string())
        return True
    except Exception as e:
        print(f"  Email send failed: {e}")
        return False

def dispatch(alert, cfg):
    channel = cfg['channel']
    if channel == 'slack' and cfg.get('slack_webhook_url'):
        ok = send_slack(alert, cfg['slack_webhook_url'])
        if not ok: send_log(alert)   # fallback
    elif channel == 'email' and cfg['email'].get('to_addrs'):
        ok = send_email(alert, cfg)
        if not ok: send_log(alert)
    else:
        send_log(alert)

# ── Severity filter ───────────────────────────────────────────────────────────
SEVERITY_RANK = {'info': 0, 'warning': 1, 'critical': 2}

def meets_min_severity(alert, min_sev):
    return SEVERITY_RANK.get(alert['severity'], 0) >= SEVERITY_RANK.get(min_sev, 0)

# ── Main ──────────────────────────────────────────────────────────────────────
def run(args):
    cfg   = load_config()
    if args.channel:
        cfg['channel'] = args.channel

    if args.test:
        fake = {
            'alert_id': 0, 'alert_type': 'price_spike', 'severity': 'critical',
            'portal': 'Falabella', 'insurer': 'TestCo',
            'fired_at': datetime.now().isoformat()[:16],
            'value': 63.4, 'detail': 'TestCo on Falabella: 30000 → 49000 (+63.4%)'
        }
        print("Sending test alert...")
        dispatch(fake, cfg)
        return

    if not ALERTS_PATH.exists():
        print("No alert_events.csv found.")
        return

    # Load alerts
    alerts = []
    with open(ALERTS_PATH) as f:
        for row in csv.DictReader(f):
            row['value'] = float(row['value'])
            row['alert_id'] = int(row['alert_id'])
            row['acknowledged'] = row['acknowledged'].lower() == 'true'
            alerts.append(row)

    unacked = [a for a in alerts if not a['acknowledged']]
    filtered = [a for a in unacked if meets_min_severity(a, cfg['min_severity'])]

    print(f"Total alerts: {len(alerts)} | Unacked: {len(unacked)} | Above min_severity: {len(filtered)}")

    state = load_state()
    sent_count = 0

    for alert in filtered:
        if is_duplicate(alert, state, cfg['dedup_window_minutes']):
            continue
        dispatch(alert, cfg)
        record_sent(alert, state)
        sent_count += 1

    save_state(state)
    print(f"Dispatched {sent_count} notifications via [{cfg['channel']}]")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Price monitor notifications')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--channel', choices=['log', 'slack', 'email'])
    args = parser.parse_args()
    run(args)
