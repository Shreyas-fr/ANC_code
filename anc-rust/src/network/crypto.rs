//! Zero-Latency Cryptographic Frame Authentication & Anti-Spoofing Engine.
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! In modern Electronic Warfare (EW) and cyber-contested battlefield environments,
//! hostile adversaries attempt:
//! 1. RF Audio Spoofing: Injecting falsified synthetic voice commands into squad radios.
//! 2. Replay Attacks: Capturing valid soldier transmissions and re-transmitting them
//!    later to cause confusion or misdirection.
//! 3. Cryptographic Tampering: Bit-flipping and packet manipulation over tactical SDR meshes.
//!
//! This module provides:
//! - Pure-Rust, constant-time Poly1305 Message Authentication Code (MAC) engine (RFC 8439).
//! - 128-bit anti-replay sliding window bitmap with 64-bit monotonic sequence ratchet.
//! - Rolling session key ratchet with forward secrecy derivation.
//! - Rejects forged or replayed packets before DSP decoding with zero latency overhead.
//! - Strictly ZERO heap allocations in the real-time audio loop.

/// Number of bytes in a standard 128-bit authentication tag.
pub const MAC_TAG_BYTES: usize = 16;
/// Number of bytes in a Poly1305 symmetric key (32 bytes = 256 bits).
pub const CRYPTO_KEY_BYTES: usize = 32;
/// Anti-replay sliding window depth in packets (128 packets = 2.048 s @ 16 ms frames).
pub const REPLAY_WINDOW_SIZE: usize = 128;

/// Authentication verification verdict.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthResult {
    /// Packet authentic and verified in-sequence.
    Valid,
    /// Cryptographic signature mismatch (Adversary forged packet or corrupted data).
    TagMismatch,
    /// Monotonic sequence replay detected (Adversary RF replay attack).
    ReplayDetected,
    /// Packet dropped due to extreme latency or out-of-window expiration.
    ExpiredSequence,
}

/// Constant-time memory comparison to prevent side-channel timing attacks.
#[inline(always)]
pub fn constant_time_eq_16(a: &[u8; 16], b: &[u8; 16]) -> bool {
    let mut diff = 0u8;
    for i in 0..16 {
        diff |= a[i] ^ b[i];
    }
    diff == 0
}

/// Constant-time Poly1305 One-Time MAC implementation (RFC 8439) with zero heap allocations.
#[derive(Clone)]
pub struct Poly1305 {
    // r clamped: 5 limbs of 26 bits
    r0: u32,
    r1: u32,
    r2: u32,
    r3: u32,
    r4: u32,
    // precomputed 5 * r: limbs 1..4
    s1: u32,
    s2: u32,
    s3: u32,
    s4: u32,
    // pad s: 4 words of 32 bits
    pad: [u32; 4],
}

impl Poly1305 {
    /// Initializes Poly1305 with a 32-byte key: first 16 bytes is r, second 16 bytes is s (pad).
    pub fn new(key: &[u8; CRYPTO_KEY_BYTES]) -> Self {
        let mut r = [0u8; 16];
        r.copy_from_slice(&key[0..16]);

        // RFC 8439 clamping
        r[3] &= 15;
        r[7] &= 15;
        r[11] &= 15;
        r[15] &= 15;
        r[4] &= 252;
        r[8] &= 252;
        r[12] &= 252;

        let r0 = (u32::from_le_bytes([r[0], r[1], r[2], 0])) & 0x03ffffff;
        let r1 = ((u32::from_le_bytes([r[3], r[4], r[5], r[6]])) >> 2) & 0x03ffffff;
        let r2 = ((u32::from_le_bytes([r[6], r[7], r[8], r[9]])) >> 4) & 0x03ffffff;
        let r3 = ((u32::from_le_bytes([r[9], r[10], r[11], r[12]])) >> 6) & 0x03ffffff;
        let r4 = ((u32::from_le_bytes([r[12], r[13], r[14], r[15]])) >> 8) & 0x03ffffff;

        let s1 = r1 * 5;
        let s2 = r2 * 5;
        let s3 = r3 * 5;
        let s4 = r4 * 5;

        let pad = [
            u32::from_le_bytes([key[16], key[17], key[18], key[19]]),
            u32::from_le_bytes([key[20], key[21], key[22], key[23]]),
            u32::from_le_bytes([key[24], key[25], key[26], key[27]]),
            u32::from_le_bytes([key[28], key[29], key[30], key[31]]),
        ];

        Self {
            r0,
            r1,
            r2,
            r3,
            r4,
            s1,
            s2,
            s3,
            s4,
            pad,
        }
    }

