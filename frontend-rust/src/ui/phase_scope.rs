//! Multi-Channel Acoustic Spatial Lissajous Scope & Phase Correlation Monitor.
//!
//! Interactive X-Y phase vector monitor (Goniometer) visualizing:
//! - Mono target speech: sharp vertical line (+45 deg in raw mic coordinates, rotated to vertical M-axis)
//! - Diffuse acoustic noise: isotropic circular glowing cloud
//! - Out-of-phase interference: horizontal ellipse (warning of acoustic cancellation)
//! - Wind buffeting turbulence: swirling uncorrelated low-frequency dispersion
//!
//! Displays real-time:
//! - Inter-channel correlation coefficient r in [-1.0, +1.0]
//! - Stereo width percentage [0%, 100%]
//! - Wind buffeting intensity percentage

use egui::{Color32, Frame, Margin, Pos2, Rounding, Stroke, Ui, Vec2};
use std::f32::consts::{FRAC_1_SQRT_2, PI};
use super::theme::Theme;

/// Real-time phase correlation statistics.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PhaseScopeStats {
    pub correlation_r: f32,
    pub stereo_width_pct: f32,
    pub wind_buffeting_pct: f32,
    pub peak_amp: f32,
}

impl Default for PhaseScopeStats {
    fn default() -> Self {
        Self {
            correlation_r: 1.0,
            stereo_width_pct: 0.0,
            wind_buffeting_pct: 0.0,
            peak_amp: 0.0,
        }
    }
}

/// Circular Lissajous Phase Scope and Goniometer Widget.
pub struct PhaseScopeWidget {
    history_x: Vec<f32>,
    history_y: Vec<f32>,
    max_points: usize,
    gain_scale: f32,
    stats: PhaseScopeStats,
}

impl Default for PhaseScopeWidget {
    fn default() -> Self {
        Self::new(256)
    }
}

impl PhaseScopeWidget {
    /// Creates a new PhaseScopeWidget maintaining `max_points` historical vector samples.
    pub fn new(max_points: usize) -> Self {
        Self {
            history_x: Vec::with_capacity(max_points),
            history_y: Vec::with_capacity(max_points),
            max_points,
            gain_scale: 1.2,
            stats: PhaseScopeStats::default(),
        }
    }

    /// Pushes stereo audio samples (left/mic1 and right/mic2) and updates real-time correlation.
    pub fn push_samples(&mut self, mic1: &[f32], mic2: &[f32], wti_telemetry: Option<f32>) {
        if mic1.is_empty() || mic2.is_empty() {
            return;
        }

        let n = mic1.len().min(mic2.len());
        let mut sum_xy = 0.0f32;
        let mut sum_x2 = 0.0f32;
        let mut sum_y2 = 0.0f32;
        let mut peak: f32 = 0.0;

        // Subsample if hop is large
        let step = (n / self.max_points).max(1);

        self.history_x.clear();
        self.history_y.clear();

        for i in (0..n).step_by(step) {
            let m1 = mic1[i];
            let m2 = mic2[i];

            peak = peak.max(m1.abs()).max(m2.abs());

            sum_xy += m1 * m2;
            sum_x2 += m1 * m1;
            sum_y2 += m2 * m2;

            // Goniometer Mid-Side projection:
            // Mid = (m1 + m2) / sqrt(2)  -> Vertical axis
            // Side = (m1 - m2) / sqrt(2) -> Horizontal axis
            let mid = (m1 + m2) * FRAC_1_SQRT_2;
            let side = (m1 - m2) * FRAC_1_SQRT_2;

            self.history_x.push(side);
            self.history_y.push(mid);
        }

        // Pearson correlation coefficient r in [-1.0, 1.0]
        let denom = (sum_x2 * sum_y2).sqrt().max(1e-8);
        let r = (sum_xy / denom).clamp(-1.0, 1.0);
        self.stats.correlation_r = r;

        // Stereo width: 0% = pure mono (r = 1.0), 100% = wide diffuse (r = 0.0)
        let width = ((1.0 - r) * 50.0).clamp(0.0, 100.0);
        self.stats.stereo_width_pct = width;

        // Wind buffeting intensity derived from telemetry WTI or low-frequency decorrelation
        self.stats.wind_buffeting_pct = if let Some(wti) = wti_telemetry {
            (wti * 100.0).clamp(0.0, 100.0)
        } else if peak > 0.05 && r < 0.30 {
            ((1.0 - r) * 70.0).clamp(0.0, 100.0)
        } else {
            0.0
        };

        self.stats.peak_amp = peak;
    }

