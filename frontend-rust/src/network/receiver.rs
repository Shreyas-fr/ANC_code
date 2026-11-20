//! Network receivers for SIH 26052 UDP audio and telemetry streams.

use std::net::UdpSocket;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use anc_rust::network::{AudioPacket, EdgeTelemetry, FecDecoder, AUDIO_FRAME_SAMPLES};

#[derive(Debug, Clone, Copy)]
pub struct StreamStats {
    pub packets_received: u64,
    pub packets_lost: u64,
    pub last_sequence: Option<u64>,
    pub last_arrival: Option<Instant>,
    pub loss_percentage: f32,
    pub packets_fec_recovered: u64,
    pub fec_recovery_rate: f32,
    pub rf_link_health: f32,
}

impl Default for StreamStats {
    fn default() -> Self {
        Self {
            packets_received: 0,
            packets_lost: 0,
            last_sequence: None,
            last_arrival: None,
            loss_percentage: 0.0,
            packets_fec_recovered: 0,
            fec_recovery_rate: 100.0,
            rf_link_health: 100.0,
        }
    }
}

pub type SharedStreamStats = Arc<Mutex<StreamStats>>;
pub type AudioFrameCallback = Arc<dyn Fn(&AudioPacket) + Send + Sync>;

/// Asynchronous UDP Audio Receiver thread with integrated Sliding-Window XOR Parity FEC.
pub struct UdpAudioReceiver {
    port: u16,
    running: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
    pub stats: SharedStreamStats,
}

impl UdpAudioReceiver {
    pub fn new(port: u16, callback: AudioFrameCallback) -> Self {
        let running = Arc::new(AtomicBool::new(true));
        let stats = Arc::new(Mutex::new(StreamStats::default()));

        let is_running = Arc::clone(&running);
        let stream_stats = Arc::clone(&stats);

        let handle = thread::spawn(move || {
            let socket = match UdpSocket::bind(format!("0.0.0.0:{}", port)) {
                Ok(s) => {
                    let _ = s.set_read_timeout(Some(Duration::from_millis(200)));
                    s
                }
                Err(e) => {
                    eprintln!("Failed to bind UDP audio socket on port {}: {}", port, e);
                    return;
                }
            };

            let mut buf = [0u8; 4096];
            let mut fec_decoder = FecDecoder::new();
            let mut rec_buf = [
                AudioPacket::new(0, [0.0; AUDIO_FRAME_SAMPLES]),
                AudioPacket::new(0, [0.0; AUDIO_FRAME_SAMPLES]),
            ];

            while is_running.load(Ordering::Relaxed) {
                match socket.recv_from(&mut buf) {
                    Ok((len, _)) => {
                        if let Ok(packet) = AudioPacket::deserialize(&buf[..len]) {
                            let n_rec = fec_decoder.process_packet(&packet, &mut rec_buf);

                            if let Ok(mut st) = stream_stats.lock() {
                                st.last_sequence = Some(packet.sequence);
                                st.packets_received = fec_decoder.stats.packets_received;
                                st.packets_lost = fec_decoder.stats.packets_lost;
                                st.packets_fec_recovered = fec_decoder.stats.packets_recovered;
                                st.fec_recovery_rate = fec_decoder.stats.recovery_rate;
                                st.rf_link_health = fec_decoder.stats.rf_link_health;
                                st.last_arrival = Some(Instant::now());

                                let total = st.packets_received + st.packets_lost;
                                if total > 0 {
                                    st.loss_percentage =
                                        (st.packets_lost as f32 / total as f32) * 100.0;
                                }
                            }

                            // Deliver reconstructed packets first, then incoming packet
                            for rec_packet in rec_buf.iter().take(n_rec) {
                                callback(rec_packet);
                            }
                            callback(&packet);
                        }
                    }
                    Err(ref e)
                        if e.kind() == std::io::ErrorKind::WouldBlock
                            || e.kind() == std::io::ErrorKind::TimedOut =>
                    {
                        // Read timeout - loop again
                    }
                    Err(e) => {
                        eprintln!("UDP receive error on port {}: {}", port, e);
                    }
                }
            }
        });

        Self {
            port,
            running,
            handle: Some(handle),
            stats,
        }
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::Relaxed);
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

pub type TelemetryCallback = Arc<dyn Fn(&EdgeTelemetry) + Send + Sync>;

/// Asynchronous UDP Telemetry Receiver thread.
pub struct UdpTelemetryReceiver {
    port: u16,
    running: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
    pub latest_telemetry: Arc<Mutex<Option<EdgeTelemetry>>>,
    pub last_arrival: Arc<Mutex<Option<Instant>>>,
}

impl UdpTelemetryReceiver {
    pub fn new(port: u16, callback: Option<TelemetryCallback>) -> Self {
        let running = Arc::new(AtomicBool::new(true));
        let latest_telemetry = Arc::new(Mutex::new(None));
        let last_arrival = Arc::new(Mutex::new(None));

        let is_running = Arc::clone(&running);
        let telem_store = Arc::clone(&latest_telemetry);
        let arrival_store = Arc::clone(&last_arrival);

        let handle = thread::spawn(move || {
            let socket = match UdpSocket::bind(format!("0.0.0.0:{}", port)) {
                Ok(s) => {
                    let _ = s.set_read_timeout(Some(Duration::from_millis(500)));
                    s
                }
                Err(e) => {
                    eprintln!(
                        "Failed to bind UDP telemetry socket on port {}: {}",
                        port, e
                    );
                    return;
                }
            };

            let mut buf = [0u8; 4096];

            while is_running.load(Ordering::Relaxed) {
                match socket.recv_from(&mut buf) {
                    Ok((len, _)) => {
                        if let Ok(telem) = serde_json::from_slice::<EdgeTelemetry>(&buf[..len]) {
                            if let Ok(mut store) = telem_store.lock() {
                                *store = Some(telem.clone());
                            }
                            if let Ok(mut arr) = arrival_store.lock() {
                                *arr = Some(Instant::now());
                            }
                            if let Some(ref cb) = callback {
                                cb(&telem);
                            }
                        }
                    }
                    Err(ref e)
                        if e.kind() == std::io::ErrorKind::WouldBlock
                            || e.kind() == std::io::ErrorKind::TimedOut =>
                    {
                        // Read timeout
                    }
                    Err(e) => {
                        eprintln!("UDP telemetry receive error on port {}: {}", port, e);
                    }
                }
            }
        });

        Self {
            port,
            running,
            handle: Some(handle),
            latest_telemetry,
            last_arrival,
        }
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::Relaxed);
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}
