"""Constants for the RainViewer Nowcast integration."""

DOMAIN = "rainviewer_nowcast"

ATTRIBUTION = "Radar data from RainViewer"

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_KM = "radius_km"
CONF_HORIZON_MINUTES = "horizon_minutes"
CONF_ZOOM = "zoom"

DEFAULT_RADIUS_KM = 2.0
DEFAULT_HORIZON_MINUTES = 45
DEFAULT_ZOOM = 7

MIN_RADIUS_KM = 0.5
MAX_RADIUS_KM = 20.0
MIN_HORIZON_MINUTES = 10
MAX_HORIZON_MINUTES = 90
MIN_ZOOM = 5
MAX_ZOOM = 7

RAINVIEWER_API_URL = "https://api.rainviewer.com/public/weather-maps.json"
TILE_SIZE = 512
ANALYSIS_SIZE = 128

