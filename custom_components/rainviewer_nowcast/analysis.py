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


_INTENSITY_ALPHA_THRESHOLD = 24
_INTENSITY_WET_THRESHOLD = 18
_PALETTE_QUANT_BITS = 5
_PALETTE_QUANT_SIZE = 1 << _PALETTE_QUANT_BITS
_PALETTE_SHIFT = 8 - _PALETTE_QUANT_BITS
_PALETTE_LUT: list[int] | None = None
_STATIC_CLUTTER_MAX_INTENSITY = 60
_STATIC_CLUTTER_MIN_RATIO = 0.65
_STATIC_CLUTTER_MIN_FRAMES = 3

# RainViewer color scheme 2 "Universal Blue" rain ramp from the published API
# color table. Values are relative 0-255 intensity, not rainfall rate.
_INTENSITY_RAMP: tuple[tuple[tuple[int, int, int], int], ...] = (
    ((99, 97, 89), 1),  # -10 dBZ, alpha 20
    ((102, 99, 90), 2),  # -9 dBZ, alpha 25
    ((105, 102, 92), 5),  # -8 dBZ, alpha 30
    ((108, 104, 93), 7),  # -7 dBZ, alpha 36
    ((111, 107, 95), 10),  # -6 dBZ, alpha 41
    ((114, 110, 97), 12),  # -5 dBZ, alpha 46
    ((117, 112, 98), 15),  # -4 dBZ, alpha 52
    ((120, 115, 100), 17),  # -3 dBZ, alpha 57
    ((124, 117, 101), 19),  # -2 dBZ, alpha 62
    ((127, 120, 103), 22),  # -1 dBZ, alpha 68
    ((130, 123, 105), 24),  # 0 dBZ, alpha 73
    ((133, 125, 106), 27),  # 1 dBZ, alpha 78
    ((136, 128, 108), 29),  # 2 dBZ, alpha 84
    ((139, 130, 109), 32),  # 3 dBZ, alpha 89
    ((142, 133, 111), 34),  # 4 dBZ, alpha 94
    ((146, 136, 113), 36),  # 5 dBZ, alpha 100
    ((158, 147, 117), 39),  # 6 dBZ, alpha 110
    ((170, 158, 121), 41),  # 7 dBZ, alpha 120
    ((182, 169, 126), 44),  # 8 dBZ, alpha 130
    ((194, 180, 130), 46),  # 9 dBZ, alpha 140
    ((206, 192, 135), 49),  # 10 dBZ, alpha 150
    ((210, 196, 139), 51),  # 11 dBZ, alpha 160
    ((214, 200, 143), 53),  # 12 dBZ, alpha 170
    ((218, 204, 147), 56),  # 13 dBZ, alpha 180
    ((222, 208, 151), 58),  # 14 dBZ, alpha 190
    ((136, 221, 238), 61),  # 15 dBZ, alpha 255
    ((108, 209, 235), 63),  # 16 dBZ, alpha 255
    ((81, 197, 232), 66),  # 17 dBZ, alpha 255
    ((54, 186, 229), 68),  # 18 dBZ, alpha 255
    ((27, 174, 226), 70),  # 19 dBZ, alpha 255
    ((0, 163, 224), 73),  # 20 dBZ, alpha 255
    ((0, 154, 213), 75),  # 21 dBZ, alpha 255
    ((0, 145, 202), 78),  # 22 dBZ, alpha 255
    ((0, 136, 191), 80),  # 23 dBZ, alpha 255
    ((0, 127, 180), 83),  # 24 dBZ, alpha 255
    ((0, 119, 170), 85),  # 25 dBZ, alpha 255
    ((0, 112, 163), 87),  # 26 dBZ, alpha 255
    ((0, 105, 156), 90),  # 27 dBZ, alpha 255
    ((0, 98, 149), 92),  # 28 dBZ, alpha 255
    ((0, 91, 142), 95),  # 29 dBZ, alpha 255
    ((0, 85, 136), 97),  # 30 dBZ, alpha 255
    ((0, 81, 128), 100),  # 31 dBZ, alpha 255
    ((0, 78, 120), 102),  # 32 dBZ, alpha 255
    ((0, 74, 112), 104),  # 33 dBZ, alpha 255
    ((0, 71, 104), 107),  # 34 dBZ, alpha 255
    ((255, 238, 0), 109),  # 35 dBZ, alpha 255
    ((255, 224, 0), 112),  # 36 dBZ, alpha 255
    ((255, 210, 0), 114),  # 37 dBZ, alpha 255
    ((255, 197, 0), 117),  # 38 dBZ, alpha 255
    ((255, 183, 0), 119),  # 39 dBZ, alpha 255
    ((255, 170, 0), 121),  # 40 dBZ, alpha 255
    ((255, 159, 0), 124),  # 41 dBZ, alpha 255
    ((255, 149, 0), 126),  # 42 dBZ, alpha 255
    ((255, 139, 0), 129),  # 43 dBZ, alpha 255
    ((255, 129, 0), 131),  # 44 dBZ, alpha 255
    ((255, 68, 0), 134),  # 45 dBZ, alpha 255
    ((242, 54, 0), 136),  # 46 dBZ, alpha 255
    ((230, 40, 0), 138),  # 47 dBZ, alpha 255
    ((217, 27, 0), 141),  # 48 dBZ, alpha 255
    ((205, 13, 0), 143),  # 49 dBZ, alpha 255
    ((193, 0, 0), 146),  # 50 dBZ, alpha 255
    ((168, 0, 0), 148),  # 51 dBZ, alpha 255
    ((143, 0, 0), 151),  # 52 dBZ, alpha 255
    ((118, 0, 0), 153),  # 53 dBZ, alpha 255
    ((93, 0, 0), 155),  # 54 dBZ, alpha 255
    ((255, 170, 255), 158),  # 55 dBZ, alpha 255
    ((255, 159, 255), 160),  # 56 dBZ, alpha 255
    ((255, 149, 255), 163),  # 57 dBZ, alpha 255
    ((255, 139, 255), 165),  # 58 dBZ, alpha 255
    ((255, 129, 255), 168),  # 59 dBZ, alpha 255
    ((255, 119, 255), 170),  # 60 dBZ, alpha 255
    ((255, 108, 255), 172),  # 61 dBZ, alpha 255
    ((255, 98, 255), 175),  # 62 dBZ, alpha 255
    ((255, 88, 255), 177),  # 63 dBZ, alpha 255
    ((255, 78, 255), 180),  # 64 dBZ, alpha 255
    ((255, 255, 255), 182),  # 65 dBZ, alpha 255
    ((0, 255, 0), 206),  # 75 dBZ, alpha 255
    ((0, 255, 0), 255),  # 95 dBZ, alpha 255
)


