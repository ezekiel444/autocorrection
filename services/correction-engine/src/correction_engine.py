"""Correction Engine - Core pipeline for text analysis and correction.

Implements the full correction pipeline: segment → detect language → LLM →
dictionary filter → plugins → style guide → score → report.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import httpx

from .database import Database
from .dictionary_manager import DictionaryManager
from .language_detector import LanguageDetector, LanguageResult
from .models import (
    Correction,
    CorrectionReport,
    CorrectionType,
    FeedbackEntry,
    Severity,
    TextStatistics,
)
from .plugin_registry import PluginRegistry
from .style_guide import StyleGuideEnforcer
from .text_segmenter import segment_text

logger = logging.getLogger(__name__)

# LLM communication defaults
DEFAULT_LLM_TIMEOUT = 120.0
DEFAULT_LLM_RETRIES = 3
DEFAULT_LLM_BASE_URL = "http://llm:11434"


# ─── Prompt Builder ───────────────────────────────────────────────────────────


class PromptBuilder:
    """Constructs LLM prompts for text correction tasks.

    Builds structured prompts that instruct the LLM to identify and suggest
    corrections for spelling, grammar, punctuation, style, and clarity issues.
    """

    SYSTEM_PROMPT = """You are a precise text correction assistant. Analyze the given text and identify errors in spelling, grammar, punctuation, style, and clarity. For each issue found, provide a JSON response.

Rules:
- Only suggest corrections you are confident about.
- Preserve the original meaning and intent.
- Respect the detected language.
- Return corrections as a JSON array.

Each correction must have:
- "original": the exact text that needs correction
- "suggested": the corrected text
- "type": one of "spelling", "grammar", "punctuation", "style", "clarity"
- "reason": brief explanation
- "confidence": float 0.0-1.0
- "start_offset": character position where the issue starts
- "end_offset": character position where the issue ends

If no corrections are needed, return an empty array: []"""

    def __init__(self, model_name: str = "llama3.2:3b", temperature: float = 0.3):
        """Initialize the prompt builder.

        Args:
            model_name: Name of the LLM model.
            temperature: Sampling temperature for generation.
        """
        self.model_name = model_name
        self.temperature = temperature

    def build_correction_prompt(
        self,
        text: str,
        language: str,
        style_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a correction prompt for the Ollama API.

        Args:
            text: The text to correct.
            language: Detected language code.
            style_context: Optional style guide context.

        Returns:
            Dict suitable for POST /api/generate.
        """
        user_prompt = f"Language: {language}\n\nText to analyze:\n\"\"\"\n{text}\n\"\"\"\n\nProvide corrections as a JSON array."

        if style_context:
            user_prompt += f"\n\nStyle guidelines:\n{style_context}"

        full_prompt = f"{self.SYSTEM_PROMPT}\n\n{user_prompt}"

        return {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": 2048,
            },
            "format": "json",
        }

    def parse_llm_response(self, response_text: str, source_text: str) -> list[Correction]:
        """Parse LLM response into Correction objects.

        Args:
            response_text: Raw text response from the LLM.
            source_text: The original text that was analyzed.

        Returns:
            List of parsed Correction objects.
        """
        corrections = []

        try:
            # Try to parse as JSON
            data = json.loads(response_text)

            # Handle both array and object with "corrections" key
            if isinstance(data, dict):
                data = data.get("corrections", data.get("results", []))
            if not isinstance(data, list):
                data = [data]

            for item in data:
                if not isinstance(item, dict):
                    continue

                try:
                    # Map type string to enum
                    type_str = item.get("type", "grammar")
                    try:
                        correction_type = CorrectionType(type_str)
                    except ValueError:
                        correction_type = CorrectionType.GRAMMAR

                    original = item.get("original", "")
                    suggested = item.get("suggested", "")
                    reason = item.get("reason", "")
                    confidence = float(item.get("confidence", 0.5))

                    # Get offsets, or try to find them in source text
                    start_offset = item.get("start_offset", -1)
                    end_offset = item.get("end_offset", -1)

                    if start_offset < 0 and original:
                        # Try to find the original text in source
                        idx = source_text.find(original)
                        if idx >= 0:
                            start_offset = idx
                            end_offset = idx + len(original)
                        else:
                            start_offset = 0
                            end_offset = len(original)

                    if not original or not suggested:
                        continue

                    corrections.append(
                        Correction(
                            original_text=original,
                            suggested_text=suggested,
                            correction_type=correction_type,
                            confidence=confidence,
                            reason=reason,
                            start_offset=start_offset,
                            end_offset=end_offset,
                            source="llm",
                        )
                    )
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Skipping malformed correction item: {e}")
                    continue

        except json.JSONDecodeError:
            # Try to extract JSON from the response
            json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
            if json_match:
                return self.parse_llm_response(json_match.group(), source_text)
            logger.warning("Could not parse LLM response as JSON")

        return corrections


