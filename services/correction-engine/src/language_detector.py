"""Language Detector - Detects text language with confidence scoring.

Uses langdetect for language identification with configurable confidence
thresholds. Supports paragraph-level detection for multilingual text.
"""

import re
from dataclasses import dataclass
from typing import Optional

from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

# Ensure deterministic results from langdetect
DetectorFactory.seed = 0

# Supported languages
SUPPORTED_LANGUAGES = {"en", "fr", "es", "de", "pt"}

# Default confidence threshold (70%)
DEFAULT_CONFIDENCE_THRESHOLD = 0.7

# Minimum text length for reliable detection
MIN_DETECTION_LENGTH = 20


@dataclass
class LanguageResult:
    """Result of language detection for a text segment."""

    language: str
    confidence: float
    is_default: bool = False  # True if default was used due to low confidence/short text
    detection_method: str = "langdetect"  # "langdetect", "default_short", "default_low_confidence"


@dataclass
class MultilingualResult:
    """Result of paragraph-level language detection."""

    paragraphs: list[tuple[str, LanguageResult]]
    primary_language: str
    is_multilingual: bool


class LanguageDetector:
    """Detects language of text with confidence-based fallback logic.

    Implements the following rules:
    - Text shorter than 20 characters: use default language.
    - Detection confidence below threshold: use default language.
    - Detection confidence at or above threshold: use detected language.
    - Multilingual text: detect per paragraph (paragraphs >= 20 chars).
    """

    def __init__(
        self,
        default_language: str = "en",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        supported_languages: Optional[set[str]] = None,
    ):
        """Initialize the language detector.

        Args:
            default_language: Language to use when detection is uncertain.
            confidence_threshold: Minimum confidence to trust detection (0.0-1.0).
            supported_languages: Set of supported language codes.
        """
        self.default_language = default_language
        self.confidence_threshold = confidence_threshold
        self.supported_languages = supported_languages or SUPPORTED_LANGUAGES

    def detect(self, text: str) -> LanguageResult:
        """Detect the language of a text string.

        Applies confidence-based rules:
        1. If text is shorter than 20 characters, return default language.
        2. If detection confidence is below threshold, return default language.
        3. If detected language is not in supported set, return default language.
        4. Otherwise, return detected language with confidence.

        Args:
            text: The text to detect language for.

        Returns:
            LanguageResult with detected or default language.
        """
        # Rule 1: Short text uses default
        if len(text.strip()) < MIN_DETECTION_LENGTH:
            return LanguageResult(
                language=self.default_language,
                confidence=0.0,
                is_default=True,
                detection_method="default_short",
            )

        # Attempt detection
        try:
            results = detect_langs(text)
        except LangDetectException:
            # Detection failed entirely, use default
            return LanguageResult(
                language=self.default_language,
                confidence=0.0,
                is_default=True,
                detection_method="default_low_confidence",
            )

        if not results:
            return LanguageResult(
                language=self.default_language,
                confidence=0.0,
                is_default=True,
                detection_method="default_low_confidence",
            )

        # Get the top result
        top_result = results[0]
        detected_lang = top_result.lang
        detected_confidence = top_result.prob

        # Rule 3: Check if detected language is supported
        if detected_lang not in self.supported_languages:
            # Try to find a supported language in results
            for result in results[1:]:
                if result.lang in self.supported_languages and result.prob >= self.confidence_threshold:
                    return LanguageResult(
                        language=result.lang,
                        confidence=round(result.prob, 2),
                        is_default=False,
                        detection_method="langdetect",
                    )
            # No supported language found with sufficient confidence
            return LanguageResult(
                language=self.default_language,
                confidence=round(detected_confidence, 2),
                is_default=True,
                detection_method="default_low_confidence",
            )

        # Rule 2: Check confidence threshold
        if detected_confidence < self.confidence_threshold:
            return LanguageResult(
                language=self.default_language,
                confidence=round(detected_confidence, 2),
                is_default=True,
                detection_method="default_low_confidence",
            )

        # Confidence is sufficient, use detected language
        return LanguageResult(
            language=detected_lang,
            confidence=round(detected_confidence, 2),
            is_default=False,
            detection_method="langdetect",
        )

    def detect_multilingual(self, text: str) -> MultilingualResult:
        """Detect languages at paragraph level for multilingual text.

        Splits text into paragraphs (separated by blank lines) and detects
        language independently for each paragraph that is at least 20 characters.
        Short paragraphs inherit the language of the preceding paragraph or
        use the default language.

        Args:
            text: The text to analyze for multiple languages.

        Returns:
            MultilingualResult with per-paragraph detection.
        """
        # Split into paragraphs (separated by double newlines)
        paragraph_pattern = re.compile(r"\n\s*\n")
        raw_paragraphs = paragraph_pattern.split(text)

        # Filter to non-empty paragraphs
        paragraphs = [p for p in raw_paragraphs if p.strip()]

        if not paragraphs:
            return MultilingualResult(
                paragraphs=[],
                primary_language=self.default_language,
                is_multilingual=False,
            )

        # Detect language for each paragraph
        results: list[tuple[str, LanguageResult]] = []
        language_counts: dict[str, int] = {}
        previous_language = self.default_language

        for paragraph in paragraphs:
            stripped = paragraph.strip()

            if len(stripped) < MIN_DETECTION_LENGTH:
                # Short paragraph: use previous language or default
                result = LanguageResult(
                    language=previous_language,
                    confidence=0.0,
                    is_default=True,
                    detection_method="default_short",
                )
            else:
                result = self.detect(stripped)

            results.append((paragraph, result))
            previous_language = result.language

            # Count languages for primary determination
            lang = result.language
            language_counts[lang] = language_counts.get(lang, 0) + 1

        # Determine primary language (most frequent)
        primary_language = max(language_counts, key=language_counts.get)  # type: ignore

        # Determine if multilingual (more than one language detected)
        detected_languages = {
            r.language for _, r in results if not r.is_default
        }
        is_multilingual = len(detected_languages) > 1

        return MultilingualResult(
            paragraphs=results,
            primary_language=primary_language,
            is_multilingual=is_multilingual,
        )