def _decode_intensity(tile: bytes, size: int) -> list[int]:
    """Decode a tile to a relative 0-255 precipitation-intensity mask."""
    with Image.open(BytesIO(tile)) as image:
        rgba = image.convert("RGBA").resize((size, size), Image.Resampling.BILINEAR)
        return [_rgba_intensity(pixel) for pixel in rgba.getdata()]


def suppress_static_clutter_tiles(radar_tiles: list[bytes]) -> list[bytes]:
    """Remove persistent low-intensity stationary clutter from radar tiles."""
    if len(radar_tiles) < _STATIC_CLUTTER_MIN_FRAMES:
        return radar_tiles

    masks = [_decode_intensity(tile, TILE_SIZE) for tile in radar_tiles]
    static_clutter = _static_clutter_mask(masks)
    if not any(static_clutter):
        return radar_tiles

    cleaned_tiles = []
    for tile, mask in zip(radar_tiles, masks, strict=True):
        with Image.open(BytesIO(tile)) as image:
            radar = image.convert("RGBA")

        pixels = list(radar.getdata())
        radar.putdata(
            [
                (red, green, blue, 0)
                if static_clutter[index]
                and mask[index] <= _STATIC_CLUTTER_MAX_INTENSITY
                else (red, green, blue, alpha)
                for index, (red, green, blue, alpha) in enumerate(pixels)
            ]
        )
        cleaned_tiles.append(_encode_png(radar))

    return cleaned_tiles


def _rgba_intensity(pixel: tuple[int, int, int, int]) -> int:
    """Return relative precipitation intensity for a RainViewer RGBA pixel."""
    red, green, blue, alpha = pixel
    if alpha <= _INTENSITY_ALPHA_THRESHOLD or (red < 4 and green < 4 and blue < 4):
        return 0

    lut = _palette_lut()
    index = (
        (red >> _PALETTE_SHIFT) * _PALETTE_QUANT_SIZE * _PALETTE_QUANT_SIZE
        + (green >> _PALETTE_SHIFT) * _PALETTE_QUANT_SIZE
        + (blue >> _PALETTE_SHIFT)
    )
    return round(lut[index] * alpha / 255)


