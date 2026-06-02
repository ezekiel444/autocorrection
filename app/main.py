"""System Tray Application - Cross-platform desktop UI for the Auto-Correction Tool.

Provides system tray icon with status indicators, hotkey management,
clipboard monitoring, and desktop notifications.
Works on Windows, Linux, and macOS.
"""

import logging
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import httpx

from .text_capture import (
    CaptureError,
    CaptureResult,
    capture_and_validate,
    write_clipboard,
)

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

API_GATEWAY_URL = "http://localhost:8080"
DEFAULT_API_KEY = "changeme"
CLIPBOARD_POLL_INTERVAL = 0.3  # 300ms
CLIPBOARD_MIN_LENGTH = 10
CLIPBOARD_MAX_LENGTH = 5000


# ─── Status Enum ──────────────────────────────────────────────────────────────


class AppStatus(Enum):
    """Application status indicators."""

    IDLE = "idle"
    PROCESSING = "processing"
    ERROR = "error"


# ─── Hotkey Manager ───────────────────────────────────────────────────────────


@dataclass
class HotkeyBinding:
    """A registered hotkey binding."""

    keys: str  # e.g., "ctrl+alt+c"
    action: str  # e.g., "analyze"
    callback: Optional[Callable] = None


class HotkeyManager:
    """Manages global keyboard shortcuts using pynput.

    Registers system-wide hotkeys for triggering text analysis
    and auto-apply actions. Supports both left and right modifier keys
    on all platforms (Windows, Linux, macOS).
    """

    def __init__(self):
        """Initialize the hotkey manager."""
        self._bindings: dict[str, HotkeyBinding] = {}
        self._listener = None
        self._active_keys: set = set()
        self._running = False
        self._hotkeys_available = True

    @property
    def hotkeys_available(self) -> bool:
        """Whether hotkeys are currently functional."""
        return self._hotkeys_available

    @staticmethod
    def validate_hotkey(hotkey_str: str) -> tuple[bool, Optional[str]]:
        """Validate a hotkey combination string."""
        modifiers = {"ctrl", "alt", "shift", "super", "cmd", "meta"}
        parts = [p.strip().lower() for p in hotkey_str.split("+")]

        if len(parts) < 2:
            return False, "Hotkey must have at least one modifier and one key"

        modifier_parts = [p for p in parts if p in modifiers]
        key_parts = [p for p in parts if p not in modifiers]

        if not modifier_parts:
            return False, "Hotkey must include at least one modifier key"

        if len(key_parts) != 1:
            return False, "Hotkey must include exactly one non-modifier key"

        if not key_parts[0]:
            return False, "Non-modifier key cannot be empty"

        return True, None

    def register(self, hotkey_str: str, action: str, callback: Callable) -> bool:
        """Register a hotkey binding."""
        is_valid, error = self.validate_hotkey(hotkey_str)
        if not is_valid:
            logger.error(f"Invalid hotkey '{hotkey_str}': {error}")
            return False

        self._bindings[action] = HotkeyBinding(
            keys=hotkey_str.lower(),
            action=action,
            callback=callback,
        )
        logger.info(f"Registered hotkey: {hotkey_str} -> {action}")
        return True

    @staticmethod
    def _normalize_key(key):
        """Normalize a key to a canonical form for comparison.

        Maps right-side modifiers to left-side equivalents.
        Normalizes character keys to lowercase string representation.
        Handles platform differences in key reporting.
        """
        try:
            from pynput import keyboard

            # Map right modifiers to left equivalents
            modifier_map = {
                keyboard.Key.ctrl_r: keyboard.Key.ctrl_l,
                keyboard.Key.alt_r: keyboard.Key.alt_l,
                keyboard.Key.shift_r: keyboard.Key.shift_l,
                keyboard.Key.alt_gr: keyboard.Key.alt_l,
            }

            if key in modifier_map:
                return modifier_map[key]

            # For character keys, normalize to a string representation
            if hasattr(key, 'char') and key.char is not None:
                return key.char.lower()

            # For virtual key codes on Windows, try to get the character
            if hasattr(key, 'vk') and key.vk is not None:
                # vk codes 65-90 are A-Z
                if 65 <= key.vk <= 90:
                    return chr(key.vk).lower()
                # vk codes 48-57 are 0-9
                if 48 <= key.vk <= 57:
                    return chr(key.vk)

            return key
        except ImportError:
            return key

    def start(self) -> None:
        """Start listening for hotkey events."""
        if self._running:
            return

        self._running = True

        try:
            from pynput import keyboard

            def _parse_hotkey(hotkey_str: str):
                """Parse hotkey string into a set of canonical key representations.

                Uses normalized forms so both left and right modifiers match.
                Supports: ctrl, shift, alt, super/cmd, space, tab, enter, f1-f12.
                """
                parts = hotkey_str.split("+")
                keys = set()
                for part in parts:
                    part = part.strip().lower()
                    if part == "ctrl":
                        keys.add(keyboard.Key.ctrl_l)
                    elif part == "shift":
                        keys.add(keyboard.Key.shift_l)
                    elif part == "alt":
                        keys.add(keyboard.Key.alt_l)
                    elif part in ("super", "cmd"):
                        keys.add(keyboard.Key.cmd)
                    elif part == "space":
                        keys.add(keyboard.Key.space)
                    elif part == "tab":
                        keys.add(keyboard.Key.tab)
                    elif part == "enter":
                        keys.add(keyboard.Key.enter)
                    elif part.startswith("f") and part[1:].isdigit():
                        # F1-F12 keys
                        fnum = int(part[1:])
                        fkey = getattr(keyboard.Key, f"f{fnum}", None)
                        if fkey:
                            keys.add(fkey)
                        else:
                            keys.add(part)
                    else:
                        # Store character keys as lowercase string
                        keys.add(part.lower())
                return keys

            # Build hotkey sets using canonical forms
            hotkey_sets = {}
            for action, binding in self._bindings.items():
                hotkey_sets[action] = _parse_hotkey(binding.keys)

            def on_press(key):
                try:
                    normalized = self._normalize_key(key)
                    self._active_keys.add(normalized)
                    for action, key_set in hotkey_sets.items():
                        if key_set.issubset(self._active_keys):
                            binding = self._bindings[action]
                            if binding.callback:
                                threading.Thread(
                                    target=binding.callback, daemon=True
                                ).start()
                except Exception as e:
                    logger.debug(f"Hotkey on_press error: {e}")

            def on_release(key):
                try:
                    normalized = self._normalize_key(key)
                    self._active_keys.discard(normalized)
                except Exception as e:
                    logger.debug(f"Hotkey on_release error: {e}")

            self._listener = keyboard.Listener(
                on_press=on_press, on_release=on_release
            )
            self._listener.start()
            self._hotkeys_available = True
            logger.info("Hotkey listener started")

        except ImportError:
            self._hotkeys_available = False
            msg = (
                "WARNING: pynput is not installed. Hotkeys are disabled. "
                "Install with: pip install pynput"
            )
            logger.warning(msg)
            print(msg, file=sys.stderr)
        except Exception as e:
            self._hotkeys_available = False
            msg = f"WARNING: Failed to start hotkey listener: {e}"
            logger.error(msg)
            print(msg, file=sys.stderr)

    def stop(self) -> None:
        """Stop listening for hotkey events."""
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        logger.info("Hotkey listener stopped")


