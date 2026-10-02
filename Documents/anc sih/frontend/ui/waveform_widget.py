import numpy as np
import collections
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPen
import pyqtgraph as pg

class WaveformWidget(QFrame):
    """
    Live rolling waveform panel for displaying real-time audio signals.
    Memory-only: never saves waveforms to disk.
    """
    def __init__(self, title: str, color_hex: str = "#00FF66", sample_rate: int = 16000, window_sec: float = 3.0, parent=None):
        super().__init__(parent)
        self.title = title
        self.color_hex = color_hex
        self.sample_rate = sample_rate
        self.window_sec = window_sec
        self.max_samples = int(sample_rate * window_sec)
        
        self.data_buffer = collections.deque(maxlen=self.max_samples)
        # Pre-fill with zeros
        self.data_buffer.extend([0.0] * self.max_samples)
        
        self.is_active = False
        self.available = True
        self.setup_ui()
        
    def setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            WaveformWidget {
                background-color: #0F141D;
                border: 1px solid #1E293B;
                border-radius: 6px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        # Header Row
        header_layout = QHBoxLayout()
        
        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #E2E8F0; letter-spacing: 1px;")
        
        self.activity_dot = QLabel("●")
        self.activity_dot.setFont(QFont("Arial", 12))
        self.activity_dot.setStyleSheet("color: #64748B;") # Default gray
        
        self.status_label = QLabel("DISCONNECTED")
        self.status_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #64748B;")
        
        header_layout.addWidget(self.activity_dot)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)
        layout.addLayout(header_layout)
        
        # PyQtGraph Plot
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#090D14')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        
        # Axes limits
        self.plot_widget.setYRange(-1.05, 1.05, padding=0)
        self.plot_widget.setXRange(-self.window_sec, 0.0, padding=0)
        self.plot_widget.getAxis('bottom').setLabel('Time (s)', color='#64748B')
        self.plot_widget.getAxis('left').setLabel('Amplitude', color='#64748B')
        
        pen = pg.mkPen(color=self.color_hex, width=1.5)
        self.curve = self.plot_widget.plot(pen=pen)
        
        layout.addWidget(self.plot_widget)

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
            self.activity_dot.setStyleSheet("color: #F59E0B;") # Amber
            self.status_label.setText(custom_msg if custom_msg else "N/A — STREAM NOT CONNECTED")
            self.status_label.setStyleSheet("color: #F59E0B;")
        elif is_active:
            self.activity_dot.setStyleSheet(f"color: {self.color_hex};")
            self.status_label.setText("LIVE STREAM ACTIVE")
            self.status_label.setStyleSheet(f"color: {self.color_hex};")
        else:
            self.activity_dot.setStyleSheet("color: #64748B;")
            self.status_label.setText(custom_msg if custom_msg else "DISCONNECTED")
            self.status_label.setStyleSheet("color: #64748B;")

    def clear(self):
        """Clear buffer to silence."""
        self.data_buffer.clear()
        self.data_buffer.extend([0.0] * self.max_samples)
        self.update_plot()
