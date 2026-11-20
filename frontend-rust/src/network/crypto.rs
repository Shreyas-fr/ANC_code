//! Tactical Audio Cryptographic Verification & Anti-Spoofing Monitoring for Frontend.
//!
//! Provides frontend telemetry, HUD counters, and packet authentication hooks
//! protecting the mission dashboard against electronic warfare RF spoofing and replay attacks.

pub use anc_rust::network::crypto::{
    constant_time_eq_16, AntiReplayWindow, AuthResult, Poly1305, TacticalFrameAuthenticator,
    CRYPTO_KEY_BYTES, MAC_TAG_BYTES, REPLAY_WINDOW_SIZE,
};

use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
};

/// Live anti-spoofing and cryptographic status telemetry for the GUI dashboard.
#[derive(Debug, Default)]
pub struct AntiSpoofTelemetry {
    pub verified_packets: AtomicU64,
    pub forged_packets_blocked: AtomicU64,
    pub replayed_packets_blocked: AtomicU64,
    pub expired_packets_dropped: AtomicU64,
}

impl AntiSpoofTelemetry {
    pub fn new() -> Arc<Self> {
        Arc::new(Self::default())
    }

    pub fn record_result(&self, res: AuthResult) {
        match res {
            AuthResult::Valid => {
                self.verified_packets.fetch_add(1, Ordering::Relaxed);
            }
            AuthResult::TagMismatch => {
                self.forged_packets_blocked.fetch_add(1, Ordering::Relaxed);
            }
            AuthResult::ReplayDetected => {
                self.replayed_packets_blocked
                    .fetch_add(1, Ordering::Relaxed);
            }
            AuthResult::ExpiredSequence => {
                self.expired_packets_dropped.fetch_add(1, Ordering::Relaxed);
            }
        }
    }

    pub fn snapshot(&self) -> (u64, u64, u64, u64) {
        (
            self.verified_packets.load(Ordering::Relaxed),
            self.forged_packets_blocked.load(Ordering::Relaxed),
            self.replayed_packets_blocked.load(Ordering::Relaxed),
            self.expired_packets_dropped.load(Ordering::Relaxed),
        )
    }
}

/// Frontend packet validator wrapping TacticalFrameAuthenticator with thread-safe counters.
pub struct FrontendCryptoVerifier {
    authenticator: TacticalFrameAuthenticator,
    telemetry: Arc<AntiSpoofTelemetry>,
}

impl FrontendCryptoVerifier {
    pub fn new(key: &[u8; CRYPTO_KEY_BYTES], telemetry: Arc<AntiSpoofTelemetry>) -> Self {
        Self {
            authenticator: TacticalFrameAuthenticator::new(key),
            telemetry,
        }
    }

    pub fn verify_and_record(
        &mut self,
        seq: u64,
        payload: &[u8],
        tag: &[u8; MAC_TAG_BYTES],
    ) -> AuthResult {
        let res = self.authenticator.verify_frame(seq, payload, tag);
        self.telemetry.record_result(res);
        res
    }

    pub fn telemetry(&self) -> Arc<AntiSpoofTelemetry> {
        Arc::clone(&self.telemetry)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_frontend_crypto_verifier_telemetry() {
        let key = [0x77u8; 32];
        let tele = AntiSpoofTelemetry::new();
        let mut verifier = FrontendCryptoVerifier::new(&key, Arc::clone(&tele));

        let mut signer = TacticalFrameAuthenticator::new(&key);
        let mut tag = [0u8; 16];
        let payload = b"Radio Broadcast";
        signer.sign_frame(1, payload, &mut tag);

        let res = verifier.verify_and_record(1, payload, &tag);
        assert_eq!(res, AuthResult::Valid);

        let replay = verifier.verify_and_record(1, payload, &tag);
        assert_eq!(replay, AuthResult::ReplayDetected);

        let mut forged_tag = tag;
        forged_tag[0] ^= 0x01;
        let forged = verifier.verify_and_record(2, payload, &forged_tag);
        assert_eq!(forged, AuthResult::TagMismatch);

        let (verified, forged_cnt, replayed_cnt, expired_cnt) = tele.snapshot();
        assert_eq!(verified, 1);
        assert_eq!(forged_cnt, 1);
        assert_eq!(replayed_cnt, 1);
        assert_eq!(expired_cnt, 0);
    }
}
