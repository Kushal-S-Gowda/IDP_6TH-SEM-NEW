# FloodSense Pro — Database Module
# SQLite persistence for alerts, zone risk logs, drill runs
# Drop-in: place this file at project root (same level as app.py)

import sqlite3
import os
from datetime import datetime

DB_PATH = "database/floodsense.db"

def get_conn():
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn

def init_db():
    """
    Create all tables if they don't exist.
    Call once at app startup — safe to call repeatedly (IF NOT EXISTS).
    """
    conn = get_conn()
    c = conn.cursor()

    # ── Table 1: Alert History ──────────────────────────────────────
    # Every alert fired by the early warning system
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            level       TEXT    NOT NULL,   -- RED / AMBER / GREEN / INFO
            signal      TEXT,               -- rainfall / wind / humidity / lake / drain / soil / zone
            zone_name   TEXT,               -- which zone triggered it (nullable)
            message     TEXT    NOT NULL,
            mode        TEXT    DEFAULT 'live',  -- live / drill
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Table 2: Zone Risk Log ──────────────────────────────────────
    # Snapshot of all zone risk levels — written every 30s in live mode
    c.execute("""
        CREATE TABLE IF NOT EXISTS zone_risk_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT    NOT NULL,
            zone_name    TEXT    NOT NULL,
            risk_label   TEXT    NOT NULL,   -- LOW / MEDIUM / HIGH / EXTREME
            risk_class   INTEGER NOT NULL,   -- 0 / 1 / 2 / 3
            rainfall_1h  REAL    DEFAULT 0,
            humidity     REAL    DEFAULT 0,
            wind_kmh     REAL    DEFAULT 0,
            population   INTEGER DEFAULT 0,
            created_at   TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Table 3: Drill Runs ─────────────────────────────────────────
    # Record of every drill executed — useful for evaluation demo
    c.execute("""
        CREATE TABLE IF NOT EXISTS drill_runs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT    NOT NULL,
            scenario_name TEXT    NOT NULL,
            scenario_type TEXT    NOT NULL,   -- natural / manmade
            lead_hours    INTEGER,
            zones_affected INTEGER DEFAULT 0,
            max_risk      TEXT,               -- highest risk level seen
            completed     INTEGER DEFAULT 0,  -- 0=aborted, 1=completed
            created_at    TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    conn.commit()
    conn.close()
    print("✅ FloodSense DB initialised →", DB_PATH)


# ── ALERT FUNCTIONS ─────────────────────────────────────────────────

def log_alert(level, message, signal=None, zone_name=None, mode='live'):
    """Insert one alert into the alerts table."""
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO alerts (timestamp, level, signal, zone_name, message, mode)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%H:%M:%S"),
            level, signal, zone_name, message, mode
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] log_alert error: {e}")

def get_alert_history(limit=50, mode=None):
    """Fetch recent alerts, newest first."""
    try:
        conn = get_conn()
        if mode:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE mode=? ORDER BY id DESC LIMIT ?",
                (mode, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[DB] get_alert_history error: {e}")
        return []

def get_alert_stats():
    """Summary counts for the authority dashboard header."""
    try:
        conn = get_conn()
        total  = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        red    = conn.execute("SELECT COUNT(*) FROM alerts WHERE level='RED'").fetchone()[0]
        amber  = conn.execute("SELECT COUNT(*) FROM alerts WHERE level='AMBER'").fetchone()[0]
        today  = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE DATE(created_at)=DATE('now','localtime')"
        ).fetchone()[0]
        conn.close()
        return {"total": total, "red": red, "amber": amber, "today": today}
    except Exception as e:
        print(f"[DB] get_alert_stats error: {e}")
        return {"total": 0, "red": 0, "amber": 0, "today": 0}


# ── ZONE RISK LOG FUNCTIONS ─────────────────────────────────────────

