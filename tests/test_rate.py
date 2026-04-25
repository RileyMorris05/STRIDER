from strider_landing.rate import RateLimiter


def test_rate_limiter() -> None:
    limiter = RateLimiter(rate_hz=10)

    assert limiter.ready(1.0)
    assert not limiter.ready(1.05)
    assert limiter.ready(1.10)
