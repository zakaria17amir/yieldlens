from datetime import UTC, datetime, timedelta

from desk.schemas import (
    AprByPeriod,
    Argument,
    Case,
    FixVsFloatStats,
    MarketSnapshot,
    PendlePoint,
    PendleSnapshot,
)
from desk.tools.evidence import allowed_fields, invalid_citations

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _inputs():
    stats = FixVsFloatStats(
        days=1,
        pct_days_float_beat_fixed=100.0,
        current_gap_bps=340,
        breakeven_apr_bps=1500,
        trend_30d="flat",
    )
    gmx = MarketSnapshot(
        market="m",
        current_apr_bps=1840,
        apr_by_period=AprByPeriod.model_validate({"7d": 1840}),
        fetched_at=NOW,
    )
    pendle = PendleSnapshot(
        market="p",
        address="0x" + "11" * 20,
        implied_apy_bps=1500,
        underlying_apy_bps=1800,
        expiry=NOW + timedelta(days=60),
        liquidity_usd=1.0,
        fetched_at=NOW,
        history=[PendlePoint(ts=NOW, implied_apy_bps=1500, underlying_apy_bps=1800)],
    )
    return stats, gmx, pendle


def test_allowed_fields_contains_leaves_not_history():
    allowed = allowed_fields(*_inputs())
    assert {
        "stats.current_gap_bps",
        "stats.trend_30d",
        "gmx.current_apr_bps",
        "gmx.apr_by_period.7d",
        "pendle.implied_apy_bps",
        "pendle.liquidity_usd",
    } <= allowed
    assert not any(f.startswith("pendle.history") for f in allowed)
    assert not any(f.endswith("fetched_at") or f.endswith(".address") for f in allowed)
    assert "stats" not in allowed


def test_invalid_citations_flags_made_up_fields():
    allowed = allowed_fields(*_inputs())
    case = Case(
        position="fixed",
        confidence=0.5,
        arguments=[
            Argument(claim="a", evidence_field="stats.magic"),
            Argument(claim="b", evidence_field="stats.current_gap_bps"),
        ],
    )
    assert invalid_citations(case, allowed) == [0]


def test_allowed_fields_excludes_none_leaves():
    stats, gmx, pendle = _inputs()
    allowed = allowed_fields(stats, gmx, pendle)
    assert "gmx.apr_by_period.7d" in allowed
    assert "gmx.apr_by_period.30d" not in allowed