def log_zone_snapshot(zones):
    """
    Write a risk snapshot for all zones.
    zones: list of dicts with name, risk_label, risk_class, rainfall_1h, humidity, wind_kmh, population
    """
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_conn()
        for z in zones:
            conn.execute("""
                INSERT INTO zone_risk_log
                    (timestamp, zone_name, risk_label, risk_class, rainfall_1h, humidity, wind_kmh, population)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts,
                z.get("name", "Unknown"),
                z.get("risk_label", "LOW"),
                z.get("risk_class", 0),
                z.get("rainfall_1h", 0),
                z.get("humidity", 0),
                z.get("wind_kmh", z.get("wind_speed", 0)),
                z.get("population", 0),
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] log_zone_snapshot error: {e}")

def get_zone_history(zone_name, limit=48):
    """Get risk history for a specific zone — last N snapshots."""
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT timestamp, risk_label, risk_class, rainfall_1h, humidity
            FROM zone_risk_log
            WHERE zone_name=?
            ORDER BY id DESC LIMIT ?
        """, (zone_name, limit)).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]   # chronological order
    except Exception as e:
        print(f"[DB] get_zone_history error: {e}")
        return []

def get_latest_zone_risks():
    """Get the most recent risk entry per zone — for the authority map."""
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT zone_name, risk_label, risk_class, timestamp
            FROM zone_risk_log
            WHERE id IN (
                SELECT MAX(id) FROM zone_risk_log GROUP BY zone_name
            )
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[DB] get_latest_zone_risks error: {e}")
        return []


# ── DRILL RUN FUNCTIONS ─────────────────────────────────────────────

def log_drill_start(scenario_name, scenario_type, lead_hours):
    """Insert a drill run record, return its ID for later update."""
    try:
        conn = get_conn()
        cur = conn.execute("""
            INSERT INTO drill_runs (timestamp, scenario_name, scenario_type, lead_hours, completed)
            VALUES (?, ?, ?, ?, 0)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            scenario_name, scenario_type, lead_hours
        ))
        drill_id = cur.lastrowid
        conn.commit()
        conn.close()
        return drill_id
    except Exception as e:
        print(f"[DB] log_drill_start error: {e}")
        return None

def log_drill_complete(drill_id, zones_affected, max_risk):
    """Mark a drill as completed with final stats."""
    try:
        conn = get_conn()
        conn.execute("""
            UPDATE drill_runs
            SET completed=1, zones_affected=?, max_risk=?
            WHERE id=?
        """, (zones_affected, max_risk, drill_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] log_drill_complete error: {e}")

def get_drill_history(limit=20):
    """Fetch recent drill runs."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM drill_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[DB] get_drill_history error: {e}")
        return []


# ── TEST ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    log_alert("RED",   "TEST: Rainfall 135mm — EXTREME flood risk", signal="rainfall", zone_name="Bellandur")
    log_alert("AMBER", "TEST: Lake level 87% — watch threshold crossed", signal="lake")
    log_alert("INFO",  "System online — all signals nominal")
    log_zone_snapshot([
        {"name": "Bellandur",   "risk_label": "HIGH",   "risk_class": 2, "rainfall_1h": 4.5, "humidity": 88, "wind_kmh": 18, "population": 35000},
        {"name": "HSR Layout",  "risk_label": "MEDIUM", "risk_class": 1, "rainfall_1h": 3.1, "humidity": 82, "wind_kmh": 15, "population": 28000},
        {"name": "Indiranagar", "risk_label": "LOW",    "risk_class": 0, "rainfall_1h": 0.0, "humidity": 65, "wind_kmh": 11, "population": 30000},
    ])
    drill_id = log_drill_start("Extreme Monsoon", "natural", 6)
    log_drill_complete(drill_id, zones_affected=5, max_risk="EXTREME")

    print("\n── Alert History ──────────────────────")
    for a in get_alert_history(): print(f"  [{a['level']}] {a['message']}")
    print("\n── Alert Stats ────────────────────────")
    print(" ", get_alert_stats())
    print("\n── Zone History (Bellandur) ───────────")
    for z in get_zone_history("Bellandur"): print(f"  {z['timestamp']} → {z['risk_label']}")
    print("\n── Drill History ──────────────────────")
    for d in get_drill_history(): print(f"  [{d['scenario_name']}] completed={d['completed']} max={d['max_risk']}")
    print("\n✅ Database module ready!")