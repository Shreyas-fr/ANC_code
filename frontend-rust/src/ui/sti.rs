//! IEC 60268-16 Rapid Speech Transmission Index (RASTI) & STI Gauge Widget.
//!
//! Developed for SIH 26052 Tactical Military Audio HUD.
//!
//! Visualizes real-time objective speech intelligibility:
//! - Objective STI Score (0.00 to 1.00).
//! - IEC 60268-16 Qualification Rating:
//!   - EXCELLENT (> 0.75)
//!   - GOOD (0.60 to 0.75)
//!   - FAIR (0.45 to 0.60)
//!   - POOR (0.30 to 0.45)
//!   - BAD (< 0.30)
//! - Apparent Speech-to-Noise Ratio (dB) derived from Modulation Transfer Function (MTF).
//! - Multi-octave modulation transfer factor bar graph.

use eframe::egui::{self, Color32, Frame, Margin, Rect, Rounding, Stroke, Ui, Vec2};
use crate::ui::theme::Theme;
pub use anc_rust::metrics::sti::{StiRating, StiTelemetry, NUM_RASTI_MOD_FREQS};

/// Interactive RASTI Speech Transmission Index Gauge Widget.
#[derive(Debug, Clone)]
pub struct RastiWidget {
    pub telemetry: StiTelemetry,
    history_sti: [f32; 32],
    history_idx: usize,
}

impl Default for RastiWidget {
    fn default() -> Self {
        Self {
            telemetry: StiTelemetry::default(),
            history_sti: [0.0; 32],
            history_idx: 0,
        }
    }
}

impl RastiWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal telemetry and records historical STI score.
    pub fn update(&mut self, telem: StiTelemetry) {
        self.telemetry = telem;
        self.history_sti[self.history_idx] = telem.sti_score;
        self.history_idx = (self.history_idx + 1) % self.history_sti.len();
    }

    /// Renders the RASTI / STI Intelligibility Gauge HUD Widget.
    pub fn show(&mut self, ui: &mut Ui, _height: f32) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Header
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("🗣").color(Theme::ACCENT_GREEN).size(13.0));
                    ui.label(
                        egui::RichText::new("IEC 60268-16 SPEECH TRANSMISSION INDEX (RASTI)")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (rating_text, rating_col) = match self.telemetry.rating {
                            StiRating::Excellent => ("IEC: EXCELLENT", Theme::ACCENT_CYAN),
                            StiRating::Good => ("IEC: GOOD", Theme::ACCENT_GREEN),
                            StiRating::Fair => ("IEC: FAIR", Theme::ACCENT_AMBER),
                            StiRating::Poor => ("IEC: POOR", Theme::ACCENT_AMBER),
                            StiRating::Bad => ("IEC: UNINTELLIGIBLE", Theme::ACCENT_RED),
                        };

                        ui.label(
                            egui::RichText::new(rating_text)
                                .size(10.0)
                                .strong()
                                .monospace()
                                .color(rating_col),
                        );
                    });
                });

                ui.add_space(6.0);

                // Main STI Score Gauge + Details
                ui.horizontal(|ui| {
                    // Large STI score readout
                    let sti = self.telemetry.sti_score.clamp(0.0, 1.0);
                    let sti_color = match self.telemetry.rating {
                        StiRating::Excellent => Theme::ACCENT_CYAN,
                        StiRating::Good => Theme::ACCENT_GREEN,
                        StiRating::Fair | StiRating::Poor => Theme::ACCENT_AMBER,
                        StiRating::Bad => Theme::ACCENT_RED,
                    };

                    ui.label(
                        egui::RichText::new(format!("{:.2}", sti))
                            .size(24.0)
                            .strong()
                            .monospace()
                            .color(sti_color),
                    );

                    ui.add_space(8.0);

                    ui.vertical(|ui| {
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("APPARENT SNR:").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("{:>+5.1} dB", self.telemetry.mean_apparent_snr_db))
                                    .size(11.0)
                                    .monospace()
                                    .color(Theme::TEXT_PRIMARY),
                            );

                            ui.add_space(10.0);
                            ui.label(egui::RichText::new("MEAN MTF:").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("{:.2}", self.telemetry.mean_mtf))
                                    .size(11.0)
                                    .monospace()
                                    .color(Theme::TEXT_PRIMARY),
                            );
                        });

                        ui.add_space(3.0);

                        // Horizontal STI quality progress bar
                        let bar_width = 180.0_f32;
                        let bar_height = 6.0_f32;
                        let (bar_rect, _) = ui.allocate_exact_size(Vec2::new(bar_width, bar_height), egui::Sense::hover());
                        let bar_painter = ui.painter_at(bar_rect);
                        bar_painter.rect_filled(bar_rect, Rounding::same(3.0), Color32::from_rgb(26, 32, 44));

                        let fill_rect = Rect::from_min_size(
                            bar_rect.min,
                            Vec2::new(bar_width * sti, bar_height),
                        );
                        bar_painter.rect_filled(fill_rect, Rounding::same(3.0), sti_color);
                    });
                });

                ui.add_space(4.0);

                // Modulation Frequency Bars (14 RASTI sub-modulation bands)
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("MTF BANDS:").size(9.0).color(Theme::TEXT_MUTED));
                    for i in 0..NUM_RASTI_MOD_FREQS {
                        let m = self.telemetry.mtf_bands[i].clamp(0.0, 1.0);
                        let bar_w = 6.0_f32;
                        let bar_h = 10.0_f32;
                        let (b_rect, _) = ui.allocate_exact_size(Vec2::new(bar_w, bar_h), egui::Sense::hover());
                        let p = ui.painter_at(b_rect);
                        p.rect_filled(b_rect, Rounding::same(1.0), Color32::from_rgb(26, 32, 44));
                        let f_h = bar_h * m;
                        let f_rect = Rect::from_min_max(
                            egui::pos2(b_rect.min.x, b_rect.max.y - f_h),
                            b_rect.max,
                        );
                        p.rect_filled(f_rect, Rounding::same(1.0), Theme::ACCENT_GREEN);
                    }
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rasti_widget_initialization() {
        let widget = RastiWidget::new();
        assert_eq!(widget.telemetry.sti_score, 0.0);
        assert_eq!(widget.telemetry.rating, StiRating::Bad);
        assert_eq!(widget.history_idx, 0);
    }

    #[test]
    fn test_rasti_widget_update() {
        let mut widget = RastiWidget::new();
        let telem = StiTelemetry {
            sti_score: 0.82,
            rating: StiRating::Excellent,
            mean_apparent_snr_db: 12.5,
            mean_mtf: 0.78,
            mtf_bands: [0.8; NUM_RASTI_MOD_FREQS],
            is_authoritative: true,
        };
        widget.update(telem);
        assert_eq!(widget.telemetry.sti_score, 0.82);
        assert_eq!(widget.telemetry.rating, StiRating::Excellent);
        assert_eq!(widget.history_sti[0], 0.82);
    }

    #[test]
    fn test_rasti_widget_headless_context() {
        let mut widget = RastiWidget::new();
        let ctx = egui::Context::default();
        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                widget.show(ui, 75.0);
            });
        });
    }
}
