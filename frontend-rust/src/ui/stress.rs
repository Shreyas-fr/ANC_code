//! Tactical Cognitive Stress & Soldier Vocal Fatigue HUD Widget.
//!
//! Visualizes real-time acoustic biomarkers of soldier cognitive workload,
//! fear/adrenaline surge, and vocal tract fatigue:
//! - Tactical Cognitive Stress Index Gauge (0% to 100%).
//! - Real-time acoustic biomarker indicators: Vocal Jitter, Vocal Shimmer, Delta F0, and Cadence.
//! - Cumulative vocal fatigue progress bar.
//! - Scrolling stress history sparkline.

use eframe::egui::{self, Color32, Pos2, Rect, Stroke, Ui, Vec2};
use crate::ui::theme::Theme;

/// Rolling history length for the stress sparkline.
const STRESS_HISTORY_LEN: usize = 64;

/// Tactical Cognitive Stress HUD Widget.
pub struct TacticalStressWidget {
    pub stress_index_pct: f32,
    pub jitter_pct: f32,
    pub shimmer_pct: f32,
    pub pitch_elevation_hz: f32,
    pub speaking_rate_sps: f32,
    pub vocal_fatigue_pct: f32,
    pub is_acute_stress: bool,
    history: [f32; STRESS_HISTORY_LEN],
    history_idx: usize,
}

impl Default for TacticalStressWidget {
    fn default() -> Self {
        Self {
            stress_index_pct: 18.0,
            jitter_pct: 0.65,
            shimmer_pct: 2.4,
            pitch_elevation_hz: 6.0,
            speaking_rate_sps: 3.6,
            vocal_fatigue_pct: 12.0,
            is_acute_stress: false,
            history: [18.0; STRESS_HISTORY_LEN],
            history_idx: 0,
        }
    }
}

impl TacticalStressWidget {
    /// Creates a new TacticalStressWidget.
    pub fn new() -> Self {
        Self::default()
    }

    /// Pushes updated acoustic stress biomarkers from network telemetry or local analyzer.
    pub fn push_measurements(
        &mut self,
        stress_pct: f32,
        jitter_pct: f32,
        shimmer_pct: f32,
        pitch_elevation_hz: f32,
        speaking_rate_sps: f32,
        fatigue_pct: f32,
    ) {
        self.stress_index_pct = stress_pct.clamp(0.0, 100.0);
        self.jitter_pct = jitter_pct;
        self.shimmer_pct = shimmer_pct;
        self.pitch_elevation_hz = pitch_elevation_hz;
        self.speaking_rate_sps = speaking_rate_sps;
        self.vocal_fatigue_pct = fatigue_pct.clamp(0.0, 100.0);
        self.is_acute_stress = self.stress_index_pct >= 65.0;

        self.history[self.history_idx] = self.stress_index_pct;
        self.history_idx = (self.history_idx + 1) % STRESS_HISTORY_LEN;
    }

