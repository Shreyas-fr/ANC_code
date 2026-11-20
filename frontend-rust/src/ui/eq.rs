//! Operator Headset Calibration & Parametric Graphic EQ Widget.
//!
//! Provides an interactive 8-band parametric tactical equalizer with real-time
//! biquad filtering (Direct Form II Transposed) for soldier headset calibration.
//!
//! Includes soldier audiogram compensation presets:
//! - Flat (Default studio monitor baseline)
//! - Aviation Pilot (Cuts rotor/cockpit drone at 150/400 Hz, boosts speech formants at 2.5/4 kHz)
//! - Tanker Rumble Cut (Deep low-frequency cuts at 60/150 Hz to eliminate chassis vibration fatigue)
//! - Fricative Clarity Boost (High-frequency boost at 4/6/8 kHz for noise-induced hearing loss)

use std::f32::consts::PI;
use eframe::egui;
use crate::ui::theme::Theme;

/// 8 center frequencies covering the human auditory speech and tactical noise spectrum.
pub const EQ_FREQUENCIES: [f32; 8] = [60.0, 150.0, 400.0, 1000.0, 2500.0, 4000.0, 6000.0, 8000.0];
pub const EQ_LABELS: [&str; 8] = [
    "60 Hz", "150 Hz", "400 Hz", "1 kHz", "2.5 kHz", "4 kHz", "6 kHz", "8 kHz",
];
pub const NUM_BANDS: usize = 8;

/// Soldier audiogram calibration presets.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum EqPreset {
    #[default]
    Flat,
    AviationPilot,
    TankerRumbleCut,
    FricativeClarityBoost,
}

impl EqPreset {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Flat => "FLAT (MONITOR)",
            Self::AviationPilot => "AVIATION PILOT",
            Self::TankerRumbleCut => "TANKER RUMBLE CUT",
            Self::FricativeClarityBoost => "FRICATIVE CLARITY BOOST",
        }
    }

    pub fn gains_db(&self) -> [f32; NUM_BANDS] {
        match self {
            Self::Flat => [0.0; NUM_BANDS],
            Self::AviationPilot => [-2.0, -6.0, -4.0, 1.0, 4.0, 5.0, 2.0, -1.0],
            Self::TankerRumbleCut => [-12.0, -8.0, -3.0, 2.0, 3.0, 4.0, 1.0, 0.0],
            Self::FricativeClarityBoost => [-6.0, -2.0, 0.0, 1.0, 3.0, 6.0, 5.0, 3.0],
        }
    }
}

/// Numerically stable single-channel Biquad filter (Direct Form II Transposed).
#[derive(Debug, Clone, Copy)]
pub struct BiquadFilter {
    b0: f32,
    b1: f32,
    b2: f32,
    a1: f32,
    a2: f32,
    s1: f32,
    s2: f32,
}

impl Default for BiquadFilter {
    fn default() -> Self {
        Self {
            b0: 1.0,
            b1: 0.0,
            b2: 0.0,
            a1: 0.0,
            a2: 0.0,
            s1: 0.0,
            s2: 0.0,
        }
    }
}

impl BiquadFilter {
    /// Configures biquad coefficients for a peaking EQ filter (Robert Bristow-Johnson Audio EQ Cookbook).
    pub fn set_peaking(&mut self, f0: f32, sample_rate: f32, gain_db: f32, q: f32) {
        if gain_db.abs() < 0.05 {
            // Passthrough for flat gain
            self.b0 = 1.0;
            self.b1 = 0.0;
            self.b2 = 0.0;
            self.a1 = 0.0;
            self.a2 = 0.0;
            return;
        }

        let a = 10.0f32.powf(gain_db / 40.0);
        let omega = 2.0 * PI * (f0 / sample_rate).clamp(0.001, 0.499);
        let alpha = omega.sin() / (2.0 * q.max(0.1));
        let cos_w = omega.cos();

        let b0 = 1.0 + alpha * a;
        let b1 = -2.0 * cos_w;
        let b2 = 1.0 - alpha * a;
        let a0 = 1.0 + alpha / a;
        let a1 = -2.0 * cos_w;
        let a2 = 1.0 - alpha / a;

        let inv_a0 = 1.0 / a0;
        self.b0 = b0 * inv_a0;
        self.b1 = b1 * inv_a0;
        self.b2 = b2 * inv_a0;
        self.a1 = a1 * inv_a0;
        self.a2 = a2 * inv_a0;
    }

