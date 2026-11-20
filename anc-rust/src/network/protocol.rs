//! SIH 26052 UDP Network Wire Protocol specifications.

use byteorder::{LittleEndian, ReadBytesExt, WriteBytesExt};
use serde::{Deserialize, Serialize};
use std::io::{self, Cursor};

/// Standard packet sizes for SIH 26052 tactical audio transmission.
pub const AUDIO_FRAME_SAMPLES: usize = 256; // 16 ms @ 16 kHz
pub const AUDIO_PACKET_BYTES: usize = 8 + AUDIO_FRAME_SAMPLES * 4; // 1032 bytes
pub const FEC_HEADER_BYTES: usize = 12; // 8 bytes base_seq + 1 byte window + 3 bytes padding
pub const FEC_PACKET_TOTAL_BYTES: usize =
    AUDIO_PACKET_BYTES + FEC_HEADER_BYTES + AUDIO_FRAME_SAMPLES * 4; // 2068 bytes

pub const DEFAULT_AUDIO_PORT: u16 = 5005;
pub const DEFAULT_TELEMETRY_PORT: u16 = 5006;
pub const DEFAULT_RAW_INPUT_PORT: u16 = 5007;

/// Parsed Audio Packet from UDP stream with optional Tactical Forward Error Correction (FEC).
#[derive(Debug, Clone)]
pub struct AudioPacket {
    pub sequence: u64,
    pub samples: [f32; AUDIO_FRAME_SAMPLES],
    pub fec_base_seq: Option<u64>,
    pub fec_window: u8,
    pub fec_parity: Option<[f32; AUDIO_FRAME_SAMPLES]>,
}

impl AudioPacket {
    /// Creates an AudioPacket without FEC parity.
    pub fn new(sequence: u64, samples: [f32; AUDIO_FRAME_SAMPLES]) -> Self {
        Self {
            sequence,
            samples,
            fec_base_seq: None,
            fec_window: 0,
            fec_parity: None,
        }
    }

    /// Creates an AudioPacket with sliding-window XOR FEC parity.
    pub fn new_with_fec(
        sequence: u64,
        samples: [f32; AUDIO_FRAME_SAMPLES],
        fec_base_seq: u64,
        fec_window: u8,
        fec_parity: [f32; AUDIO_FRAME_SAMPLES],
    ) -> Self {
        Self {
            sequence,
            samples,
            fec_base_seq: Some(fec_base_seq),
            fec_window,
            fec_parity: Some(fec_parity),
        }
    }

    /// Serializes audio packet into a UDP datagram (1032 bytes standard, or 2068 bytes with FEC).
    pub fn serialize(&self) -> Vec<u8> {
        let has_fec = self.fec_base_seq.is_some() && self.fec_parity.is_some();
        let total_bytes = if has_fec {
            FEC_PACKET_TOTAL_BYTES
        } else {
            AUDIO_PACKET_BYTES
        };

        let mut buf = Vec::with_capacity(total_bytes);
        buf.write_u64::<LittleEndian>(self.sequence).unwrap();
        for &s in &self.samples {
            buf.write_f32::<LittleEndian>(s).unwrap();
        }

        if let (Some(base_seq), Some(parity)) = (self.fec_base_seq, self.fec_parity.as_ref()) {
            buf.write_u64::<LittleEndian>(base_seq).unwrap();
            buf.write_u8(self.fec_window).unwrap();
            buf.write_u8(0).unwrap(); // padding
            buf.write_u8(0).unwrap();
            buf.write_u8(0).unwrap();
            for &p in parity {
                buf.write_f32::<LittleEndian>(p).unwrap();
            }
        }

        buf
    }

    /// Serializes audio packet into 4-bit IMA/DVI ADPCM datagram (140 bytes, 4x compression).
    pub fn serialize_adpcm(&self) -> Vec<u8> {
        let mut encoder = crate::network::codec::AdpcmEncoder::new();
        let adpcm = encoder.encode_frame(self.sequence, &self.samples);
        adpcm.serialize()
    }

    /// Deserializes a raw UDP datagram. Handles both standard (1032 B) and FEC (2068 B) packets.
    pub fn deserialize(bytes: &[u8]) -> io::Result<Self> {
        if bytes.len() < AUDIO_PACKET_BYTES {
            if bytes.len() >= crate::network::codec::ADPCM_PACKET_BYTES {
                if let Ok(adpcm) = crate::network::codec::AdpcmPacket::deserialize(bytes) {
                    let mut decoder = crate::network::codec::AdpcmDecoder::new();
                    let mut samples = [0.0f32; AUDIO_FRAME_SAMPLES];
                    decoder.decode_packet(&adpcm, &mut samples);
                    return Ok(Self {
                        sequence: adpcm.sequence,
                        samples,
                        fec_base_seq: adpcm.fec_base_seq,
                        fec_window: adpcm.fec_window,
                        fec_parity: None,
                    });
                }
            }
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "Packet smaller than minimum 1032 bytes",
            ));
        }

        let mut rdr = Cursor::new(bytes);
        let sequence = rdr.read_u64::<LittleEndian>()?;
        let mut samples = [0.0f32; AUDIO_FRAME_SAMPLES];
        for s in samples.iter_mut() {
            *s = rdr.read_f32::<LittleEndian>()?;
        }

        let (fec_base_seq, fec_window, fec_parity) = if bytes.len() >= FEC_PACKET_TOTAL_BYTES {
            let base_seq = rdr.read_u64::<LittleEndian>()?;
            let window = rdr.read_u8()?;
            let _pad0 = rdr.read_u8()?;
            let _pad1 = rdr.read_u8()?;
            let _pad2 = rdr.read_u8()?;

            let mut parity = [0.0f32; AUDIO_FRAME_SAMPLES];
            for s in parity.iter_mut() {
                *s = rdr.read_f32::<LittleEndian>()?;
            }
            (Some(base_seq), window, Some(parity))
        } else {
            (None, 0, None)
        };

        Ok(Self {
            sequence,
            samples,
            fec_base_seq,
            fec_window,
            fec_parity,
        })
    }
}

