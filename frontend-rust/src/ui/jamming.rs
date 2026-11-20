//! Tactical RF Jamming & Link Degradation Diagnostics Widget.
//!
//! Developed for SIH 26052 Tactical Military Audio HUD.
//!
//! Visualizes real-time EW (Electronic Warfare) RF status and link health:
//! - RF jamming classification: Nominal RF, Spot Jamming, Barrage Jamming, Sweep Jamming.
//! - Jamming classification confidence & threat level.
//! - Network Jitter Variance \sigma^2_J in ms^2.
//! - Burst packet loss clustering factor.
//! - Tactical remediation action: 4-bit ADPCM Fallback & Max FEC parity redundancy.

use eframe::egui::{self, Color32, Frame, Margin, Rect, Rounding, Stroke, Ui, Vec2};
use crate::ui::theme::Theme;
pub use anc_rust::network::jamming::{JammingDetectorConfig, JammingRemediation, JammingTelemetry, JammingType};

/// Interactive Jamming & Link Diagnostics HUD Widget.
#[derive(Debug, Clone)]
pub struct JammingWidget {
    pub telemetry: JammingTelemetry,
    history_loss: [f32; 32],
    history_idx: usize,
}

impl Default for JammingWidget {
    fn default() -> Self {
        Self {
            telemetry: JammingTelemetry::default(),
            history_loss: [0.0; 32],
            history_idx: 0,
        }
    }
}

