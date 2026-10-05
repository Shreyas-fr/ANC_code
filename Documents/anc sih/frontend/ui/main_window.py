"""
SIH 2026 PS 26052 Edge-AI Audio Mission Control — Master Window.
High-performance native PySide6 desktop GUI for live audio playback,
real-time DSP visualization, telemetry monitoring, and network diagnostics.
"""

import sys
import os
import json
import time
import numpy as np
import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QColor, QCursor

from frontend.audio.jitter_buffer import JitterBuffer
from frontend.audio.playback import AudioPlayback
from frontend.network.audio_receiver import AudioReceiver
from frontend.network.telemetry_receiver import TelemetryReceiver

from frontend.ui.theme import Theme, GLOBAL_QSS
from frontend.ui.components import (
    StatusPill, ReadinessBadge, MetricCard, NavRail,
    SignalTransformWidget, EventFeedWidget
)
from frontend.ui.waveform_widget import WaveformWidget
from frontend.ui.spectrum_widget import SpectrumWidget
from frontend.ui.diagnostics_panel import DiagnosticsPanel

logger = logging.getLogger("MainWindow")


class MainWindow(QMainWindow):
    """
    SIH 2026 PS 26052 Edge-AI Audio Mission Control.
    Edge hardware performs AI inference; PC operates strictly as
    network receiver, real-time audio playback engine, and DSP telemetry console.
    """
    def __init__(self, config_path: str):
        super().__init__()
        self.config_path = config_path
        self.load_config()
        
        self.state = "DISCONNECTED" # DISCONNECTED, LIVE, DEGRADED, ERROR
        
        # Audio Pipeline Components
        self.jitter_buffer = JitterBuffer(
            sample_rate=self.cfg['sample_rate'],
            target_buffer_ms=self.cfg['buffer_ms'],
            max_buffer_ms=self.cfg.get('max_buffer_ms', 250),
            prebuffer=True
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
        
        # UI Refresh Timer (30 FPS)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._on_ui_tick)
        self.ui_timer.start(33) # ~30 FPS
        
        # Start Network Receivers
        self.enhanced_receiver.start()
        self.input_receiver.start()
        self.telemetry_receiver.start()
        
        self.event_feed.log_event("SYSTEM", "Mission Control GUI initialized", "INFO")
        self.event_feed.log_event("NETWORK", "Listening on UDP 5005 (Enhanced), 5007 (Input), 5006 (Telemetry)", "INFO")

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
        self.setWindowTitle("SIH 2026 | PS 26052 — Edge-AI Audio Mission Control")
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)
        
        # Apply Global Styling
        self.setStyleSheet(GLOBAL_QSS)
        
        # Central Root Container
        central_widget = QWidget()
        central_widget.setObjectName("CentralRoot")
        central_widget.setStyleSheet(f"#CentralRoot {{ background-color: {Theme.BG_ROOT}; }}")
        self.setCentralWidget(central_widget)
        
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # 1. Mission-Control Fixed Top Header
        self.header_frame = self._build_header()
        root_layout.addWidget(self.header_frame)
        
        # 2. Main Body Container (Nav Rail + Vertically Scrollable Content Area)
        body_container = QWidget()
        body_layout = QHBoxLayout(body_container)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        
        # Operations Navigation Rail
        self.nav_rail = NavRail()
        self.nav_rail.section_clicked.connect(self._scroll_to_section)
        body_layout.addWidget(self.nav_rail)
        
        # Scroll Area for Main Content
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.scroll_content.setStyleSheet(f"#ScrollContent {{ background-color: {Theme.BG_ROOT}; }}")
        
        self.content_layout = QVBoxLayout(self.scroll_content)
        self.content_layout.setContentsMargins(24, 20, 24, 28)
        self.content_layout.setSpacing(20)
        
        # Section Anchors for Navigation
        self.section_widgets = {}
        
        # -------------------------------------------------------------
        # Section 1: Hero Live Audio Waveforms & Transformation Flow
        # -------------------------------------------------------------
        self.audio_section_container = QWidget()
        self.audio_section_layout = QVBoxLayout(self.audio_section_container)
        self.audio_section_layout.setContentsMargins(0, 0, 0, 0)
        self.audio_section_layout.setSpacing(10)
        
        sec_header = QHBoxLayout()
        lbl_sec1 = QLabel("LIVE AUDIO INSTRUMENTATION")
        lbl_sec1.setFont(QFont(Theme.FONT_FAMILY_UI, 10, QFont.Weight.Bold))
        lbl_sec1.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; letter-spacing: 1px;")
        sec_header.addWidget(lbl_sec1)
        sec_header.addStretch()
        lbl_sec1_sub = QLabel("16 kHz Mono PCM · Low-Latency Memory Ring Buffer · Zero Disk I/O")
        lbl_sec1_sub.setFont(QFont(Theme.FONT_FAMILY_UI, 8))
        lbl_sec1_sub.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        sec_header.addWidget(lbl_sec1_sub)
        self.audio_section_layout.addLayout(sec_header)
        
        # Dual Waveform Layout (Responsive Layout)
        self.wave_container = QWidget()
        self.wave_layout = QHBoxLayout(self.wave_container)
        self.wave_layout.setContentsMargins(0, 0, 0, 0)
        self.wave_layout.setSpacing(14)
        
        self.wave_input = WaveformWidget(
            title="INPUT AUDIO",
            subtitle="Raw microphone / Bluetooth HFP pre-AI stream",
            port_label="UDP 5007",
            color_hex=Theme.ACCENT_CYAN,
            sample_rate=self.cfg['sample_rate'],
            window_sec=self.cfg['window_seconds']
        )
        self.wave_enhanced = WaveformWidget(
            title="ENHANCED OUTPUT",
            subtitle="AI filtered DFN3 post-enhancement stream",
            port_label="UDP 5005",
            color_hex=Theme.ACCENT_VIOLET,
            sample_rate=self.cfg['sample_rate'],
            window_sec=self.cfg['window_seconds']
        )
        
        self.wave_layout.addWidget(self.wave_input, stretch=1)
        self.wave_layout.addWidget(self.wave_enhanced, stretch=1)
        self.audio_section_layout.addWidget(self.wave_container)
        
        # Central Signal Transformation Flow Bridge
        self.signal_transform = SignalTransformWidget()
        self.audio_section_layout.addWidget(self.signal_transform)
        
        self.content_layout.addWidget(self.audio_section_container)
        self.section_widgets["overview"] = self.audio_section_container
        self.section_widgets["audio"] = self.audio_section_container
        
        # -------------------------------------------------------------
        # Section 2: AI & Stream Performance KPI Bento Row
        # -------------------------------------------------------------
        self.kpi_container = QWidget()
        self.kpi_layout = QHBoxLayout(self.kpi_container)
        self.kpi_layout.setContentsMargins(0, 0, 0, 0)
        self.kpi_layout.setSpacing(12)
        
        # Hero Primary KPI: AI Latency (Pi Model Inference)
        self.kpi_lat = MetricCard("END-TO-END LATENCY", tag="P50 / Median", context="Pi Model Execution Time", is_primary=True)
        self.kpi_loss = MetricCard("PACKET LOSS", tag="UDP 5005", context="0 lost / 0 recv")
        self.kpi_sr = MetricCard("SAMPLE RATE", tag="16 kHz", context="HFP Mono 256 Smpl")
        self.kpi_sr.set_value("16 kHz", Theme.ACCENT_CYAN, "HFP Mono 256 Smpl")
        self.kpi_temp = MetricCard("PI TEMPERATURE", tag="BCM2712", context="Thermal Core Watchdog")
        self.kpi_buf = MetricCard("JITTER BUFFER", tag="Ring Buffer", context="Target: 48.0 ms (Zero Disk I/O)")
        self.kpi_buf.set_value("0.0 ms", Theme.ACCENT_EMERALD, "Target: 48.0 ms (Zero Disk I/O)")
        
        self.kpi_layout.addWidget(self.kpi_lat, stretch=3)
        self.kpi_layout.addWidget(self.kpi_loss, stretch=2)
        self.kpi_layout.addWidget(self.kpi_sr, stretch=2)
        self.kpi_layout.addWidget(self.kpi_temp, stretch=2)
        self.kpi_layout.addWidget(self.kpi_buf, stretch=2)
        
        self.content_layout.addWidget(self.kpi_container)
        self.section_widgets["ai"] = self.kpi_container
        
        # -------------------------------------------------------------
        # Section 3: Live Frequency Spectrum (0–8 kHz DSP Analyzer)
        # -------------------------------------------------------------
        self.spectrum_widget = SpectrumWidget(
            sample_rate=self.cfg['sample_rate'],
            fft_size=self.cfg['fft_size']
        )
        self.content_layout.addWidget(self.spectrum_widget)
        self.section_widgets["spectrum"] = self.spectrum_widget
        
        # -------------------------------------------------------------
        # Section 4: Collapsible Engineering Diagnostics & Signal Chain
        # -------------------------------------------------------------
        self.diagnostics_panel = DiagnosticsPanel()
        self.content_layout.addWidget(self.diagnostics_panel)
        self.section_widgets["diag"] = self.diagnostics_panel
        self.section_widgets["pipeline"] = self.diagnostics_panel.sec_pipe
        
        # -------------------------------------------------------------
        # Section 5: Real-Time System Activity Log
        # -------------------------------------------------------------
        self.event_feed = EventFeedWidget()
        self.content_layout.addWidget(self.event_feed)
        self.section_widgets["events"] = self.event_feed
        
        self.scroll_area.setWidget(self.scroll_content)
        body_layout.addWidget(self.scroll_area, stretch=1)
        
        root_layout.addWidget(body_container, stretch=1)

    def _build_header(self) -> QFrame:
        header_frame = QFrame()
        header_frame.setFixedHeight(66)
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_SECONDARY};
                border-bottom: 1px solid {Theme.BORDER_DEFAULT};
            }}
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(20, 8, 20, 8)
        h_layout.setSpacing(16)
        
        # Left Branding
        brand_box = QVBoxLayout()
        brand_box.setSpacing(1)
        
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        
        lbl_sih = QLabel("SIH 2026 · PS 26052")
        lbl_sih.setFont(QFont(Theme.FONT_FAMILY_UI, 11, QFont.Weight.Bold))
        lbl_sih.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; letter-spacing: 0.8px;")
        title_row.addWidget(lbl_sih)
        title_row.addStretch()
        
        brand_box.addLayout(title_row)
        
        lbl_sub = QLabel("EDGE AI COMMUNICATION ENHANCEMENT  |  DEEPFILTERNET3 · 16 kHz HFP")
        lbl_sub.setFont(QFont(Theme.FONT_FAMILY_MONO, 8))
        lbl_sub.setStyleSheet(f"color: {Theme.TEXT_MUTED}; letter-spacing: 0.5px;")
        brand_box.addWidget(lbl_sub)
        
        h_layout.addLayout(brand_box)
        h_layout.addSpacing(16)
        
        # Center: Real-Time Readiness Badge
        self.readiness_badge = ReadinessBadge()
        h_layout.addWidget(self.readiness_badge)
        
        h_layout.addSpacing(16)
        
        # Right: Instrumentation Status Badges
        pills_box = QHBoxLayout()
        pills_box.setSpacing(8)
        
        self.pill_edge = StatusPill("EDGE", "OFFLINE", Theme.ACCENT_ROSE)
        self.pill_bt = StatusPill("BLUETOOTH", "UNAVAILABLE", Theme.TEXT_MUTED)
        self.pill_ai = StatusPill("AI", "UNAVAILABLE", Theme.TEXT_MUTED)
        self.pill_audio = StatusPill("AUDIO", "IDLE", Theme.TEXT_MUTED)
        self.pill_net = StatusPill("NET", "DISCONNECTED", Theme.ACCENT_ROSE)
        
        pills_box.addWidget(self.pill_edge)
        pills_box.addWidget(self.pill_bt)
        pills_box.addWidget(self.pill_ai)
        pills_box.addWidget(self.pill_audio)
        pills_box.addWidget(self.pill_net)
        h_layout.addLayout(pills_box)
        
        h_layout.addStretch()
        
        # Controls: Audio Output Selector & Mute Toggle
        ctrl_box = QHBoxLayout()
        ctrl_box.setSpacing(10)
        
        # Device Selector
        self.combo_device = QComboBox()
        self.combo_device.setFixedWidth(190)
        self._populate_audio_devices()
        self.combo_device.currentIndexChanged.connect(self._on_device_changed)
        ctrl_box.addWidget(self.combo_device)
        
        # Mute Button
        self.btn_mute = QPushButton("🔊 AUDIO ON")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setStyleSheet(f"""
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
                border-color: {Theme.BORDER_CYAN};
            }}
            QPushButton:checked {{
                background-color: #4C0519;
                color: #FECDD3;
                border: 1px solid {Theme.ACCENT_ROSE};
            }}
        """)
        self.btn_mute.clicked.connect(self._toggle_mute)
        ctrl_box.addWidget(self.btn_mute)
        
        h_layout.addLayout(ctrl_box)
        return header_frame

    def _populate_audio_devices(self):
        self.combo_device.addItem("Output: System Default", None)
        devices = AudioPlayback.get_output_devices()
        for idx, name in devices:
            self.combo_device.addItem(name, idx)

    def _scroll_to_section(self, section_id: str):
        if section_id in self.section_widgets:
            target = self.section_widgets[section_id]
            self.scroll_area.ensureWidgetVisible(target, 0, 20)

    def bind_signals(self):
        self.enhanced_receiver.frame_received.connect(self._on_enhanced_frame)
        self.enhanced_receiver.status_changed.connect(self._on_stream_status_changed)
        
        self.input_receiver.frame_received.connect(self._on_input_frame)
        self.input_receiver.status_changed.connect(self._on_stream_status_changed)
        
        self.telemetry_receiver.telemetry_received.connect(self._on_telemetry_received)
        self.telemetry_receiver.telemetry_status.connect(self._on_telemetry_status)

    @Slot(str, np.ndarray, int, float)
    def _on_enhanced_frame(self, stream_name: str, samples: np.ndarray, seq: int, timestamp: float):
        # 1. Add to JitterBuffer for live audio playback
        self.jitter_buffer.write(samples)
        
        # 2. Add to enhanced waveform plot
        self.wave_enhanced.add_samples(samples)
        
        # 3. Add to spectrum display
        self.spectrum_widget.update_spectrum(samples)
        
        # 4. Auto-start playback on stream arrival without requiring user 'Play' click
        if not self.playback.is_playing:
            self.playback.start()
            self.event_feed.log_event("AUDIO", "Low-latency playback auto-started", "SUCCESS")

    @Slot(str, np.ndarray, int, float)
    def _on_input_frame(self, stream_name: str, samples: np.ndarray, seq: int, timestamp: float):
        self.wave_input.add_samples(samples)

    @Slot(str, bool)
    def _on_stream_status_changed(self, stream_name: str, is_connected: bool):
        if stream_name == "enhanced":
            if is_connected:
                self.state = "LIVE"
                self.pill_edge.set_status("CONNECTED", Theme.ACCENT_EMERALD)
                self.pill_audio.set_status("LIVE STREAM", Theme.ACCENT_EMERALD)
                self.pill_net.set_status("SYNCHRONIZED", Theme.ACCENT_EMERALD)
                self.wave_enhanced.set_active_status(True)
                self.signal_transform.set_active(True)
                self.readiness_badge.set_state("SYSTEM READY (STREAMING)", Theme.ACCENT_EMERALD, Theme.BORDER_GREEN)
                self.event_feed.log_event("STREAM", "UDP Port 5005 connected", "SUCCESS")
            else:
                self.state = "DISCONNECTED"
                self.pill_edge.set_status("OFFLINE", Theme.ACCENT_ROSE)
                self.pill_audio.set_status("IDLE", Theme.TEXT_MUTED)
                self.pill_net.set_status("DISCONNECTED", Theme.ACCENT_ROSE)
                self.wave_enhanced.set_active_status(False)
                self.signal_transform.set_active(False)
                self.readiness_badge.set_state("WAITING FOR EDGE DEVICE", Theme.ACCENT_AMBER, Theme.BORDER_AMBER)
                # Mute/stop playback when stream disappears
                self.playback.stop()
                self.wave_enhanced.clear()
                self.spectrum_widget.clear()
                self.event_feed.log_event("STREAM", "UDP Port 5005 timeout (auto-muted)", "WARN")
                
        elif stream_name == "input":
            if is_connected:
                self.wave_input.set_active_status(True)
                self.event_feed.log_event("STREAM", "UDP Port 5007 input stream connected", "SUCCESS")
            else:
                self.wave_input.set_active_status(
                    is_active=False,
                    is_available=False,
                    custom_msg="PORT 5007 IDLE"
                )

    @Slot(dict)
    def _on_telemetry_received(self, data: dict):
        self.diagnostics_panel.update_telemetry(data)
        
        # Update Pills
        if data.get('bluetooth_connected', False):
            self.pill_bt.set_status("CONNECTED", Theme.ACCENT_EMERALD)
        else:
            self.pill_bt.set_status("DISCONNECTED", Theme.ACCENT_ROSE)
            
        if data.get('model_active', False):
            self.pill_ai.set_status("ACTIVE", Theme.ACCENT_EMERALD)
        else:
            self.pill_ai.set_status("INACTIVE", Theme.ACCENT_ROSE)
            
        # Update Hero AI Latency KPI
        buffer_ms = self.jitter_buffer.get_level_ms()
        if 'latency_median_ms' in data:
            lat = data['latency_median_ms']
            self.kpi_lat.set_value(f"buffer: {buffer_ms:.1f} ms", Theme.ACCENT_VIOLET_LIGHT, f"processing delay: {lat:.1f} ms")
        elif 'latency_ms' in data:
            lat = data['latency_ms']
            self.kpi_lat.set_value(f"buffer: {buffer_ms:.1f} ms", Theme.ACCENT_VIOLET_LIGHT, f"processing delay: {lat:.1f} ms")
        else:
            self.kpi_lat.set_value(f"buffer: {buffer_ms:.1f} ms", Theme.ACCENT_VIOLET_LIGHT, "processing delay: unknown")
            
        if 'temperature_c' in data:
            temp = data['temperature_c']
            color = Theme.ACCENT_EMERALD if temp < 70 else (Theme.ACCENT_AMBER if temp < 82 else Theme.ACCENT_ROSE)
            status_text = "Normal" if temp < 70 else ("Elevated" if temp < 82 else "Throttling")
            self.kpi_temp.set_value(f"{temp:.1f}°C", color, f"BCM2712 Core · {status_text}")

    @Slot(bool)
    def _on_telemetry_status(self, is_connected: bool):
        if not is_connected:
            self.diagnostics_panel.reset_pi_telemetry()
            self.pill_bt.set_status("UNAVAILABLE", Theme.TEXT_MUTED)
            self.pill_ai.set_status("UNAVAILABLE", Theme.TEXT_MUTED)
            self.kpi_lat.set_unavailable("Telemetry unavailable")
            self.kpi_temp.set_unavailable("Telemetry unavailable")
            self.event_feed.log_event("TELEMETRY", "Telemetry Port 5006 offline", "WARN")

    def _on_ui_tick(self):
        """30 FPS UI Update Loop."""
        # Update rolling plot graphics
        self.wave_input.update_plot()
        self.wave_enhanced.update_plot()
        
        # Update network stats in diagnostics panel and KPI
        stats_enh = self.enhanced_receiver.get_stats()
        stats_in = self.input_receiver.get_stats()
        buf_stats = self.jitter_buffer.get_stats()
        telemetry = self.telemetry_receiver.latest_data or {}
        
        # State Machine (F1d)
        new_state = "DISCONNECTED"
        new_color = Theme.ACCENT_ROSE
        
        is_enh_conn = stats_enh['connected']
        is_raw_conn = stats_in['connected']
        
        loss_5s = stats_enh.get('recent_loss_pct', 0.0)
        jitter_p95 = stats_enh.get('jitter_p95_ms', 0.0)
        target_buf_ms = getattr(self.jitter_buffer, 'target_samples', 960) / getattr(self.jitter_buffer, 'sample_rate', 16000) * 1000.0
        
        # Check underruns over last 5s
        if not hasattr(self, '_last_underruns'):
            self._last_underruns = buf_stats.get('underrun_events', 0)
            self._underrun_diffs = [] # (time, diff)
        
        curr_time = time.time()
        curr_underruns = buf_stats.get('underrun_events', 0)
        if curr_underruns > self._last_underruns:
            self._underrun_diffs.append((curr_time, curr_underruns - self._last_underruns))
            self._last_underruns = curr_underruns
            
        # prune underruns
        while self._underrun_diffs and self._underrun_diffs[0][0] < curr_time - 5.0:
            self._underrun_diffs.pop(0)
        underruns_5s = sum(x[1] for x in self._underrun_diffs)
        
        ai_error_reported = telemetry.get('error', False) # Sender might report model error
        model_active = telemetry.get('model_active', True) # Assume active if no telemetry yet
        
        if not is_enh_conn and not is_raw_conn:
            new_state = "DISCONNECTED"
            new_color = Theme.ACCENT_ROSE
        elif is_raw_conn and not is_enh_conn:
            new_state = "AI ERROR"
            new_color = Theme.ACCENT_ROSE
        elif ai_error_reported:
            new_state = "AI ERROR"
            new_color = Theme.ACCENT_ROSE
        elif not model_active:
            new_state = "PASSTHROUGH"
            new_color = Theme.ACCENT_CYAN
        elif getattr(self.jitter_buffer, '_holding', False) or (is_enh_conn and stats_enh['received'] < 10):
            new_state = "BUFFERING"
            new_color = Theme.ACCENT_AMBER
        elif loss_5s >= 2.0 or underruns_5s > 3 or jitter_p95 > target_buf_ms:
            new_state = "DEGRADED"
            new_color = Theme.ACCENT_AMBER
        else:
            new_state = "STREAMING"
            new_color = Theme.ACCENT_EMERALD
            
        if new_state != self.state:
            self.event_feed.log_event("STATE", f"{self.state} ➔ {new_state}", "INFO")
            self.state = new_state
            
        self.readiness_badge.set_state(self.state, new_color)
        buf_ms = self.jitter_buffer.get_level_ms()
        self.diagnostics_panel.update_network_stats(stats_enh, stats_in, buf_stats, buf_ms)
        
        # Update KPI cards
        pct = stats_enh.get('loss_pct', 0.0)
        color = Theme.ACCENT_EMERALD if pct < 1.0 else (Theme.ACCENT_AMBER if pct < 5.0 else Theme.ACCENT_ROSE)
        recv = stats_enh.get('received', 0)
        lost = stats_enh.get('lost', 0)
        self.kpi_loss.set_value(f"{pct:.2f}%", color, f"{lost} lost / {recv:,} recv")
        
        target_ms = self.cfg.get('buffer_ms', 60.0)
        self.kpi_buf.set_value(f"{buf_ms:.1f} ms", Theme.ACCENT_EMERALD if buf_ms <= target_ms * 1.5 else Theme.ACCENT_AMBER, f"Target: {target_ms:.1f} ms (Zero Disk I/O)")
        
        # Check input receiver status if port 5007 is idle
        if not self.input_receiver.is_connected:
            self.wave_input.set_active_status(
                is_active=False,
                is_available=False,
                custom_msg="PORT 5007 IDLE"
            )
            
        # Update pipeline widget status
        self.diagnostics_panel.pipeline_widget.update_pipeline(
            net_connected=self.enhanced_receiver.is_connected,
            telemetry=self.telemetry_receiver.latest_data
        )

    def _toggle_mute(self):
        muted = self.btn_mute.isChecked()
        self.playback.set_muted(muted)
        if muted:
            self.btn_mute.setText("🔇 AUDIO MUTED")
            self.event_feed.log_event("AUDIO", "Playback muted by user", "WARN")
        else:
            self.btn_mute.setText("🔊 AUDIO ON")
            self.event_feed.log_event("AUDIO", "Playback unmuted by user", "INFO")

    def _on_device_changed(self, index: int):
        device_id = self.combo_device.currentData()
        device_name = self.combo_device.currentText()
        if self.playback.is_playing:
            self.playback.stop()
            self.playback.start(device=device_id)
            self.event_feed.log_event("AUDIO", f"Audio device changed to: {device_name}", "INFO")

    def resizeEvent(self, event):
        """Responsive reflow when window width changes."""
        super().resizeEvent(event)
        w = event.size().width()
        if w < 1180:
            if self.wave_layout.direction() != QVBoxLayout.Direction.TopToBottom:
                self.wave_layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        else:
            if self.wave_layout.direction() != QHBoxLayout.Direction.LeftToRight:
                self.wave_layout.setDirection(QHBoxLayout.Direction.LeftToRight)

    def closeEvent(self, event):
        """Clean resource shutdown on window close."""
        self.ui_timer.stop()
        self.playback.stop()
        self.enhanced_receiver.stop()
        self.input_receiver.stop()
        self.telemetry_receiver.stop()
        event.accept()
