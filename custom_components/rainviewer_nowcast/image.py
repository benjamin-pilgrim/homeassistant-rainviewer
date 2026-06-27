"""Image platform for RainViewer Nowcast."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.image import ImageEntity
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
    """Set up RainViewer image entities."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            RainViewerRadarMapImage(coordinator, config_entry),
            RainViewerRadarOverlayImage(coordinator, config_entry),
            RainViewerRadarAnimationImage(coordinator, config_entry),
            RainViewerRadarAnimationOverlayImage(coordinator, config_entry),
        ]
    )


class RainViewerRadarMapImage(
    CoordinatorEntity[RainViewerCoordinator], ImageEntity
):
    """Latest RainViewer radar map image."""

    _attr_attribution = ATTRIBUTION
    _attr_name = "Radar Map"
    _attr_content_type = "image/png"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the image entity."""
        ImageEntity.__init__(self, coordinator.hass)
        CoordinatorEntity.__init__(self, coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_radar_map"

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
    def image_last_updated(self) -> datetime | None:
        """Return when the image last changed."""
        return self.coordinator.radar_image_last_updated

    async def async_image(self) -> bytes | None:
        """Return latest radar map image bytes."""
        return self.coordinator.radar_image

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return nowcast details."""
        data = self.coordinator.data
        if data is None:
            return {}
        motion = data.motion
        return {
            "raining_now": data.raining_now,
            "rain_approaching": data.rain_approaching,
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
            "motion_direction": motion.direction if motion else None,
            "motion_speed_kmh": motion.speed_kmh if motion else None,
            "latitude": self.coordinator.latitude,
            "longitude": self.coordinator.longitude,
            "zoom": self.coordinator.zoom,
        }


class RainViewerRadarOverlayImage(RainViewerRadarMapImage):
    """Latest RainViewer radar overlay image without a base map."""

    _attr_name = "Radar Overlay"

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the image entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_radar_overlay"

    async def async_image(self) -> bytes | None:
        """Return latest raw radar overlay image bytes."""
        return self.coordinator.radar_overlay


class RainViewerRadarAnimationImage(RainViewerRadarMapImage):
    """Animated radar map loop."""

    _attr_name = "Radar Animation"

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the image entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_radar_animation"

    async def async_image(self) -> bytes | None:
        """Return latest animated radar map image bytes."""
        return self.coordinator.radar_animation


class RainViewerRadarAnimationOverlayImage(RainViewerRadarMapImage):
    """Animated transparent radar overlay loop."""

    _attr_name = "Radar Animation Overlay"

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the image entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_radar_animation_overlay"

    async def async_image(self) -> bytes | None:
        """Return latest animated radar overlay bytes."""
        return self.coordinator.radar_animation_overlay
