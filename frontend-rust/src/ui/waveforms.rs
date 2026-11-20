//! Real-Time Rolling Waveform Visualizer using egui_plot.

use super::theme::Theme;
use egui::{Color32, Margin, Rounding, Stroke, Ui};
use egui_plot::{Line, Plot, PlotPoints};
use std::collections::VecDeque;

pub struct RollingWaveform {
    samples: VecDeque<f32>,
    max_samples: usize,
    sample_rate: f32,
    downsample_factor: usize,
}

impl RollingWaveform {
    pub fn new(max_seconds: f32, sample_rate: f32) -> Self {
        let max_samples = (max_seconds * sample_rate) as usize;
        let mut samples = VecDeque::with_capacity(max_samples);
        samples.resize(max_samples, 0.0);

        Self {
            samples,
            max_samples,
            sample_rate,
            downsample_factor: 16, // Downsample for 60 FPS silky smooth UI rendering
        }
    }

    pub fn push_samples(&mut self, new_samples: &[f32]) {
        for &s in new_samples {
            if self.samples.len() >= self.max_samples {
                self.samples.pop_front();
            }
            self.samples.push_back(s);
        }
    }

    pub fn clear(&mut self) {
        self.samples.clear();
        self.samples.resize(self.max_samples, 0.0);
    }

    pub fn samples_vec(&self) -> Vec<f32> {
        self.samples.iter().cloned().collect()
    }

    pub fn show(
        &self,
        ui: &mut Ui,
        title: &str,
        port_label: &str,
        color: Color32,
        plot_height: f32,
    ) {
        let peak_abs = self.samples.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        let peak_db = 20.0 * peak_abs.max(1e-4).log10();

        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("●").color(color).size(11.0));
                    ui.label(
                        egui::RichText::new(title)
                            .strong()
                            .size(12.0)
                            .color(Theme::TEXT_PRIMARY),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let peak_color = if peak_db > -3.0 {
                            Theme::ACCENT_AMBER
                        } else {
                            Theme::TEXT_SECONDARY
                        };
                        ui.label(
                            egui::RichText::new(format!("{:.1} dBFS", peak_db))
                                .size(10.5)
                                .strong()
                                .color(peak_color),
                        );

                        // 6-Segment Tactical LED Peak Meter
                        ui.horizontal(|ui| {
                            let thresholds = [-36.0, -24.0, -18.0, -12.0, -6.0, -1.0];
                            let colors = [
                                Color32::from_rgb(0, 180, 80),
                                Color32::from_rgb(0, 210, 90),
                                Color32::from_rgb(0, 230, 118),
                                Color32::from_rgb(0, 255, 140),
                                Theme::ACCENT_AMBER,
                                Theme::ACCENT_RED,
                            ];
                            for (&th, &col) in thresholds.iter().zip(colors.iter()) {
                                let is_lit = peak_db >= th;
                                let lit_color = if is_lit {
                                    col
                                } else {
                                    Color32::from_rgb(22, 30, 48)
                                };
                                let (rect, _) = ui.allocate_exact_size(
                                    egui::vec2(5.0, 9.0),
                                    egui::Sense::hover(),
                                );
                                ui.painter()
                                    .rect_filled(rect, Rounding::same(1.5), lit_color);
                                ui.add_space(1.5);
                            }
                        });

                        ui.add_space(6.0);
                        ui.label(
                            egui::RichText::new(format!("{} · 16 kHz", port_label))
                                .size(10.0)
                                .color(Theme::TEXT_MUTED),
                        );
                    });
                });

                ui.add_space(4.0);

                let dt = self.downsample_factor as f64 / self.sample_rate as f64;
                let total_time = self.max_samples as f64 / self.sample_rate as f64;

                let points: PlotPoints = self
                    .samples
                    .iter()
                    .step_by(self.downsample_factor)
                    .enumerate()
                    .map(|(i, &s)| [i as f64 * dt - total_time, s as f64])
                    .collect();

                let line = Line::new(points).color(color).width(1.5_f32).fill(0.0_f32);

                Plot::new(title)
                    .height(plot_height)
                    .include_y(1.0)
                    .include_y(-1.0)
                    .show_axes([false, true])
                    .show_grid(true)
                    .allow_drag(false)
                    .allow_zoom(false)
                    .allow_scroll(false)
                    .show(ui, |plot_ui| {
                        plot_ui.line(line);
                    });
            });
    }
}
