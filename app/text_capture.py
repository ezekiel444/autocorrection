"""Text Capture Module - Cross-platform clipboard integration with input validation.

Provides clipboard read/write using platform-appropriate backends:
- Windows: pyperclip (uses win32 APIs internally)
- Linux: xclip/xsel with pyperclip fallback
- macOS: pyperclip (uses pbcopy/pbpaste internally)

Includes input validation and formatting preservation.
"""

import sys
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CaptureError(Exception):
    """Raised when text capture fails."""

    pass


class ClipboardBackend(Enum):
    """Available clipboard backends in priority order."""

    XCLIP = "xclip"
    XSEL = "xsel"
    PYPERCLIP = "pyperclip"


@dataclass
class CaptureResult:
    """Result of a text capture operation."""

    text: str
    backend_used: ClipboardBackend
    character_count: int
    has_formatting: bool


# Maximum allowed text length (100,000 characters)
MAX_TEXT_LENGTH = 100_000


def validate_text(text: str) -> tuple[bool, Optional[str]]:
    """Validate captured text against input constraints.

    Args:
        text: The text to validate.

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if text is None:
        return False, "Text is None"

    if len(text) == 0:
        return False, "Text is empty"

    if text.isspace():
        return False, "Text contains only whitespace characters"

    if not text.strip():
        return False, "Text contains only whitespace characters"

    if len(text) > MAX_TEXT_LENGTH:
        return False, (
            f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters "
            f"(actual: {len(text)})"
        )

    return True, None


def has_formatting_markers(text: str) -> bool:
    """Check if text contains formatting markers that need preservation.

    Args:
        text: The text to check.

    Returns:
        True if the text contains formatting markers.
    """
    formatting_chars = {"\n", "\r", "\t", "\v", "\f", "\u2028", "\u2029"}
    return any(c in text for c in formatting_chars)


def _detect_clipboard_backend() -> ClipboardBackend:
    """Detect the best available clipboard backend based on platform.

    On Windows and macOS, pyperclip is used directly (it handles
    platform-specific clipboard APIs internally).
    On Linux, xclip/xsel are preferred with pyperclip as fallback.

    Returns:
        The detected backend.

    Raises:
        CaptureError: If no clipboard backend is available.
    """
    # On Windows or macOS, go straight to pyperclip (uses win32/pbcopy internally)
    if sys.platform in ("win32", "darwin"):
        try:
            import pyperclip  # noqa: F401

            # Verify pyperclip can actually access the clipboard
            pyperclip.determine_clipboard()
            return ClipboardBackend.PYPERCLIP
        except ImportError:
            raise CaptureError(
                "pyperclip is not installed. Install with: pip install pyperclip"
            )
        except Exception as e:
            raise CaptureError(
                f"Clipboard not accessible on {sys.platform}: {e}. "
                "Ensure pyperclip is installed: pip install pyperclip"
            )

    # On Linux, prefer xclip/xsel, fall back to pyperclip
    if shutil.which("xclip"):
        return ClipboardBackend.XCLIP
    if shutil.which("xsel"):
        return ClipboardBackend.XSEL

    # Try pyperclip as fallback on Linux
    try:
        import pyperclip  # noqa: F401

        return ClipboardBackend.PYPERCLIP
    except ImportError:
        pass

    raise CaptureError(
        "No clipboard backend available. "
        "On Linux, install xclip (`sudo apt install xclip`) or xsel, "
        "or install pyperclip (`pip install pyperclip`)."
    )


def read_clipboard(backend: Optional[ClipboardBackend] = None) -> CaptureResult:
    """Read text from the system clipboard.

    Uses platform-appropriate backend. Preserves all formatting markers.

    Args:
        backend: Force a specific backend. Auto-detects if None.

    Returns:
        CaptureResult with the clipboard text and metadata.

    Raises:
        CaptureError: If clipboard cannot be read or text is invalid.
    """
    if backend is None:
        backend = _detect_clipboard_backend()

    text = _read_from_backend(backend)

    is_valid, error = validate_text(text)
    if not is_valid:
        raise CaptureError(f"Invalid clipboard content: {error}")

    return CaptureResult(
        text=text,
        backend_used=backend,
        character_count=len(text),
        has_formatting=has_formatting_markers(text),
    )


def _read_from_backend(backend: ClipboardBackend) -> str:
    """Read clipboard content using the specified backend.

    Args:
        backend: The clipboard backend to use.

    Returns:
        The clipboard text content.

    Raises:
        CaptureError: If the read operation fails.
    """
    try:
        if backend == ClipboardBackend.XCLIP:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise CaptureError(
                    f"xclip read failed: {result.stderr.strip() or 'unknown error'}"
                )
            return result.stdout

        elif backend == ClipboardBackend.XSEL:
            result = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise CaptureError(
                    f"xsel read failed: {result.stderr.strip() or 'unknown error'}"
                )
            return result.stdout

        elif backend == ClipboardBackend.PYPERCLIP:
            import pyperclip

            text = pyperclip.paste()
            if text is None:
                return ""
            return text

        else:
            raise CaptureError(f"Unknown backend: {backend}")

    except CaptureError:
        raise
    except subprocess.TimeoutExpired:
        raise CaptureError(f"Clipboard read timed out using {backend.value}")
    except FileNotFoundError:
        raise CaptureError(f"{backend.value} not found on system")
    except PermissionError:
        raise CaptureError(
            f"Permission denied accessing clipboard via {backend.value}. "
            "Ensure the display server is accessible."
        )
    except Exception as e:
        raise CaptureError(f"Clipboard read failed ({backend.value}): {e}")


def write_clipboard(
    text: str, backend: Optional[ClipboardBackend] = None
) -> ClipboardBackend:
    """Write text to the system clipboard.

    Preserves all formatting markers in the written text.

    Args:
        text: The text to write to clipboard.
        backend: Force a specific backend. Auto-detects if None.

    Returns:
        The backend that was used.

    Raises:
        CaptureError: If clipboard cannot be written.
    """
    if backend is None:
        backend = _detect_clipboard_backend()

    _write_to_backend(text, backend)
    return backend


def _write_to_backend(text: str, backend: ClipboardBackend) -> None:
    """Write text to clipboard using the specified backend.

    Args:
        text: The text to write.
        backend: The clipboard backend to use.

    Raises:
        CaptureError: If the write operation fails.
    """
    try:
        if backend == ClipboardBackend.XCLIP:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-i"],
                input=text,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise CaptureError(
                    f"xclip write failed: {result.stderr.strip() or 'unknown error'}"
                )

        elif backend == ClipboardBackend.XSEL:
            result = subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise CaptureError(
                    f"xsel write failed: {result.stderr.strip() or 'unknown error'}"
                )

        elif backend == ClipboardBackend.PYPERCLIP:
            import pyperclip

            pyperclip.copy(text)

        else:
            raise CaptureError(f"Unknown backend: {backend}")

    except CaptureError:
        raise
    except subprocess.TimeoutExpired:
        raise CaptureError(f"Clipboard write timed out using {backend.value}")
    except FileNotFoundError:
        raise CaptureError(f"{backend.value} not found on system")
    except PermissionError:
        raise CaptureError(
            f"Permission denied accessing clipboard via {backend.value}. "
            "Ensure the display server is accessible."
        )
    except Exception as e:
        raise CaptureError(f"Clipboard write failed ({backend.value}): {e}")


def capture_and_validate(
    backend: Optional[ClipboardBackend] = None,
) -> CaptureResult:
    """Capture text from clipboard and validate it.

    This is the main entry point for the text capture pipeline.
    It reads from the clipboard, validates the content, and returns
    a structured result preserving all formatting.

    Args:
        backend: Force a specific backend. Auto-detects if None.

    Returns:
        CaptureResult with validated text.

    Raises:
        CaptureError: If capture fails or text is invalid.
    """
    return read_clipboard(backend)
