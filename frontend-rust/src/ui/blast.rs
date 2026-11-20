//! Acoustic Blast Wave Air-Overpressure & MIL-STD-1474E Impulse Exposure HUD Widget.
//!
//! Visualizes real-time physical acoustic concussions and weapon blast impulses:
//! - Instantaneous peak air overpressure in Pascals (Pa) and Pounds per Square Inch (PSI).
//! - Calibrated sound pressure level in dB SPL peak.
//! - Friedlander shock waveform profile with positive phase A-duration (ms).
//! - Cumulative daily impulse blast dose percentage against MIL-STD-1474E limits.
//! - Incident log of recent concussive events.

use eframe::egui::{self, Pos2, Rect, Stroke, Vec2};
use crate::ui::theme::Theme;
pub use anc_rust::metrics::blast::{BlastEvent, BlastHazardStatus, BlastTelemetry, BLAST_HISTORY_CAPACITY};

/// Interactive Blast Impulse & Overpressure Widget.
#[derive(Debug, Clone)]
pub struct BlastImpulseWidget {
    pub telemetry: BlastTelemetry,
    pub blast_history: [BlastEvent; BLAST_HISTORY_CAPACITY],
    pub history_count: usize,
}

impl Default for BlastImpulseWidget {
    fn default() -> Self {
        Self {
            telemetry: BlastTelemetry::default(),
            blast_history: [BlastEvent::default(); BLAST_HISTORY_CAPACITY],
            history_count: 0,
        }
    }
}

