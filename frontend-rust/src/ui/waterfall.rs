//! 2D Scrolling Waterfall Spectrogram Display.
//!
//! Renders a real-time time-frequency-energy waterfall heatmap (0–8 kHz)
//! styled in high-contrast tactical military phosphor/plasma colors.

use super::theme::Theme;
use egui::{Color32, Margin, Pos2, Rect, Rounding, Stroke, Ui, Vec2};

/// 2D Scrolling Waterfall Spectrogram Buffer.
pub struct WaterfallSpectrogram {
    /// Circular buffer of historical spectrum frames [history_len][num_bands]
    history: Vec<Vec<f32>>,
    max_history: usize,
    num_bands: usize,
}

impl WaterfallSpectrogram {
    pub fn new(max_history: usize, num_bands: usize) -> Self {
        Self {
            history: Vec::with_capacity(max_history),
            max_history,
            num_bands,
        }
    }

    /// Pushes a new FFT magnitude frame (dBFS) into the waterfall history.
    pub fn push_frame(&mut self, spectrum_db: &[f64]) {
        if spectrum_db.is_empty() {
            return;
        }

        let mut band_energies = vec![-90.0f32; self.num_bands];
        let bins_per_band = spectrum_db.len() as f32 / self.num_bands as f32;

        for (b, energy) in band_energies.iter_mut().enumerate() {
            let start = (b as f32 * bins_per_band) as usize;
            let end = (((b + 1) as f32 * bins_per_band) as usize).min(spectrum_db.len());
            if start < end {
                let max_in_band = spectrum_db[start..end]
                    .iter()
                    .fold(-120.0f64, |m, &v| m.max(v));
                *energy = max_in_band as f32;
            }
        }

        if self.history.len() >= self.max_history {
            self.history.remove(0);
        }
        self.history.push(band_energies);
    }

    /// Maps dBFS magnitude (-90 to 0 dBFS) to tactical color.
    fn db_to_tactical_color(db: f32) -> Color32 {
        if db <= -75.0 {
            Color32::from_rgb(8, 14, 24)
        } else if db <= -55.0 {
            let t = (db + 75.0) / 20.0;
            Color32::from_rgb(
                (8.0 + t * 4.0) as u8,
                (14.0 + t * 50.0) as u8,
                (24.0 + t * 70.0) as u8,
            )
        } else if db <= -35.0 {
            let t = (db + 55.0) / 20.0;
            Color32::from_rgb(
                (12.0 + t * 10.0) as u8,
                (64.0 + t * 150.0) as u8,
                (94.0 + t * 24.0) as u8,
            )
        } else if db <= -18.0 {
            let t = (db + 35.0) / 17.0;
            Color32::from_rgb(
                (22.0 + t * 230.0) as u8,
                (214.0 - t * 35.0) as u8,
                (118.0 - t * 100.0) as u8,
            )
        } else {
            let t = ((db + 18.0) / 18.0).clamp(0.0, 1.0);
            Color32::from_rgb(
                255,
                (179.0 * (1.0 - t * 0.7)) as u8,
                (50.0 * (1.0 - t)) as u8,
            )
        }
    }

    /// Renders the 2D scrolling waterfall display.
    pub fn show(&self, ui: &mut Ui, height: f32) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("●")
                            .color(Theme::ACCENT_VIOLET)
                            .size(11.0),
                    );
                    ui.label(
                        egui::RichText::new("2D TACTICAL SPECTRAL WATERFALL")
                            .strong()
                            .size(12.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(
                            egui::RichText::new("Time-Frequency Energy Heatmap (0–8 kHz)")
                                .size(10.0)
                                .color(Theme::TEXT_MUTED),
                        );
                        // Mini gradient legend
                        ui.label(
                            egui::RichText::new("Peak")
                                .size(9.5)
                                .color(Theme::ACCENT_RED),
                        );
                        ui.label(
                            egui::RichText::new("High")
                                .size(9.5)
                                .color(Theme::ACCENT_AMBER),
                        );
                        ui.label(
                            egui::RichText::new("Voice")
                                .size(9.5)
                                .color(Theme::ACCENT_GREEN),
                        );
                        ui.label(
                            egui::RichText::new("Noise")
                                .size(9.5)
                                .color(Theme::ACCENT_CYAN),
                        );
                        ui.label(
                            egui::RichText::new("Floor")
                                .size(9.5)
                                .color(Theme::TEXT_MUTED),
                        );
                    });
                });

                ui.add_space(4.0);

                let available_width = ui.available_width();
                let (rect, _) = ui
                    .allocate_exact_size(Vec2::new(available_width, height), egui::Sense::hover());

                if self.history.is_empty() {
                    ui.painter()
                        .rect_filled(rect, Rounding::same(4.0), Theme::BG_VOID);
                    return;
                }

                let _num_frames = self.history.len();
                let dx = rect.width() / self.max_history as f32;
                let dy = rect.height() / self.num_bands as f32;

                // Draw background
                ui.painter()
                    .rect_filled(rect, Rounding::same(4.0), Theme::BG_VOID);

                // Render heatmap cells
                for (frame_idx, frame) in self.history.iter().enumerate() {
                    let x = rect.left() + (frame_idx as f32 * dx);
                    for (b, &db) in frame.iter().enumerate() {
                        // Invert Y so low frequencies are at the bottom, high at top
                        let y = rect.bottom() - ((b + 1) as f32 * dy);
                        let cell_rect =
                            Rect::from_min_size(Pos2::new(x, y), Vec2::new(dx + 0.5, dy + 0.5));
                        let color = Self::db_to_tactical_color(db);
                        ui.painter().rect_filled(cell_rect, Rounding::ZERO, color);
                    }
                }

                // Overlay 300 Hz and 3.4 kHz horizontal tactical guide lines
                // 300 Hz / 8000 Hz = 3.75% of height from bottom
                let y_300 = rect.bottom() - (0.0375 * rect.height());
                ui.painter().line_segment(
                    [
                        Pos2::new(rect.left(), y_300),
                        Pos2::new(rect.right(), y_300),
                    ],
                    Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(80, 110, 150, 90)),
                );

                // 3.4 kHz / 8000 Hz = 42.5% of height from bottom
                let y_3400 = rect.bottom() - (0.425 * rect.height());
                ui.painter().line_segment(
                    [
                        Pos2::new(rect.left(), y_3400),
                        Pos2::new(rect.right(), y_3400),
                    ],
                    Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(80, 110, 150, 90)),
                );
            });
    }
}
