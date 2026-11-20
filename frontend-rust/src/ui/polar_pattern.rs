//! Interactive Polar Directivity Scope & De-Esser Meter Widget.
//!
//! Developed for SIH 26052 Tactical Military Audio HUD.
//!
//! Visualizes:
//! 1. 360-Degree First-Order Differential Polar Directivity Sensitivity:
//!    - Plots on-axis lobe, side nulls, and rear attenuation for Omnidirectional, Cardioid,
//!      Supercardioid, Hypercardioid, Figure-8, and Custom Steered Null patterns.
//!    - Highlights acoustic null angle markers (±110°, ±126°, 180°).
//!    - Front-to-back ratio (dB) and Directivity Index (DI dB).
//! 2. Real-Time Dynamic Psychoacoustic De-Esser Gain Reduction Meter:
//!    - Segmented LED-style attenuation display (0 dB down to -18 dB).
//!    - Sibilance ratio sparkline and active consonant damping beacon.
//! 3. Interactive controls to steer acoustic nulls directly toward incoming tactical threats.

use crate::ui::theme::Theme;
pub use anc_rust::dsp::deesser::DeEsserTelemetry;
pub use anc_rust::dsp::polar_pattern::{PolarPatternTelemetry, PolarPatternType};
use eframe::egui::{self, Color32, Frame, Margin, Pos2, Rect, Rounding, Stroke, Ui, Vec2};
use std::f32::consts::PI;

/// Interactive Polar Sensitivity & Anti-Sibilance HUD Widget.
pub struct PolarDirectivityWidget {
    pub polar_telemetry: PolarPatternTelemetry,
    pub deesser_telemetry: DeEsserTelemetry,
    pub selected_pattern: PolarPatternType,
    pub steered_null_deg: f32,
    reduction_history: [f32; 48],
    history_idx: usize,
}

impl Default for PolarDirectivityWidget {
    fn default() -> Self {
        Self {
            polar_telemetry: PolarPatternTelemetry::default(),
            deesser_telemetry: DeEsserTelemetry::default(),
            selected_pattern: PolarPatternType::Cardioid,
            steered_null_deg: 180.0,
            reduction_history: [0.0; 48],
            history_idx: 0,
        }
    }
}

