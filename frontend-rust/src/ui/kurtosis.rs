//! Spectral Kurtosis (SK) & Crest Factor Diagnostic HUD Widget.
//!
//! Visualizes real-time 4th-order spectral non-Gaussianity across 32 frequency bands,
//! displays time-domain Crest Factor (dB), and provides real-time warning indicators
//! for combat shock transients (gunfire, artillery detonations, supersonic bullet cracks)
//! with interactive simulation triggers.

use super::theme::Theme;
use anc_rust::dsp::{KurtosisTelemetry, KURTOSIS_HUD_BANDS};
use egui::{Color32, Frame, Margin, Pos2, Rect, Rounding, Sense, Stroke, Ui, Vec2};

/// Number of display bands on the Diagnostic HUD.
pub const HUD_BANDS: usize = KURTOSIS_HUD_BANDS;

/// Real-Time Spectral Kurtosis & Crest Factor HUD Widget.
pub struct SpectralKurtosisWidget {
    pub bands: [f32; HUD_BANDS],
    pub peak_kurtosis: f32,
    pub mean_kurtosis: f32,
    pub crest_factor_db: f32,
    pub peak_frequency_hz: f32,
    pub is_shock: bool,
    pub shock_decay: f32,
    pub shock_event_count: u64,
}

impl Default for SpectralKurtosisWidget {
    fn default() -> Self {
        Self::new()
    }
}

impl SpectralKurtosisWidget {
    /// Creates a new SpectralKurtosisWidget.
    pub fn new() -> Self {
        Self {
            bands: [0.0; HUD_BANDS],
            peak_kurtosis: 0.1,
            mean_kurtosis: 0.05,
            crest_factor_db: 9.0,
            peak_frequency_hz: 1000.0,
            is_shock: false,
            shock_decay: 0.0,
            shock_event_count: 0,
        }
    }

    /// Ingests real-time telemetry from the DSP Spectral Kurtosis Detector.
    pub fn update_from_telemetry(&mut self, telem: &KurtosisTelemetry) {
        self.bands.copy_from_slice(&telem.hud_band_kurtosis);
        self.peak_kurtosis = telem.peak_kurtosis;
        self.mean_kurtosis = telem.mean_kurtosis;
        self.crest_factor_db = telem.crest_factor_db;
        self.peak_frequency_hz = telem.peak_frequency_hz;
        if telem.is_shock_transient {
            self.is_shock = true;
            self.shock_decay = 1.0;
            self.shock_event_count += 1;
        }
    }

    /// Advances internal decay timer for visual alert pulses.
    pub fn tick(&mut self, dt: f32) {
        if self.shock_decay > 0.0 {
            self.shock_decay = (self.shock_decay - dt * 2.5).max(0.0);
            if self.shock_decay == 0.0 {
                self.is_shock = false;
            }
        }
    }

    /// Injects test transient signals for demonstration and validation.
    pub fn inject_test_signal(&mut self, scenario: &str) {
        match scenario {
            "gunfire" => {
                // Wideband massive non-Gaussian impulsive blast
                for (i, b) in self.bands.iter_mut().enumerate() {
                    let f_factor = 1.0 - (i as f32 / HUD_BANDS as f32) * 0.4;
                    *b = 24.0 * f_factor;
                }
                self.peak_kurtosis = 28.5;
                self.mean_kurtosis = 18.2;
                self.crest_factor_db = 19.4;
                self.peak_frequency_hz = 650.0;
                self.is_shock = true;
                self.shock_decay = 1.0;
                self.shock_event_count += 1;
            }
            "crack" => {
                // Supersonic bullet crack (high frequency N-wave shock)
                for (i, b) in self.bands.iter_mut().enumerate() {
                    if i > 16 {
                        *b = 18.0 + ((i - 16) as f32 * 0.8);
                    } else {
                        *b = 1.5;
                    }
                }
                self.peak_kurtosis = 22.0;
                self.mean_kurtosis = 9.8;
                self.crest_factor_db = 16.5;
                self.peak_frequency_hz = 4200.0;
                self.is_shock = true;
                self.shock_decay = 1.0;
                self.shock_event_count += 1;
            }
            "gaussian" => {
                // Stationary Gaussian thermal / ambient noise
                for b in self.bands.iter_mut() {
                    *b = 0.15;
                }
                self.peak_kurtosis = 0.4;
                self.mean_kurtosis = 0.15;
                self.crest_factor_db = 8.8;
                self.peak_frequency_hz = 250.0;
                self.is_shock = false;
                self.shock_decay = 0.0;
            }
            _ => {
                self.reset();
            }
        }
    }

    /// Resets monitor to clean state.
    pub fn reset(&mut self) {
        self.bands.fill(0.0);
        self.peak_kurtosis = 0.0;
        self.mean_kurtosis = 0.0;
        self.crest_factor_db = 0.0;
        self.peak_frequency_hz = 0.0;
        self.is_shock = false;
        self.shock_decay = 0.0;
    }

    /// Renders the Spectral Kurtosis & Crest Factor HUD widget.
    pub fn show(&mut self, ui: &mut Ui, height: f32) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Header row
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("SPECTRAL KURTOSIS & CREST FACTOR HUD")
                            .size(11.5)
                            .strong()
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (alert_color, alert_text) = if self.is_shock || self.shock_decay > 0.1 {
                            (Color32::from_rgb(255, 45, 85), "BLAST SHOCK DETECTED")
                        } else if self.peak_kurtosis > 4.0 {
                            (Theme::ACCENT_AMBER, "NON-STATIONARY TRANSIENT")
                        } else {
                            (Theme::ACCENT_CYAN, "GAUSSIAN STATIONARY")
                        };