    /// Renders the Tactical Stress Index HUD widget into the given UI context.
    pub fn show(&mut self, ui: &mut Ui, height: f32) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(egui::Margin::same(10.0))
            .show(ui, |ui| {
                // Header line
                ui.horizontal(|ui| {
                    let (indicator_col, status_text) = if self.is_acute_stress {
                        (Theme::ACCENT_RED, "ACUTE COMBAT STRAIN")
                    } else if self.stress_index_pct > 35.0 {
                        (Theme::ACCENT_AMBER, "MODERATE COGNITIVE LOAD")
                    } else {
                        (Theme::ACCENT_GREEN, "CALM / STEADY STATE")
                    };

                    ui.label(egui::RichText::new("●").color(indicator_col).size(11.0));
                    ui.label(
                        egui::RichText::new("SOLDIER COGNITIVE STRESS INDEX")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(
                            egui::RichText::new(format!("{:.1}% [{}]", self.stress_index_pct, status_text))
                                .size(10.0)
                                .strong()
                                .color(indicator_col),
                        );
                    });
                });

                ui.add_space(6.0);

                // Main gauge bar & sparkline
                let (rect, _) = ui.allocate_exact_size(
                    Vec2::new(ui.available_width(), (height - 40.0).max(48.0)),
                    egui::Sense::hover(),
                );
                let painter = ui.painter_at(rect);

                // Background track
                painter.rect_filled(
                    Rect::from_min_size(rect.min, Vec2::new(rect.width(), 10.0)),
                    4.0,
                    Color32::from_rgb(20, 24, 30),
                );

                // Fill bar
                let fill_w = (rect.width() * (self.stress_index_pct / 100.0)).clamp(0.0, rect.width());
                let fill_col = if self.stress_index_pct > 65.0 {
                    Theme::ACCENT_RED
                } else if self.stress_index_pct > 35.0 {
                    Theme::ACCENT_AMBER
                } else {
                    Theme::ACCENT_GREEN
                };
                painter.rect_filled(
                    Rect::from_min_size(rect.min, Vec2::new(fill_w, 10.0)),
                    4.0,
                    fill_col,
                );

                // Sparkline history below bar
                let spark_y = rect.min.y + 16.0;
                let spark_h = (rect.height() - 20.0).max(18.0);
                let step_x = rect.width() / (STRESS_HISTORY_LEN - 1) as f32;

                for i in 0..(STRESS_HISTORY_LEN - 1) {
                    let idx1 = (self.history_idx + i) % STRESS_HISTORY_LEN;
                    let idx2 = (self.history_idx + i + 1) % STRESS_HISTORY_LEN;
                    let v1 = self.history[idx1] / 100.0;
                    let v2 = self.history[idx2] / 100.0;

                    let p1 = Pos2::new(rect.min.x + i as f32 * step_x, spark_y + spark_h * (1.0 - v1));
                    let p2 = Pos2::new(rect.min.x + (i + 1) as f32 * step_x, spark_y + spark_h * (1.0 - v2));

                    painter.line_segment([p1, p2], Stroke::new(1.2_f32, fill_col));
                }

                ui.add_space(4.0);

                // Sub-metrics row
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!("Jitter: {:.2}%", self.jitter_pct))
                            .size(9.5)
                            .color(Theme::TEXT_SECONDARY),
                    );
                    ui.label(egui::RichText::new("·").size(9.5).color(Theme::TEXT_MUTED));
                    ui.label(
                        egui::RichText::new(format!("Shimmer: {:.1}%", self.shimmer_pct))
                            .size(9.5)
                            .color(Theme::TEXT_SECONDARY),
                    );
                    ui.label(egui::RichText::new("·").size(9.5).color(Theme::TEXT_MUTED));
                    ui.label(
                        egui::RichText::new(format!("ΔF0: +{:.0} Hz", self.pitch_elevation_hz))
                            .size(9.5)
                            .color(Theme::TEXT_SECONDARY),
                    );
                    ui.label(egui::RichText::new("·").size(9.5).color(Theme::TEXT_MUTED));
                    ui.label(
                        egui::RichText::new(format!("Fatigue: {:.0}%", self.vocal_fatigue_pct))
                            .size(9.5)
                            .color(Theme::TEXT_SECONDARY),
                    );
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stress_widget_initialization() {
        let widget = TacticalStressWidget::new();
        assert_eq!(widget.stress_index_pct, 18.0);
        assert!(!widget.is_acute_stress);
    }

    #[test]
    fn test_stress_widget_push_measurements() {
        let mut widget = TacticalStressWidget::new();
        widget.push_measurements(78.5, 2.8, 8.4, 42.0, 5.8, 35.0);
        assert_eq!(widget.stress_index_pct, 78.5);
        assert!(widget.is_acute_stress);
        assert_eq!(widget.vocal_fatigue_pct, 35.0);
    }
}
