//! First-Order 2D/3D Ambisonics Tactical Acoustic Intensity & Diffuseness Scope Widget.
//!
//! Developed for SIH 26052 Tactical Military Audio HUD.
//!
//! Visualizes real-time B-format acoustic energy flow:
//! - Active acoustic intensity vector \vec{I}_a = \frac{1}{2}\text{Re}\{P \cdot \vec{V}^*\} (Direction & Magnitude).
//! - Acoustic diffuseness index \psi = 1 - \frac{\|\vec{I}\|}{c \cdot E} (0.0 = pure plane wave, 1.0 = isotropic diffuse noise).
//! - 360° directional flow vector rendered on a tactical polar HUD scope with azimuth indicator.

use eframe::egui::{self, Color32, Frame, Margin, Pos2, Rect, Rounding, Stroke, Ui, Vec2};
use crate::ui::theme::Theme;
pub use anc_rust::dsp::ambisonics::AmbisonicsTelemetry;

/// Interactive Ambisonics Intensity & Diffuseness Scope Widget.
#[derive(Debug, Clone)]
pub struct AmbisonicsScopeWidget {
    pub telemetry: AmbisonicsTelemetry,
    history_azimuth: [f32; 32],
    history_diffuseness: [f32; 32],
    history_idx: usize,
}

impl Default for AmbisonicsScopeWidget {
    fn default() -> Self {
        Self {
            telemetry: AmbisonicsTelemetry::default(),
            history_azimuth: [0.0; 32],
            history_diffuseness: [0.0; 32],
            history_idx: 0,
        }
    }
}

