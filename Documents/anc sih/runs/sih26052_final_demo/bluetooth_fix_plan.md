# Bluetooth Fix Plan

- **Exact WirePlumber version**: `0.5.8` (Note: PipeWire and `wpctl` report version `1.4.2`, but `wireplumber --version` reports `0.5.8`).
- **Exact configuration mechanism**: WirePlumber `0.5.x` utilizes SPA-JSON format `.conf` files and `.conf.d/` drop-in directories for configuration (replacing the Lua-based configuration used in older `0.4.x` versions, although internal scripts remain Lua).
- **Exact relevant installed configuration file(s)**: `/usr/share/wireplumber/wireplumber.conf`
- **Exact current Bluetooth profile settings**:
  - `bluez5.auto-connect = "[ hfp_hf hsp_hs a2dp_sink hfp_ag hsp_ag a2dp_source ]"` (as seen in `wpctl inspect`)
  - `bluez5.profile = "off"`
- **Whether A2DP sink is currently allowed/disabled**: Allowed by default in WirePlumber's `auto-connect` list, but effectively disabled/failing due to BlueZ `Access denied` authorization failures during D-Bus endpoint negotiation.
- **Whether HFP/HSP is currently allowed/disabled**: Allowed by default in WirePlumber's `auto-connect` list, but effectively disabled/failing due to BlueZ `Hands-Free unit rejected` errors during authorization.
- **The smallest proposed configuration change**: 
  Create a custom WirePlumber drop-in configuration file to explicitly define `monitor.bluez.properties` with the desired `bluez5.roles` (e.g. `[ a2dp_sink hfp_hf ]`). If the authorization failure stems from BlueZ policies rather than WirePlumber, the smallest change would be adding `Enable=Source,Sink,Media,Socket` under the `[General]` section in BlueZ's configuration.
- **Exact file that would be changed**: `~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf` (this file would be created). Alternatively, if it is a BlueZ issue, `/etc/bluetooth/main.conf`.
- **Whether the proposed change requires restarting**: Yes. WirePlumber must be restarted (`systemctl --user restart wireplumber`), and if `main.conf` is touched, `sudo systemctl restart bluetooth` is required.
- **Rollback procedure**: Remove the newly created drop-in file (`rm ~/.config/wireplumber/wireplumber.conf.d/51-bluez.conf`) and restart WirePlumber (`systemctl --user restart wireplumber`). If BlueZ was altered, revert the change in `main.conf` and restart the bluetooth service.
