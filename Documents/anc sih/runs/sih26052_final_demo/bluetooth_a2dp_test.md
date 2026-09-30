# Bluetooth A2DP Test

### System
- Raspberry Pi hostname: `shreyas`
- WirePlumber version: 0.5.8
- PipeWire version: 1.4.2
- BlueZ version: 5.82

### Bluetooth
- device name: realme narzo 60 5G
- MAC address: A8:EF:5F:FF:6E:82
- paired state: yes
- trusted state: yes
- connected state: yes

### Configuration
- exact configuration path:
  `~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf`
- exact configuration contents:
```conf
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_sink ]
}
```

### Before
- wpctl status: Device present (ID 76), but no audio Source or Sink nodes.
- Bluetooth profile: `off` (Failing with `Access denied`)

### After
- wpctl status: Device present (ID 36), but still no audio Source or Sink nodes appeared under the Audio section.
- Bluetooth profile: BlueZ endpoints for `A2DPSink` registered successfully without `Access denied` or `Hands-Free unit rejected` errors. However, PipeWire's device profile remained inactive/off (or `audio-gateway` but unrouted).
- whether A2DP became active: The BlueZ endpoints successfully registered (authorization passed), but PipeWire did not activate the node.
- whether a PipeWire source appeared: NO.

### Audio Test
*(Not performed due to missing PipeWire audio source node)*
- capture path: N/A
- duration: N/A
- sample rate: N/A
- channels: N/A
- clipping: N/A
- finite-sample check: N/A

### Result
A2DP_PROFILE_ACTIVE_BUT_NO_AUDIO_NODE
