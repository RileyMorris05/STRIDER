from __future__ import annotations

from dataclasses import dataclass

import cv2
from pupil_apriltags import Detector

from strider_landing.config import AprilTagConfig


@dataclass(frozen=True)
class TagDetection:
    tag_id: int
    center_u: float
    center_v: float
    decision_margin: float


class AprilTagDetector:
    def __init__(self, config: AprilTagConfig) -> None:
        self._config = config
        self._detector = Detector(families=config.family)

    def detect_best(self, frame) -> TagDetection | None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detections = self._detector.detect(gray)

        accepted: list[TagDetection] = []
        for detection in detections:
            if self._config.id is not None and detection.tag_id != self._config.id:
                continue
            if detection.decision_margin < self._config.decision_margin_min:
                continue
            accepted.append(
                TagDetection(
                    tag_id=int(detection.tag_id),
                    center_u=float(detection.center[0]),
                    center_v=float(detection.center[1]),
                    decision_margin=float(detection.decision_margin),
                )
            )

        if not accepted:
            return None
        return max(accepted, key=lambda item: item.decision_margin)
