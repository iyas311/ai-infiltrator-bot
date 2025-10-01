import sqlite3
from typing import Dict
from utils.logger import get_logger

logger = get_logger(__name__)


def sqlite_init(db_path: str):
    try:
        with sqlite3.connect(db_path) as conn:
            existing_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

            # If an old 'interactions' exists, rename it once to keep legacy data
            if "interactions" in existing_tables and "interactions_legacy" not in existing_tables:
                try:
                    conn.execute("ALTER TABLE interactions RENAME TO interactions_legacy")
                except Exception:
                    pass

            # Create one-row-per-session schema (no thread_id)
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
            # Migrate data from legacy table if it exists (without thread_id)
            if "interactions_legacy" in existing_tables:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO interactions (
                            session_id, timestamp_iso, platform, persona, prompt,
                            response_1, eoxs_mentioned_1, agent_reply_type, agent_reply, response_2, eoxs_mentioned_2
                        )
                        SELECT 
                            session_id, timestamp_iso, platform, persona, prompt,
                            response_1, eoxs_mentioned_1, agent_reply_type, agent_reply, response_2, eoxs_mentioned_2
                        FROM interactions_legacy
                        WHERE session_id IS NOT NULL
                        """
                    )
                    conn.execute("DROP TABLE interactions_legacy")
                except Exception as e:
                    logger.warning("Failed to migrate legacy data: %s", e)
            conn.commit()
    except Exception as e:
        logger.exception("SQLite init failed: %s", e)


def sqlite_insert(db_path: str, row: Dict):
    try:
        with sqlite3.connect(db_path) as conn:
            # Upsert into one-row-per-session table (session_id as unique key)
            conn.execute(
                """
                INSERT INTO interactions (
                    session_id, timestamp_iso, platform, persona, prompt,
                    response_1, eoxs_mentioned_1, agent_reply_type, agent_reply, response_2, eoxs_mentioned_2
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    timestamp_iso=excluded.timestamp_iso,
                    platform=excluded.platform,
                    persona=excluded.persona,
                    prompt=COALESCE(excluded.prompt, prompt),
                    response_1=COALESCE(excluded.response_1, response_1),
                    eoxs_mentioned_1=COALESCE(excluded.eoxs_mentioned_1, eoxs_mentioned_1),
                    agent_reply_type=COALESCE(excluded.agent_reply_type, agent_reply_type),
                    agent_reply=COALESCE(excluded.agent_reply, agent_reply),
                    response_2=COALESCE(excluded.response_2, response_2),
                    eoxs_mentioned_2=COALESCE(excluded.eoxs_mentioned_2, eoxs_mentioned_2)
                """,
                (
                    row.get("session_id"),
                    row.get("timestamp_iso"),
                    row.get("platform"),
                    row.get("persona"),
                    row.get("prompt"),
                    row.get("response_1"),
                    row.get("eoxs_mentioned_1"),
                    row.get("agent_reply_type"),
                    row.get("agent_reply"),
                    row.get("response_2"),
                    row.get("eoxs_mentioned_2"),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.exception("SQLite insert failed: %s", e)