/// High-resolution microsecond execution timings across core pipeline DSP stages.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct DspStageTimings {
    pub stft_us: u32,
    pub afc_us: u32,
    pub beamformer_us: u32,
    pub dereverb_us: u32,
    pub spectral_us: u32,
    #[serde(default)]
    pub intelligibility_us: u32,
    pub synthesis_us: u32,
    pub total_us: u32,
}

/// Real-time edge telemetry payload sent to mission control on port 5006.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeTelemetry {
    pub frame: u64,
    pub model: String,
    pub mode: String,
    pub model_active: bool,
    pub compute_time_ms: f32,
    pub algorithmic_latency_ms: f32,
    pub total_latency_ms: f32,
    pub avg_rtf: f32,
    pub deadline_misses: u64,
    pub fallback_frames: u64,
    pub enhanced_frames: u64,
    pub input_rms: f32,
    pub output_rms: f32,
    pub temperature_c: f32,
    #[serde(default)]
    pub talker_angle_deg: f32,
    #[serde(default)]
    pub doa_confidence: f32,
    #[serde(default)]
    pub mean_cdr_db: f32,
    #[serde(default)]
    pub spatial_coherence: f32,
    #[serde(default)]
    pub speech_intelligibility_index: f32,
    #[serde(default)]
    pub intelligibility_gain_db: f32,
    #[serde(default)]
    pub fec_recovery_rate: f32,
    #[serde(default)]
    pub rf_link_health: f32,
    #[serde(default)]
    pub wind_turbulence_index: f32,
    #[serde(default)]
    pub wind_detected: bool,
    #[serde(default)]
    pub glottal_crest_factor: f32,
    #[serde(default)]
    pub estimated_snr_gain_db: f32,
    #[serde(default)]
    pub aggressive_snr_active: bool,
    #[serde(default)]
    pub momentary_lufs: f32,
    #[serde(default)]
    pub short_term_lufs: f32,
    #[serde(default)]
    pub integrated_lufs: f32,
    #[serde(default)]
    pub loudness_range_lu: f32,
    #[serde(default)]
    pub true_peak_dbfs: f32,
    #[serde(default)]
    pub lufs_gain_reduction_db: f32,
    #[serde(default)]
    pub res_echo_suppression_db: f32,
    #[serde(default)]
    pub total_erle_db: f32,
    #[serde(default)]
    pub mic_cal_mismatch_db: f32,
    #[serde(default)]
    pub mic_clog_detected: bool,
    #[serde(default)]
    pub tactical_stress_index: f32,
    #[serde(default)]
    pub vocal_jitter_pct: f32,
    #[serde(default)]
    pub vocal_shimmer_pct: f32,
    #[serde(default)]
    pub lombard_strain_index: f32,
    #[serde(default)]
    pub howling_detected: bool,
    #[serde(default)]
    pub howling_suppression_db: f32,
    #[serde(default)]
    pub battery_soc_pct: f32,
    #[serde(default)]
    pub battery_voltage_v: f32,
    #[serde(default)]
    pub battery_runtime_hours: f32,
    #[serde(default)]
    pub battery_power_mw: f32,
    #[serde(default)]
    pub blast_overpressure_pa: f32,
    #[serde(default)]
    pub blast_overpressure_psi: f32,
    #[serde(default)]
    pub blast_daily_dose_pct: f32,
    #[serde(default)]
    pub bone_fusion_active: bool,
    #[serde(default)]
    pub audiogram_wdrc_gain_db: f32,
    #[serde(default)]
    pub deesser_gain_reduction_db: f32,
    #[serde(default)]
    pub deesser_sibilance_ratio_db: f32,
    #[serde(default)]
    pub deesser_active: bool,
    #[serde(default)]
    pub polar_pattern_type: u8,
    #[serde(default)]
    pub polar_null_angle_deg: f32,
    #[serde(default)]
    pub polar_front_to_back_ratio_db: f32,
    #[serde(default)]
    pub thermal_noise_floor_dbfs: f32,
    #[serde(default)]
    pub preamp_temperature_c: f32,
    #[serde(default)]
    pub cable_impedance_ohms: f32,
    #[serde(default)]
    pub cable_health_pct: f32,
    #[serde(default)]
    pub cable_fault_status: u8,
    #[serde(default)]
    pub spectral_contrast_db: f32,
    #[serde(default)]
    pub spectral_contrast_gamma: f32,
    #[serde(default)]
    pub ambisonics_intensity_mag: f32,
    #[serde(default)]
    pub ambisonics_diffuseness: f32,
    #[serde(default)]
    pub ambisonics_azimuth_deg: f32,
    #[serde(default)]
    pub jamming_type: u8,
    #[serde(default)]
    pub jamming_confidence: f32,
    #[serde(default)]
    pub rf_jitter_var_ms2: f32,
    #[serde(default)]
    pub packet_burst_clustering: f32,
    #[serde(default)]
    pub rasti_sti_score: f32,
    #[serde(default)]
    pub rasti_rating: u8,
    #[serde(default)]
    pub stage_timings: DspStageTimings,
}
