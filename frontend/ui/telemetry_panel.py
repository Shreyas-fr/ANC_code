"""
Telemetry and status panel for SIH 2026 PS 26052.
Maintains backward compatibility and provides full diagnostics integration.
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout
from frontend.ui.diagnostics_panel import DiagnosticsPanel


class TelemetryPanel(QFrame):
    """
    Backward-compatible TelemetryPanel wrapping the modern DiagnosticsPanel.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.diagnostics = DiagnosticsPanel(self)
        layout.addWidget(self.diagnostics)

    def update_network_stats(self, stats: dict, buffer_ms: float):
        self.diagnostics.update_network_stats(stats, buffer_ms)

    def update_telemetry(self, data: dict):
        self.diagnostics.update_telemetry(data)

    def reset_pi_telemetry(self):
        self.diagnostics.reset_pi_telemetry()
