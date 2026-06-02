"""Custom Dictionary Manager - Load, validate, and filter corrections.

Provides dictionary loading from plain text and CSV formats with validation,
activation/deactivation of named dictionaries, and case-insensitive matching
for correction filtering.
"""

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import Correction, CorrectionType

logger = logging.getLogger(__name__)

# Constraints
MAX_TERM_LENGTH = 100
MAX_TERMS_PER_DICTIONARY = 10_000
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_DICTIONARIES = 20


@dataclass
class LoadResult:
    """Result of loading a dictionary file."""

    dictionary_name: str
    terms_loaded: int
    terms_skipped: int
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


@dataclass
class Dictionary:
    """A named dictionary with its terms and state."""

    name: str
    terms: set[str]  # Stored lowercase for case-insensitive matching
    is_active: bool = True
    source_path: Optional[str] = None


class DictionaryManager:
    """Manages custom dictionaries for correction filtering.

    Features:
    - Load dictionaries from plain text (one term per line) and CSV formats.
    - Validate: UTF-8, terms up to 100 chars, max 10,000 terms, files up to 5MB.
    - Skip blank lines, duplicates, over-length entries; report skipped count.
    - Support up to 20 named dictionaries with activate/deactivate.
    - Case-insensitive matching for correction filtering.
    - Mark matching corrections as overridden.
    """

    def __init__(self):
        """Initialize the dictionary manager."""
        self._dictionaries: dict[str, Dictionary] = {}

    @property
    def dictionary_count(self) -> int:
        """Number of loaded dictionaries."""
        return len(self._dictionaries)

    @property
    def active_dictionaries(self) -> list[str]:
        """Names of currently active dictionaries."""
        return [name for name, d in self._dictionaries.items() if d.is_active]

    def get_dictionary(self, name: str) -> Optional[Dictionary]:
        """Get a dictionary by name.

        Args:
            name: The dictionary name.

        Returns:
            The Dictionary object, or None if not found.
        """
        return self._dictionaries.get(name)

    def load_from_text(self, name: str, file_path: str) -> LoadResult:
        """Load a dictionary from a plain text file (one term per line).

        Args:
            name: Name for this dictionary.
            file_path: Path to the text file.

        Returns:
            LoadResult with loading statistics.
        """
        if len(self._dictionaries) >= MAX_DICTIONARIES and name not in self._dictionaries:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"Maximum number of dictionaries ({MAX_DICTIONARIES}) reached",
            )

        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"File not found: {file_path}",
            )

        # Validate file size
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"File exceeds maximum size of 5MB (actual: {file_size} bytes)",
            )

        # Read and parse file
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error="File is not valid UTF-8",
            )
        except (OSError, IOError) as e:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"Cannot read file: {e}",
            )

        # Parse terms
        terms: set[str] = set()
        skipped = 0
        skipped_reasons: dict[str, int] = {}

        for line in content.splitlines():
            term = line.strip()

            # Skip blank lines
            if not term:
                skipped += 1
                skipped_reasons["blank_line"] = skipped_reasons.get("blank_line", 0) + 1
                continue

            # Skip over-length entries
            if len(term) > MAX_TERM_LENGTH:
                skipped += 1
                skipped_reasons["over_length"] = skipped_reasons.get("over_length", 0) + 1
                continue

            # Skip duplicates (case-insensitive)
            term_lower = term.lower()
            if term_lower in terms:
                skipped += 1
                skipped_reasons["duplicate"] = skipped_reasons.get("duplicate", 0) + 1
                continue

            # Check max terms limit
            if len(terms) >= MAX_TERMS_PER_DICTIONARY:
                skipped += 1
                skipped_reasons["max_terms_exceeded"] = (
                    skipped_reasons.get("max_terms_exceeded", 0) + 1
                )
                continue

            terms.add(term_lower)

        # Store dictionary
        self._dictionaries[name] = Dictionary(
            name=name,
            terms=terms,
            is_active=True,
            source_path=file_path,
        )

        logger.info(
            f"Loaded dictionary '{name}': {len(terms)} terms, {skipped} skipped"
        )

        return LoadResult(
            dictionary_name=name,
            terms_loaded=len(terms),
            terms_skipped=skipped,
            skipped_reasons=skipped_reasons,
            success=True,
        )

    def load_from_csv(self, name: str, file_path: str) -> LoadResult:
        """Load a dictionary from a CSV file (term, optional definition).

        Args:
            name: Name for this dictionary.
            file_path: Path to the CSV file.

        Returns:
            LoadResult with loading statistics.
        """
        if len(self._dictionaries) >= MAX_DICTIONARIES and name not in self._dictionaries:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"Maximum number of dictionaries ({MAX_DICTIONARIES}) reached",
            )

        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"File not found: {file_path}",
            )

        # Validate file size
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"File exceeds maximum size of 5MB (actual: {file_size} bytes)",
            )

        # Read file
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error="File is not valid UTF-8",
            )
        except (OSError, IOError) as e:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"Cannot read file: {e}",
            )

        # Parse CSV
        terms: set[str] = set()
        skipped = 0
        skipped_reasons: dict[str, int] = {}

        try:
            reader = csv.reader(io.StringIO(content))
            for row in reader:
                if not row:
                    skipped += 1
                    skipped_reasons["blank_line"] = skipped_reasons.get("blank_line", 0) + 1
                    continue

                term = row[0].strip()

                # Skip blank terms
                if not term:
                    skipped += 1
                    skipped_reasons["blank_line"] = skipped_reasons.get("blank_line", 0) + 1
                    continue

                # Skip over-length entries
                if len(term) > MAX_TERM_LENGTH:
                    skipped += 1
                    skipped_reasons["over_length"] = skipped_reasons.get("over_length", 0) + 1
                    continue

                # Skip duplicates (case-insensitive)
                term_lower = term.lower()
                if term_lower in terms:
                    skipped += 1
                    skipped_reasons["duplicate"] = skipped_reasons.get("duplicate", 0) + 1
                    continue

                # Check max terms limit
                if len(terms) >= MAX_TERMS_PER_DICTIONARY:
                    skipped += 1
                    skipped_reasons["max_terms_exceeded"] = (
                        skipped_reasons.get("max_terms_exceeded", 0) + 1
                    )
                    continue

                terms.add(term_lower)

        except csv.Error as e:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"CSV parsing error: {e}",
            )

        # Store dictionary
        self._dictionaries[name] = Dictionary(
            name=name,
            terms=terms,
            is_active=True,
            source_path=file_path,
        )

        logger.info(
            f"Loaded CSV dictionary '{name}': {len(terms)} terms, {skipped} skipped"
        )

        return LoadResult(
            dictionary_name=name,
            terms_loaded=len(terms),
            terms_skipped=skipped,
            skipped_reasons=skipped_reasons,
            success=True,
        )

    def load_from_terms(self, name: str, terms: list[str]) -> LoadResult:
        """Load a dictionary from a list of terms directly.

        Args:
            name: Name for this dictionary.
            terms: List of term strings.

        Returns:
            LoadResult with loading statistics.
        """
        if len(self._dictionaries) >= MAX_DICTIONARIES and name not in self._dictionaries:
            return LoadResult(
                dictionary_name=name,
                terms_loaded=0,
                terms_skipped=0,
                success=False,
                error=f"Maximum number of dictionaries ({MAX_DICTIONARIES}) reached",
            )

        valid_terms: set[str] = set()
        skipped = 0
        skipped_reasons: dict[str, int] = {}

        for term in terms:
            term = term.strip()

            if not term:
                skipped += 1
                skipped_reasons["blank_line"] = skipped_reasons.get("blank_line", 0) + 1
                continue

            if len(term) > MAX_TERM_LENGTH:
                skipped += 1
                skipped_reasons["over_length"] = skipped_reasons.get("over_length", 0) + 1
                continue

            term_lower = term.lower()
            if term_lower in valid_terms:
                skipped += 1
                skipped_reasons["duplicate"] = skipped_reasons.get("duplicate", 0) + 1
                continue

            if len(valid_terms) >= MAX_TERMS_PER_DICTIONARY:
                skipped += 1
                skipped_reasons["max_terms_exceeded"] = (
                    skipped_reasons.get("max_terms_exceeded", 0) + 1
                )
                continue

            valid_terms.add(term_lower)

        self._dictionaries[name] = Dictionary(
            name=name,
            terms=valid_terms,
            is_active=True,
        )

        return LoadResult(
            dictionary_name=name,
            terms_loaded=len(valid_terms),
            terms_skipped=skipped,
            skipped_reasons=skipped_reasons,
            success=True,
        )

    def activate(self, name: str) -> bool:
        """Activate a dictionary for correction filtering.

        Args:
            name: The dictionary name.

        Returns:
            True if activated, False if dictionary not found.
        """
        if name not in self._dictionaries:
            return False
        self._dictionaries[name].is_active = True
        return True

    def deactivate(self, name: str) -> bool:
        """Deactivate a dictionary (stops filtering against it).

        Args:
            name: The dictionary name.

        Returns:
            True if deactivated, False if dictionary not found.
        """
        if name not in self._dictionaries:
            return False
        self._dictionaries[name].is_active = False
        return True

    def remove(self, name: str) -> bool:
        """Remove a dictionary entirely.

        Args:
            name: The dictionary name.

        Returns:
            True if removed, False if not found.
        """
        if name not in self._dictionaries:
            return False
        del self._dictionaries[name]
        return True

    def get_all_active_terms(self) -> set[str]:
        """Get all terms from all active dictionaries.

        Returns:
            Set of lowercase terms from active dictionaries.
        """
        all_terms: set[str] = set()
        for dictionary in self._dictionaries.values():
            if dictionary.is_active:
                all_terms.update(dictionary.terms)
        return all_terms

    def is_term_in_dictionary(self, term: str) -> bool:
        """Check if a term exists in any active dictionary (case-insensitive).

        Args:
            term: The term to check.

        Returns:
            True if the term is found in any active dictionary.
        """
        term_lower = term.lower()
        for dictionary in self._dictionaries.values():
            if dictionary.is_active and term_lower in dictionary.terms:
                return True
        return False

    def filter_corrections(
        self, corrections: list[Correction]
    ) -> list[Correction]:
        """Filter corrections against active dictionaries.

        For spelling corrections where the original text matches a dictionary
        term, mark the correction as overridden. Non-spelling corrections
        are not affected.

        Args:
            corrections: List of corrections to filter.

        Returns:
            The same list with matching corrections marked as overridden.
        """
        active_terms = self.get_all_active_terms()

        if not active_terms:
            return corrections

        for correction in corrections:
            # Only filter spelling corrections
            if correction.correction_type != CorrectionType.SPELLING:
                continue

            # Check if the original text (the word being "corrected") is in dictionary
            # Split original text into words and check each
            original_words = correction.original_text.split()
            for word in original_words:
                # Strip punctuation for matching
                clean_word = word.strip(".,;:!?\"'()-[]{}").lower()
                if clean_word in active_terms:
                    correction.is_overridden = True
                    break

        return corrections
