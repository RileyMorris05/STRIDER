# STRIDER
The coolest robot dog ever

## Landing target notes

- `april16h5-landing-a1.pdf`: AprilTag landing target using the `tag16h5` / April16h5 family. This PDF is already formatted as A1 and the primary landing tag detects as ID `19`.
- `aruco_calibration_board_a4.pdf`: ArUco calibration chessboard using dictionary `ARUCO_MIP_36h12`. Although the PDF page is A4, the physical print was made on A1 paper.
- For planning and camera calibration measurements, treat both printed sheets as A1 physical prints.

## Precision landing companion

This repo now includes the first Raspberry Pi companion app for AprilTag-based ArduPilot precision landing.

Install on the Pi:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Before flight, edit `config/landing.yaml`:

- Set `apriltag.size_m` to the measured outer black square of the printed `tag16h5` landing target.
- Keep `apriltag.id` at `19` for the included landing target unless you intentionally choose a different tag.
- Add calibrated camera intrinsics: `fx`, `fy`, `cx`, and `cy`.
- Confirm `mavlink.device`, usually `/dev/ttyACM0` over USB to the SpeedyBee F405 V4.
- Adjust `mount.yaw_deg`, `flip_x`, and `flip_y` after bench sign tests.

Bench test without MAVLink:

```bash
strider-land --dry-run --config config/landing.yaml
```

Send `LANDING_TARGET` over USB MAVLink:

```bash
strider-land --config config/landing.yaml --mavlink-device /dev/ttyACM0
```

The app currently sends angles-only `LANDING_TARGET` messages using `MAV_FRAME_BODY_FRD`, which is the intended first milestone for ArduPilot precision landing.
