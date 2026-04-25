from __future__ import annotations

import argparse
import logging
from time import monotonic

from strider_landing.camera import OpenCVCamera
from strider_landing.config import load_config
from strider_landing.detector import AprilTagDetector
from strider_landing.geometry import (
    CameraIntrinsics,
    apply_mount_transform,
    default_intrinsics,
    pixel_to_angles,
)
from strider_landing.mavlink import LandingTargetSender
from strider_landing.rate import RateLimiter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="STRIDER AprilTag precision landing companion.")
    parser.add_argument("--config", default="config/landing.yaml", help="Path to YAML config.")
    parser.add_argument("--dry-run", action="store_true", help="Print target offsets without MAVLink.")
    parser.add_argument("--camera-device", help="Override camera device from config.")
    parser.add_argument("--mavlink-device", help="Override MAVLink device from config.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser


def _intrinsics(config) -> CameraIntrinsics:
    if None not in (config.fx, config.fy, config.cx, config.cy):
        return CameraIntrinsics(
            fx=float(config.fx),
            fy=float(config.fy),
            cx=float(config.cx),
            cy=float(config.cy),
        )
    logging.warning("Using rough default camera intrinsics. Calibrate before flight.")
    return default_intrinsics(config.width, config.height)


def run() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = load_config(args.config)
    if args.camera_device is not None:
        object.__setattr__(config.camera, "device", args.camera_device)
    if args.mavlink_device is not None:
        object.__setattr__(config.mavlink, "device", args.mavlink_device)

    intrinsics = _intrinsics(config.camera)
    detector = AprilTagDetector(config.apriltag)
    limiter = RateLimiter(config.mavlink.send_rate_hz)
    last_log_s = 0.0
    sent_count = 0
    seen_count = 0

    sender_context = (
        _NullSender()
        if args.dry_run
        else LandingTargetSender(config.mavlink, config.landing_target.frame)
    )

    logging.info("Starting precision landing companion; dry_run=%s", args.dry_run)
    logging.info("Detecting AprilTag family %s", config.apriltag.family)

    with OpenCVCamera(config.camera) as camera, sender_context as sender:
        while True:
            frame = camera.read()
            detection = detector.detect_best(frame)
            now_s = monotonic()

            if detection is None:
                if now_s - last_log_s >= config.runtime.log_every_s:
                    logging.info("No landing tag detected")
                    last_log_s = now_s
                continue

            seen_count += 1
            raw_offset = pixel_to_angles(detection.center_u, detection.center_v, intrinsics)
            offset = apply_mount_transform(
                raw_offset,
                yaw_deg=config.mount.yaw_deg,
                flip_x=config.mount.flip_x,
                flip_y=config.mount.flip_y,
            )

            if limiter.ready(now_s):
                sender.send_angles(offset)
                sent_count += 1

            if now_s - last_log_s >= config.runtime.log_every_s:
                logging.info(
                    "tag=%s margin=%.1f center=(%.1f, %.1f) angles=(%.4f, %.4f) seen=%d sent=%d",
                    detection.tag_id,
                    detection.decision_margin,
                    detection.center_u,
                    detection.center_v,
                    offset.x_rad,
                    offset.y_rad,
                    seen_count,
                    sent_count,
                )
                last_log_s = now_s


class _NullSender:
    def __enter__(self) -> "_NullSender":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def send_angles(self, offset) -> None:
        return None


def main() -> None:
    run()


if __name__ == "__main__":
    main()
