"""
Diagnostics and Engineering Panels for SIH 2026 PS 26052 Edge-AI Audio Mission Control.
Presents Edge AI metadata, network synchronization diagnostics, and system health in clean collapsible sections.
"""

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from frontend.ui.theme import Theme
from frontend.ui.components import CollapsibleSection
from frontend.ui.pipeline_widget import PipelineWidget


class DiagnosticsPanel(QWidget):
    """
    Comprehensive diagnostics and telemetry container.
    Organized into 4 clean collapsible engineering sections:
      1. Edge Device & AI Engine
      2. Network & Stream Diagnostics
      3. System Health & Fail-Safe Status
      4. Signal Processing Pipeline
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # -------------------------------------------------------------
        # Section 1: EDGE DEVICE & AI ENGINE
        # -------------------------------------------------------------
        self.sec_edge = CollapsibleSection("EDGE DEVICE & AI ENGINE", badge_text="HARDWARE & AI", is_expanded=True)
        edge_content = QWidget()
        edge_grid = QGridLayout(edge_content)
        edge_grid.setContentsMargins(4, 4, 4, 4)
        edge_grid.setHorizontalSpacing(24)
        edge_grid.setVerticalSpacing(8)

        # Row 0
        edge_grid.addWidget(self._make_label("Edge Hardware:"), 0, 0)
        self.val_edge_hw = self._make_val("Raspberry Pi 5 (BCM2712 Quad-Core)")
        edge_grid.addWidget(self.val_edge_hw, 0, 1)

        edge_grid.addWidget(self._make_label("AI Architecture:"), 0, 2)
        self.val_ai_arch = self._make_val("StatefulPolarLSTM (1,448,962 params)", color=Theme.ACCENT_VIOLET_LIGHT)
        edge_grid.addWidget(self.val_ai_arch, 0, 3)

        # Row 1
        edge_grid.addWidget(self._make_label("Audio Interface:"), 1, 0)
        self.val_audio_iface = self._make_val("Bluetooth HFP (16 kHz Mono)")
        edge_grid.addWidget(self.val_audio_iface, 1, 1)

        edge_grid.addWidget(self._make_label("Inference Backend:"), 1, 2)
        self.val_model_backend = self._make_val("PyTorch / ONNX", color=Theme.TEXT_PRIMARY)
        edge_grid.addWidget(self.val_model_backend, 1, 3)

        # Row 2
        edge_grid.addWidget(self._make_label("Model File:"), 2, 0)
        self.val_model_file = self._make_val("best.pt", color=Theme.TEXT_PRIMARY)
        edge_grid.addWidget(self.val_model_file, 2, 1)

        edge_grid.addWidget(self._make_label("Model SHA-256:"), 2, 2)
        self.val_model_sha = self._make_val("WAITING FOR TELEMETRY", color=Theme.TEXT_MUTED)
        edge_grid.addWidget(self.val_model_sha, 2, 3)

        # Row 3
        edge_grid.addWidget(self._make_label("State Resets:"), 3, 0)
        self.val_state_resets = self._make_val("--", color=Theme.TEXT_MUTED)
        edge_grid.addWidget(self.val_state_resets, 3, 1)

        edge_grid.addWidget(self._make_label("NaN / Inf Events:"), 3, 2)
        self.val_nan_events = self._make_val("--", color=Theme.TEXT_MUTED)
        edge_grid.addWidget(self.val_nan_events, 3, 3)

        self.sec_edge.set_content_widget(edge_content)
        main_layout.addWidget(self.sec_edge)

        # -------------------------------------------------------------
        # Section 2: NETWORK & STREAM SYNCHRONIZATION
        # -------------------------------------------------------------
        self.sec_net = CollapsibleSection("NETWORK & STREAM SYNCHRONIZATION", badge_text="UDP 5005 / 5006 / 5007", is_expanded=True)
        net_content = QWidget()
        net_grid = QGridLayout(net_content)
        net_grid.setContentsMargins(4, 4, 4, 4)
        net_grid.setHorizontalSpacing(24)
        net_grid.setVerticalSpacing(8)

        # Row 0
        net_grid.addWidget(self._make_label("Frames Received:"), 0, 0)
        self.val_net_recv = self._make_val("0")
        net_grid.addWidget(self.val_net_recv, 0, 1)

        net_grid.addWidget(self._make_label("Enhanced Audio Port:"), 0, 2)
        self.val_port_enh = self._make_val("UDP 5005 (1032 B = 8B Seq + 1024B PCM)", color=Theme.ACCENT_CYAN)
        net_grid.addWidget(self.val_port_enh, 0, 3)

        # Row 1
        net_grid.addWidget(self._make_label("Frames Lost:"), 1, 0)
        self.val_net_lost = self._make_val("0")
        net_grid.addWidget(self.val_net_lost, 1, 1)

        net_grid.addWidget(self._make_label("Input Audio Port:"), 1, 2)
        self.val_port_in = self._make_val("UDP 5007 (1032 B = 8B Seq + 1024B PCM)")
        net_grid.addWidget(self.val_port_in, 1, 3)

        # Row 2
        net_grid.addWidget(self._make_label("Packet Loss %:"), 2, 0)
        self.val_net_loss_pct = self._make_val("0.00%", color=Theme.ACCENT_EMERALD)
        net_grid.addWidget(self.val_net_loss_pct, 2, 1)

        net_grid.addWidget(self._make_label("Telemetry Port:"), 2, 2)
        self.val_port_telem = self._make_val("UDP 5006 (JSON Datagrams)")
        net_grid.addWidget(self.val_port_telem, 2, 3)

        # Row 3
        net_grid.addWidget(self._make_label("Sequence Errors:"), 3, 0)
        self.val_net_seq_err = self._make_val("0")
        net_grid.addWidget(self.val_net_seq_err, 3, 1)

        net_grid.addWidget(self._make_label("Stream Duration:"), 3, 2)
        self.val_net_duration = self._make_val("00:00:00")
        net_grid.addWidget(self.val_net_duration, 3, 3)

        self.sec_net.set_content_widget(net_content)
        main_layout.addWidget(self.sec_net)

        # -------------------------------------------------------------
        # Section 3: SYSTEM HEALTH & FAIL-SAFE STATUS
        # -------------------------------------------------------------
        self.sec_health = CollapsibleSection("SYSTEM HEALTH & FAIL-SAFE STATUS", badge_text="WATCHDOG & GUARDS", is_expanded=True)
        health_content = QWidget()
        health_grid = QGridLayout(health_content)
        health_grid.setContentsMargins(4, 4, 4, 4)
        health_grid.setHorizontalSpacing(24)
        health_grid.setVerticalSpacing(8)

        # Row 0
        health_grid.addWidget(self._make_label("Edge Pi Link:"), 0, 0)
        self.val_health_edge = self._make_val("DISCONNECTED", color=Theme.ACCENT_ROSE)
        health_grid.addWidget(self.val_health_edge, 0, 1)

        health_grid.addWidget(self._make_label("Bluetooth Source:"), 0, 2)
        self.val_health_bt = self._make_val("UNAVAILABLE", color=Theme.TEXT_MUTED)
        health_grid.addWidget(self.val_health_bt, 0, 3)

        # Row 1
        health_grid.addWidget(self._make_label("AI Model Engine:"), 1, 0)
        self.val_health_ai = self._make_val("UNAVAILABLE", color=Theme.TEXT_MUTED)
        health_grid.addWidget(self.val_health_ai, 1, 1)

        health_grid.addWidget(self._make_label("PCM Audio Output:"), 1, 2)
        self.val_health_audio = self._make_val("sounddevice Low-Latency Ring", color=Theme.TEXT_PRIMARY)
        health_grid.addWidget(self.val_health_audio, 1, 3)

        # Row 2
        health_grid.addWidget(self._make_label("Fail-Safe Guard:"), 2, 0)
        self.val_health_failsafe = self._make_val("Auto-Mute on >1.0s Packet Loss Timeout", color=Theme.ACCENT_EMERALD)
        health_grid.addWidget(self.val_health_failsafe, 2, 1)

        health_grid.addWidget(self._make_label("Memory Streaming:"), 2, 2)
        self.val_health_mem = self._make_val("Zero Disk I/O (Ring Buffer Only)", color=Theme.ACCENT_EMERALD)
        health_grid.addWidget(self.val_health_mem, 2, 3)

        self.sec_health.set_content_widget(health_content)
        main_layout.addWidget(self.sec_health)

        # -------------------------------------------------------------
        # Section 4: PROCESSING SIGNAL CHAIN
        # -------------------------------------------------------------
        self.sec_pipe = CollapsibleSection("PROCESSING SIGNAL CHAIN", badge_text="SIGNAL FLOW", is_expanded=True)
        self.pipeline_widget = PipelineWidget()
        self.sec_pipe.set_content_widget(self.pipeline_widget)
        main_layout.addWidget(self.sec_pipe)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(Theme.FONT_FAMILY_UI, 8))
        lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        return lbl

    def _make_val(self, text: str, color: str = Theme.TEXT_PRIMARY) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {color};")
        return lbl

    def update_network_stats(self, stats: dict, buffer_ms: float):
        """Update network telemetry from receiver stats."""
        self.val_net_recv.setText(f"{stats.get('received', 0):,}")
        self.val_net_lost.setText(f"{stats.get('lost', 0):,}")

        pct = stats.get('loss_pct', 0.0)
        self.val_net_loss_pct.setText(f"{pct:.2f}%")
        if pct > 5.0:
            self.val_net_loss_pct.setStyleSheet(f"color: {Theme.ACCENT_ROSE};")
        elif pct > 1.0:
            self.val_net_loss_pct.setStyleSheet(f"color: {Theme.ACCENT_AMBER};")
        else:
            self.val_net_loss_pct.setStyleSheet(f"color: {Theme.ACCENT_EMERALD};")

        seq_err = stats.get('out_of_order', 0) + stats.get('duplicates', 0)
        self.val_net_seq_err.setText(str(seq_err))

        dur_sec = int(stats.get('duration_sec', 0))
        hrs = dur_sec // 3600
        mins = (dur_sec % 3600) // 60
        secs = dur_sec % 60
        self.val_net_duration.setText(f"{hrs:02d}:{mins:02d}:{secs:02d}")

        conn = stats.get('connected', False)
        if conn:
            self.val_health_edge.setText("CONNECTED")
            self.val_health_edge.setStyleSheet(f"color: {Theme.ACCENT_EMERALD};")
        else:
            self.val_health_edge.setText("DISCONNECTED")
            self.val_health_edge.setStyleSheet(f"color: {Theme.ACCENT_ROSE};")

    def update_telemetry(self, data: dict):
        """Update Pi telemetry when JSON packet arrives on Port 5006."""
        if not data:
            self.reset_pi_telemetry()
            return

        if 'bluetooth_connected' in data:
            bt = data['bluetooth_connected']
            self.val_health_bt.setText("CONNECTED" if bt else "DISCONNECTED")
            self.val_health_bt.setStyleSheet(f"color: {Theme.ACCENT_EMERALD if bt else Theme.ACCENT_ROSE};")

        if 'model_active' in data:
            ai = data['model_active']
            self.val_health_ai.setText("RUNNING" if ai else "INACTIVE")
            self.val_health_ai.setStyleSheet(f"color: {Theme.ACCENT_EMERALD if ai else Theme.ACCENT_ROSE};")

        if 'backend' in data:
            self.val_model_backend.setText(str(data['backend']))
            self.val_model_backend.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")

        if 'model_sha' in data:
            sha = str(data['model_sha'])
            self.val_model_sha.setText(sha[:16] + "..." if len(sha) > 16 else sha)
            self.val_model_sha.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")
        else:
            self.val_model_sha.setText("WAITING FOR TELEMETRY")
            self.val_model_sha.setStyleSheet(f"color: {Theme.TEXT_MUTED};")

        if 'state_resets' in data:
            self.val_state_resets.setText(str(data['state_resets']))
            self.val_state_resets.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")

        if 'nan_inf_events' in data:
            self.val_nan_events.setText(str(data['nan_inf_events']))
            self.val_nan_events.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")

    def reset_pi_telemetry(self):
        """Reset Pi telemetry when telemetry link is offline."""
        self.val_health_bt.setText("UNAVAILABLE")
        self.val_health_bt.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        self.val_health_ai.setText("UNAVAILABLE")
        self.val_health_ai.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        self.val_model_sha.setText("WAITING FOR TELEMETRY")
        self.val_model_sha.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        self.val_state_resets.setText("--")
        self.val_state_resets.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        self.val_nan_events.setText("--")
        self.val_nan_events.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
