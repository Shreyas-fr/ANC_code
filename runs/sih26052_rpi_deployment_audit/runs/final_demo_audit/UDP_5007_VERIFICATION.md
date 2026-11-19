# UDP 5007 Verification

## Frontend implementation
The Mac frontend fully supports UDP port 5007. It is documented in `PROTOCOL.md` and `README.md` as the "Reference Input Audio Stream (Binary Extension)". In `config/frontend_config.json`, `input_port` is set to 5007. The `MainWindow` class in `ui/main_window.py` instantiates an `AudioReceiver` listening on port 5007 and actively pipes the received PCM samples into `self.wave_input.add_samples(samples)` to drive the INPUT AUDIO waveform panel. However, if no traffic is received, the frontend renders a fallback `custom_msg="N/A — PROTOCOL EXTENSION PORT 5007"`.

## Pi implementation
There is absolutely no implementation of UDP 5007 anywhere in the Raspberry Pi production codebase. An exhaustive recursive search across all Python scripts and bash scripts in `~/sih26052_edge/` yielded zero hits for port 5007 (or any reference to sending a raw unenhanced input stream over the network). The existing network sender (`prototype/pi_ai_network_sender.py`) strictly binds to port 5005.

## Packet format
The frontend expects 1032-byte UDP packets on port 5007 containing:
- An 8-byte `uint64` sequence number header (little-endian).
- A 1024-byte payload consisting of exactly 256 `float32` mono PCM samples at 16,000 Hz.

## Runtime packet observation
A 5-second passive packet capture (`tcpdump`/socket polling) on ports 5005, 5006, and 5007 on the Mac showed exactly **0 packets received**. The production pipeline is not currently transmitting live audio over the network (the `anc_stream.py` daemon is merely running a dummy noise loop locally on the Pi).

## 5005 comparison
UDP port 5005 is fully defined as the primary DFN3 Enhanced Audio output. The `AudioReceiver` decodes the identical 1032-byte packet format and pushes it to both the `self.wave_enhanced` UI panel and the `JitterBuffer` for live system audio playback. The Pi script `pi_ai_network_sender.py` handles reading the PipeWire source, running `ANCStream.process_frame()`, and transmitting the resulting enhanced chunks over UDP 5005.

## 5006 comparison
UDP port 5006 is defined for telemetry. The frontend's `TelemetryReceiver` expects a UTF-8 JSON payload to populate the right-side dashboard (latency, thermal, network stats). The Pi script `wav_udp_sender_16k.py` is configured to periodically send these telemetry JSON packets every 100 audio frames.

## Input waveform status
`INPUT_WAVEFORM_NOT_LIVE`
Because the Pi does not actually transmit UDP 5007 traffic, the frontend's left Input Waveform panel stays greyed out and displays the placeholder "N/A — PROTOCOL EXTENSION PORT 5007".

## Synchronization status
`NOT_IMPLEMENTED` (Since the 5007 transmission stream doesn't exist yet on the Pi, there is no synchronization to evaluate).

## Final classification
`FRONTEND_ONLY`

## Exact files inspected
- Mac:
  - `/Users/shreyasdivekar/Documents/anc sih/frontend/PROTOCOL.md`
  - `/Users/shreyasdivekar/Documents/anc sih/frontend/README.md`
  - `/Users/shreyasdivekar/Documents/anc sih/frontend/config/frontend_config.json`
  - `/Users/shreyasdivekar/Documents/anc sih/frontend/network/audio_receiver.py`
  - `/Users/shreyasdivekar/Documents/anc sih/frontend/network/telemetry_receiver.py`
  - `/Users/shreyasdivekar/Documents/anc sih/frontend/ui/main_window.py`
- Pi:
  - `~/sih26052_edge/app/anc_stream.py`
  - `~/sih26052_edge/prototype/pi_ai_network_sender.py`
  - `~/sih26052_edge/runs/dfn3_pi_optimization/wav_deployment/wav_udp_sender_16k.py`

## Any required next step
To make the 5007 input stream live, a new Pi-side component must be added (or the existing sender modified). This script must tap the raw 8kHz Rockerz microphone via PipeWire (`pw-record`), continuously resample it to 16kHz, pack it into the 256-sample `float32` chunks with the 8-byte sequence header, and send it over a UDP socket to port 5007 on the PC's IP address—ideally synchronized sequentially alongside the 5005 processing chunks.
