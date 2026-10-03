import json
import re
from datetime import UTC, datetime
from pathlib import Path

from web3 import Web3

from desk.reporter import build_report, canonical_json, new_run_id, report_hash, save_report
from desk.schemas import (
    AprByPeriod,
    Argument,
    Case,
    DeskReport,
    ExecutionReport,
    FixVsFloatStats,
    MarketSnapshot,
    Move,
    PendlePoint,
    PendleSnapshot,
    Verdict,
)
from desk.state import DeskState

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _state() -> DeskState:
    return DeskState(
        run_id="2026-10-03T12-00-00Z-ab12",
        gmx=MarketSnapshot(
            market="GM: ETH/USD [WETH-USDC]",
            current_apr_bps=1840,
            apr_by_period=AprByPeriod.model_validate({"1d": 1200, "7d": 1840}),
            fetched_at=NOW,
        ),
        pendle=PendleSnapshot(
            market="PT-GM",
            address="0x" + "11" * 20,
            implied_apy_bps=1500,
            underlying_apy_bps=1800,
            expiry=NOW,
            liquidity_usd=1234567.5,
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
            arguments=[Argument(claim="é", evidence_field="stats.trend_30d")],
        ),
        verdict=Verdict(
            target_fixed_bps=3000,
            vetoed=False,
            rationale="r",
            objections=[],
            needs_rebuttal=False,
        ),
        rebuttal_round=1,
        errors=[],
    )


def _execution() -> ExecutionReport:
    return ExecutionReport(
        moves=[
            Move(
                user="0x" + "22" * 20,
                from_vault="0x" + "33" * 20,
                to_vault="0x" + "44" * 20,
                assets=1_000_000,
                tx_hash="0x" + "55" * 32,
            )
        ],
        skipped=[],
        gas_used=21000,
    )


def test_build_report_sets_hash_and_fields():
    report = build_report(_state(), NOW)
    assert report.run_id == "2026-10-03T12-00-00Z-ab12"
    assert report.created_at == NOW
    assert report.report_hash == report_hash(report)
    assert report.float_case is None


def test_hash_ignores_execution_and_hash_fields():
    base = build_report(_state(), NOW)
    with_exec = base.model_copy(update={"execution": _execution(), "report_hash": "0xdead"})
    assert report_hash(base) == report_hash(with_exec)
    assert canonical_json(base) == canonical_json(with_exec)


def test_hash_changes_when_content_changes():
    base = build_report(_state(), NOW)
    other = base.model_copy(update={"rebuttal_round": 0})
    assert report_hash(base) != report_hash(other)


def test_hash_is_deterministic_across_key_order():
    report = build_report(_state(), NOW)
    data = json.loads(report.model_dump_json(by_alias=True))

    def reverse(obj):
        if isinstance(obj, dict):
            return {k: reverse(obj[k]) for k in reversed(list(obj))}
        if isinstance(obj, list):
            return [reverse(x) for x in obj]
        return obj

    shuffled = DeskReport.model_validate_json(json.dumps(reverse(data)))
    assert report_hash(shuffled) == report_hash(report)


def test_canonical_json_format():
    text = canonical_json(build_report(_state(), NOW))
    assert " " not in text.replace("é", "").replace("GM: ETH/USD [WETH-USDC]", "")
    assert "+00:00" not in text
    assert '"created_at":"2026-10-03T12:00:00Z"' in text
    assert '"execution":null' in text and '"report_hash":null' in text
    assert '"7d":1840' in text
    assert "é" in text
    assert '"liquidity_usd":1234567.5' in text


def test_hash_matches_solidity_keccak():
    report = build_report(_state(), NOW)
    expected = "0x" + Web3.keccak(text=canonical_json(report)).hex().removeprefix("0x")
    assert report_hash(report) == expected
    assert re.fullmatch(r"0x[0-9a-f]{64}", expected)


def test_save_writes_run_and_latest(tmp_path: Path):
    runs = tmp_path / "runs"
    first = build_report(_state(), NOW)
    path = save_report(first, runs)
    assert path == runs / f"{first.run_id}.json"
    assert DeskReport.model_validate_json(path.read_text(encoding="utf-8")) == first
    assert (runs / "latest.json").read_text(encoding="utf-8") == path.read_text(encoding="utf-8")

    second = first.model_copy(update={"run_id": "2026-10-03T13-00-00Z-cd34", "execution": _execution()})
    save_report(second, runs)
    assert DeskReport.model_validate_json((runs / "latest.json").read_text(encoding="utf-8")) == second
    assert (runs / f"{first.run_id}.json").exists()


def test_new_run_id_format():
    run_id = new_run_id(NOW)
    assert re.fullmatch(r"2026-10-03T12-00-00Z-[0-9a-f]{4}", run_id)