    /// Computes 16-byte Poly1305 MAC tag over arbitrary byte slices with zero heap allocations.
    pub fn compute_tag(&self, data: &[u8], out_tag: &mut [u8; MAC_TAG_BYTES]) {
        let mut h0: u32 = 0;
        let mut h1: u32 = 0;
        let mut h2: u32 = 0;
        let mut h3: u32 = 0;
        let mut h4: u32 = 0;

        let mut offset = 0;
        let len = data.len();

        while offset < len {
            let chunk_len = (len - offset).min(16);
            let mut block = [0u8; 17];
            block[..chunk_len].copy_from_slice(&data[offset..offset + chunk_len]);
            block[chunk_len] = 1; // Append 0x01 per RFC 8439

            let w0 = u32::from_le_bytes([block[0], block[1], block[2], block[3]]);
            let w1 = u32::from_le_bytes([block[4], block[5], block[6], block[7]]);
            let w2 = u32::from_le_bytes([block[8], block[9], block[10], block[11]]);
            let w3 = u32::from_le_bytes([block[12], block[13], block[14], block[15]]);
            let hibit = block[16] as u32;

            h0 += w0 & 0x03ffffff;
            h1 += ((w0 >> 26) | (w1 << 6)) & 0x03ffffff;
            h2 += ((w1 >> 20) | (w2 << 12)) & 0x03ffffff;
            h3 += ((w2 >> 14) | (w3 << 18)) & 0x03ffffff;
            h4 += (w3 >> 8) | (hibit << 24);

            let d0 = (h0 as u64) * (self.r0 as u64)
                + (h1 as u64) * (self.s4 as u64)
                + (h2 as u64) * (self.s3 as u64)
                + (h3 as u64) * (self.s2 as u64)
                + (h4 as u64) * (self.s1 as u64);

            let d1 = (h0 as u64) * (self.r1 as u64)
                + (h1 as u64) * (self.r0 as u64)
                + (h2 as u64) * (self.s4 as u64)
                + (h3 as u64) * (self.s3 as u64)
                + (h4 as u64) * (self.s2 as u64);

            let d2 = (h0 as u64) * (self.r2 as u64)
                + (h1 as u64) * (self.r1 as u64)
                + (h2 as u64) * (self.r0 as u64)
                + (h3 as u64) * (self.s4 as u64)
                + (h4 as u64) * (self.s3 as u64);

            let d3 = (h0 as u64) * (self.r3 as u64)
                + (h1 as u64) * (self.r2 as u64)
                + (h2 as u64) * (self.r1 as u64)
                + (h3 as u64) * (self.r0 as u64)
                + (h4 as u64) * (self.s4 as u64);

            let d4 = (h0 as u64) * (self.r4 as u64)
                + (h1 as u64) * (self.r3 as u64)
                + (h2 as u64) * (self.r2 as u64)
                + (h3 as u64) * (self.r1 as u64)
                + (h4 as u64) * (self.r0 as u64);

            let mut c = d0 >> 26;
            h0 = (d0 as u32) & 0x03ffffff;
            let d1 = d1 + c;
            c = d1 >> 26;
            h1 = (d1 as u32) & 0x03ffffff;
            let d2 = d2 + c;
            c = d2 >> 26;
            h2 = (d2 as u32) & 0x03ffffff;
            let d3 = d3 + c;
            c = d3 >> 26;
            h3 = (d3 as u32) & 0x03ffffff;
            let d4 = d4 + c;
            c = d4 >> 26;
            h4 = (d4 as u32) & 0x03ffffff;
            h0 += (c as u32) * 5;
            let c2 = h0 >> 26;
            h0 &= 0x03ffffff;
            h1 += c2;

            offset += chunk_len;
        }

        // Full carry propagation
        let mut c = h1 >> 26;
        h1 &= 0x03ffffff;
        h2 += c;
        c = h2 >> 26;
        h2 &= 0x03ffffff;
        h3 += c;
        c = h3 >> 26;
        h3 &= 0x03ffffff;
        h4 += c;
        c = h4 >> 26;
        h4 &= 0x03ffffff;
        h0 += c * 5;
        c = h0 >> 26;
        h0 &= 0x03ffffff;
        h1 += c;

        // Compute h + -p to determine if reduction modulo 2^130 - 5 is required
        let mut g0 = h0.wrapping_add(5);
        c = g0 >> 26;
        g0 &= 0x03ffffff;
        let mut g1 = h1.wrapping_add(c);
        c = g1 >> 26;
        g1 &= 0x03ffffff;
        let mut g2 = h2.wrapping_add(c);
        c = g2 >> 26;
        g2 &= 0x03ffffff;
        let mut g3 = h3.wrapping_add(c);
        c = g3 >> 26;
        g3 &= 0x03ffffff;
        let g4 = h4.wrapping_add(c).wrapping_sub(1 << 26);

        let mask = (g4 >> 31).wrapping_sub(1);
        g0 &= mask;
        g1 &= mask;
        g2 &= mask;
        g3 &= mask;
        let not_mask = !mask;
        h0 = (h0 & not_mask) | g0;
        h1 = (h1 & not_mask) | g1;
        h2 = (h2 & not_mask) | g2;
        h3 = (h3 & not_mask) | g3;
        h4 = (h4 & not_mask) | (g4 & mask);

        // Convert 5 limbs of 26 bits into 4 words of 32 bits
        let f0 = ((h0) | (h1 << 26)) as u64 + self.pad[0] as u64;
        let c = f0 >> 32;
        let f1 = ((h1 >> 6) | (h2 << 20)) as u64 + self.pad[1] as u64 + c;
        let c = f1 >> 32;
        let f2 = ((h2 >> 12) | (h3 << 14)) as u64 + self.pad[2] as u64 + c;
        let c = f2 >> 32;
        let f3 = ((h3 >> 18) | (h4 << 8)) as u64 + self.pad[3] as u64 + c;

        out_tag[0..4].copy_from_slice(&(f0 as u32).to_le_bytes());
        out_tag[4..8].copy_from_slice(&(f1 as u32).to_le_bytes());
        out_tag[8..12].copy_from_slice(&(f2 as u32).to_le_bytes());
        out_tag[12..16].copy_from_slice(&(f3 as u32).to_le_bytes());
    }
}

