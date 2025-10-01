import sqlite3
from typing import Dict
from utils.logger import get_logger

logger = get_logger(__name__)


def sqlite_init(db_path: str):
    """Simple table creation - no migration logic"""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE,
                    timestamp_iso TEXT NOT NULL,
                    platform TEXT,
                    persona TEXT,
                    prompt TEXT,
                    response_1 TEXT,
                    eoxs_mentioned_1 INTEGER,
                    agent_reply_type TEXT,
                    agent_reply TEXT,
                    response_2 TEXT,
                    eoxs_mentioned_2 INTEGER
                )
                """
            )
            conn.commit()
    except Exception as e:
        logger.exception("SQLite init failed: %s", e)


def sqlite_insert(db_path: str, row: Dict):
    """Simple insert - just add new data"""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO interactions (
                    session_id, timestamp_iso, platform, persona, prompt,
                    response_1, eoxs_mentioned_1, agent_reply_type, agent_reply, response_2, eoxs_mentioned_2
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("session_id"),
                    row.get("timestamp_iso"),
                    row.get("platform"),
                    row.get("persona"),
                    row.get("prompt"),
                    row.get("response_1", ""),
                    row.get("eoxs_mentioned_1", 0),
                    row.get("agent_reply_type", "none"),
                    row.get("agent_reply", ""),
                    row.get("response_2", ""),
                    row.get("eoxs_mentioned_2", 0),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.exception("SQLite insert failed: %s", e)


def sqlite_update_second_response(db_path: str, session_id: str, response_2: str, eoxs_mentioned_2: int):
    """Update only the second response fields"""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE interactions 
                SET response_2 = ?, eoxs_mentioned_2 = ?
                WHERE session_id = ?
                """,
                (response_2, eoxs_mentioned_2, session_id)
            )
            conn.commit()
    except Exception as e:
        logger.exception("SQLite update failed: %s", e)