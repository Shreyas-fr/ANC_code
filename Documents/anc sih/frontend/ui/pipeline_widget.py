from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class PipelineWidget(QFrame):
    """
    Bottom pipeline status bar showing the complete end-to-end signal chain:
    [MIC] -> [HFP] -> [PI 5] -> [AI ENHANCEMENT] -> [NETWORK] -> [PC OUTPUT]
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        self.setFixedHeight(56)
        self.setStyleSheet("""
            PipelineWidget {
                background-color: #0F141D;
                border: 1px solid #1E293B;
                border-radius: 6px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(12)
        
        # Pipeline Stages
        self.stages = {
            'mic': self._create_stage_item("● MIC", "Microphone"),
            'hfp': self._create_stage_item("● HFP", "Bluetooth HFP"),
            'pi': self._create_stage_item("● PI 5", "Raspberry Pi 5"),
            'ai': self._create_stage_item("● AI", "PolarLSTM AI"),
            'net': self._create_stage_item("● NET", "UDP Network"),
            'out': self._create_stage_item("● OUTPUT", "PC Speakers")
        }
        
        stage_keys = ['mic', 'hfp', 'pi', 'ai', 'net', 'out']
        for i, k in enumerate(stage_keys):
            layout.addWidget(self.stages[k]['container'])
            if i < len(stage_keys) - 1:
                arr = QLabel("➔")
                arr.setFont(QFont("Arial", 12))
                arr.setStyleSheet("color: #475569;")
                layout.addWidget(arr)
                
    def _create_stage_item(self, tag: str, desc: str) -> dict:
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #090D14;
                border: 1px solid #1E293B;
                border-radius: 4px;
                padding: 2px 8px;
            }
        """)
        l = QVBoxLayout(container)
        l.setContentsMargins(4, 2, 4, 2)
        l.setSpacing(0)
        
        lbl_tag = QLabel(tag)
        lbl_tag.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        lbl_tag.setStyleSheet("color: #64748B;")
        
        lbl_desc = QLabel(desc)
        lbl_desc.setFont(QFont("Inter", 8))
        lbl_desc.setStyleSheet("color: #94A3B8;")
        
        l.addWidget(lbl_tag, alignment=Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        
        return {'container': container, 'tag': lbl_tag, 'desc': lbl_desc}

    def update_pipeline(self, net_connected: bool, is_demo: bool = False, telemetry: dict = None):
        """Update stage status colors based on network and telemetry health."""
        if is_demo:
            for k in self.stages:
                self.stages[k]['tag'].setStyleSheet("color: #F59E0B;") # Amber for demo
                self.stages[k]['container'].setStyleSheet("border: 1px solid #F59E0B; background-color: #090D14;")
            self.stages['net']['tag'].setText("● DEMO NET")
            return
            
        self.stages['net']['tag'].setText("● NET")
        
        if not net_connected:
            # Everything upstream is offline/disconnected
            for k in ['mic', 'hfp', 'pi', 'ai', 'net']:
                self.stages[k]['tag'].setStyleSheet("color: #EF4444;") # Red
                self.stages[k]['container'].setStyleSheet("border: 1px solid #EF4444; background-color: #090D14;")
            self.stages['out']['tag'].setStyleSheet("color: #64748B;")
            self.stages['out']['container'].setStyleSheet("border: 1px solid #1E293B; background-color: #090D14;")
        else:
            # Network is connected
            self.stages['net']['tag'].setStyleSheet("color: #10B981;") # Green
            self.stages['net']['container'].setStyleSheet("border: 1px solid #10B981; background-color: #090D14;")
            
            self.stages['out']['tag'].setStyleSheet("color: #10B981;")
            self.stages['out']['container'].setStyleSheet("border: 1px solid #10B981; background-color: #090D14;")
            
            self.stages['pi']['tag'].setStyleSheet("color: #10B981;")
            self.stages['pi']['container'].setStyleSheet("border: 1px solid #10B981; background-color: #090D14;")
            
            # Check telemetry for mic, hfp, ai
            if telemetry and isinstance(telemetry, dict):
                bt_conn = telemetry.get('bluetooth_connected', True)
                ai_act = telemetry.get('model_active', True)
                
                self.stages['hfp']['tag'].setStyleSheet("color: #10B981;" if bt_conn else "color: #EF4444;")
                self.stages['hfp']['container'].setStyleSheet("border: 1px solid #10B981;" if bt_conn else "border: 1px solid #EF4444;")
                
                self.stages['mic']['tag'].setStyleSheet("color: #10B981;" if bt_conn else "color: #EF4444;")
                self.stages['mic']['container'].setStyleSheet("border: 1px solid #10B981;" if bt_conn else "border: 1px solid #EF4444;")
                
                self.stages['ai']['tag'].setStyleSheet("color: #10B981;" if ai_act else "color: #EF4444;")
                self.stages['ai']['container'].setStyleSheet("border: 1px solid #10B981;" if ai_act else "border: 1px solid #EF4444;")
            else:
                # Without telemetry, assume active if stream is receiving
                for k in ['mic', 'hfp', 'ai']:
                    self.stages[k]['tag'].setStyleSheet("color: #10B981;")
                    self.stages[k]['container'].setStyleSheet("border: 1px solid #10B981; background-color: #090D14;")