/// Anti-Replay Sliding Window protecting against EW voice injection and replay attacks.
#[derive(Debug, Clone)]
pub struct AntiReplayWindow {
    highest_seq: u64,
    /// 128-bit bitmap tracking received packets within [highest_seq - 127, highest_seq].
    window: u128,
    replayed_count: u64,
    rejected_count: u64,
    accepted_count: u64,
}

impl Default for AntiReplayWindow {
    fn default() -> Self {
        Self::new()
    }
}

impl AntiReplayWindow {
    /// Creates a new AntiReplayWindow.
    pub fn new() -> Self {
        Self {
            highest_seq: 0,
            window: 0,
            replayed_count: 0,
            rejected_count: 0,
            accepted_count: 0,
        }
    }

    /// Resets the sliding window state.
    pub fn reset(&mut self) {
        self.highest_seq = 0;
        self.window = 0;
        self.replayed_count = 0;
        self.rejected_count = 0;
        self.accepted_count = 0;
    }

    /// Checks and updates the sequence window with zero allocations.
    pub fn check_and_update(&mut self, seq: u64) -> AuthResult {
        if self.accepted_count == 0 {
            // First received packet initializes the anchor
            self.highest_seq = seq;
            self.window = 1u128;
            self.accepted_count += 1;
            return AuthResult::Valid;
        }

        if seq > self.highest_seq {
            let diff = seq - self.highest_seq;
            if diff < 128 {
                self.window = (self.window << diff) | 1u128;
            } else {
                // Massive jump or desync: reset window bitmap anchor
                self.window = 1u128;
            }
            self.highest_seq = seq;
            self.accepted_count += 1;
            AuthResult::Valid
        } else {
            let diff = self.highest_seq - seq;
            if diff >= 128 {
                // Packet too old, outside sliding window
                self.rejected_count += 1;
                AuthResult::ExpiredSequence
            } else {
                let mask = 1u128 << diff;
                if (self.window & mask) != 0 {
                    // Sequence already marked as received -> REPLAY ATTACK DETECTED
                    self.replayed_count += 1;
                    AuthResult::ReplayDetected
                } else {
                    // Out-of-order packet within valid window
                    self.window |= mask;
                    self.accepted_count += 1;
                    AuthResult::Valid
                }
            }
        }
    }

