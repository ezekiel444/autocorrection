"""Correction History Module - SQLite-based storage for correction records.

Stores all successful corrections with timestamps, original/corrected text,
individual corrections as JSON, and detected language.
Database is stored at ~/.autocorrect_history.db.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional


DB_PATH = os.path.join(os.path.expanduser("~"), ".autocorrect_history.db")


def _get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a SQLite connection, creating the table if needed."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS correction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            original_text TEXT NOT NULL,
            corrected_text TEXT NOT NULL,
            corrections_json TEXT NOT NULL,
            language TEXT
        )
    """)
    conn.commit()
    return conn


def save_correction(
    original_text: str,
    corrected_text: str,
    corrections: list[dict],
    language: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    """Save a correction record to the database.

    Args:
        original_text: The original text before correction.
        corrected_text: The text after corrections applied.
        corrections: List of correction dicts from the LLM.
        language: Detected language of the text (optional).
        db_path: Override database path (for testing).

    Returns:
        The row ID of the inserted record.
    """
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO correction_history
                (timestamp, original_text, corrected_text, corrections_json, language)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                original_text,
                corrected_text,
                json.dumps(corrections, ensure_ascii=False),
                language,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_history(limit: int = 50, db_path: Optional[str] = None) -> list[dict]:
    """Retrieve recent correction history.

    Args:
        limit: Maximum number of records to return (default 50).
        db_path: Override database path (for testing).

    Returns:
        List of correction records as dicts, most recent first.
    """
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, original_text, corrected_text,
                   corrections_json, language
            FROM correction_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "original_text": row["original_text"],
                "corrected_text": row["corrected_text"],
                "corrections": json.loads(row["corrections_json"]),
                "language": row["language"],
            })
        return results
    finally:
        conn.close()


def clear_history(db_path: Optional[str] = None) -> int:
    """Clear all correction history.

    Args:
        db_path: Override database path (for testing).

    Returns:
        Number of records deleted.
    """
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute("DELETE FROM correction_history")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
