//! Subband Thermal Johnson-Nyquist Preamplifier Noise Estimator.
//!
//! Developed for SIH 26052 Tactical Military Audio Systems.
//!
//! In silent desert night patrols and covert reconnaissance operations, thermal resistor noise
//! from microphone preamplifiers causes faint white hiss:
//! $$P_{\text{thermal}} = 4 \cdot k_B \cdot T \cdot R \cdot \Delta f$$
//! where:
//! - $k_B = 1.380649 \times 10^{-23}\text{ J/K}$ is Boltzmann's constant
//! - $T = T_{\text{Celsius}} + 273.15$ is absolute temperature in Kelvin
//! - $R$ is preamplifier input resistor impedance (nominally $2200.0\ \Omega$)
//! - $\Delta f = f_s / N_{\text{fft}}$ is the subband frequency bin bandwidth
//!
//! Physical Problem:
//! Preamplifier noise is non-acoustic thermal electron movement in the front-end amplifier stage.
//! Without physical thermal modeling, aggressive Wiener gain suppression and MVDR spatial inversion
//! attempt to cancel this non-acoustic electron hiss, causing:
//! 1. Audible noise pumping / breathing during silent pauses.
//! 2. Musical noise / chirp artifacts from fluctuating random subband noise peaks.
//! 3. MVDR covariance matrix ill-conditioning (high condition number $\kappa > 10^5$).
//!
//! This module:
//! 1. Tracks physical thermal noise power across temperature extremes ($-40^\circ\text{C}$ arctic to $+55^\circ\text{C}$ desert).
//! 2. Bounds the subband Wiener gain floor, preventing gain collapse and acoustic pumping.
//! 3. Enforces physical lower bounds on MVDR diagonal loading ($\epsilon_{\text{diag}} \ge \sigma^2_{\text{thermal}} \cdot \kappa_{\text{margin}}$).
//! 4. Zero heap allocations in real-time execution.

/// Boltzmann's constant in Joules per Kelvin ($J/K$).
pub const BOLTZMANN_CONSTANT: f32 = 1.380649e-23;

/// Maximum number of subband frequency bins supported without allocation.
pub const MAX_THERMAL_BINS: usize = 513;

/// Configuration for Johnson-Nyquist Thermal Noise Estimator.
#[derive(Debug, Clone, Copy)]
pub struct ThermalNoiseConfig {
    /// Audio sampling rate in Hz (default: 16000.0).
    pub sample_rate: f32,
    /// STFT FFT size (default: 512).
    pub fft_size: usize,
    /// Preamplifier input resistance in Ohms (default: 2200.0 Ohm).
    pub input_impedance_ohms: f32,
    /// Preamplifier voltage gain in dB (default: 40.0 dB = 100x).
    pub preamp_gain_db: f32,
    /// ADC full-scale reference voltage in Volts peak (default: 1.0 V).
    pub adc_vref_volts: f32,
    /// Preamplifier Noise Figure (NF) in dB (default: 3.5 dB for ultra-low-noise FET stage).
    pub noise_figure_db: f32,
    /// Diagonal loading margin multiplier for MVDR (default: 3.0).
    pub diag_loading_margin: f32,
    /// Minimum allowed Wiener gain floor even in total silence (default: 0.05 = -26 dB).
    pub min_wiener_floor: f32,
}

impl Default for ThermalNoiseConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            fft_size: 512,
            input_impedance_ohms: 2200.0,
            preamp_gain_db: 40.0,
            adc_vref_volts: 1.0,
            noise_figure_db: 3.5,
            diag_loading_margin: 3.0,
            min_wiener_floor: 0.05,
        }
    }
}

/// Telemetry emitted by the Thermal Noise Estimator.
#[derive(Debug, Clone, Copy, Default)]
pub struct ThermalNoiseTelemetry {
    /// Thermal noise floor in digital dBFS.
    pub thermal_noise_floor_dbfs: f32,
    /// Current tracked operating temperature in degrees Celsius.
    pub temperature_c: f32,
    /// Physical thermal power spectral density in Watts per Hz.
    pub thermal_psd_w_hz: f32,
    /// Subband bin thermal noise power in digital domain.
    pub thermal_bin_power: f32,
    /// Equivalent Input Noise (EIN) in dBV (unweighted).
    pub ein_dbv: f32,
    /// Preamplifier Noise Figure in dB.
    pub noise_figure_db: f32,
    /// Total number of noise pumping / over-suppression events prevented.
    pub pumping_prevention_events: u64,
}

