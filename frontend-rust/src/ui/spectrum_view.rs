//! Real-Time FFT Spectral Energy Distribution View.

use super::theme::Theme;
use egui::{Color32, Margin, Rounding, Stroke, Ui};
use egui_plot::{Line, Plot, PlotPoints, VLine};

pub struct SpectrumView;

impl SpectrumView {
    pub fn show(
        ui: &mut Ui,
        freq_bins: &[f64],
        enhanced_db: &[f64],
        raw_db: Option<&[f64]>,
        plot_height: f32,
    ) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("●")
                            .color(Theme::ACCENT_CYAN)
                            .size(11.0),
                    );
                    ui.label(
                        egui::RichText::new("FREQUENCY SPECTRUM (0–8 kHz FFT)")
                            .strong()
                            .size(12.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(
                            egui::RichText::new("512-pt · 31.25 Hz/bin")
                                .size(10.0)
                                .color(Theme::TEXT_MUTED),
                        );
                        // Mini legend
                        ui.label(
                            egui::RichText::new("Enhanced")
                                .size(10.0)
                                .color(Theme::ACCENT_CYAN),
                        );
                        ui.label(egui::RichText::new("—").color(Theme::ACCENT_CYAN));
                        ui.add_space(6.0);
                        ui.label(
                            egui::RichText::new("Raw")
                                .size(10.0)
                                .color(Theme::ACCENT_AMBER),
                        );
                        ui.label(egui::RichText::new("—").color(Theme::ACCENT_AMBER));
                        ui.add_space(8.0);
                        ui.label(
                            egui::RichText::new("Zone: 0.3–3.4 kHz Voice Band")
                                .size(10.0)
                                .color(Theme::TEXT_MUTED),
                        );
                    });
                });

                ui.add_space(4.0);

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
                        // Tactical Voice Formant Boundary Markers
                        let marker_stroke =
                            Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(80, 110, 150, 60));
                        plot_ui.vline(
                            VLine::new(300.0)
                                .stroke(marker_stroke)
                                .name("300 Hz High-Pass Barrier"),
                        );
                        plot_ui.vline(
                            VLine::new(3400.0)
                                .stroke(marker_stroke)
                                .name("3.4 kHz Formant Boundary"),
                        );

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

                        // Render enhanced spectrum in cyan with soft fill
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
            });
    }
}
