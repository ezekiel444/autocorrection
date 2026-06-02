"""Review Window - Modern popup for reviewing corrections before applying.

Clean dark design with high-contrast text for readability.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from .theme import COLORS, FONTS, DEVELOPER


class ReviewWindow:
    """Dark-themed review window for corrections."""

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
        self._window.geometry("720x540")
        self._window.configure(bg=COLORS["bg"])
        self._window.attributes("-topmost", True)
        self._window.resizable(True, True)

        self._build_ui()
        self._center()
        self._window.mainloop()
        return self._result

    def _center(self):
        self._window.update_idletasks()
        x = (self._window.winfo_screenwidth() // 2) - (720 // 2)
        y = (self._window.winfo_screenheight() // 2) - (540 // 2)
        self._window.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        w = self._window

        # Header
        header = tk.Frame(w, bg=COLORS["bg"], padx=28, pady=18)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="Review Corrections",
            font=FONTS["heading"], bg=COLORS["bg"], fg=COLORS["text_bright"],
        ).pack(side=tk.LEFT)

        tk.Label(
            header, text=f"{len(self._corrections)} found",
            font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text_dim"],
        ).pack(side=tk.RIGHT)

        tk.Frame(w, bg=COLORS["border"], height=1).pack(fill=tk.X)

        # Scrollable list
        list_frame = tk.Frame(w, bg=COLORS["bg"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        canvas = tk.Canvas(list_frame, bg=COLORS["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                        background=COLORS["surface"], troughcolor=COLORS["bg"])

        scroll_inner = tk.Frame(canvas, bg=COLORS["bg"])
        scroll_inner.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_inner, anchor="nw", width=650)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Correction cards
        for i, corr in enumerate(self._corrections):
            var = tk.BooleanVar(value=True)
            self._selected.append(var)

            card = tk.Frame(scroll_inner, bg=COLORS["surface"], padx=16, pady=14)
            card.pack(fill=tk.X, pady=4, padx=2)

            # Top: checkbox + original -> suggested
            top = tk.Frame(card, bg=COLORS["surface"])
            top.pack(fill=tk.X)

            cb = tk.Checkbutton(
                top, variable=var, bg=COLORS["surface"],
                activebackground=COLORS["surface"], selectcolor=COLORS["bg"],
                highlightthickness=0, bd=0,
            )
            cb.pack(side=tk.LEFT, padx=(0, 12))

            original = corr.get("original_text", "")
            suggested = corr.get("suggested_text", "")

            # Original (red)
            tk.Label(
                top, text=self._truncate(original, 45),
                font=FONTS["code"], fg=COLORS["error"], bg=COLORS["surface"],
            ).pack(side=tk.LEFT)

            # Arrow
            tk.Label(
                top, text="  ->  ",
                font=FONTS["body"], fg=COLORS["text_dim"], bg=COLORS["surface"],
            ).pack(side=tk.LEFT)

            # Suggested (green)
            tk.Label(
                top, text=self._truncate(suggested, 45),
                font=FONTS["code_bold"], fg=COLORS["success"], bg=COLORS["surface"],
            ).pack(side=tk.LEFT)

            # Bottom: type + reason
            reason = corr.get("reason", "")
            ctype = corr.get("correction_type", "")
            if reason or ctype:
                bottom = tk.Frame(card, bg=COLORS["surface"])
                bottom.pack(fill=tk.X, padx=(36, 0), pady=(6, 0))

                if ctype:
                    tk.Label(
                        bottom, text=f" {ctype} ",
                        font=FONTS["small"], fg=COLORS["purple"],
                        bg=COLORS["bg"], padx=4,
                    ).pack(side=tk.LEFT, padx=(0, 8))

                if reason:
                    tk.Label(
                        bottom, text=reason,
                        font=FONTS["small"], fg=COLORS["text_dim"],
                        bg=COLORS["surface"],
                    ).pack(side=tk.LEFT)

        # Divider
        tk.Frame(w, bg=COLORS["border"], height=1).pack(fill=tk.X)

        # Footer
        footer = tk.Frame(w, bg=COLORS["bg"], pady=14, padx=28)
        footer.pack(fill=tk.X)

        tk.Button(
            footer, text="Cancel", font=FONTS["body"],
            bg=COLORS["btn_cancel"], fg=COLORS["text"],
            activebackground=COLORS["surface_hover"], activeforeground=COLORS["text"],
            relief=tk.FLAT, padx=18, pady=7, cursor="hand2",
            command=self._on_cancel,
        ).pack(side=tk.LEFT)

        tk.Button(
            footer, text="Apply All", font=FONTS["body_bold"],
            bg=COLORS["btn_primary"], fg=COLORS["text_bright"],
            activebackground=COLORS["btn_primary_hover"], activeforeground=COLORS["text_bright"],
            relief=tk.FLAT, padx=18, pady=7, cursor="hand2",
            command=self._on_apply_all,
        ).pack(side=tk.RIGHT)

        tk.Button(
            footer, text="Apply Selected", font=FONTS["body"],
            bg=COLORS["btn_secondary"], fg=COLORS["text"],
            activebackground=COLORS["surface_hover"], activeforeground=COLORS["text"],
            relief=tk.FLAT, padx=18, pady=7, cursor="hand2",
            command=self._on_apply_selected,
        ).pack(side=tk.RIGHT, padx=(0, 10))

        # Developer credit
        tk.Label(
            w, text=DEVELOPER,
            font=FONTS["credit"], bg=COLORS["bg"], fg="#4a5568",
        ).pack(side=tk.BOTTOM, pady=(0, 8))

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[:max_len - 3] + "..."

    def _on_apply_all(self):
        self._result = self._corrections[:]
        self._window.destroy()

    def _on_apply_selected(self):
        self._result = [c for c, v in zip(self._corrections, self._selected) if v.get()]
        self._window.destroy()

    def _on_cancel(self):
        self._result = None
        self._window.destroy()


def show_review(original_text: str, corrections: list[dict]) -> Optional[list[dict]]:
    """Show the review window and return selected corrections."""
    return ReviewWindow(original_text, corrections).show()
