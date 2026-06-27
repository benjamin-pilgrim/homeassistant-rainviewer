"""Config flow for RainViewer Nowcast."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import get_weather_maps
from .const import (
    CONF_HORIZON_MINUTES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_ZOOM,
    DEFAULT_HORIZON_MINUTES,
    DEFAULT_RADIUS_KM,
    DEFAULT_ZOOM,
    DOMAIN,
    MAX_HORIZON_MINUTES,
    MAX_RADIUS_KM,
    MAX_ZOOM,
    MIN_HORIZON_MINUTES,
    MIN_RADIUS_KM,
    MIN_ZOOM,
)


def _entry_title(latitude: float, longitude: float) -> str:
    """Return a readable config-entry title."""
    return f"RainViewer {latitude:.4f}, {longitude:.4f}"


class RainViewerNowcastConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a RainViewer Nowcast config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle a flow start."""
        errors: dict[str, str] = {}

        default_latitude = round(float(self.hass.config.latitude or 0), 6)
        default_longitude = round(float(self.hass.config.longitude or 0), 6)

        if user_input is not None:
            latitude = float(user_input[CONF_LATITUDE])
            longitude = float(user_input[CONF_LONGITUDE])
            radius_km = float(user_input[CONF_RADIUS_KM])
            horizon_minutes = int(user_input[CONF_HORIZON_MINUTES])
            zoom = int(user_input[CONF_ZOOM])

            session = async_get_clientsession(hass=self.hass)
            try:
                await get_weather_maps(session)
            except TimeoutError:
                errors["base"] = "timeout"
            except (aiohttp.ClientError, KeyError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    f"{latitude:.5f},{longitude:.5f}",
                    raise_on_progress=False,
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_entry_title(latitude, longitude),
                    data={
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        CONF_RADIUS_KM: radius_km,
                        CONF_HORIZON_MINUTES: horizon_minutes,
                        CONF_ZOOM: zoom,
                    },
                )

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LATITUDE, default=default_latitude): vol.All(
                        vol.Coerce(float), vol.Range(min=-90, max=90)
                    ),
                    vol.Required(CONF_LONGITUDE, default=default_longitude): vol.All(
                        vol.Coerce(float), vol.Range(min=-180, max=180)
                    ),
                    vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): vol.All(
                        vol.Coerce(float), vol.Range(min=MIN_RADIUS_KM, max=MAX_RADIUS_KM)
                    ),
                    vol.Required(
                        CONF_HORIZON_MINUTES, default=DEFAULT_HORIZON_MINUTES
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_HORIZON_MINUTES, max=MAX_HORIZON_MINUTES),
                    ),
                    vol.Required(CONF_ZOOM, default=DEFAULT_ZOOM): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_ZOOM, max=MAX_ZOOM)
                    ),
                }
            ),
        )