# ─── Correction Applier ───────────────────────────────────────────────────────


class CorrectionApplier:
    """Applies corrections to text preserving uncorrected segments.

    Handles offset adjustments when applying multiple corrections in sequence.
    """

    @staticmethod
    def apply_corrections(
        text: str,
        corrections: list[Correction],
        mode: str = "all",
    ) -> str:
        """Apply corrections to text.

        Args:
            text: The original text.
            corrections: List of corrections to apply.
            mode: "all" to apply all, "selected" to apply only non-overridden.

        Returns:
            The corrected text.
        """
        # Filter corrections based on mode
        if mode == "selected":
            applicable = [c for c in corrections if not c.is_overridden]
        else:
            applicable = [c for c in corrections if not c.is_overridden]

        if not applicable:
            return text

        # Sort by start_offset descending to apply from end to start
        # This avoids offset shifting issues
        sorted_corrections = sorted(
            applicable, key=lambda c: c.start_offset, reverse=True
        )

        result = text
        for correction in sorted_corrections:
            start = correction.start_offset
            end = correction.end_offset

            # Validate offsets
            if start < 0 or end < 0 or start > len(result) or end > len(result):
                continue
            if start >= end:
                continue

            # Verify the original text matches (fuzzy)
            actual_text = result[start:end]
            if actual_text.lower().strip() != correction.original_text.lower().strip():
                # Try to find the correct position
                idx = result.find(correction.original_text)
                if idx >= 0:
                    start = idx
                    end = idx + len(correction.original_text)
                else:
                    continue

            # Apply the correction
            result = result[:start] + correction.suggested_text + result[end:]

        return result

    @staticmethod
    def apply_high_confidence(
        text: str, corrections: list[Correction], threshold: float = 0.8
    ) -> tuple[str, list[Correction]]:
        """Apply only high-confidence corrections automatically.

        Args:
            text: The original text.
            corrections: All corrections.
            threshold: Confidence threshold for auto-apply.

        Returns:
            Tuple of (corrected text, list of applied corrections).
        """
        high_confidence = [
            c for c in corrections
            if c.confidence >= threshold and not c.is_overridden
        ]

        if not high_confidence:
            return text, []

        corrected = CorrectionApplier.apply_corrections(text, high_confidence)
        return corrected, high_confidence


# ─── Confidence Scorer ────────────────────────────────────────────────────────


class ConfidenceScorer:
    """Assigns and adjusts confidence scores for corrections.

    Integrates feedback data to adjust scores based on historical
    user acceptance/rejection patterns.
    """

    FEEDBACK_ADJUSTMENT = 0.1  # Amount to adjust per feedback signal

    def __init__(self, database: Optional[Database] = None):
        """Initialize the confidence scorer.

        Args:
            database: Database instance for feedback queries.
        """
        self._database = database

    async def adjust_scores(
        self, corrections: list[Correction]
    ) -> list[Correction]:
        """Adjust confidence scores based on feedback history.

        For corrections matching positive feedback patterns, increase by 0.1.
        For corrections matching negative feedback patterns, decrease by 0.1.
        Scores are clamped to [0.0, 1.0].

        Args:
            corrections: Corrections to adjust.

        Returns:
            The same corrections with adjusted scores.
        """
        if not self._database:
            return corrections

        for correction in corrections:
            try:
                feedback_entries = await self._database.get_feedback_for_pattern(
                    correction.original_text, correction.correction_type
                )

                if not feedback_entries:
                    continue

                # Count positive and negative signals
                positive = sum(1 for f in feedback_entries if f.signal == "positive")
                negative = sum(1 for f in feedback_entries if f.signal == "negative")

                # Net adjustment
                if positive > negative:
                    adjustment = self.FEEDBACK_ADJUSTMENT
                elif negative > positive:
                    adjustment = -self.FEEDBACK_ADJUSTMENT
                else:
                    adjustment = 0.0

                # Apply adjustment, clamped to [0.0, 1.0]
                new_confidence = max(0.0, min(1.0, correction.confidence + adjustment))
                correction.confidence = round(new_confidence, 2)

            except Exception as e:
                logger.warning(
                    f"Error adjusting confidence for correction: {e}"
                )
                continue

        return corrections

    @staticmethod
    def sort_by_confidence(corrections: list[Correction]) -> list[Correction]:
        """Sort corrections by confidence score descending.

        Args:
            corrections: Corrections to sort.

        Returns:
            Sorted list (highest confidence first).
        """
        return sorted(corrections, key=lambda c: c.confidence, reverse=True)