impl AmbisonicsScopeWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal telemetry and records circular buffer history.
    pub fn update(&mut self, telem: AmbisonicsTelemetry) {
        self.telemetry = telem;
        self.history_azimuth[self.history_idx] = telem.azimuth_deg;
        self.history_diffuseness[self.history_idx] = telem.diffuseness;
        self.history_idx = (self.history_idx + 1) % self.history_azimuth.len();
    }

    /// Renders the Ambisonics Intensity & Diffuseness Scope HUD Widget.
    pub fn show(&mut self, ui: &mut Ui, height: f32) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Header
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("🧭").color(Theme::ACCENT_CYAN).size(13.0));
                    ui.label(
                        egui::RichText::new("B-FORMAT AMBISONICS INTENSITY & DIFFUSENESS")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let diff = self.telemetry.diffuseness.clamp(0.0, 1.0);
                        let (field_type, field_col) = if diff < 0.35 {
                            ("DIRECT PLANE WAVE", Theme::ACCENT_CYAN)
                        } else if diff < 0.70 {
                            ("MIXED DIRECT/DIFFUSE", Theme::ACCENT_GREEN)
                        } else {
                            ("ISOTROPIC DIFFUSE", Theme::ACCENT_AMBER)
                        };

                        ui.label(
                            egui::RichText::new(field_type)
                                .size(10.0)
                                .strong()
                                .monospace()
                                .color(field_col),
                        );
                    });
                });

                ui.add_space(6.0);

                // Main body: Left scope circle + Right telemetry readouts
                ui.horizontal(|ui| {
                    // Left scope (Circular radar / intensity vector)
                    let scope_size = (height - 28.0).max(50.0);
                    let (rect, _response) = ui.allocate_exact_size(
                        Vec2::new(scope_size, scope_size),
                        egui::Sense::hover(),
                    );

                    let painter = ui.painter_at(rect);
                    let center = rect.center();
                    let radius = scope_size * 0.45;

                    // Scope background
                    painter.circle_filled(center, radius, Color32::from_rgb(12, 17, 26));
                    painter.circle_stroke(
                        center,
                        radius,
                        Stroke::new(1.0_f32, Theme::BORDER_DEFAULT),
                    );

                    // Diffuseness ring (radius proportional to diffuseness)
                    let diff_radius = (radius * self.telemetry.diffuseness.clamp(0.05, 1.0)).max(4.0);
                    painter.circle_stroke(
                        center,
                        diff_radius,
                        Stroke::new(1.2_f32, Color32::from_rgba_premultiplied(245, 158, 11, 70)),
                    );

                    // Crosshairs
                    painter.line_segment(
                        [Pos2::new(center.x - radius, center.y), Pos2::new(center.x + radius, center.y)],
                        Stroke::new(0.8_f32, Color32::from_rgb(30, 41, 59)),
                    );
                    painter.line_segment(
                        [Pos2::new(center.x, center.y - radius), Pos2::new(center.x, center.y + radius)],
                        Stroke::new(0.8_f32, Color32::from_rgb(30, 41, 59)),
                    );

                    // Intensity Vector Arrow
                    let angle_rad = self.telemetry.azimuth_deg.to_radians();
                    let mag_norm = (self.telemetry.intensity_mag * 2.0).clamp(0.1, 1.0);
                    let vector_len = radius * mag_norm;
                    let target_x = center.x + angle_rad.sin() * vector_len;
                    let target_y = center.y - angle_rad.cos() * vector_len;
                    let target_pos = Pos2::new(target_x, target_y);

                    // Draw intensity flow vector line
                    painter.line_segment(
                        [center, target_pos],
                        Stroke::new(2.2_f32, Theme::ACCENT_CYAN),
                    );

                    // Arrowhead
                    painter.circle_filled(target_pos, 3.5, Theme::ACCENT_CYAN);
                    painter.circle_filled(center, 2.0, Theme::TEXT_MUTED);

                    ui.add_space(8.0);

                    // Right column: Detailed metrics
                    let diff = self.telemetry.diffuseness;
                    ui.vertical(|ui| {
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("AZIMUTH:").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("{:>+5.1}°", self.telemetry.azimuth_deg))
                                    .size(11.0)
                                    .strong()
                                    .monospace()
                                    .color(Theme::ACCENT_CYAN),
                            );

                            ui.add_space(8.0);
                            ui.label(egui::RichText::new("INTENSITY:").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("{:.3}", self.telemetry.intensity_mag))
                                    .size(11.0)
                                    .monospace()
                                    .color(Theme::TEXT_PRIMARY),
                            );
                        });

                        ui.add_space(2.0);

                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("DIFFUSENESS \u{03c8}:").size(9.5).color(Theme::TEXT_MUTED));
                            let diff = self.telemetry.diffuseness;
                            let diff_col = if diff < 0.35 {
                                Theme::ACCENT_CYAN
                            } else if diff < 0.70 {
                                Theme::ACCENT_GREEN
                            } else {
                                Theme::ACCENT_AMBER
                            };
                            ui.label(
                                egui::RichText::new(format!("{:.2}", diff))
                                    .size(11.0)
                                    .strong()
                                    .monospace()
                                    .color(diff_col),
                            );

                            ui.add_space(8.0);
                            ui.label(egui::RichText::new("ENERGY DENS:").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("{:.3}", self.telemetry.energy_density))
                                    .size(11.0)
                                    .monospace()
                                    .color(Theme::TEXT_PRIMARY),
                            );
                        });

                        ui.add_space(2.0);

                        // Mini progress bar for diffuseness
                        let bar_width = 140.0_f32;
                        let bar_height = 4.0_f32;
                        let (bar_rect, _) = ui.allocate_exact_size(Vec2::new(bar_width, bar_height), egui::Sense::hover());
                        let bar_painter = ui.painter_at(bar_rect);
                        bar_painter.rect_filled(bar_rect, Rounding::same(2.0), Color32::from_rgb(26, 32, 44));
                        let fill_rect = Rect::from_min_size(
                            bar_rect.min,
                            Vec2::new(bar_width * diff.clamp(0.0, 1.0), bar_height),
                        );
                        let fill_color = if diff < 0.35 {
                            Theme::ACCENT_CYAN
                        } else if diff < 0.70 {
                            Theme::ACCENT_GREEN
                        } else {
                            Theme::ACCENT_AMBER
                        };
                        bar_painter.rect_filled(fill_rect, Rounding::same(2.0), fill_color);
                    });
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ambisonics_widget_initialization() {
        let widget = AmbisonicsScopeWidget::new();
        assert_eq!(widget.telemetry.azimuth_deg, 0.0);
        assert_eq!(widget.telemetry.diffuseness, 0.0);
        assert_eq!(widget.history_idx, 0);
    }

    #[test]
    fn test_ambisonics_widget_update() {
        let mut widget = AmbisonicsScopeWidget::new();
        let telem = AmbisonicsTelemetry {
            intensity_x: 0.3,
            intensity_y: 0.4,
            intensity_z: 0.0,
            intensity_mag: 0.5,
            energy_density: 0.6,
            diffuseness: 0.25,
            azimuth_deg: 36.87,
            elevation_deg: 0.0,
            is_localized: true,
        };
        widget.update(telem);
        assert_eq!(widget.telemetry.intensity_mag, 0.5);
        assert_eq!(widget.telemetry.diffuseness, 0.25);
        assert_eq!(widget.history_azimuth[0], 36.87);
        assert_eq!(widget.history_idx, 1);
    }

    #[test]
    fn test_ambisonics_widget_headless_context() {
        let mut widget = AmbisonicsScopeWidget::new();
        let ctx = egui::Context::default();
        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                widget.show(ui, 75.0);
            });
        });
    }
}
