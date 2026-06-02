"""Review Window Module - Modern popup for reviewing corrections before applying.

A clean, minimal design showing corrections with red/green highlighting.
Users can select/deselect individual corrections before applying.
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
from typing import Optional


# ─── Color Palette ────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#1e1e2e",           # Dark background
    "surface": "#2a2a3c",      # Card/panel background
    "surface_hover": "#33334a", # Hover state
    "text": "#e4e4e7",         # Primary text
    "text_dim": "#9ca3af",     # Secondary text
    "accent": "#8b5cf6",       # Purple accent
    "success": "#34d399",      # Green for corrections
    "error": "#f87171",        # Red for original errors
    "border": "#3f3f5a",       # Subtle border
    "btn_primary": "#7c3aed",  # Button purple
    "btn_hover": "#6d28d9",    # Button hover
    "btn_cancel": "#4b5563",   # Cancel button
}


class ReviewWindow:
    """Modern review window for corrections."""

    def __init__(self, original_text: str, corrections: list[dict]):
        self._original_text = original_text
        self._corrections = corrections
        self._selected: list[tk.BooleanVar] = []
        self._result: Optional[list[dict]] = None
        self._window: Optional[tk.Tk] = None

    def show(self) -> Optional[list[dict]]:
        """Show the review window and block until user acts."""
        self._window = tk.Tk()
        self._window.title("Review Corrections")
        self._window.geometry("680x520")
        self._window.configure(bg=COLORS["bg"])
        self._window.attributes("-topmost", True)
        self._window.overrideredirect(False)

        # Remove default window icon padding
        try:
            self._window.iconbitmap(default="")
        except Exception:
            pass

        self._build_ui()

        # Center on screen
        self._window.update_idletasks()
        x = (self._window.winfo_screenwidth() // 2) - (680 // 2)
        y = (self._window.winfo_screenheight() // 2) - (520 // 2)
        self._window.geometry(f"+{x}+{y}")

        self._window.mainloop()
        return self._result

    def _build_ui(self) -> None:
        window = self._window

        # ─── Header ──────────────────────────────────────────────────────
        header = tk.Frame(window, bg=COLORS["bg"], pady=16, padx=24)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Review Corrections",
            font=("Segoe UI", 16, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(side=tk.LEFT)

        count_label = tk.Label(
            header,
            text=f"{len(self._corrections)} found",
            font=("Segoe UI", 11),
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
        )
        count_label.pack(side=tk.RIGHT)

        # ─── Divider ─────────────────────────────────────────────────────
        tk.Frame(window, bg=COLORS["border"], height=1).pack(fill=tk.X)

        # ─── Scrollable corrections list ─────────────────────────────────
        list_container = tk.Frame(window, bg=COLORS["bg"])
        list_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        canvas = tk.Canvas(
            list_container, bg=COLORS["bg"],
            highlightthickness=0, bd=0,
        )
        scrollbar = ttk.Scrollbar(
            list_container, orient=tk.VERTICAL, command=canvas.yview
        )

        # Style the scrollbar
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
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=620)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ─── Correction cards ────────────────────────────────────────────
        for i, corr in enumerate(self._corrections):
            var = tk.BooleanVar(value=True)
            self._selected.append(var)

            # Card frame
            card = tk.Frame(
                scroll_frame, bg=COLORS["surface"],
                padx=16, pady=12, relief=tk.FLAT,
            )
            card.pack(fill=tk.X, pady=4)

            # Top row: checkbox + original → suggested
            top_row = tk.Frame(card, bg=COLORS["surface"])
            top_row.pack(fill=tk.X)

            cb = tk.Checkbutton(
                top_row, variable=var,
                bg=COLORS["surface"], fg=COLORS["text"],
                activebackground=COLORS["surface"],
                activeforeground=COLORS["text"],
                selectcolor=COLORS["bg"],
                highlightthickness=0, bd=0,
            )
            cb.pack(side=tk.LEFT, padx=(0, 10))

            original = corr.get("original_text", "")
            suggested = corr.get("suggested_text", "")

            # Original text (red, strikethrough)
            tk.Label(
                top_row,
                text=original if len(original) <= 50 else original[:47] + "...",
                font=("Consolas", 11, "overstrike"),
                fg=COLORS["error"],
                bg=COLORS["surface"],
            ).pack(side=tk.LEFT)

            # Arrow
            tk.Label(
                top_row,
                text="  →  ",
                font=("Segoe UI", 11),
                fg=COLORS["text_dim"],
                bg=COLORS["surface"],
            ).pack(side=tk.LEFT)

            # Suggested text (green, bold)
            tk.Label(
                top_row,
                text=suggested if len(suggested) <= 50 else suggested[:47] + "...",
                font=("Consolas", 11, "bold"),
                fg=COLORS["success"],
                bg=COLORS["surface"],
            ).pack(side=tk.LEFT)

            # Bottom row: type badge + reason
            reason = corr.get("reason", "")
            correction_type = corr.get("correction_type", "")

            if reason or correction_type:
                bottom_row = tk.Frame(card, bg=COLORS["surface"])
                bottom_row.pack(fill=tk.X, padx=(32, 0), pady=(4, 0))

                if correction_type:
                    badge = tk.Label(
                        bottom_row,
                        text=f" {correction_type} ",
                        font=("Segoe UI", 8),
                        fg=COLORS["accent"],
                        bg=COLORS["bg"],
                        padx=4, pady=1,
                    )
                    badge.pack(side=tk.LEFT, padx=(0, 8))

                if reason:
                    tk.Label(
                        bottom_row,
                        text=reason,
                        font=("Segoe UI", 9),
                        fg=COLORS["text_dim"],
                        bg=COLORS["surface"],
                        anchor="w",
                    ).pack(side=tk.LEFT)

        # ─── Divider ─────────────────────────────────────────────────────
        tk.Frame(window, bg=COLORS["border"], height=1).pack(fill=tk.X)

        # ─── Footer buttons ──────────────────────────────────────────────
        footer = tk.Frame(window, bg=COLORS["bg"], pady=14, padx=24)
        footer.pack(fill=tk.X)

        # Cancel button
        cancel_btn = tk.Button(
            footer,
            text="Cancel",
            font=("Segoe UI", 10),
            bg=COLORS["btn_cancel"],
            fg=COLORS["text"],
            activebackground="#6b7280",
            activeforeground=COLORS["text"],
            relief=tk.FLAT,
            padx=16, pady=6,
            cursor="hand2",
            command=self._on_cancel,
        )
        cancel_btn.pack(side=tk.LEFT)

        # Apply All button
        apply_all_btn = tk.Button(
            footer,
            text="Apply All",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["btn_primary"],
            fg="#ffffff",
            activebackground=COLORS["btn_hover"],
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16, pady=6,
            cursor="hand2",
            command=self._on_apply_all,
        )
        apply_all_btn.pack(side=tk.RIGHT)

        # Apply Selected button
        apply_sel_btn = tk.Button(
            footer,
            text="Apply Selected",
            font=("Segoe UI", 10),
            bg=COLORS["surface"],
            fg=COLORS["text"],
            activebackground=COLORS["surface_hover"],
            activeforeground=COLORS["text"],
            relief=tk.FLAT,
            padx=16, pady=6,
            cursor="hand2",
            command=self._on_apply_selected,
        )
        apply_sel_btn.pack(side=tk.RIGHT, padx=(0, 8))

    # ─── Actions ──────────────────────────────────────────────────────────

    def _on_apply_all(self) -> None:
        self._result = self._corrections[:]
        self._window.destroy()

    def _on_apply_selected(self) -> None:
        self._result = [
            corr for corr, var in zip(self._corrections, self._selected)
            if var.get()
        ]
        self._window.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self._window.destroy()


def show_review(original_text: str, corrections: list[dict]) -> Optional[list[dict]]:
    """Show the review window and return selected corrections."""
    window = ReviewWindow(original_text, corrections)
    return window.show()
