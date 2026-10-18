"""
Professional Audio/DSP Spectrum Analyzer for SIH 2026 PS 26052.
Real-time 0–8 kHz FFT spectral energy distribution analyzer using pyqtgraph.
"""

import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
import pyqtgraph as pg

from frontend.ui.theme import Theme


class SpectrumWidget(QFrame):
    """
    Mission-control 0–8 kHz FFT frequency spectrum analyzer.
    Renders real-time magnitude response (dB) across audio spectrum.
    """
    def __init__(self, sample_rate: int = 16000, fft_size: int = 512, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate) # 0 to 8000 Hz
        
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setup_ui()
        
    def setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            SpectrumWidget {{
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
        header_layout.setSpacing(8)
        
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        
        title_label = QLabel("LIVE FREQUENCY SPECTRUM (0–8 kHz)")
        title_label.setFont(QFont(Theme.FONT_FAMILY_UI, 10, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; letter-spacing: 0.6px;")
        title_box.addWidget(title_label)
        
        sub_label = QLabel("Real-Time FFT Spectral Energy Distribution (Enhanced AI Output)")
        sub_label.setFont(QFont(Theme.FONT_FAMILY_UI, 8))
        sub_label.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        title_box.addWidget(sub_label)
        
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        
        # Tech Specs Badge
        badge = QLabel("512-pt FFT · 31.25 Hz/bin")
        badge.setFont(QFont(Theme.FONT_FAMILY_MONO, 8))
        badge.setStyleSheet(f"""
            color: {Theme.TEXT_SECONDARY};
            background-color: {Theme.BG_INPUT};
            border: 1px solid {Theme.BORDER_SUBTLE};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(badge)
        
        layout.addLayout(header_layout)
        
        # PyQtGraph Plot
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(Theme.BG_GRAPH)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.12)
        
        # Axis Ranges & Labels
        self.plot_widget.setXRange(0, 8000, padding=0)
        self.plot_widget.setYRange(-90, 0, padding=0)
        self.plot_widget.getAxis('bottom').setLabel('Frequency (Hz)', color=Theme.TEXT_MUTED)
        self.plot_widget.getAxis('left').setLabel('Magnitude (dB)', color=Theme.TEXT_MUTED)
        self.plot_widget.getAxis('bottom').setTextPen(Theme.TEXT_MUTED)
        self.plot_widget.getAxis('left').setTextPen(Theme.TEXT_MUTED)
        self.plot_widget.getAxis('bottom').setPen(Theme.BORDER_SUBTLE)
        self.plot_widget.getAxis('left').setPen(Theme.BORDER_SUBTLE)
        
        # Semi-transparent cyan fill for DSP aesthetic
        pen = pg.mkPen(color=Theme.ACCENT_CYAN, width=1.6)
        fill_brush = pg.mkBrush(QColor(34, 211, 238, 22))
        self.curve = self.plot_widget.plot(pen=pen, fillLevel=-90.0, fillBrush=fill_brush)
        
        # Initial silent baseline
        self.curve.setData(self.freqs, np.full_like(self.freqs, -90.0))
        
        layout.addWidget(self.plot_widget, stretch=1)

    def update_spectrum(self, samples: np.ndarray):
        """Compute FFT on audio slice and update dB plot."""
        if samples is None or len(samples) < 64:
            return
            
        # Pad or truncate to fft_size
        if len(samples) < self.fft_size:
            padded = np.pad(samples, (0, self.fft_size - len(samples)))
        else:
            padded = samples[-self.fft_size:]
            
        # Windowing & FFT calculation
        windowed = padded * np.hanning(len(padded))
        fft_complex = np.fft.rfft(windowed)
        mag = np.abs(fft_complex) / (len(padded) / 2.0)
        
        # Convert to dB magnitude (log scale)
        db_mag = 20.0 * np.log10(np.maximum(mag, 1e-5))
        db_mag = np.clip(db_mag, -90.0, 0.0)
        
        self.curve.setData(self.freqs, db_mag)

    def clear(self):
        """Reset spectrum to silence."""
        self.curve.setData(self.freqs, np.full_like(self.freqs, -90.0))