def _palette_lut() -> list[int]:
    """Return a quantized RGB lookup table for the intensity ramp."""
    global _PALETTE_LUT
    if _PALETTE_LUT is not None:
        return _PALETTE_LUT

    lut = []
    half_bin = 1 << (_PALETTE_SHIFT - 1)
    for red_q in range(_PALETTE_QUANT_SIZE):
        red = min(255, (red_q << _PALETTE_SHIFT) + half_bin)
        for green_q in range(_PALETTE_QUANT_SIZE):
            green = min(255, (green_q << _PALETTE_SHIFT) + half_bin)
            for blue_q in range(_PALETTE_QUANT_SIZE):
                blue = min(255, (blue_q << _PALETTE_SHIFT) + half_bin)
                lut.append(_palette_intensity(red, green, blue))

    _PALETTE_LUT = lut
    return lut


def _palette_intensity(red: int, green: int, blue: int) -> int:
    """Return interpolated intensity for an RGB color."""
    best_distance: float | None = None
    best_intensity = 0.0

    for (start_rgb, start_value), (end_rgb, end_value) in zip(
        _INTENSITY_RAMP,
        _INTENSITY_RAMP[1:],
        strict=False,
    ):
        segment = (
            end_rgb[0] - start_rgb[0],
            end_rgb[1] - start_rgb[1],
            end_rgb[2] - start_rgb[2],
        )
        point = (
            red - start_rgb[0],
            green - start_rgb[1],
            blue - start_rgb[2],
        )
        segment_length_sq = (
            segment[0] ** 2 + segment[1] ** 2 + segment[2] ** 2
        )
        if segment_length_sq == 0:
            continue

        position = (
            point[0] * segment[0]
            + point[1] * segment[1]
            + point[2] * segment[2]
        ) / segment_length_sq
        position = max(0.0, min(1.0, position))
        projected = (
            start_rgb[0] + segment[0] * position,
            start_rgb[1] + segment[1] * position,
            start_rgb[2] + segment[2] * position,
        )
        distance = (
            (red - projected[0]) ** 2
            + (green - projected[1]) ** 2
            + (blue - projected[2]) ** 2
        )

        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_intensity = start_value + (end_value - start_value) * position

    return round(best_intensity)


def _suppress_static_clutter_masks(masks: list[list[int]]) -> list[list[int]]:
    """Return intensity masks with persistent low-intensity clutter removed."""
    if len(masks) < _STATIC_CLUTTER_MIN_FRAMES:
        return masks

    static_clutter = _static_clutter_mask(masks)
    if not any(static_clutter):
        return masks

    return [
        [
            0
            if static_clutter[index] and value <= _STATIC_CLUTTER_MAX_INTENSITY
            else value
            for index, value in enumerate(mask)
        ]
        for mask in masks
    ]


def _static_clutter_mask(masks: list[list[int]]) -> list[bool]:
    """Return pixels that are low intensity in the same place over time."""
    if not masks:
        return []

    length = len(masks[0])
    low_hit_counts = [0] * length
    minimum_hits = max(
        _STATIC_CLUTTER_MIN_FRAMES,
        math.ceil(len(masks) * _STATIC_CLUTTER_MIN_RATIO),
    )

    for mask in masks:
        for index, value in enumerate(mask):
            if 0 < value <= _STATIC_CLUTTER_MAX_INTENSITY:
                low_hit_counts[index] += 1

    return [hits >= minimum_hits for hits in low_hit_counts]


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
    return _encode_png(_render_radar_frame(radar_tile, base_tiles))


def render_radar_animation_map(
    *,
    radar_tiles: list[bytes],
    base_tiles: list[BaseMapTile],
) -> bytes | None:
    """Render an animated radar map from recent radar frames."""
    frames = [_render_radar_frame(tile, base_tiles) for tile in radar_tiles]
    return _encode_apng(frames)


def render_nowcast_animation_map(
    *,
    radar_tiles: list[bytes],
    base_tiles: list[BaseMapTile],
    motion: MotionVector | None,
    horizon_minutes: int,
) -> bytes | None:
    """Render observed radar frames followed by low-opacity projected frames."""
    frames = [_render_radar_frame(tile, base_tiles) for tile in radar_tiles]
    future_overlays = _projected_radar_images(
        radar_tiles[-1] if radar_tiles else None,
        motion=motion,
        horizon_minutes=horizon_minutes,
    )
    for overlay in future_overlays:
        frame = _render_base_frame(base_tiles)
        frame.alpha_composite(overlay)
        _draw_center_marker(frame)
        frames.append(frame)

    return _encode_apng(frames)


def render_radar_animation_overlay(*, radar_tiles: list[bytes]) -> bytes | None:
    """Render an animated transparent radar overlay from recent frames."""
    frames = [_radar_image(tile) for tile in radar_tiles]
    return _encode_apng(frames)


