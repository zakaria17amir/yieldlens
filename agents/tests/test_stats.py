from datetime import UTC, datetime, timedelta

from desk.schemas import AprByPeriod, MarketSnapshot, PendlePoint, PendleSnapshot
from desk.tools.stats import fix_vs_float_stats

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _gmx(current_apr_bps: int = 1840) -> MarketSnapshot:
    return MarketSnapshot(
        market="GM: ETH/USD [WETH-USDC]",
        current_apr_bps=current_apr_bps,
        apr_by_period=AprByPeriod.model_validate({"7d": current_apr_bps}),
        fetched_at=NOW,
    )


def _pendle(history: list[tuple[int, int]], implied: int = 1500) -> PendleSnapshot:
    start = NOW - timedelta(days=len(history))
    return PendleSnapshot(
        market="PT-X",
        address="0x" + "11" * 20,
        implied_apy_bps=implied,
        underlying_apy_bps=1800,
        expiry=NOW + timedelta(days=90),
        liquidity_usd=1.0,
        fetched_at=NOW,
        history=[
            PendlePoint(ts=start + timedelta(days=i), implied_apy_bps=i_, underlying_apy_bps=u)
            for i, (i_, u) in enumerate(history)
        ],
    )


def test_pct_days_counts_strict_wins():
    p = _pendle([(1500, 1800), (1500, 1500), (1500, 1400), (1500, 1600)])
    assert fix_vs_float_stats(_gmx(), p).pct_days_float_beat_fixed == 50.0


def test_gap_uses_gmx_current_vs_implied():
    stats = fix_vs_float_stats(_gmx(1840), _pendle([(1500, 1800)], implied=1500))
    assert stats.current_gap_bps == 340
    assert stats.breakeven_apr_bps == 1500


def test_trend_up_down_flat():
    up = [(1500, 1000 + 10 * i) for i in range(40)]
    down = [(1500, 2000 - 10 * i) for i in range(40)]
    flat = [(1500, 1500)] * 40
    assert fix_vs_float_stats(_gmx(), _pendle(up)).trend_30d == "up"
    assert fix_vs_float_stats(_gmx(), _pendle(down)).trend_30d == "down"
    assert fix_vs_float_stats(_gmx(), _pendle(flat)).trend_30d == "flat"


def test_trend_flat_with_too_few_points():
    ramp = [(1500, 1000 + 100 * i) for i in range(36)]
    assert fix_vs_float_stats(_gmx(), _pendle(ramp)).trend_30d == "flat"


def test_empty_history_is_safe():
    stats = fix_vs_float_stats(_gmx(), _pendle([]))
    assert stats.days == 0
    assert stats.pct_days_float_beat_fixed == 0.0
    assert stats.trend_30d == "flat"
