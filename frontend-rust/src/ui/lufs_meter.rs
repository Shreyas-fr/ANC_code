//! Interactive ITU-R BS.1770-4 & EBU R128 Tactical Loudness Radar Widget.
//!
//! Provides a real-time tactical visualization of:
//! - Momentary Loudness (M, 400 ms sliding window)
//! - Short-Term Loudness (S, 3.0 s sliding window)
//! - Integrated Loudness (I, EBU R128 dual-gated)
//! - Loudness Range (LRA, EBU Tech 3342)
//! - Live True-Peak dBFS Bar & Peak-Hold Ceiling
//! - Dynamic Range Compression (DRC) Gain Reduction Curve
//! - Interactive Target LUFS Slider (-28 to -16 LUFS) with Tactical Presets

use egui::{Color32, Frame, Margin, Pos2, Rect, Rounding, Sense, Stroke, Ui, Vec2};
use std::f32::consts::PI;
use super::theme::Theme;
use anc_rust::network::EdgeTelemetry;

/// Number of rolling history points for dynamic gain reduction curve.
const GAIN_RED_HISTORY_LEN: usize = 64;

/// Interactive EBU R128 Tactical Loudness Radar & True-Peak Range Widget.
pub struct TacticalLufsRadarWidget {
    pub momentary_lufs: f32,
    pub short_term_lufs: f32,
    pub integrated_lufs: f32,
    pub loudness_range_lu: f32,
    pub true_peak_dbfs: f32,
    pub gain_reduction_db: f32,
    pub target_lufs: f32,
    gain_red_history: [f32; GAIN_RED_HISTORY_LEN],
    history_idx: usize,
    sweep_phase: f32,
}

impl Default for TacticalLufsRadarWidget {
    fn default() -> Self {
        Self::new()
    }
}

impl TacticalLufsRadarWidget {
    /// Creates a new TacticalLufsRadarWidget with default EBU R128 (-23 LUFS) target.
    pub fn new() -> Self {
        Self {
            momentary_lufs: -23.0,
            short_term_lufs: -23.0,
            integrated_lufs: -23.0,
            loudness_range_lu: 4.2,
            true_peak_dbfs: -3.5,
            gain_reduction_db: 0.0,
            target_lufs: -23.0,
            gain_red_history: [0.0; GAIN_RED_HISTORY_LEN],
            history_idx: 0,
            sweep_phase: 0.0,
        }
    }

    /// Ingests real-time telemetry from edge receiver.
    pub fn update_from_telemetry(&mut self, telem: &EdgeTelemetry) {
        if telem.momentary_lufs > -90.0 {
            self.momentary_lufs = telem.momentary_lufs;
        }
        if telem.short_term_lufs > -90.0 {
            self.short_term_lufs = telem.short_term_lufs;
        }
        if telem.integrated_lufs > -90.0 {
            self.integrated_lufs = telem.integrated_lufs;
        }
        self.loudness_range_lu = telem.loudness_range_lu.max(0.0);
        self.true_peak_dbfs = telem.true_peak_dbfs;
        self.gain_reduction_db = telem.lufs_gain_reduction_db;

        self.push_gain_reduction(telem.lufs_gain_reduction_db);
    }

    /// Pushes simulated or direct measurements into the widget.
    pub fn push_measurements(
        &mut self,
        momentary: f32,
        short_term: f32,
        integrated: f32,
        lra: f32,
        true_peak: f32,
        gain_reduction: f32,
    ) {
        self.momentary_lufs = momentary;
        self.short_term_lufs = short_term;
        self.integrated_lufs = integrated;
        self.loudness_range_lu = lra;
        self.true_peak_dbfs = true_peak;
        self.gain_reduction_db = gain_reduction;

        self.push_gain_reduction(gain_reduction);
    }

    fn push_gain_reduction(&mut self, gr: f32) {
        self.gain_red_history[self.history_idx] = gr;
        self.history_idx = (self.history_idx + 1) % GAIN_RED_HISTORY_LEN;
    }

    /// Dynamically sets the target LUFS.
    pub fn set_target_lufs(&mut self, target: f32) {
        self.target_lufs = target.clamp(-36.0, -12.0);
    }

    /// Maps LUFS [-48.0, -12.0] to a normalized radius [0.0, 1.0].
    #[inline]
    fn lufs_to_radius(lufs: f32) -> f32 {
        let clamped = lufs.clamp(-48.0, -12.0);
        (clamped - (-48.0)) / ((-12.0) - (-48.0))
    }

