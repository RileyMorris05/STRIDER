from inspect import signature

from strider_landing.mavlink import MAV_FRAMES
from pymavlink import mavutil


def test_mavlink2_landing_target_signature_is_available() -> None:
    params = signature(mavutil.mavlink.MAVLink.landing_target_send).parameters

    assert mavutil.mavlink.WIRE_PROTOCOL_VERSION == "2.0"
    assert "position_valid" in params
    assert MAV_FRAMES["MAV_FRAME_BODY_FRD"] == mavutil.mavlink.MAV_FRAME_BODY_FRD
