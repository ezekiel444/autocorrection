"""Core data models for the Correction Engine.

Defines all dataclasses and enums used throughout the correction pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CorrectionType(Enum):
    """Types of text corrections the system can identify."""

    SPELLING = "spelling"
    GRAMMAR = "grammar"
    PUNCTUATION = "punctuation"
    STYLE = "style"
    CLARITY = "clarity"


class Severity(Enum):
    """Severity levels for corrections, ordered from most to least severe."""

    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class ConfidenceTier(Enum):
    """Confidence tiers for categorizing correction confidence scores."""

    HIGH = "high"  # 0.8 - 1.0
    MEDIUM = "medium"  # 0.5 - 0.79
    LOW = "low"  # 0.0 - 0.49


@dataclass
class TextStatistics:
    """Statistical information about analyzed text."""

    word_count: int
    sentence_count: int
    character_count: int
    paragraph_count: int


@dataclass
class Correction:
    """A single correction suggestion for a text segment."""

    original_text: str
    suggested_text: str
    correction_type: CorrectionType
    confidence: float  # 0.0 to 1.0, rounded to 2 decimal places
    reason: str
    start_offset: int
    end_offset: int
    severity: Severity = Severity.WARNING
    rule_name: Optional[str] = None
    is_overridden: bool = False  # True if custom dictionary match
    confidence_undetermined: bool = False
    source: str = "llm"  # "llm", "plugin:<name>", "style_guide"

    def __post_init__(self):
        """Validate and normalize confidence score."""
        self.confidence = round(max(0.0, min(1.0, self.confidence)), 2)

    @property
    def confidence_tier(self) -> ConfidenceTier:
        """Determine the confidence tier for this correction."""
        if self.confidence >= 0.8:
            return ConfidenceTier.HIGH
        elif self.confidence >= 0.5:
            return ConfidenceTier.MEDIUM
        else:
            return ConfidenceTier.LOW


@dataclass
class CorrectionReport:
    """Complete correction report for an analyzed text."""

    id: str
    timestamp: datetime
    original_text: str
    corrections: list[Correction]
    language_detected: str
    language_confidence: float
    text_statistics: TextStatistics
    metadata: dict = field(default_factory=dict)

    @property
    def correction_count(self) -> int:
        """Total number of corrections in this report."""
        return len(self.corrections)

    @property
    def high_confidence_corrections(self) -> list[Correction]:
        """Corrections with high confidence (>= 0.8)."""
        return [c for c in self.corrections if c.confidence >= 0.8]

    def corrections_by_type(self) -> dict[CorrectionType, list[Correction]]:
        """Group corrections by their type."""
        result: dict[CorrectionType, list[Correction]] = {}
        for correction in self.corrections:
            if correction.correction_type not in result:
                result[correction.correction_type] = []
            result[correction.correction_type].append(correction)
        return result

    def confidence_distribution(self) -> dict[ConfidenceTier, int]:
        """Count corrections in each confidence tier."""
        distribution = {tier: 0 for tier in ConfidenceTier}
        for correction in self.corrections:
            distribution[correction.confidence_tier] += 1
        return distribution


@dataclass
class CorrectionHistoryEntry:
    """A record of a past correction stored in history."""

    id: str
    timestamp: datetime
    original_text: str
    corrected_text: str
    correction_type: CorrectionType
    source_context: str  # app name + surrounding 50 chars
    corrections_applied: int
    confidence_avg: float


@dataclass
class FeedbackEntry:
    """User feedback on a specific correction suggestion."""

    id: str
    timestamp: datetime
    original_text: str
    suggestion: str
    correction_type: CorrectionType
    signal: str  # "positive" or "negative"
    context: Optional[str] = None


@dataclass
class AggregatedFeedback:
    """Aggregated feedback for patterns older than 90 days."""

    pattern_hash: str
    correction_type: CorrectionType
    signal: str
    occurrence_count: int
    last_seen: datetime
    sample_original: Optional[str] = None
    sample_suggestion: Optional[str] = None


@dataclass
class StyleRule:
    """A configurable style guide rule."""

    name: str
    rule_type: str  # "sentence_length", "passive_voice", "tone", "jargon"
    severity: Severity
    enabled: bool = True
    config: dict = field(default_factory=dict)


@dataclass
class PluginManifest:
    """Metadata and configuration for a loaded plugin."""

    name: str
    version: str
    enabled: bool
    config_path: str
    timeout_seconds: int = 30
