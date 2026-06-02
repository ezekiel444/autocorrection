"""Shared UI Theme - Colors and constants for all popup windows.

Provides a consistent, readable dark theme with clear typography.
"""

# ─── Color Palette ────────────────────────────────────────────────────────────
# A refined dark theme with high contrast for readability

COLORS = {
    # Backgrounds
    "bg": "#1a1b26",             # Deep navy background
    "surface": "#24283b",        # Card/panel surface
    "surface_hover": "#2f3349",  # Hover state

    # Text
    "text": "#c0caf5",           # Primary text (bright, readable)
    "text_bright": "#ffffff",    # High emphasis text
    "text_dim": "#565f89",       # Secondary/muted text

    # Accents
    "accent": "#7aa2f7",         # Blue accent
    "success": "#9ece6a",        # Green for suggestions
    "error": "#f7768e",          # Red/pink for errors
    "warning": "#e0af68",        # Amber for warnings
    "purple": "#bb9af7",         # Purple for badges

    # Borders
    "border": "#3b4261",         # Subtle border

    # Buttons
    "btn_primary": "#7aa2f7",    # Primary button (blue)
    "btn_primary_hover": "#89b4fa",
    "btn_hover": "#89b4fa",      # Alias for backward compat
    "btn_secondary": "#3b4261",  # Secondary button
    "btn_danger": "#f7768e",     # Danger button
    "btn_cancel": "#414868",     # Cancel/neutral
}

# ─── Typography ───────────────────────────────────────────────────────────────

FONTS = {
    "heading": ("Segoe UI", 16, "bold"),
    "subheading": ("Segoe UI", 13, "bold"),
    "body": ("Segoe UI", 11),
    "body_bold": ("Segoe UI", 11, "bold"),
    "small": ("Segoe UI", 10),
    "code": ("Consolas", 12),
    "code_bold": ("Consolas", 12, "bold"),
    "credit": ("Segoe UI", 9),
}

# ─── Developer Info ───────────────────────────────────────────────────────────

DEVELOPER = "Ezekiel Matomi Lucky"