# ─── Clipboard Monitor ────────────────────────────────────────────────────────


class ClipboardMonitor:
    """Monitors clipboard for new text content.

    Detects clipboard changes within 300ms, filters by length,
    and ignores self-originated changes to prevent feedback loops.
    """

    def __init__(
        self,
        on_text_captured: Optional[Callable[[str], None]] = None,
        min_length: int = CLIPBOARD_MIN_LENGTH,
        max_length: int = CLIPBOARD_MAX_LENGTH,
        poll_interval: float = CLIPBOARD_POLL_INTERVAL,
    ):
        """Initialize the clipboard monitor."""
        self._callback = on_text_captured
        self._min_length = min_length
        self._max_length = max_length
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_content: Optional[str] = None
        self._self_originated: set[str] = set()
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        """Whether clipboard monitoring is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable clipboard monitoring."""
        self._enabled = True
        if not self._running:
            self.start()

    def disable(self) -> None:
        """Disable clipboard monitoring."""
        self._enabled = False

    def mark_self_originated(self, text: str) -> None:
        """Mark text as self-originated to prevent feedback loops."""
        self._self_originated.add(text)
        if len(self._self_originated) > 10:
            self._self_originated = set(list(self._self_originated)[-10:])

    def start(self) -> None:
        """Start the clipboard monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Clipboard monitor started")

    def stop(self) -> None:
        """Stop the clipboard monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Clipboard monitor stopped")

    def _poll_loop(self) -> None:
        """Main polling loop for clipboard changes."""
        while self._running:
            if self._enabled:
                try:
                    self._check_clipboard()
                except Exception as e:
                    logger.debug(f"Clipboard poll error: {e}")
            time.sleep(self._poll_interval)

    def _check_clipboard(self) -> None:
        """Check clipboard for new content."""
        try:
            result = capture_and_validate()
            content = result.text
        except CaptureError:
            return

        if content == self._last_content:
            return
        self._last_content = content

        if content in self._self_originated:
            self._self_originated.discard(content)
            return

        if len(content) < self._min_length:
            return
        if len(content) > self._max_length:
            return

        if self._callback:
            self._callback(content)


