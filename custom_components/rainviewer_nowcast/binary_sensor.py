"""Binary sensor platform for RainViewer Nowcast."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import RainViewerConfigEntry, RainViewerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RainViewerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RainViewer binary sensors."""
    coordinator = config_entry.runtime_data
    async_add_entities([RainApproachingBinarySensor(coordinator, config_entry)])


class RainViewerBaseEntity(CoordinatorEntity[RainViewerCoordinator]):
    """Base RainViewer entity."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self._entry.entry_id)},
            manufacturer="RainViewer",
            model="Radar nowcast",
            name="RainViewer Nowcast",
        )

    @property
    def _attrs(self) -> dict[str, Any]:
        """Return common nowcast attributes."""
        data = self.coordinator.data
        if data is None:
            return {}
        motion = data.motion
        return {
            "raining_now": data.raining_now,
            "eta_minutes": data.eta_minutes,
            "clear_eta_minutes": data.clear_eta_minutes,
            "duration_minutes": data.duration_minutes,
            "confidence": data.confidence,
            "now_coverage_percent": data.now_coverage_percent,
            "frame_time": data.frame_time.isoformat() if data.frame_time else None,
            "generated_time": (
                data.generated_time.isoformat() if data.generated_time else None
            ),
            "frame_age_minutes": data.frame_age_minutes,
            "frame_count": data.frame_count,
            "motion_direction": motion.direction if motion else None,
            "motion_speed_kmh": motion.speed_kmh if motion else None,
            "motion_bearing_toward_deg": (
                motion.bearing_toward_deg if motion else None
            ),
            "motion_samples": motion.samples if motion else 0,
            "motion_consistency": motion.consistency if motion else None,
            "latitude": self.coordinator.latitude,
            "longitude": self.coordinator.longitude,
            "radius_km": self.coordinator.radius_km,
            "horizon_minutes": self.coordinator.horizon_minutes,
            "zoom": self.coordinator.zoom,
        }


class RainApproachingBinarySensor(RainViewerBaseEntity, BinarySensorEntity):
    """Whether precipitation is approaching the configured location."""

    _attr_name = "Rain Approaching"
    _attr_icon = "mdi:weather-pouring"

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_approaching"

    @property
    def is_on(self) -> bool:
        """Return true if rain is approaching."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.rain_approaching

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return nowcast details."""
        return self._attrs
