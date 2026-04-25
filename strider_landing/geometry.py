from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, radians, sin


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float


@dataclass(frozen=True)
class AngularOffset:
    x_rad: float
    y_rad: float


def default_intrinsics(width: int, height: int) -> CameraIntrinsics:
    """Return a rough pinhole model for bench testing only."""
    focal_px = max(width, height)
    return CameraIntrinsics(
        fx=float(focal_px),
        fy=float(focal_px),
        cx=(width - 1) / 2.0,
        cy=(height - 1) / 2.0,
    )


def pixel_to_angles(u: float, v: float, intrinsics: CameraIntrinsics) -> AngularOffset:
    """Convert image position to optical angular offsets in radians."""
    x_norm = (u - intrinsics.cx) / intrinsics.fx
    y_norm = (v - intrinsics.cy) / intrinsics.fy
    return AngularOffset(x_rad=atan2(x_norm, 1.0), y_rad=atan2(y_norm, 1.0))


def apply_mount_transform(
    offset: AngularOffset,
    yaw_deg: float,
    flip_x: bool = False,
    flip_y: bool = False,
) -> AngularOffset:
    """Apply simple sign/yaw corrections for the camera mount."""
    x = -offset.x_rad if flip_x else offset.x_rad
    y = -offset.y_rad if flip_y else offset.y_rad

    yaw = radians(yaw_deg)
    rotated_x = (cos(yaw) * x) - (sin(yaw) * y)
    rotated_y = (sin(yaw) * x) + (cos(yaw) * y)
    return AngularOffset(x_rad=rotated_x, y_rad=rotated_y)
