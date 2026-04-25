from __future__ import annotations

import cv2

from strider_landing.config import CameraConfig


class OpenCVCamera:
    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._capture: cv2.VideoCapture | None = None

    def __enter__(self) -> "OpenCVCamera":
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def open(self) -> None:
        capture = cv2.VideoCapture(self._config.device)
        if not capture.isOpened():
            raise RuntimeError(f"Could not open camera device {self._config.device!r}")

        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.height)
        capture.set(cv2.CAP_PROP_FPS, self._config.fps)
        self._capture = capture

    def read(self):
        if self._capture is None:
            raise RuntimeError("Camera is not open")
        ok, frame = self._capture.read()
        if not ok:
            raise RuntimeError("Camera frame read failed")
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
