"""Review Window Module - Tkinter popup for reviewing corrections before applying.

Shows original text with errors highlighted in red and suggested corrections
in green. Users can select/deselect individual corrections before applying.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional


class ReviewWindow:
    """Tkinter window for reviewing and selectively applying corrections.

    Displays original text with errors highlighted, shows suggested
    corrections, and allows selective application via checkboxes.
    """

    def __init__(self, original_text: str, corrections: list[dict]):
        """Initialize the review window.

        Args:
            original_text: The original text before correction.
            corrections: List of correction dicts from the LLM.
        """
        self._original_text = original_text
        self._corrections = corrections
        self._selected: list[tk.BooleanVar] = []
        self._result: Optional[list[dict]] = None
        self._window: Optional[tk.Tk] = None

    @property
    def result(self) -> Optional[list[dict]]:
        """The selected corrections after the window is closed, or None if cancelled."""
        return self._result

    def show(self) -> Optional[list[dict]]:
        """Show the review window and block until user acts.

        Returns:
            List of selected corrections, or None if cancelled.
        """
        self._window = tk.Tk()
        self._window.title("Review Corrections")
        self._window.geometry("700x500")
        self._window.configure(bg="#f5f5f5")

        # Make window stay on top
        self._window.attributes("-topmost", True)

        self._build_ui()

        # Center window on screen
        self._window.update_idletasks()
        x = (self._window.winfo_screenwidth() // 2) - (700 // 2)
        y = (self._window.winfo_screenheight() // 2) - (500 // 2)
        self._window.geometry(f"+{x}+{y}")

        self._window.mainloop()
        return self._result

    def _build_ui(self) -> None:
        """Build the window UI components."""
        window = self._window

        # Title label
        title_frame = tk.Frame(window, bg="#f5f5f5")
        title_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        tk.Label(
            title_frame,
            text=f"Found {len(self._corrections)} correction(s)",
            font=("Segoe UI", 12, "bold"),
            bg="#f5f5f5",
        ).pack(side=tk.LEFT)

        # Scrollable corrections list
        list_frame = tk.Frame(window, bg="#ffffff", relief=tk.SUNKEN, bd=1)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas = tk.Canvas(list_frame, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#ffffff")

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Add each correction as a row
        for i, corr in enumerate(self._corrections):
            var = tk.BooleanVar(value=True)
            self._selected.append(var)

            row_frame = tk.Frame(scroll_frame, bg="#ffffff", pady=4, padx=8)
            row_frame.pack(fill=tk.X, padx=4, pady=2)

            # Checkbox
            cb = tk.Checkbutton(
                row_frame, variable=var, bg="#ffffff", activebackground="#ffffff"
            )
            cb.pack(side=tk.LEFT, padx=(0, 8))

            # Correction details
            detail_frame = tk.Frame(row_frame, bg="#ffffff")
            detail_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Original in red
            original = corr.get("original_text", "")
            suggested = corr.get("suggested_text", "")
            correction_type = corr.get("correction_type", "")
            reason = corr.get("reason", "")

            text_frame = tk.Frame(detail_frame, bg="#ffffff")
            text_frame.pack(fill=tk.X)

            tk.Label(
                text_frame,
                text=original,
                fg="#d32f2f",
                font=("Consolas", 10, "overstrike"),
                bg="#ffffff",
                anchor="w",
            ).pack(side=tk.LEFT)

            tk.Label(
                text_frame,
                text=" → ",
                font=("Segoe UI", 10),
                bg="#ffffff",
            ).pack(side=tk.LEFT)

            tk.Label(
                text_frame,
                text=suggested,
                fg="#388e3c",
                font=("Consolas", 10, "bold"),
                bg="#ffffff",
                anchor="w",
            ).pack(side=tk.LEFT)

            # Type and reason
            if reason or correction_type:
                info_text = f"[{correction_type}]" if correction_type else ""
                if reason:
                    info_text += f" {reason}" if info_text else reason
                tk.Label(
                    detail_frame,
                    text=info_text,
                    fg="#757575",
                    font=("Segoe UI", 9),
                    bg="#ffffff",
                    anchor="w",
                ).pack(fill=tk.X)

            # Separator
            ttk.Separator(scroll_frame, orient=tk.HORIZONTAL).pack(
                fill=tk.X, padx=8
            )

        # Buttons frame
        btn_frame = tk.Frame(window, bg="#f5f5f5")
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
            width=12,
            bg="#e0e0e0",
        ).pack(side=tk.RIGHT, padx=(5, 0))

        tk.Button(
            btn_frame,
            text="Apply Selected",
            command=self._on_apply_selected,
            width=14,
            bg="#bbdefb",
        ).pack(side=tk.RIGHT, padx=(5, 0))

        tk.Button(
            btn_frame,
            text="Apply All",
            command=self._on_apply_all,
            width=12,
            bg="#c8e6c9",
        ).pack(side=tk.RIGHT, padx=(5, 0))

    def _on_apply_all(self) -> None:
        """Apply all corrections."""
        self._result = self._corrections[:]
        self._window.destroy()

    def _on_apply_selected(self) -> None:
        """Apply only selected corrections."""
        self._result = [
            corr
            for corr, var in zip(self._corrections, self._selected)
            if var.get()
        ]
        self._window.destroy()

    def _on_cancel(self) -> None:
        """Cancel without applying."""
        self._result = None
        self._window.destroy()


def show_review(original_text: str, corrections: list[dict]) -> Optional[list[dict]]:
    """Show the review window and return selected corrections.

    Convenience function that creates and shows the ReviewWindow.

    Args:
        original_text: The original text.
        corrections: List of correction dicts.

    Returns:
        List of selected corrections, or None if cancelled.
    """
    window = ReviewWindow(original_text, corrections)
    return window.show()
