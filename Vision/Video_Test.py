#!/usr/bin/env python3
"""Simple USB webcam HTTP streamer that plugs into the driver-station discovery and telemetry flow."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

DISCOVERY_MAGIC = b"F310_DISCOVERY_V1"

# Default configuration allows running the script without additional parameters.
DEFAULT_DEVICE_INDEX = -1
DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 540
DEFAULT_FPS = 24.0
DEFAULT_JPEG_QUALITY = 70
DEFAULT_HTTP_PORT = 8081
DEFAULT_TELEMETRY_PORT = 10000
DEFAULT_DISCOVERY_PORT = 11010
DEFAULT_TELEMETRY_RATE = 2.0
DEFAULT_DRIVER_STATION_IP: Optional[str] = None
DEFAULT_ADVERTISE_HOST: Optional[str] = None
DEFAULT_BIND_HOST: Optional[str] = None
DEFAULT_LOW_LATENCY = True
DEFAULT_DEVICE_SCAN_LIMIT = 8

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - OpenCV is optional but strongly recommended
    cv2 = None  # type: ignore[assignment]


@dataclass
class VideoSettings:
    width: int
    height: int
    fps: float
    quality: int
    device_index: int
    low_latency: bool


class DriverStationTracker:
    def __init__(self, initial: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._addr = initial

    def update(self, ip: str) -> None:
        if not ip:
            return
        with self._lock:
            self._addr = ip

    def current(self) -> Optional[str]:
        with self._lock:
            return self._addr


class VideoCaptureWorker:
    def __init__(self, settings: VideoSettings) -> None:
        if cv2 is None:
            raise SystemExit("OpenCV (cv2) is required to capture video; pip install opencv-python")
        self._settings = settings
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[bytes] = None
        self._actual_fps = 0.0
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="VideoCapture", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def latest_frame(self) -> Optional[bytes]:
        with self._frame_lock:
            return None if self._latest_frame is None else bytes(self._latest_frame)

    def actual_fps(self) -> float:
        with self._frame_lock:
            return self._actual_fps

    @property
    def settings(self) -> VideoSettings:
        return self._settings

    @staticmethod
    def _backend_candidates() -> list[int]:
        assert cv2 is not None
        if sys.platform.startswith("win"):
            return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        return [cv2.CAP_ANY]

    @staticmethod
    def _device_label(index: int, backend: int) -> str:
        backend_name = "default"
        if cv2 is not None:
            if backend == getattr(cv2, "CAP_DSHOW", -9999):
                backend_name = "dshow"
            elif backend == getattr(cv2, "CAP_MSMF", -9999):
                backend_name = "msmf"
            elif backend == getattr(cv2, "CAP_ANY", -9999):
                backend_name = "any"
        return f"index {index} ({backend_name})"

    def _open_capture(self) -> tuple[Optional[object], Optional[str]]:
        assert cv2 is not None

        preferred_indices = [self._settings.device_index] if self._settings.device_index >= 0 else []
        scanned_indices = [idx for idx in range(DEFAULT_DEVICE_SCAN_LIMIT) if idx not in preferred_indices]
        candidates = preferred_indices + scanned_indices

        for index in candidates:
            for backend in self._backend_candidates():
                cap = cv2.VideoCapture(index, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                ok, frame = cap.read()
                if ok and frame is not None:
                    label = self._device_label(index, backend)
                    self._settings.device_index = index
                    return cap, label
                cap.release()
        return None, None

    def _run(self) -> None:
        assert cv2 is not None
        cap, selected_label = self._open_capture()
        if cap is None:
            print(
                f"[camera] Unable to open any camera device. "
                f"Tried preferred index {self._settings.device_index if self._settings.device_index >= 0 else 'auto'} "
                f"and scanned indices 0-{DEFAULT_DEVICE_SCAN_LIMIT - 1}.",
                file=sys.stderr,
            )
            return
        print(f"[camera] Using {selected_label}", file=sys.stderr)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._settings.width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._settings.height))
        if self._settings.fps > 0:
            cap.set(cv2.CAP_PROP_FPS, float(self._settings.fps))
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        encode_quality = int(max(1, min(100, self._settings.quality)))
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), encode_quality]
        interval = 0.0 if self._settings.low_latency else 1.0 / max(self._settings.fps, 0.1)
        last_frame_time = time.monotonic()
        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                now = time.monotonic()
                if ret:
                    ok, buffer = cv2.imencode(".jpg", frame, encode_params)
                    if ok:
                        with self._frame_lock:
                            self._latest_frame = buffer.tobytes()
                            delta = max(1e-6, now - last_frame_time)
                            instant = 1.0 / delta
                            self._actual_fps = instant if self._actual_fps == 0.0 else (0.8 * self._actual_fps + 0.2 * instant)
                        last_frame_time = now
                else:
                    time.sleep(0.05)
                loop_elapsed = time.monotonic() - now
                if interval > 0.0:
                    remaining = interval - loop_elapsed
                    if remaining > 0:
                        self._stop_event.wait(remaining)
                else:
                    self._stop_event.wait(0.001)
        finally:
            cap.release()


class CameraRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in ("/", "/frame"):
            self.send_error(404, "Not Found")
            return
        frame = getattr(self.server, "video_source").latest_frame()  # type: ignore[attr-defined]
        if frame is None:
            self.send_error(503, "Camera frame unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.end_headers()
        self.wfile.write(frame)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


class CameraHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], video_source: VideoCaptureWorker) -> None:
        self.video_source = video_source
        super().__init__(address, CameraRequestHandler)
        self.daemon_threads = True


class DiscoveryResponder:
    def __init__(
        self,
        listen_port: int,
        udp_port: int,
        command_port: int,
        telemetry_port: int,
        tracker: DriverStationTracker,
    ) -> None:
        self._listen_port = listen_port
        self._udp_port = udp_port
        self._command_port = command_port
        self._telemetry_port = telemetry_port
        self._tracker = tracker
        payload = {
            "role": "video_test",
            "udp_port": udp_port,
            "command_port": command_port,
            "telemetry_port": telemetry_port,
        }
        self._reply = json.dumps(payload).encode("utf-8")
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="DiscoveryResponder", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self._listen_port))
            sock.settimeout(0.5)
        except OSError as exc:
            print(f"[discovery] disabled: {exc}", file=sys.stderr)
            return
        with sock:
            while not self._stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(128)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if data.strip() != DISCOVERY_MAGIC:
                    continue
                self._tracker.update(addr[0])
                try:
                    sock.sendto(self._reply, addr)
                except OSError:
                    continue


class TelemetryBroadcaster:
    def __init__(
        self,
        tracker: DriverStationTracker,
        telemetry_port: int,
        payload_factory: Callable[[Optional[str]], Optional[bytes]],
        interval: float,
    ) -> None:
        self._tracker = tracker
        self._telemetry_port = telemetry_port
        self._payload_factory = payload_factory
        self._interval = max(0.2, interval)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="TelemetryBroadcaster", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        with sock:
            while not self._stop_event.is_set():
                target = self._tracker.current()
                payload = self._payload_factory(target)
                if target and payload:
                    try:
                        sock.sendto(payload, (target, self._telemetry_port))
                    except OSError:
                        pass
                self._stop_event.wait(self._interval)


def guess_advertised_host(driver_station_ip: Optional[str], override: Optional[str]) -> Optional[str]:
    if override:
        return override
    if not driver_station_ip:
        return None
    probe: Optional[socket.socket] = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((driver_station_ip, 9))
        host = probe.getsockname()[0]
    except OSError:
        host = None
    finally:
        try:
            if probe is not None:
                probe.close()
        except Exception:
            pass
    return host


def auto_local_ip() -> str:
    probe: Optional[socket.socket] = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        host = probe.getsockname()[0]
    except OSError:
        try:
            host = socket.gethostbyname(socket.gethostname())
        except OSError:
            host = "127.0.0.1"
    finally:
        try:
            if probe is not None:
                probe.close()
        except Exception:
            pass
    return host


class VideoStreamerApp:
    def __init__(self, args: argparse.Namespace) -> None:
        settings = VideoSettings(
            width=args.width,
            height=args.height,
            fps=args.fps,
            quality=args.quality,
            device_index=args.device,
            low_latency=args.low_latency,
        )
        self.args = args
        self.capture = VideoCaptureWorker(settings)
        self.tracker = DriverStationTracker(args.driver_station)
        self.bind_host = self._determine_bind_host(args.bind_host, args.driver_station)
        self.advertise_host = args.advertise_host or self.bind_host
        self.discovery = DiscoveryResponder(
            listen_port=args.discovery_port,
            udp_port=args.udp_port,
            command_port=args.command_port,
            telemetry_port=args.telemetry_port,
            tracker=self.tracker,
        )
        self.http_server = CameraHTTPServer((self.bind_host, args.http_port), self.capture)
        telemetry_interval = 1.0 / max(args.telemetry_rate, 0.1)
        self.telemetry = TelemetryBroadcaster(
            tracker=self.tracker,
            telemetry_port=args.telemetry_port,
            payload_factory=self._build_payload,
            interval=telemetry_interval,
        )
        self._http_thread = threading.Thread(target=self.http_server.serve_forever, name="CameraHTTP", daemon=True)

    def start(self) -> None:
        self.capture.start()
        self._http_thread.start()
        self.discovery.start()
        self.telemetry.start()
        print(
            f"[video] Serving JPEG snapshots on {self.bind_host}:{self.args.http_port}/frame "
            f"(device {self.args.device}, {self.args.width}x{self.args.height}@{self.args.fps}fps, q={self.args.quality})"
        )

    def stop(self) -> None:
        self.telemetry.stop()
        self.discovery.stop()
        self.http_server.shutdown()
        self._http_thread.join(timeout=2.0)
        self.capture.stop()

    def _build_payload(self, driver_station_ip: Optional[str]) -> Optional[bytes]:
        camera_host = self.advertise_host or guess_advertised_host(driver_station_ip, None)
        camera_url = None
        if camera_host:
            camera_url = f"http://{camera_host}:{self.args.http_port}/frame"
        payload = {
            "camera_url": camera_url,
            "video_width": self.capture.settings.width,
            "video_height": self.capture.settings.height,
            "video_quality": self.capture.settings.quality,
            "video_target_fps": self.capture.settings.fps,
            "video_low_latency": self.capture.settings.low_latency,
            "video_actual_fps": round(self.capture.actual_fps(), 2),
        }
        return json.dumps(payload).encode("utf-8")

    @staticmethod
    def _determine_bind_host(bind_override: Optional[str], driver_station_ip: Optional[str]) -> str:
        host = guess_advertised_host(driver_station_ip, bind_override)
        if host:
            return host
        return auto_local_ip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream a USB webcam over HTTP and advertise it to the F310 GUI.")
    parser.add_argument("--device", type=int, default=DEFAULT_DEVICE_INDEX, help="Camera index; use -1 to auto-detect (default: auto-detect)")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help=f"Capture width in pixels (default: {DEFAULT_WIDTH})")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help=f"Capture height in pixels (default: {DEFAULT_HEIGHT})")
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS, help=f"Target capture frame rate (default: {DEFAULT_FPS})")
    parser.add_argument("--quality", type=int, default=DEFAULT_JPEG_QUALITY, help=f"JPEG quality 1-100 (default: {DEFAULT_JPEG_QUALITY})")
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT, help=f"HTTP port for the /frame endpoint (default: {DEFAULT_HTTP_PORT})")
    parser.add_argument("--telemetry-port", type=int, default=DEFAULT_TELEMETRY_PORT, help=f"Driver-station telemetry port (default: {DEFAULT_TELEMETRY_PORT})")
    parser.add_argument("--discovery-port", type=int, default=DEFAULT_DISCOVERY_PORT, help=f"Discovery port shared with f310_comp (default: {DEFAULT_DISCOVERY_PORT})")
    parser.add_argument("--udp-port", type=int, default=0, help="Advertised UDP control port (unused)")
    parser.add_argument("--command-port", type=int, default=0, help="Advertised command console port (unused)")
    parser.add_argument("--telemetry-rate", type=float, default=DEFAULT_TELEMETRY_RATE, help=f"Telemetry updates per second (default: {DEFAULT_TELEMETRY_RATE})")
    parser.add_argument("--driver-station", default=DEFAULT_DRIVER_STATION_IP, help="Driver-station IP override for telemetry (optional)")
    parser.add_argument("--bind-host", default=DEFAULT_BIND_HOST, help="Host/IP to bind HTTP server (default: auto-detect PC IP)")
    parser.add_argument(
        "--low-latency",
        dest="low_latency",
        action="store_true",
        default=DEFAULT_LOW_LATENCY,
        help="Capture continuously without FPS throttling for lowest latency (default: enabled)",
    )
    parser.add_argument(
        "--no-low-latency",
        dest="low_latency",
        action="store_false",
        help="Disable low-latency capture and throttle to the requested FPS",
    )
    parser.add_argument(
        "--advertise-host",
        default=DEFAULT_ADVERTISE_HOST,
        help="Host/IP placed in camera_url; autodetected from driver station connection when omitted",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = VideoStreamerApp(args)
    try:
        app.start()
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[video] stopping...")
    finally:
        app.stop()


if __name__ == "__main__":
    main()
