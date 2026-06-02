"""Configuration Manager - YAML loading with defaults and validation.

Provides configuration loading from YAML files with full default fallback,
validation of setting values, and graceful handling of missing/malformed files.
Supports round-trip serialization.
"""

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


# ─── Default Configuration ────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "default_language": "en",
        "auto_apply_high_confidence": False,
        "clipboard_monitoring": False,
        "clipboard_min_length": 10,
        "clipboard_max_length": 5000,
        "max_text_length": 100000,
        "history_retention_days": 30,
    },
    "language": {
        "supported": ["en", "fr", "es", "de", "pt"],
        "detection_threshold": 0.7,
        "default_on_low_confidence": "en",
    },
    "style_guide": {
        "enabled": True,
        "max_sentence_length": 30,
        "detect_passive_voice": True,
        "tone": "neutral",
        "custom_rules_path": "/config/style_rules.yaml",
    },
    "hotkeys": {
        "analyze": "ctrl+alt+c",
        "analyze_and_apply": "ctrl+alt+a",
    },
    "api": {
        "port": 8080,
        "rate_limit_per_minute": 60,
    },
    "batch": {
        "default_segment_size": 1000,
        "min_segment_size": 100,
        "max_segment_size": 5000,
    },
    "plugins": {
        "directory": "/plugins",
        "max_plugins": 50,
        "execution_timeout_seconds": 30,
    },
    "model": {
        "name": "llama3.2:3b",
        "context_window": 4096,
        "temperature": 0.3,
        "top_p": 0.9,
    },
}


# ─── Validation Constraints ───────────────────────────────────────────────────