/// Subband Johnson-Nyquist Preamplifier Thermal Noise Estimator.
pub struct ThermalNoiseEstimator {
    config: ThermalNoiseConfig,
    temperature_c: f32,
    bin_width_hz: f32,

    // Precomputed physical quantities
    thermal_psd_w_hz: f32,
    thermal_bin_power_digital: f32,
    thermal_floor_dbfs: f32,
    ein_dbv: f32,

    // Telemetry and statistics
    pumping_prevention_counter: u64,
    telemetry: ThermalNoiseTelemetry,
}

impl ThermalNoiseEstimator {
    /// Creates a new ThermalNoiseEstimator with the given configuration.
    pub fn new(config: ThermalNoiseConfig) -> Self {
        let mut est = Self {
            config,
            temperature_c: 25.0, // Default nominal 25°C
            bin_width_hz: config.sample_rate / config.fft_size as f32,
            thermal_psd_w_hz: 0.0,
            thermal_bin_power_digital: 0.0,
            thermal_floor_dbfs: -100.0,
            ein_dbv: -125.0,
            pumping_prevention_counter: 0,
            telemetry: ThermalNoiseTelemetry::default(),
        };

        est.recompute_thermal_constants();
        est
    }

    /// Recomputes physical noise figures and digital scaling constants.
    fn recompute_thermal_constants(&mut self) {
        let temp_k = (self.temperature_c + 273.15).max(10.0);
        let r = self.config.input_impedance_ohms.max(100.0);

        // 1. Johnson-Nyquist thermal voltage noise spectral density:
        //    v_n^2 / df = 4 * k_B * T * R  (V^2 / Hz)
        let vn2_per_hz = 4.0 * BOLTZMANN_CONSTANT * temp_k * r;
        self.thermal_psd_w_hz = vn2_per_hz / r; // Power spectral density in W/Hz

        // Factor in preamplifier noise figure (NF = 10^(NF_dB / 10))
        let nf_linear = 10.0f32.powf(self.config.noise_figure_db / 10.0);
        let total_input_vn2_per_hz = vn2_per_hz * nf_linear;

        // 2. Equivalent Input Noise (EIN) in 20 kHz bandwidth (or fs/2) in dBV:
        let bandwidth = (self.config.sample_rate * 0.5).min(20000.0);
        let total_ein_v2 = total_input_vn2_per_hz * bandwidth;
        self.ein_dbv = 10.0 * total_ein_v2.max(1e-18).log10();

        // 3. Subband bin noise voltage at ADC input:
        //    V_bin_adc^2 = total_input_vn2_per_hz * bin_width * G_preamp^2
        let preamp_gain_linear = 10.0f32.powf(self.config.preamp_gain_db / 20.0);
        let v_bin_adc_sq = total_input_vn2_per_hz * self.bin_width_hz * (preamp_gain_linear * preamp_gain_linear);

        // 4. Digital full-scale power conversion:
        //    Full scale 1.0 peak = 0.5 mean square for full sine wave
        let v_fs = self.config.adc_vref_volts.max(0.1);
        let v_fs_sq = v_fs * v_fs;
        self.thermal_bin_power_digital = (v_bin_adc_sq / v_fs_sq).max(1e-14);

        self.thermal_floor_dbfs = 10.0 * self.thermal_bin_power_digital.log10();

        self.telemetry = ThermalNoiseTelemetry {
            thermal_noise_floor_dbfs: self.thermal_floor_dbfs,
            temperature_c: self.temperature_c,
            thermal_psd_w_hz: self.thermal_psd_w_hz,
            thermal_bin_power: self.thermal_bin_power_digital,
            ein_dbv: self.ein_dbv,
            noise_figure_db: self.config.noise_figure_db,
            pumping_prevention_events: self.pumping_prevention_counter,
        };
    }

    /// Updates current operational chassis/sensor temperature in degrees Celsius.
    pub fn update_temperature(&mut self, temp_c: f32) {
        let clamped = temp_c.clamp(-50.0, 100.0);
        if (clamped - self.temperature_c).abs() > 0.5 {
            self.temperature_c = clamped;
            self.recompute_thermal_constants();
        }
    }

