//! Real-Time FFT Spectral Energy Distribution View.

use egui::Ui;
use egui_plot::{Line, Plot, PlotPoints};
use super::theme::Theme;

pub struct SpectrumView;

impl SpectrumView {
    pub fn show(
        ui: &mut Ui,
        freq_bins: &[f64],
        enhanced_db: &[f64],
        raw_db: Option<&[f64]>,
        plot_height: f32,
    ) {
        ui.horizontal(|ui| {
            ui.label(egui::RichText::new("●").color(Theme::ACCENT_CYAN).size(12.0));
            ui.label(
                egui::RichText::new("LIVE FREQUENCY SPECTRUM (0–8 kHz)")
                    .strong()
                    .color(Theme::TEXT_PRIMARY),
            );
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.label(
                    egui::RichText::new("512-pt FFT · 31.25 Hz/bin")
                        .size(10.0)
                        .color(Theme::TEXT_SECONDARY),
                );
            });
        });

        Plot::new("spectrum_plot")
            .height(plot_height)
            .include_x(0.0)
            .include_x(8000.0)
            .include_y(0.0)
            .include_y(-90.0)
            .show_axes([true, true])
            .show_grid(true)
            .x_axis_label("Frequency (Hz)")
            .y_axis_label("Magnitude (dBFS)")
            .allow_drag(false)
            .allow_zoom(false)
            .allow_scroll(false)
            .show(ui, |plot_ui| {
                // If raw spectrum is available, render in amber
                if let Some(raw) = raw_db {
                    let raw_points: PlotPoints = freq_bins
                        .iter()
                        .zip(raw.iter())
                        .map(|(&f, &db)| [f, db])
                        .collect();

                    let raw_line = Line::new(raw_points)
                        .color(Theme::ACCENT_AMBER)
                        .width(1.2_f32)
                        .name("Raw Input");
                    plot_ui.line(raw_line);
                }

                // Render enhanced spectrum in cyan with fill
                let enh_points: PlotPoints = freq_bins
                    .iter()
                    .zip(enhanced_db.iter())
                    .map(|(&f, &db)| [f, db])
                    .collect();

                let enh_line = Line::new(enh_points)
                    .color(Theme::ACCENT_CYAN)
                    .width(1.8_f32)
                    .fill(-90.0_f32)
                    .name("Enhanced Output");
                plot_ui.line(enh_line);
            });
    }
}
