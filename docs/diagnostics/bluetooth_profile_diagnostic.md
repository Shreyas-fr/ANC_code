# Bluetooth Profile Diagnostic Report

## Profile Availability
- **A2DP Sink/Source Profiles**: Available. The `bluez5.auto-connect` property for the device lists `a2dp_sink` and `a2dp_source`. 
- **HFP/HSP Profiles**: Available. The `bluez5.auto-connect` property lists `hfp_hf`, `hsp_hs`, `hfp_ag`, and `hsp_ag`.
- **libspa Bluetooth Support**: Installed. `libspa-0.2-bluetooth` (version 1.4.2-1+rpt3) is present and contains the necessary BlueZ 5 codec and interface plugins (`libspa-bluez5.so`, `libspa-codec-bluez5-sbc.so`, etc.).

## Exact Error Responsible for Failure
The failure occurs during the BlueZ authorization phase when attempting to activate the audio profiles. The `bluetoothd` journal logs explicitly show:
- `src/profile.c:ext_auth() Hands-Free unit rejected A8:EF:5F:FF:6E:82:`
- `profiles/audio/a2dp.c:auth_cb() Access denied:`

This indicates that while the Bluetooth pairing succeeds, WirePlumber/PipeWire (acting as the BlueZ media endpoint) or the BlueZ agent policy is actively denying or failing to authorize the `Hands-Free` (HFP) and `A2DP` service connections from the phone.

## Minimum Configuration Change Required
To fix this, a configuration change is required in **WirePlumber's Bluetooth monitor configuration** (usually located in `/etc/wireplumber/bluetooth.lua.d/` or `/usr/share/wireplumber/wireplumber.conf.d/`). Specifically, the `bluez5.roles` property needs to explicitly enable and prioritize the `hfp_hf` (Hands-Free) and `a2dp_sink` roles, and WirePlumber must be granted proper policy to auto-authorize incoming connections without an interactive agent prompt. 

PROFILE_PRESENT_AUTHORIZATION_FAILURE
