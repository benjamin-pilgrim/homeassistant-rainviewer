"""Radar image analysis for RainViewer Nowcast."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
import math

from PIL import Image, ImageDraw

from .const import ANALYSIS_SIZE, TILE_SIZE


@dataclass(slots=True, frozen=True)
class MotionVector:
    """Estimated radar echo motion."""

    dx_px_per_10min: float
    dy_px_per_10min: float
    samples: int
    speed_kmh: float
    bearing_toward_deg: float
    direction: str
    consistency: float


@dataclass(slots=True, frozen=True)
class NowcastResult:
    """Derived nowcast values."""

    rain_approaching: bool
    raining_now: bool
    eta_minutes: int | None
    clear_eta_minutes: int | None
    duration_minutes: int | None
    confidence: int
    now_coverage_percent: float
    frame_time: datetime | None
    generated_time: datetime | None
    frame_age_minutes: float | None
    motion: MotionVector | None
    frame_count: int


@dataclass(slots=True, frozen=True)
class BaseMapTile:
    """A base-map tile and its placement in the radar viewport."""

    data: bytes
    x_offset: int
    y_offset: int


def _decode_alpha(tile: bytes, size: int) -> list[int]:
    """Decode a tile to an alpha/intensity mask."""
    with Image.open(BytesIO(tile)) as image:
        rgba = image.convert("RGBA").resize((size, size), Image.Resampling.BILINEAR)
        return list(rgba.getchannel("A").getdata())


def _pixel(mask: list[int], size: int, x_coord: int, y_coord: int) -> int:
    """Return a mask pixel or zero outside the image."""
    if 0 <= x_coord < size and 0 <= y_coord < size:
        return mask[y_coord * size + x_coord]
    return 0


def _meters_per_pixel(latitude: float, zoom: int) -> float:
    """Return approximate Web Mercator meters per pixel at latitude."""
    return 156543.03392804097 * math.cos(math.radians(latitude)) / (2**zoom)


def _latlon_to_world_pixels(
    latitude: float,
    longitude: float,
    zoom: int,
    tile_size: int = 256,
) -> tuple[float, float]:
    """Return Web Mercator world-pixel coordinates for a lat/lon."""
    sin_lat = math.sin(math.radians(latitude))
    sin_lat = min(max(sin_lat, -0.9999), 0.9999)
    scale = tile_size * (2**zoom)
    x_coord = (longitude + 180) / 360 * scale
    y_coord = (
        0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
    ) * scale
    return x_coord, y_coord


def base_map_tile_requests(
    latitude: float,
    longitude: float,
    zoom: int,
) -> list[tuple[int, int, int, int]]:
    """Return OSM tile x/y values and viewport offsets for a centered image."""
    center_x, center_y = _latlon_to_world_pixels(latitude, longitude, zoom)
    left = center_x - TILE_SIZE / 2
    top = center_y - TILE_SIZE / 2
    osm_tile_size = 256
    requests: list[tuple[int, int, int, int]] = []

    for tile_x in range(
        math.floor(left / osm_tile_size),
        math.floor((left + TILE_SIZE - 1) / osm_tile_size) + 1,
    ):
        for tile_y in range(
            math.floor(top / osm_tile_size),
            math.floor((top + TILE_SIZE - 1) / osm_tile_size) + 1,
        ):
            requests.append(
                (
                    tile_x,
                    tile_y,
                    round(tile_x * osm_tile_size - left),
                    round(tile_y * osm_tile_size - top),
                )
            )

    return requests


def render_radar_map(
    *,
    radar_tile: bytes,
    base_tiles: list[BaseMapTile],
) -> bytes:
    """Render a 512px radar map image from base-map tiles and radar overlay."""
    canvas = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (238, 242, 244, 255))

    for base_tile in base_tiles:
        with Image.open(BytesIO(base_tile.data)) as image:
            canvas.alpha_composite(
                image.convert("RGBA"),
                (base_tile.x_offset, base_tile.y_offset),
            )

    with Image.open(BytesIO(radar_tile)) as image:
        radar = image.convert("RGBA")

    pixels = radar.load()
    for y_coord in range(radar.height):
        for x_coord in range(radar.width):
            red, green, blue, alpha = pixels[x_coord, y_coord]
            if alpha and red < 4 and green < 4 and blue < 4:
                pixels[x_coord, y_coord] = (red, green, blue, 0)

    canvas.alpha_composite(radar)

    draw = ImageDraw.Draw(canvas)
    center = TILE_SIZE // 2
    draw.line(
        (center - 16, center, center + 16, center),
        fill=(176, 0, 0, 255),
        width=3,
    )
    draw.line(
        (center, center - 16, center, center + 16),
        fill=(176, 0, 0, 255),
        width=3,
    )
    draw.ellipse(
        (center - 10, center - 10, center + 10, center + 10),
        outline=(255, 255, 255, 255),
        width=4,
    )
    draw.ellipse(
        (center - 5, center - 5, center + 5, center + 5),
        fill=(255, 255, 255, 255),
        outline=(176, 0, 0, 255),
        width=2,
    )

    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _direction_from_bearing(bearing: float) -> str:
    """Return an 8-point compass direction."""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return directions[int((bearing + 22.5) // 45) % 8]


def _estimate_pair_shift(
    previous: list[int],
    current: list[int],
    *,
    center_x: int,
    center_y: int,
    window: int = 28,
    max_shift: int = 10,
) -> tuple[int, int, float] | None:
    """Estimate how a precipitation pattern moved from previous to current."""
    energy = 0
    for y_coord in range(center_y - window, center_y + window + 1):
        for x_coord in range(center_x - window, center_x + window + 1):
            energy += _pixel(previous, ANALYSIS_SIZE, x_coord, y_coord)
            energy += _pixel(current, ANALYSIS_SIZE, x_coord, y_coord)

    if energy < 255 * 40:
        return None

    best_score: float | None = None
    best_dx = 0
    best_dy = 0

    for dy_coord in range(-max_shift, max_shift + 1):
        for dx_coord in range(-max_shift, max_shift + 1):
            score = 0
            count = 0
            for y_coord in range(center_y - window, center_y + window + 1, 2):
                for x_coord in range(center_x - window, center_x + window + 1, 2):
                    score += abs(
                        _pixel(current, ANALYSIS_SIZE, x_coord, y_coord)
                        - _pixel(
                            previous,
                            ANALYSIS_SIZE,
                            x_coord - dx_coord,
                            y_coord - dy_coord,
                        )
                    )
                    count += 1
            mean_score = score / count
            if best_score is None or mean_score < best_score:
                best_score = mean_score
                best_dx = dx_coord
                best_dy = dy_coord

    if best_score is None:
        return None
    return best_dx, best_dy, best_score


def _estimate_motion(
    masks: list[list[int]], latitude: float, zoom: int
) -> MotionVector | None:
    """Estimate local radar echo motion from recent masks."""
    if len(masks) < 2:
        return None

    center = ANALYSIS_SIZE // 2
    shifts: list[tuple[int, int]] = []
    for previous, current in zip(masks[-7:-1], masks[-6:], strict=False):
        shift = _estimate_pair_shift(
            previous,
            current,
            center_x=center,
            center_y=center,
        )
        if shift is not None:
            shifts.append((shift[0], shift[1]))

    if not shifts:
        return None

    dx = sum(shift[0] for shift in shifts) / len(shifts)
    dy = sum(shift[1] for shift in shifts) / len(shifts)
    variance = sum(
        (shift[0] - dx) ** 2 + (shift[1] - dy) ** 2 for shift in shifts
    ) / len(shifts)
    consistency = max(0.0, min(1.0, 1.0 - math.sqrt(variance) / 8.0))

    analysis_px_km = _meters_per_pixel(latitude, zoom) * (
        TILE_SIZE / ANALYSIS_SIZE
    ) / 1000
    east_km_per_10min = dx * analysis_px_km
    north_km_per_10min = -dy * analysis_px_km
    speed_kmh = math.hypot(east_km_per_10min, north_km_per_10min) * 6

    if speed_kmh < 3:
        return None

    bearing = (
        math.degrees(math.atan2(east_km_per_10min, north_km_per_10min)) + 360
    ) % 360
    return MotionVector(
        dx_px_per_10min=dx * (TILE_SIZE / ANALYSIS_SIZE),
        dy_px_per_10min=dy * (TILE_SIZE / ANALYSIS_SIZE),
        samples=len(shifts),
        speed_kmh=round(speed_kmh, 1),
        bearing_toward_deg=round(bearing, 1),
        direction=_direction_from_bearing(bearing),
        consistency=round(consistency, 2),
    )


def _coverage_percent(mask: list[int], radius_px: float) -> float:
    """Return precipitation-pixel coverage around the tile center."""
    center = TILE_SIZE // 2
    radius = max(2, math.ceil(radius_px))
    total = 0
    wet = 0

    for y_coord in range(center - radius, center + radius + 1):
        for x_coord in range(center - radius, center + radius + 1):
            if (x_coord - center) ** 2 + (y_coord - center) ** 2 > radius**2:
                continue
            total += 1
            if _pixel(mask, TILE_SIZE, x_coord, y_coord) > 24:
                wet += 1

    if total == 0:
        return 0.0
    return round(wet / total * 100, 1)


def _project_rain_window(
    latest_mask: list[int],
    motion: MotionVector | None,
    *,
    radius_px: float,
    horizon_minutes: int,
) -> tuple[int | None, int | None, int | None, int]:
    """Project the latest mask and return ETA, clear ETA, duration, confidence."""
    if motion is None:
        return None, None, None, 0

    center = TILE_SIZE // 2
    radius = max(2, math.ceil(radius_px))
    first_hit: int | None = None
    last_hit: int | None = None
    hit_minutes: list[int] = []

    for minutes in range(5, horizon_minutes + 1, 5):
        factor = minutes / 10
        source_center_x = center - motion.dx_px_per_10min * factor
        source_center_y = center - motion.dy_px_per_10min * factor

        hit = False
        for y_offset in range(-radius, radius + 1):
            for x_offset in range(-radius, radius + 1):
                if x_offset**2 + y_offset**2 > radius**2:
                    continue
                value = _pixel(
                    latest_mask,
                    TILE_SIZE,
                    round(source_center_x + x_offset),
                    round(source_center_y + y_offset),
                )
                if value > 24:
                    hit = True
                    break
            if hit:
                break

        if hit:
            hit_minutes.append(minutes)
            if first_hit is None:
                first_hit = minutes
            last_hit = minutes

    if first_hit is None or last_hit is None:
        return None, None, None, 0

    clear_eta = last_hit + 5
    if clear_eta > horizon_minutes:
        clear_eta = None

    duration = len(hit_minutes) * 5
    return first_hit, clear_eta, duration, min(40, len(hit_minutes) * 8)


def analyse_nowcast(
    *,
    tiles: list[bytes],
    frame_times: list[int],
    generated: int | None,
    latitude: float,
    zoom: int,
    radius_km: float,
    horizon_minutes: int,
) -> NowcastResult:
    """Analyse RainViewer tiles and return a local nowcast."""
    if not tiles:
        return NowcastResult(
            rain_approaching=False,
            raining_now=False,
            eta_minutes=None,
            clear_eta_minutes=None,
            duration_minutes=None,
            confidence=0,
            now_coverage_percent=0.0,
            frame_time=None,
            generated_time=None,
            frame_age_minutes=None,
            motion=None,
            frame_count=0,
        )

    analysis_masks = [_decode_alpha(tile, ANALYSIS_SIZE) for tile in tiles]
    latest_mask = _decode_alpha(tiles[-1], TILE_SIZE)
    motion = _estimate_motion(analysis_masks, latitude, zoom)

    radius_px = radius_km / (_meters_per_pixel(latitude, zoom) / 1000)
    now_coverage = _coverage_percent(latest_mask, radius_px)
    raining_now = now_coverage > 0

    eta_minutes: int | None
    clear_eta_minutes: int | None
    duration_minutes: int | None
    projection_confidence: int
    if raining_now:
        eta_minutes = 0
        _projected_eta, clear_eta_minutes, projected_duration, projection_confidence = (
            _project_rain_window(
                latest_mask,
                motion,
                radius_px=radius_px,
                horizon_minutes=horizon_minutes,
            )
        )
        duration_minutes = projected_duration
        if duration_minutes is None:
            duration_minutes = 5
        if projection_confidence == 0:
            projection_confidence = 35
    else:
        (
            eta_minutes,
            clear_eta_minutes,
            duration_minutes,
            projection_confidence,
        ) = _project_rain_window(
            latest_mask,
            motion,
            radius_px=radius_px,
            horizon_minutes=horizon_minutes,
        )

    rain_approaching = eta_minutes is not None and eta_minutes <= horizon_minutes
    motion_confidence = 0
    if motion is not None:
        motion_confidence = round(40 * motion.consistency)
        motion_confidence += min(20, motion.samples * 3)

    confidence = min(100, projection_confidence + motion_confidence)
    if not rain_approaching:
        confidence = min(confidence, 40)

    frame_time = (
        datetime.fromtimestamp(frame_times[-1], tz=UTC) if frame_times else None
    )
    generated_time = (
        datetime.fromtimestamp(generated, tz=UTC) if generated is not None else None
    )
    frame_age_minutes = None
    if frame_time is not None:
        frame_age_minutes = round(
            (datetime.now(tz=UTC) - frame_time).total_seconds() / 60,
            1,
        )

    return NowcastResult(
        rain_approaching=rain_approaching,
        raining_now=raining_now,
        eta_minutes=eta_minutes,
        clear_eta_minutes=clear_eta_minutes,
        duration_minutes=duration_minutes,
        confidence=confidence,
        now_coverage_percent=now_coverage,
        frame_time=frame_time,
        generated_time=generated_time,
        frame_age_minutes=frame_age_minutes,
        motion=motion,
        frame_count=len(tiles),
    )
