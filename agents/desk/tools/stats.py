from statistics import fmean

from desk.schemas import FixVsFloatStats, MarketSnapshot, PendleSnapshot

TREND_WINDOW = 7
TREND_LOOKBACK = 30


def fix_vs_float_stats(
    gmx: MarketSnapshot, pendle: PendleSnapshot, trend_threshold_bps: int = 50
) -> FixVsFloatStats:
    history = pendle.history
    days = len(history)
    wins = sum(1 for p in history if p.underlying_apy_bps > p.implied_apy_bps)
    return FixVsFloatStats(
        days=days,
        pct_days_float_beat_fixed=100 * wins / days if days else 0.0,
        current_gap_bps=gmx.current_apr_bps - pendle.implied_apy_bps,
        breakeven_apr_bps=pendle.implied_apy_bps,
        trend_30d=_trend(
            [p.underlying_apy_bps for p in history], trend_threshold_bps
        ),
    )


def _trend(series: list[int], threshold_bps: int):
    if len(series) < TREND_LOOKBACK + TREND_WINDOW:
        return "flat"
    recent = fmean(series[-TREND_WINDOW:])
    end = len(series) - TREND_LOOKBACK
    earlier = fmean(series[end - TREND_WINDOW : end])
    delta = recent - earlier
    if delta > threshold_bps:
        return "up"
    if delta < -threshold_bps:
        return "down"
    return "flat"