@dataclass
class ValidationConstraint:
    """Defines validation rules for a configuration setting."""

    setting_type: type
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    allowed_values: Optional[list[Any]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None


# Constraints for each setting path (dot-separated)
VALIDATION_CONSTRAINTS: dict[str, ValidationConstraint] = {
    "general.default_language": ValidationConstraint(
        setting_type=str, allowed_values=["en", "fr", "es", "de", "pt"]
    ),
    "general.auto_apply_high_confidence": ValidationConstraint(setting_type=bool),
    "general.clipboard_monitoring": ValidationConstraint(setting_type=bool),
    "general.clipboard_min_length": ValidationConstraint(
        setting_type=int, min_value=1, max_value=10000
    ),
    "general.clipboard_max_length": ValidationConstraint(
        setting_type=int, min_value=100, max_value=100000
    ),
    "general.max_text_length": ValidationConstraint(
        setting_type=int, min_value=1000, max_value=1000000
    ),
    "general.history_retention_days": ValidationConstraint(
        setting_type=int, min_value=1, max_value=365
    ),
    "language.detection_threshold": ValidationConstraint(
        setting_type=float, min_value=0.0, max_value=1.0
    ),
    "language.default_on_low_confidence": ValidationConstraint(
        setting_type=str, allowed_values=["en", "fr", "es", "de", "pt"]
    ),
    "language.supported": ValidationConstraint(setting_type=list, min_length=1),
    "style_guide.enabled": ValidationConstraint(setting_type=bool),
    "style_guide.max_sentence_length": ValidationConstraint(
        setting_type=int, min_value=5, max_value=200
    ),
    "style_guide.detect_passive_voice": ValidationConstraint(setting_type=bool),
    "style_guide.tone": ValidationConstraint(
        setting_type=str, allowed_values=["formal", "informal", "neutral"]
    ),
    "style_guide.custom_rules_path": ValidationConstraint(setting_type=str),
    "hotkeys.analyze": ValidationConstraint(setting_type=str),
    "hotkeys.analyze_and_apply": ValidationConstraint(setting_type=str),
    "api.port": ValidationConstraint(
        setting_type=int, min_value=1, max_value=65535
    ),
    "api.rate_limit_per_minute": ValidationConstraint(
        setting_type=int, min_value=1, max_value=10000
    ),
    "batch.default_segment_size": ValidationConstraint(
        setting_type=int, min_value=100, max_value=5000
    ),
    "batch.min_segment_size": ValidationConstraint(
        setting_type=int, min_value=10, max_value=1000
    ),
    "batch.max_segment_size": ValidationConstraint(
        setting_type=int, min_value=500, max_value=50000
    ),
    "plugins.directory": ValidationConstraint(setting_type=str),
    "plugins.max_plugins": ValidationConstraint(
        setting_type=int, min_value=1, max_value=200
    ),
    "plugins.execution_timeout_seconds": ValidationConstraint(
        setting_type=int, min_value=1, max_value=300
    ),
    "model.name": ValidationConstraint(setting_type=str),
    "model.context_window": ValidationConstraint(
        setting_type=int, min_value=512, max_value=131072
    ),
    "model.temperature": ValidationConstraint(
        setting_type=float, min_value=0.0, max_value=2.0
    ),
    "model.top_p": ValidationConstraint(
        setting_type=float, min_value=0.0, max_value=1.0
    ),
}


# ─── Validation Error ─────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    """Describes a validation failure for a specific setting."""

    path: str
    value: Any
    constraint: str
    message: str


# ─── Configuration Manager ────────────────────────────────────────────────────

class ConfigManager:
    """Manages application configuration with YAML persistence.

    Features:
    - Loads settings from YAML with full default fallback.
    - Validates all setting values against defined constraints.
    - Handles missing, empty, or malformed YAML files gracefully.
    - Supports round-trip serialization (serialize → deserialize = equivalent).
    - Rejects invalid values while retaining previous valid values.
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the configuration manager.

        Args:
            config_path: Path to the YAML configuration file.
                        If None, uses defaults only.
        """
        self._config_path = config_path
        self._config: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self._validation_errors: list[ValidationError] = []

    @property
    def config(self) -> dict[str, Any]:
        """Get the current configuration dictionary."""
        return self._config

    @property
    def validation_errors(self) -> list[ValidationError]:
        """Get validation errors from the last load operation."""
        return self._validation_errors

    def load(self) -> dict[str, Any]:
        """Load configuration from YAML file with default fallback.

        If the file is missing, empty, or malformed, returns full defaults.
        Invalid values are rejected and defaults are used for those settings.

        Returns:
            The loaded (and validated) configuration dictionary.
        """
        self._validation_errors = []

        if self._config_path is None:
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            return self._config

        file_path = Path(self._config_path)

        # Handle missing file
        if not file_path.exists():
            logger.warning(
                f"Configuration file not found: {self._config_path}. Using defaults."
            )
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            return self._config

        # Read and parse YAML
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, IOError) as e:
            logger.warning(
                f"Cannot read configuration file: {e}. Using defaults."
            )
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            return self._config

        # Handle empty file
        if not content.strip():
            logger.warning("Configuration file is empty. Using defaults.")
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            return self._config

        # Parse YAML
        try:
            loaded = yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.warning(
                f"Malformed YAML in configuration file: {e}. Using defaults."
            )
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            return self._config

        # Handle non-dict YAML (e.g., a scalar or list at top level)
        if not isinstance(loaded, dict):
            logger.warning(
                "Configuration file does not contain a mapping. Using defaults."
            )
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            return self._config

        # Merge loaded config with defaults (loaded values override defaults)
        merged = copy.deepcopy(DEFAULT_CONFIG)
        self._deep_merge(merged, loaded)

        # Validate all settings
        validated = self._validate_config(merged)
        self._config = validated

        return self._config

    def get(self, path: str, default: Any = None) -> Any:
        """Get a configuration value by dot-separated path.

        Args:
            path: Dot-separated path (e.g., "general.default_language").
            default: Value to return if path not found.

        Returns:
            The configuration value, or default if not found.
        """
        keys = path.split(".")
        current = self._config

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    def set(self, path: str, value: Any) -> Optional[ValidationError]:
        """Set a configuration value with validation.

        If the value is invalid, the previous value is retained and
        a ValidationError is returned.

        Args:
            path: Dot-separated path (e.g., "general.default_language").
            value: The new value to set.

        Returns:
            ValidationError if validation failed, None if successful.
        """
        # Validate the value
        error = self._validate_value(path, value)
        if error:
            self._validation_errors.append(error)
            return error

        # Set the value
        keys = path.split(".")
        current = self._config

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value
        return None

    def serialize(self) -> str:
        """Serialize current configuration to YAML string.

        Returns:
            YAML string representation of the configuration.
        """
        return yaml.dump(
            self._config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def save(self) -> bool:
        """Save current configuration to the YAML file.

        Returns:
            True if saved successfully, False otherwise.
        """
        if self._config_path is None:
            logger.error("No configuration file path set.")
            return False

        try:
            file_path = Path(self._config_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(self.serialize(), encoding="utf-8")
            return True
        except (OSError, IOError) as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def reset_to_defaults(self) -> dict[str, Any]:
        """Reset all settings to their default values.

        Returns:
            The default configuration dictionary.
        """
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._validation_errors = []
        return self._config

    @staticmethod
    def get_defaults() -> dict[str, Any]:
        """Get a copy of the default configuration.

        Returns:
            Deep copy of the default configuration dictionary.
        """
        return copy.deepcopy(DEFAULT_CONFIG)

    # ─── Private Methods ──────────────────────────────────────────────────

    def _deep_merge(self, base: dict, override: dict) -> None:
        """Recursively merge override dict into base dict (in-place).

        Args:
            base: The base dictionary to merge into.
            override: The override dictionary with values to apply.
        """
        for key, value in override.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate all settings in a configuration dictionary.

        Invalid values are replaced with defaults.

        Args:
            config: The configuration to validate.

        Returns:
            Validated configuration with invalid values replaced by defaults.
        """
        validated = copy.deepcopy(config)

        for path, constraint in VALIDATION_CONSTRAINTS.items():
            keys = path.split(".")
            value = self._get_nested(validated, keys)

            if value is None:
                # Missing value, use default
                default_value = self._get_nested(DEFAULT_CONFIG, keys)
                self._set_nested(validated, keys, default_value)
                continue

            error = self._validate_value(path, value)
            if error:
                self._validation_errors.append(error)
                # Replace with default
                default_value = self._get_nested(DEFAULT_CONFIG, keys)
                self._set_nested(validated, keys, default_value)

        return validated

    def _validate_value(self, path: str, value: Any) -> Optional[ValidationError]:
        """Validate a single setting value against its constraints.

        Args:
            path: Dot-separated setting path.
            value: The value to validate.

        Returns:
            ValidationError if invalid, None if valid.
        """
        constraint = VALIDATION_CONSTRAINTS.get(path)
        if constraint is None:
            # No constraint defined, accept any value
            return None

        # Type check
        if constraint.setting_type == float:
            # Accept int as float
            if not isinstance(value, (int, float)):
                return ValidationError(
                    path=path,
                    value=value,
                    constraint="type",
                    message=f"Expected {constraint.setting_type.__name__}, got {type(value).__name__}",
                )
        elif not isinstance(value, constraint.setting_type):
            return ValidationError(
                path=path,
                value=value,
                constraint="type",
                message=f"Expected {constraint.setting_type.__name__}, got {type(value).__name__}",
            )

        # Range check for numeric types
        if constraint.min_value is not None and value < constraint.min_value:
            return ValidationError(
                path=path,
                value=value,
                constraint="min_value",
                message=f"Value {value} is below minimum {constraint.min_value}",
            )

        if constraint.max_value is not None and value > constraint.max_value:
            return ValidationError(
                path=path,
                value=value,
                constraint="max_value",
                message=f"Value {value} exceeds maximum {constraint.max_value}",
            )

        # Allowed values check
        if constraint.allowed_values is not None and value not in constraint.allowed_values:
            return ValidationError(
                path=path,
                value=value,
                constraint="allowed_values",
                message=f"Value '{value}' not in allowed values: {constraint.allowed_values}",
            )

        # Length check for sequences
        if constraint.min_length is not None and hasattr(value, "__len__"):
            if len(value) < constraint.min_length:
                return ValidationError(
                    path=path,
                    value=value,
                    constraint="min_length",
                    message=f"Length {len(value)} is below minimum {constraint.min_length}",
                )

        if constraint.max_length is not None and hasattr(value, "__len__"):
            if len(value) > constraint.max_length:
                return ValidationError(
                    path=path,
                    value=value,
                    constraint="max_length",
                    message=f"Length {len(value)} exceeds maximum {constraint.max_length}",
                )

        return None

    @staticmethod
    def _get_nested(d: dict, keys: list[str]) -> Any:
        """Get a value from a nested dictionary by key path.

        Args:
            d: The dictionary to traverse.
            keys: List of keys forming the path.

        Returns:
            The value at the path, or None if not found.
        """
        current = d
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    @staticmethod
    def _set_nested(d: dict, keys: list[str], value: Any) -> None:
        """Set a value in a nested dictionary by key path.

        Args:
            d: The dictionary to modify.
            keys: List of keys forming the path.
            value: The value to set.
        """
        current = d
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
