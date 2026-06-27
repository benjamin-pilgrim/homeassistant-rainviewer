# RainViewer Nowcast

Home Assistant custom integration for short-range rain arrival estimates using
RainViewer radar history.

The integration tracks recent RainViewer radar frames around a configured
location, estimates precipitation echo motion, and exposes sensors for
automation-friendly local nowcasting.

## Installation

### HACS custom repository

1. In HACS, add this repository as a custom repository.
2. Select category `Integration`.
3. Install `RainViewer Nowcast`.
4. Restart Home Assistant.
5. Add the integration from **Settings > Devices & services**.

### Manual

Copy `custom_components/rainviewer_nowcast` into your Home Assistant
`custom_components` directory, then restart Home Assistant.

## Configuration

By default the config flow uses your Home Assistant home coordinates. You can
also enter a manual latitude and longitude.

Options:

| Option | Default | Description |
|---|---:|---|
| Latitude | HA home latitude | Location to monitor. |
| Longitude | HA home longitude | Location to monitor. |
| Detection radius | `2 km` | Radius around the location considered "at home". |
| Forecast horizon | `45 min` | Furthest arrival estimate to expose. |
| Radar zoom | `7` | RainViewer image zoom. RainViewer's coordinate image endpoint supports up to `7`. |

## Entities

The integration creates:

| Entity | Description |
|---|---|
| `binary_sensor.rain_approaching` | On when radar echoes are projected to reach the location within the configured horizon. |
| `sensor.rain_arrival_eta` | Estimated minutes until precipitation reaches the location. |
| `sensor.rain_clear_eta` | Estimated minutes until the configured location clears again. |
| `sensor.rain_duration` | Estimated wet minutes within the configured forecast horizon. |
| `sensor.rain_motion_direction` | Compass direction the echoes are moving toward. |
| `sensor.rain_motion_speed` | Estimated echo speed in km/h. |
| `sensor.rain_frame_age` | Age of the latest RainViewer radar frame. |
| `sensor.rain_now_coverage` | Percentage of pixels with precipitation inside the detection radius. |
| `sensor.rain_nowcast_confidence` | Simple confidence score from motion consistency and projected hits. |
| `image.radar_map` | Latest 512px radar map image with an OpenStreetMap base layer, RainViewer radar overlay, and center marker. |
| `image.radar_overlay` | Latest raw 512px RainViewer radar overlay without base-map tiles. |

## Notes

- This tracks radar echo motion, not ground truth rainfall.
- `Rain Clear ETA` and `Rain Duration` are based on projecting the current radar
  mask forward; if precipitation still intersects the target at the forecast
  horizon, clear ETA is unknown.
- The estimate is most useful for the next 15-45 minutes.
- Showers can grow, decay, split, or evaporate before reaching the ground.
- RainViewer is used as an aggregate radar mosaic; individual station data is
  not required for the first version.
- The image entities refresh when the RainViewer frame changes. `Radar Map`
  uses OpenStreetMap tiles as a visual base map; `Radar Overlay` is the raw
  RainViewer overlay.