# ─── Notification Manager ─────────────────────────────────────────────────────


class NotificationManager:
    """Cross-platform desktop notifications.

    Uses platform-appropriate notification mechanism:
    - Linux: notify-send
    - Windows: Windows toast notifications (via plyer or win10toast)
    - Fallback: print to stderr
    """

    NOTIFICATION_TIMEOUT_MS = 8000  # 8 seconds

    def __init__(self, app_name: str = "Auto-Correction Tool"):
        """Initialize the notification manager."""
        self._app_name = app_name
        self._last_report: Optional[dict] = None
        self._backend = self._detect_notification_backend()

    def _detect_notification_backend(self) -> str:
        """Detect the best notification backend for the current platform."""
        if sys.platform == "win32":
            # Try plyer first (cross-platform)
            try:
                from plyer import notification  # noqa: F401
                return "plyer"
            except ImportError:
                pass
            # Try win10toast
            try:
                from win10toast import ToastNotifier  # noqa: F401
                return "win10toast"
            except ImportError:
                pass
            # Try winotify
            try:
                from winotify import Notification  # noqa: F401
                return "winotify"
            except ImportError:
                pass
            # Fallback to console
            return "console"
        elif sys.platform == "darwin":
            return "osascript"
        else:
            # Linux - check for notify-send
            if shutil.which("notify-send"):
                return "notify-send"
            return "console"

    def notify_corrections_found(self, count: int, high_confidence: int = 0) -> None:
        """Show notification for corrections found."""
        if count == 0:
            self._send_notification(
                "No Corrections Needed",
                "Your text looks good! No corrections were found.",
            )
        else:
            body = f"Found {count} correction(s)."
            if high_confidence > 0:
                body += f" {high_confidence} high-confidence."
            body += "\nCorrected text is on your clipboard - paste it back."
            self._send_notification("Corrections Found", body)

    def notify_auto_applied(self, count: int) -> None:
        """Show notification for auto-applied corrections."""
        self._send_notification(
            "Corrections Applied",
            f"Auto-applied {count} high-confidence correction(s).\n"
            "Paste (Ctrl+V) to replace your text.",
        )

    def notify_error(self, message: str) -> None:
        """Show error notification."""
        self._send_notification("Error", message)

    def notify_processing(self) -> None:
        """Show processing notification."""
        self._send_notification("Processing", "Analyzing text...")

    def notify_info(self, title: str, message: str) -> None:
        """Show an informational notification."""
        self._send_notification(title, message)

    def _send_notification(self, title: str, body: str) -> None:
        """Send a desktop notification using the detected backend."""
        try:
            if self._backend == "notify-send":
                subprocess.run(
                    [
                        "notify-send",
                        "--app-name", self._app_name,
                        "--expire-time", str(self.NOTIFICATION_TIMEOUT_MS),
                        title,
                        body,
                    ],
                    capture_output=True,
                    timeout=5,
                )
            elif self._backend == "plyer":
                from plyer import notification
                notification.notify(
                    title=title,
                    message=body,
                    app_name=self._app_name,
                    timeout=self.NOTIFICATION_TIMEOUT_MS // 1000,
                )
            elif self._backend == "win10toast":
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(
                    title,
                    body,
                    duration=self.NOTIFICATION_TIMEOUT_MS // 1000,
                    threaded=True,
                )
            elif self._backend == "winotify":
                from winotify import Notification, audio
                toast = Notification(
                    app_id=self._app_name,
                    title=title,
                    msg=body,
                )
                toast.show()
            elif self._backend == "osascript":
                subprocess.run(
                    [
                        "osascript", "-e",
                        f'display notification "{body}" with title "{title}"',
                    ],
                    capture_output=True,
                    timeout=5,
                )
            else:
                # Console fallback
                print(f"[{self._app_name}] {title}: {body}", file=sys.stderr)
        except Exception as e:
            # Always fall back to console if notification fails
            logger.debug(f"Notification error ({self._backend}): {e}")
            print(f"[{self._app_name}] {title}: {body}", file=sys.stderr)