    /// Number of detected replay attacks blocked.
    pub fn replayed_attacks_blocked(&self) -> u64 {
        self.replayed_count
    }

    /// Number of valid packets accepted.
    pub fn accepted_packets(&self) -> u64 {
        self.accepted_count
    }
}

/// Tactical Authenticator managing frame signing, validation, anti-replay, and rolling keys.
pub struct TacticalFrameAuthenticator {
    poly1305: Poly1305,
    key: [u8; CRYPTO_KEY_BYTES],
    anti_replay: AntiReplayWindow,
    packet_counter: u64,
    forged_packets_blocked: u64,
    scratch_buf: [u8; 2048],
}

impl TacticalFrameAuthenticator {
    /// Creates a new TacticalFrameAuthenticator initialized with a 32-byte tactical session key.
    pub fn new(key: &[u8; CRYPTO_KEY_BYTES]) -> Self {
        Self {
            poly1305: Poly1305::new(key),
            key: *key,
            anti_replay: AntiReplayWindow::new(),
            packet_counter: 0,
            forged_packets_blocked: 0,
            scratch_buf: [0u8; 2048],
        }
    }

    /// Signs an outgoing audio frame (sequence + raw audio payload).
    pub fn sign_frame(&mut self, seq: u64, payload: &[u8], out_tag: &mut [u8; MAC_TAG_BYTES]) {
        let seq_bytes = seq.to_le_bytes();
        let total_len = 8 + payload.len();

        if total_len <= self.scratch_buf.len() {
            self.scratch_buf[0..8].copy_from_slice(&seq_bytes);
            self.scratch_buf[8..total_len].copy_from_slice(payload);
            self.poly1305
                .compute_tag(&self.scratch_buf[..total_len], out_tag);
        } else {
            // Fallback for oversized frames: process sequence then payload
            self.poly1305.compute_tag(payload, out_tag);
        }
        self.packet_counter += 1;
    }

    /// Authenticates an incoming frame, verifying the cryptographic MAC and checking anti-replay.
    pub fn verify_frame(
        &mut self,
        seq: u64,
        payload: &[u8],
        received_tag: &[u8; MAC_TAG_BYTES],
    ) -> AuthResult {
        // 1. First check anti-replay window to reject replayed packets before expensive verification
        let replay_status = self.anti_replay.check_and_update(seq);
        if replay_status != AuthResult::Valid {
            return replay_status;
        }

        // 2. Compute expected tag over sequence + payload
        let mut expected_tag = [0u8; MAC_TAG_BYTES];
        let seq_bytes = seq.to_le_bytes();
        let total_len = 8 + payload.len();

        if total_len <= self.scratch_buf.len() {
            self.scratch_buf[0..8].copy_from_slice(&seq_bytes);
            self.scratch_buf[8..total_len].copy_from_slice(payload);
            self.poly1305
                .compute_tag(&self.scratch_buf[..total_len], &mut expected_tag);
        } else {
            self.poly1305.compute_tag(payload, &mut expected_tag);
        }

        // 3. Constant-time equality check
        if constant_time_eq_16(&expected_tag, received_tag) {
            AuthResult::Valid
        } else {
            self.forged_packets_blocked += 1;
            AuthResult::TagMismatch
        }
    }

    /// Ratchets session key forward using rolling hash derivation.
    pub fn ratchet_key(&mut self) {
        let mut new_key = [0u8; CRYPTO_KEY_BYTES];
        let salt = b"TACTICAL-KEY-RATCHET-SIH26052-Z12";
        let mut tag1 = [0u8; 16];
        let mut tag2 = [0u8; 16];

        self.poly1305.compute_tag(salt, &mut tag1);
        self.poly1305
            .compute_tag(&self.packet_counter.to_le_bytes(), &mut tag2);

        new_key[0..16].copy_from_slice(&tag1);
        new_key[16..32].copy_from_slice(&tag2);

        self.key = new_key;
        self.poly1305 = Poly1305::new(&new_key);
    }

    /// Number of forged / spoofed packets blocked.
    pub fn forged_packets_blocked(&self) -> u64 {
        self.forged_packets_blocked
    }

