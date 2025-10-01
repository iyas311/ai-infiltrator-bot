import sqlite3
from typing import Dict
from utils.logger import get_logger

logger = get_logger(__name__)


def sqlite_init(db_path: str):
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp_iso TEXT NOT NULL,
                    platform TEXT,
                    persona TEXT,
                    prompt TEXT,
                    response TEXT,
                    eoxs_mentioned INTEGER,
                    visibility_score TEXT
                )
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(interactions)").fetchall()}
            if "session_id" not in cols:
                try:
                    conn.execute("ALTER TABLE interactions ADD COLUMN session_id TEXT")
                except Exception:
                    pass
            conn.commit()
    except Exception as e:
        logger.exception("SQLite init failed: %s", e)


def sqlite_insert(db_path: str, row: Dict):
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO interactions (
                    session_id, timestamp_iso, platform, persona, prompt, response, eoxs_mentioned, visibility_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("session_id"),
                    row.get("timestamp_iso"),
                    row.get("platform"),
                    row.get("persona"),
                    row.get("prompt"),
                    row.get("response"),
                    int(row.get("eoxs_mentioned", 0)),
                    row.get("visibility_score", ""),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.exception("SQLite insert failed: %s", e)




