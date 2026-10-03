"""
Hero Live Audio Waveform Instrumentation for SIH 2026 PS 26052.
Real-time PCM signal visualization using pyqtgraph.
Memory-only ring buffer: zero disk I/O.
"""

import numpy as np
import collections
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPen
import pyqtgraph as pg

from frontend.ui.theme import Theme


class WaveformWidget(QFrame):
    """
    Mission-control live rolling waveform analyzer.
    Renders incoming PCM buffer at 30 FPS with high contrast and DSP instrumentation.
    """
    def __init__(self, title: str, subtitle: str = "", port_label: str = "UDP 5005",
                 color_hex: str = Theme.ACCENT_CYAN, sample_rate: int = 16000,
                 window_sec: float = 3.0, parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.port_label = port_label
        self.color_hex = color_hex
        self.sample_rate = sample_rate
        self.window_sec = window_sec
        self.max_samples = int(sample_rate * window_sec)
        
        self.data_buffer = collections.deque(maxlen=self.max_samples)
        # Pre-fill with zeros for clean start
        self.data_buffer.extend([0.0] * self.max_samples)
        
        self.is_active = False
        self.available = True
        
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setup_ui()
        
    def setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            WaveformWidget {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        
        # Header Row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        # Title Box
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        
        self.activity_dot = QLabel("●")
        self.activity_dot.setFont(QFont("Arial", 8))
        self.activity_dot.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        title_row.addWidget(self.activity_dot)
        
        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont(Theme.FONT_FAMILY_UI, 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; letter-spacing: 0.6px;")
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        
        title_box.addLayout(title_row)
        
        if self.subtitle:
            self.lbl_sub = QLabel(self.subtitle)
            self.lbl_sub.setFont(QFont(Theme.FONT_FAMILY_UI, 8))
            self.lbl_sub.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
            title_box.addWidget(self.lbl_sub)
            
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        
        # Technical Micro-Badge (Port + Sampling)
        self.tech_badge = QLabel(f"{self.port_label} · 16 kHz")
        self.tech_badge.setFont(QFont(Theme.FONT_FAMILY_MONO, 8))
        self.tech_badge.setStyleSheet(f"""
            color: {Theme.TEXT_SECONDARY};
            background-color: {Theme.BG_INPUT};
            border: 1px solid {Theme.BORDER_SUBTLE};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(self.tech_badge)
        
        # Status Badge
        self.status_badge = QLabel("WAITING FOR STREAM")
        self.status_badge.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        self.status_badge.setStyleSheet(f"""
            color: {Theme.TEXT_MUTED};
            background-color: {Theme.BG_INPUT};
            border: 1px solid {Theme.BORDER_SUBTLE};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(self.status_badge)
        
        layout.addLayout(header_layout)
        
        # PyQtGraph Plot Widget
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(Theme.BG_GRAPH)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.12)
        
        # Axes limits & styling
        self.plot_widget.setYRange(-1.05, 1.05, padding=0)
        self.plot_widget.setXRange(-self.window_sec, 0.0, padding=0)
        self.plot_widget.getAxis('bottom').setLabel('Time (s)', color=Theme.TEXT_MUTED)
        self.plot_widget.getAxis('left').setLabel('Amplitude', color=Theme.TEXT_MUTED)
        self.plot_widget.getAxis('bottom').setTextPen(Theme.TEXT_MUTED)
        self.plot_widget.getAxis('left').setTextPen(Theme.TEXT_MUTED)
        self.plot_widget.getAxis('bottom').setPen(Theme.BORDER_SUBTLE)
        self.plot_widget.getAxis('left').setPen(Theme.BORDER_SUBTLE)
        
        pen = pg.mkPen(color=self.color_hex, width=1.6)
        self.curve = self.plot_widget.plot(pen=pen)
        
        layout.addWidget(self.plot_widget, stretch=1)

    def add_samples(self, samples: np.ndarray):
        """Append new PCM samples to rolling waveform buffer."""
        if samples is None or len(samples) == 0:
            return
        for s in samples:
            self.data_buffer.append(float(s))

    def update_plot(self):
        """Redraw waveform curve (called by GUI timer)."""
        arr = np.array(self.data_buffer, dtype=np.float32)
        time_x = np.linspace(-self.window_sec, 0.0, len(arr))
        self.curve.setData(time_x, arr)

    def set_active_status(self, is_active: bool, is_available: bool = True, custom_msg: str = None):
        """Update live activity status indicator."""
        self.is_active = is_active
        self.available = is_available
        
        if not is_available:
            self.activity_dot.setStyleSheet(f"color: {Theme.ACCENT_AMBER};")
            msg = custom_msg if custom_msg else "WAITING FOR STREAM"
            self.status_badge.setText(msg)
            self.status_badge.setStyleSheet(f"""
                color: {Theme.ACCENT_AMBER};
                background-color: {Theme.BG_INPUT};
                border: 1px solid {Theme.ACCENT_AMBER};
                border-radius: 4px;
                padding: 2px 8px;
            """)
        elif is_active:
            self.activity_dot.setStyleSheet(f"color: {self.color_hex};")
            msg = custom_msg if custom_msg else "● LIVE STREAM ACTIVE"
            self.status_badge.setText(msg)
            self.status_badge.setStyleSheet(f"""
                color: {self.color_hex};
                background-color: {Theme.BG_INPUT};
                border: 1px solid {self.color_hex};
                border-radius: 4px;
                padding: 2px 8px;
            """)
        else:
            self.activity_dot.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
            msg = custom_msg if custom_msg else "WAITING FOR STREAM"
            self.status_badge.setText(msg)
            self.status_badge.setStyleSheet(f"""
                color: {Theme.TEXT_MUTED};
                background-color: {Theme.BG_INPUT};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 2px 8px;
            """)

    def clear(self):
        """Clear buffer to silence."""
        self.data_buffer.clear()
        self.data_buffer.extend([0.0] * self.max_samples)
        self.update_plot()