    /// Latest correlation metrics.
    pub fn stats(&self) -> PhaseScopeStats {
        self.stats
    }

    /// Renders the interactive Lissajous Phase Scope widget in egui.
    pub fn show(&mut self, ui: &mut Ui, diameter: f32) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Widget Header
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("●").color(Theme::ACCENT_CYAN).size(11.0));
                    ui.label(
                        egui::RichText::new("SPATIAL LISSAJOUS PHASE SCOPE")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (r_label, r_color) = if self.stats.correlation_r >= 0.70 {
                            (format!("r: {:+.2} (IN-PHASE)", self.stats.correlation_r), Theme::ACCENT_GREEN)
                        } else if self.stats.correlation_r >= 0.20 {
                            (format!("r: {:+.2} (DIFFUSE)", self.stats.correlation_r), Theme::ACCENT_CYAN)
                        } else if self.stats.correlation_r >= -0.20 {
                            (format!("r: {:+.2} (UNCORRELATED)", self.stats.correlation_r), Theme::ACCENT_AMBER)
                        } else {
                            (format!("r: {:+.2} (OUT-OF-PHASE)", self.stats.correlation_r), Theme::ACCENT_RED)
                        };

                        ui.label(
                            egui::RichText::new(r_label)
                                .size(10.5)
                                .strong()
                                .monospace()
                                .color(r_color),
                        );
                    });
                });

                ui.add_space(6.0);

                // Scope Canvas
                let (rect, _response) = ui.allocate_exact_size(
                    Vec2::new(diameter, diameter),
                    egui::Sense::hover(),
                );
                let painter = ui.painter_at(rect);
                let center = rect.center();
                let radius = diameter * 0.46;

                // 1. Dark circular radar background
                painter.circle_filled(
                    center,
                    radius,
                    Color32::from_rgb(10, 14, 20),
                );

                // 2. Range rings and polar reticles
                for &frac in &[0.33, 0.66, 1.0] {
                    painter.circle_stroke(
                        center,
                        radius * frac,
                        Stroke::new(0.8_f32, Color32::from_rgba_unmultiplied(25, 45, 60, 140)),
                    );
                }

                // Orthogonal Mid-Side Axes
                let axis_stroke = Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(35, 60, 80, 180));
                // Vertical (Mid / In-Phase Mono)
                painter.line_segment(
                    [Pos2::new(center.x, center.y - radius), Pos2::new(center.x, center.y + radius)],
                    axis_stroke,
                );
                // Horizontal (Side / Out-of-Phase)
                painter.line_segment(
                    [Pos2::new(center.x - radius, center.y), Pos2::new(center.x + radius, center.y)],
                    axis_stroke,
                );

                // Diagonal +/- 45 deg guide lines (Raw Mic 1 and Mic 2 axes)
                let diag_stroke = Stroke::new(0.6_f32, Color32::from_rgba_unmultiplied(30, 50, 65, 100));
                let cos45 = (PI / 4.0).cos() * radius;
                painter.line_segment(
                    [Pos2::new(center.x - cos45, center.y - cos45), Pos2::new(center.x + cos45, center.y + cos45)],
                    diag_stroke,
                );
                painter.line_segment(
                    [Pos2::new(center.x - cos45, center.y + cos45), Pos2::new(center.x + cos45, center.y - cos45)],
                    diag_stroke,
                );

                // Axis Labels
                painter.text(
                    Pos2::new(center.x, center.y - radius + 8.0),
                    egui::Align2::CENTER_TOP,
                    "+M (MONO)",
                    egui::FontId::monospace(8.5),
                    Color32::from_rgb(0, 215, 235),
                );
                painter.text(
                    Pos2::new(center.x + radius - 6.0, center.y),
                    egui::Align2::RIGHT_CENTER,
                    "+S",
                    egui::FontId::monospace(8.0),
                    Color32::from_rgb(120, 140, 160),
                );
                painter.text(
                    Pos2::new(center.x - radius + 6.0, center.y),
                    egui::Align2::LEFT_CENTER,
                    "-S",
                    egui::FontId::monospace(8.0),
                    Color32::from_rgb(120, 140, 160),
                );

                // 3. Render Lissajous Vector Trajectory Points
                let n_points = self.history_x.len();
                if n_points > 1 {
                    let trace_color = if self.stats.correlation_r >= 0.65 {
                        Color32::from_rgba_unmultiplied(0, 225, 245, 180) // In-phase Cyan
                    } else if self.stats.correlation_r >= 0.15 {
                        Color32::from_rgba_unmultiplied(80, 200, 255, 160) // Diffuse Light Blue
                    } else if self.stats.correlation_r >= -0.20 {
                        Color32::from_rgba_unmultiplied(245, 166, 35, 180) // Amber Uncorrelated
                    } else {
                        Color32::from_rgba_unmultiplied(255, 75, 75, 200) // Red Out-of-Phase
                    };

                    let scale = (radius * 0.90) * self.gain_scale;

                    for i in 0..n_points {
                        let side = self.history_x[i];
                        let mid = self.history_y[i];

                        let px = center.x + (side * scale).clamp(-radius, radius);
                        // Invert Y so positive Mid points upward
                        let py = center.y - (mid * scale).clamp(-radius, radius);

                        // Fading trail effect
                        let alpha = ((i as f32 / n_points as f32) * 200.0) as u8 + 55;
                        let mut pt_color = trace_color;
                        pt_color = Color32::from_rgba_unmultiplied(pt_color.r(), pt_color.g(), pt_color.b(), alpha);

                        painter.circle_filled(Pos2::new(px, py), 1.3, pt_color);
                    }
                }

                ui.add_space(4.0);

                // Lower Readout Bar: Stereo Width & Wind Buffeting
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!("WIDTH: {:.0}%", self.stats.stereo_width_pct))
                            .size(10.0)
                            .color(Theme::TEXT_SECONDARY),
                    );
                    ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));

                    let wind_color = if self.stats.wind_buffeting_pct > 70.0 {
                        Theme::ACCENT_RED
                    } else if self.stats.wind_buffeting_pct > 30.0 {
                        Theme::ACCENT_AMBER
                    } else {
                        Theme::ACCENT_GREEN
                    };

                    ui.label(
                        egui::RichText::new(format!("WIND TURB: {:.0}%", self.stats.wind_buffeting_pct))
                            .size(10.0)
                            .strong()
                            .color(wind_color),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button(egui::RichText::new("1x").size(9.0)).clicked() {
                            self.gain_scale = 1.0;
                        }
                        if ui.button(egui::RichText::new("2x").size(9.0)).clicked() {
                            self.gain_scale = 2.0;
                        }
                    });
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_phase_scope_correlation_pure_mono() {
        let mut scope = PhaseScopeWidget::new(128);
        let mic1 = [0.1, 0.2, -0.3, 0.4, 0.5, -0.2, 0.3, 0.1];
        let mic2 = [0.1, 0.2, -0.3, 0.4, 0.5, -0.2, 0.3, 0.1]; // Identical in-phase

        scope.push_samples(&mic1, &mic2, None);
        let stats = scope.stats();

        assert!((stats.correlation_r - 1.0).abs() < 1e-4);
        assert!(stats.stereo_width_pct < 1.0);
    }

    #[test]
    fn test_phase_scope_correlation_pure_out_of_phase() {
        let mut scope = PhaseScopeWidget::new(128);
        let mic1 = [0.1, 0.2, -0.3, 0.4, 0.5];
        let mic2 = [-0.1, -0.2, 0.3, -0.4, -0.5]; // 180 degrees out of phase

        scope.push_samples(&mic1, &mic2, None);
        let stats = scope.stats();

        assert!((stats.correlation_r - (-1.0)).abs() < 1e-4);
        assert!(stats.stereo_width_pct > 99.0);
    }
}
