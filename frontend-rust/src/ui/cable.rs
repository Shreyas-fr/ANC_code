//! Acoustic Transducer Impedance & Cable Continuity Fault Diagnostics Widget.
//!
//! Developed for SIH 26052 Tactical Military Audio HUD.
//!
//! Visualizes real-time physical electrical and acoustic cable integrity:
//! - Transducer dynamic load impedance in Ohms (Nominal 2.2 kΩ).
//! - Overall cable health progress bar (0% to 100%).
//! - Real-time inter-channel transfer function coherence (0.0 to 1.0).
//! - DC bias leakage / phantom power drift (mV).
//! - Mechanical micro-intermittent contact bounce (fault counter).
//! - Continuous integrity sparkline.

use crate::ui::theme::Theme;
pub use anc_rust::metrics::cable::{CableFaultStatus, CableTelemetry};
use eframe::egui::{self, Color32, Frame, Margin, Pos2, Rect, Rounding, Stroke, Ui, Vec2};

/// Interactive Cable Diagnostics & Continuity HUD Widget.
#[derive(Debug, Clone)]
pub struct CableDiagnosticWidget {
    pub telemetry: CableTelemetry,
    health_history: [f32; 48],
    history_idx: usize,
}

impl Default for CableDiagnosticWidget {
    fn default() -> Self {
        Self {
            telemetry: CableTelemetry {
                health_pct: 100.0,
                estimated_impedance_ohms: 2200.0,
                low_freq_coherence: 1.0,
                dc_offset_mv: 0.0,
                micro_intermittent_events: 0,
                status: CableFaultStatus::Nominal,
            },
            health_history: [100.0; 48],
            history_idx: 0,
        }
    }
}

