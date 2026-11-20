//! Interactive In-Headset Audiogram Hearing Test Wizard.
//!
//! Provides an onboard pure-tone audiometry diagnostic wizard:
//! - Generates calibrated test tones at 500 Hz, 1 kHz, 2 kHz, 4 kHz, 6 kHz, 8 kHz.
//! - Tests Left and Right ear Hearing Threshold Levels (HTL in dB HL).
//! - Visualizes clinical audiogram curve (inverted dB HL scale with normal/mild/severe zones).
//! - Includes presets for acoustic trauma (4 kHz gunfire notch, tank crew NIHL).
//! - "PROGRAM DSP WDRC" action instantly calibrates the NAL-NL2 dynamic compressor.

use eframe::egui::{self, Color32, Pos2, Rect, Stroke, Vec2};
use crate::ui::theme::Theme;
pub use anc_rust::dsp::audiogram::{Ear, PersonalAudiogram, AUDIOMETRIC_FREQUENCIES, NUM_AUDIOMETRIC_BANDS};

/// Wizard test frequencies subset for quick in-headset triage.
pub const WIZARD_FREQUENCIES: [f32; 6] = [500.0, 1000.0, 2000.0, 4000.0, 6000.0, 8000.0];

/// Interactive In-Headset Audiometry Testing Wizard.
#[derive(Debug, Clone)]
pub struct AudiogramTestWizard {
    pub audiogram: PersonalAudiogram,
    pub selected_ear: Ear,
    pub current_freq_idx: usize,
    pub is_tone_playing: bool,
    pub tone_phase: f32,
    pub tone_duration_sec: f32,
    pub is_wizard_open: bool,
}

impl Default for AudiogramTestWizard {
    fn default() -> Self {
        Self {
            audiogram: PersonalAudiogram::normal(),
            selected_ear: Ear::Left,
            current_freq_idx: 1, // Start at 1 kHz standard reference
            is_tone_playing: false,
            tone_phase: 0.0,
            tone_duration_sec: 0.0,
            is_wizard_open: false,
        }
    }
}

impl AudiogramTestWizard {
    pub fn new() -> Self {
        Self::default()
    }

    /// Advances the pulsed test tone generator by `dt` seconds.
    /// Injects audio samples into `buffer` if tone is actively playing.
    pub fn generate_test_tone(&mut self, buffer: &mut [f32], sample_rate: f32) {
        if !self.is_tone_playing {
            return;
        }

        let freq = WIZARD_FREQUENCIES[self.current_freq_idx];
        let htl = match self.selected_ear {
            Ear::Left => self.audiogram.htl_left[self.band_index_for_freq(freq)],
            Ear::Right => self.audiogram.htl_right[self.band_index_for_freq(freq)],
        };

        // Calibrated amplitude from dB HL: 0 dB HL ~ -45 dBFS, 60 dB HL ~ -15 dBFS
        let dbfs = -45.0 + (htl * 0.50);
        let linear_gain = 10.0f32.powf(dbfs / 20.0).clamp(0.001, 0.85);

        let dt = buffer.len() as f32 / sample_rate;
        self.tone_duration_sec += dt;

        // Auto-stop after 1.5s pulse
        if self.tone_duration_sec >= 1.5 {
            self.is_tone_playing = false;
            self.tone_duration_sec = 0.0;
            return;
        }

        let phase_inc = 2.0 * std::f32::consts::PI * freq / sample_rate;
        for s in buffer.iter_mut() {
            let tone = self.tone_phase.sin() * linear_gain;
            self.tone_phase += phase_inc;
            if self.tone_phase > 2.0 * std::f32::consts::PI {
                self.tone_phase -= 2.0 * std::f32::consts::PI;
            }
            *s += tone;
        }
    }

    /// Maps a wizard frequency (500 Hz..8 kHz) to the 8-band audiogram index.
    pub fn band_index_for_freq(&self, freq: f32) -> usize {
        match freq as u32 {
            250 => 0,
            500 => 1,
            1000 => 2,
            2000 => 3,
            3000 => 4,
            4000 => 5,
            6000 => 6,
            8000 => 7,
            _ => 2,
        }
    }

