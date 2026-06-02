"""Settings Window Module - Tkinter GUI for configuring the application.

Provides a settings dialog opened from the system tray menu.
Loads current values from .env and saves changes back to .env.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional


def _find_env_path() -> str:
    """Find the .env file path."""
    # Project root is parent of app/
    project_root = os.path.dirname(os.path.dirname(__file__))
    env_path = os.path.join(project_root, ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.getcwd(), ".env")
    return env_path


def _load_env(env_path: Optional[str] = None) -> dict[str, str]:
    """Load environment variables from .env file."""
    path = env_path or _find_env_path()
    env_vars = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    return env_vars


def _save_env(env_vars: dict[str, str], env_path: Optional[str] = None) -> None:
    """Save environment variables back to .env file.

    Preserves comments and structure, updates existing keys, appends new ones.
    """
    path = env_path or _find_env_path()

    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    # Track which keys we've written
    written_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in env_vars:
                new_lines.append(f"{key}={env_vars[key]}\n")
                written_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Append any new keys that weren't in the original file
    for key, value in env_vars.items():
        if key not in written_keys:
            new_lines.append(f"{key}={value}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


class SettingsWindow:
    """Tkinter settings window for configuring the auto-correction tool."""

    BACKENDS = ["openai", "gemini", "ollama"]

    def __init__(self):
        """Initialize the settings window."""
        self._window: Optional[tk.Tk] = None
        self._env_vars: dict[str, str] = {}

    def show(self) -> None:
        """Show the settings window."""
        self._env_vars = _load_env()

        self._window = tk.Tk()
        self._window.title("Auto-Correction Settings")
        self._window.geometry("550x450")
        self._window.configure(bg="#f5f5f5")
        self._window.attributes("-topmost", True)

        self._build_ui()

        # Center on screen
        self._window.update_idletasks()
        x = (self._window.winfo_screenwidth() // 2) - (550 // 2)
        y = (self._window.winfo_screenheight() // 2) - (450 // 2)
        self._window.geometry(f"+{x}+{y}")

        self._window.mainloop()

    def _build_ui(self) -> None:
        """Build the settings UI."""
        window = self._window

        # Title
        tk.Label(
            window,
            text="Settings",
            font=("Segoe UI", 14, "bold"),
            bg="#f5f5f5",
        ).pack(pady=(15, 10))

        # Main frame
        main_frame = tk.Frame(window, bg="#f5f5f5")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        row = 0

        # LLM Backend
        tk.Label(
            main_frame, text="LLM Backend:", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._backend_var = tk.StringVar(
            value=self._env_vars.get("LLM_BACKEND", "openai")
        )
        backend_combo = ttk.Combobox(
            main_frame,
            textvariable=self._backend_var,
            values=self.BACKENDS,
            state="readonly",
            width=30,
        )
        backend_combo.grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        # Groq/OpenAI API Key
        tk.Label(
            main_frame, text="Groq API Key:", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._openai_key_var = tk.StringVar(
            value=self._env_vars.get("OPENAI_API_KEY", "")
        )
        tk.Entry(
            main_frame, textvariable=self._openai_key_var, width=35, show="*"
        ).grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        # OpenAI Base URL
        tk.Label(
            main_frame, text="Base URL:", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._base_url_var = tk.StringVar(
            value=self._env_vars.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
        )
        tk.Entry(
            main_frame, textvariable=self._base_url_var, width=35
        ).grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        # Model
        tk.Label(
            main_frame, text="Model:", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._model_var = tk.StringVar(
            value=self._env_vars.get("OPENAI_MODEL", "llama-3.3-70b-versatile")
        )
        tk.Entry(
            main_frame, textvariable=self._model_var, width=35
        ).grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        # Gemini API Key
        tk.Label(
            main_frame, text="Gemini API Key:", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._gemini_key_var = tk.StringVar(
            value=self._env_vars.get("GEMINI_API_KEY", "")
        )
        tk.Entry(
            main_frame, textvariable=self._gemini_key_var, width=35, show="*"
        ).grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        # Hotkeys section
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=10
        )
        row += 1

        tk.Label(
            main_frame, text="Hotkey (Analyze):", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._hotkey_analyze_var = tk.StringVar(
            value=self._env_vars.get("HOTKEY_ANALYZE", "ctrl+alt+c")
        )
        tk.Entry(
            main_frame, textvariable=self._hotkey_analyze_var, width=35
        ).grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        tk.Label(
            main_frame, text="Hotkey (Apply):", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._hotkey_apply_var = tk.StringVar(
            value=self._env_vars.get("HOTKEY_APPLY", "ctrl+alt+a")
        )
        tk.Entry(
            main_frame, textvariable=self._hotkey_apply_var, width=35
        ).grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        tk.Label(
            main_frame, text="Hotkey (Review):", bg="#f5f5f5", font=("Segoe UI", 10)
        ).grid(row=row, column=0, sticky="w", pady=5)

        self._hotkey_review_var = tk.StringVar(
            value=self._env_vars.get("HOTKEY_REVIEW", "ctrl+alt+r")
        )
        tk.Entry(
            main_frame, textvariable=self._hotkey_review_var, width=35
        ).grid(row=row, column=1, sticky="w", pady=5, padx=(10, 0))
        row += 1

        # Buttons
        btn_frame = tk.Frame(window, bg="#f5f5f5")
        btn_frame.pack(fill=tk.X, padx=20, pady=15)

        tk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
            width=10,
            bg="#e0e0e0",
        ).pack(side=tk.RIGHT, padx=(5, 0))

        tk.Button(
            btn_frame,
            text="Save",
            command=self._on_save,
            width=10,
            bg="#c8e6c9",
        ).pack(side=tk.RIGHT, padx=(5, 0))

    def _on_save(self) -> None:
        """Save settings to .env file."""
        updates = {
            "LLM_BACKEND": self._backend_var.get(),
            "OPENAI_API_KEY": self._openai_key_var.get(),
            "OPENAI_BASE_URL": self._base_url_var.get(),
            "OPENAI_MODEL": self._model_var.get(),
            "HOTKEY_ANALYZE": self._hotkey_analyze_var.get(),
            "HOTKEY_APPLY": self._hotkey_apply_var.get(),
            "HOTKEY_REVIEW": self._hotkey_review_var.get(),
        }

        # Only save Gemini key if provided
        gemini_key = self._gemini_key_var.get()
        if gemini_key:
            updates["GEMINI_API_KEY"] = gemini_key

        try:
            _save_env(updates)
            messagebox.showinfo(
                "Settings Saved",
                "Settings saved successfully.\nRestart the app for changes to take effect.",
            )
            self._window.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def _on_cancel(self) -> None:
        """Cancel without saving."""
        self._window.destroy()


def show_settings() -> None:
    """Show the settings window. Convenience function."""
    window = SettingsWindow()
    window.show()