impl PolarDirectivityWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal telemetry states and rolls the reduction history sparkline.
    pub fn update(&mut self, polar: PolarPatternTelemetry, deesser: DeEsserTelemetry) {
        self.polar_telemetry = polar;
        self.deesser_telemetry = deesser;
        self.selected_pattern = PolarPatternType::from_u8(polar.pattern_type);
        self.steered_null_deg = polar.null_angle_deg;

        self.reduction_history[self.history_idx] = deesser.gain_reduction_db.abs();
        self.history_idx = (self.history_idx + 1) % self.reduction_history.len();
    }

    /// Calculates theoretical sensitivity $D(\theta) \in [0.0, 1.0]$.
    pub fn sensitivity_at_angle(&self, angle_rad: f32) -> f32 {
        let cos_theta = angle_rad.cos();
        match self.selected_pattern {
            PolarPatternType::Omnidirectional => 1.0,
            PolarPatternType::Cardioid => (0.5 * (1.0 + cos_theta)).abs(),
            PolarPatternType::Supercardioid => (0.37 + 0.63 * cos_theta).abs(),
            PolarPatternType::Hypercardioid => (0.25 + 0.75 * cos_theta).abs(),
            PolarPatternType::Figure8 => cos_theta.abs(),
            PolarPatternType::CustomSteered => {
                let null_rad = self.steered_null_deg.to_radians();
                let tau_norm = -null_rad.cos().max(0.0);
                ((tau_norm + cos_theta) / (tau_norm + 1.0).max(1e-4))
                    .abs()
                    .clamp(0.0, 1.0)
            }
        }
    }

    /// Renders the Polar Directivity Scope and De-Esser Meter.
    ///
    /// Returns `Some((pattern, null_deg))` if operator modified the pattern or steered angle.
    pub fn show(&mut self, ui: &mut Ui, height: f32) -> Option<(PolarPatternType, f32)> {
        let mut user_action = None;

        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Header bar
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("🎯")
                            .color(Theme::ACCENT_CYAN)
                            .size(13.0),
                    );
                    ui.label(
                        egui::RichText::new("POLAR DIRECTIVITY & DE-ESSER")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if self.deesser_telemetry.sibilance_detected {
                            ui.label(
                                egui::RichText::new("● ANTI-SIBILANCE ACTIVE")
                                    .size(10.0)
                                    .strong()
                                    .monospace()
                                    .color(Theme::ACCENT_AMBER),
                            );
                        } else {
                            ui.label(
                                egui::RichText::new("● MONITORING")
                                    .size(10.0)
                                    .monospace()
                                    .color(Theme::TEXT_MUTED),
                            );
                        }

                        ui.add_space(8.0);
                        ui.label(
                            egui::RichText::new(self.selected_pattern.name())
                                .size(10.0)
                                .color(Theme::ACCENT_CYAN),
                        );
                    });
                });

                ui.add_space(6.0);

                let available_w = ui.available_width();
                let actual_h = height.max(120.0);
                let (rect, _response) =
                    ui.allocate_exact_size(Vec2::new(available_w, actual_h), egui::Sense::hover());

                let painter = ui.painter_at(rect);

                // Split into: Left = Polar Plot (circular), Right = Controls & LED Meter
                let plot_diameter = actual_h.min(available_w * 0.42);
                let plot_center = Pos2::new(rect.min.x + plot_diameter * 0.55, rect.center().y);
                let plot_radius = plot_diameter * 0.46;

                // 1. Draw concentric range rings (0 dB, -6 dB, -12 dB, -18 dB)
                for &(frac, label) in &[
                    (1.0f32, "0dB"),
                    (0.75, "-6dB"),
                    (0.50, "-12dB"),
                    (0.25, "-18dB"),
                ] {
                    let r = plot_radius * frac;
                    painter.circle_stroke(
                        plot_center,
                        r,
                        Stroke::new(
                            1.0_f32,
                            if frac == 1.0 {
                                Theme::BORDER_DEFAULT
                            } else {
                                Theme::BORDER_DEFAULT.gamma_multiply(0.4)
                            },
                        ),
                    );
                    painter.text(
                        Pos2::new(plot_center.x + 3.0, plot_center.y - r + 2.0),
                        egui::Align2::LEFT_TOP,
                        label,
                        egui::FontId::monospace(8.0),
                        Theme::TEXT_MUTED,
                    );
                }

                // 2. Draw crosshair angle rays
                for &deg in &[0.0f32, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0] {
                    let rad = (deg - 90.0).to_radians();
                    let p_end = Pos2::new(
                        plot_center.x + plot_radius * rad.cos(),
                        plot_center.y + plot_radius * rad.sin(),
                    );
                    painter.line_segment(
                        [plot_center, p_end],
                        Stroke::new(1.0_f32, Theme::BORDER_DEFAULT.gamma_multiply(0.3)),
                    );
                }

                // Label 0° Front and 180° Rear
                painter.text(
                    Pos2::new(plot_center.x, plot_center.y - plot_radius - 8.0),
                    egui::Align2::CENTER_BOTTOM,
                    "FRONT 0°",
                    egui::FontId::proportional(8.5),
                    Theme::ACCENT_CYAN,
                );
                painter.text(
                    Pos2::new(plot_center.x, plot_center.y + plot_radius + 8.0),
                    egui::Align2::CENTER_TOP,
                    "REAR 180°",
                    egui::FontId::proportional(8.5),
                    Theme::TEXT_MUTED,
                );

                // 3. Draw theoretical 360-degree polar sensitivity lobe
                let steps = 72;
                let mut lobe_points = Vec::with_capacity(steps + 1);
                for i in 0..=steps {
                    let theta = (i as f32 / steps as f32) * 2.0 * PI; // 0 to 2pi (0 rad is front, i.e. up)
                    let sens = self.sensitivity_at_angle(theta).clamp(0.04, 1.0);
                    let r = plot_radius * sens;
                    let draw_angle = theta - PI * 0.5; // rotate so 0 rad is up
                    let pt = Pos2::new(
                        plot_center.x + r * draw_angle.cos(),
                        plot_center.y + r * draw_angle.sin(),
                    );
                    lobe_points.push(pt);
                }

                // Translucent fill for sensitivity lobe
                let lobe_fill = Color32::from_rgba_unmultiplied(40, 220, 200, 30);
                painter.add(egui::Shape::convex_polygon(
                    lobe_points.clone(),
                    lobe_fill,
                    Stroke::NONE,
                ));
                // Lobe outline
                for i in 0..steps {
                    painter.line_segment(
                        [lobe_points[i], lobe_points[i + 1]],
                        Stroke::new(1.5_f32, Theme::ACCENT_CYAN),
                    );
                }

                // 4. Highlight null markers (e.g. ±null_angle)
                if self.selected_pattern != PolarPatternType::Omnidirectional {
                    let null_deg = self.steered_null_deg;
                    for &sign in &[-1.0f32, 1.0] {
                        let null_angle = (sign * null_deg - 90.0).to_radians();
                        let p_null = Pos2::new(
                            plot_center.x + plot_radius * null_angle.cos(),
                            plot_center.y + plot_radius * null_angle.sin(),
                        );
                        painter.line_segment(
                            [plot_center, p_null],
                            Stroke::new(1.2_f32, Theme::ACCENT_RED.gamma_multiply(0.7)),
                        );
                        painter.circle_filled(p_null, 3.0, Theme::ACCENT_RED);
                    }
                }

                // 5. Right pane: Metrics, De-Esser LED meter, and controls
                let right_min_x = plot_center.x + plot_radius + 18.0;
                let right_w = rect.max.x - right_min_x;

                let right_rect = Rect::from_min_size(
                    Pos2::new(right_min_x, rect.min.y + 2.0),
                    Vec2::new(right_w, actual_h - 4.0),
                );
                ui.allocate_new_ui(egui::UiBuilder::new().max_rect(right_rect), |right_ui| {
                    // Metrics row
                    right_ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new("F/B RATIO:")
                                .size(9.5)
                                .color(Theme::TEXT_MUTED),
                        );
                        ui.label(
                            egui::RichText::new(format!(
                                "{:.1} dB",
                                self.polar_telemetry.front_to_back_ratio_db
                            ))
                            .size(9.5)
                            .strong()
                            .color(Theme::ACCENT_CYAN),
                        );
                        ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));
                        ui.label(
                            egui::RichText::new("DI:")
                                .size(9.5)
                                .color(Theme::TEXT_MUTED),
                        );
                        ui.label(
                            egui::RichText::new(format!(
                                "{:.1} dB",
                                self.polar_telemetry.directivity_index_db
                            ))
                            .size(9.5)
                            .strong()
                            .color(Theme::ACCENT_GREEN),
                        );
                        ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));
                        ui.label(
                            egui::RichText::new("NULL:")
                                .size(9.5)
                                .color(Theme::TEXT_MUTED),
                        );
                        ui.label(
                            egui::RichText::new(format!("{:.0}°", self.steered_null_deg))
                                .size(9.5)
                                .strong()
                                .color(Theme::ACCENT_AMBER),
                        );
                    });

                    right_ui.add_space(4.0);

                    // De-Esser Gain Reduction LED Meter
                    right_ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new("DE-ESS REDUCTION:")
                                .size(9.5)
                                .strong()
                                .color(Theme::TEXT_SECONDARY),
                        );
                        let red_db = self.deesser_telemetry.gain_reduction_db;
                        let red_text = format!("{:.1} dB", red_db);
                        let red_col = if red_db < -6.0 {
                            Theme::ACCENT_RED
                        } else if red_db < -1.0 {
                            Theme::ACCENT_AMBER
                        } else {
                            Theme::ACCENT_GREEN
                        };
                        ui.label(
                            egui::RichText::new(red_text)
                                .size(9.5)
                                .strong()
                                .color(red_col),
                        );
                    });

                    // LED meter bar
                    let led_w = (right_w - 8.0).max(100.0);
                    let (led_rect, _) =
                        right_ui.allocate_exact_size(Vec2::new(led_w, 10.0), egui::Sense::hover());
                    let led_painter = right_ui.painter_at(led_rect);
                    let num_leds = 18;
                    let cur_reduction = self.deesser_telemetry.gain_reduction_db.abs().min(18.0);
                    let active_leds = (cur_reduction / 18.0 * num_leds as f32).round() as usize;

                    let segment_w =
                        (led_rect.width() - (num_leds - 1) as f32 * 2.0) / num_leds as f32;
                    for i in 0..num_leds {
                        let seg_x = led_rect.min.x + i as f32 * (segment_w + 2.0);
                        let seg_rect = Rect::from_min_size(
                            Pos2::new(seg_x, led_rect.min.y),
                            Vec2::new(segment_w, led_rect.height()),
                        );
                        let is_lit = i < active_leds;
                        let col = if is_lit {
                            if i >= 12 {
                                Theme::ACCENT_RED
                            } else if i >= 6 {
                                Theme::ACCENT_AMBER
                            } else {
                                Theme::ACCENT_GREEN
                            }
                        } else {
                            Color32::from_gray(30)
                        };
                        led_painter.rect_filled(seg_rect, Rounding::same(1.5), col);
                    }

                    right_ui.add_space(4.0);

                    // Pattern Mode Selectors
                    right_ui.horizontal(|ui| {
                        let patterns = [
                            (PolarPatternType::Omnidirectional, "OMNI"),
                            (PolarPatternType::Cardioid, "CARDIOID"),
                            (PolarPatternType::Supercardioid, "SUPER"),
                            (PolarPatternType::Hypercardioid, "HYPER"),
                            (PolarPatternType::Figure8, "FIG-8"),
                        ];

                        for (pat, label) in patterns {
                            let is_active = self.selected_pattern == pat;
                            if ui
                                .selectable_label(
                                    is_active,
                                    egui::RichText::new(label).size(9.0).strong(),
                                )
                                .clicked()
                            {
                                self.selected_pattern = pat;
                                user_action = Some((pat, self.steered_null_deg));
                            }
                        }
                    });

                    right_ui.add_space(4.0);

                    // Null Steering Slider
                    right_ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new("STEER NULL:")
                                .size(9.0)
                                .color(Theme::TEXT_MUTED),
                        );
                        let mut angle = self.steered_null_deg;
                        let slider = egui::Slider::new(&mut angle, 90.0..=180.0)
                            .suffix("°")
                            .show_value(true)
                            .text_color(Theme::ACCENT_AMBER);
                        if ui.add_sized([130.0, 16.0], slider).changed() {
                            self.steered_null_deg = angle;
                            self.selected_pattern = PolarPatternType::CustomSteered;
                            user_action = Some((PolarPatternType::CustomSteered, angle));
                        }
                    });
                });
            });

        user_action
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_polar_widget_initialization() {
        let widget = PolarDirectivityWidget::new();
        assert_eq!(widget.selected_pattern, PolarPatternType::Cardioid);
        assert_eq!(widget.steered_null_deg, 180.0);
    }

    #[test]
    fn test_polar_widget_update() {
        let mut widget = PolarDirectivityWidget::new();
        let polar_telem = PolarPatternTelemetry {
            pattern_type: PolarPatternType::Hypercardioid as u8,
            null_angle_deg: 110.0,
            front_to_back_ratio_db: 6.0,
            directivity_index_db: 6.0,
            internal_delay_us: 19.4,
        };
        let deesser_telem = DeEsserTelemetry {
            sibilance_detected: true,
            sibilance_ratio_db: 5.5,
            gain_reduction_db: -4.5,
            sibilant_energy_dbfs: -35.0,
            broadband_energy_dbfs: -40.0,
        };

        widget.update(polar_telem, deesser_telem);
        assert_eq!(widget.selected_pattern, PolarPatternType::Hypercardioid);
        assert_eq!(widget.steered_null_deg, 110.0);
        assert!(widget.deesser_telemetry.sibilance_detected);
    }

    #[test]
    fn test_polar_sensitivity_function() {
        let mut widget = PolarDirectivityWidget::new();
        widget.selected_pattern = PolarPatternType::Cardioid;

        // Front 0 rad (cos=1) -> sens = 1.0
        let s_front = widget.sensitivity_at_angle(0.0);
        assert!((s_front - 1.0).abs() < 1e-4);

        // Rear PI rad (cos=-1) -> sens = 0.0
        let s_rear = widget.sensitivity_at_angle(PI);
        assert!(s_rear < 1e-4);
    }
}
