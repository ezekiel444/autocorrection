"""Plugin Registry - Load, validate, and execute correction plugins.

Provides plugin discovery from a directory, interface validation,
sequential execution with timeout enforcement, and error isolation.
"""

import importlib.util
import logging
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

import yaml

from .models import Correction, CorrectionType, PluginManifest, Severity

logger = logging.getLogger(__name__)

# Constraints
MAX_PLUGINS = 50
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass
class PluginIssue:
    """An issue identified by a plugin."""

    message: str
    start_offset: int
    end_offset: int
    original_text: str
    severity: str = "suggestion"  # error, warning, suggestion
    category: str = "style"


class CorrectionPlugin(Protocol):
    """Protocol defining the required plugin interface."""

    name: str
    version: str

    def analyze(self, text: str, language: str) -> list[PluginIssue]:
        """Identify issues in text."""
        ...

    def suggest(self, text: str, issue: PluginIssue) -> Optional[str]:
        """Suggest a correction for an identified issue."""
        ...


@dataclass
class LoadedPlugin:
    """A successfully loaded and validated plugin."""

    name: str
    version: str
    module: Any
    manifest: Optional[PluginManifest] = None
    config: dict = field(default_factory=dict)
    error_count: int = 0
    last_error: Optional[str] = None


@dataclass
class PluginExecutionResult:
    """Result of executing a single plugin."""

    plugin_name: str
    corrections: list[Correction]
    success: bool
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class PluginRegistry:
    """Manages plugin loading, validation, and execution.

    Features:
    - Load plugins from directory (max 50).
    - Validate interface: name, version, analyze, suggest.
    - Execute sequentially in alphabetical order.
    - 30-second timeout per plugin.
    - Catch exceptions, skip failing plugins.
    - YAML configuration per plugin.
    """

    def __init__(
        self,
        plugins_dir: Optional[str] = None,
        max_plugins: int = MAX_PLUGINS,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize the plugin registry.

        Args:
            plugins_dir: Path to the plugins directory.
            max_plugins: Maximum number of plugins to load.
            timeout_seconds: Timeout per plugin execution in seconds.
        """
        self._plugins_dir = plugins_dir
        self._max_plugins = max_plugins
        self._timeout_seconds = timeout_seconds
        self._plugins: dict[str, LoadedPlugin] = {}

    @property
    def plugin_count(self) -> int:
        """Number of loaded plugins."""
        return len(self._plugins)

    @property
    def plugin_names(self) -> list[str]:
        """Names of loaded plugins in alphabetical order."""
        return sorted(self._plugins.keys())

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get a loaded plugin by name.

        Args:
            name: The plugin name.

        Returns:
            The LoadedPlugin, or None if not found.
        """
        return self._plugins.get(name)

    def load_plugins(self) -> list[str]:
        """Load all plugins from the configured directory.

        Returns:
            List of successfully loaded plugin names.
        """
        if not self._plugins_dir:
            logger.info("No plugins directory configured")
            return []

        plugins_path = Path(self._plugins_dir)
        if not plugins_path.exists():
            logger.warning(f"Plugins directory not found: {self._plugins_dir}")
            return []

        if not plugins_path.is_dir():
            logger.error(f"Plugins path is not a directory: {self._plugins_dir}")
            return []

        loaded_names = []
        plugin_dirs = sorted(plugins_path.iterdir())

        for item in plugin_dirs:
            if len(self._plugins) >= self._max_plugins:
                logger.warning(
                    f"Maximum plugin count ({self._max_plugins}) reached, "
                    f"skipping remaining plugins"
                )
                break

            if item.is_dir():
                result = self._load_plugin_from_dir(item)
                if result:
                    loaded_names.append(result)
            elif item.suffix == ".py" and item.name != "__init__.py":
                result = self._load_plugin_from_file(item)
                if result:
                    loaded_names.append(result)

        logger.info(f"Loaded {len(loaded_names)} plugins: {loaded_names}")
        return loaded_names

    def _load_plugin_from_dir(self, plugin_dir: Path) -> Optional[str]:
        """Load a plugin from a directory containing a Python module and config.

        Args:
            plugin_dir: Path to the plugin directory.

        Returns:
            Plugin name if loaded successfully, None otherwise.
        """
        # Look for main module
        main_file = plugin_dir / "main.py"
        if not main_file.exists():
            main_file = plugin_dir / "__init__.py"
            if not main_file.exists():
                logger.warning(
                    f"Plugin directory '{plugin_dir.name}' has no main.py or __init__.py"
                )
                return None

        # Load config if available
        config = self._load_plugin_config(plugin_dir)

        # Check if plugin is disabled in config
        if config and not config.get("enabled", True):
            logger.info(f"Plugin '{plugin_dir.name}' is disabled in config")
            return None

        # Load the module
        return self._load_and_validate_module(main_file, config)

    def _load_plugin_from_file(self, plugin_file: Path) -> Optional[str]:
        """Load a plugin from a single Python file.

        Args:
            plugin_file: Path to the plugin .py file.

        Returns:
            Plugin name if loaded successfully, None otherwise.
        """
        # Check for adjacent YAML config
        config_path = plugin_file.with_suffix(".yaml")
        config = {}
        if config_path.exists():
            config = self._load_plugin_config(config_path.parent, config_path.name)

        return self._load_and_validate_module(plugin_file, config)

    def _load_and_validate_module(
        self, module_path: Path, config: dict
    ) -> Optional[str]:
        """Load a Python module and validate it implements the plugin interface.

        Args:
            module_path: Path to the Python file.
            config: Plugin configuration dict.

        Returns:
            Plugin name if valid, None otherwise.
        """
        module_name = f"plugin_{module_path.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                logger.error(f"Cannot create module spec for: {module_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

        except Exception as e:
            logger.error(f"Error loading plugin module '{module_path}': {e}")
            return None

        # Validate interface
        if not self._validate_plugin_interface(module, str(module_path)):
            return None

        plugin_name = getattr(module, "name")
        plugin_version = getattr(module, "version", "0.0.0")

        # Store the plugin
        self._plugins[plugin_name] = LoadedPlugin(
            name=plugin_name,
            version=plugin_version,
            module=module,
            config=config,
            manifest=PluginManifest(
                name=plugin_name,
                version=plugin_version,
                enabled=True,
                config_path=str(module_path),
                timeout_seconds=config.get("timeout", self._timeout_seconds),
            ),
        )

        logger.info(f"Loaded plugin: {plugin_name} v{plugin_version}")
        return plugin_name

    def _validate_plugin_interface(self, module: Any, source: str) -> bool:
        """Validate that a module implements the required plugin interface.

        Required: name (str), version (str), analyze (callable), suggest (callable).

        Args:
            module: The loaded Python module.
            source: Source path for error messages.

        Returns:
            True if the module is a valid plugin.
        """
        # Check 'name' attribute
        if not hasattr(module, "name"):
            logger.error(f"Plugin '{source}' missing required 'name' attribute")
            return False
        if not isinstance(getattr(module, "name"), str):
            logger.error(f"Plugin '{source}' 'name' must be a string")
            return False

        # Check 'version' attribute
        if not hasattr(module, "version"):
            logger.error(f"Plugin '{source}' missing required 'version' attribute")
            return False
        if not isinstance(getattr(module, "version"), str):
            logger.error(f"Plugin '{source}' 'version' must be a string")
            return False

        # Check 'analyze' callable
        if not hasattr(module, "analyze"):
            logger.error(f"Plugin '{source}' missing required 'analyze' function")
            return False
        if not callable(getattr(module, "analyze")):
            logger.error(f"Plugin '{source}' 'analyze' must be callable")
            return False

        # Check 'suggest' callable
        if not hasattr(module, "suggest"):
            logger.error(f"Plugin '{source}' missing required 'suggest' function")
            return False
        if not callable(getattr(module, "suggest")):
            logger.error(f"Plugin '{source}' 'suggest' must be callable")
            return False

        return True

    def _load_plugin_config(
        self, directory: Path, filename: str = "config.yaml"
    ) -> dict:
        """Load plugin configuration from a YAML file.

        Args:
            directory: Directory containing the config file.
            filename: Name of the config file.

        Returns:
            Configuration dictionary, empty if not found or invalid.
        """
        config_path = directory / filename

        # Also try plugin.yaml
        if not config_path.exists():
            config_path = directory / "plugin.yaml"
        if not config_path.exists():
            return {}

        try:
            content = config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            return data if isinstance(data, dict) else {}
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"Error loading plugin config '{config_path}': {e}")
            return {}

    def execute_all(
        self, text: str, language: str
    ) -> list[PluginExecutionResult]:
        """Execute all loaded plugins sequentially in alphabetical order.

        Each plugin has a timeout. Failing plugins are skipped and their
        errors are logged.

        Args:
            text: The text to analyze.
            language: The detected language code.

        Returns:
            List of execution results from all plugins.
        """
        results = []

        for plugin_name in self.plugin_names:
            plugin = self._plugins[plugin_name]
            result = self._execute_plugin(plugin, text, language)
            results.append(result)

        return results

    def _execute_plugin(
        self, plugin: LoadedPlugin, text: str, language: str
    ) -> PluginExecutionResult:
        """Execute a single plugin with timeout and error handling.

        Args:
            plugin: The plugin to execute.
            text: The text to analyze.
            language: The detected language code.

        Returns:
            PluginExecutionResult with corrections or error info.
        """
        import time

        start_time = time.time()
        timeout = (
            plugin.manifest.timeout_seconds
            if plugin.manifest
            else self._timeout_seconds
        )

        try:
            # Run analyze with timeout
            issues = self._run_with_timeout(
                lambda: plugin.module.analyze(text, language),
                timeout,
            )

            if issues is None:
                return PluginExecutionResult(
                    plugin_name=plugin.name,
                    corrections=[],
                    success=False,
                    error=f"Plugin timed out after {timeout}s",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Get suggestions for each issue
            corrections = []
            for issue in issues:
                try:
                    suggestion = self._run_with_timeout(
                        lambda i=issue: plugin.module.suggest(text, i),
                        timeout,
                    )

                    # Map severity string to enum
                    try:
                        severity = Severity(
                            getattr(issue, "severity", "suggestion")
                        )
                    except ValueError:
                        severity = Severity.SUGGESTION

                    # Map category to correction type
                    try:
                        correction_type = CorrectionType(
                            getattr(issue, "category", "style")
                        )
                    except ValueError:
                        correction_type = CorrectionType.STYLE

                    corrections.append(
                        Correction(
                            original_text=getattr(issue, "original_text", ""),
                            suggested_text=suggestion or "",
                            correction_type=correction_type,
                            confidence=0.5,
                            reason=getattr(issue, "message", "Plugin suggestion"),
                            start_offset=getattr(issue, "start_offset", 0),
                            end_offset=getattr(issue, "end_offset", 0),
                            severity=severity,
                            rule_name=f"plugin:{plugin.name}",
                            source=f"plugin:{plugin.name}",
                        )
                    )
                except Exception as e:
                    logger.warning(
                        f"Plugin '{plugin.name}' suggest() failed for issue: {e}"
                    )
                    continue

            elapsed = (time.time() - start_time) * 1000
            return PluginExecutionResult(
                plugin_name=plugin.name,
                corrections=corrections,
                success=True,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            plugin.error_count += 1
            plugin.last_error = str(e)
            logger.error(f"Plugin '{plugin.name}' execution failed: {e}")
            return PluginExecutionResult(
                plugin_name=plugin.name,
                corrections=[],
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )

    def _run_with_timeout(self, func: Callable, timeout: int) -> Any:
        """Run a function with a timeout.

        Args:
            func: The function to execute.
            timeout: Timeout in seconds.

        Returns:
            The function result, or None if timed out.
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError:
                logger.warning(f"Plugin execution timed out after {timeout}s")
                return None
            except Exception as e:
                raise e

    def get_all_corrections(
        self, text: str, language: str
    ) -> list[Correction]:
        """Execute all plugins and return merged corrections.

        Args:
            text: The text to analyze.
            language: The detected language code.

        Returns:
            Merged list of corrections from all plugins.
        """
        results = self.execute_all(text, language)
        corrections = []
        for result in results:
            if result.success:
                corrections.extend(result.corrections)
        return corrections
