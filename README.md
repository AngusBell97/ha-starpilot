# StarPilot for Home Assistant

Shows a comma device running StarPilot as a device in Home Assistant. It reads Galaxy, the web page StarPilot already serves on your home network, so nothing has to be installed or changed on the comma.

## What you get

| Kind | Entities |
|---|---|
| State | Status (Parked / Car on / Driving), Driving |
| Device health | Temperature, Car battery voltage, Free storage, Memory usage, Fan speed, Processes |
| Software | StarPilot version, Update, Driving model |
| Drives | Last drive distance, duration, engaged and end time; Distance in the past week |
| Navigation | Navigation state, Destination, Clear destination button |
| External GPU | Status, temperature, power and whether it is running the driving model (only when one is fitted) |
| Controls | Drive state (Automatic / Always offroad / Always onroad), Check for updates |
| Events | Drive finished, Notification |

Some diagnostic entities start disabled: the separate CPU, GPU and memory temperatures, Last boot, Processes running, Total distance, the external GPU supply voltage and the Location tracker.

There is one action, **StarPilot: Set destination** (`starpilot.navigate`). Give it either a search, or a latitude and longitude with an optional name.

## Limits

- The comma is only reachable on your home network. Away from home the entities show as unavailable.
- Galaxy gives password-free access to devices on the same local network that reach it by IP address. A proxy between Home Assistant and the comma will be refused.
- Give the comma a fixed address in your router. If it changes, use **Reconfigure** on the integration.
- "Last drive" is the most recent drive Galaxy has finished analysing, which can lag the drive you just finished by a few minutes.
- Drive state uses Galaxy's own control, so Galaxy's own checks apply (it refuses Always offroad unless the car is parked).

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
