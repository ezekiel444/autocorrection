"""Tests for text capture and clipboard validation.

Tests input validation logic: empty text, whitespace-only, too long text,
and valid text scenarios.
"""

import pytest

from app.text_capture import validate_text, has_formatting_markers, MAX_TEXT_LENGTH


class TestValidateText:
    """Tests for the validate_text function."""

    def test_none_text_is_invalid(self):
        """None text should be rejected."""
        is_valid, error = validate_text(None)
        assert is_valid is False
        assert "None" in error

    def test_empty_text_is_invalid(self):
        """Empty string should be rejected."""
        is_valid, error = validate_text("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_whitespace_only_is_invalid(self):
        """Text containing only spaces should be rejected."""
        is_valid, error = validate_text("     ")
        assert is_valid is False
        assert "whitespace" in error.lower()

    def test_tabs_only_is_invalid(self):
        """Text containing only tabs should be rejected."""
        is_valid, error = validate_text("\t\t\t")
        assert is_valid is False
        assert "whitespace" in error.lower()

    def test_newlines_only_is_invalid(self):
        """Text containing only newlines should be rejected."""
        is_valid, error = validate_text("\n\n\n")
        assert is_valid is False
        assert "whitespace" in error.lower()

    def test_mixed_whitespace_only_is_invalid(self):
        """Text containing only mixed whitespace should be rejected."""
        is_valid, error = validate_text("  \t\n  \r  ")
        assert is_valid is False
        assert "whitespace" in error.lower()

    def test_too_long_text_is_invalid(self):
        """Text exceeding MAX_TEXT_LENGTH should be rejected."""
        long_text = "a" * (MAX_TEXT_LENGTH + 1)
        is_valid, error = validate_text(long_text)
        assert is_valid is False
        assert "maximum length" in error.lower()

    def test_exactly_max_length_is_valid(self):
        """Text at exactly MAX_TEXT_LENGTH should be accepted."""
        text = "a" * MAX_TEXT_LENGTH
        is_valid, error = validate_text(text)
        assert is_valid is True
        assert error is None

    def test_normal_text_is_valid(self):
        """Regular text should be accepted."""
        is_valid, error = validate_text("Hello, world!")
        assert is_valid is True
        assert error is None

    def test_text_with_formatting_is_valid(self):
        """Text with newlines and tabs should be accepted."""
        is_valid, error = validate_text("Line 1\nLine 2\tTabbed")
        assert is_valid is True
        assert error is None

    def test_unicode_text_is_valid(self):
        """Unicode text should be accepted."""
        is_valid, error = validate_text("Héllo wörld! 你好世界 🌍")
        assert is_valid is True
        assert error is None

    def test_single_character_is_valid(self):
        """Single non-whitespace character should be accepted."""
        is_valid, error = validate_text("a")
        assert is_valid is True
        assert error is None


class TestHasFormattingMarkers:
    """Tests for the has_formatting_markers function."""

    def test_plain_text_no_formatting(self):
        """Plain text without special chars has no formatting."""
        assert has_formatting_markers("Hello world") is False

    def test_text_with_newline(self):
        """Text with newline has formatting."""
        assert has_formatting_markers("Hello\nworld") is True

    def test_text_with_tab(self):
        """Text with tab has formatting."""
        assert has_formatting_markers("Hello\tworld") is True

    def test_text_with_carriage_return(self):
        """Text with carriage return has formatting."""
        assert has_formatting_markers("Hello\rworld") is True

    def test_text_with_unicode_line_separator(self):
        """Text with unicode line separator has formatting."""
        assert has_formatting_markers("Hello\u2028world") is True
