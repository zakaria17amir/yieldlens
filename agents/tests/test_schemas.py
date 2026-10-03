from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from desk.schemas import (
    AprByPeriod,
    Argument,
    Case,
    DeskReport,
    ExecutionReport,
    FixVsFloatStats,
    MarketSnapshot,
    Move,
    Objection,
    PendlePoint,
    PendleSnapshot,
    Skip,
    Verdict,
)

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def test_case_requires_at_least_one_argument():
    with pytest.raises(ValidationError):
        Case(position="fixed", confidence=0.5, arguments=[])


def test_verdict_bps_bounds():
    with pytest.raises(ValidationError):
        Verdict(
            target_fixed_bps=10001,
            vetoed=False,
            rationale="x",
            objections=[],
            needs_rebuttal=False,
        )


def test_apr_by_period_alias():
    apr = AprByPeriod.model_validate({"7d": 1840})
    assert apr.seven_d == 1840
    assert apr.one_d is None


def test_desk_report_round_trips_json():
    report = DeskReport(
        run_id="2026-10-03T12-00-00Z-ab12",
        created_at=NOW,
        gmx=MarketSnapshot(
            market="GM: ETH/USD [WETH-USDC]",
            current_apr_bps=1840,
            apr_by_period=AprByPeriod.model_validate(
                {"1d": 1200, "7d": 1840, "30d": 2100, "90d": 1950}
            ),
            fetched_at=NOW,
        ),
        pendle=PendleSnapshot(
            market="PT-GM-ETHUSD",
            address="0x" + "11" * 20,
            implied_apy_bps=1500,
            underlying_apy_bps=1800,
            expiry=NOW,
            liquidity_usd=1234567.0,
            fetched_at=NOW,
            history=[PendlePoint(ts=NOW, implied_apy_bps=1500, underlying_apy_bps=1800)],
        ),
        stats=FixVsFloatStats(
            days=90,
            pct_days_float_beat_fixed=62.2,
            current_gap_bps=340,
            breakeven_apr_bps=1500,
            trend_30d="down",
        ),
        fixed_case=Case(
            position="fixed",
            confidence=0.6,
            arguments=[Argument(claim="c", evidence_field="stats.trend_30d")],
        ),
        float_case=Case(
            position="floating",
            confidence=0.7,
            arguments=[Argument(claim="c", evidence_field="stats.pct_days_float_beat_fixed")],
        ),
        verdict=Verdict(
            target_fixed_bps=3000,
            vetoed=False,
            rationale="r",
            objections=[Objection(to="fixed", argument_idx=0, reason="r")],
            needs_rebuttal=False,
        ),
        rebuttal_round=1,
        report_hash="0x" + "ab" * 32,
        execution=ExecutionReport(
            moves=[
                Move(
                    user="0x" + "22" * 20,
                    from_vault="0x" + "33" * 20,
                    to_vault="0x" + "44" * 20,
                    assets=1_000_000,
                    tx_hash="0x" + "55" * 32,
                )
            ],
            skipped=[Skip(user="0x" + "66" * 20, reason="cooldown")],
            gas_used=0,
        ),
        errors=[],
    )
    restored = DeskReport.model_validate_json(report.model_dump_json(by_alias=True))
    assert restored == report
