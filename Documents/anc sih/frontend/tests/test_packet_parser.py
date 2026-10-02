import struct
import numpy as np
import pytest

def parse_udp_packet(data: bytes):
    """
    Parses a UDP audio packet:
      - 8-byte uint64 sequence number
      - 256 float32 PCM samples (1024 bytes)
    """
    if len(data) < 8:
        raise ValueError("Packet length < 8 bytes")
    header = data[:8]
    payload = data[8:]
    seq = struct.unpack('<Q', header)[0]
    samples = np.frombuffer(payload, dtype=np.float32)
    return seq, samples

def test_valid_packet_parsing():
    seq_num = 123456789
    pcm_in = np.sin(np.linspace(0, 2*np.pi, 256)).astype(np.float32)
    header = struct.pack('<Q', seq_num)
    payload = pcm_in.tobytes()
    packet = header + payload

    parsed_seq, parsed_pcm = parse_udp_packet(packet)
    assert parsed_seq == seq_num
    assert len(parsed_pcm) == 256
    np.testing.assert_allclose(parsed_pcm, pcm_in, rtol=1e-5)

def test_malformed_short_packet():
    short_data = b"\x01\x02\x03"
    with pytest.raises(ValueError):
        parse_udp_packet(short_data)
