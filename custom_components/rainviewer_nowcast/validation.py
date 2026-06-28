"""Validation capture helpers for RainViewer Nowcast."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .analysis import NowcastResult
from .api import RainViewerFrame
from .const import DOMAIN

_ROW_SCHEMA_VERSION = 1


async def async_capture_validation(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    host: str,
    frames: list[RainViewerFrame],
    analysis_tiles: list[bytes],
    result: NowcastResult,
    latitude: float,
    longitude: float,
    radius_km: float,
    horizon_minutes: int,
    zoom: int,
    save_tiles: bool,
    keep_days: int,
) -> None:
    """Persist one validation row without blocking the event loop."""
    base_path = Path(hass.config.path(DOMAIN, "validation"))
    frame_infos = [{"time": frame.time, "path": frame.path} for frame in frames]
    row = _base_row(
        entry=entry,
        host=host,
        frames=frame_infos,
        result=result,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        horizon_minutes=horizon_minutes,
        zoom=zoom,
        save_tiles=save_tiles,
        keep_days=keep_days,
    )
    await hass.async_add_executor_job(
        _write_capture,
        base_path,
        row,
        frame_infos,
        list(analysis_tiles),
        save_tiles,
        keep_days,
    )


def _base_row(
    *,
    entry: ConfigEntry,
    host: str,
    frames: list[dict[str, Any]],
    result: NowcastResult,
    latitude: float,
    longitude: float,
    radius_km: float,
    horizon_minutes: int,
    zoom: int,
    save_tiles: bool,
    keep_days: int,
) -> dict[str, Any]:
    """Return the serializable validation row before tile paths are attached."""
    motion = asdict(result.motion) if result.motion is not None else None
    return {
        "schema_version": _ROW_SCHEMA_VERSION,
        "captured_at": datetime.now(tz=UTC).isoformat(),
        "entry_id": entry.entry_id,
        "entry_title": entry.title,
        "source": {
            "host": host,
            "frames": frames,
        },
        "config": {
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
            "horizon_minutes": horizon_minutes,
            "zoom": zoom,
        },
        "capture": {
            "save_tiles": save_tiles,
            "keep_days": keep_days,
        },
        "result": {
            "rain_approaching": result.rain_approaching,
            "raining_now": result.raining_now,
            "eta_minutes": result.eta_minutes,
            "clear_eta_minutes": result.clear_eta_minutes,
            "duration_minutes": result.duration_minutes,
            "confidence": result.confidence,
            "now_coverage_percent": result.now_coverage_percent,
            "now_total_pixels": result.now_total_pixels,
            "now_wet_pixels": result.now_wet_pixels,
            "frame_time": (
                result.frame_time.isoformat() if result.frame_time else None
            ),
            "generated_time": (
                result.generated_time.isoformat()
                if result.generated_time
                else None
            ),
            "frame_age_minutes": result.frame_age_minutes,
            "motion": motion,
            "frame_count": result.frame_count,
            "projection_trace": [
                asdict(point) for point in result.projection_trace
            ],
        },
    }


def _write_capture(
    base_path: Path,
    row: dict[str, Any],
    frames: list[dict[str, Any]],
    analysis_tiles: list[bytes],
    save_tiles: bool,
    keep_days: int,
) -> None:
    """Write validation data from a worker thread."""
    frame_time = _row_date(row)
    day = frame_time.isoformat()

    rows_path = base_path / "rows"
    rows_path.mkdir(parents=True, exist_ok=True)

    row["analysis_tiles"] = []
    if save_tiles:
        tile_path = base_path / "tiles" / "analysis" / day
        tile_path.mkdir(parents=True, exist_ok=True)
        for frame, tile in zip(frames, analysis_tiles, strict=False):
            digest = hashlib.sha256(tile).hexdigest()
            filename = f"{frame['time']}_{digest[:16]}.png"
            path = tile_path / filename
            if not path.exists():
                path.write_bytes(tile)
            row["analysis_tiles"].append(
                {
                    "time": frame["time"],
                    "path": frame["path"],
                    "sha256": digest,
                    "file": str(path.relative_to(base_path)),
                }
            )

    line = json.dumps(row, sort_keys=True, separators=(",", ":"))
    with (rows_path / f"{day}.jsonl").open("a", encoding="utf-8") as file:
        file.write(line)
        file.write("\n")

    (base_path / "latest.json").write_text(
        json.dumps(row, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _prune_old_days(base_path, keep_days)


def _row_date(row: dict[str, Any]) -> date:
    """Return the row date from frame time, falling back to capture time."""
    value = row["result"].get("frame_time") or row["captured_at"]
    return datetime.fromisoformat(value).date()


def _prune_old_days(base_path: Path, keep_days: int) -> None:
    """Remove old daily rows and tile directories."""
    cutoff = datetime.now(tz=UTC).date() - timedelta(days=keep_days)

    rows_path = base_path / "rows"
    for path in rows_path.glob("*.jsonl"):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < cutoff:
            path.unlink(missing_ok=True)

    tiles_path = base_path / "tiles" / "analysis"
    if not tiles_path.exists():
        return

    for path in tiles_path.iterdir():
        if not path.is_dir():
            continue
        try:
            day = date.fromisoformat(path.name)
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(path, ignore_errors=True)