impl CableDiagnosticWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal telemetry and records historical health trend.
    pub fn update(&mut self, telem: CableTelemetry) {
        self.telemetry = telem;
        self.health_history[self.history_idx] = telem.health_pct;
        self.history_idx = (self.history_idx + 1) % self.health_history.len();
    }

    /// Renders the Transducer Impedance & Cable Continuity Widget.
    pub fn show(&mut self, ui: &mut Ui, height: f32) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Header
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("⚡")
                            .color(Theme::ACCENT_AMBER)
                            .size(13.0),
                    );
                    ui.label(
                        egui::RichText::new("TRANSDUCER & CABLE CONTINUITY")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (status_text, status_col) = match self.telemetry.status {
                            CableFaultStatus::Nominal => ("NOMINAL", Theme::ACCENT_GREEN),
                            CableFaultStatus::MicroIntermittent => {
                                ("FAULT: CONTACT BOUNCE", Theme::ACCENT_AMBER)
                            }
                            CableFaultStatus::HighImpedanceFray => {
                                ("WARN: CABLE FRAY", Theme::ACCENT_AMBER)
                            }
                            CableFaultStatus::OpenCircuit => {
                                ("CRITICAL: OPEN CIRCUIT", Theme::ACCENT_RED)
                            }
                            CableFaultStatus::ShortCircuit => {
                                ("CRITICAL: SHORT CIRCUIT", Theme::ACCENT_RED)
                            }
                        };

                        ui.label(
                            egui::RichText::new(status_text)
                                .size(10.0)
                                .strong()
                                .monospace()
                                .color(status_col),
                        );
                    });
                });

                ui.add_space(6.0);

                // Health Progress Bar
                let health = self.telemetry.health_pct.clamp(0.0, 100.0);
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("INTEGRITY:")
                            .size(9.5)
                            .color(Theme::TEXT_MUTED),
                    );
                    let (bar_col, _) = if health > 80.0 {
                        (Theme::ACCENT_GREEN, "EXCELLENT")
                    } else if health > 50.0 {
                        (Theme::ACCENT_AMBER, "DEGRADED")
                    } else {
                        (Theme::ACCENT_RED, "CRITICAL")
                    };

                    let bar_w = ui.available_width() - 55.0;
                    let (bar_rect, _) = ui.allocate_exact_size(
                        Vec2::new(bar_w.max(50.0), 10.0),
                        egui::Sense::hover(),
                    );
                    let painter = ui.painter_at(bar_rect);

                    // Background track
                    painter.rect_filled(bar_rect, Rounding::same(3.0), Color32::from_gray(25));
                    // Filled health progress
                    let fill_w = bar_rect.width() * (health / 100.0);
                    let fill_rect =
                        Rect::from_min_size(bar_rect.min, Vec2::new(fill_w, bar_rect.height()));
                    painter.rect_filled(fill_rect, Rounding::same(3.0), bar_col);

                    ui.label(
                        egui::RichText::new(format!("{:.0}%", health))
                            .size(9.5)
                            .strong()
                            .color(bar_col),
                    );
                });

                ui.add_space(4.0);

                // Key Electrical & Physical Metrics
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("IMPEDANCE:")
                            .size(9.5)
                            .color(Theme::TEXT_MUTED),
                    );
                    let z = self.telemetry.estimated_impedance_ohms;
                    let z_col = if z > 1500.0 && z < 3500.0 {
                        Theme::ACCENT_CYAN
                    } else if z <= 500.0 || z >= 25000.0 {
                        Theme::ACCENT_RED
                    } else {
                        Theme::ACCENT_AMBER
                    };
                    ui.label(
                        egui::RichText::new(format!("{:.0} Ω", z))
                            .size(9.5)
                            .strong()
                            .color(z_col),
                    );

                    ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));

                    ui.label(
                        egui::RichText::new("COHERENCE:")
                            .size(9.5)
                            .color(Theme::TEXT_MUTED),
                    );
                    let coh = self.telemetry.low_freq_coherence;
                    let coh_col = if coh > 0.70 {
                        Theme::ACCENT_GREEN
                    } else {
                        Theme::ACCENT_AMBER
                    };
                    ui.label(
                        egui::RichText::new(format!("{:.2}", coh))
                            .size(9.5)
                            .strong()
                            .color(coh_col),
                    );

                    ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));

                    ui.label(
                        egui::RichText::new("DC BIAS:")
                            .size(9.5)
                            .color(Theme::TEXT_MUTED),
                    );
                    ui.label(
                        egui::RichText::new(format!("{:.1} mV", self.telemetry.dc_offset_mv))
                            .size(9.5)
                            .color(Theme::TEXT_SECONDARY),
                    );

                    ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));

                    ui.label(
                        egui::RichText::new("FAULTS:")
                            .size(9.5)
                            .color(Theme::TEXT_MUTED),
                    );
                    let fault_count = self.telemetry.micro_intermittent_events;
                    let fault_col = if fault_count == 0 {
                        Theme::TEXT_MUTED
                    } else {
                        Theme::ACCENT_AMBER
                    };
                    ui.label(
                        egui::RichText::new(format!("{}", fault_count))
                            .size(9.5)
                            .strong()
                            .color(fault_col),
                    );
                });

                ui.add_space(4.0);

                // Historical Sparkline
                let spark_h = (height - 50.0).max(24.0);
                let (spark_rect, _) = ui.allocate_exact_size(
                    Vec2::new(ui.available_width(), spark_h),
                    egui::Sense::hover(),
                );
                let painter = ui.painter_at(spark_rect);

                // Background
                painter.rect_filled(spark_rect, Rounding::same(3.0), Color32::from_gray(18));

                let n = self.health_history.len();
                let dx = spark_rect.width() / (n - 1) as f32;

                let mut pts = Vec::with_capacity(n);
                for i in 0..n {
                    let idx = (self.history_idx + i) % n;
                    let val = self.health_history[idx].clamp(0.0, 100.0);
                    let x = spark_rect.min.x + i as f32 * dx;
                    let y = spark_rect.max.y - (val / 100.0) * (spark_rect.height() - 4.0) - 2.0;
                    pts.push(Pos2::new(x, y));
                }

                for i in 0..(n - 1) {
                    painter.line_segment(
                        [pts[i], pts[i + 1]],
                        Stroke::new(1.2_f32, Theme::ACCENT_CYAN),
                    );
                }
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cable_widget_initialization() {
        let widget = CableDiagnosticWidget::new();
        assert_eq!(widget.telemetry.status, CableFaultStatus::Nominal);
        assert_eq!(widget.telemetry.health_pct, 100.0);
        assert_eq!(widget.telemetry.estimated_impedance_ohms, 2200.0);
    }

    #[test]
    fn test_cable_widget_update() {
        let mut widget = CableDiagnosticWidget::new();
        let telem = CableTelemetry {
            health_pct: 55.0,
            estimated_impedance_ohms: 6500.0,
            low_freq_coherence: 0.35,
            dc_offset_mv: 12.5,
            micro_intermittent_events: 3,
            status: CableFaultStatus::MicroIntermittent,
        };

        widget.update(telem);
        assert_eq!(widget.telemetry.status, CableFaultStatus::MicroIntermittent);
        assert_eq!(widget.telemetry.micro_intermittent_events, 3);
        assert_eq!(widget.telemetry.health_pct, 55.0);
    }
}
