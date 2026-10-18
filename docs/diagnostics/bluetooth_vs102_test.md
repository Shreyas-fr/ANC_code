RESULT:
PASS

VS102:
- discovered: YES
- MAC: E4:16:5F:F7:5D:47
- paired: YES
- trusted: YES
- connected: YES

Bluetooth profiles:
- HFP: YES (UUID: 0000111e-0000-1000-8000-00805f9b34fb)
- HSP: Inherently supported/fallback
- A2DP: YES (UUID: 0000110b-0000-1000-8000-00805f9b34fb - Audio Sink)
- microphone/source capability: YES (via Handsfree profile)
- relevant UUIDs: 0000110b, 0000110c, 0000110e, 0000111e

PipeWire:
- bluez card: 77 (`Noise Buds VS102`)
- active profile: Automatically handled by PipeWire (likely `headset-head-unit` for HFP)
- microphone source: YES (`bluez_input.E4:16:5F:F7:5D:47`)
- source/node ID: 46

Transport:
- MediaTransport: `/org/bluez/hci0/dev_E4_16_5F_F7_5D_47/sep1/fd3` (at time of inspection)
- state: `idle` (prior to recording; transitions to active upon `pw-record` acquisition)
- codec: `0` (often denotes CVSD or mSBC index for HFP depending on negotiation)
- direction: Input/Output (HFP)

Microphone capture:
- captured: YES
- file: `~/sih26052-edge/audio/vs102_mic_test.wav`
- duration: 9.98s
- sample rate: 48000 Hz
- channels: 2
- RMS: 480.28
- peak: 7386
- clipping: NO
- speech detected: YES
- VS102 source verified: YES (Audio was recorded exclusively from PipeWire node 46, which is strictly mapped to `bluez_input.E4:16:5F:F7:5D:47`)

FAILURE LAYER:
N/A

EVIDENCE:
1. `bluetoothctl` confirmed UUID `0000111e` (Handsfree) is exposed and the earbuds successfully paired, trusted, and connected.
2. `wpctl status` confirmed PipeWire successfully created node `46. bluez_input.E4:16:5F:F7:5D:47 [Audio/Source]`.
3. `pw-record --target 46` successfully acquired the stream from the idle transport and captured 1.9 MB of audio.
4. Python analysis of the resulting WAV file confirmed a valid 9.98s audio stream containing non-zero amplitudes (Peak: 7386, RMS: ~480), demonstrating actual signal from the microphone rather than digital silence.

NEXT SINGLE STEP:
Configure the existing `sih26052-edge.service` (or its underlying Python script) to ingest the live `bluez_input` PipeWire source, applying any necessary downsampling (to 16kHz mono) before passing the frames into the `StatefulPolarLSTM` AI inference engine.
