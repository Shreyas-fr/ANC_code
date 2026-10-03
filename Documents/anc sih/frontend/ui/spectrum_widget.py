import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import pyqtgraph as pg

class SpectrumWidget(QFrame):
    """
    Live 0–8 kHz FFT spectrum display for visualization.
    Uses numpy FFT on enhanced audio frames purely for UI rendering.
    Decoupled from AI model inference.
    """
    def __init__(self, sample_rate: int = 16000, fft_size: int = 512, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate) # 0 to 8000 Hz
        
        self.setup_ui()
        
    def setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            SpectrumWidget {
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
        title_label = QLabel("LIVE FREQUENCY SPECTRUM (0–8 kHz)")
        title_label.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #E2E8F0; letter-spacing: 1px;")
        
        sub_label = QLabel("FFT VISUALIZATION ONLY — DECOUPLED FROM AI")
        sub_label.setFont(QFont("Consolas", 8))
        sub_label.setStyleSheet("color: #64748B;")
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(sub_label)
        layout.addLayout(header_layout)
        
        # Plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#090D14')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        
        self.plot_widget.setXRange(0, 8000, padding=0)
        self.plot_widget.setYRange(-90, 0, padding=0)
        self.plot_widget.getAxis('bottom').setLabel('Frequency (Hz)', color='#64748B')
        self.plot_widget.getAxis('left').setLabel('Magnitude (dB)', color='#64748B')
        
        pen = pg.mkPen(color='#38BDF8', width=1.5)
        self.curve = self.plot_widget.plot(pen=pen)
        
        # Initial zero curve
        self.curve.setData(self.freqs, np.full_like(self.freqs, -90.0))
        
        layout.addWidget(self.plot_widget)

    def update_spectrum(self, samples: np.ndarray):
        """Compute FFT on audio slice and update dB plot."""
        if samples is None or len(samples) < 64:
            return
            
        # Pad or truncate to fft_size
        if len(samples) < self.fft_size:
            padded = np.pad(samples, (0, self.fft_size - len(samples)))
        else:
            padded = samples[-self.fft_size:]
            
        # Window & FFT
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
