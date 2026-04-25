from math import isclose, pi

from strider_landing.geometry import (
    AngularOffset,
    CameraIntrinsics,
    apply_mount_transform,
    default_intrinsics,
    pixel_to_angles,
)


def test_default_intrinsics_centers_image() -> None:
    intrinsics = default_intrinsics(640, 480)

    assert intrinsics.fx == 640.0
    assert intrinsics.fy == 640.0
    assert intrinsics.cx == 319.5
    assert intrinsics.cy == 239.5


def test_pixel_to_angles_is_zero_at_principal_point() -> None:
    intrinsics = CameraIntrinsics(fx=500.0, fy=500.0, cx=320.0, cy=240.0)

    offset = pixel_to_angles(320.0, 240.0, intrinsics)

    assert offset.x_rad == 0.0
    assert offset.y_rad == 0.0


def test_pixel_to_angles_signs_follow_image_axes() -> None:
    intrinsics = CameraIntrinsics(fx=500.0, fy=500.0, cx=320.0, cy=240.0)

    right_down = pixel_to_angles(420.0, 340.0, intrinsics)
    left_up = pixel_to_angles(220.0, 140.0, intrinsics)

    assert right_down.x_rad > 0
    assert right_down.y_rad > 0
    assert left_up.x_rad < 0
    assert left_up.y_rad < 0


def test_apply_mount_transform_rotates_offsets() -> None:
    offset = AngularOffset(x_rad=1.0, y_rad=0.0)

    rotated = apply_mount_transform(offset, yaw_deg=90.0)

    assert isclose(rotated.x_rad, 0.0, abs_tol=1e-12)
    assert isclose(rotated.y_rad, 1.0, abs_tol=1e-12)


def test_apply_mount_transform_flips_axes() -> None:
    offset = AngularOffset(x_rad=pi / 8, y_rad=-pi / 9)

    flipped = apply_mount_transform(offset, yaw_deg=0.0, flip_x=True, flip_y=True)

    assert flipped.x_rad == -offset.x_rad
    assert flipped.y_rad == -offset.y_rad