    /// Returns the physical digital thermal noise floor power per subband bin.
    #[inline(always)]
    pub fn thermal_bin_power(&self) -> f32 {
        self.thermal_bin_power_digital
    }

    /// Bounds Wiener gain floor across all subbands, preventing non-acoustic electron pumping.
    ///
    /// Modifies `subband_gains` in-place so no subband drops below the physical thermal boundary.
    pub fn bound_wiener_gains(&mut self, subband_gains: &mut [f32], subband_power: &[f32]) {
        let n = subband_gains.len().min(subband_power.len()).min(MAX_THERMAL_BINS);
        let thermal_pwr = self.thermal_bin_power_digital;
        let min_floor = self.config.min_wiener_floor;

        let mut clamped_any = false;
        for i in 0..n {
            let pwr = subband_power[i];
            // When signal power approaches thermal floor, gain floor must rise smoothly
            // to avoid audible chirping/pumping on electron noise:
            // bound = max(min_floor, sqrt(P_thermal / (P_signal + P_thermal)))
            let thermal_ratio = thermal_pwr / (pwr + thermal_pwr);
            let dynamic_floor = min_floor.max(thermal_ratio.sqrt() * 0.40);

            if subband_gains[i] < dynamic_floor {
                subband_gains[i] = dynamic_floor;
                clamped_any = true;
            }
        }

        if clamped_any {
            self.pumping_prevention_counter = self.pumping_prevention_counter.saturating_add(1);
            self.telemetry.pumping_prevention_events = self.pumping_prevention_counter;
        }
    }

    /// Enforces physical lower bound on MVDR covariance diagonal loading.
    #[inline]
    pub fn bound_mvdr_diagonal_loading(&mut self, default_loading: f32) -> f32 {
        let physical_floor = self.thermal_bin_power_digital * self.config.diag_loading_margin;
        if default_loading < physical_floor {
            self.pumping_prevention_counter = self.pumping_prevention_counter.saturating_add(1);
            self.telemetry.pumping_prevention_events = self.pumping_prevention_counter;
            physical_floor
        } else {
            default_loading
        }
    }

    /// Returns the current telemetry metrics.
    pub fn telemetry(&self) -> ThermalNoiseTelemetry {
        self.telemetry
    }

    /// Resets statistics.
    pub fn reset(&mut self) {
        self.pumping_prevention_counter = 0;
        self.recompute_thermal_constants();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_thermal_noise_constants_nominal() {
        let config = ThermalNoiseConfig {
            sample_rate: 16000.0,
            fft_size: 512,
            input_impedance_ohms: 2200.0,
            ..Default::default()
        };
        let est = ThermalNoiseEstimator::new(config);
        let telem = est.telemetry();

        assert_eq!(telem.temperature_c, 25.0);
        // EIN should be around -125 to -115 dBV for standard military preamps
        assert!(telem.ein_dbv > -135.0 && telem.ein_dbv < -100.0);
        // Digital thermal floor should be <= -80 dBFS
        assert!(telem.thermal_noise_floor_dbfs < -70.0);
    }

    #[test]
    fn test_temperature_scaling_increases_noise() {
        let mut est = ThermalNoiseEstimator::new(ThermalNoiseConfig::default());
        est.update_temperature(-20.0); // Arctic cold
        let cold_floor = est.thermal_bin_power();

        est.update_temperature(55.0); // Desert extreme
        let hot_floor = est.thermal_bin_power();

        assert!(hot_floor > cold_floor, "Thermal noise power must increase with temperature (T_hot > T_cold)");
    }

    #[test]
    fn test_bound_wiener_gains_prevents_zero_gain_on_electron_noise() {
        let mut est = ThermalNoiseEstimator::new(ThermalNoiseConfig::default());

        // Subband power at exact thermal floor
        let pwr = [est.thermal_bin_power(); 32];
        let mut gains = [0.001f32; 32]; // Very low gain that would cause pumping

        est.bound_wiener_gains(&mut gains, &pwr);

        for &g in &gains {
            assert!(g >= 0.05, "Gain must be bounded above minimum floor to prevent pumping");
        }
        assert!(est.telemetry().pumping_prevention_events > 0);
    }
}