# ─── HTTP Client ──────────────────────────────────────────────────────────────


class APIClient:
    """HTTP client for communicating with the API Gateway."""

    def __init__(
        self,
        base_url: str = API_GATEWAY_URL,
        api_key: str = DEFAULT_API_KEY,
    ):
        """Initialize the API client."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def analyze_text(self, text: str, language: Optional[str] = None) -> Optional[dict]:
        """Send text for analysis."""
        try:
            with httpx.Client(timeout=300.0) as client:
                response = client.post(
                    f"{self.base_url}/api/v1/correct",
                    json={"text": text, "language": language},
                    headers={"X-API-Key": self.api_key},
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(
                        f"API request failed: {response.status_code} - {response.text}"
                    )
                    return None
        except httpx.TimeoutException:
            logger.error("API request timed out")
            return None
        except httpx.ConnectError:
            logger.error("Cannot connect to API Gateway")
            return None
        except Exception as e:
            logger.error(f"API request error: {e}")
            return None

    def check_health(self) -> bool:
        """Check if the API Gateway is healthy."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/v1/health")
                return response.status_code == 200
        except Exception:
            return False


# ─── System Tray Application ──────────────────────────────────────────────────


class SystemTrayApp:
    """Main system tray application.

    Coordinates all components: tray icon, hotkeys, clipboard monitor,
    notifications, and API communication. Works cross-platform.
    """

    def __init__(
        self,
        api_url: str = API_GATEWAY_URL,
        api_key: str = DEFAULT_API_KEY,
        analyze_hotkey: str = "ctrl+alt+c",
        review_hotkey: str = "ctrl+alt+v",
        clipboard_monitoring: bool = False,
    ):
        """Initialize the system tray application."""
        self._status = AppStatus.IDLE
        self._api_client = APIClient(base_url=api_url, api_key=api_key)
        self._notification_manager = NotificationManager()
        self._hotkey_manager = HotkeyManager()
        self._clipboard_monitor = ClipboardMonitor(
            on_text_captured=self._on_clipboard_text,
        )
        self._tray_icon = None
        self._last_report: Optional[dict] = None

        # Register hotkeys
        self._hotkey_manager.register(
            analyze_hotkey, "analyze", self._on_analyze_hotkey
        )
        self._hotkey_manager.register(
            review_hotkey, "review", self._on_review_hotkey
        )

        # Enable clipboard monitoring if configured
        if clipboard_monitoring:
            self._clipboard_monitor.enable()

    @property
    def status(self) -> AppStatus:
        """Current application status."""
        return self._status

    def run(self) -> None:
        """Start the system tray application."""
        # Start hotkey listener
        self._hotkey_manager.start()

        # Check if hotkeys are available and notify user
        if not self._hotkey_manager.hotkeys_available:
            self._update_status(AppStatus.ERROR)
            self._notification_manager.notify_error(
                "Hotkeys are not available. Install pynput: pip install pynput"
            )

        # Start clipboard monitor
        self._clipboard_monitor.start()

        try:
            import pystray
            from PIL import Image

            icon_image = self._create_icon_image(self._status)

            menu = pystray.Menu(
                pystray.MenuItem("Run Correction", self._tray_run_correction),
                pystray.MenuItem("Open History", self._tray_open_history),
                pystray.MenuItem("Settings", self._tray_open_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._tray_quit),
            )

            self._tray_icon = pystray.Icon(
                "autocorrect",
                icon_image,
                "Auto-Correction Tool",
                menu,
            )

            # Show startup notification
            if self._hotkey_manager.hotkeys_available:
                self._notification_manager.notify_info(
                    "Auto-Correction Tool Ready",
                    "Hotkeys active:\n"
                    "• Ctrl+Alt+C (auto-correct)\n"
                    "• Ctrl+Alt+V (review before applying)"
                )

            logger.info("System tray application started")

            # Use setup callback to start background work after icon is ready
            def on_setup(icon):
                """Called once the tray icon is visible and ready."""
                icon.visible = True

            # Run the tray icon (blocks main thread - this is required on Windows)
            self._tray_icon.run(setup=on_setup)

        except ImportError:
            logger.warning(
                "pystray or PIL not available. Running in headless mode."
            )
            self._run_headless()

    def _run_headless(self) -> None:
        """Run without system tray (hotkeys and clipboard only)."""
        if self._hotkey_manager.hotkeys_available:
            self._notification_manager.notify_info(
                "Auto-Correction Tool Ready (Headless)",
                "Hotkeys active:\n"
                "• Ctrl+Alt+C (auto-correct)\n"
                "• Ctrl+Alt+V (review before applying)"
            )

        logger.info("Running in headless mode (no system tray)")
        print(
            "Auto-Correction Tool running. "
            "Press Ctrl+Alt+C to correct, "
            "Ctrl+Alt+V to review. Press Ctrl+C to quit.",
            file=sys.stderr,
        )
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop the application and cleanup."""
        logger.info("Stopping system tray application...")
        self._hotkey_manager.stop()
        self._clipboard_monitor.stop()
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception as e:
                logger.debug(f"Error stopping tray icon: {e}")
        logger.info("System tray application stopped")

    def _create_icon_image(self, status: AppStatus):
        """Create a tray icon image based on status.

        Loads the custom logo from assets/tray_icon.png if available,
        otherwise falls back to a generated colored circle.
        Resizes to 64x64 for the system tray.
        Works both in development and when bundled with PyInstaller.
        """
        import os
        from PIL import Image, ImageDraw

        size = 64

        # Determine base path (handles PyInstaller bundled exe)
        if getattr(sys, 'frozen', False):
            # Running as bundled exe
            base_dir = os.path.dirname(sys.executable)
        else:
            # Running from source
            base_dir = os.path.dirname(os.path.dirname(__file__))

        # Try to load custom logo from multiple locations
        search_paths = [
            os.path.join(base_dir, "assets", "tray_icon.png"),
            os.path.join(base_dir, "assets", "tray_icon.ico"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "tray_icon.png"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "tray_icon.ico"),
        ]

        # Also check PyInstaller's _MEIPASS temp directory
        if hasattr(sys, '_MEIPASS'):
            search_paths.insert(0, os.path.join(sys._MEIPASS, "assets", "tray_icon.png"))
            search_paths.insert(1, os.path.join(sys._MEIPASS, "assets", "tray_icon.ico"))

        logo_path = None
        for path in search_paths:
            if os.path.exists(path):
                logo_path = path
                break

        if os.path.exists(logo_path):
            try:
                image = Image.open(logo_path)
                # Convert to RGBA if needed
                image = image.convert("RGBA")
                # Resize to fit tray icon (maintain aspect ratio, fit in square)
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                # Create a square canvas and paste centered
                canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                x_offset = (size - image.width) // 2
                y_offset = (size - image.height) // 2
                canvas.paste(image, (x_offset, y_offset), image)
                return canvas
            except Exception as e:
                logger.debug(f"Failed to load custom icon: {e}")

        # Fallback: generate a colored circle
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        colors = {
            AppStatus.IDLE: (76, 175, 80, 255),       # Green
            AppStatus.PROCESSING: (255, 193, 7, 255), # Amber
            AppStatus.ERROR: (244, 67, 54, 255),      # Red
        }

        color = colors.get(status, colors[AppStatus.IDLE])
        draw.ellipse([4, 4, size - 4, size - 4], fill=color)
        draw.text((20, 16), "A", fill=(255, 255, 255, 255))

        return image

    def _update_status(self, status: AppStatus) -> None:
        """Update the application status and tray icon."""
        self._status = status
        if self._tray_icon:
            try:
                self._tray_icon.icon = self._create_icon_image(status)
            except Exception:
                pass

    # ─── Tray Menu Handlers ───────────────────────────────────────────────
    # pystray on Windows calls these with (icon, item) signature.
    # They must be simple and not block.

    def _tray_run_correction(self, icon, item):
        """Handle 'Run Correction' menu click."""
        threading.Thread(
            target=self._run_correction, kwargs={"auto_apply": False}, daemon=True
        ).start()

    def _tray_open_history(self, icon, item):
        """Handle 'Open History' menu click."""
        logger.info("Open History requested")
        threading.Thread(target=self._show_history_window, daemon=True).start()

    def _show_history_window(self) -> None:
        """Open the history window."""
        try:
            if getattr(sys, 'frozen', False):
                # Running as .exe — run tkinter in this thread directly
                from .history_window import show_history
                show_history()
            else:
                # Running from source — use subprocess to avoid tkinter thread issues
                import os
                import subprocess as sp
                project_root = os.path.dirname(os.path.dirname(__file__))
                sp.Popen(
                    [sys.executable, "-c",
                     "from app.history_window import show_history; show_history()"],
                    cwd=project_root,
                )
        except Exception as e:
            logger.error(f"History window error: {e}")
            self._notification_manager.notify_error(f"Cannot open history: {e}")

    def _tray_open_settings(self, icon, item):
        """Handle 'Settings' menu click — opens the settings GUI."""
        logger.info("Settings requested")
        threading.Thread(target=self._show_settings_window, daemon=True).start()

    def _show_settings_window(self) -> None:
        """Open the settings window."""
        try:
            if getattr(sys, 'frozen', False):
                # Running as .exe — run tkinter in this thread directly
                from .settings_window import show_settings
                show_settings()
            else:
                # Running from source — use subprocess to avoid tkinter thread issues
                import os
                import subprocess as sp
                project_root = os.path.dirname(os.path.dirname(__file__))
                sp.Popen(
                    [sys.executable, "-c",
                     "from app.settings_window import show_settings; show_settings()"],
                    cwd=project_root,
                )
        except Exception as e:
            logger.error(f"Settings window error: {e}")
            self._notification_manager.notify_error(f"Cannot open settings: {e}")

    def _tray_quit(self, icon, item):
        """Handle 'Quit' menu click."""
        self.stop()

    # ─── Hotkey Event Handlers ────────────────────────────────────────────

    def _on_analyze_hotkey(self) -> None:
        """Handle analyze hotkey press."""
        self._run_correction(auto_apply=False)

    def _on_clipboard_text(self, text: str) -> None:
        """Handle new clipboard text detected."""
        self._run_correction(auto_apply=False, text=text)

    def _on_review_hotkey(self) -> None:
        """Handle review hotkey press (Ctrl+Alt+V) — correction with review popup."""
        self._run_correction(auto_apply=False, with_review=True)

    def _simulate_copy(self) -> None:
        """Simulate Ctrl+C to copy the current selection to clipboard.

        Uses pynput keyboard controller to send the keystroke to the
        active application (Word, Notepad, OpenOffice, etc.).
        Includes longer delays for apps like OpenOffice that are slower
        to respond to copy commands.
        """
        try:
            from pynput.keyboard import Key, Controller

            kb = Controller()
            # Release ALL modifier keys that might be held from the hotkey
            for key in (Key.ctrl_l, Key.ctrl_r, Key.alt_l, Key.alt_r, Key.shift_l, Key.shift_r):
                try:
                    kb.release(key)
                except Exception:
                    pass
            # Wait for keys to fully release
            time.sleep(0.3)
            # Send Ctrl+C
            with kb.pressed(Key.ctrl_l):
                kb.tap('c')
            # Wait for clipboard to update (longer for apps like OpenOffice)
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"Simulate copy failed: {e}")

    @staticmethod
    def _split_into_chunks(text: str, max_chunk_size: int = 1500) -> list[str]:
        """Split text into chunks on sentence boundaries.

        If text is <= 2000 chars, returns it as-is in a single-element list.
        Otherwise splits on sentence-ending punctuation (. ! ? newline) into
        chunks of approximately max_chunk_size characters.
        """
        if len(text) <= 2000:
            return [text]

        chunks = []
        current_chunk = ""

        # Split on sentence boundaries: periods, exclamation, question marks, newlines
        import re
        sentences = re.split(r'(?<=[.!?\n])\s+', text)

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 > max_chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk = current_chunk + " " + sentence if current_chunk else sentence

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text]

    def _call_llm(self, text: str, api_key: str, base_url: str, model: str) -> Optional[dict]:
        """Make a single LLM API call for text correction.

        Args:
            text: The text chunk to analyze.
            api_key: The API key.
            base_url: The API base URL.
            model: The model name.

        Returns:
            Dict with "corrections" list, or None on failure.
        """
        import json as json_mod

        prompt = (
            "You are a precise text correction assistant. "
            "Find all spelling, grammar, and punctuation errors. "
            "Return a JSON object with a \"corrections\" array. "
            "Each correction: {\"original_text\": \"...\", \"suggested_text\": \"...\", "
            "\"correction_type\": \"spelling|grammar|punctuation\", "
            "\"reason\": \"...\", \"confidence\": 0.9, "
            "\"start_offset\": 0, \"end_offset\": 5}. "
            "If no errors, return {\"corrections\": []}.\n\n"
            f"Text to correct:\n\"{text}\""
        )

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = json_mod.loads(content)
            corrections = parsed.get("corrections", [])
            return {"corrections": corrections}
        else:
            logger.error(f"LLM request failed: {response.status_code} - {response.text}")
            return None

    def _analyze_text(self, text: str) -> Optional[dict]:
        """Analyze text using Groq directly (if configured) or the local API.

        Features:
        - Text chunking: splits text >2000 chars into ~1500 char chunks
        - Gemini fallback: retries with Gemini if Groq fails
        - Falls back to the local API gateway if cloud is not configured
        """
        import os

        # Load config
        env_file = _load_env_file()
        backend = os.environ.get("LLM_BACKEND", env_file.get("LLM_BACKEND", "ollama"))

        if backend == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", env_file.get("OPENAI_API_KEY", ""))
            base_url = os.environ.get("OPENAI_BASE_URL", env_file.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"))
            model = os.environ.get("OPENAI_MODEL", env_file.get("OPENAI_MODEL", "llama-3.3-70b-versatile"))

            if not api_key:
                return self._api_client.analyze_text(text)

            # Split into chunks if text is long
            chunks = self._split_into_chunks(text)
            all_corrections = []

            for chunk in chunks:
                # Try primary backend (Groq)
                try:
                    result = self._call_llm(chunk, api_key, base_url, model)
                    if result is not None:
                        all_corrections.extend(result.get("corrections", []))
                        continue
                except Exception as e:
                    logger.warning(f"Groq call failed for chunk: {e}")

                # Fallback to Gemini
                gemini_key = os.environ.get("GEMINI_API_KEY", env_file.get("GEMINI_API_KEY", ""))
                if gemini_key:
                    logger.info("Falling back to Gemini...")
                    try:
                        gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai"
                        gemini_model = "gemini-2.0-flash-lite"
                        result = self._call_llm(chunk, gemini_key, gemini_url, gemini_model)
                        if result is not None:
                            all_corrections.extend(result.get("corrections", []))
                            continue
                    except Exception as e2:
                        logger.error(f"Gemini fallback also failed: {e2}")

                # Both failed for this chunk
                logger.error("All LLM backends failed for chunk")

            return {"corrections": all_corrections}

        elif backend == "gemini":
            # Direct Gemini usage
            gemini_key = os.environ.get("GEMINI_API_KEY", env_file.get("GEMINI_API_KEY", ""))
            if not gemini_key:
                return self._api_client.analyze_text(text)

            gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            gemini_model = "gemini-2.0-flash-lite"

            chunks = self._split_into_chunks(text)
            all_corrections = []

            for chunk in chunks:
                try:
                    result = self._call_llm(chunk, gemini_key, gemini_url, gemini_model)
                    if result is not None:
                        all_corrections.extend(result.get("corrections", []))
                except Exception as e:
                    logger.error(f"Gemini call failed for chunk: {e}")

            return {"corrections": all_corrections}

        else:
            # Use local API gateway (ollama or other)
            return self._api_client.analyze_text(text)

    def _run_correction(
        self, auto_apply: bool = False, text: Optional[str] = None,
        with_review: bool = False,
    ) -> None:
        """Run the correction flow.

        Args:
            auto_apply: Whether to auto-apply corrections (legacy, kept for compatibility).
            text: Text to correct. If None, copies current selection.
            with_review: If True, shows the review window before applying.
        """
        self._update_status(AppStatus.PROCESSING)

        try:
            # Get text from clipboard if not provided
            if text is None:
                # Simulate Ctrl+C to copy the current selection to clipboard
                self._simulate_copy()
                # Small delay to let the clipboard update
                time.sleep(0.15)

                try:
                    result = capture_and_validate()
                    text = result.text
                except CaptureError as e:
                    self._notification_manager.notify_error(
                        f"Cannot read clipboard: {e}\n"
                        "Make sure you have text selected."
                    )
                    self._update_status(AppStatus.ERROR)
                    return

            # Send to API — use direct Groq if configured, otherwise local API
            self._notification_manager.notify_processing()
            report = self._analyze_text(text)

            if report is None:
                self._notification_manager.notify_error(
                    "Failed to analyze text. Is the service running?\n"
                    "Start with: podman-compose up -d"
                )
                self._update_status(AppStatus.ERROR)
                return

            self._last_report = report
            corrections = report.get("corrections", [])

            if not corrections:
                self._notification_manager.notify_corrections_found(0)
                self._update_status(AppStatus.IDLE)
                return

            # Apply ALL corrections that have actual changes
            # (filter out corrections where original == suggested)
            applicable = [
                c for c in corrections
                if c.get("original_text", "") != c.get("suggested_text", "")
                and c.get("original_text", "")
                and c.get("suggested_text", "")
            ]

            if not applicable:
                self._notification_manager.notify_corrections_found(0)
                self._update_status(AppStatus.IDLE)
                return

            # If review mode, show the review window
            if with_review:
                try:
                    from .review_window import show_review
                    selected = show_review(text, applicable)
                    if selected is None:
                        # User cancelled
                        self._notification_manager.notify_info(
                            "Cancelled", "Correction review cancelled."
                        )
                        self._update_status(AppStatus.IDLE)
                        return
                    applicable = selected
                except Exception as e:
                    logger.error(f"Review window error: {e}")
                    # Fall through to auto-apply if review fails

            if not applicable:
                self._notification_manager.notify_info(
                    "No Corrections", "No corrections were selected."
                )
                self._update_status(AppStatus.IDLE)
                return

            # Build corrected text using find-and-replace (more reliable than offsets)
            # LLM offsets are often wrong, so we search for the original text instead
            corrected = text
            applied_count = 0
            applied_details = []
            for c in applicable:
                original = c.get("original_text", "")
                suggested = c.get("suggested_text", "")
                if original in corrected:
                    corrected = corrected.replace(original, suggested, 1)
                    applied_count += 1
                    applied_details.append((original, suggested))

            # Put corrected text on clipboard
            self._clipboard_monitor.mark_self_originated(corrected)
            write_clipboard(corrected)

            # Better notification: show what was corrected
            self._notify_corrections_detailed(applied_count, applied_details)

            # Save to history
            try:
                from .history import save_correction
                save_correction(
                    original_text=text,
                    corrected_text=corrected,
                    corrections=applicable,
                )
            except Exception as e:
                logger.debug(f"Failed to save to history: {e}")

            self._update_status(AppStatus.IDLE)

        except Exception as e:
            logger.error(f"Correction flow error: {e}")
            self._notification_manager.notify_error(f"Error: {e}")
            self._update_status(AppStatus.ERROR)

    def _notify_corrections_detailed(
        self, count: int, details: list[tuple[str, str]]
    ) -> None:
        """Show a detailed notification of corrections applied.

        Shows the first 3 corrections as bullet points.
        """
        if count == 0:
            self._notification_manager.notify_corrections_found(0)
            return

        lines = [f"Applied {count} correction(s):"]
        for original, suggested in details[:3]:
            # Truncate long strings for notification
            orig_short = original[:30] + "..." if len(original) > 30 else original
            sugg_short = suggested[:30] + "..." if len(suggested) > 30 else suggested
            lines.append(f"\u2022 {orig_short} \u2192 {sugg_short}")

        if count > 3:
            lines.append(f"  ...and {count - 3} more")

        lines.append("\nPaste (Ctrl+V) to replace your text.")
        body = "\n".join(lines)
        self._notification_manager._send_notification("Corrections Applied", body)


# ─── Entry Point ──────────────────────────────────────────────────────────────


def _load_env_file() -> dict[str, str]:
    """Load environment variables from .env file.

    Searches in multiple locations to work both in development
    and when bundled as a PyInstaller .exe.
    """
    import os
    env_vars = {}

    # Search locations in priority order
    search_paths = []

    # 1. Next to the .exe (for bundled distribution)
    if getattr(sys, 'frozen', False):
        search_paths.append(os.path.join(os.path.dirname(sys.executable), ".env"))

    # 2. Project root (parent of app/)
    search_paths.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

    # 3. Current working directory
    search_paths.append(os.path.join(os.getcwd(), ".env"))

    # 4. PyInstaller temp directory
    if hasattr(sys, '_MEIPASS'):
        search_paths.append(os.path.join(sys._MEIPASS, ".env"))

    env_path = None
    for path in search_paths:
        if os.path.exists(path):
            env_path = path
            break

    if env_path:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    return env_vars


def main():
    """Main entry point for the system tray application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import os

    # Load .env file so API_KEY and other settings are picked up automatically
    env_file = _load_env_file()

    def get_config(key: str, default: str) -> str:
        """Get config from environment variable, then .env file, then default."""
        return os.environ.get(key, env_file.get(key, default))

    api_port = get_config("API_PORT", "8080")
    api_url = get_config("API_URL", f"http://localhost:{api_port}")

    app = SystemTrayApp(
        api_url=api_url,
        api_key=get_config("API_KEY", DEFAULT_API_KEY),
        analyze_hotkey=get_config("HOTKEY_ANALYZE", "ctrl+alt+c"),
        review_hotkey=get_config("HOTKEY_REVIEW", "ctrl+alt+v"),
        clipboard_monitoring=get_config("CLIPBOARD_MONITORING", "false").lower()
        == "true",
    )

    try:
        app.run()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
