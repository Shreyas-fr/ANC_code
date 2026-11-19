### Before rollback
- wpctl status: Device present (ID 36), no Audio Sources or Sinks visible.
- profile: `off` (WirePlumber property), while the underlying SPA parameter was `audio-gateway`.
- transport state: `"idle"`
- temporary configuration:
```conf
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_sink ]
}
```

### Configuration rollback
- exact file removed: `~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf`
- confirmation that it no longer exists: File removed and deletion verified.

### After rollback
- wpctl status: Device successfully re-enumerated (ID 76), but still no Audio Sources or Sinks appeared.
- Bluetooth profile: `off`
- PipeWire device: ID 76 (`bluez_card.A8_EF_5F_FF_6E_82`)
- MediaTransport state: `"idle"`
- codec: `aptx_hd`

### Active playback test
- whether real phone audio was played: Yes (playback attempted).
- whether transport changed state: No, the transport remained explicitly stuck in the `"idle"` state.
- whether an Audio/Source node appeared: No Audio/Source node appeared.

### Audio capture
*(Not performed due to missing PipeWire audio source node)*
- path: N/A
- duration: N/A
- sample rate: N/A
- channels: N/A
- clipping: N/A
- finite sample result: N/A

### Final result
A2DP_TRANSPORT_REMAINS_IDLE
