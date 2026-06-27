"""RainViewer Nowcast coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .analysis import (
    BaseMapTile,
    NowcastResult,
    analyse_nowcast,
    base_map_tile_requests,
    render_nowcast_animation_map,
    render_nowcast_animation_overlay,
    render_radar_animation_map,
    render_radar_animation_overlay,
    render_radar_map,
)
from .api import get_osm_tile, get_radar_tile, get_weather_maps
from .const import (
    CONF_HORIZON_MINUTES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_ZOOM,
    DEFAULT_HORIZON_MINUTES,
    DEFAULT_RADIUS_KM,
    DEFAULT_ZOOM,
)

_LOGGER = logging.getLogger(__name__)

RainViewerConfigEntry = ConfigEntry


class RainViewerCoordinator(DataUpdateCoordinator[NowcastResult]):
    """Class to manage fetching and analysing RainViewer radar data."""

    def __init__(self, hass: HomeAssistant, entry: RainViewerConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._session = async_get_clientsession(hass=hass)
        self._base_tile_cache: dict[tuple[int, int, int], bytes] = {}
        self.radar_image: bytes | None = None
        self.radar_overlay: bytes | None = None
        self.radar_animation: bytes | None = None
        self.radar_animation_overlay: bytes | None = None
        self.nowcast_animation: bytes | None = None
        self.nowcast_animation_overlay: bytes | None = None
        self.radar_image_last_updated: datetime | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="rainviewer_nowcast",
            update_interval=timedelta(minutes=5),
        )

    @property
    def latitude(self) -> float:
        """Return the configured latitude."""
        return float(self._entry.data[CONF_LATITUDE])

    @property
    def longitude(self) -> float:
        """Return the configured longitude."""
        return float(self._entry.data[CONF_LONGITUDE])

    @property
    def radius_km(self) -> float:
        """Return the configured detection radius."""
        return float(self._entry.data.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM))

    @property
    def horizon_minutes(self) -> int:
        """Return the configured forecast horizon."""
        return int(
            self._entry.data.get(CONF_HORIZON_MINUTES, DEFAULT_HORIZON_MINUTES)
        )

    @property
    def zoom(self) -> int:
        """Return the configured RainViewer image zoom."""
        return int(self._entry.data.get(CONF_ZOOM, DEFAULT_ZOOM))

    async def _async_update_data(self) -> NowcastResult:
        """Fetch the latest radar data and derive a nowcast."""
        maps = await get_weather_maps(self._session)
        frames = maps.frames[-7:]
        analysis_tiles = []
        display_tiles = []
        frame_times = []

        for frame in frames:
            analysis_tile = await get_radar_tile(
                self._session,
                maps.host,
                frame,
                self.latitude,
                self.longitude,
                self.zoom,
                smooth=False,
                snow=False,
            )
            display_tile = await get_radar_tile(
                self._session,
                maps.host,
                frame,
                self.latitude,
                self.longitude,
                self.zoom,
                smooth=True,
                snow=False,
            )
            analysis_tiles.append(analysis_tile)
            display_tiles.append(display_tile)
            frame_times.append(frame.time)

        result = analyse_nowcast(
            tiles=analysis_tiles,
            frame_times=frame_times,
            generated=maps.generated,
            latitude=self.latitude,
            zoom=self.zoom,
            radius_km=self.radius_km,
            horizon_minutes=self.horizon_minutes,
        )

        if display_tiles:
            self.radar_overlay = display_tiles[-1]
            self.radar_animation_overlay = render_radar_animation_overlay(
                radar_tiles=display_tiles
            )
            self.nowcast_animation_overlay = render_nowcast_animation_overlay(
                radar_tiles=display_tiles,
                motion=result.motion,
                horizon_minutes=self.horizon_minutes,
            )
            try:
                base_tiles = []
                for tile_x, tile_y, x_offset, y_offset in base_map_tile_requests(
                    self.latitude,
                    self.longitude,
                    self.zoom,
                ):
                    cache_key = (self.zoom, tile_x, tile_y)
                    if cache_key not in self._base_tile_cache:
                        self._base_tile_cache[cache_key] = await get_osm_tile(
                            self._session,
                            self.zoom,
                            tile_x,
                            tile_y,
                        )
                    base_tiles.append(
                        BaseMapTile(
                            data=self._base_tile_cache[cache_key],
                            x_offset=x_offset,
                            y_offset=y_offset,
                        )
                    )
                self.radar_image = render_radar_map(
                    radar_tile=display_tiles[-1],
                    base_tiles=base_tiles,
                )
                self.radar_animation = render_radar_animation_map(
                    radar_tiles=display_tiles,
                    base_tiles=base_tiles,
                )
                self.nowcast_animation = render_nowcast_animation_map(
                    radar_tiles=display_tiles,
                    base_tiles=base_tiles,
                    motion=result.motion,
                    horizon_minutes=self.horizon_minutes,
                )
            except Exception:
                _LOGGER.exception("Could not render radar map image")
                self.radar_image = self.radar_overlay
                self.radar_animation = self.radar_animation_overlay
                self.nowcast_animation = self.nowcast_animation_overlay

            self.radar_image_last_updated = result.frame_time

        return result