impl JammingWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal telemetry and records loss trend.
    pub fn update(&mut self, telem: JammingTelemetry) {
        self.telemetry = telem;
        self.history_loss[self.history_idx] = telem.packet_loss_rate;
        self.history_idx = (self.history_idx + 1) % self.history_loss.len();
    }

    /// Renders the Jamming & RF Link Diagnostics HUD Widget.
    pub fn show(&mut self, ui: &mut Ui, _height: f32) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Header
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("📡").color(Theme::ACCENT_AMBER).size(13.0));
                    ui.label(
                        egui::RichText::new("TACTICAL RF & EW LINK HEALTH")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (badge_text, badge_color) = match self.telemetry.jamming_type {
                            JammingType::NominalRF => ("NOMINAL RF LINK", Theme::ACCENT_GREEN),
                            JammingType::SpotJamming => ("EW: SPOT JAMMING DETECTED", Theme::ACCENT_AMBER),
                            JammingType::BarrageJamming => ("EW: BARRAGE JAMMING ACTIVE", Theme::ACCENT_RED),
                            JammingType::SweepJamming => ("EW: SWEEP CHIRP JAMMING", Theme::ACCENT_RED),
                        };

                        ui.label(
                            egui::RichText::new(badge_text)
                                .size(10.0)
                                .strong()
                                .monospace()
                                .color(badge_color),
                        );
                    });
                });

                ui.add_space(6.0);

                // Row 1: Loss Rate & Jitter Variance
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("PACKET LOSS:").size(9.5).color(Theme::TEXT_MUTED));
                    let loss_pct = self.telemetry.packet_loss_rate * 100.0;
                    let loss_col = if loss_pct < 1.0 {
                        Theme::ACCENT_GREEN
                    } else if loss_pct < 10.0 {
                        Theme::ACCENT_AMBER
                    } else {
                        Theme::ACCENT_RED
                    };
                    ui.label(
                        egui::RichText::new(format!("{:>4.1}%", loss_pct))
                            .size(11.0)
                            .strong()
                            .monospace()
                            .color(loss_col),
                    );

                    ui.add_space(10.0);
                    ui.label(egui::RichText::new("JITTER VAR:").size(9.5).color(Theme::TEXT_MUTED));
                    let j_col = if self.telemetry.jitter_variance_ms2 < 5.0 {
                        Theme::TEXT_PRIMARY
                    } else if self.telemetry.jitter_variance_ms2 < 15.0 {
                        Theme::ACCENT_AMBER
                    } else {
                        Theme::ACCENT_RED
                    };
                    ui.label(
                        egui::RichText::new(format!("{:>5.1} ms²", self.telemetry.jitter_variance_ms2))
                            .size(11.0)
                            .strong()
                            .monospace()
                            .color(j_col),
                    );

                    ui.add_space(10.0);
                    ui.label(egui::RichText::new("BURST CLUSTERING:").size(9.5).color(Theme::TEXT_MUTED));
                    ui.label(
                        egui::RichText::new(format!("{:.2}", self.telemetry.burst_clustering))
                            .size(11.0)
                            .monospace()
                            .color(Theme::TEXT_PRIMARY),
                    );
                });

                ui.add_space(4.0);

                // Row 2: Tactical Remediation Action
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("REMEDIATION:").size(9.5).color(Theme::TEXT_MUTED));
                    let (rem_text, rem_col) = if self.telemetry.remediation_active {
                        ("ENGAGED: 4-BIT ADPCM + 100% FEC PARITY", Theme::ACCENT_CYAN)
                    } else {
                        ("STANDBY / FULL PCM 16-BIT", Theme::TEXT_MUTED)
                    };
                    ui.label(
                        egui::RichText::new(rem_text)
                            .size(10.0)
                            .strong()
                            .monospace()
                            .color(rem_col),
                    );

                    ui.add_space(10.0);
                    ui.label(egui::RichText::new("CONFIDENCE:").size(9.5).color(Theme::TEXT_MUTED));
                    ui.label(
                        egui::RichText::new(format!("{:.0}%", self.telemetry.confidence * 100.0))
                            .size(10.0)
                            .monospace()
                            .color(Theme::TEXT_PRIMARY),
                    );
                });

                ui.add_space(4.0);

                // Mini sparkline for packet loss history
                let bar_width = 240.0_f32;
                let bar_height = 4.0_f32;
                let (bar_rect, _) = ui.allocate_exact_size(Vec2::new(bar_width, bar_height), egui::Sense::hover());
                let bar_painter = ui.painter_at(bar_rect);
                bar_painter.rect_filled(bar_rect, Rounding::same(2.0), Color32::from_rgb(26, 32, 44));
                let loss_norm = (self.telemetry.packet_loss_rate * 5.0).clamp(0.0, 1.0);
                let fill_rect = Rect::from_min_size(
                    bar_rect.min,
                    Vec2::new(bar_width * loss_norm, bar_height),
                );
                let fill_color = if loss_norm < 0.1 {
                    Theme::ACCENT_GREEN
                } else if loss_norm < 0.4 {
                    Theme::ACCENT_AMBER
                } else {
                    Theme::ACCENT_RED
                };
                bar_painter.rect_filled(fill_rect, Rounding::same(2.0), fill_color);
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jamming_widget_initialization() {
        let widget = JammingWidget::new();
        assert_eq!(widget.telemetry.jamming_type, JammingType::NominalRF);
        assert_eq!(widget.telemetry.packet_loss_rate, 0.0);
        assert!(!widget.telemetry.remediation_active);
    }

    #[test]
    fn test_jamming_widget_update() {
        let mut widget = JammingWidget::new();
        let telem = JammingTelemetry {
            jamming_type: JammingType::BarrageJamming,
            confidence: 0.95,
            jitter_variance_ms2: 24.5,
            mean_jitter_ms: 12.0,
            packet_loss_rate: 0.35,
            burst_clustering: 0.65,
            auth_failure_rate: 0.0,
            remediation_active: true,
            remediation_code: 1,
        };
        widget.update(telem);
        assert_eq!(widget.telemetry.jamming_type, JammingType::BarrageJamming);
        assert!(widget.telemetry.remediation_active);
        assert_eq!(widget.history_loss[0], 0.35);
    }

    #[test]
    fn test_jamming_widget_headless_context() {
        let mut widget = JammingWidget::new();
        let ctx = egui::Context::default();
        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                widget.show(ui, 75.0);
            });
        });
    }
}