    /// Resets internal delay states to zero.
    pub fn reset(&mut self) {
        self.s1 = 0.0;
        self.s2 = 0.0;
    }

    /// Filters a single sample in-place using Direct Form II Transposed.
    #[inline(always)]
    pub fn process_sample(&mut self, x: f32) -> f32 {
        let y = self.b0 * x + self.s1;
        self.s1 = self.b1 * x - self.a1 * y + self.s2;
        self.s2 = self.b2 * x - self.a2 * y;
        y
    }
}

/// Real-time 8-Band Tactical Equalizer.
#[derive(Debug, Clone)]
pub struct TacticalEqualizer {
    gains_db: [f32; NUM_BANDS],
    filters: [BiquadFilter; NUM_BANDS],
    sample_rate: f32,
    preset: EqPreset,
    enabled: bool,
}

impl TacticalEqualizer {
    /// Creates a new `TacticalEqualizer`.
    pub fn new(sample_rate: f32) -> Self {
        let mut eq = Self {
            gains_db: [0.0; NUM_BANDS],
            filters: [BiquadFilter::default(); NUM_BANDS],
            sample_rate,
            preset: EqPreset::Flat,
            enabled: true,
        };
        eq.recalculate_filters();
        eq
    }

    /// Recalculates biquad coefficients for all 8 bands.
    #[allow(clippy::needless_range_loop)]
    fn recalculate_filters(&mut self) {
        let q = 1.414f32; // Standard 1-octave bandwidth
        for i in 0..NUM_BANDS {
            self.filters[i].set_peaking(
                EQ_FREQUENCIES[i],
                self.sample_rate,
                self.gains_db[i],
                q,
            );
        }
    }

    /// Sets gain for a single band in decibels [-12.0 dB, +12.0 dB].
    pub fn set_gain(&mut self, band: usize, gain_db: f32) {
        if band < NUM_BANDS {
            self.gains_db[band] = gain_db.clamp(-12.0, 12.0);
            self.filters[band].set_peaking(
                EQ_FREQUENCIES[band],
                self.sample_rate,
                self.gains_db[band],
                1.414,
            );
        }
    }

    /// Returns current gain for a band.
    pub fn gain(&self, band: usize) -> f32 {
        if band < NUM_BANDS {
            self.gains_db[band]
        } else {
            0.0
        }
    }

    /// Loads a tactical audiogram preset.
    pub fn set_preset(&mut self, preset: EqPreset) {
        self.preset = preset;
        self.gains_db = preset.gains_db();
        self.recalculate_filters();
    }

    /// Returns the currently active preset.
    pub fn preset(&self) -> EqPreset {
        self.preset
    }

    /// Enables or disables the equalizer.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }

    /// Returns whether the equalizer is currently active.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Resets all filter delay states.
    pub fn reset(&mut self) {
        for f in self.filters.iter_mut() {
            f.reset();
        }
    }

    /// Processes an audio buffer in-place with zero heap allocations.
    pub fn process_block(&mut self, samples: &mut [f32]) {
        if !self.enabled {
            return;
        }

        for sample in samples.iter_mut() {
            let mut s = *sample;
            for filter in self.filters.iter_mut() {
                s = filter.process_sample(s);
            }
            *sample = s;
        }
    }
}

impl Default for TacticalEqualizer {
    fn default() -> Self {
        Self::new(16000.0)
    }
}

/// Visual egui widget for interactive tactical EQ controls.
pub struct TacticalEqWidget;

