from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CameraConfig:
    device: int | str
    width: int
    height: int
    fps: int
    fx: float | None = None
    fy: float | None = None
    cx: float | None = None
    cy: float | None = None
    distortion: list[float] | None = None


@dataclass(frozen=True)
class AprilTagConfig:
    family: str
    id: int | None
    size_m: float
    decision_margin_min: float


@dataclass(frozen=True)
class MavlinkConfig:
    device: str
    baud: int
    source_system: int
    source_component: int
    target_num: int
    send_rate_hz: float


@dataclass(frozen=True)
class MountConfig:
    yaw_deg: float
    flip_x: bool
    flip_y: bool


@dataclass(frozen=True)
class LandingTargetConfig:
    frame: str
    position_valid: bool


@dataclass(frozen=True)
class RuntimeConfig:
    log_every_s: float
    lost_target_timeout_s: float


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig
    apriltag: AprilTagConfig
    mavlink: MavlinkConfig
    mount: MountConfig
    landing_target: LandingTargetConfig
    runtime: RuntimeConfig


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid config section: {name}")
    return value


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    camera = _section(raw, "camera")
    apriltag = _section(raw, "apriltag")
    mavlink = _section(raw, "mavlink")
    mount = _section(raw, "mount")
    landing_target = _section(raw, "landing_target")
    runtime = _section(raw, "runtime")

    return AppConfig(
        camera=CameraConfig(**camera),
        apriltag=AprilTagConfig(**apriltag),
        mavlink=MavlinkConfig(**mavlink),
        mount=MountConfig(**mount),
        landing_target=LandingTargetConfig(**landing_target),
        runtime=RuntimeConfig(**runtime),
    )
