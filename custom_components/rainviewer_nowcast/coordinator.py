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
    RadarMapTile,
    analyse_nowcast,
    base_map_tile_requests,
    radar_map_tile_requests,
    render_clean_radar_bounds_overlay,
    render_clean_radar_bounds_map,
    render_clean_radar_animation_map,
    render_clean_radar_animation_overlay,
    render_clean_radar_map,
    render_clean_radar_overlay,
    render_nowcast_animation_map,
    render_nowcast_animation_overlay,
    render_radar_animation_map,
    render_radar_animation_overlay,
    render_radar_map,
)
from .api import (
    RainViewerFrame,
    get_osm_tile,
    get_radar_tile,
    get_radar_xyz_tile,
    get_weather_maps,
)
from .const import (
    CONF_HORIZON_MINUTES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_VALIDATION_CAPTURE,
    CONF_VALIDATION_KEEP_DAYS,
    CONF_VALIDATION_SAVE_TILES,
    CONF_ZOOM,
    DEFAULT_HORIZON_MINUTES,
    DEFAULT_RADIUS_KM,
    DEFAULT_VALIDATION_CAPTURE,
    DEFAULT_VALIDATION_KEEP_DAYS,
    DEFAULT_VALIDATION_SAVE_TILES,
    DEFAULT_ZOOM,
)
from .validation import async_capture_validation

_LOGGER = logging.getLogger(__name__)
_MAX_BOUNDS_TILE_REQUESTS = 64

RainViewerConfigEntry = ConfigEntry


class RainViewerCoordinator(DataUpdateCoordinator[NowcastResult]):
    """Class to manage fetching and analysing RainViewer radar data."""

    def __init__(self, hass: HomeAssistant, entry: RainViewerConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._session = async_get_clientsession(hass=hass)
        self._base_tile_cache: dict[tuple[int, int, int], bytes] = {}
        self._clean_tile_cache: dict[tuple[int, int, int, int], bytes] = {}
        self._latest_host: str | None = None
        self._latest_frame: RainViewerFrame | None = None
        self.radar_image: bytes | None = None
        self.radar_overlay: bytes | None = None
        self.clean_radar_image: bytes | None = None
        self.clean_radar_overlay: bytes | None = None
        self.clean_radar_animation: bytes | None = None
        self.clean_radar_animation_overlay: bytes | None = None
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

    @property
    def validation_capture(self) -> bool:
        """Return whether validation capture is enabled."""
        return bool(
            self._entry.options.get(
                CONF_VALIDATION_CAPTURE,
                DEFAULT_VALIDATION_CAPTURE,
            )
        )

    @property
    def validation_save_tiles(self) -> bool:
        """Return whether validation capture should save analysis tiles."""
        return bool(
            self._entry.options.get(
                CONF_VALIDATION_SAVE_TILES,
                DEFAULT_VALIDATION_SAVE_TILES,
            )
        )

    @property
    def validation_keep_days(self) -> int:
        """Return validation capture retention in days."""
        return int(
            self._entry.options.get(
                CONF_VALIDATION_KEEP_DAYS,
                DEFAULT_VALIDATION_KEEP_DAYS,
            )
        )

    async def _async_update_data(self) -> NowcastResult:
        """Fetch the latest radar data and derive a nowcast."""
        maps = await get_weather_maps(self._session)
        frames = maps.frames[-7:]
        latest_frame = frames[-1] if frames else None
        if latest_frame is not None and (
            self._latest_frame is None
            or latest_frame.time != self._latest_frame.time
        ):
            self._clean_tile_cache.clear()
        self._latest_host = maps.host
        self._latest_frame = latest_frame
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

        if self.validation_capture:
            try:
                await async_capture_validation(
                    self.hass,
                    self._entry,
                    host=maps.host,
                    frames=frames,
                    analysis_tiles=analysis_tiles,
                    result=result,
                    latitude=self.latitude,
                    longitude=self.longitude,
                    radius_km=self.radius_km,
                    horizon_minutes=self.horizon_minutes,
                    zoom=self.zoom,
                    save_tiles=self.validation_save_tiles,
                    keep_days=self.validation_keep_days,
                )
            except Exception:
                _LOGGER.exception("Could not capture validation data")

        if display_tiles:
            self.radar_overlay = display_tiles[-1]
            self.clean_radar_overlay = render_clean_radar_overlay(
                radar_tile=analysis_tiles[-1]
            )
            self.clean_radar_animation_overlay = render_clean_radar_animation_overlay(
                radar_tiles=analysis_tiles
            )
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
                self.clean_radar_image = render_clean_radar_map(
                    radar_tile=analysis_tiles[-1],
                    base_tiles=base_tiles,
                )
                self.clean_radar_animation = render_clean_radar_animation_map(
                    radar_tiles=analysis_tiles,
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
                self.clean_radar_image = self.clean_radar_overlay
                self.clean_radar_animation = self.clean_radar_animation_overlay
                self.radar_animation = self.radar_animation_overlay
                self.nowcast_animation = self.nowcast_animation_overlay

            self.radar_image_last_updated = result.frame_time

        return result

    async def async_get_clean_radar_bounds_overlay(
        self,
        *,
        north: float,
        south: float,
        east: float,
        west: float,
        zoom: int,
        width: int,
        height: int,
        background: bytes | None = None,
        radar_opacity: float = 1.0,
    ) -> bytes:
        """Return clean radar rendered into the requested map bounds."""
        tile_requests = radar_map_tile_requests(
            north=north,
            south=south,
            east=east,
            west=west,
            zoom=zoom,
        )
        if len(tile_requests) > _MAX_BOUNDS_TILE_REQUESTS:
            raise ValueError("Requested clean radar overlay covers too many tiles")

        clean_tiles = []
        for tile_x, tile_y in tile_requests:
            clean_tiles.append(
                RadarMapTile(
                    data=await self.async_get_clean_radar_tile(
                        zoom,
                        tile_x,
                        tile_y,
                    ),
                    x=tile_x,
                    y=tile_y,
                )
            )

        if background is not None:
            return render_clean_radar_bounds_map(
                clean_tiles=clean_tiles,
                background=background,
                north=north,
                south=south,
                east=east,
                west=west,
                zoom=zoom,
                width=width,
                height=height,
                radar_opacity=radar_opacity,
            )

        return render_clean_radar_bounds_overlay(
            clean_tiles=clean_tiles,
            north=north,
            south=south,
            east=east,
            west=west,
            zoom=zoom,
            width=width,
            height=height,
        )

    async def async_get_clean_radar_tile(
        self,
        zoom: int,
        tile_x: int,
        tile_y: int,
    ) -> bytes:
        """Return a clean-rendered transparent XYZ radar tile."""
        if self._latest_host is None or self._latest_frame is None:
            raise RuntimeError("No RainViewer radar frame is available")

        cache_key = (self._latest_frame.time, zoom, tile_x, tile_y)
        if cache_key in self._clean_tile_cache:
            return self._clean_tile_cache[cache_key]

        radar_tile = await get_radar_xyz_tile(
            self._session,
            self._latest_host,
            self._latest_frame,
            zoom,
            tile_x,
            tile_y,
            smooth=False,
            snow=False,
        )
        rendered_tile = render_clean_radar_overlay(radar_tile=radar_tile)
        if len(self._clean_tile_cache) >= 256:
            self._clean_tile_cache.clear()
        self._clean_tile_cache[cache_key] = rendered_tile
        return rendered_tile