impl BlastImpulseWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal telemetry state and records any new blast event.
    pub fn update(&mut self, telem: BlastTelemetry) {
        if telem.last_blast_event.frame_index > 0
            && (self.history_count == 0 || self.blast_history[0].frame_index != telem.last_blast_event.frame_index)
        {
            // Shift history and insert latest at index 0
            for i in (1..BLAST_HISTORY_CAPACITY).rev() {
                self.blast_history[i] = self.blast_history[i - 1];
            }
            self.blast_history[0] = telem.last_blast_event;
            self.history_count = (self.history_count + 1).min(BLAST_HISTORY_CAPACITY);
        }
        self.telemetry = telem;
    }

    /// Renders the Blast & Overpressure HUD widget.
    pub fn show(&mut self, ui: &mut egui::Ui, height: f32) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(egui::Margin::same(10.0))
            .show(ui, |ui| {
                // Header
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("💣").color(Theme::ACCENT_RED).size(13.0));
                    ui.label(
                        egui::RichText::new("MIL-STD-1474E BLAST OVERPRESSURE")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (status_text, status_col) = match self.telemetry.hazard_status {
                            BlastHazardStatus::Nominal => ("NOMINAL (<50%)", Theme::ACCENT_GREEN),
                            BlastHazardStatus::Caution => ("CAUTION (50-100%)", Theme::ACCENT_AMBER),
                            BlastHazardStatus::Hazardous => ("HAZARDOUS (>100%)", Theme::ACCENT_RED),
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

                let (rect, _response) = ui.allocate_exact_size(
                    Vec2::new(ui.available_width(), height.max(80.0)),
                    egui::Sense::hover(),
                );

                let painter = ui.painter_at(rect);

                // Left Section: Overpressure Gauge & Friedlander Shock Profile
                let gauge_w = (rect.width() * 0.48).min(200.0);
                let text_x = rect.min.x + gauge_w + 12.0;

                // Draw Friedlander shock wave curve preview
                let shock_rect = Rect::from_min_size(rect.min, Vec2::new(gauge_w, rect.height() - 20.0));
                painter.rect_filled(shock_rect, 4.0, Theme::BG_SURFACE);
                painter.rect_stroke(shock_rect, 4.0, Stroke::new(1.0_f32, Theme::BORDER_DEFAULT));

                let baseline_y = shock_rect.min.y + shock_rect.height() * 0.65;
                painter.line_segment(
                    [Pos2::new(shock_rect.min.x, baseline_y), Pos2::new(shock_rect.max.x, baseline_y)],
                    Stroke::new(1.0_f32, Theme::BORDER_SUBTLE),
                );

                // Draw Friedlander curve: p(t) = P * (1 - t/T) * exp(-b * t / T)
                let peak_px = (shock_rect.height() * 0.50).min(35.0);
                let t_plus_w = gauge_w * 0.60;
                let mut prev_pt = Pos2::new(shock_rect.min.x + 8.0, baseline_y);

                for step in 0..=40 {
                    let frac = step as f32 / 40.0;
                    let t_x = shock_rect.min.x + 8.0 + frac * (gauge_w - 16.0);
                    let norm_t = (frac * (gauge_w - 16.0)) / t_plus_w;
                    let p = if norm_t <= 0.05 {
                        norm_t / 0.05 // Sharp instantaneous shock rise
                    } else {
                        let t_decay = (norm_t - 0.05) / 0.95;
                        (1.0 - t_decay) * (-1.5 * t_decay).exp()
                    };

                    let cur_pt = Pos2::new(t_x, baseline_y - p * peak_px);
                    painter.line_segment([prev_pt, cur_pt], Stroke::new(1.5_f32, Theme::ACCENT_RED));
                    prev_pt = cur_pt;
                }

                painter.text(
                    Pos2::new(shock_rect.min.x + 6.0, shock_rect.min.y + 4.0),
                    egui::Align2::LEFT_TOP,
                    "FRIEDLANDER WAVE",
                    egui::FontId::monospace(8.5),
                    Theme::TEXT_MUTED,
                );

                // Right Section: Numerical Readouts
                let line_h = 15.0;

                // 1. Peak Overpressure in Pa and PSI
                let pa_str = format!(
                    "PEAK: {:.1} Pa ({:.3} PSI)",
                    self.telemetry.peak_overpressure_pa,
                    self.telemetry.peak_overpressure_psi,
                );
                painter.text(
                    Pos2::new(text_x, rect.min.y + 4.0),
                    egui::Align2::LEFT_TOP,
                    pa_str,
                    egui::FontId::monospace(10.5),
                    Theme::ACCENT_AMBER,
                );

                // 2. Sound Pressure Level & Impulse Count
                let spl_str = format!(
                    "SPL: {:.1} dB peak  |  IMPULSES: {}",
                    self.telemetry.peak_spl_db,
                    self.telemetry.daily_impulse_count,
                );
                painter.text(
                    Pos2::new(text_x, rect.min.y + 4.0 + line_h),
                    egui::Align2::LEFT_TOP,
                    spl_str,
                    egui::FontId::monospace(10.0),
                    Theme::TEXT_SECONDARY,
                );

                // 3. MIL-STD-1474E Cumulative Dose Bar
                let dose_y = rect.min.y + 4.0 + line_h * 2.0;
                let bar_w = (rect.max.x - text_x - 8.0).max(60.0);
                let bar_h = 10.0;
                let dose_rect = Rect::from_min_size(Pos2::new(text_x, dose_y + 4.0), Vec2::new(bar_w, bar_h));

                painter.rect_filled(dose_rect, 2.0, Theme::BG_SURFACE);
                painter.rect_stroke(dose_rect, 2.0, Stroke::new(1.0_f32, Theme::BORDER_SUBTLE));

                let dose_pct = self.telemetry.cumulative_dose_pct.clamp(0.0, 100.0);
                let fill_w = bar_w * (dose_pct / 100.0);
                let fill_col = if dose_pct > 80.0 {
                    Theme::ACCENT_RED
                } else if dose_pct > 40.0 {
                    Theme::ACCENT_AMBER
                } else {
                    Theme::ACCENT_GREEN
                };

                if fill_w > 1.0 {
                    let fill_rect = Rect::from_min_size(dose_rect.min, Vec2::new(fill_w, bar_h));
                    painter.rect_filled(fill_rect, 2.0, fill_col);
                }

                let dose_label = format!("DAILY DOSE: {:.1}% OF LIMIT", self.telemetry.cumulative_dose_pct);
                painter.text(
                    Pos2::new(text_x, dose_y + 18.0),
                    egui::Align2::LEFT_TOP,
                    dose_label,
                    egui::FontId::monospace(9.5),
                    fill_col,
                );
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_blast_widget_initial_state() {
        let widget = BlastImpulseWidget::new();
        assert_eq!(widget.telemetry.daily_impulse_count, 0);
        assert_eq!(widget.telemetry.hazard_status, BlastHazardStatus::Nominal);
    }

    #[test]
    fn test_blast_widget_update() {
        let mut widget = BlastImpulseWidget::new();
        let telem = BlastTelemetry {
            peak_overpressure_pa: 632.0,
            peak_overpressure_psi: 0.092,
            daily_impulse_count: 5,
            hazard_status: BlastHazardStatus::Caution,
            ..Default::default()
        };

        widget.update(telem);
        assert_eq!(widget.telemetry.daily_impulse_count, 5);
        assert_eq!(widget.telemetry.hazard_status, BlastHazardStatus::Caution);
    }

    #[test]
    fn test_blast_widget_headless_context() {
        let mut widget = BlastImpulseWidget::new();
        let ctx = egui::Context::default();
        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                widget.show(ui, 85.0);
            });
        });
    }
}