                        ui.label(
                            egui::RichText::new(alert_text)
                                .size(10.0)
                                .strong()
                                .color(alert_color),
                        );
                        ui.label(egui::RichText::new("●").size(9.0).color(alert_color));
                    });
                });

                ui.add_space(6.0);

                // Telemetry metrics readout strip
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("Crest Factor:")
                            .size(10.0)
                            .color(Theme::TEXT_MUTED),
                    );
                    ui.label(
                        egui::RichText::new(format!("{:.1} dB", self.crest_factor_db))
                            .size(11.0)
                            .strong()
                            .color(if self.crest_factor_db > 14.0 {
                                Theme::ACCENT_RED
                            } else {
                                Theme::ACCENT_GREEN
                            }),
                    );

                    ui.add_space(8.0);
                    ui.label(
                        egui::RichText::new("Peak K(f):")
                            .size(10.0)
                            .color(Theme::TEXT_MUTED),
                    );
                    ui.label(
                        egui::RichText::new(format!("{:.1}", self.peak_kurtosis))
                            .size(11.0)
                            .strong()
                            .color(if self.peak_kurtosis > 10.0 {
                                Theme::ACCENT_RED
                            } else {
                                Theme::ACCENT_CYAN
                            }),
                    );

                    ui.add_space(8.0);
                    ui.label(
                        egui::RichText::new("Peak Freq:")
                            .size(10.0)
                            .color(Theme::TEXT_MUTED),
                    );
                    ui.label(
                        egui::RichText::new(format!("{:.0} Hz", self.peak_frequency_hz))
                            .size(11.0)
                            .color(Theme::TEXT_SECONDARY),
                    );

                    ui.add_space(8.0);
                    ui.label(
                        egui::RichText::new("Shocks Blocked:")
                            .size(10.0)
                            .color(Theme::TEXT_MUTED),
                    );
                    ui.label(
                        egui::RichText::new(format!("{}", self.shock_event_count))
                            .size(11.0)
                            .strong()
                            .color(Theme::ACCENT_AMBER),
                    );
                });

                ui.add_space(6.0);

                // 32-Band Bar Chart Display
                let (rect, _response) = ui.allocate_exact_size(
                    Vec2::new(ui.available_width(), height.max(70.0)),
                    Sense::hover(),
                );

                let painter = ui.painter_at(rect);
                // Background dark canvas
                painter.rect_filled(rect, Rounding::same(4.0), Color32::from_rgb(10, 14, 20));

                let w = rect.width();
                let h = rect.height();
                let bar_width = (w / HUD_BANDS as f32).max(2.0);
                let max_display_kurt = 30.0f32;

                // Threshold baseline indicators
                let shock_thresh_y = rect.bottom() - (10.0 / max_display_kurt) * h;

                // Draw 10.0 shock threshold dashed line
                painter.line_segment(
                    [
                        Pos2::new(rect.left(), shock_thresh_y),
                        Pos2::new(rect.right(), shock_thresh_y),
                    ],
                    Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(255, 45, 85, 90)),
                );

                // Draw 32 Kurtosis bars
                for (i, &kurt) in self.bands.iter().enumerate() {
                    let clamped_k = kurt.clamp(0.0, max_display_kurt);
                    let bar_h = (clamped_k / max_display_kurt) * (h - 4.0);
                    let x0 = rect.left() + (i as f32 * bar_width);
                    let x1 = x0 + bar_width - 1.0;
                    let y1 = rect.bottom() - 2.0;
                    let y0 = y1 - bar_h;

                    let bar_color = if clamped_k >= 10.0 {
                        Color32::from_rgb(255, 45, 85) // Red shock
                    } else if clamped_k >= 4.0 {
                        Color32::from_rgb(255, 180, 50) // Amber non-stationary
                    } else {
                        Color32::from_rgb(0, 190, 160) // Cyan/teal Gaussian
                    };

                    let bar_rect = Rect::from_min_max(Pos2::new(x0, y0), Pos2::new(x1, y1));
                    painter.rect_filled(bar_rect, Rounding::same(1.0), bar_color);
                }

                ui.add_space(6.0);

                // Interactive Diagnostic Simulation Controls
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("Simulate:")
                            .size(9.5)
                            .color(Theme::TEXT_MUTED),
                    );

                    if ui
                        .button(egui::RichText::new("💥 Gunfire Blast").size(9.5))
                        .clicked()
                    {
                        self.inject_test_signal("gunfire");
                    }
                    if ui
                        .button(egui::RichText::new("⚡ Supersonic Crack").size(9.5))
                        .clicked()
                    {
                        self.inject_test_signal("crack");
                    }
                    if ui
                        .button(egui::RichText::new("🌊 Gaussian Noise").size(9.5))
                        .clicked()
                    {
                        self.inject_test_signal("gaussian");
                    }
                    if ui
                        .button(egui::RichText::new("🔄 Reset").size(9.5))
                        .clicked()
                    {
                        self.inject_test_signal("reset");
                    }
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kurtosis_widget_initial_state() {
        let widget = SpectralKurtosisWidget::new();
        assert_eq!(widget.bands.len(), 32);
        assert!(!widget.is_shock);
        assert_eq!(widget.shock_event_count, 0);
    }

    #[test]
    fn test_kurtosis_widget_test_injection_and_decay() {
        let mut widget = SpectralKurtosisWidget::new();
        widget.inject_test_signal("gunfire");
        assert!(widget.is_shock);
        assert!(widget.peak_kurtosis > 20.0);
        assert_eq!(widget.shock_event_count, 1);

        // Tick 1.0 second: shock visual alert should decay
        widget.tick(1.0);
        assert!(!widget.is_shock);
    }
}
