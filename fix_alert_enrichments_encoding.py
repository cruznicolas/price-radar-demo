#!/usr/bin/env python3
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "output"
CACHE = OUT / "llm_cache"


def load_csv(name: str) -> list[dict]:
    with open(OUT / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_date(value: str):
    return datetime.fromisoformat(value).date()


def fnum(value: str):
    try:
        return float(value)
    except Exception:
        return None


def select_period(rows: list[dict], end_date, days: int = 7) -> list[dict]:
    start_date = end_date - timedelta(days=days)
    selected = []
    for row in rows:
        row_date = parse_date(row["date"])
        if start_date <= row_date <= end_date:
            selected.append(row)
    return selected


def build_indexes():
    price_stats = load_csv("kpi_price_stats.csv")
    presence = load_csv("kpi_presence_rate.csv")
    win_rates = load_csv("kpi_win_rates.csv")
    market_floor = load_csv("kpi_market_floor.csv")

    ps_idx = defaultdict(list)
    for row in price_stats:
        ps_idx[(row["portal"], row["insurer"])].append(row)

    pr_idx = defaultdict(list)
    for row in presence:
        pr_idx[(row["portal"], row["insurer"])].append(row)

    wr_idx = defaultdict(list)
    for row in win_rates:
        if row["window"] == "7d":
            wr_idx[(row["portal"], row["insurer"])].append(row)

    mf_idx = defaultdict(list)
    for row in market_floor:
        mf_idx[row["portal"]].append(row)

    for idx in (ps_idx, pr_idx, wr_idx, mf_idx):
        for key in idx:
            idx[key].sort(key=lambda row: row["date"])

    return ps_idx, pr_idx, wr_idx, mf_idx


def insurer_text(alert: dict, ps_idx, pr_idx, wr_idx) -> str:
    portal = alert["portal"]
    insurer = alert["insurer"]
    end_date = parse_date(alert["fired_at"])
    ps = select_period(ps_idx[(portal, insurer)], end_date)
    pr = select_period(pr_idx[(portal, insurer)], end_date)
    wr = select_period(wr_idx[(portal, insurer)], end_date)
    value = fnum(alert["value"]) or 0.0
    move_up = value > 0

    cvs = [fnum(row["cv"]) for row in ps if fnum(row["cv"]) is not None]
    medians = [fnum(row["median"]) for row in ps if fnum(row["median"]) is not None]
    mins = [fnum(row["min_price"]) for row in ps if fnum(row["min_price"]) is not None]
    maxs = [fnum(row["max_price"]) for row in ps if fnum(row["max_price"]) is not None]
    pres = [fnum(row["presence_pct"]) for row in pr if fnum(row["presence_pct"]) is not None]
    wins = [fnum(row["win_rate"]) for row in wr if fnum(row["win_rate"]) is not None]

    avg_cv = sum(cvs) / len(cvs) if cvs else None
    latest_win = wins[-1] if wins else None
    stable = avg_cv is not None and avg_cv < 2
    volatile = avg_cv is not None and avg_cv >= 8
    dominant = latest_win is not None and latest_win >= 60
    uneven_presence = any(value is not None and value < 80 for value in pres)
    wide_day = False
    if mins and maxs and medians and medians[-1]:
        wide_day = ((maxs[-1] - mins[-1]) / medians[-1]) > 0.25

    if move_up:
        if stable and not dominant:
            s1 = f"En los d\u00edas previos, {insurer} ven\u00eda mostrando un patr\u00f3n relativamente estable en {portal}, por lo que este salto luce m\u00e1s como un ajuste t\u00e1ctico puntual que como un cambio estructural de posicionamiento."
        elif volatile:
            s1 = f"{insurer} ya ven\u00eda operando con alta dispersi\u00f3n de precios en {portal}, de modo que este salto encaja con un patr\u00f3n de repricing agresivo m\u00e1s que con una ruptura totalmente nueva."
        elif dominant:
            s1 = f"Aunque {insurer} ya ten\u00eda una posici\u00f3n competitiva fuerte en {portal}, este salto apunta m\u00e1s a una correcci\u00f3n t\u00e1ctica dentro de su estrategia que a una p\u00e9rdida inmediata de liderazgo."
        else:
            s1 = f"El movimiento alcista de {insurer} en {portal} aparece por encima de su comportamiento reciente y sugiere un ajuste puntual de precio m\u00e1s que una tendencia ya consolidada en la semana."

        if wide_day:
            s2 = "La amplitud observada entre m\u00ednimo y m\u00e1ximo diario refuerza la hip\u00f3tesis de una se\u00f1al transitoria o de una calibraci\u00f3n intradiaria todav\u00eda no asentada."
        elif uneven_presence:
            s2 = "Como su presencia reciente no fue completamente uniforme, conviene leer este cambio junto con la continuidad de publicaci\u00f3n y no solo por nivel de precio."
        else:
            s2 = "Por ahora, la lectura m\u00e1s prudente es de repricing t\u00e1ctico y no necesariamente de un nuevo rango estable para la aseguradora."

        s3 = f"Lo clave ahora es monitorear si el nuevo nivel se sostiene en las pr\u00f3ximas corridas o si revierte r\u00e1pidamente hacia su rango habitual en {portal}."
    else:
        if stable and dominant:
            s1 = f"Esta ca\u00edda rompe una secuencia bastante estable de {insurer} en {portal} y sugiere una decisi\u00f3n competitiva deliberada m\u00e1s que ruido operativo."
        elif volatile:
            s1 = f"Dado que {insurer} ya ven\u00eda mostrando una volatilidad elevada en {portal}, esta baja se entiende mejor como una reversi\u00f3n fuerte dentro de un patr\u00f3n de repricing agresivo."
        elif stable:
            s1 = f"Como {insurer} ven\u00eda transando con baja dispersi\u00f3n en {portal}, la magnitud de esta ca\u00edda destaca frente a su comportamiento reciente y sugiere un cambio t\u00e1ctico relevante."
        else:
            s1 = f"La baja de {insurer} en {portal} aparece como una correcci\u00f3n significativa respecto de su trayectoria reciente y merece leerse como una se\u00f1al competitiva m\u00e1s que como ruido menor."

        if dominant:
            s2 = "Si el nuevo nivel persiste, el efecto m\u00e1s probable es un refuerzo de su liderazgo y una mayor presi\u00f3n sobre el resto del mercado del portal."
        elif wide_day:
            s2 = "La dispersi\u00f3n intradiaria del mismo d\u00eda sugiere adem\u00e1s que podr\u00eda tratarse de una reversi\u00f3n r\u00e1pida despu\u00e9s de haber transitado temporalmente por un nivel inflado."
        else:
            s2 = "La se\u00f1al todav\u00eda requiere validaci\u00f3n, porque no est\u00e1 claro si estamos frente a un nuevo piso estable o a un ajuste de corta duraci\u00f3n."

        s3 = f"La m\u00e9trica a seguir es si el precio logra sostenerse cerca del nuevo nivel en las pr\u00f3ximas corridas y si provoca reacci\u00f3n defensiva de otros actores en {portal}."

    return " ".join([s1, s2, s3])


def market_floor_text(alert: dict, mf_idx) -> str:
    portal = alert["portal"]
    end_date = parse_date(alert["fired_at"])
    rows = select_period(mf_idx[portal], end_date)
    floors = [fnum(row["floor_price"]) for row in rows if fnum(row["floor_price"]) is not None]
    deltas = [fnum(row["floor_delta_pct"]) for row in rows if fnum(row["floor_delta_pct"]) is not None]
    repeated = sum(1 for delta in deltas if delta is not None and delta <= -20) >= 2
    trending_down = len(floors) >= 2 and floors[-1] <= min(floors[:-1])

    if repeated:
        s1 = f"Esta ca\u00edda del piso de mercado en {portal} no luce completamente aislada, sino consistente con una semana donde ya hubo episodios de ajuste brusco en el nivel m\u00ednimo disponible."
    elif trending_down:
        s1 = f"La baja del piso de mercado en {portal} profundiza una trayectoria descendente reciente y sugiere un endurecimiento de la presi\u00f3n competitiva a nivel portal."
    else:
        s1 = f"La ca\u00edda del piso de mercado en {portal} destaca frente al comportamiento reciente y apunta a una descompresi\u00f3n competitiva relevante m\u00e1s que a una variaci\u00f3n marginal."

    if portal == "Santander":
        s2 = "Dado el dominio que Sura viene mostrando en este canal, una compresi\u00f3n de esta magnitud suele ser se\u00f1al de un ajuste del l\u00edder o de una respuesta directa al nivel del l\u00edder."
    else:
        s2 = "En Falabella, donde la competencia viene siendo m\u00e1s t\u00e1ctica y fragmentada, este tipo de movimiento suele reflejar reposicionamientos r\u00e1pidos entre los actores que est\u00e1n disputando el piso efectivo."

    s3 = f"Lo importante ahora es observar si el nuevo piso se sostiene en las siguientes corridas y si arrastra una correcci\u00f3n coordinada del resto del mercado en {portal}."
    return " ".join([s1, s2, s3])


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    alerts = [row for row in load_csv("alert_events.csv") if row["severity"] == "critical"]
    ps_idx, pr_idx, wr_idx, mf_idx = build_indexes()

    summary_lines = ["# Demo critical alert enrichments", ""]
    for alert in alerts:
        text = (
            market_floor_text(alert, mf_idx)
            if alert["insurer"] == "ALL"
            else insurer_text(alert, ps_idx, pr_idx, wr_idx)
        )
        path = CACHE / f"alert_{alert['alert_id']}.txt"
        path.write_text(text, encoding="utf-8")
        summary_lines.append(f"## alert_{alert['alert_id']}.txt")
        summary_lines.append("")
        summary_lines.append(text)
        summary_lines.append("")

    (CACHE / "demo_alert_enrichments_all_critical.md").write_text(
        "\n".join(summary_lines), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
