//! UDP audio and telemetry receiver with sequence tracking and packet loss detection.

use std::net::UdpSocket;
use std::io;
use super::protocol::{AudioPacket, EdgeTelemetry};

/// UDP Audio Stream Receiver.
pub struct AudioReceiver {
    socket: UdpSocket,
    pub last_sequence: Option<u64>,
    pub packets_received: u64,
    pub packets_lost: u64,
}

impl AudioReceiver {
    pub fn bind(port: u16) -> io::Result<Self> {
        let socket = UdpSocket::bind(format!("0.0.0.0:{}", port))?;
        socket.set_nonblocking(false)?;
        Ok(Self {
            socket,
            last_sequence: None,
            packets_received: 0,
            packets_lost: 0,
        })
    }

    /// Receives the next incoming audio packet.
    pub fn recv_packet(&mut self) -> io::Result<AudioPacket> {
        let mut buf = [0u8; 4096];
        let (len, _) = self.socket.recv_from(&mut buf)?;
        let packet = AudioPacket::deserialize(&buf[..len])?;

        if let Some(last) = self.last_sequence {
            if packet.sequence > last + 1 {
                self.packets_lost += packet.sequence - (last + 1);
            }
        }
        self.last_sequence = Some(packet.sequence);
        self.packets_received += 1;

        Ok(packet)
    }
}

/// UDP Telemetry Receiver.
pub struct TelemetryReceiver {
    socket: UdpSocket,
}

impl TelemetryReceiver {
    pub fn bind(port: u16) -> io::Result<Self> {
        let socket = UdpSocket::bind(format!("0.0.0.0:{}", port))?;
        Ok(Self { socket })
    }

    pub fn recv_telemetry(&self) -> io::Result<EdgeTelemetry> {
        let mut buf = [0u8; 4096];
        let (len, _) = self.socket.recv_from(&mut buf)?;
        serde_json::from_slice(&buf[..len])
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))
    }
}
