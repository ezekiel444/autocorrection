"""SQLite database layer with async CRUD operations.

Provides schema initialization, connection management, and all database
operations for correction history, feedback, dictionaries, and plugin state.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

from .models import (
    AggregatedFeedback,
    CorrectionHistoryEntry,
    CorrectionType,
    FeedbackEntry,
)

# SQL schema for all tables
SCHEMA_SQL = """
-- Correction History
CREATE TABLE IF NOT EXISTS correction_history (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    original_text TEXT NOT NULL,
    corrected_text TEXT NOT NULL,
    correction_type TEXT NOT NULL,
    source_context TEXT,
    corrections_applied INTEGER DEFAULT 0,
    confidence_avg REAL DEFAULT 0.0,
    expires_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_history_timestamp ON correction_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_history_type ON correction_history(correction_type);
CREATE INDEX IF NOT EXISTS idx_history_expires ON correction_history(expires_at);

-- Feedback Store
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    original_text TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    correction_type TEXT NOT NULL,
    signal TEXT NOT NULL CHECK(signal IN ('positive', 'negative')),
    context TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_signal ON feedback(signal);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(correction_type);

-- Aggregated Feedback (for entries > 90 days old when count > 10,000)
CREATE TABLE IF NOT EXISTS aggregated_feedback (
    pattern_hash TEXT PRIMARY KEY,
    correction_type TEXT NOT NULL,
    signal TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    last_seen DATETIME NOT NULL,
    sample_original TEXT,
    sample_suggestion TEXT
);

-- Custom Dictionaries
CREATE TABLE IF NOT EXISTS dictionaries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER DEFAULT 1,
    term_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dictionary_terms (
    id TEXT PRIMARY KEY,
    dictionary_id TEXT NOT NULL REFERENCES dictionaries(id),
    term TEXT NOT NULL,
    definition TEXT,
    UNIQUE(dictionary_id, term)
);

CREATE INDEX IF NOT EXISTS idx_terms_dict ON dictionary_terms(dictionary_id);
CREATE INDEX IF NOT EXISTS idx_terms_term ON dictionary_terms(term COLLATE NOCASE);

-- Plugin State
CREATE TABLE IF NOT EXISTS plugin_state (
    name TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    last_loaded DATETIME,
    error_count INTEGER DEFAULT 0,
    last_error TEXT
);
"""


class Database:
    """Async SQLite database manager for the Correction Engine.

    Handles connection lifecycle, schema initialization, and provides
    CRUD operations for all data entities.
    """

    def __init__(self, db_path: str = ":memory:"):
        """Initialize database with the given path.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory.
        """
        self._db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open database connection and initialize schema."""
        self._connection = await aiosqlite.connect(self._db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._initialize_schema()

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _initialize_schema(self) -> None:
        """Create all tables and indexes if they don't exist."""
        assert self._connection is not None
        await self._connection.executescript(SCHEMA_SQL)
        await self._connection.commit()

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the active database connection."""
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    # ─── Correction History CRUD ─────────────────────────────────────────

    async def add_history_entry(
        self,
        original_text: str,
        corrected_text: str,
        correction_type: CorrectionType,
        source_context: str,
        corrections_applied: int,
        confidence_avg: float,
        retention_days: int = 30,
    ) -> CorrectionHistoryEntry:
        """Insert a new correction history entry.

        Args:
            original_text: The original text before correction.
            corrected_text: The text after corrections applied.
            correction_type: Primary type of correction.
            source_context: Application context (app name + surrounding chars).
            corrections_applied: Number of corrections applied.
            confidence_avg: Average confidence of applied corrections.
            retention_days: Days before automatic cleanup.

        Returns:
            The created CorrectionHistoryEntry.
        """
        entry_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(days=retention_days)

        await self.connection.execute(
            """INSERT INTO correction_history
               (id, timestamp, original_text, corrected_text, correction_type,
                source_context, corrections_applied, confidence_avg, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                now.isoformat(),
                original_text,
                corrected_text,
                correction_type.value,
                source_context,
                corrections_applied,
                round(confidence_avg, 2),
                expires_at.isoformat(),
            ),
        )
        await self.connection.commit()

        return CorrectionHistoryEntry(
            id=entry_id,
            timestamp=now,
            original_text=original_text,
            corrected_text=corrected_text,
            correction_type=correction_type,
            source_context=source_context,
            corrections_applied=corrections_applied,
            confidence_avg=round(confidence_avg, 2),
        )

    async def get_history(
        self,
        page: int = 1,
        per_page: int = 50,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        correction_type: Optional[CorrectionType] = None,
    ) -> tuple[list[CorrectionHistoryEntry], int]:
        """Query correction history with pagination and filters.

        Args:
            page: Page number (1-indexed).
            per_page: Number of entries per page.
            date_from: Filter entries after this date.
            date_to: Filter entries before this date.
            correction_type: Filter by correction type.

        Returns:
            Tuple of (entries list, total count).
        """
        conditions = []
        params: list = []

        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from.isoformat())
        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to.isoformat())
        if correction_type:
            conditions.append("correction_type = ?")
            params.append(correction_type.value)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM correction_history {where_clause}"
        async with self.connection.execute(count_sql, params) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        # Get paginated results
        offset = (page - 1) * per_page
        query_sql = f"""
            SELECT * FROM correction_history {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        query_params = params + [per_page, offset]

        entries = []
        async with self.connection.execute(query_sql, query_params) as cursor:
            async for row in cursor:
                entries.append(
                    CorrectionHistoryEntry(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        original_text=row["original_text"],
                        corrected_text=row["corrected_text"],
                        correction_type=CorrectionType(row["correction_type"]),
                        source_context=row["source_context"] or "",
                        corrections_applied=row["corrections_applied"],
                        confidence_avg=row["confidence_avg"],
                    )
                )

        return entries, total

    async def get_history_entry(self, entry_id: str) -> Optional[CorrectionHistoryEntry]:
        """Get a single history entry by ID.

        Args:
            entry_id: The unique identifier of the entry.

        Returns:
            The entry if found, None otherwise.
        """
        async with self.connection.execute(
            "SELECT * FROM correction_history WHERE id = ?", (entry_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return CorrectionHistoryEntry(
                id=row["id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                original_text=row["original_text"],
                corrected_text=row["corrected_text"],
                correction_type=CorrectionType(row["correction_type"]),
                source_context=row["source_context"] or "",
                corrections_applied=row["corrections_applied"],
                confidence_avg=row["confidence_avg"],
            )

    async def delete_expired_history(self) -> int:
        """Remove history entries past their retention date.

        Returns:
            Number of entries deleted.
        """
        now = datetime.utcnow().isoformat()
        async with self.connection.execute(
            "DELETE FROM correction_history WHERE expires_at <= ?", (now,)
        ) as cursor:
            deleted = cursor.rowcount
        await self.connection.commit()
        return deleted

    async def get_all_history_for_export(self) -> list[CorrectionHistoryEntry]:
        """Get all history entries for JSON export.

        Returns:
            All history entries ordered by timestamp descending.
        """
        entries = []
        async with self.connection.execute(
            "SELECT * FROM correction_history ORDER BY timestamp DESC"
        ) as cursor:
            async for row in cursor:
                entries.append(
                    CorrectionHistoryEntry(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        original_text=row["original_text"],
                        corrected_text=row["corrected_text"],
                        correction_type=CorrectionType(row["correction_type"]),
                        source_context=row["source_context"] or "",
                        corrections_applied=row["corrections_applied"],
                        confidence_avg=row["confidence_avg"],
                    )
                )
        return entries

    # ─── Feedback CRUD ───────────────────────────────────────────────────

    async def add_feedback(
        self,
        original_text: str,
        suggestion: str,
        correction_type: CorrectionType,
        signal: str,
        context: Optional[str] = None,
    ) -> FeedbackEntry:
        """Record user feedback on a correction.

        Args:
            original_text: The original text that was corrected.
            suggestion: The correction suggestion.
            correction_type: Type of correction.
            signal: "positive" (accepted) or "negative" (rejected).
            context: Optional context information.

        Returns:
            The created FeedbackEntry.
        """
        if signal not in ("positive", "negative"):
            raise ValueError("Signal must be 'positive' or 'negative'")

        entry_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self.connection.execute(
            """INSERT INTO feedback
               (id, timestamp, original_text, suggestion, correction_type, signal, context)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                now.isoformat(),
                original_text,
                suggestion,
                correction_type.value,
                signal,
                context,
            ),
        )
        await self.connection.commit()

        return FeedbackEntry(
            id=entry_id,
            timestamp=now,
            original_text=original_text,
            suggestion=suggestion,
            correction_type=correction_type,
            signal=signal,
            context=context,
        )

    async def get_feedback_for_pattern(
        self, original_text: str, correction_type: CorrectionType
    ) -> list[FeedbackEntry]:
        """Query feedback entries matching a correction pattern.

        Args:
            original_text: The original text to match.
            correction_type: The correction type to match.

        Returns:
            List of matching feedback entries.
        """
        entries = []
        async with self.connection.execute(
            """SELECT * FROM feedback
               WHERE original_text = ? AND correction_type = ?
               ORDER BY timestamp DESC""",
            (original_text, correction_type.value),
        ) as cursor:
            async for row in cursor:
                entries.append(
                    FeedbackEntry(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        original_text=row["original_text"],
                        suggestion=row["suggestion"],
                        correction_type=CorrectionType(row["correction_type"]),
                        signal=row["signal"],
                        context=row["context"],
                    )
                )
        return entries

    async def get_feedback_count(self) -> int:
        """Get total number of feedback entries.

        Returns:
            Total count of feedback entries.
        """
        async with self.connection.execute("SELECT COUNT(*) FROM feedback") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_feedback_page(
        self, page: int = 1, per_page: int = 50
    ) -> tuple[list[FeedbackEntry], int]:
        """Get paginated feedback entries.

        Args:
            page: Page number (1-indexed).
            per_page: Entries per page.

        Returns:
            Tuple of (entries list, total count).
        """
        total = await self.get_feedback_count()
        offset = (page - 1) * per_page

        entries = []
        async with self.connection.execute(
            "SELECT * FROM feedback ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        ) as cursor:
            async for row in cursor:
                entries.append(
                    FeedbackEntry(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        original_text=row["original_text"],
                        suggestion=row["suggestion"],
                        correction_type=CorrectionType(row["correction_type"]),
                        signal=row["signal"],
                        context=row["context"],
                    )
                )
        return entries, total

    async def delete_feedback(self, entry_id: str) -> bool:
        """Delete a single feedback entry.

        Args:
            entry_id: The ID of the entry to delete.

        Returns:
            True if deleted, False if not found.
        """
        async with self.connection.execute(
            "DELETE FROM feedback WHERE id = ?", (entry_id,)
        ) as cursor:
            deleted = cursor.rowcount > 0
        await self.connection.commit()
        return deleted

    async def aggregate_old_feedback(self, days_threshold: int = 90) -> int:
        """Aggregate feedback entries older than threshold.

        Entries older than the threshold with identical patterns are
        consolidated into aggregated_feedback records.

        Args:
            days_threshold: Age in days after which to aggregate.

        Returns:
            Number of entries aggregated.
        """
        import hashlib

        cutoff = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()

        # Get old entries grouped by pattern
        async with self.connection.execute(
            """SELECT original_text, correction_type, signal, COUNT(*) as cnt,
                      MAX(timestamp) as last_seen
               FROM feedback
               WHERE timestamp < ?
               GROUP BY original_text, correction_type, signal""",
            (cutoff,),
        ) as cursor:
            aggregated_count = 0
            async for row in cursor:
                pattern_key = f"{row['original_text']}:{row['correction_type']}:{row['signal']}"
                pattern_hash = hashlib.sha256(pattern_key.encode()).hexdigest()[:32]

                await self.connection.execute(
                    """INSERT INTO aggregated_feedback
                       (pattern_hash, correction_type, signal, occurrence_count,
                        last_seen, sample_original)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(pattern_hash) DO UPDATE SET
                         occurrence_count = occurrence_count + excluded.occurrence_count,
                         last_seen = excluded.last_seen""",
                    (
                        pattern_hash,
                        row["correction_type"],
                        row["signal"],
                        row["cnt"],
                        row["last_seen"],
                        row["original_text"],
                    ),
                )
                aggregated_count += row["cnt"]

        # Delete the aggregated raw entries
        await self.connection.execute(
            "DELETE FROM feedback WHERE timestamp < ?", (cutoff,)
        )
        await self.connection.commit()
        return aggregated_count

    # ─── Dictionary CRUD ─────────────────────────────────────────────────

    async def create_dictionary(self, name: str) -> str:
        """Create a new custom dictionary.

        Args:
            name: Unique name for the dictionary.

        Returns:
            The ID of the created dictionary.
        """
        dict_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        await self.connection.execute(
            """INSERT INTO dictionaries (id, name, is_active, term_count, created_at, updated_at)
               VALUES (?, ?, 1, 0, ?, ?)""",
            (dict_id, name, now, now),
        )
        await self.connection.commit()
        return dict_id

    async def add_dictionary_term(
        self, dictionary_id: str, term: str, definition: Optional[str] = None
    ) -> str:
        """Add a term to a dictionary.

        Args:
            dictionary_id: The dictionary to add the term to.
            term: The term text.
            definition: Optional definition.

        Returns:
            The ID of the created term entry.
        """
        term_id = str(uuid.uuid4())

        await self.connection.execute(
            """INSERT OR IGNORE INTO dictionary_terms (id, dictionary_id, term, definition)
               VALUES (?, ?, ?, ?)""",
            (term_id, dictionary_id, term, definition),
        )

        # Update term count
        await self.connection.execute(
            """UPDATE dictionaries SET term_count = (
                 SELECT COUNT(*) FROM dictionary_terms WHERE dictionary_id = ?
               ), updated_at = ? WHERE id = ?""",
            (dictionary_id, datetime.utcnow().isoformat(), dictionary_id),
        )
        await self.connection.commit()
        return term_id

    async def get_active_dictionary_terms(self) -> set[str]:
        """Get all terms from active dictionaries (case-insensitive).

        Returns:
            Set of lowercase terms from all active dictionaries.
        """
        terms: set[str] = set()
        async with self.connection.execute(
            """SELECT dt.term FROM dictionary_terms dt
               JOIN dictionaries d ON dt.dictionary_id = d.id
               WHERE d.is_active = 1"""
        ) as cursor:
            async for row in cursor:
                terms.add(row["term"].lower())
        return terms

    async def set_dictionary_active(self, dictionary_id: str, active: bool) -> None:
        """Activate or deactivate a dictionary.

        Args:
            dictionary_id: The dictionary to modify.
            active: Whether to activate (True) or deactivate (False).
        """
        await self.connection.execute(
            "UPDATE dictionaries SET is_active = ? WHERE id = ?",
            (1 if active else 0, dictionary_id),
        )
        await self.connection.commit()

    # ─── Plugin State CRUD ───────────────────────────────────────────────

    async def update_plugin_state(
        self,
        name: str,
        enabled: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Update or create plugin state record.

        Args:
            name: Plugin name.
            enabled: Whether the plugin is enabled.
            error: Error message if plugin failed to load.
        """
        now = datetime.utcnow().isoformat()

        if error:
            await self.connection.execute(
                """INSERT INTO plugin_state (name, enabled, last_loaded, error_count, last_error)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     enabled = excluded.enabled,
                     error_count = error_count + 1,
                     last_error = excluded.last_error""",
                (name, 0, now, error),
            )
        else:
            await self.connection.execute(
                """INSERT INTO plugin_state (name, enabled, last_loaded, error_count, last_error)
                   VALUES (?, ?, ?, 0, NULL)
                   ON CONFLICT(name) DO UPDATE SET
                     enabled = excluded.enabled,
                     last_loaded = excluded.last_loaded,
                     error_count = 0,
                     last_error = NULL""",
                (name, 1 if enabled else 0, now),
            )
        await self.connection.commit()

    async def get_plugin_state(self, name: str) -> Optional[dict]:
        """Get plugin state by name.

        Args:
            name: Plugin name.

        Returns:
            Dict with plugin state or None if not found.
        """
        async with self.connection.execute(
            "SELECT * FROM plugin_state WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "name": row["name"],
                "enabled": bool(row["enabled"]),
                "last_loaded": row["last_loaded"],
                "error_count": row["error_count"],
                "last_error": row["last_error"],
            }
