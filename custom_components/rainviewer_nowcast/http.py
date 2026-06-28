"""HTTP views for RainViewer Nowcast."""

from __future__ import annotations

import logging

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
    # Dashboard image elements are normal browser <img> requests and do not
    # include Home Assistant's frontend bearer token.
    requires_auth = False

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
        height = _query_int(request, "height", 624)
        _validate_bounds(north=north, south=south, east=east, west=west)
        _validate_dimensions(zoom=zoom, width=width, height=height)

        try:
            image = await coordinator.async_get_clean_radar_bounds_overlay(
                north=north,
                south=south,
                east=east,
                west=west,
                zoom=zoom,
                width=width,
                height=height,
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
