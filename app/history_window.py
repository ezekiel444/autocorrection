"""History Window Module - Dashboard for viewing past corrections.

Provides a dark-themed tkinter window showing correction history
from the SQLite database with expandable detail rows.
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from .theme import COLORS, FONTS, DEVELOPER



class HistoryWindow:
    """Dark-themed history dashboard window."""

    def __init__(self):
        self._window: Optional[tk.Tk] = None
        self._records: list[dict] = []
        self._detail_frame: Optional[tk.Frame] = None

    def show(self) -> None:
        """Show the history window."""
        self._window = tk.Tk()
        self._window.title("Correction History")
        self._window.geometry("750x550")
        self._window.configure(bg=COLORS["bg"])
        self._window.attributes("-topmost", True)

        try:
            self._window.iconbitmap(default="")
        except Exception:
            pass

        self._load_records()
        self._build_ui()

        # Center on screen
        self._window.update_idletasks()
        x = (self._window.winfo_screenwidth() // 2) - (750 // 2)
        y = (self._window.winfo_screenheight() // 2) - (550 // 2)
        self._window.geometry(f"+{x}+{y}")

        self._window.mainloop()

    def _load_records(self) -> None:
        """Load correction history from the database."""
        try:
            from .history import get_history
            self._records = get_history(limit=100)
        except Exception:
            self._records = []

    def _build_ui(self) -> None:
        """Build the history dashboard UI."""
        window = self._window

        # ─── Header ──────────────────────────────────────────────────────
        header = tk.Frame(window, bg=COLORS["bg"], pady=16, padx=24)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Correction History",
            font=("Segoe UI", 16, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(side=tk.LEFT)

        count_text = f"{len(self._records)} record(s)"
        tk.Label(
            header,
            text=count_text,
            font=("Segoe UI", 11),
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
        ).pack(side=tk.RIGHT)

        # ─── Divider ─────────────────────────────────────────────────────
        tk.Frame(window, bg=COLORS["border"], height=1).pack(fill=tk.X)

        # ─── Main content area ───────────────────────────────────────────
        content = tk.Frame(window, bg=COLORS["bg"])
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        if not self._records:
            tk.Label(
                content,
                text="No correction history yet.",
                font=("Segoe UI", 12),
                bg=COLORS["bg"],
                fg=COLORS["text_dim"],
            ).pack(expand=True)
        else:
            self._build_list(content)

        # ─── Divider ─────────────────────────────────────────────────────
        tk.Frame(window, bg=COLORS["border"], height=1).pack(fill=tk.X)

        # ─── Footer buttons ──────────────────────────────────────────────
        footer = tk.Frame(window, bg=COLORS["bg"], pady=12, padx=24)
        footer.pack(fill=tk.X)

        clear_btn = tk.Button(
            footer,
            text="Clear History",
            font=("Segoe UI", 10),
            bg=COLORS["error"],
            fg="#ffffff",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16, pady=6,
            cursor="hand2",
            command=self._on_clear,
        )
        clear_btn.pack(side=tk.LEFT)

        close_btn = tk.Button(
            footer,
            text="Close",
            font=("Segoe UI", 10),
            bg=COLORS["btn_cancel"],
            fg=COLORS["text"],
            activebackground="#6b7280",
            activeforeground=COLORS["text"],
            relief=tk.FLAT,
            padx=16, pady=6,
            cursor="hand2",
            command=self._on_close,
        )
        close_btn.pack(side=tk.RIGHT)

        # ─── Developer credit ────────────────────────────────────────────
        credit = tk.Label(
            window,
            text="Ezekiel Matomi Lucky",
            font=("Segoe UI", 8),
            bg=COLORS["bg"],
            fg="#6b7280",
        )
        credit.pack(side=tk.BOTTOM, pady=(0, 6))

    def _build_list(self, parent: tk.Frame) -> None:
        """Build the scrollable list of correction records."""
        canvas = tk.Canvas(
            parent, bg=COLORS["bg"],
            highlightthickness=0, bd=0,
        )
        scrollbar = ttk.Scrollbar(
            parent, orient=tk.VERTICAL, command=canvas.yview
        )

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Vertical.TScrollbar",
            background=COLORS["surface"],
            troughcolor=COLORS["bg"],
            arrowcolor=COLORS["text_dim"],
        )

        scroll_frame = tk.Frame(canvas, bg=COLORS["bg"])
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=690)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Build rows
        for record in self._records:
            self._build_row(scroll_frame, record)

    def _build_row(self, parent: tk.Frame, record: dict) -> None:
        """Build a single clickable row for a correction record."""
        # Format timestamp
        ts_raw = record.get("timestamp", "")
        ts_display = ts_raw[:16].replace("T", " ") if ts_raw else "Unknown"

        # Preview of original text
        original = record.get("original_text", "")
        preview = original[:60] + ("..." if len(original) > 60 else "")

        # Number of corrections
        corrections = record.get("corrections", [])
        n_corrections = len(corrections)

        # Card frame
        card = tk.Frame(
            parent, bg=COLORS["surface"],
            padx=14, pady=10, relief=tk.FLAT,
        )
        card.pack(fill=tk.X, pady=3)

        # Row content
        row = tk.Frame(card, bg=COLORS["surface"])
        row.pack(fill=tk.X)

        # Timestamp
        tk.Label(
            row,
            text=ts_display,
            font=("Consolas", 9),
            bg=COLORS["surface"],
            fg=COLORS["accent"],
        ).pack(side=tk.LEFT, padx=(0, 12))

        # Corrections count badge
        tk.Label(
            row,
            text=f"{n_corrections} fix(es)",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["success"],
            padx=6, pady=1,
        ).pack(side=tk.LEFT, padx=(0, 12))

        # Text preview
        tk.Label(
            row,
            text=preview,
            font=("Segoe UI", 9),
            bg=COLORS["surface"],
            fg=COLORS["text"],
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Detail frame (hidden by default)
        detail = tk.Frame(card, bg=COLORS["bg"], padx=10, pady=8)
        detail._visible = False

        # Make the card clickable
        def toggle_detail(event=None, d=detail, r=record):
            if d._visible:
                d.pack_forget()
                d._visible = False
            else:
                self._populate_detail(d, r)
                d.pack(fill=tk.X, pady=(8, 0))
                d._visible = True

        # Bind click on the card and row
        card.bind("<Button-1>", toggle_detail)
        row.bind("<Button-1>", toggle_detail)
        for child in row.winfo_children():
            child.bind("<Button-1>", toggle_detail)

    def _populate_detail(self, frame: tk.Frame, record: dict) -> None:
        """Populate detail frame with original and corrected text."""
        # Clear previous content
        for widget in frame.winfo_children():
            widget.destroy()

        original = record.get("original_text", "")
        corrected = record.get("corrected_text", "")

        # Original text section
        tk.Label(
            frame,
            text="Original:",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["error"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 2))

        orig_text = tk.Text(
            frame, height=3, wrap=tk.WORD,
            bg=COLORS["surface"], fg=COLORS["text"],
            font=("Consolas", 9),
            relief=tk.FLAT, bd=0,
            highlightthickness=1,
            highlightcolor=COLORS["border"],
            highlightbackground=COLORS["border"],
        )
        orig_text.insert("1.0", original)
        orig_text.configure(state=tk.DISABLED)
        orig_text.pack(fill=tk.X, pady=(0, 6))

        # Corrected text section
        tk.Label(
            frame,
            text="Corrected:",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["success"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 2))

        corr_text = tk.Text(
            frame, height=3, wrap=tk.WORD,
            bg=COLORS["surface"], fg=COLORS["text"],
            font=("Consolas", 9),
            relief=tk.FLAT, bd=0,
            highlightthickness=1,
            highlightcolor=COLORS["border"],
            highlightbackground=COLORS["border"],
        )
        corr_text.insert("1.0", corrected)
        corr_text.configure(state=tk.DISABLED)
        corr_text.pack(fill=tk.X)

    def _on_clear(self) -> None:
        """Clear all history after confirmation."""
        confirm = messagebox.askyesno(
            "Clear History",
            "Are you sure you want to delete all correction history?",
            parent=self._window,
        )
        if confirm:
            try:
                from .history import clear_history
                deleted = clear_history()
                self._records = []
                # Rebuild the window
                for widget in self._window.winfo_children():
                    widget.destroy()
                self._build_ui()
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to clear history: {e}",
                    parent=self._window,
                )

    def _on_close(self) -> None:
        """Close the history window."""
        self._window.destroy()


def show_history() -> None:
    """Show the history window. Convenience function."""
    window = HistoryWindow()
    window.show()
