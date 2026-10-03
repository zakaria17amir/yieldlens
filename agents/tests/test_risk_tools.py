from datetime import UTC, datetime, timedelta

from desk.schemas import AprByPeriod, MarketSnapshot, PendleSnapshot, Verdict
from desk.tools.risk import enforce, expiry_blocks_fixed, freshness_errors

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def _gmx(age_h: float = 0, stale: bool = False) -> MarketSnapshot:
    return MarketSnapshot(
        market="m",
        current_apr_bps=1,
        apr_by_period=AprByPeriod(),
        fetched_at=NOW - timedelta(hours=age_h),
        stale=stale,
    )


def _pendle(
    age_h: float = 0, days_to_expiry: float = 60, expired_fallback: bool = False
) -> PendleSnapshot:
    return PendleSnapshot(
        market="p",
        address="0x" + "11" * 20,
        implied_apy_bps=1500,
        underlying_apy_bps=1800,
        expiry=NOW + timedelta(days=days_to_expiry),
        liquidity_usd=1.0,
        fetched_at=NOW - timedelta(hours=age_h),
        expired_fallback=expired_fallback,
        history=[],
    )


def _verdict(bps: int = 7000, vetoed: bool = False) -> Verdict:
    return Verdict(
        target_fixed_bps=bps, vetoed=vetoed, rationale="base", objections=[], needs_rebuttal=False
    )


def test_freshness_ok():
    assert freshness_errors(_gmx(1), _pendle(1), NOW, 12) == []


def test_freshness_flags_old_snapshot():
    errors = freshness_errors(_gmx(0), _pendle(13), NOW, 12)
    assert len(errors) == 1
    assert "pendle" in errors[0]


def test_freshness_flags_stale_flag():
    errors = freshness_errors(_gmx(0, stale=True), _pendle(0), NOW, 12)
    assert len(errors) == 1
    assert "gmx" in errors[0]


def test_expiry_blocks_within_14_days():
    assert expiry_blocks_fixed(_pendle(days_to_expiry=13), NOW, 14) is True
    assert expiry_blocks_fixed(_pendle(days_to_expiry=15), NOW, 14) is False


def test_expiry_blocks_expired_fallback():
    assert expiry_blocks_fixed(_pendle(days_to_expiry=-30, expired_fallback=True), NOW, 14) is True
    assert expiry_blocks_fixed(_pendle(days_to_expiry=90, expired_fallback=True), NOW, 14) is True


def test_enforce_zeroes_fixed_when_expiry_blocked():
    out = enforce(_verdict(7000), [], True)
    assert out.target_fixed_bps == 0
    assert out.vetoed is False
    assert "expiry" in out.rationale


def test_enforce_vetoes_on_stale():
    out = enforce(_verdict(7000), ["pendle data older than 12h"], False)
    assert out.vetoed is True
    assert out.target_fixed_bps == 7000
    assert "older than 12h" in out.rationale


def test_enforce_is_noop_when_clean_and_does_not_mutate():
    original = _verdict(3000)
    out = enforce(original, [], False)
    assert out == original
    enforce(original, ["x"], True)
    assert original.vetoed is False and original.target_fixed_bps == 3000
