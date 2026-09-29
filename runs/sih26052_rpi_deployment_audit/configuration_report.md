# SIH26052 Raspberry Pi Edge Prototype Configuration Report

## A. COMPUTE REAL-TIME VALIDATION
- **System**: Raspberry Pi 5 Model B Rev 1.1
- **CPU**: 4 Cores, 2.0 GiB RAM
- **OS**: Debian GNU/Linux 13 (trixie)
- **Model**: StatefulPolarLSTM (1,448,962 parameters)
- **Runtime**: PyTorch 2.14.0+cpu natively on ARM64
- **Performance**: Natively completed 5-minute prerecorded testing within the 16ms frame budget limit. Details are in `five_minute_test_summary.txt`.
- **Status**: PASSED

## B. STREAMING VALIDATION
- **Statefulness**: Model core explicitly managed with external cyclic STFT and iSTFT buffers over `h` and `c` buffers. State persists cleanly over sequential frames without NaN/Inf failures. 
- **Audio Contract**: Processing enforces exactly 16000 Hz, 1-channel mono, 256-sample frames (16 ms hop), and 512-point STFT.
- **Fail-safe Path**: Implemented. Drops gracefully to input bypass if exceptions or numerical instabilities occur.
- **Service**: systemd service `sih26052-edge.service` successfully deployed and starts on boot, running locally as normal user `shreyas`.
- **Status**: PASSED

## C. AUDIO I/O VALIDATION
- **ALSA Hardware**: No physical audio capture devices (microphones) or dedicated hardware codecs detected on `arecord -l` or `lsusb` apart from virtual null/default sinks.
- **Status**: AUDIO_INPUT_STATUS=NOT_CONNECTED

## D. END-TO-END LATENCY
- **Microphone-to-Headphone Measurement**: Not performed, as physical hardware is absent.
- **Status**: END_TO_END_LATENCY=NOT_MEASURED

## FINAL STATUS
**RPI_CONFIGURATION_VALID**
The edge software stack, Python runtime, inference application, and systemd service are fully validated, configured, and capable of real-time execution natively. Full end-to-end testing will be possible as soon as physical microphone arrays/hardware are attached.
