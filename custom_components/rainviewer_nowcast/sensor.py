"""Sensor platform for RainViewer Nowcast."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .binary_sensor import RainViewerBaseEntity
from .coordinator import RainViewerConfigEntry, RainViewerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RainViewerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RainViewer sensors."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            RainArrivalEtaSensor(coordinator, config_entry),
            RainClearEtaSensor(coordinator, config_entry),
            RainDurationSensor(coordinator, config_entry),
            RainMotionDirectionSensor(coordinator, config_entry),
            RainMotionSpeedSensor(coordinator, config_entry),
            RainFrameAgeSensor(coordinator, config_entry),
            RainNowCoverageSensor(coordinator, config_entry),
            RainNowcastConfidenceSensor(coordinator, config_entry),
        ]
    )


class RainViewerSensor(RainViewerBaseEntity, SensorEntity):
    """Base RainViewer sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def _common_attributes(self) -> dict[str, Any]:
        """Return common attributes without duplicating the sensor state."""
        attrs = dict(self._attrs)
        attrs.pop("eta_minutes", None)
        attrs.pop("clear_eta_minutes", None)
        attrs.pop("duration_minutes", None)
        attrs.pop("confidence", None)
        attrs.pop("now_coverage_percent", None)
        attrs.pop("frame_age_minutes", None)
        attrs.pop("motion_direction", None)
        attrs.pop("motion_speed_kmh", None)
        return attrs


class RainArrivalEtaSensor(RainViewerSensor):
    """Estimated rain arrival time."""

    _attr_name = "Rain Arrival ETA"
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_arrival_eta"

    @property
    def native_value(self) -> int | None:
        """Return ETA in minutes."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.eta_minutes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._common_attributes()


class RainMotionDirectionSensor(RainViewerBaseEntity, SensorEntity):
    """Direction radar echoes are moving toward."""

    _attr_name = "Rain Motion Direction"
    _attr_icon = "mdi:compass"

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_motion_direction"

    @property
    def native_value(self) -> str | None:
        """Return compass direction."""
        if self.coordinator.data is None or self.coordinator.data.motion is None:
            return None
        return self.coordinator.data.motion.direction

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._attrs


class RainClearEtaSensor(RainViewerSensor):
    """Estimated time until the target area clears."""

    _attr_name = "Rain Clear ETA"
    _attr_icon = "mdi:weather-sunny-alert"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_clear_eta"

    @property
    def native_value(self) -> int | None:
        """Return clear ETA in minutes."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.clear_eta_minutes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._common_attributes()


class RainDurationSensor(RainViewerSensor):
    """Estimated rain duration within the forecast horizon."""

    _attr_name = "Rain Duration"
    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_duration"

    @property
    def native_value(self) -> int | None:
        """Return projected rain duration in minutes."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.duration_minutes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._common_attributes()


class RainMotionSpeedSensor(RainViewerSensor):
    """Estimated radar echo speed."""

    _attr_name = "Rain Motion Speed"
    _attr_icon = "mdi:speedometer"
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_motion_speed"

    @property
    def native_value(self) -> float | None:
        """Return speed in km/h."""
        if self.coordinator.data is None or self.coordinator.data.motion is None:
            return None
        return self.coordinator.data.motion.speed_kmh

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._common_attributes()


class RainFrameAgeSensor(RainViewerSensor):
    """Age of the latest RainViewer radar frame."""

    _attr_name = "Rain Frame Age"
    _attr_icon = "mdi:clock-outline"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_frame_age"

    @property
    def native_value(self) -> float | None:
        """Return latest frame age in minutes."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.frame_age_minutes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._common_attributes()


class RainNowCoverageSensor(RainViewerSensor):
    """Current local precipitation coverage."""

    _attr_name = "Rain Now Coverage"
    _attr_icon = "mdi:weather-rainy"
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_now_coverage"

    @property
    def native_value(self) -> float | None:
        """Return local wet-pixel coverage."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.now_coverage_percent

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._common_attributes()


class RainNowcastConfidenceSensor(RainViewerSensor):
    """Confidence score for the nowcast."""

    _attr_name = "Rain Nowcast Confidence"
    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self,
        coordinator: RainViewerCoordinator,
        entry: RainViewerConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_nowcast_confidence"

    @property
    def native_value(self) -> int | None:
        """Return confidence percentage."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.confidence

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return self._common_attributes()
