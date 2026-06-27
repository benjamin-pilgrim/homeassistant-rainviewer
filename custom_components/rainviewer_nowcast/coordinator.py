"""RainViewer Nowcast coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .analysis import NowcastResult, analyse_nowcast
from .api import get_radar_tile, get_weather_maps
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
        tiles = []
        frame_times = []

        for frame in frames:
            tile = await get_radar_tile(
                self._session,
                maps.host,
                frame,
                self.latitude,
                self.longitude,
                self.zoom,
            )
            tiles.append(tile)
            frame_times.append(frame.time)

        return analyse_nowcast(
            tiles=tiles,
            frame_times=frame_times,
            generated=maps.generated,
            latitude=self.latitude,
            zoom=self.zoom,
            radius_km=self.radius_km,
            horizon_minutes=self.horizon_minutes,
        )