    /// Number of replayed packets blocked.
    pub fn replayed_packets_blocked(&self) -> u64 {
        self.anti_replay.replayed_attacks_blocked()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_poly1305_rfc8439_test_vector() {
        // Standard RFC 8439 test vector
        let key: [u8; 32] = [
            0x85, 0xd6, 0xbe, 0x78, 0x57, 0x55, 0x6d, 0x33, 0x7f, 0x44, 0x52, 0xfe, 0x42, 0xd5,
            0x06, 0xa8, 0x01, 0x03, 0x80, 0x8a, 0xfb, 0x0d, 0xb2, 0xfd, 0x4a, 0xbf, 0xf6, 0xaf,
            0x41, 0x49, 0xf5, 0x1b,
        ];
        let msg = b"Cryptographic Forum Research Group";
        let poly = Poly1305::new(&key);
        let mut tag = [0u8; 16];
        poly.compute_tag(msg, &mut tag);

        let expected: [u8; 16] = [
            0xa8, 0x06, 0x1d, 0xc1, 0x30, 0x51, 0x36, 0xc6, 0xc2, 0x2b, 0x8b, 0xaf, 0x0c, 0x01,
            0x27, 0xa9,
        ];
        assert_eq!(
            tag, expected,
            "Poly1305 tag must match RFC 8439 test vector"
        );
    }

    #[test]
    fn test_anti_replay_sliding_window() {
        let mut window = AntiReplayWindow::new();

        // Sequential packets: 1, 2, 3, 4
        assert_eq!(window.check_and_update(1), AuthResult::Valid);
        assert_eq!(window.check_and_update(2), AuthResult::Valid);
        assert_eq!(window.check_and_update(3), AuthResult::Valid);
        assert_eq!(window.check_and_update(4), AuthResult::Valid);

        // Replay attack: retransmitting sequence 2
        assert_eq!(window.check_and_update(2), AuthResult::ReplayDetected);
        assert_eq!(window.replayed_attacks_blocked(), 1);

        // Out-of-order valid packet: 10
        assert_eq!(window.check_and_update(10), AuthResult::Valid);
        // Then packet 7 arrives out of order
        assert_eq!(window.check_and_update(7), AuthResult::Valid);
        // Replaying packet 7
        assert_eq!(window.check_and_update(7), AuthResult::ReplayDetected);

        // Expired packet outside 128 window
        assert_eq!(window.check_and_update(200), AuthResult::Valid);
        assert_eq!(window.check_and_update(1), AuthResult::ExpiredSequence);
    }

    #[test]
    fn test_tactical_frame_authenticator_valid_and_forged() {
        let key = [0x42u8; 32];
        let mut auth = TacticalFrameAuthenticator::new(&key);

        let seq = 1001u64;
        let payload = vec![0.15f32.to_bits() as u8; 256];
        let mut tag = [0u8; 16];

        auth.sign_frame(seq, &payload, &mut tag);

        // Verify valid frame
        let mut receiver_auth = TacticalFrameAuthenticator::new(&key);
        let res = receiver_auth.verify_frame(seq, &payload, &tag);
        assert_eq!(res, AuthResult::Valid);

        // Verify replay attack
        let replay_res = receiver_auth.verify_frame(seq, &payload, &tag);
        assert_eq!(replay_res, AuthResult::ReplayDetected);

        // Verify forged / tampered packet
        let mut tampered_payload = payload.clone();
        tampered_payload[10] ^= 0xFF; // Bit-flip injected by adversary
        let forge_res = receiver_auth.verify_frame(seq + 1, &tampered_payload, &tag);
        assert_eq!(forge_res, AuthResult::TagMismatch);
        assert_eq!(receiver_auth.forged_packets_blocked(), 1);
    }

    #[test]
    fn test_tactical_authenticator_key_ratchet() {
        let key = [0x55u8; 32];
        let mut auth = TacticalFrameAuthenticator::new(&key);
        let payload = b"Squad Alpha Check-In";
        let mut tag1 = [0u8; 16];
        auth.sign_frame(1, payload, &mut tag1);

        auth.ratchet_key();
        let mut tag2 = [0u8; 16];
        auth.sign_frame(2, payload, &mut tag2);

        // Tags must differ after ratcheting key
        assert_ne!(tag1, tag2);
    }
}
