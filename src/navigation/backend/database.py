import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "patrol.db"


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            x REAL,
            y REAL,
            yaw REAL,
            temperature REAL,
            humidity REAL,
            noise REAL,
            gas REAL
        )
        """
    )
    conn.commit()
    conn.close()


def insert_status(timestamp, x, y, yaw, temperature=None,
                  humidity=None, noise=None, gas=None):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO robot_status
        (timestamp, x, y, yaw, temperature, humidity, noise, gas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, x, y, yaw, temperature, humidity, noise, gas),
    )
    conn.commit()
    conn.close()


def get_latest_status():
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM robot_status ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None
