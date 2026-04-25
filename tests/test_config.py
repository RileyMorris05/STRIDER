from strider_landing.config import load_config


def test_load_default_config() -> None:
    config = load_config("config/landing.yaml")

    assert config.apriltag.family == "tag16h5"
    assert config.apriltag.id == 19
    assert config.landing_target.frame == "MAV_FRAME_BODY_FRD"
    assert config.mavlink.send_rate_hz == 20