impl TacticalEqWidget {
    /// Renders the 8-band parametric tactical EQ panel.
    #[allow(clippy::needless_range_loop)]
    pub fn show(ui: &mut egui::Ui, eq: &mut TacticalEqualizer) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(egui::Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(egui::Margin::symmetric(14.0, 10.0))
            .show(ui, |ui| {
                // Header Bar
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("🎚️ OPERATOR HEADSET TACTICAL EQUALIZER & AUDIOGRAM")
                            .strong()
                            .size(11.5)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    let (enable_txt, enable_col) = if eq.is_enabled() {
                        ("EQ: ACTIVE", Theme::ACCENT_GREEN)
                    } else {
                        ("EQ: BYPASS", Theme::TEXT_MUTED)
                    };

                    if ui.button(egui::RichText::new(enable_txt).size(10.5).color(enable_col)).clicked() {
                        let cur = eq.is_enabled();
                        eq.set_enabled(!cur);
                    }

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        // Preset Selector Dropdown
                        egui::ComboBox::from_id_salt("eq_preset_sel")
                            .selected_text(
                                egui::RichText::new(format!("PRESET: {}", eq.preset().name()))
                                    .size(10.5)
                                    .color(Theme::ACCENT_CYAN),
                            )
                            .show_ui(ui, |ui| {
                                for &p in &[
                                    EqPreset::Flat,
                                    EqPreset::AviationPilot,
                                    EqPreset::TankerRumbleCut,
                                    EqPreset::FricativeClarityBoost,
                                ] {
                                    if ui.selectable_label(eq.preset() == p, p.name()).clicked() {
                                        eq.set_preset(p);
                                    }
                                }
                            });
                    });
                });

                ui.add_space(8.0);

                // 8 Vertical Sliders
                ui.horizontal(|ui| {
                    let total_width = ui.available_width();
                    let slider_col_width = (total_width - 16.0) / NUM_BANDS as f32;

                    for i in 0..NUM_BANDS {
                        ui.allocate_ui_with_layout(
                            egui::vec2(slider_col_width, 100.0),
                            egui::Layout::top_down(egui::Align::Center),
                            |ui| {
                                let mut gain = eq.gain(i);
                                let col = if gain > 0.5 {
                                    Theme::ACCENT_CYAN
                                } else if gain < -0.5 {
                                    Theme::ACCENT_AMBER
                                } else {
                                    Theme::TEXT_MUTED
                                };

                                // Gain Readout
                                ui.label(
                                    egui::RichText::new(format!("{:+.1}dB", gain))
                                        .size(9.5)
                                        .color(col),
                                );

                                // Vertical Slider
                                let slider_resp = ui.add(
                                    egui::Slider::new(&mut gain, -12.0..=12.0)
                                        .vertical()
                                        .show_value(false),
                                );
                                if slider_resp.changed() {
                                    eq.set_gain(i, gain);
                                }

                                // Frequency Label
                                ui.label(
                                    egui::RichText::new(EQ_LABELS[i])
                                        .size(9.5)
                                        .strong()
                                        .color(Theme::TEXT_SECONDARY),
                                );
                            },
                        );
                    }
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_biquad_peaking_filter_gain() {
        let sample_rate = 16000.0f32;
        let mut filter = BiquadFilter::default();

        // 1 kHz peaking filter with +6 dB gain
        filter.set_peaking(1000.0, sample_rate, 6.0, 1.414);

        let n = 2048;
        let mut in_sig = vec![0.0f32; n];
        let mut out_sig = vec![0.0f32; n];

        for i in 0..n {
            let t = i as f32 / sample_rate;
            in_sig[i] = (2.0 * PI * 1000.0 * t).sin();
            out_sig[i] = filter.process_sample(in_sig[i]);
        }

        // Measure steady-state gain
        let pwr_in: f32 = in_sig[500..].iter().map(|s| s * s).sum();
        let pwr_out: f32 = out_sig[500..].iter().map(|s| s * s).sum();
        let gain_measured_db = 10.0 * (pwr_out / pwr_in).log10();

        assert!(
            (gain_measured_db - 6.0).abs() < 0.6,
            "Peaking filter gain deviates: {:.2} dB vs expected +6 dB",
            gain_measured_db
        );
    }

    #[test]
    fn test_audiogram_presets_load_correctly() {
        let mut eq = TacticalEqualizer::new(16000.0);
        assert_eq!(eq.preset(), EqPreset::Flat);

        eq.set_preset(EqPreset::TankerRumbleCut);
        assert_eq!(eq.gain(0), -12.0); // 60 Hz
        assert_eq!(eq.gain(1), -8.0);  // 150 Hz
        assert_eq!(eq.gain(5), 4.0);   // 4 kHz

        eq.set_preset(EqPreset::AviationPilot);
        assert_eq!(eq.gain(1), -6.0);  // 150 Hz
        assert_eq!(eq.gain(5), 5.0);   // 4 kHz

        eq.set_preset(EqPreset::FricativeClarityBoost);
        assert_eq!(eq.gain(5), 6.0);   // 4 kHz
        assert_eq!(eq.gain(6), 5.0);   // 6 kHz
    }
}
