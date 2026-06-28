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
| `image.radar_animation` | Animated PNG loop of recent radar frames on the OpenStreetMap base layer. |
| `image.radar_animation_overlay` | Animated PNG loop of recent radar overlays without base-map tiles. |
| `image.rain_nowcast_animation` | Animated PNG loop with observed radar followed by low-opacity projected future frames. |
| `image.rain_nowcast_animation_overlay` | Transparent observed-plus-projected nowcast animation without base-map tiles. |

## Notes

- This tracks radar echo motion, not ground truth rainfall.
- `Rain Clear ETA` and `Rain Duration` are based on projecting the current radar
  mask forward; if precipitation still intersects the target at the forecast
  horizon, clear ETA is unknown.
- The estimate is most useful for the next 15-45 minutes.
- Showers can grow, decay, split, or evaporate before reaching the ground.
- RainViewer is used as an aggregate radar mosaic; individual station data is
  not required for the first version.
- Analysis uses unsmoothed RainViewer Universal Blue rain tiles without separate
  snow coloring (`2/0_0`) and converts pixels through the published RainViewer
  color table to a relative intensity mask.
- Local rain detection requires a small cluster of wet pixels inside the
  configured radius, not a single barely-wet radar pixel.
- Display images use smoothed Universal Blue rain tiles without separate snow
  coloring (`2/1_0`) so the visual palette matches the analysis palette.
- The image entities refresh when the RainViewer frame changes. `Radar Map`
  uses OpenStreetMap tiles as a visual base map; `Radar Overlay` is the raw
  RainViewer overlay.
- Animation entities are APNG files served as `image/png`, preserving
  transparency for overlay use while remaining compatible with normal image
  cards in modern browsers.
- `Radar Animation` is observed history only. `Rain Nowcast Animation` appends
  generated future frames at low opacity so projected movement is visually
  distinct from observed radar.

## Validation capture

For local algorithm development, the integration has an optional validation
capture mode in the config entry options. When enabled, each update writes
append-only replay data under:

```text
/config/rainviewer_nowcast/validation
```

The capture stores daily JSONL rows, a `latest.json` snapshot, and optionally
deduplicated unsmoothed analysis tiles. This data is deliberately kept out of
Home Assistant entity attributes and recorder history because it changes every
poll and is intended for offline replay/scoring.
