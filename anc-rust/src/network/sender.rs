//! High-throughput UDP network audio & telemetry streamer for the edge daemon.

use std::io;
use std::net::{SocketAddr, UdpSocket};

use super::fec::FecEncoder;
use super::protocol::{AudioPacket, EdgeTelemetry, AUDIO_FRAME_SAMPLES};

/// Autonomous Edge Network Streamer.
pub struct EdgeSender {
    sock_enhanced: UdpSocket,
    sock_raw: UdpSocket,
    sock_telemetry: UdpSocket,
    target_enhanced_addr: SocketAddr,
    target_raw_addr: SocketAddr,
    target_telemetry_addr: SocketAddr,
}

impl EdgeSender {
    /// Binds local UDP sockets and targets the destination IP.
    pub fn bind(
        target_ip: &str,
        enhanced_port: u16,
        telemetry_port: u16,
        raw_port: u16,
    ) -> io::Result<Self> {
        let sock_enhanced = UdpSocket::bind("0.0.0.0:0")?;
        let sock_raw = UdpSocket::bind("0.0.0.0:0")?;
        let sock_telemetry = UdpSocket::bind("0.0.0.0:0")?;

        let target_enhanced_addr = format!("{}:{}", target_ip, enhanced_port)
            .parse()
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;
        let target_raw_addr = format!("{}:{}", target_ip, raw_port)
            .parse()
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;
        let target_telemetry_addr = format!("{}:{}", target_ip, telemetry_port)
            .parse()
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;

        Ok(Self {
            sock_enhanced,
            sock_raw,
            sock_telemetry,
            target_enhanced_addr,
            target_raw_addr,
            target_telemetry_addr,
        })
    }

    /// Sends an enhanced audio packet over UDP.
    pub fn send_enhanced(&self, sequence: u64, samples: &[f32]) -> io::Result<()> {
        let mut pkt_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
        let n = samples.len().min(AUDIO_FRAME_SAMPLES);
        pkt_samples[..n].copy_from_slice(&samples[..n]);

        let packet = AudioPacket::new(sequence, pkt_samples);
        let bytes = packet.serialize();
        self.sock_enhanced
            .send_to(&bytes, self.target_enhanced_addr)?;
        Ok(())
    }

    /// Sends an enhanced audio packet with sliding-window XOR FEC parity over UDP.
    pub fn send_enhanced_fec(
        &self,
        sequence: u64,
        samples: &[f32],
        encoder: &mut FecEncoder,
    ) -> io::Result<()> {
        let mut pkt_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
        let n = samples.len().min(AUDIO_FRAME_SAMPLES);
        pkt_samples[..n].copy_from_slice(&samples[..n]);

        let packet = encoder.encode(sequence, pkt_samples);
        let bytes = packet.serialize();
        self.sock_enhanced
            .send_to(&bytes, self.target_enhanced_addr)?;
        Ok(())
    }

    /// Sends a raw unenhanced audio packet over UDP.
    pub fn send_raw(&self, sequence: u64, samples: &[f32]) -> io::Result<()> {
        let mut pkt_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
        let n = samples.len().min(AUDIO_FRAME_SAMPLES);
        pkt_samples[..n].copy_from_slice(&samples[..n]);

        let packet = AudioPacket::new(sequence, pkt_samples);
        let bytes = packet.serialize();
        self.sock_raw.send_to(&bytes, self.target_raw_addr)?;
        Ok(())
    }

    /// Sends telemetry JSON data to the mission control operator.
    pub fn send_telemetry(&self, telemetry: &EdgeTelemetry) -> io::Result<()> {
        let json = serde_json::to_vec(telemetry).map_err(io::Error::other)?;
        self.sock_telemetry
            .send_to(&json, self.target_telemetry_addr)?;
        Ok(())
    }
}
