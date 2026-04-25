from __future__ import annotations

import os
from time import time

os.environ.setdefault("MAVLINK20", "1")

from pymavlink import mavutil

from strider_landing.config import MavlinkConfig
from strider_landing.geometry import AngularOffset


MAV_FRAMES = {
    "MAV_FRAME_BODY_FRD": mavutil.mavlink.MAV_FRAME_BODY_FRD,
}


class LandingTargetSender:
    def __init__(self, config: MavlinkConfig, frame_name: str) -> None:
        self._config = config
        self._frame = MAV_FRAMES[frame_name]
        self._connection = None

    def __enter__(self) -> "LandingTargetSender":
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def open(self) -> None:
        self._connection = mavutil.mavlink_connection(
            self._config.device,
            baud=self._config.baud,
            source_system=self._config.source_system,
            source_component=self._config.source_component,
        )
        self._connection.wait_heartbeat(timeout=30)

    def send_angles(self, offset: AngularOffset) -> None:
        if self._connection is None:
            raise RuntimeError("MAVLink connection is not open")

        now_us = int(time() * 1_000_000)
        self._connection.mav.landing_target_send(
            now_us,
            self._config.target_num,
            self._frame,
            offset.x_rad,
            offset.y_rad,
            0.0,
            0.0,
            0.0,
            0.0,
            (0.0, 0.0, 0.0, 0.0),
            0,
            0,
        )

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
