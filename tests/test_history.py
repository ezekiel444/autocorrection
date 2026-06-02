"""Tests for the correction history module.

Tests save, retrieve, and clear operations on the SQLite history database.
Uses a temporary database file for isolation.
"""

import json
import os
import tempfile

import pytest

from app.history import save_correction, get_history, clear_history


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


class TestSaveCorrection:
    """Tests for the save_correction function."""

    def test_save_basic_correction(self, temp_db):
        """Save a basic correction and verify it returns a valid ID."""
        corrections = [
            {
                "original_text": "teh",
                "suggested_text": "the",
                "correction_type": "spelling",
                "reason": "Common misspelling",
                "confidence": 0.95,
            }
        ]
        row_id = save_correction(
            original_text="I went to teh store",
            corrected_text="I went to the store",
            corrections=corrections,
            language="en",
            db_path=temp_db,
        )
        assert row_id is not None
        assert row_id > 0

    def test_save_multiple_corrections(self, temp_db):
        """Save multiple corrections in one record."""
        corrections = [
            {"original_text": "buyed", "suggested_text": "bought"},
            {"original_text": "stor", "suggested_text": "store"},
        ]
        row_id = save_correction(
            original_text="I buyed from the stor",
            corrected_text="I bought from the store",
            corrections=corrections,
            db_path=temp_db,
        )
        assert row_id > 0

    def test_save_without_language(self, temp_db):
        """Save a correction without specifying language."""
        row_id = save_correction(
            original_text="test",
            corrected_text="test",
            corrections=[],
            db_path=temp_db,
        )
        assert row_id > 0

    def test_save_increments_id(self, temp_db):
        """Each save should return an incrementing ID."""
        id1 = save_correction("a", "b", [{"x": "y"}], db_path=temp_db)
        id2 = save_correction("c", "d", [{"x": "y"}], db_path=temp_db)
        assert id2 > id1


class TestGetHistory:
    """Tests for the get_history function."""

    def test_empty_history(self, temp_db):
        """Empty database should return empty list."""
        records = get_history(db_path=temp_db)
        assert records == []

    def test_get_saved_records(self, temp_db):
        """Saved corrections should be retrievable."""
        corrections = [
            {"original_text": "helo", "suggested_text": "hello"}
        ]
        save_correction(
            original_text="helo world",
            corrected_text="hello world",
            corrections=corrections,
            language="en",
            db_path=temp_db,
        )

        records = get_history(db_path=temp_db)
        assert len(records) == 1
        record = records[0]
        assert record["original_text"] == "helo world"
        assert record["corrected_text"] == "hello world"
        assert record["language"] == "en"
        assert record["corrections"] == corrections
        assert "timestamp" in record
        assert "id" in record

    def test_limit_parameter(self, temp_db):
        """Limit should cap the number of returned records."""
        for i in range(10):
            save_correction(f"text {i}", f"fixed {i}", [], db_path=temp_db)

        records = get_history(limit=3, db_path=temp_db)
        assert len(records) == 3

    def test_most_recent_first(self, temp_db):
        """Records should be returned most recent first."""
        save_correction("first", "first_fixed", [], db_path=temp_db)
        save_correction("second", "second_fixed", [], db_path=temp_db)
        save_correction("third", "third_fixed", [], db_path=temp_db)

        records = get_history(db_path=temp_db)
        assert records[0]["original_text"] == "third"
        assert records[1]["original_text"] == "second"
        assert records[2]["original_text"] == "first"

    def test_corrections_json_roundtrip(self, temp_db):
        """Complex corrections should survive JSON serialization."""
        corrections = [
            {
                "original_text": "café",
                "suggested_text": "café",
                "correction_type": "spelling",
                "reason": "Unicode test",
                "confidence": 0.99,
                "start_offset": 0,
                "end_offset": 4,
            }
        ]
        save_correction("café", "café", corrections, language="fr", db_path=temp_db)

        records = get_history(db_path=temp_db)
        assert records[0]["corrections"] == corrections


class TestClearHistory:
    """Tests for the clear_history function."""

    def test_clear_empty_database(self, temp_db):
        """Clearing empty database should return 0."""
        count = clear_history(db_path=temp_db)
        assert count == 0

    def test_clear_with_records(self, temp_db):
        """Clear should remove all records and return count."""
        save_correction("a", "b", [], db_path=temp_db)
        save_correction("c", "d", [], db_path=temp_db)
        save_correction("e", "f", [], db_path=temp_db)

        count = clear_history(db_path=temp_db)
        assert count == 3

        # Verify empty
        records = get_history(db_path=temp_db)
        assert records == []

    def test_clear_is_complete(self, temp_db):
        """After clear, new saves should start fresh."""
        save_correction("old", "old_fixed", [], db_path=temp_db)
        clear_history(db_path=temp_db)
        save_correction("new", "new_fixed", [], db_path=temp_db)

        records = get_history(db_path=temp_db)
        assert len(records) == 1
        assert records[0]["original_text"] == "new"
