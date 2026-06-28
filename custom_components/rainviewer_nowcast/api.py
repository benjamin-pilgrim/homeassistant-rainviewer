"""Client helpers for the RainViewer API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import RAINVIEWER_API_URL, TILE_SIZE


@dataclass(slots=True, frozen=True)
class RainViewerFrame:
    """A RainViewer radar frame."""

    time: int
    path: str


@dataclass(slots=True, frozen=True)
class RainViewerMap:
    """RainViewer map metadata."""

    generated: int
    host: str
    frames: list[RainViewerFrame]


async def get_weather_maps(session: aiohttp.ClientSession) -> RainViewerMap:
    """Return RainViewer weather-map metadata."""
    response = await session.get(
        RAINVIEWER_API_URL,
        raise_for_status=True,
        timeout=aiohttp.ClientTimeout(total=30),
    )
    data: dict[str, Any] = await response.json()
    frames = [
        RainViewerFrame(time=frame["time"], path=frame["path"])
        for frame in data.get("radar", {}).get("past", [])
        if "time" in frame and "path" in frame
    ]
    return RainViewerMap(
        generated=data["generated"],
        host=data["host"],
        frames=frames,
    )


async def get_radar_tile(
    session: aiohttp.ClientSession,
    host: str,
    frame: RainViewerFrame,
    latitude: float,
    longitude: float,
    zoom: int,
    *,
    smooth: bool = True,
    snow: bool = False,
) -> bytes:
    """Return a coordinate-centered RainViewer radar tile."""
    url = (
        f"{host}{frame.path}/{TILE_SIZE}/{zoom}/"
        f"{latitude:.6f}/{longitude:.6f}/2/{int(smooth)}_{int(snow)}.png"
    )
    response = await session.get(
        url,
        raise_for_status=True,
        timeout=aiohttp.ClientTimeout(total=30),
    )
    return await response.read()


async def get_radar_xyz_tile(
    session: aiohttp.ClientSession,
    host: str,
    frame: RainViewerFrame,
    zoom: int,
    tile_x: int,
    tile_y: int,
    *,
    smooth: bool = True,
    snow: bool = False,
) -> bytes:
    """Return a Web Mercator RainViewer radar tile."""
    url = (
        f"{host}{frame.path}/{TILE_SIZE}/{zoom}/"
        f"{tile_x}/{tile_y}/2/{int(smooth)}_{int(snow)}.png"
    )
    response = await session.get(
        url,
        raise_for_status=True,
        timeout=aiohttp.ClientTimeout(total=30),
    )
    return await response.read()


async def get_osm_tile(
    session: aiohttp.ClientSession,
    zoom: int,
    tile_x: int,
    tile_y: int,
) -> bytes:
    """Return an OpenStreetMap base-map tile."""
    url = f"https://tile.openstreetmap.org/{zoom}/{tile_x}/{tile_y}.png"
    response = await session.get(
        url,
        headers={"User-Agent": "Home Assistant RainViewer Nowcast"},
        raise_for_status=True,
        timeout=aiohttp.ClientTimeout(total=30),
    )
    return await response.read()
