# Bluetooth Phone Test

## Hardware
- Raspberry Pi 5
- Bluetooth controller: `98:FE:54:39:9C:4F`
- Phone model/name: realme narzo 60 5G

## Bluetooth
- BlueZ version: 5.82
- Pairing status: yes
- Connection status: yes
- MAC address: `A8:EF:5F:FF:6E:82`
- negotiated profile: `off` (The HFP/A2DP audio profile initialization was rejected during authorization, leaving the profile in the 'off' state).

## Audio
- Phone → Pi available: NO
- Pi → Phone available: NO
- HFP/HSP available: NO (Hands-Free unit rejected by phone/bluetoothd)
- A2DP available: NO (PipeWire didn't expose any sinks/sources)
- Linux audio backend: PipeWire (1.4.2)
- source/sink device names: N/A (None created for Bluetooth device)
- sample rate: N/A
- channels: N/A

## Test
- capture performed: NO
- playback performed: NO
- duration: N/A
- clipping/NaN/Inf checks: N/A
- errors encountered: 
  - `src/profile.c:ext_auth() Hands-Free unit rejected A8:EF:5F:FF:6E:82`
  - `profiles/audio/a2dp.c:auth_cb() Access denied`

## Prototype Readiness
BLUETOOTH_CONNECTED_BUT_AUDIO_DIRECTION_UNAVAILABLE

## Recommended NEXT STEP
Configure PipeWire/WirePlumber to properly support and authorize HFP HF / A2DP Sink roles (e.g., enabling proper `bluez5` role overrides in wireplumber config, or fixing `bluetoothd` authorization policies) so the Pi can act as an audio receiver.
