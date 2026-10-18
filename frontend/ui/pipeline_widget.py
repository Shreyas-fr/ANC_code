"""
Processing Pipeline Architecture Diagram for SIH 2026 PS 26052.
Displays end-to-end signal flow:
[MIC] -> [HFP] -> [EDGE PI 5] -> [DFN3] -> [UDP STREAM] -> [OUTPUT]
"""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from frontend.ui.theme import Theme


class PipelineWidget(QFrame):
    """
    Mission-control signal chain architecture visualizer.
    Renders status at each physical and logical stage in real-time.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            PipelineWidget {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 8px;
            }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)
        
        # Header
        header_layout = QHBoxLayout()
        lbl_title = QLabel("SIGNAL PROCESSING CHAIN")
        lbl_title.setFont(QFont(Theme.FONT_FAMILY_UI, 9, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; letter-spacing: 0.6px;")
        header_layout.addWidget(lbl_title)
        
        header_layout.addStretch()
        
        lbl_sub = QLabel("End-to-End Edge-to-Host Pipeline Architecture")
        lbl_sub.setFont(QFont(Theme.FONT_FAMILY_UI, 8))
        lbl_sub.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        header_layout.addWidget(lbl_sub)
        
        main_layout.addLayout(header_layout)
        
        # Stages Flow Container
        flow_layout = QHBoxLayout()
        flow_layout.setContentsMargins(0, 4, 0, 4)
        flow_layout.setSpacing(6)
        
        self.stages = {
            'mic': self._create_stage_item("● MIC", "Microphone Capture", "Raw Analog", is_ai=False),
            'hfp': self._create_stage_item("● HFP", "Bluetooth 16kHz", "mSBC / CVSD", is_ai=False),
            'pi': self._create_stage_item("● EDGE PI 5", "Edge Hardware", "BCM2712 Quad-Core", is_ai=False),
            'ai': self._create_stage_item("● AI ENGINE", "DeepFilterNet3", "ONNX / Rust", is_ai=True),
            'net': self._create_stage_item("● UDP STREAM", "Port 5005 PCM", "1032 B Datagrams", is_ai=False),
            'out': self._create_stage_item("● OUTPUT", "Host Playback", "Low-Latency Ring", is_ai=False)
        }
        
        stage_keys = ['mic', 'hfp', 'pi', 'ai', 'net', 'out']
        for i, k in enumerate(stage_keys):
            flow_layout.addWidget(self.stages[k]['container'], stretch=1)
            if i < len(stage_keys) - 1:
                arr = QLabel("➔")
                arr.setFont(QFont("Arial", 11, QFont.Weight.Bold))
                arr.setStyleSheet(f"color: {Theme.TEXT_DISABLED};")
                arr.setAlignment(Qt.AlignmentFlag.AlignCenter)
                flow_layout.addWidget(arr)
                
        main_layout.addLayout(flow_layout)

    def _create_stage_item(self, tag: str, title: str, subtitle: str, is_ai: bool = False) -> dict:
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_ELEVATED};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)
        l = QVBoxLayout(container)
        l.setContentsMargins(8, 6, 8, 6)
        l.setSpacing(2)
        
        lbl_tag = QLabel(tag)
        lbl_tag.setFont(QFont(Theme.FONT_FAMILY_MONO, 8, QFont.Weight.Bold))
        tag_color = Theme.ACCENT_VIOLET_LIGHT if is_ai else Theme.TEXT_MUTED
        lbl_tag.setStyleSheet(f"color: {tag_color};")
        lbl_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_title = QLabel(title)
        lbl_title.setFont(QFont(Theme.FONT_FAMILY_UI, 8, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_sub = QLabel(subtitle)
        lbl_sub.setFont(QFont(Theme.FONT_FAMILY_UI, 7))
        lbl_sub.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        l.addWidget(lbl_tag)
        l.addWidget(lbl_title)
        l.addWidget(lbl_sub)
        
        return {'container': container, 'tag': lbl_tag, 'title': lbl_title, 'sub': lbl_sub, 'is_ai': is_ai}

    def update_pipeline(self, net_connected: bool, telemetry: dict = None):
        """Update stage status colors based on network and telemetry health."""
        if not net_connected:
            # Disconnected / Offline
            for k in ['mic', 'hfp', 'pi', 'ai', 'net']:
                self.stages[k]['tag'].setStyleSheet(f"color: {Theme.ACCENT_ROSE};")
                self.stages[k]['container'].setStyleSheet(f"""
                    QFrame {{
                        background-color: {Theme.BG_ELEVATED};
                        border: 1px solid {Theme.ACCENT_ROSE};
                        border-radius: 6px;
                    }}
                """)
            self.stages['out']['tag'].setStyleSheet(f"color: {Theme.TEXT_MUTED};")
            self.stages['out']['container'].setStyleSheet(f"""
                QFrame {{
                    background-color: {Theme.BG_ELEVATED};
                    border: 1px solid {Theme.BORDER_SUBTLE};
                    border-radius: 6px;
                }}
            """)
        else:
            # Network connected
            for k in ['pi', 'net', 'out']:
                self.stages[k]['tag'].setStyleSheet(f"color: {Theme.ACCENT_EMERALD};")
                self.stages[k]['container'].setStyleSheet(f"""
                    QFrame {{
                        background-color: {Theme.BG_ELEVATED};
                        border: 1px solid {Theme.ACCENT_EMERALD};
                        border-radius: 6px;
                    }}
                """)
            
            # Check telemetry for mic, hfp, ai
            if telemetry and isinstance(telemetry, dict):
                bt_conn = telemetry.get('bluetooth_connected', True)
                ai_act = telemetry.get('model_active', True)
                
                color_bt = Theme.ACCENT_EMERALD if bt_conn else Theme.ACCENT_ROSE
                color_ai = Theme.ACCENT_VIOLET if ai_act else Theme.ACCENT_ROSE
                
                self.stages['hfp']['tag'].setStyleSheet(f"color: {color_bt};")
                self.stages['hfp']['container'].setStyleSheet(f"""
                    QFrame {{
                        background-color: {Theme.BG_ELEVATED};
                        border: 1px solid {color_bt};
                        border-radius: 6px;
                    }}
                """)
                
                self.stages['mic']['tag'].setStyleSheet(f"color: {color_bt};")
                self.stages['mic']['container'].setStyleSheet(f"""
                    QFrame {{
                        background-color: {Theme.BG_ELEVATED};
                        border: 1px solid {color_bt};
                        border-radius: 6px;
                    }}
                """)
                
                self.stages['ai']['tag'].setStyleSheet(f"color: {color_ai};")
                self.stages['ai']['container'].setStyleSheet(f"""
                    QFrame {{
                        background-color: {Theme.BG_ELEVATED};
                        border: 1px solid {color_ai};
                        border-radius: 6px;
                    }}
                """)
            else:
                for k in ['mic', 'hfp', 'ai']:
                    tag_color = Theme.ACCENT_VIOLET if self.stages[k]['is_ai'] else Theme.ACCENT_EMERALD
                    self.stages[k]['tag'].setStyleSheet(f"color: {tag_color};")
                    self.stages[k]['container'].setStyleSheet(f"""
                        QFrame {{
                            background-color: {Theme.BG_ELEVATED};
                            border: 1px solid {tag_color};
                            border-radius: 6px;
                        }}
                    """)
