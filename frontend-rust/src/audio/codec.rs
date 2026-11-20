//! Audio Codec integration for frontend playback and low-bitrate decompression.

pub use anc_rust::network::codec::{
    AdpcmDecoder, AdpcmEncoder, AdpcmFecCodec, AdpcmPacket,
    ADPCM_FRAME_SAMPLES, ADPCM_PAYLOAD_BYTES, ADPCM_PACKET_BYTES, ADPCM_FEC_PACKET_BYTES,
};

/// Frontend Audio Decompressor supporting ultra-low-bitrate 64 kbps ADPCM streams.
pub struct FrontendAudioCodec {
    pub decoder: AdpcmDecoder,
    pub decoded_samples: [f32; ADPCM_FRAME_SAMPLES],
}

impl Default for FrontendAudioCodec {
    fn default() -> Self {
        Self::new()
    }
}

impl FrontendAudioCodec {
    pub fn new() -> Self {
        Self {
            decoder: AdpcmDecoder::new(),
            decoded_samples: [0.0; ADPCM_FRAME_SAMPLES],
        }
    }

    /// Decodes an incoming ADPCM packet into the pre-allocated sample buffer.
    pub fn decode(&mut self, packet: &AdpcmPacket) -> &[f32; ADPCM_FRAME_SAMPLES] {
        self.decoder.decode_packet(packet, &mut self.decoded_samples);
        &self.decoded_samples
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_frontend_codec_decode_packet() {
        let mut codec = FrontendAudioCodec::new();
        let packet = AdpcmPacket::new(1, 0, 0, [0x00; ADPCM_PAYLOAD_BYTES]);
        let samples = codec.decode(&packet);
        assert_eq!(samples.len(), ADPCM_FRAME_SAMPLES);
    }
}
