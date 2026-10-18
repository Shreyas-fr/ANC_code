"""
Mission-Control UI Components for SIH 2026 PS 26052 Edge-AI Audio Mission Control.
Includes StatusPill, ReadinessBadge, MetricCard, CollapsibleSection, NavRail,
SignalTransformWidget, and EventFeedWidget.
"""

from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QScrollArea, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QColor, QCursor

from frontend.ui.theme import Theme


class StatusPill(QFrame):
    """
    Compact instrumentation status badge.
    Format: [ ● LABEL : STATE ]
    """
    def __init__(self, label: str, initial_state: str = "OFFLINE", initial_color: str = Theme.TEXT_MUTED, parent=None):
        super().__init__(parent)
        self.label_text = label
        self.state_text = initial_state
        self.color_hex = initial_color
        
        self.setFixedHeight(28)
        self.setup_ui()
        self.set_status(initial_state, initial_color)

    def setup_ui(self):
        self.setStyleSheet(f"""
            StatusPill {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 0px 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        
        # Indicator Dot
        self.dot = QLabel("●")
        self.dot.setFont(QFont("Arial", 8))
        self.dot.setStyleSheet(f"color: {self.color_hex};")
        layout.addWidget(self.dot)
        
        # Label
        self.lbl_tag = QLabel(self.label_text)
        self.lbl_tag.setFont(QFont(Theme.FONT_FAMILY_UI, 8, QFont.Weight.Bold))
        self.lbl_tag.setStyleSheet(f"color: {Theme.TEXT_MUTED}; letter-spacing: 0.6px;")
        layout.addWidget(self.lbl_tag)
        
        # State
        self.lbl_val = QLabel(self.state_text)
        self.lbl_val.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.lbl_val.setStyleSheet(f"color: {self.color_hex};")
        layout.addWidget(self.lbl_val)

    def set_status(self, state: str, color_hex: str):
        self.state_text = state
        self.color_hex = color_hex
        self.lbl_val.setText(state)
        self.lbl_val.setStyleSheet(f"color: {color_hex};")
        self.dot.setStyleSheet(f"color: {color_hex};")


class ReadinessBadge(QFrame):
    """
    System Readiness Badge driven strictly by real-time hardware & stream state.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet(f"""
            ReadinessBadge {{
                background-color: {Theme.BG_INPUT};
                border: 1px solid {Theme.BORDER_AMBER};
                border-radius: 6px;
                padding: 0px 10px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self.dot = QLabel("●")
        self.dot.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        self.dot.setStyleSheet(f"color: {Theme.ACCENT_AMBER};")
        layout.addWidget(self.dot)

        self.lbl_state = QLabel("WAITING FOR EDGE DEVICE")
        self.lbl_state.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.lbl_state.setStyleSheet(f"color: {Theme.ACCENT_AMBER}; letter-spacing: 0.8px;")
        layout.addWidget(self.lbl_state)

    def set_state(self, state_text: str, color_hex: str, border_hex: str = None):
        if border_hex is None:
            border_hex = color_hex
        self.setStyleSheet(f"""
            ReadinessBadge {{
                background-color: {Theme.BG_INPUT};
                border: 1px solid {border_hex};
                border-radius: 6px;
                padding: 0px 10px;
            }}
        """)
        self.dot.setStyleSheet(f"color: {color_hex};")
        self.lbl_state.setText(state_text)
        self.lbl_state.setStyleSheet(f"color: {color_hex}; letter-spacing: 0.8px;")


class MetricCard(QFrame):
    """
    Bento-style KPI card with support for primary hero metrics (latency with P50/P95/Max)
    and secondary system stream metrics.
    """
    def __init__(self, title: str, tag: str = "", context: str = "", is_primary: bool = False, parent=None):
        super().__init__(parent)
        self.title_text = title
        self.tag_text = tag
        self.context_text = context
        self.is_primary = is_primary
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(105)
        self.setup_ui()

    def setup_ui(self):
        border_color = Theme.BORDER_DEFAULT
        bg_color = Theme.BG_SURFACE
        
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            MetricCard:hover {{
                border-color: {Theme.BORDER_CYAN if not self.is_primary else Theme.BORDER_VIOLET};
                background-color: {Theme.BG_HOVER};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        
        # Header Row: Label + Tag
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)
        
        self.lbl_title = QLabel(self.title_text.upper())
        self.lbl_title.setFont(QFont(Theme.FONT_FAMILY_UI, 8, QFont.Weight.Bold))
        title_color = Theme.ACCENT_VIOLET_LIGHT if self.is_primary else Theme.TEXT_MUTED
        self.lbl_title.setStyleSheet(f"color: {title_color}; letter-spacing: 0.8px;")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        
        if self.tag_text:
            self.lbl_tag = QLabel(self.tag_text)
            self.lbl_tag.setFont(QFont(Theme.FONT_FAMILY_MONO, 8))
            self.lbl_tag.setStyleSheet(f"""
                color: {Theme.TEXT_SECONDARY};
                background-color: {Theme.BG_INPUT};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 3px;
                padding: 1px 6px;
            """)
            header_layout.addWidget(self.lbl_tag)
            
        layout.addLayout(header_layout)
        
        # Center: Large Value (28-32px font for hero hierarchy)
        self.lbl_val = QLabel("--")
        val_size = 22 if self.is_primary else 18
        self.lbl_val.setFont(QFont(Theme.FONT_FAMILY_MONO, val_size, QFont.Weight.Bold))
        self.lbl_val.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")
        layout.addWidget(self.lbl_val)
        
        # Bottom: Context / Subtext
        self.lbl_sub = QLabel(self.context_text if self.context_text else "Telemetry unavailable")
        self.lbl_sub.setFont(QFont(Theme.FONT_FAMILY_UI, 8))
        self.lbl_sub.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        layout.addWidget(self.lbl_sub)

    def set_value(self, value_text: str, color_hex: str = Theme.TEXT_PRIMARY, subtext: str = None):
        self.lbl_val.setText(str(value_text))
        self.lbl_val.setStyleSheet(f"color: {color_hex};")
        if subtext is not None:
            self.lbl_sub.setText(subtext)

    def set_unavailable(self, reason: str = "Telemetry unavailable"):
        self.lbl_val.setText("--")
        self.lbl_val.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        self.lbl_sub.setText(reason)


class SignalTransformWidget(QFrame):
    """
    Visual bridge between Raw Audio Input and Enhanced Output.
    Communicates: RAW AUDIO IN ➔ PI 5 BCM2712 ➔ DFN3 ➔ ENHANCED AUDIO OUT.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet(f"""
            SignalTransformWidget {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # Stage 1: Input Tag
        self.lbl_in = QLabel("PRE-AI RAW AUDIO")
        self.lbl_in.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.lbl_in.setStyleSheet(f"color: {Theme.ACCENT_CYAN};")
        layout.addWidget(self.lbl_in)

        arr1 = QLabel("➔")
        arr1.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        arr1.setStyleSheet(f"color: {Theme.TEXT_DISABLED};")
        layout.addWidget(arr1)

        # Stage 2: Hardware
        self.lbl_pi = QLabel("PI 5 (BCM2712)")
        self.lbl_pi.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.lbl_pi.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        layout.addWidget(self.lbl_pi)

        arr2 = QLabel("➔")
        arr2.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        arr2.setStyleSheet(f"color: {Theme.TEXT_DISABLED};")
        layout.addWidget(arr2)

        # Stage 3: AI Inference
        self.lbl_ai = QLabel("DFN3 ENGINE")
        self.lbl_ai.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.lbl_ai.setStyleSheet(f"color: {Theme.ACCENT_VIOLET_LIGHT};")
        layout.addWidget(self.lbl_ai)

        arr3 = QLabel("➔")
        arr3.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        arr3.setStyleSheet(f"color: {Theme.TEXT_DISABLED};")
        layout.addWidget(arr3)

        # Stage 4: Enhanced Out
        self.lbl_out = QLabel("ENHANCED PCM (PORT 5005)")
        self.lbl_out.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.lbl_out.setStyleSheet(f"color: {Theme.ACCENT_EMERALD};")
        layout.addWidget(self.lbl_out)

        layout.addStretch()

        self.lbl_state = QLabel("● IDLE")
        self.lbl_state.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.lbl_state.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        layout.addWidget(self.lbl_state)

    def set_active(self, is_active: bool):
        if is_active:
            self.lbl_state.setText("● AI TRANSFORM ACTIVE")
            self.lbl_state.setStyleSheet(f"color: {Theme.ACCENT_EMERALD};")
            self.setStyleSheet(f"""
                SignalTransformWidget {{
                    background-color: {Theme.BG_ELEVATED};
                    border: 1px solid {Theme.BORDER_CYAN};
                    border-radius: 6px;
                }}
            """)
        else:
            self.lbl_state.setText("● WAITING FOR STREAM")
            self.lbl_state.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
            self.setStyleSheet(f"""
                SignalTransformWidget {{
                    background-color: {Theme.BG_SURFACE};
                    border: 1px solid {Theme.BORDER_DEFAULT};
                    border-radius: 6px;
                }}
            """)


class EventFeedWidget(QFrame):
    """
    Real-time system activity & event log feed.
    Captures the latest 20 verified application lifecycle events.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.events = []
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet(f"""
            EventFeedWidget {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header
        h_layout = QHBoxLayout()
        lbl_title = QLabel("SYSTEM ACTIVITY LOG")
        lbl_title.setFont(QFont(Theme.FONT_FAMILY_UI, 9, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; letter-spacing: 0.6px;")
        h_layout.addWidget(lbl_title)
        h_layout.addStretch()

        self.lbl_count = QLabel("0 events")
        self.lbl_count.setFont(QFont(Theme.FONT_FAMILY_MONO, 8))
        self.lbl_count.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        h_layout.addWidget(self.lbl_count)
        layout.addLayout(h_layout)

        # List Widget
        self.list_widget = QListWidget()
        self.list_widget.setFixedHeight(120)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {Theme.BG_GRAPH};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 4px;
                color: {Theme.TEXT_SECONDARY};
                font-family: {Theme.FONT_FAMILY_MONO};
                font-size: 10px;
            }}
            QListWidget::item {{
                padding: 2px 4px;
                border-bottom: 1px solid {Theme.BG_INPUT};
            }}
        """)
        layout.addWidget(self.list_widget)

    def log_event(self, category: str, message: str, level: str = "INFO"):
        now_str = datetime.now().strftime("%H:%M:%S")
        
        color_tag = Theme.TEXT_SECONDARY
        if level == "SUCCESS":
            color_tag = Theme.ACCENT_EMERALD
        elif level == "WARN":
            color_tag = Theme.ACCENT_AMBER
        elif level == "ERROR":
            color_tag = Theme.ACCENT_ROSE
        elif level == "AI":
            color_tag = Theme.ACCENT_VIOLET_LIGHT

        entry_text = f"[{now_str}] [{category}] {message}"
        item = QListWidgetItem(entry_text)
        item.setForeground(QColor(color_tag))
        
        self.list_widget.insertItem(0, item)
        if self.list_widget.count() > 20:
            self.list_widget.takeItem(20)
            
        self.lbl_count.setText(f"{self.list_widget.count()} events")


class CollapsibleSection(QFrame):
    """
    Clean engineering accordion container with smooth toggle.
    """
    toggled = Signal(bool)

    def __init__(self, title: str, badge_text: str = "", is_expanded: bool = True, parent=None):
        super().__init__(parent)
        self.title_text = title
        self.badge_text = badge_text
        self.is_expanded = is_expanded
        
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet(f"""
            CollapsibleSection {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 8px;
            }}
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Header Button Bar
        self.header_btn = QPushButton()
        self.header_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_header_btn_style()
        
        h_layout = QHBoxLayout(self.header_btn)
        h_layout.setContentsMargins(14, 8, 14, 8)
        h_layout.setSpacing(10)
        
        # Chevron icon
        self.lbl_chevron = QLabel("▼" if self.is_expanded else "▶")
        self.lbl_chevron.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        self.lbl_chevron.setStyleSheet(f"color: {Theme.ACCENT_CYAN};")
        h_layout.addWidget(self.lbl_chevron)
        
        # Title
        self.lbl_title = QLabel(self.title_text)
        self.lbl_title.setFont(QFont(Theme.FONT_FAMILY_UI, 9, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; letter-spacing: 0.5px;")
        h_layout.addWidget(self.lbl_title)
        
        h_layout.addStretch()
        
        # Optional Badge
        if self.badge_text:
            self.lbl_badge = QLabel(self.badge_text)
            self.lbl_badge.setFont(QFont(Theme.FONT_FAMILY_MONO, 8))
            self.lbl_badge.setStyleSheet(f"""
                color: {Theme.TEXT_MUTED};
                background-color: {Theme.BG_INPUT};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 2px 8px;
            """)
            h_layout.addWidget(self.lbl_badge)
            
        self.header_btn.clicked.connect(self.toggle_collapse)
        self.main_layout.addWidget(self.header_btn)
        
        # Content Widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(14, 12, 14, 12)
        self.content_layout.setSpacing(6)
        self.content_widget.setVisible(self.is_expanded)
        self.main_layout.addWidget(self.content_widget)

    def _update_header_btn_style(self):
        self.header_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_ELEVATED};
                border: none;
                border-bottom: {'1px solid ' + Theme.BORDER_SUBTLE if self.is_expanded else 'none'};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom-left-radius: {'0px' if self.is_expanded else '8px'};
                border-bottom-right-radius: {'0px' if self.is_expanded else '8px'};
                padding: 8px 12px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {Theme.BG_HOVER};
            }}
        """)

    def set_content_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def toggle_collapse(self):
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)
        self.lbl_chevron.setText("▼" if self.is_expanded else "▶")
        self._update_header_btn_style()
        self.toggled.emit(self.is_expanded)


class NavRail(QFrame):
    """
    Operations console navigation sidebar with categorized sections:
    - OVERVIEW: Overview, Live Audio, DSP Spectrum, AI Performance
    - SYSTEM: Signal Chain, Diagnostics, Event Feed
    Supports collapsed (~60px) and expanded (~210px) states.
    """
    section_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        self.current_active = "overview"
        self.setup_ui()

    def setup_ui(self):
        self.setFixedWidth(210)
        self.setStyleSheet(f"""
            NavRail {{
                background-color: {Theme.BG_SECONDARY};
                border-right: 1px solid {Theme.BORDER_DEFAULT};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(2)
        
        self.buttons = {}
        
        # Section Category: MONITOR
        self.lbl_cat_mon = QLabel("MONITOR")
        self.lbl_cat_mon.setFont(QFont(Theme.FONT_FAMILY_UI, 8, QFont.Weight.Bold))
        self.lbl_cat_mon.setStyleSheet(f"color: {Theme.TEXT_MUTED}; letter-spacing: 1.2px; padding-left: 8px; padding-bottom: 4px;")
        layout.addWidget(self.lbl_cat_mon)
        
        monitor_items = [
            ("overview", "Overview", "☵"),
            ("audio", "Live Audio", "〰"),
            ("spectrum", "DSP Spectrum", "📶"),
            ("ai", "AI Engine", "⚡"),
        ]
        for key, text, icon in monitor_items:
            btn = self._create_nav_button(key, text, icon)
            layout.addWidget(btn)
            self.buttons[key] = (btn, text, icon)
            
        layout.addSpacing(16)
        
        # Section Category: SYSTEM
        self.lbl_cat_sys = QLabel("SYSTEM")
        self.lbl_cat_sys.setFont(QFont(Theme.FONT_FAMILY_UI, 8, QFont.Weight.Bold))
        self.lbl_cat_sys.setStyleSheet(f"color: {Theme.TEXT_MUTED}; letter-spacing: 1.2px; padding-left: 8px; padding-bottom: 4px;")
        layout.addWidget(self.lbl_cat_sys)
        
        system_items = [
            ("pipeline", "Signal Chain", "➔"),
            ("diag", "Diagnostics", "⚙"),
            ("events", "Activity Log", "📋"),
        ]
        for key, text, icon in system_items:
            btn = self._create_nav_button(key, text, icon)
            layout.addWidget(btn)
            self.buttons[key] = (btn, text, icon)
            
        layout.addStretch()
        
        # Bottom Hardware Badge
        self.hw_frame = QFrame()
        self.hw_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 8px;
            }}
        """)
        hw_layout = QVBoxLayout(self.hw_frame)
        hw_layout.setContentsMargins(6, 4, 6, 4)
        hw_layout.setSpacing(2)
        
        self.lbl_hw_title = QLabel("Raspberry Pi 5")
        self.lbl_hw_title.setFont(QFont(Theme.FONT_FAMILY_UI, 8, QFont.Weight.Bold))
        self.lbl_hw_title.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")
        hw_layout.addWidget(self.lbl_hw_title)
        
        self.lbl_hw_sub = QLabel("● BCM2712 Edge Node")
        self.lbl_hw_sub.setFont(QFont(Theme.FONT_FAMILY_UI, 7))
        self.lbl_hw_sub.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        hw_layout.addWidget(self.lbl_hw_sub)
        
        layout.addWidget(self.hw_frame)
        layout.addSpacing(8)
        
        # Collapse / Expand Toggle Button
        self.btn_toggle = QPushButton("◀  Collapse")
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_INPUT};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {Theme.TEXT_PRIMARY};
                border-color: {Theme.BORDER_DEFAULT};
            }}
        """)
        self.btn_toggle.clicked.connect(self.toggle_rail)
        layout.addWidget(self.btn_toggle)
        
        self.set_active("overview")

    def _create_nav_button(self, key: str, text: str, icon: str) -> QPushButton:
        btn = QPushButton(f" {icon}   {text}")
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(lambda checked=False, k=key: self._on_btn_clicked(k))
        return btn

    def _on_btn_clicked(self, key: str):
        self.set_active(key)
        self.section_clicked.emit(key)

    def set_active(self, active_key: str):
        self.current_active = active_key
        for key, (btn, text, icon) in self.buttons.items():
            if key == active_key:
                label = f" {icon}" if self.is_collapsed else f" {icon}   {text}"
                btn.setText(label)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Theme.BG_ELEVATED};
                        color: {Theme.ACCENT_CYAN};
                        border: none;
                        border-left: 3px solid {Theme.ACCENT_CYAN};
                        border-radius: 4px;
                        padding: 8px 10px;
                        font-size: 11px;
                        font-weight: bold;
                        text-align: left;
                    }}
                """)
            else:
                label = f" {icon}" if self.is_collapsed else f" {icon}   {text}"
                btn.setText(label)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {Theme.TEXT_SECONDARY};
                        border: none;
                        border-left: 3px solid transparent;
                        border-radius: 4px;
                        padding: 8px 10px;
                        font-size: 11px;
                        font-weight: 500;
                        text-align: left;
                    }}
                    QPushButton:hover {{
                        background-color: {Theme.BG_HOVER};
                        color: {Theme.TEXT_PRIMARY};
                    }}
                """)

    def toggle_rail(self):
        self.is_collapsed = not self.is_collapsed
        if self.is_collapsed:
            self.setFixedWidth(60)
            self.lbl_cat_mon.setVisible(False)
            self.lbl_cat_sys.setVisible(False)
            self.hw_frame.setVisible(False)
            self.btn_toggle.setText("▶")
        else:
            self.setFixedWidth(210)
            self.lbl_cat_mon.setVisible(True)
            self.lbl_cat_sys.setVisible(True)
            self.hw_frame.setVisible(True)
            self.btn_toggle.setText("◀  Collapse")
        self.set_active(self.current_active)