    /// Renders the interactive in-headset audiometry wizard.
    /// Returns `Some(PersonalAudiogram)` when the operator clicks "PROGRAM DSP WDRC".
    pub fn show(&mut self, ui: &mut egui::Ui, height: f32) -> Option<PersonalAudiogram> {
        let mut programmed_audiogram = None;

        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(egui::Margin::same(10.0))
            .show(ui, |ui| {
                // Header
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("🩺").color(Theme::ACCENT_CYAN).size(13.0));
                    ui.label(
                        egui::RichText::new("IN-HEADSET AUDIOMETRY & NIHL COMPENSATOR")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        // Ear toggle
                        let (ear_label, ear_col) = match self.selected_ear {
                            Ear::Left => ("EAR: LEFT (BLUE 'X')", Theme::ACCENT_CYAN),
                            Ear::Right => ("EAR: RIGHT (RED 'O')", Theme::ACCENT_RED),
                        };
                        if ui.button(egui::RichText::new(ear_label).size(10.0).strong().color(ear_col)).clicked() {
                            self.selected_ear = match self.selected_ear {
                                Ear::Left => Ear::Right,
                                Ear::Right => Ear::Left,
                            };
                        }

                        // Presets menu
                        egui::ComboBox::from_id_salt("audiogram_preset_combo")
                            .selected_text(egui::RichText::new("PRESETS").size(10.0).color(Theme::TEXT_SECONDARY))
                            .show_ui(ui, |ui| {
                                if ui.selectable_label(false, "Normal Hearing (0 dB HL)").clicked() {
                                    self.audiogram = PersonalAudiogram::normal();
                                }
                                if ui.selectable_label(false, "Gunfire / 4 kHz Blast Dip").clicked() {
                                    self.audiogram = PersonalAudiogram::mild_4khz_notch();
                                }
                                if ui.selectable_label(false, "Severe Artillery Blast Trauma").clicked() {
                                    self.audiogram = PersonalAudiogram::severe_artillery_blast();
                                }
                                if ui.selectable_label(false, "Tank Crew High-Noise NIHL").clicked() {
                                    self.audiogram = PersonalAudiogram::tank_crew_nihl();
                                }
                            });
                    });
                });

                ui.add_space(6.0);

                // Split into: Left Side (Audiogram Graph) and Right Side (Wizard Controls)
                ui.columns(2, |cols| {
                    // Column 0: Audiogram Clinical Graph
                    let (graph_rect, _resp) = cols[0].allocate_exact_size(
                        Vec2::new(cols[0].available_width(), height.max(120.0)),
                        egui::Sense::hover(),
                    );
                    self.paint_audiogram_graph(&cols[0], graph_rect);

                    // Column 1: Test Controls & Program Button
                    cols[1].vertical(|ui| {
                        let cur_freq = WIZARD_FREQUENCIES[self.current_freq_idx];
                        let band_idx = self.band_index_for_freq(cur_freq);

                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new(format!("FREQ: {:.0} Hz", cur_freq)).strong().size(11.0).color(Theme::ACCENT_AMBER));
                            if ui.button(egui::RichText::new("◀").size(10.0)).clicked() && self.current_freq_idx > 0 {
                                self.current_freq_idx -= 1;
                            }
                            if ui.button(egui::RichText::new("▶").size(10.0)).clicked() && self.current_freq_idx < WIZARD_FREQUENCIES.len() - 1 {
                                self.current_freq_idx += 1;
                            }
                        });

                        // Current Threshold Slider (0 to 80 dB HL)
                        let mut cur_htl = match self.selected_ear {
                            Ear::Left => self.audiogram.htl_left[band_idx],
                            Ear::Right => self.audiogram.htl_right[band_idx],
                        };

                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("THRESHOLD:").size(10.0).color(Theme::TEXT_MUTED));
                            ui.label(egui::RichText::new(format!("{:.0} dB HL", cur_htl)).strong().size(10.5).color(Theme::TEXT_PRIMARY));
                        });

                        if ui.add(egui::Slider::new(&mut cur_htl, 0.0..=80.0).step_by(5.0).show_value(false)).changed() {
                            self.audiogram.set_htl(self.selected_ear, band_idx, cur_htl);
                        }

                        // Test Tone Trigger
                        ui.horizontal(|ui| {
                            let (play_lbl, play_col) = if self.is_tone_playing {
                                ("⏹ PLAYING TONE...", Theme::ACCENT_RED)
                            } else {
                                ("▶ PLAY TEST TONE", Theme::ACCENT_GREEN)
                            };

                            if ui.button(egui::RichText::new(play_lbl).size(10.5).strong().color(play_col)).clicked() {
                                self.is_tone_playing = !self.is_tone_playing;
                                self.tone_duration_sec = 0.0;
                            }
                        });

                        ui.add_space(4.0);

                        // Big Action Button: PROGRAM DSP WDRC
                        if ui.button(
                            egui::RichText::new("⚡ PROGRAM DSP WDRC")
                                .size(11.0)
                                .strong()
                                .color(Theme::ACCENT_CYAN),
                        ).clicked() {
                            programmed_audiogram = Some(self.audiogram);
                        }
                    });
                });
            });

        programmed_audiogram
    }

    /// Draws clinical audiogram grid with normal (0-20 dB), mild (20-40), moderate (40-60), severe (60-80).
    fn paint_audiogram_graph(&self, ui: &egui::Ui, rect: Rect) {
        let painter = ui.painter_at(rect);

        // Fill background
        painter.rect_filled(rect, 4.0, Theme::BG_SURFACE);
        painter.rect_stroke(rect, 4.0, Stroke::new(1.0_f32, Theme::BORDER_DEFAULT));

        let pad_l = 28.0;
        let pad_r = 12.0;
        let pad_t = 12.0;
        let pad_b = 16.0;

        let plot_w = rect.width() - pad_l - pad_r;
        let plot_h = rect.height() - pad_t - pad_b;

        // In clinical audiograms, 0 dB HL is at TOP and 80 dB HL is at BOTTOM
        let y_from_db = |db: f32| -> f32 {
            let frac = (db.clamp(0.0, 80.0)) / 80.0;
            rect.min.y + pad_t + frac * plot_h
        };

        let x_from_band = |idx: usize| -> f32 {
            let frac = idx as f32 / (WIZARD_FREQUENCIES.len() - 1) as f32;
            rect.min.x + pad_l + frac * plot_w
        };

        // Normal hearing green band (0 to 20 dB HL)
        let normal_rect = Rect::from_min_max(
            Pos2::new(rect.min.x + pad_l, y_from_db(0.0)),
            Pos2::new(rect.max.x - pad_r, y_from_db(20.0)),
        );
        painter.rect_filled(normal_rect, 0.0, Color32::from_rgba_unmultiplied(16, 185, 129, 25));

        // Horizontal grid lines (0, 20, 40, 60, 80 dB HL)
        for &db in &[0.0, 20.0, 40.0, 60.0, 80.0] {
            let y = y_from_db(db);
            painter.line_segment(
                [Pos2::new(rect.min.x + pad_l, y), Pos2::new(rect.max.x - pad_r, y)],
                Stroke::new(0.8_f32, Theme::BORDER_SUBTLE),
            );
            painter.text(
                Pos2::new(rect.min.x + pad_l - 4.0, y),
                egui::Align2::RIGHT_CENTER,
                format!("{:.0}", db),
                egui::FontId::monospace(8.0),
                Theme::TEXT_MUTED,
            );
        }

        // Vertical frequency lines
        for (i, &f) in WIZARD_FREQUENCIES.iter().enumerate() {
            let x = x_from_band(i);
            painter.line_segment(
                [Pos2::new(x, rect.min.y + pad_t), Pos2::new(x, rect.max.y - pad_b)],
                Stroke::new(0.8_f32, Theme::BORDER_SUBTLE),
            );

            let lbl = if f >= 1000.0 {
                format!("{:.0}k", f / 1000.0)
            } else {
                format!("{:.0}", f)
            };
            painter.text(
                Pos2::new(x, rect.max.y - pad_b + 2.0),
                egui::Align2::CENTER_TOP,
                lbl,
                egui::FontId::monospace(8.0),
                Theme::TEXT_MUTED,
            );
        }

        // Plot Left Ear (Blue 'X' and dashed lines)
        let mut prev_left: Option<Pos2> = None;
        for (i, &f) in WIZARD_FREQUENCIES.iter().enumerate() {
            let b_idx = self.band_index_for_freq(f);
            let htl = self.audiogram.htl_left[b_idx];
            let pt = Pos2::new(x_from_band(i), y_from_db(htl));

            if let Some(prev) = prev_left {
                painter.line_segment([prev, pt], Stroke::new(1.5_f32, Theme::ACCENT_CYAN));
            }
            prev_left = Some(pt);

            // Draw 'X' marker
            let d = 3.5;
            painter.line_segment([Pos2::new(pt.x - d, pt.y - d), Pos2::new(pt.x + d, pt.y + d)], Stroke::new(1.8_f32, Theme::ACCENT_CYAN));
            painter.line_segment([Pos2::new(pt.x - d, pt.y + d), Pos2::new(pt.x + d, pt.y - d)], Stroke::new(1.8_f32, Theme::ACCENT_CYAN));
        }

        // Plot Right Ear (Red 'O' and solid lines)
        let mut prev_right: Option<Pos2> = None;
        for (i, &f) in WIZARD_FREQUENCIES.iter().enumerate() {
            let b_idx = self.band_index_for_freq(f);
            let htl = self.audiogram.htl_right[b_idx];
            let pt = Pos2::new(x_from_band(i), y_from_db(htl));

            if let Some(prev) = prev_right {
                painter.line_segment([prev, pt], Stroke::new(1.5_f32, Theme::ACCENT_RED));
            }
            prev_right = Some(pt);

            // Draw 'O' marker
            painter.circle_stroke(pt, 3.5, Stroke::new(1.8_f32, Theme::ACCENT_RED));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audiogram_test_wizard_initial_state() {
        let wizard = AudiogramTestWizard::new();
        assert_eq!(wizard.selected_ear, Ear::Left);
        assert_eq!(wizard.current_freq_idx, 1);
        assert!(!wizard.is_tone_playing);
    }

    #[test]
    fn test_audiogram_test_wizard_tone_generation() {
        let mut wizard = AudiogramTestWizard::new();
        wizard.is_tone_playing = true;

        let mut buf = [0.0f32; 256];
        wizard.generate_test_tone(&mut buf, 16000.0);

        // Tone should inject sinusoidal energy
        let energy: f32 = buf.iter().map(|s| s * s).sum();
        assert!(energy > 0.0);
    }

    #[test]
    fn test_audiogram_test_wizard_headless_context() {
        let mut wizard = AudiogramTestWizard::new();
        let ctx = egui::Context::default();
        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                let _ = wizard.show(ui, 120.0);
            });
        });
    }
}