def render_nowcast_animation_overlay(
    *,
    radar_tiles: list[bytes],
    motion: MotionVector | None,
    horizon_minutes: int,
) -> bytes | None:
    """Render observed overlays followed by low-opacity projected overlays."""
    frames = [_radar_image(tile) for tile in radar_tiles]
    frames.extend(
        _projected_radar_images(
            radar_tiles[-1] if radar_tiles else None,
            motion=motion,
            horizon_minutes=horizon_minutes,
        )
    )
    return _encode_apng(frames)


def _render_radar_frame(
    radar_tile: bytes,
    base_tiles: list[BaseMapTile],
) -> Image.Image:
    """Render a single radar frame over the base map."""
    canvas = _render_base_frame(base_tiles)
    canvas.alpha_composite(_radar_image(radar_tile))
    _draw_center_marker(canvas)
    return canvas


def _render_base_frame(base_tiles: list[BaseMapTile]) -> Image.Image:
    """Render only the base map for a radar frame."""
    canvas = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (238, 242, 244, 255))

    for base_tile in base_tiles:
        with Image.open(BytesIO(base_tile.data)) as image:
            canvas.alpha_composite(
                image.convert("RGBA"),
                (base_tile.x_offset, base_tile.y_offset),
            )

    return canvas


def _draw_center_marker(image: Image.Image) -> None:
    """Draw the configured location marker."""
    draw = ImageDraw.Draw(image)
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


def _radar_image(radar_tile: bytes) -> Image.Image:
    """Return a RainViewer radar tile with black background made transparent."""
    with Image.open(BytesIO(radar_tile)) as image:
        radar = image.convert("RGBA")

    pixels = radar.load()
    for y_coord in range(radar.height):
        for x_coord in range(radar.width):
            red, green, blue, alpha = pixels[x_coord, y_coord]
            if alpha and red < 4 and green < 4 and blue < 4:
                pixels[x_coord, y_coord] = (red, green, blue, 0)

    return radar


def _projected_radar_images(
    radar_tile: bytes | None,
    *,
    motion: MotionVector | None,
    horizon_minutes: int,
) -> list[Image.Image]:
    """Return low-opacity future radar frames shifted from the latest frame."""
    if radar_tile is None or motion is None:
        return []

    radar = _radar_image(radar_tile)
    radar = _with_scaled_alpha(radar, 0.38)
    frames: list[Image.Image] = []
    for minutes in range(5, min(horizon_minutes, 30) + 1, 5):
        factor = minutes / 10
        frames.append(
            _shift_image_no_wrap(
                radar,
                round(motion.dx_px_per_10min * factor),
                round(motion.dy_px_per_10min * factor),
            )
        )
    return frames


def _with_scaled_alpha(image: Image.Image, scale: float) -> Image.Image:
    """Return an image with its alpha channel scaled."""
    result = image.copy()
    alpha = result.getchannel("A").point(lambda value: round(value * scale))
    result.putalpha(alpha)
    return result


def _shift_image_no_wrap(image: Image.Image, dx: int, dy: int) -> Image.Image:
    """Shift an image without wrapping pixels around the viewport edges."""
    result = Image.new(image.mode, image.size, (0, 0, 0, 0))
    width, height = image.size

    source_left = max(0, -dx)
    source_top = max(0, -dy)
    source_right = min(width, width - dx)
    source_bottom = min(height, height - dy)

    if source_left >= source_right or source_top >= source_bottom:
        return result

    crop = image.crop((source_left, source_top, source_right, source_bottom))
    result.paste(crop, (max(0, dx), max(0, dy)))
    return result


def _encode_png(image: Image.Image) -> bytes:
    """Return PNG bytes for an image."""
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _encode_apng(frames: list[Image.Image]) -> bytes | None:
    """Return APNG bytes for a list of frames."""
    if not frames:
        return None

    output = BytesIO()
    frames[0].save(
        output,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=650,
        loop=0,
        disposal=2,
    )
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
            if _pixel(mask, TILE_SIZE, x_coord, y_coord) > _INTENSITY_WET_THRESHOLD:
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
                if value > _INTENSITY_WET_THRESHOLD:
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

    analysis_masks = _suppress_static_clutter_masks(
        [_decode_intensity(tile, ANALYSIS_SIZE) for tile in tiles]
    )
    full_size_masks = _suppress_static_clutter_masks(
        [_decode_intensity(tile, TILE_SIZE) for tile in tiles]
    )
    latest_mask = full_size_masks[-1]
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