    /// Renders the interactive tactical LUFS radar widget.
    ///
    /// Returns `Some(new_target_lufs)` if user altered the target via slider or preset buttons.
    pub fn show(&mut self, ui: &mut Ui, height: f32) -> Option<f32> {
        let mut target_changed = None;
        self.sweep_phase = (self.sweep_phase + 0.03) % (2.0 * PI);

        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // 1. Header Bar
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("●").color(Theme::ACCENT_CYAN).size(11.0));
                    ui.label(
                        egui::RichText::new("ITU-R BS.1770-4 / EBU R128 LOUDNESS RADAR")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    let target_diff = (self.integrated_lufs - self.target_lufs).abs();
                    let (status_text, status_col) = if target_diff <= 1.0 {
                        ("EBU R128 PASS", Theme::ACCENT_GREEN)
                    } else if target_diff <= 3.0 {
                        ("GOVERNED", Theme::ACCENT_AMBER)
                    } else {
                        ("DEVIATING", Theme::ACCENT_RED)
                    };

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(
                            egui::RichText::new(status_text)
                                .size(9.5)
                                .strong()
                                .monospace()
                                .color(status_col),
                        );
                        ui.label(egui::RichText::new("·").size(10.0).color(Theme::TEXT_MUTED));
                        ui.label(
                            egui::RichText::new(format!("TARGET: {:.1} LUFS", self.target_lufs))
                                .size(9.5)
                                .monospace()
                                .color(Theme::ACCENT_AMBER),
                        );
                    });
                });

                ui.add_space(6.0);

                // 2. Main Content: Radar Dial (Left) + Meters & Controls (Right)
                let available_width = ui.available_width();
                let radar_diameter = (height - 38.0).min(available_width * 0.46).max(100.0);

                ui.horizontal(|ui| {
                    // Left Column: Radar Dial
                    let (rect_radar, _) = ui.allocate_exact_size(
                        Vec2::new(radar_diameter, radar_diameter),
                        Sense::hover(),
                    );
                    let painter = ui.painter_at(rect_radar);
                    let center = rect_radar.center();
                    let max_r = radar_diameter * 0.48;

                    // Concentric calibrated LUFS rings
                    let ring_levels = [-42.0f32, -36.0, -28.0, -23.0, -18.0, -14.0];
                    for &lvl in &ring_levels {
                        let r = max_r * Self::lufs_to_radius(lvl);
                        let is_target_ring = (lvl - self.target_lufs).abs() < 1.0;
                        let (stroke_col, stroke_w) = if is_target_ring {
                            (Theme::ACCENT_AMBER, 1.5_f32)
                        } else {
                            (Theme::BORDER_SUBTLE, 1.0_f32)
                        };
                        painter.circle_stroke(center, r, Stroke::new(stroke_w, stroke_col));

                        // Ring level text marker (top edge of ring)
                        let text_pos = Pos2::new(center.x, center.y - r + 3.0);
                        let label_str = format!("{:.0}", lvl);
                        painter.text(
                            text_pos,
                            egui::Align2::CENTER_CENTER,
                            label_str,
                            egui::FontId::monospace(7.5),
                            Theme::TEXT_MUTED,
                        );
                    }

                    // Rotating radar sweep glow line
                    let sweep_angle = self.sweep_phase;
                    let sweep_end = Pos2::new(
                        center.x + max_r * sweep_angle.cos(),
                        center.y + max_r * sweep_angle.sin(),
                    );
                    painter.line_segment(
                        [center, sweep_end],
                        Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(0, 229, 255, 40)),
                    );

                    // Loudness Range (LRA) bracket arc
                    let lra_half = (self.loudness_range_lu * 0.5).clamp(0.5, 12.0);
                    let lra_r_min = max_r * Self::lufs_to_radius(self.short_term_lufs - lra_half);
                    let lra_r_max = max_r * Self::lufs_to_radius(self.short_term_lufs + lra_half);
                    let lra_col = Color32::from_rgba_unmultiplied(168, 85, 247, 45); // Violet tint
                    painter.circle_stroke(
                        center,
                        (lra_r_min + lra_r_max) * 0.5,
                        Stroke::new((lra_r_max - lra_r_min).max(3.0), lra_col),
                    );

                    // Short-Term Loudness (S) Ring: Green solid
                    let r_s = max_r * Self::lufs_to_radius(self.short_term_lufs);
                    painter.circle_stroke(
                        center,
                        r_s,
                        Stroke::new(2.0_f32, Theme::ACCENT_GREEN),
                    );

                    // Momentary Loudness (M) Arc: Cyan bright
                    let r_m = max_r * Self::lufs_to_radius(self.momentary_lufs);
                    painter.circle_stroke(
                        center,
                        r_m,
                        Stroke::new(2.5_f32, Theme::ACCENT_CYAN),
                    );

                    // Target marker: Amber tick
                    let r_target = max_r * Self::lufs_to_radius(self.target_lufs);
                    painter.circle_stroke(
                        center,
                        r_target,
                        Stroke::new(1.5_f32, Theme::ACCENT_AMBER),
                    );

                    // Center Digital Readout
                    painter.text(
                        center,
                        egui::Align2::CENTER_CENTER,
                        format!("{:.1}\nLUFS", self.short_term_lufs),
                        egui::FontId::monospace(10.5),
                        Theme::ACCENT_CYAN,
                    );

                    ui.add_space(8.0);

                    // Right Column: Digital Badges, True-Peak Bar, Gain Reduction & Target Controls
                    ui.vertical(|ui| {
                        // Numeric Readout Grid
                        ui.horizontal(|ui| {
                            ui.label(
                                egui::RichText::new(format!("M: {:.1}", self.momentary_lufs))
                                    .size(9.5)
                                    .monospace()
                                    .color(Theme::ACCENT_CYAN),
                            );
                            ui.label(egui::RichText::new("·").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("S: {:.1}", self.short_term_lufs))
                                    .size(9.5)
                                    .monospace()
                                    .color(Theme::ACCENT_GREEN),
                            );
                            ui.label(egui::RichText::new("·").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("I: {:.1}", self.integrated_lufs))
                                    .size(9.5)
                                    .monospace()
                                    .color(Theme::ACCENT_VIOLET),
                            );
                            ui.label(egui::RichText::new("·").size(9.5).color(Theme::TEXT_MUTED));
                            ui.label(
                                egui::RichText::new(format!("LRA: {:.1} LU", self.loudness_range_lu))
                                    .size(9.5)
                                    .monospace()
                                    .color(Theme::TEXT_SECONDARY),
                            );
                        });

                        ui.add_space(4.0);

                        // True-Peak dBFS Bar
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("TRUE-PEAK:").size(9.0).color(Theme::TEXT_MUTED));
                            let (tp_bar_rect, _) = ui.allocate_exact_size(
                                Vec2::new(120.0, 10.0),
                                Sense::hover(),
                            );
                            let tp_painter = ui.painter_at(tp_bar_rect);
                            tp_painter.rect_filled(tp_bar_rect, Rounding::same(2.0), Theme::BG_VOID);

                            let tp_norm = ((self.true_peak_dbfs - (-36.0)) / 36.0).clamp(0.0, 1.0);
                            let filled_w = tp_bar_rect.width() * tp_norm;
                            let (bar_col, _) = if self.true_peak_dbfs > -0.5 {
                                (Theme::ACCENT_RED, "OVERLOAD")
                            } else if self.true_peak_dbfs > -3.0 {
                                (Theme::ACCENT_AMBER, "HOT")
                            } else {
                                (Theme::ACCENT_GREEN, "NOMINAL")
                            };
                            let fill_rect = Rect::from_min_size(tp_bar_rect.min, Vec2::new(filled_w, tp_bar_rect.height()));
                            tp_painter.rect_filled(fill_rect, Rounding::same(2.0), bar_col);

                            ui.label(
                                egui::RichText::new(format!("{:.1} dBFS", self.true_peak_dbfs))
                                    .size(9.0)
                                    .monospace()
                                    .color(bar_col),
                            );
                        });

                        ui.add_space(4.0);

                        // Dynamic Gain Reduction (DRC) Display & Sparkline
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("DRC GAIN:").size(9.0).color(Theme::TEXT_MUTED));
                            let (spark_rect, _) = ui.allocate_exact_size(
                                Vec2::new(120.0, 12.0),
                                Sense::hover(),
                            );
                            let spark_painter = ui.painter_at(spark_rect);
                            spark_painter.rect_filled(spark_rect, Rounding::same(2.0), Theme::BG_VOID);

                            // Draw baseline 0 dB line (center)
                            let mid_y = spark_rect.center().y;
                            spark_painter.line_segment(
                                [Pos2::new(spark_rect.min.x, mid_y), Pos2::new(spark_rect.max.x, mid_y)],
                                Stroke::new(1.0_f32, Theme::BORDER_SUBTLE),
                            );

                            // Render rolling gain reduction curve
                            let step_x = spark_rect.width() / (GAIN_RED_HISTORY_LEN - 1) as f32;
                            let mut prev_pt = None;
                            for i in 0..GAIN_RED_HISTORY_LEN {
                                let hist_i = (self.history_idx + i) % GAIN_RED_HISTORY_LEN;
                                let gr_val = self.gain_red_history[hist_i]; // -18 dB to +12 dB
                                let y_offset = (gr_val / 18.0) * (spark_rect.height() * 0.45);
                                let pt = Pos2::new(
                                    spark_rect.min.x + i as f32 * step_x,
                                    (mid_y - y_offset).clamp(spark_rect.min.y, spark_rect.max.y),
                                );
                                if let Some(prev) = prev_pt {
                                    let curve_col = if gr_val < -0.1 {
                                        Theme::ACCENT_CYAN
                                    } else if gr_val > 0.1 {
                                        Theme::ACCENT_AMBER
                                    } else {
                                        Theme::TEXT_MUTED
                                    };
                                    spark_painter.line_segment([prev, pt], Stroke::new(1.2_f32, curve_col));
                                }
                                prev_pt = Some(pt);
                            }

                            let gr_label = format!("{:+.1} dB", self.gain_reduction_db);
                            let gr_col = if self.gain_reduction_db < -0.5 {
                                Theme::ACCENT_CYAN
                            } else if self.gain_reduction_db > 0.5 {
                                Theme::ACCENT_AMBER
                            } else {
                                Theme::TEXT_SECONDARY
                            };
                            ui.label(egui::RichText::new(gr_label).size(9.0).monospace().color(gr_col));
                        });

                        ui.add_space(4.0);

                        // Interactive Target LUFS Slider & Tactical Mission Presets
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("TARGET:").size(9.0).color(Theme::TEXT_MUTED));
                            let slider = egui::Slider::new(&mut self.target_lufs, -28.0..=-16.0)
                                .step_by(0.5)
                                .suffix(" LUFS")
                                .show_value(true);
                            if ui.add_sized([115.0, 16.0], slider).changed() {
                                target_changed = Some(self.target_lufs);
                            }

                            // Quick tactical preset buttons
                            if ui.button(egui::RichText::new("EBU (-23)").size(8.5)).clicked() {
                                self.target_lufs = -23.0;
                                target_changed = Some(-23.0);
                            }
                            if ui.button(egui::RichText::new("TAC (-18)").size(8.5)).clicked() {
                                self.target_lufs = -18.0;
                                target_changed = Some(-18.0);
                            }
                            if ui.button(egui::RichText::new("RECON (-26)").size(8.5)).clicked() {
                                self.target_lufs = -26.0;
                                target_changed = Some(-26.0);
                            }
                        });
                    });
                });
            });

        target_changed
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lufs_radar_widget_initialization() {
        let widget = TacticalLufsRadarWidget::new();
        assert_eq!(widget.target_lufs, -23.0);
        assert_eq!(widget.momentary_lufs, -23.0);
        assert_eq!(widget.gain_reduction_db, 0.0);
    }

    #[test]
    fn test_lufs_radar_widget_push_measurements() {
        let mut widget = TacticalLufsRadarWidget::new();
        widget.push_measurements(-18.5, -20.2, -21.0, 5.1, -1.2, -3.4);

        assert_eq!(widget.momentary_lufs, -18.5);
        assert_eq!(widget.short_term_lufs, -20.2);
        assert_eq!(widget.integrated_lufs, -21.0);
        assert_eq!(widget.loudness_range_lu, 5.1);
        assert_eq!(widget.true_peak_dbfs, -1.2);
        assert_eq!(widget.gain_reduction_db, -3.4);
    }

    #[test]
    fn test_lufs_radar_widget_presets() {
        let mut widget = TacticalLufsRadarWidget::new();
        widget.set_target_lufs(-18.0);
        assert_eq!(widget.target_lufs, -18.0);
        widget.set_target_lufs(-26.0);
        assert_eq!(widget.target_lufs, -26.0);
    }
}