# ─── LLM Client ──────────────────────────────────────────────────────────────


class LLMClient:
    """HTTP client for communicating with Ollama LLM service."""

    def __init__(
        self,
        base_url: str = DEFAULT_LLM_BASE_URL,
        timeout: float = DEFAULT_LLM_TIMEOUT,
        max_retries: int = DEFAULT_LLM_RETRIES,
    ):
        """Initialize the LLM client.

        Args:
            base_url: Base URL of the Ollama service.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def generate(self, payload: dict[str, Any]) -> Optional[str]:
        """Send a generation request to Ollama.

        Args:
            payload: The request payload for /api/generate.

        Returns:
            The generated text response, or None on failure.
        """
        url = f"{self.base_url}/api/generate"

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload)

                    if response.status_code == 200:
                        data = response.json()
                        return data.get("response", "")
                    else:
                        logger.warning(
                            f"LLM request failed (attempt {attempt + 1}): "
                            f"status {response.status_code}"
                        )

            except httpx.TimeoutException:
                logger.warning(
                    f"LLM request timed out (attempt {attempt + 1}/{self.max_retries})"
                )
            except httpx.ConnectError:
                logger.warning(
                    f"Cannot connect to LLM service (attempt {attempt + 1}/{self.max_retries})"
                )
            except Exception as e:
                logger.error(f"LLM request error (attempt {attempt + 1}): {e}")

        logger.error(f"LLM request failed after {self.max_retries} attempts")
        return None

    async def is_healthy(self) -> bool:
        """Check if the LLM service is healthy.

        Returns:
            True if the service responds to health check.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception:
            return False


# ─── OpenAI-Compatible LLM Client ────────────────────────────────────────────


