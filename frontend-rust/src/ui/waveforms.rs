//! Real-Time Rolling Waveform Visualizer using egui_plot.

use egui::{Color32, Ui};
use egui_plot::{Line, Plot, PlotPoints};
use std::collections::VecDeque;
use super::theme::Theme;

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
        ui.horizontal(|ui| {
            ui.label(egui::RichText::new("●").color(color).size(12.0));
            ui.label(egui::RichText::new(title).strong().color(Theme::TEXT_PRIMARY));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.label(
                    egui::RichText::new(format!("{} · 16 kHz", port_label))
                        .size(10.0)
                        .color(Theme::TEXT_SECONDARY),
                );
            });
        });

        let dt = self.downsample_factor as f64 / self.sample_rate as f64;
        let total_time = self.max_samples as f64 / self.sample_rate as f64;

        let points: PlotPoints = self
            .samples
            .iter()
            .step_by(self.downsample_factor)
            .enumerate()
            .map(|(i, &s)| [i as f64 * dt - total_time, s as f64])
            .collect();

        let line = Line::new(points)
            .color(color)
            .width(1.5_f32);

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
    }
}
