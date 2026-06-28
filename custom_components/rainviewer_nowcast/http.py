"""HTTP views for RainViewer Nowcast."""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import RainViewerCoordinator

_LOGGER = logging.getLogger(__name__)

CLEAN_RADAR_BOUNDS_URL = (
    "/api/rainviewer_nowcast/{entry_id}/clean_radar_bounds.png"
)

_MIN_TILE_ZOOM = 0
_MAX_TILE_ZOOM = 12
_MIN_IMAGE_SIZE = 64
_MAX_IMAGE_SIZE = 2048


def clean_radar_bounds_url(entry_id: str) -> str:
    """Return the clean radar bounds overlay URL for a config entry."""
    return CLEAN_RADAR_BOUNDS_URL.format(entry_id=entry_id)


def async_setup_http(hass: HomeAssistant) -> None:
    """Set up integration HTTP views."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("http_view_registered"):
        return

    hass.http.register_view(RainViewerCleanRadarBoundsView())
    domain_data["http_view_registered"] = True


class RainViewerCleanRadarBoundsView(HomeAssistantView):
    """Serve clean radar overlays rendered for explicit lat/lon bounds."""

    url = CLEAN_RADAR_BOUNDS_URL
    name = "api:rainviewer_nowcast:clean_radar_bounds"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        entry_id: str,
    ) -> web.Response:
        """Return a transparent clean radar overlay image."""
        hass: HomeAssistant = request.app["hass"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise web.HTTPNotFound()

        coordinator = getattr(entry, "runtime_data", None)
        if not isinstance(coordinator, RainViewerCoordinator):
            raise web.HTTPServiceUnavailable()

        north = _query_float(request, "north")
        south = _query_float(request, "south")
        east = _query_float(request, "east")
        west = _query_float(request, "west")
        zoom = _query_int(request, "zoom", coordinator.zoom)
        width = _query_int(request, "width", 1200)
        height = _query_int(request, "height", 620)
        background_name = request.query.get("background")
        radar_opacity = _query_float_default(request, "opacity", 1.0)
        _validate_bounds(north=north, south=south, east=east, west=west)
        _validate_dimensions(zoom=zoom, width=width, height=height)
        _validate_opacity(radar_opacity)

        background = None
        if background_name is not None:
            background = await _read_private_background(hass, background_name)

        try:
            image = await coordinator.async_get_clean_radar_bounds_overlay(
                north=north,
                south=south,
                east=east,
                west=west,
                zoom=zoom,
                width=width,
                height=height,
                background=background,
                radar_opacity=radar_opacity,
            )
        except Exception as err:
            _LOGGER.debug("Could not render clean radar bounds overlay", exc_info=True)
            raise web.HTTPBadGateway() from err

        return web.Response(
            body=image,
            content_type="image/png",
            headers={"Cache-Control": "private, max-age=240"},
        )


def _query_float(request: web.Request, name: str) -> float:
    """Return a required floating-point query parameter."""
    value = request.query.get(name)
    if value is None:
        raise web.HTTPBadRequest(text=f"Missing query parameter: {name}")
    try:
        return float(value)
    except ValueError as err:
        raise web.HTTPBadRequest(text=f"Invalid query parameter: {name}") from err


def _query_float_default(request: web.Request, name: str, default: float) -> float:
    """Return an optional floating-point query parameter."""
    value = request.query.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as err:
        raise web.HTTPBadRequest(text=f"Invalid query parameter: {name}") from err


def _query_int(request: web.Request, name: str, default: int) -> int:
    """Return an optional integer query parameter."""
    value = request.query.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as err:
        raise web.HTTPBadRequest(text=f"Invalid query parameter: {name}") from err


def _validate_bounds(
    *,
    north: float,
    south: float,
    east: float,
    west: float,
) -> None:
    """Validate requested map bounds."""
    if not -85 <= south < north <= 85:
        raise web.HTTPBadRequest(text="Latitude bounds are invalid")
    if not -180 <= west < east <= 180:
        raise web.HTTPBadRequest(text="Longitude bounds are invalid")


def _validate_dimensions(*, zoom: int, width: int, height: int) -> None:
    """Validate requested tile zoom and output image dimensions."""
    if zoom < _MIN_TILE_ZOOM or zoom > _MAX_TILE_ZOOM:
        raise web.HTTPBadRequest(text="Unsupported tile zoom")
    if width < _MIN_IMAGE_SIZE or width > _MAX_IMAGE_SIZE:
        raise web.HTTPBadRequest(text="Image width is outside bounds")
    if height < _MIN_IMAGE_SIZE or height > _MAX_IMAGE_SIZE:
        raise web.HTTPBadRequest(text="Image height is outside bounds")


def _validate_opacity(opacity: float) -> None:
    """Validate the optional rendered radar opacity."""
    if opacity < 0.0 or opacity > 1.0:
        raise web.HTTPBadRequest(text="Opacity is outside bounds")


async def _read_private_background(
    hass: HomeAssistant,
    background_name: str,
) -> bytes:
    """Read a background image from the integration's private data directory."""
    relative_path = background_name.lstrip("/")
    if relative_path.startswith(".") or Path(relative_path).is_absolute():
        raise web.HTTPBadRequest(text="Background path is invalid")

    data_root = Path(hass.config.path("rainviewer_nowcast")).resolve()
    candidate = (data_root / relative_path).resolve()
    try:
        candidate.relative_to(data_root)
    except ValueError as err:
        raise web.HTTPBadRequest(text="Background path is invalid") from err
    if not candidate.is_file():
        raise web.HTTPBadRequest(text="Background file does not exist")

    return await hass.async_add_executor_job(candidate.read_bytes)
