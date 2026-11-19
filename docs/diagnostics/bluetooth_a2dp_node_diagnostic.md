### Current state
- The previous authorization errors (`Access denied` and `Hands-Free unit rejected`) are fully resolved.
- BlueZ successfully negotiated an A2DP connection, registering endpoints (including `aptx_hd`).
- A PipeWire Device object is present, but NO PipeWire Audio Source node is spawned.

### PipeWire device object
- ID: `36`
- Name: `bluez_card.A8_EF_5F_FF_6E_82`
- API: `bluez5`
- Profile: `bluez5.profile = "off"` (WirePlumber property)
- Media Class: `Audio/Device`

### PipeWire node objects
- None found. `pw-cli list-objects` and `wpctl status` confirm there is no `Audio/Source` representing the Bluetooth stream.

### Profile information
- Available profiles (`EnumProfile`):
  - Index 0: `off`
  - Index 65536: `audio-gateway` (Description: "Audio Gateway (A2DP Source & HSP/HFP AG)")
- Active SPA Profile (`Profile` parameter):
  - Index: `65536` (`audio-gateway`)
- Note: Although the SPA plugin reports `audio-gateway` is active, WirePlumber's device dictionary still reflects `bluez5.profile = "off"`, indicating WirePlumber's policy engine has not formally activated or routed this profile.

### BlueZ device information
- UUIDs available include `0000110a` (Audio Source) and `0000110e` (A/V Remote Control).
- Device is paired, trusted, and connected.

### BlueZ MediaTransport information
- Transport Object Path: `/org/bluez/hci0/dev_A8_EF_5F_FF_6E_82/sep4/fd1`
- State: `"idle"`
- Codec: `aptx_hd`
- UUID: `0000110b-0000-1000-8000-00805f9b34fb` (Audio Sink - reflecting the Pi's local role)

### WirePlumber logs
- No errors related to Bluetooth node creation, BlueZ, or SPA plugins were found. WirePlumber successfully loaded the `main` profile and did not emit any warnings about failing to spawn the node.

### PipeWire logs
- No RTKit or node-creation errors occurred during the Bluetooth connection phase.

### Configuration
- `~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf` successfully restricted `bluez5.roles = [ a2dp_sink ]`.

### Root-cause evidence
1. The transport is successfully established at the BlueZ layer (a `MediaTransport1` object exists and negotiated the `aptx_hd` codec). 
2. The transport state is `"idle"`. In modern PipeWire (1.0+), the Bluetooth SPA plugin often defers the creation of the `Audio/Source` node until the transport state transitions from `"idle"` to `"pending"` or `"active"` (which requires the remote phone to actively begin streaming audio).
3. The PipeWire SPA profile name is `"audio-gateway"`. Because we artificially restricted the roles to ONLY `a2dp_sink`, WirePlumber's auto-profile-switching logic might be failing to match and formally select the `"audio-gateway"` profile in its dictionary (`bluez5.profile = "off"`), even though the underlying SPA plugin has activated the index `65536`.

### Recommended SINGLE next change
LIKELY_CAUSE

Because the MediaTransport state is `"idle"` and WirePlumber sees the profile as `"off"`, the node is not being instantiated. The recommended single next change is to temporarily restore the default `bluez5.roles` (by removing `51-bluez.conf` or setting it to `[ a2dp_sink a2dp_source hfp_hf hfp_ag ]`) to determine if WirePlumber's auto-profile policy requires the full role set to activate the `"audio-gateway"` profile and spawn the node. Alternatively, testing active playback from the phone's UI to push the transport state to `"active"` would rule out the idle-deferral mechanism.