class OpenAIClient:
    """HTTP client for OpenAI-compatible APIs (OpenAI, Azure, Groq, etc.).

    Provides much faster responses than local LLM at the cost of privacy.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 30.0,
    ):
        """Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key.
            base_url: Base URL for the API (supports OpenAI-compatible endpoints).
            model: Model name to use.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def generate(self, payload: dict[str, Any]) -> Optional[str]:
        """Send a correction request to OpenAI.

        Converts the Ollama-style payload to OpenAI chat completion format.

        Args:
            payload: The Ollama-style request payload (prompt field used).

        Returns:
            The generated text response, or None on failure.
        """
        prompt = payload.get("prompt", "")

        messages = [
            {"role": "user", "content": prompt},
        ]

        openai_payload = {
            "model": self.model,
            "messages": messages,
            "temperature": payload.get("options", {}).get("temperature", 0.3),
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=openai_payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                    return ""
                else:
                    logger.error(
                        f"OpenAI request failed: {response.status_code} - {response.text}"
                    )
                    return None

        except httpx.TimeoutException:
            logger.error("OpenAI request timed out")
            return None
        except Exception as e:
            logger.error(f"OpenAI request error: {e}")
            return None

    async def is_healthy(self) -> bool:
        """Check if the OpenAI API is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return response.status_code == 200
        except Exception:
            return False


# ─── Correction Pipeline ──────────────────────────────────────────────────────


class CorrectionPipeline:
    """Full correction pipeline orchestrating all components.

    Pipeline: segment → detect language → LLM → dictionary filter →
    plugins → style guide → score → report.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        language_detector: Optional[LanguageDetector] = None,
        dictionary_manager: Optional[DictionaryManager] = None,
        plugin_registry: Optional[PluginRegistry] = None,
        style_guide: Optional[StyleGuideEnforcer] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None,
        database: Optional[Database] = None,
        model_name: str = "llama3.2:3b",
        temperature: float = 0.3,
        max_segment_words: int = 500,
    ):
        """Initialize the correction pipeline.

        Args:
            llm_client: LLM communication client.
            prompt_builder: Prompt construction helper.
            language_detector: Language detection module.
            dictionary_manager: Custom dictionary manager.
            plugin_registry: Plugin execution registry.
            style_guide: Style guide enforcer.
            confidence_scorer: Confidence scoring module.
            database: Database for history and feedback.
            model_name: LLM model name.
            temperature: LLM temperature.
            max_segment_words: Max words per segment.
        """
        self.llm_client = llm_client or LLMClient()
        self.prompt_builder = prompt_builder or PromptBuilder(
            model_name=model_name, temperature=temperature
        )
        self.language_detector = language_detector or LanguageDetector()
        self.dictionary_manager = dictionary_manager or DictionaryManager()
        self.plugin_registry = plugin_registry or PluginRegistry()
        self.style_guide = style_guide or StyleGuideEnforcer()
        self.confidence_scorer = confidence_scorer or ConfidenceScorer()
        self.database = database
        self.max_segment_words = max_segment_words

    async def analyze(
        self,
        text: str,
        language: Optional[str] = None,
        auto_apply: bool = False,
        style_guide_enabled: bool = True,
        plugins_enabled: bool = True,
    ) -> CorrectionReport:
        """Run the full correction pipeline on text.

        Args:
            text: The text to analyze.
            language: Override language detection.
            auto_apply: Whether to auto-apply high-confidence corrections.
            style_guide_enabled: Whether to run style guide checks.
            plugins_enabled: Whether to run plugins.

        Returns:
            Complete CorrectionReport.
        """
        report_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()

        # Step 1: Detect language
        if language:
            lang_result = LanguageResult(
                language=language, confidence=1.0, is_default=False
            )
        else:
            lang_result = self.language_detector.detect(text)

        # Step 2: Segment text
        segment_result = segment_text(text, max_words=self.max_segment_words)

        # Step 3: Get LLM corrections for each segment
        all_corrections: list[Correction] = []
        offset_adjustment = 0

        for segment in segment_result.segments:
            # Build prompt
            payload = self.prompt_builder.build_correction_prompt(
                segment, lang_result.language
            )

            # Call LLM
            response_text = await self.llm_client.generate(payload)

            if response_text:
                segment_corrections = self.prompt_builder.parse_llm_response(
                    response_text, segment
                )

                # Adjust offsets for segment position in original text
                segment_start = text.find(segment)
                if segment_start >= 0:
                    for correction in segment_corrections:
                        correction.start_offset += segment_start
                        correction.end_offset += segment_start

                all_corrections.extend(segment_corrections)

        # Step 4: Dictionary filter
        all_corrections = self.dictionary_manager.filter_corrections(all_corrections)

        # Step 5: Plugin corrections
        if plugins_enabled and self.plugin_registry.plugin_count > 0:
            plugin_corrections = self.plugin_registry.get_all_corrections(
                text, lang_result.language
            )
            all_corrections.extend(plugin_corrections)

        # Step 6: Style guide corrections
        if style_guide_enabled:
            style_corrections = self.style_guide.analyze(text)
            all_corrections.extend(style_corrections)

        # Step 7: Adjust confidence scores based on feedback
        all_corrections = await self.confidence_scorer.adjust_scores(all_corrections)

        # Step 8: Sort by confidence descending
        all_corrections = ConfidenceScorer.sort_by_confidence(all_corrections)

        # Calculate text statistics
        text_stats = TextStatistics(
            word_count=len(text.split()),
            sentence_count=max(1, text.count(".") + text.count("!") + text.count("?")),
            character_count=len(text),
            paragraph_count=max(1, text.count("\n\n") + 1),
        )

        # Build report
        report = CorrectionReport(
            id=report_id,
            timestamp=timestamp,
            original_text=text,
            corrections=all_corrections,
            language_detected=lang_result.language,
            language_confidence=lang_result.confidence,
            text_statistics=text_stats,
            metadata={
                "segments_processed": segment_result.segment_count,
                "language_detection_method": lang_result.detection_method
                if hasattr(lang_result, "detection_method")
                else "manual",
                "auto_apply": auto_apply,
            },
        )

        return report

    async def apply(
        self, text: str, corrections: list[Correction], mode: str = "all"
    ) -> str:
        """Apply corrections to text.

        Args:
            text: The original text.
            corrections: Corrections to apply.
            mode: "all" or "selected".

        Returns:
            The corrected text.
        """
        return CorrectionApplier.apply_corrections(text, corrections, mode)
