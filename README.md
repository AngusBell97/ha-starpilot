# StarPilot for Home Assistant

Shows a comma device running StarPilot as a device in Home Assistant. It reads Galaxy, the web page StarPilot already serves on your home network, so nothing has to be installed or changed on the comma.

## What you get

| Kind | Entities |
|---|---|
| State | Status (Parked / Car on / Driving), Driving, Drive state in effect |
| Device health | Temperature (plus CPU, GPU and memory), Thermal status, CPU usage, Memory, Storage, Fan speed, Car battery voltage, Processes, Last boot |
| Software | StarPilot version, Branch, Update, Updater, Last update check, Changed settings, Crash reports |
| Driving models | Driving model, Loaded driving model, Small driving model, health, models installed, download in progress |
| Drives | Last drive (distance, duration, engaged, Always On Lateral, start, end, model, distracted and unresponsive moments), past week and all-time totals, six records, analysis state |
| Navigation | State, Destination, Next instruction, GPS source, network, map usage counters, Clear destination button |
| External GPU | Status, link, temperature and memory temperature, highest logged temperatures, usage, power, supply voltage / current / power, clock, fan, frame time, USB speed and link errors, running the driving model (only when one is fitted) |
| Other | Sentry events, Outside temperature, Galaxy remote access, Galaxy hotspot |
| Controls | Drive state (Automatic / Always offroad / Always onroad), Navigation, Slow for turns, Avoid tolls / motorways / ferries, Check for updates, Reset highest GPU temperatures |
| Events | Drive finished, Notification |

The per-core CPU usage sensors and the Location tracker start disabled. External GPU readings such as temperature, usage and power only have values while the driving model is running on it.

## Actions

- **Set destination** (`starpilot.navigate`): give either a search, or a latitude and longitude with an optional name.
- **Get settings** (`starpilot.get_settings`): reads one Galaxy settings page (for example `sounds`, `lane_change`, `slc` or `aol`) with each setting's value and choices.
- **Change a setting** (`starpilot.set_setting`): changes one setting by page and name, the way Galaxy's own page does. Most settings can only be changed while parked.

## Limits

- The comma is only reachable on your home network. Away from home the entities show as unavailable.
- Galaxy gives password-free access to devices on the same local network that reach it by IP address. A proxy between Home Assistant and the comma will be refused.
- Give the comma a fixed address in your router. If it changes, use **Reconfigure** on the integration.
- "Last drive" is the most recent drive Galaxy has finished analysing, which can lag the drive you just finished by a few minutes.
- Drive state uses Galaxy's own control, so Galaxy's own checks apply. It only accepts Always offroad while the car is on and it can see the car is in Park; with the car off it refuses and Home Assistant shows Galaxy's reason.
- CPU usage needs two readings a couple of seconds apart, so the device-health poll takes about two seconds longer than the others.

## Notifications from the comma

The Notification event shows what the comma sends by itself, such as Sentry alarms or a drive summary. In Galaxy open **Connections › Notifications › Home Assistant** and enter your Home Assistant address and a long-lived access token, leaving the notify service empty so it posts to `/api/events/starpilot_notification`.

## Install

Copy `custom_components/starpilot` into the `custom_components` folder of your Home Assistant configuration, restart Home Assistant, then add **StarPilot** under Settings › Devices & services and enter the comma's address.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```

`tools/smoke.py <address>` reads a real comma with the integration's own client and prints what each entity would show.
