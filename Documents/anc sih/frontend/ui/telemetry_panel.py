from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QGroupBox, QScrollArea, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

class TelemetryPanel(QFrame):
    """
    Right-side telemetry and device status panel.
    Displays authoritative Pi telemetry if sent over UDP port 5006,
    or clearly displays 'N/A — telemetry unavailable' when offline.
    Calculates local stream and buffer statistics deterministically.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        self.setFixedWidth(360)
        self.setStyleSheet("""
            TelemetryPanel {
                background-color: #0F141D;
                border: 1px solid #1E293B;
                border-radius: 6px;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                color: #94A3B8;
                border: 1px solid #1E293B;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                background-color: #0F141D;
            }
            QLabel {
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)
        
        title_label = QLabel("SYSTEM TELEMETRY")
        title_label.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #38BDF8; letter-spacing: 1.5px;")
        main_layout.addWidget(title_label)
        
        # 1. Edge Device Group
        edge_group = QGroupBox("EDGE DEVICE & HARDWARE")
        edge_layout = QGridLayout(edge_group)
        edge_layout.setVerticalSpacing(4)
        
        edge_layout.addWidget(self._create_name_label("Hardware:"), 0, 0)
        self.lbl_edge_hw = self._create_val_label("Raspberry Pi 5")
        edge_layout.addWidget(self.lbl_edge_hw, 0, 1)
        
        edge_layout.addWidget(self._create_name_label("Status:"), 1, 0)
        self.lbl_edge_status = self._create_status_label("DISCONNECTED", "#64748B")
        edge_layout.addWidget(self.lbl_edge_status, 1, 1)
        
        main_layout.addWidget(edge_group)
        
        # 2. Bluetooth Group
        bt_group = QGroupBox("BLUETOOTH AUDIO SOURCE")
        bt_layout = QGridLayout(bt_group)
        bt_layout.setVerticalSpacing(4)
        
        bt_layout.addWidget(self._create_name_label("Profile:"), 0, 0)
        bt_layout.addWidget(self._create_val_label("HFP (Mono 16kHz)"), 0, 1)
        
        bt_layout.addWidget(self._create_name_label("Device:"), 1, 0)
        self.lbl_bt_device = self._create_val_label("N/A")
        bt_layout.addWidget(self.lbl_bt_device, 1, 1)

        bt_layout.addWidget(self._create_name_label("Status:"), 2, 0)
        self.lbl_bt_status = self._create_status_label("N/A — telemetry unavailable", "#64748B")
        bt_layout.addWidget(self.lbl_bt_status, 2, 1)
        
        main_layout.addWidget(bt_group)
        
        # 3. AI Model Group
        ai_group = QGroupBox("AI ENHANCEMENT ENGINE")
        ai_layout = QGridLayout(ai_group)
        ai_layout.setVerticalSpacing(4)
        
        ai_layout.addWidget(self._create_name_label("Model:"), 0, 0)
        self.lbl_model_name = self._create_val_label("N/A")
        ai_layout.addWidget(self.lbl_model_name, 0, 1)
        
        ai_layout.addWidget(self._create_name_label("Backend:"), 1, 0)
        self.lbl_model_backend = self._create_val_label("N/A")
        ai_layout.addWidget(self.lbl_model_backend, 1, 1)

        ai_layout.addWidget(self._create_name_label("Model SHA:"), 2, 0)
        self.lbl_model_sha = self._create_val_label("N/A")
        ai_layout.addWidget(self.lbl_model_sha, 2, 1)
        
        ai_layout.addWidget(self._create_name_label("AI Engine:"), 3, 0)
        self.lbl_ai_status = self._create_status_label("N/A — telemetry unavailable", "#64748B")
        ai_layout.addWidget(self.lbl_ai_status, 3, 1)
        
        main_layout.addWidget(ai_group)
        
        # 4. Processing Latency Group (Pi Authoritative)
        proc_group = QGroupBox("PROCESSING LATENCY (PI)")
        proc_layout = QGridLayout(proc_group)
        proc_layout.setVerticalSpacing(4)
        
        proc_layout.addWidget(self._create_name_label("Current Frame:"), 0, 0)
        self.lbl_lat_curr = self._create_val_label("N/A — telemetry unavailable")
        proc_layout.addWidget(self.lbl_lat_curr, 0, 1)
        
        proc_layout.addWidget(self._create_name_label("Median Latency:"), 1, 0)
        self.lbl_lat_med = self._create_val_label("N/A — telemetry unavailable")
        proc_layout.addWidget(self.lbl_lat_med, 1, 1)
        
        proc_layout.addWidget(self._create_name_label("P95 Latency:"), 2, 0)
        self.lbl_lat_p95 = self._create_val_label("N/A — telemetry unavailable")
        proc_layout.addWidget(self.lbl_lat_p95, 2, 1)

        proc_layout.addWidget(self._create_name_label("P99 Latency:"), 3, 0)
        self.lbl_lat_p99 = self._create_val_label("N/A — telemetry unavailable")
        proc_layout.addWidget(self.lbl_lat_p99, 3, 1)
        
        proc_layout.addWidget(self._create_name_label("Max Latency:"), 4, 0)
        self.lbl_lat_max = self._create_val_label("N/A — telemetry unavailable")
        proc_layout.addWidget(self.lbl_lat_max, 4, 1)
        
        main_layout.addWidget(proc_group)
        
        # 5. Network Stream Group (PC Calculated)
        net_group = QGroupBox("NETWORK UDP STREAM (PC)")
        net_layout = QGridLayout(net_group)
        net_layout.setVerticalSpacing(4)
        
        net_layout.addWidget(self._create_name_label("Frames Recv:"), 0, 0)
        self.lbl_stream_recv = self._create_val_label("0")
        net_layout.addWidget(self.lbl_stream_recv, 0, 1)
        
        net_layout.addWidget(self._create_name_label("Frames Lost:"), 1, 0)
        self.lbl_stream_lost = self._create_val_label("0")
        net_layout.addWidget(self.lbl_stream_lost, 1, 1)
        
        net_layout.addWidget(self._create_name_label("Packet Loss %:"), 2, 0)
        self.lbl_stream_pct = self._create_val_label("0.00%")
        net_layout.addWidget(self.lbl_stream_pct, 2, 1)
        
        net_layout.addWidget(self._create_name_label("Sequence Errors:"), 3, 0)
        self.lbl_stream_seqerr = self._create_val_label("0")
        net_layout.addWidget(self.lbl_stream_seqerr, 3, 1)
        
        net_layout.addWidget(self._create_name_label("Jitter Buffer:"), 4, 0)
        self.lbl_stream_buf = self._create_val_label("0.0 ms")
        net_layout.addWidget(self.lbl_stream_buf, 4, 1)

        net_layout.addWidget(self._create_name_label("Jitter Underruns:"), 5, 0)
        self.lbl_jitter_underrun = self._create_val_label("0")
        net_layout.addWidget(self.lbl_jitter_underrun, 5, 1)
        
        net_layout.addWidget(self._create_name_label("Duration:"), 6, 0)
        self.lbl_stream_dur = self._create_val_label("00:00:00")
        net_layout.addWidget(self.lbl_stream_dur, 6, 1)
        
        main_layout.addWidget(net_group)
        
        # 6. Thermal & State Group
        diag_group = QGroupBox("THERMAL & STATE HEALTH")
        diag_layout = QGridLayout(diag_group)
        diag_layout.setVerticalSpacing(4)
        
        diag_layout.addWidget(self._create_name_label("Pi Temp:"), 0, 0)
        self.lbl_pi_temp = self._create_val_label("N/A — telemetry unavailable")
        diag_layout.addWidget(self.lbl_pi_temp, 0, 1)
        
        diag_layout.addWidget(self._create_name_label("State Resets:"), 1, 0)
        self.lbl_state_resets = self._create_val_label("N/A — telemetry unavailable")
        diag_layout.addWidget(self.lbl_state_resets, 1, 1)
        
        diag_layout.addWidget(self._create_name_label("NaN/Inf Events:"), 2, 0)
        self.lbl_nan_events = self._create_val_label("N/A — telemetry unavailable")
        diag_layout.addWidget(self.lbl_nan_events, 2, 1)

        diag_layout.addWidget(self._create_name_label("Capture Underruns:"), 3, 0)
        self.lbl_cap_underrun = self._create_val_label("N/A — telemetry unavailable")
        diag_layout.addWidget(self.lbl_cap_underrun, 3, 1)

        diag_layout.addWidget(self._create_name_label("Throttle / Cooler:"), 4, 0)
        self.lbl_throttle = self._create_val_label("N/A — telemetry unavailable")
        diag_layout.addWidget(self.lbl_throttle, 4, 1)

        diag_layout.addWidget(self._create_name_label("Diag Mode:"), 5, 0)
        self.lbl_diag_mode = self._create_val_label("N/A")
        diag_layout.addWidget(self.lbl_diag_mode, 5, 1)
        
        main_layout.addWidget(diag_group)
        main_layout.addStretch()

    def _create_name_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #64748B;")
        return lbl
        
    def _create_val_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #F8FAFC;")
        return lbl

    def _create_status_label(self, text: str, color_hex: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color_hex}; font-weight: bold;")
        return lbl

    def update_network_stats(self, stats: dict, buffer_ms: float):
        """Update PC-calculated network stream telemetry."""
        self.lbl_stream_recv.setText(f"{stats.get('received', 0):,}")
        self.lbl_stream_lost.setText(f"{stats.get('lost', 0):,}")
        
        pct = stats.get('loss_pct', 0.0)
        self.lbl_stream_pct.setText(f"{pct:.2f}%")
        if pct > 5.0:
            self.lbl_stream_pct.setStyleSheet("color: #EF4444;") # Red high loss
        elif pct > 1.0:
            self.lbl_stream_pct.setStyleSheet("color: #F59E0B;") # Amber
        else:
            self.lbl_stream_pct.setStyleSheet("color: #10B981;") # Green low loss
            
        seq_err = stats.get('out_of_order', 0) + stats.get('duplicates', 0)
        self.lbl_stream_seqerr.setText(str(seq_err))
        
        self.lbl_stream_buf.setText(f"{buffer_ms:.1f} ms")
        self.lbl_jitter_underrun.setText(str(int(stats.get("jitter_underruns", 0))))
        
        dur_sec = int(stats.get('duration_sec', 0))
        hrs = dur_sec // 3600
        mins = (dur_sec % 3600) // 60
        secs = dur_sec % 60
        self.lbl_stream_dur.setText(f"{hrs:02d}:{mins:02d}:{secs:02d}")
        
        conn = stats.get('connected', False)
        if conn:
            self.lbl_edge_status.setText("CONNECTED")
            self.lbl_edge_status.setStyleSheet("color: #10B981;")
        else:
            self.lbl_edge_status.setText("DISCONNECTED")
            self.lbl_edge_status.setStyleSheet("color: #EF4444;")

    def update_telemetry(self, data: dict):
        """Update Pi telemetry when JSON packet arrives on Port 5006."""
        if not data:
            self.reset_pi_telemetry()
            return

        if 'bluetooth_connected' in data:
            bt_conn = data['bluetooth_connected']
            self.lbl_bt_status.setText("CONNECTED" if bt_conn else "DISCONNECTED")
            self.lbl_bt_status.setStyleSheet("color: #10B981;" if bt_conn else "color: #EF4444;")
            
        if 'model_active' in data:
            ai_act = data['model_active']
            self.lbl_ai_status.setText("ACTIVE" if ai_act else "INACTIVE")
            self.lbl_ai_status.setStyleSheet("color: #10B981;" if ai_act else "color: #EF4444;")

        if 'model' in data:
            self.lbl_model_name.setText(str(data['model']))
        else:
            self.lbl_model_name.setText("N/A")

        if 'backend' in data:
            self.lbl_model_backend.setText(str(data['backend']))
        else:
            self.lbl_model_backend.setText("N/A")

        if 'model_sha' in data:
            sha = str(data['model_sha'])
            self.lbl_model_sha.setText(sha[:16] + "..." if len(sha) > 16 else sha)
        else:
            self.lbl_model_sha.setText("N/A")

        if 'latency_ms' in data:
            self.lbl_lat_curr.setText(f"{data['latency_ms']:.2f} ms")
        if 'latency_median_ms' in data:
            self.lbl_lat_med.setText(f"{data['latency_median_ms']:.2f} ms")
        if 'latency_p95_ms' in data:
            self.lbl_lat_p95.setText(f"{data['latency_p95_ms']:.2f} ms")
        if 'latency_max_ms' in data:
            self.lbl_lat_max.setText(f"{data['latency_max_ms']:.2f} ms")
            
        if 'temperature_c' in data:
            self.lbl_pi_temp.setText(f"{data['temperature_c']:.1f} °C")
            
        if 'state_resets' in data:
            self.lbl_state_resets.setText(str(data['state_resets']))
            
        if 'nan_inf_events' in data:
            self.lbl_nan_events.setText(str(data['nan_inf_events']))

    def reset_pi_telemetry(self):
        """Reset telemetry indicators to 'N/A — telemetry unavailable' when channel is offline."""
        self.lbl_bt_status.setText("N/A — telemetry unavailable")
        self.lbl_bt_status.setStyleSheet("color: #64748B;")
        self.lbl_ai_status.setText("N/A — telemetry unavailable")
        self.lbl_ai_status.setStyleSheet("color: #64748B;")
        self.lbl_model_name.setText("N/A")
        self.lbl_model_backend.setText("N/A")
        self.lbl_model_sha.setText("N/A")
        
        self.lbl_lat_curr.setText("N/A — telemetry unavailable")
        self.lbl_lat_med.setText("N/A — telemetry unavailable")
        self.lbl_lat_p95.setText("N/A — telemetry unavailable")
        self.lbl_lat_max.setText("N/A — telemetry unavailable")
        self.lbl_pi_temp.setText("N/A — telemetry unavailable")
        self.lbl_state_resets.setText("N/A — telemetry unavailable")
        self.lbl_nan_events.setText("N/A — telemetry unavailable")
