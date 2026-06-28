"""RainViewer Nowcast integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import RainViewerConfigEntry, RainViewerCoordinator
from .http import async_setup_http

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
    Platform.SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: RainViewerConfigEntry
) -> bool:
    """Set up RainViewer Nowcast for this config entry."""
    async_setup_http(hass)
    coordinator = RainViewerCoordinator(hass, entry=entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: RainViewerConfigEntry
) -> bool:
    """Unload RainViewer Nowcast."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
