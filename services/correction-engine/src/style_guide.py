"""Style Guide Enforcer - Configurable style rules with conflict resolution.

Implements sentence length, passive voice detection, tone consistency,
and jargon avoidance rules with severity-based conflict resolution.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .models import Correction, CorrectionType, Severity, StyleRule

logger = logging.getLogger(__name__)

# Severity ordering for conflict resolution (higher index = higher severity)
SEVERITY_ORDER = {
    Severity.SUGGESTION: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
}


@dataclass
class StyleViolation:
    """A detected style violation."""

    rule_name: str
    message: str
    start_offset: int
    end_offset: int
    original_text: str
    suggested_text: Optional[str]
    severity: Severity
    rule_type: str


class StyleGuideEnforcer:
    """Enforces configurable style rules on text.

    Features:
    - Sentence length rule (configurable max, default 30 words).
    - Passive voice detection using regex patterns.
    - Tone consistency (formal/informal/neutral).
    - Jargon avoidance with alternatives.
    - Severity levels (error, warning, suggestion).
    - Conflict resolution: higher severity wins for overlapping ranges.
    - Skip malformed rules, log errors.
    """

    def __init__(
        self,
        rules: Optional[list[StyleRule]] = None,
        rules_path: Optional[str] = None,
        max_sentence_length: int = 30,
        detect_passive_voice: bool = True,
        tone: str = "neutral",
    ):
        """Initialize the style guide enforcer.

        Args:
            rules: Pre-loaded style rules. If None, loads from rules_path.
            rules_path: Path to style_rules.yaml file.
            max_sentence_length: Default max sentence length in words.
            detect_passive_voice: Whether to detect passive voice.
            tone: Target tone (formal, informal, neutral).
        """
        self._max_sentence_length = max_sentence_length
        self._detect_passive_voice = detect_passive_voice
        self._tone = tone
        self._rules: list[StyleRule] = []

        if rules is not None:
            self._rules = self._validate_rules(rules)
        elif rules_path:
            self._rules = self._load_rules_from_file(rules_path)
        else:
            self._rules = self._get_default_rules()

    @property
    def rules(self) -> list[StyleRule]:
        """Get the loaded style rules."""
        return self._rules

    def analyze(self, text: str) -> list[Correction]:
        """Analyze text against all enabled style rules.

        Args:
            text: The text to analyze.

        Returns:
            List of Correction objects for style violations.
        """
        violations: list[StyleViolation] = []

        for rule in self._rules:
            if not rule.enabled:
                continue

            try:
                rule_violations = self._apply_rule(rule, text)
                violations.extend(rule_violations)
            except Exception as e:
                logger.error(f"Error applying rule '{rule.name}': {e}")
                continue

        # Resolve conflicts (overlapping ranges)
        resolved = self._resolve_conflicts(violations)

        # Convert to Correction objects
        corrections = []
        for violation in resolved:
            corrections.append(
                Correction(
                    original_text=violation.original_text,
                    suggested_text=violation.suggested_text or "",
                    correction_type=CorrectionType.STYLE,
                    confidence=0.7 if violation.severity == Severity.ERROR else 0.5,
                    reason=violation.message,
                    start_offset=violation.start_offset,
                    end_offset=violation.end_offset,
                    severity=violation.severity,
                    rule_name=violation.rule_name,
                    source="style_guide",
                )
            )

        return corrections

    def _apply_rule(self, rule: StyleRule, text: str) -> list[StyleViolation]:
        """Apply a single rule to text.

        Args:
            rule: The style rule to apply.
            text: The text to check.

        Returns:
            List of violations found.
        """
        if rule.rule_type == "sentence_length":
            return self._check_sentence_length(rule, text)
        elif rule.rule_type == "passive_voice":
            return self._check_passive_voice(rule, text)
        elif rule.rule_type == "tone":
            return self._check_tone(rule, text)
        elif rule.rule_type == "jargon":
            return self._check_jargon(rule, text)
        else:
            logger.warning(f"Unknown rule type: {rule.rule_type}")
            return []

    def _check_sentence_length(
        self, rule: StyleRule, text: str
    ) -> list[StyleViolation]:
        """Check for sentences exceeding the maximum word count.

        Args:
            rule: The sentence length rule.
            text: The text to check.

        Returns:
            List of violations for long sentences.
        """
        max_words = rule.config.get("max_words", self._max_sentence_length)
        message_template = rule.config.get(
            "message",
            "Sentence exceeds {max_words} words. Consider splitting for clarity.",
        )

        violations = []

        # Split text into sentences
        sentence_pattern = re.compile(r"[^.!?]*[.!?]+|[^.!?]+$")
        sentences = sentence_pattern.findall(text)

        offset = 0
        for sentence in sentences:
            # Find the actual position in text
            start = text.find(sentence, offset)
            if start == -1:
                offset += len(sentence)
                continue

            end = start + len(sentence)
            word_count = len(sentence.split())

            if word_count > max_words:
                message = message_template.format(max_words=max_words)
                violations.append(
                    StyleViolation(
                        rule_name=rule.name,
                        message=f"{message} (found {word_count} words)",
                        start_offset=start,
                        end_offset=end,
                        original_text=sentence.strip(),
                        suggested_text=None,
                        severity=rule.severity,
                        rule_type=rule.rule_type,
                    )
                )

            offset = end

        return violations

    def _check_passive_voice(
        self, rule: StyleRule, text: str
    ) -> list[StyleViolation]:
        """Check for passive voice constructions.

        Args:
            rule: The passive voice rule.
            text: The text to check.

        Returns:
            List of violations for passive voice usage.
        """
        if not self._detect_passive_voice:
            return []

        patterns = rule.config.get(
            "patterns",
            [
                r"was \w+ed",
                r"were \w+ed",
                r"is being \w+ed",
                r"has been \w+ed",
                r"had been \w+ed",
                r"will be \w+ed",
            ],
        )
        message = rule.config.get(
            "message", "Consider using active voice for clarity."
        )

        violations = []

        for pattern_str in patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                for match in pattern.finditer(text):
                    violations.append(
                        StyleViolation(
                            rule_name=rule.name,
                            message=message,
                            start_offset=match.start(),
                            end_offset=match.end(),
                            original_text=match.group(),
                            suggested_text=None,
                            severity=rule.severity,
                            rule_type=rule.rule_type,
                        )
                    )
            except re.error as e:
                logger.error(f"Invalid regex pattern '{pattern_str}': {e}")
                continue

        return violations

    def _check_tone(self, rule: StyleRule, text: str) -> list[StyleViolation]:
        """Check for tone inconsistencies.

        Args:
            rule: The tone rule.
            text: The text to check.

        Returns:
            List of violations for tone issues.
        """
        target_tone = rule.config.get("target_tone", self._tone)
        message = rule.config.get("message", "Tone inconsistency detected.")

        violations = []

        if target_tone == "formal":
            # Check for informal patterns
            informal_patterns = rule.config.get(
                "informal_patterns",
                ["gonna", "wanna", "gotta", "kinda", "sorta", "ain't", "y'all"],
            )
            for pattern in informal_patterns:
                for match in re.finditer(
                    r"\b" + re.escape(pattern) + r"\b", text, re.IGNORECASE
                ):
                    violations.append(
                        StyleViolation(
                            rule_name=rule.name,
                            message=message,
                            start_offset=match.start(),
                            end_offset=match.end(),
                            original_text=match.group(),
                            suggested_text=None,
                            severity=rule.severity,
                            rule_type=rule.rule_type,
                        )
                    )

        elif target_tone == "informal":
            # Check for overly formal patterns
            formal_patterns = rule.config.get(
                "formal_patterns",
                [
                    "furthermore",
                    "henceforth",
                    "notwithstanding",
                    "aforementioned",
                    "hereinafter",
                ],
            )
            for pattern in formal_patterns:
                for match in re.finditer(
                    r"\b" + re.escape(pattern) + r"\b", text, re.IGNORECASE
                ):
                    violations.append(
                        StyleViolation(
                            rule_name=rule.name,
                            message=message,
                            start_offset=match.start(),
                            end_offset=match.end(),
                            original_text=match.group(),
                            suggested_text=None,
                            severity=rule.severity,
                            rule_type=rule.rule_type,
                        )
                    )

        # Neutral tone: no specific checks (accepts both)
        return violations

    def _check_jargon(self, rule: StyleRule, text: str) -> list[StyleViolation]:
        """Check for jargon terms and suggest alternatives.

        Args:
            rule: The jargon rule.
            text: The text to check.

        Returns:
            List of violations for jargon usage.
        """
        terms = rule.config.get("terms", [])
        message_template = rule.config.get(
            "message", "Consider replacing '{term}' with '{alternative}' for clarity."
        )

        violations = []

        for term_entry in terms:
            if isinstance(term_entry, dict):
                term = term_entry.get("term", "")
                alternative = term_entry.get("alternative", "")
            else:
                continue

            if not term:
                continue

            for match in re.finditer(
                r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE
            ):
                message = message_template.format(term=term, alternative=alternative)
                violations.append(
                    StyleViolation(
                        rule_name=rule.name,
                        message=message,
                        start_offset=match.start(),
                        end_offset=match.end(),
                        original_text=match.group(),
                        suggested_text=alternative if alternative else None,
                        severity=rule.severity,
                        rule_type=rule.rule_type,
                    )
                )

        return violations

    def _resolve_conflicts(
        self, violations: list[StyleViolation]
    ) -> list[StyleViolation]:
        """Resolve conflicts between overlapping violations.

        When multiple rules produce violations for overlapping character ranges,
        keep only the violation with the highest severity.

        Args:
            violations: All detected violations.

        Returns:
            Filtered list with conflicts resolved.
        """
        if not violations:
            return []

        # Sort by start offset, then by severity (highest first)
        sorted_violations = sorted(
            violations,
            key=lambda v: (v.start_offset, -SEVERITY_ORDER.get(v.severity, 0)),
        )

        resolved: list[StyleViolation] = []

        for violation in sorted_violations:
            # Check if this overlaps with any already-resolved violation
            is_overlapping = False
            for existing in resolved:
                if self._ranges_overlap(
                    violation.start_offset,
                    violation.end_offset,
                    existing.start_offset,
                    existing.end_offset,
                ):
                    # Overlap detected: keep the one with higher severity
                    existing_severity = SEVERITY_ORDER.get(existing.severity, 0)
                    new_severity = SEVERITY_ORDER.get(violation.severity, 0)

                    if new_severity > existing_severity:
                        # Replace existing with new (higher severity)
                        resolved.remove(existing)
                        resolved.append(violation)
                    # Otherwise, keep existing (it has equal or higher severity)
                    is_overlapping = True
                    break

            if not is_overlapping:
                resolved.append(violation)

        return resolved

    @staticmethod
    def _ranges_overlap(
        start1: int, end1: int, start2: int, end2: int
    ) -> bool:
        """Check if two character ranges overlap.

        Args:
            start1, end1: First range.
            start2, end2: Second range.

        Returns:
            True if the ranges overlap.
        """
        return start1 < end2 and start2 < end1

    def _validate_rules(self, rules: list[StyleRule]) -> list[StyleRule]:
        """Validate a list of style rules, skipping malformed ones.

        Args:
            rules: Rules to validate.

        Returns:
            List of valid rules.
        """
        valid_rules = []
        for rule in rules:
            if not self._is_rule_valid(rule):
                logger.error(
                    f"Skipping malformed style rule: missing required fields "
                    f"(name={rule.name!r}, rule_type={rule.rule_type!r})"
                )
                continue
            valid_rules.append(rule)
        return valid_rules

    @staticmethod
    def _is_rule_valid(rule: StyleRule) -> bool:
        """Check if a style rule has all required fields.

        Args:
            rule: The rule to validate.

        Returns:
            True if the rule is valid.
        """
        if not rule.name or not rule.name.strip():
            return False
        if not rule.rule_type or not rule.rule_type.strip():
            return False
        # rule_type must be one of the known types
        valid_types = {"sentence_length", "passive_voice", "tone", "jargon"}
        if rule.rule_type not in valid_types:
            return False
        return True

    def _load_rules_from_file(self, rules_path: str) -> list[StyleRule]:
        """Load style rules from a YAML file.

        Args:
            rules_path: Path to the style_rules.yaml file.

        Returns:
            List of valid style rules.
        """
        path = Path(rules_path)

        if not path.exists():
            logger.warning(f"Style rules file not found: {rules_path}")
            return self._get_default_rules()

        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except (yaml.YAMLError, OSError) as e:
            logger.error(f"Error loading style rules: {e}")
            return self._get_default_rules()

        if not isinstance(data, dict) or "rules" not in data:
            logger.warning("Style rules file has invalid format")
            return self._get_default_rules()

        rules = []
        for rule_data in data["rules"]:
            if not isinstance(rule_data, dict):
                logger.error(f"Skipping non-dict rule entry: {rule_data}")
                continue

            try:
                severity_str = rule_data.get("severity", "suggestion")
                severity = Severity(severity_str)
            except ValueError:
                logger.error(
                    f"Invalid severity '{rule_data.get('severity')}' in rule "
                    f"'{rule_data.get('name', 'unknown')}'"
                )
                severity = Severity.SUGGESTION

            rule = StyleRule(
                name=rule_data.get("name", ""),
                rule_type=rule_data.get("rule_type", ""),
                severity=severity,
                enabled=rule_data.get("enabled", True),
                config=rule_data.get("config", {}),
            )
            rules.append(rule)

        return self._validate_rules(rules)

    def _get_default_rules(self) -> list[StyleRule]:
        """Get default style rules.

        Returns:
            List of default style rules.
        """
        return [
            StyleRule(
                name="sentence_length",
                rule_type="sentence_length",
                severity=Severity.WARNING,
                enabled=True,
                config={"max_words": self._max_sentence_length},
            ),
            StyleRule(
                name="passive_voice",
                rule_type="passive_voice",
                severity=Severity.SUGGESTION,
                enabled=self._detect_passive_voice,
                config={
                    "patterns": [
                        r"was \w+ed",
                        r"were \w+ed",
                        r"is being \w+ed",
                        r"has been \w+ed",
                        r"had been \w+ed",
                        r"will be \w+ed",
                    ]
                },
            ),
            StyleRule(
                name="jargon_avoidance",
                rule_type="jargon",
                severity=Severity.SUGGESTION,
                enabled=True,
                config={
                    "terms": [
                        {"term": "leverage", "alternative": "use"},
                        {"term": "utilize", "alternative": "use"},
                        {"term": "synergy", "alternative": "collaboration"},
                        {"term": "paradigm", "alternative": "model"},
                    ]
                },
            ),
        ]
