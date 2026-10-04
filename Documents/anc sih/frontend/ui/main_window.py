import sys
import os
import json
import time
import numpy as np
import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QSplitter, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QColor

from frontend.audio.jitter_buffer import JitterBuffer
from frontend.audio.playback import AudioPlayback
from frontend.network.audio_receiver import AudioReceiver
from frontend.network.telemetry_receiver import TelemetryReceiver
from frontend.ui.waveform_widget import WaveformWidget
from frontend.ui.spectrum_widget import SpectrumWidget
from frontend.ui.telemetry_panel import TelemetryPanel
from frontend.ui.pipeline_widget import PipelineWidget

logger = logging.getLogger("MainWindow")

class MainWindow(QMainWindow):
    """
    SIH 2026 PS 26052 Live Defence Communication Dashboard.
    Runs on PC for live playback, visualization, telemetry monitoring, and status management.
    PC NEVER performs AI inference or PyTorch execution.
    Normal mode NEVER records audio to disk.
    """
    def __init__(self, config_path: str):
        super().__init__()
        self.config_path = config_path
        self.load_config()
        
        self.is_demo_mode = False
        self.state = "DISCONNECTED"  # DISCONNECTED, LIVE, DEGRADED, AI ERROR
        self.latest_pi_telemetry = {}
        
        # Audio Pipeline Components
        self.jitter_buffer = JitterBuffer(
            sample_rate=self.cfg['sample_rate'],
            target_buffer_ms=self.cfg['buffer_ms'],
            max_buffer_ms=self.cfg.get('max_buffer_ms', 50)
        )
        self.playback = AudioPlayback(
            jitter_buffer=self.jitter_buffer,
            sample_rate=self.cfg['sample_rate']
        )
        
        # Network Receivers
        self.enhanced_receiver = AudioReceiver(
            port=self.cfg['audio_port'],
            stream_name="enhanced",
            timeout_sec=self.cfg['packet_timeout_ms'] / 1000.0
        )
        self.input_receiver = AudioReceiver(
            port=self.cfg['input_port'],
            stream_name="input",
            timeout_sec=self.cfg['packet_timeout_ms'] / 1000.0
        )
        self.telemetry_receiver = TelemetryReceiver(
            port=self.cfg['telemetry_port'],
            timeout_sec=2.0
        )
        
        self.setup_ui()
        self.bind_signals()
        
        # Demo generator state
        self.demo_timer = QTimer(self)
        self.demo_timer.timeout.connect(self._generate_demo_frame)
        self.demo_phase = 0.0
        self.demo_seq = 0
        
        # UI Refresh Timer (30 FPS)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._on_ui_tick)
        self.ui_timer.start(33) # ~30 FPS
        
        # Start Network Receivers
        self.enhanced_receiver.start()
        self.input_receiver.start()
        self.telemetry_receiver.start()

    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                self.cfg = json.load(f)
        except Exception as e:
            logger.warning(f"Error loading config from {self.config_path}, using defaults: {e}")
            self.cfg = {
                "audio_port": 5005,
                "telemetry_port": 5006,
                "input_port": 5007,
                "sample_rate": 16000,
                "frame_size": 256,
                "buffer_ms": 48,
                "max_buffer_ms": 50,
                "packet_timeout_ms": 1000,
                "window_seconds": 3.0,
                "output_device": None,
                "fft_size": 512
            }

    def setup_ui(self):
        self.setWindowTitle("SIH 2026 | PS 26052 — Live Defence Communication Dashboard")
        self.resize(1440, 900)
        self.setMinimumSize(1200, 750)
        
        # Central Widget & Dark Theme Styling
        central_widget = QWidget()
        central_widget.setStyleSheet("""
            QWidget {
                background-color: #090D14;
                color: #F8FAFC;
                font-family: Inter, Segoe UI, sans-serif;
            }
        """)
        self.setCentralWidget(central_widget)
        
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)
        
        # 1. Header Bar
        header = self._build_header()
        root_layout.addWidget(header)
        
        # 2. Main Middle Area (Splitter: Left Visualizations, Right Telemetry)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Container (Waveforms + Spectrum)
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        self.wave_input = WaveformWidget(
            title="PANEL 1: INPUT AUDIO (PI BEFORE AI)",
            color_hex="#38BDF8",
            sample_rate=self.cfg['sample_rate'],
            window_sec=self.cfg['window_seconds']
        )
        self.wave_enhanced = WaveformWidget(
            title="PANEL 2: ENHANCED AUDIO (UDP 5005)",
            color_hex="#10B981",
            sample_rate=self.cfg['sample_rate'],
            window_sec=self.cfg['window_seconds']
        )
        self.spectrum_widget = SpectrumWidget(
            sample_rate=self.cfg['sample_rate'],
            fft_size=self.cfg['fft_size']
        )
        
        left_layout.addWidget(self.wave_input, stretch=1)
        left_layout.addWidget(self.wave_enhanced, stretch=1)
        left_layout.addWidget(self.spectrum_widget, stretch=1)
        
        # Right Container (Telemetry Panel)
        self.telemetry_panel = TelemetryPanel()
        
        main_splitter.addWidget(left_container)
        main_splitter.addWidget(self.telemetry_panel)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)
        
        root_layout.addWidget(main_splitter, stretch=1)
        
        # 3. Bottom Pipeline Bar
        self.pipeline_widget = PipelineWidget()
        root_layout.addWidget(self.pipeline_widget)

    def _build_header(self) -> QFrame:
        header_frame = QFrame()
        header_frame.setFixedHeight(64)
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #0F141D;
                border: 1px solid #1E293B;
                border-radius: 6px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(16, 8, 16, 8)
        
        # Left Titles
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        
        lbl_main = QLabel("SIH 2026 | PS 26052")
        lbl_main.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        lbl_main.setStyleSheet("color: #38BDF8; letter-spacing: 2px;")
        
        lbl_sub = QLabel("AI-POWERED DEFENCE COMMUNICATION DASHBOARD")
        lbl_sub.setFont(QFont("Inter", 9))
        lbl_sub.setStyleSheet("color: #94A3B8; letter-spacing: 1px;")
        
        title_box.addWidget(lbl_main)
        title_box.addWidget(lbl_sub)
        h_layout.addLayout(title_box)
        
        h_layout.addSpacing(20)
        
        # Connection Indicators
        ind_box = QHBoxLayout()
        ind_box.setSpacing(12)
        
        self.ind_edge = self._create_indicator("● EDGE")
        self.ind_bt = self._create_indicator("● BLUETOOTH")
        self.ind_audio = self._create_indicator("● AUDIO")
        self.ind_ai = self._create_indicator("● AI")
        self.lbl_run_state = self._create_indicator("DISCONNECTED")
        
        ind_box.addWidget(self.ind_edge)
        ind_box.addWidget(self.ind_bt)
        ind_box.addWidget(self.ind_audio)
        ind_box.addWidget(self.ind_ai)
        ind_box.addWidget(self.lbl_run_state)
        h_layout.addLayout(ind_box)
        
        h_layout.addStretch()
        
        # Audio Output Combo & Controls
        ctrl_box = QHBoxLayout()
        ctrl_box.setSpacing(10)
        
        # Mute Button
        self.btn_mute = QPushButton("🔊 AUDIO ON")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #7F1D1D;
                color: #FCA5A5;
                border: 1px solid #EF4444;
            }
        """)
        self.btn_mute.clicked.connect(self._toggle_mute)
        ctrl_box.addWidget(self.btn_mute)
        
        # Device Selector
        self.combo_device = QComboBox()
        self.combo_device.setFixedWidth(200)
        self.combo_device.setStyleSheet("""
            QComboBox {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QComboBox QAbstractItemView {
                background-color: #0F141D;
                color: #F8FAFC;
                selection-background-color: #38BDF8;
            }
        """)
        self._populate_audio_devices()
        self.combo_device.currentIndexChanged.connect(self._on_device_changed)
        ctrl_box.addWidget(self.combo_device)
        
        # Mode Switcher Button (LIVE vs DEMO)
        self.btn_mode = QPushButton("MODE: LIVE NETWORK")
        self.btn_mode.setStyleSheet("""
            QPushButton {
                background-color: #065F46;
                color: #A7F3D0;
                border: 1px solid #10B981;
                padding: 6px 14px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        self.btn_mode.clicked.connect(self._toggle_demo_mode)
        ctrl_box.addWidget(self.btn_mode)
        
        h_layout.addLayout(ctrl_box)
        return header_frame

    def _create_indicator(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #64748B;")
        return lbl

    def _populate_audio_devices(self):
        self.combo_device.clear()
        devices = AudioPlayback.get_output_devices()
        default_idx = AudioPlayback.get_default_output_index()
        selected = 0
        if not devices:
            self.combo_device.addItem("No playback devices found", None)
            return
        for i, (idx, name) in enumerate(devices):
            label = name
            if default_idx is not None and idx == default_idx:
                label = f"{name} (system default)"
                selected = i
            self.combo_device.addItem(label, idx)
        self.combo_device.setCurrentIndex(selected)
        self.playback.device = self.combo_device.currentData()

    def bind_signals(self):
        self.enhanced_receiver.frame_received.connect(self._on_enhanced_frame)
        self.enhanced_receiver.status_changed.connect(self._on_stream_status_changed)
        
        self.input_receiver.frame_received.connect(self._on_input_frame)
        self.input_receiver.status_changed.connect(self._on_stream_status_changed)
        
        self.telemetry_receiver.telemetry_received.connect(self._on_telemetry_received)
        self.telemetry_receiver.telemetry_status.connect(self._on_telemetry_status)

    @Slot(str, np.ndarray, int, float)
    def _on_enhanced_frame(self, stream_name: str, samples: np.ndarray, seq: int, timestamp: float):
        if self.is_demo_mode:
            return
            
        # 1. Add to JitterBuffer for live audio playback
        self.jitter_buffer.write(samples)
        
        # 2. Add to enhanced waveform plot
        self.wave_enhanced.add_samples(samples)
        
        # 3. Add to spectrum display
        self.spectrum_widget.update_spectrum(samples)
        
        # 4. Auto-start playback on stream arrival without requiring user 'Play' click
        if not self.playback.is_playing:
            self.playback.start()

    @Slot(str, np.ndarray, int, float)
    def _on_input_frame(self, stream_name: str, samples: np.ndarray, seq: int, timestamp: float):
        if self.is_demo_mode:
            return
        self.wave_input.add_samples(samples)

    @Slot(str, bool)
    def _on_stream_status_changed(self, stream_name: str, is_connected: bool):
        if self.is_demo_mode:
            return
            
        if stream_name == "enhanced":
            if is_connected:
                self._set_run_state("LIVE")
                self.ind_edge.setStyleSheet("color: #10B981;")
                self.ind_audio.setStyleSheet("color: #10B981;")
                self.wave_enhanced.set_active_status(True)
            else:
                self._set_run_state("DISCONNECTED")
                self.ind_edge.setStyleSheet("color: #EF4444;")
                self.ind_audio.setStyleSheet("color: #64748B;")
                self.wave_enhanced.set_active_status(False)
                # Mute/stop playback when stream disappears
                self.playback.stop()
                self.wave_enhanced.clear()
                self.spectrum_widget.clear()
                
        elif stream_name == "input":
            if is_connected:
                self.wave_input.set_active_status(True)
            else:
                self.wave_input.set_active_status(
                    is_active=False,
                    is_available=False,
                    custom_msg="N/A — PROTOCOL EXTENSION PORT 5007"
                )

    @Slot(dict)
    def _on_telemetry_received(self, data: dict):
        if self.is_demo_mode:
            return
        self.latest_pi_telemetry = data
        self.telemetry_panel.update_telemetry(data)
        
        if data.get('bluetooth_connected', False):
            self.ind_bt.setStyleSheet("color: #10B981;")
        else:
            self.ind_bt.setStyleSheet("color: #EF4444;")
            
        if data.get('model_active', False):
            self.ind_ai.setStyleSheet("color: #10B981;")
        else:
            self.ind_ai.setStyleSheet("color: #EF4444;")
        self._refresh_run_state()

    @Slot(bool)
    def _on_telemetry_status(self, is_connected: bool):
        if self.is_demo_mode:
            return
        if not is_connected:
            self.telemetry_panel.reset_pi_telemetry()
            self.ind_bt.setStyleSheet("color: #64748B;")
            self.ind_ai.setStyleSheet("color: #64748B;")

    def _on_ui_tick(self):
        """30 FPS UI Update Loop."""
        if self.is_demo_mode:
            self.wave_input.update_plot()
            self.wave_enhanced.update_plot()
            return
            
        # Update rolling plot graphics
        self.wave_input.update_plot()
        self.wave_enhanced.update_plot()
        
        # Update network stats in telemetry panel
        stats = self.enhanced_receiver.get_stats()
        jb = self.jitter_buffer.get_stats()
        buf_ms = jb.get("level_ms", self.jitter_buffer.get_level_ms())
        stats["jitter_underruns"] = jb.get("underrun_count", 0)
        stats["jitter_overflows"] = jb.get("overflow_count", 0)
        self.telemetry_panel.update_network_stats(stats, buf_ms)
        self._refresh_run_state()
        
        # Check input receiver status if port 5007 is idle
        if not self.input_receiver.is_connected:
            self.wave_input.set_active_status(
                is_active=False,
                is_available=False,
                custom_msg="N/A — PROTOCOL EXTENSION PORT 5007"
            )
            
        # Update pipeline widget status
        self.pipeline_widget.update_pipeline(
            net_connected=self.enhanced_receiver.is_connected,
            is_demo=False,
            telemetry=self.telemetry_receiver.latest_data
        )

    def _toggle_demo_mode(self):
        self.is_demo_mode = not self.is_demo_mode
        if self.is_demo_mode:
            self.btn_mode.setText("MODE: DEMO (OFFLINE TEST)")
            self.btn_mode.setStyleSheet("""
                QPushButton {
                    background-color: #78350F;
                    color: #FDE68A;
                    border: 1px solid #F59E0B;
                    padding: 6px 14px;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            self.ind_edge.setStyleSheet("color: #F59E0B;")
            self.ind_bt.setStyleSheet("color: #F59E0B;")
            self.ind_audio.setStyleSheet("color: #F59E0B;")
            self.ind_ai.setStyleSheet("color: #F59E0B;")
            
            self.wave_input.set_active_status(True, True, "DEMO — NOT LIVE PI DATA")
            self.wave_enhanced.set_active_status(True, True, "DEMO — NOT LIVE PI DATA")
            
            self.pipeline_widget.update_pipeline(True, is_demo=True)
            self.demo_timer.start(16) # ~16ms per frame
            
            # Start demo audio playback
            if not self.playback.is_playing:
                self.playback.start()
        else:
            self.btn_mode.setText("MODE: LIVE NETWORK")
            self.btn_mode.setStyleSheet("""
                QPushButton {
                    background-color: #065F46;
                    color: #A7F3D0;
                    border: 1px solid #10B981;
                    padding: 6px 14px;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            self.demo_timer.stop()
            self.jitter_buffer.clear()
            self.wave_input.clear()
            self.wave_enhanced.clear()
            self.spectrum_widget.clear()
            
            # Reset stream status check
            self._on_stream_status_changed("enhanced", self.enhanced_receiver.is_connected)

    def _generate_demo_frame(self):
        """Generate 1 kHz test signal for DEMO mode testing."""
        if not self.is_demo_mode:
            return
            
        t = np.arange(256)
        freq = 1000.0
        sr = self.cfg['sample_rate']
        
        # Raw noisy input signal
        clean = np.sin(2 * np.pi * freq * (t + self.demo_phase) / sr)
        noise = np.random.normal(0, 0.2, 256)
        noisy_in = (clean * 0.5 + noise).astype(np.float32)
        
        # Enhanced output signal
        enhanced_out = (clean * 0.5).astype(np.float32)
        
        self.demo_phase += 256
        self.demo_seq += 1
        
        # Push to buffer & plots
        self.jitter_buffer.write(enhanced_out)
        self.wave_input.add_samples(noisy_in)
        self.wave_enhanced.add_samples(enhanced_out)
        self.spectrum_widget.update_spectrum(enhanced_out)

    def _set_run_state(self, state: str):
        self.state = state
        colors = {
            "LIVE": "#10B981",
            "DEGRADED": "#F59E0B",
            "AI ERROR": "#EF4444",
            "DISCONNECTED": "#64748B",
        }
        color = colors.get(state, "#64748B")
        if hasattr(self, "lbl_run_state"):
            self.lbl_run_state.setText(state)
            self.lbl_run_state.setStyleSheet(f"color: {color};")

    def _refresh_run_state(self):
        if self.is_demo_mode:
            return
        if not self.enhanced_receiver.is_connected:
            self._set_run_state("DISCONNECTED")
            return
        tel = self.latest_pi_telemetry or {}
        nan_inf = int(tel.get("nan_inf_events") or 0)
        sha_stale = bool(tel.get("model_is_stale"))
        ai_error = nan_inf > 0 or sha_stale
        if tel.get("model_active") is False and tel.get("diag_mode") == "dfn3":
            ai_error = True
        stats = self.enhanced_receiver.get_stats()
        jb = self.jitter_buffer.get_stats()
        degraded = (
            stats.get("loss_pct", 0.0) > 5.0
            or jb.get("underrun_count", 0) > 0
            or str(tel.get("cooler_hint") or "") in ("WARM", "HOT", "THROTTLED")
        )
        if ai_error:
            self._set_run_state("AI ERROR")
        elif degraded:
            self._set_run_state("DEGRADED")
        else:
            self._set_run_state("LIVE")

    def _toggle_mute(self):
        muted = self.btn_mute.isChecked()
        self.playback.set_muted(muted)
        if muted:
            self.btn_mute.setText("🔇 AUDIO MUTED")
        else:
            self.btn_mute.setText("🔊 AUDIO ON")

    def _on_device_changed(self, index: int):
        device_id = self.combo_device.currentData()
        if self.playback.is_playing:
            self.playback.stop()
            self.playback.start(device=device_id)

    def closeEvent(self, event):
        """Clean resource shutdown on window close."""
        self.ui_timer.stop()
        self.demo_timer.stop()
        self.playback.stop()
        self.enhanced_receiver.stop()
        self.input_receiver.stop()
        self.telemetry_receiver.stop()
        event.accept()
