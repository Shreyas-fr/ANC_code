"""
Centralized Theme & Design System for SIH 2026 PS 26052 Edge-AI Audio Mission Control.
Professional DSP, aerospace mission-control, and AI inference monitoring visual tokens.
"""

class Theme:
    # Deep Canvas & Surface Hierarchy
    BG_ROOT = "#05080D"          # Deep blue-black primary canvas
    BG_SECONDARY = "#080D15"     # Sidebar & Header base surface
    BG_SURFACE = "#0C131D"       # Primary container & card surface
    BG_ELEVATED = "#101A27"      # Elevated container / active item
    BG_HOVER = "#142235"         # Interactive hover surface
    BG_INPUT = "#0A1019"         # Recessed badge / input surface
    BG_GRAPH = "#04070B"         # Deep oscilloscope / DSP chart background

    # Borders & Dividers
    BORDER_DEFAULT = "#1B2A3A"   # Primary panel border
    BORDER_SUBTLE = "#14202D"    # Subtle dividers & chart grid
    BORDER_ACCENT = "#0284C7"    # Focus border
    BORDER_CYAN = "#22D3EE"      # Technical cyan border
    BORDER_VIOLET = "#8B5CF6"    # AI violet border
    BORDER_GREEN = "#34D399"     # Healthy status border
    BORDER_AMBER = "#F59E0B"     # Warning status border
    BORDER_RED = "#FB4F67"       # Error status border

    # Primary Semantics & Accents
    ACCENT_CYAN = "#22D3EE"      # Primary Technical Cyan (Audio In/Out, Network, Live Data)
    ACCENT_CYAN_LIGHT = "#38BDF8"# Secondary Cyan
    ACCENT_CYAN_GLOW = "rgba(34, 211, 238, 0.12)"

    ACCENT_VIOLET = "#8B5CF6"    # AI Violet (StatefulPolarLSTM, Model Inference)
    ACCENT_VIOLET_LIGHT = "#A78BFA"
    ACCENT_VIOLET_GLOW = "rgba(139, 92, 246, 0.15)"

    ACCENT_EMERALD = "#34D399"   # Success / Online / Ready / Synchronized
    ACCENT_AMBER = "#F59E0B"     # Warning / Degraded / Waiting
    ACCENT_ROSE = "#FB4F67"      # Error / Disconnected / Fault

    # Typography Colors
    TEXT_PRIMARY = "#F1F5F9"     # High-contrast primary text
    TEXT_SECONDARY = "#94A3B8"   # Secondary labels & parameters
    TEXT_MUTED = "#64748B"       # Muted units & metadata
    TEXT_DISABLED = "#334155"    # Inactive / disabled text

    # Fonts
    FONT_FAMILY_UI = "'Segoe UI', Inter, system-ui, -apple-system, sans-serif"
    FONT_FAMILY_MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, monospace"


GLOBAL_QSS = f"""
/* Global Reset & Base */
QWidget {{
    background-color: transparent;
    color: {Theme.TEXT_PRIMARY};
    font-family: {Theme.FONT_FAMILY_UI};
    font-size: 12px;
}}

QMainWindow, QDialog {{
    background-color: {Theme.BG_ROOT};
}}

/* Scroll Area & Scrollbars */
QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background-color: {Theme.BG_ROOT};
    width: 6px;
    margin: 0px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background-color: {Theme.BORDER_DEFAULT};
    min-height: 28px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {Theme.TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {Theme.BG_ROOT};
    height: 6px;
    margin: 0px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background-color: {Theme.BORDER_DEFAULT};
    min-width: 28px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {Theme.TEXT_MUTED};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Tooltips */
QToolTip {{
    background-color: {Theme.BG_ELEVATED};
    color: {Theme.TEXT_PRIMARY};
    border: 1px solid {Theme.BORDER_DEFAULT};
    padding: 6px 10px;
    border-radius: 4px;
    font-family: {Theme.FONT_FAMILY_UI};
    font-size: 11px;
}}

/* Push Buttons */
QPushButton {{
    background-color: {Theme.BG_SURFACE};
    color: {Theme.TEXT_PRIMARY};
    border: 1px solid {Theme.BORDER_DEFAULT};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {Theme.BG_HOVER};
    border-color: {Theme.BORDER_CYAN};
}}

QPushButton:pressed {{
    background-color: {Theme.BG_ELEVATED};
}}

/* Combo Boxes */
QComboBox {{
    background-color: {Theme.BG_SURFACE};
    color: {Theme.TEXT_PRIMARY};
    border: 1px solid {Theme.BORDER_DEFAULT};
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 500;
    min-height: 20px;
}}

QComboBox:hover {{
    border-color: {Theme.BORDER_CYAN};
    background-color: {Theme.BG_HOVER};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {Theme.TEXT_SECONDARY};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {Theme.BG_SURFACE};
    color: {Theme.TEXT_PRIMARY};
    border: 1px solid {Theme.BORDER_DEFAULT};
    selection-background-color: {Theme.BG_HOVER};
    selection-color: {Theme.ACCENT_CYAN};
    padding: 4px;
    outline: none;
}}
"""
