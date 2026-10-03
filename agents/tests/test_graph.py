from datetime import UTC, datetime, timedelta

import pytest

from desk.config import Settings
from desk.graph import build_graph
from desk.llm import FakeLLM
from desk.schemas import (
    AprByPeriod,
    Argument,
    Case,
    DeskAborted,
    ExecutionReport,
    MarketSnapshot,
    Objection,
    PendlePoint,
    PendleSnapshot,
    Verdict,
)
from desk.tools.http import DataUnavailable

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


class FakeExecutor:
    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport:
        self.calls.append((target_fixed_bps, report_hash))
        return ExecutionReport(moves=[], skipped=[], gas_used=0)


def _gmx(*_args) -> MarketSnapshot:
    return MarketSnapshot(
        market="ETH/USD [ETH-ETH]",
        current_apr_bps=1840,
        apr_by_period=AprByPeriod.model_validate({"7d": 1840}),
        fetched_at=NOW,
    )


def _pendle(expired_fallback: bool = False) -> PendleSnapshot:
    return PendleSnapshot(
        market="PT",
        address="0x" + "11" * 20,
        implied_apy_bps=1500,
        underlying_apy_bps=1800,
        expiry=NOW + (timedelta(days=-5) if expired_fallback else timedelta(days=90)),
        liquidity_usd=1e6,
        fetched_at=NOW,
        expired_fallback=expired_fallback,
        history=[
            PendlePoint(ts=NOW - timedelta(days=i), implied_apy_bps=1500, underlying_apy_bps=1500 + 5 * i)
            for i in range(60)
        ],
    )


def _case(position: str, field: str = "stats.current_gap_bps") -> Case:
    return Case(position=position, confidence=0.6, arguments=[Argument(claim="c", evidence_field=field)])


def _verdict(bps: int = 3000, *, rebuttal: bool = False, vetoed: bool = False) -> Verdict:
    objections = [Objection(to="fixed", argument_idx=0, reason="weak-fixed-evidence")] if rebuttal else []
    return Verdict(
        target_fixed_bps=bps,
        vetoed=vetoed,
        rationale="r",
        objections=objections,
        needs_rebuttal=rebuttal,
    )


def _run(tmp_path, llm, *, executor=None, fetch_pendle=None):
    executor = executor or FakeExecutor()

    async def default_gmx(*_):
        return _gmx()

    async def default_pendle(*_):
        return _pendle()

    graph = build_graph(
        llm_small=FakeLLM(),
        llm_large=llm,
        fetch_gmx=default_gmx,
        fetch_pendle=fetch_pendle or default_pendle,
        executor=executor,
        now=lambda: NOW,
        settings=Settings(runs_dir=str(tmp_path)),
    )
    return graph, executor


def _calls(llm: FakeLLM, model) -> int:
    return sum(1 for m, _ in llm.calls if m is model)


async def test_happy_path_no_rebuttal(tmp_path):
    llm = FakeLLM().queue(_case("fixed"), _case("floating"), _verdict(3000))
    graph, executor = _run(tmp_path, llm)
    state = await graph.ainvoke({"run_id": "run-1"})
    report = state["report"]
    assert report.verdict.target_fixed_bps == 3000
    assert report.rebuttal_round == 0
    assert len(executor.calls) == 1
    target, digest = executor.calls[0]
    assert target == 3000 and len(digest) == 66
    assert report.report_hash == digest
    assert (tmp_path / "run-1.json").exists() and (tmp_path / "latest.json").exists()


async def test_rebuttal_round_runs_advocates_twice(tmp_path):
    llm = FakeLLM().queue(
        _case("fixed"),
        _case("floating"),
        _case("fixed"),
        _case("floating"),
        _verdict(3000, rebuttal=True),
        _verdict(5000),
    )
    graph, executor = _run(tmp_path, llm)
    state = await graph.ainvoke({"run_id": "run-2"})
    assert _calls(llm, Case) == 4
    assert _calls(llm, Verdict) == 2
    assert state["report"].rebuttal_round == 1
    assert state["report"].verdict.target_fixed_bps == 5000
    assert executor.calls[0][0] == 5000
    fixed_second = [m for model, m in llm.calls if model is Case and "weak-fixed-evidence" in str(m)]
    assert len(fixed_second) == 1


async def test_forced_decision_after_one_rebuttal(tmp_path):
    llm = FakeLLM().queue(
        _case("fixed"),
        _case("floating"),
        _case("fixed"),
        _case("floating"),
        _verdict(3000, rebuttal=True),
        _verdict(4000, rebuttal=True),
    )
    graph, executor = _run(tmp_path, llm)
    state = await graph.ainvoke({"run_id": "run-3"})
    assert _calls(llm, Case) == 4
    assert _calls(llm, Verdict) == 2
    assert executor.calls[0][0] == 4000
    assert state["report"].rebuttal_round == 1


async def test_invalid_citation_retries_then_aborts(tmp_path):
    llm = FakeLLM().queue(
        _case("fixed", "stats.magic"), _case("fixed", "stats.magic"), _case("floating")
    )
    graph, executor = _run(tmp_path, llm)
    with pytest.raises(DeskAborted):
        await graph.ainvoke({"run_id": "run-4"})
    assert executor.calls == []
    assert _calls(llm, Verdict) == 0


async def test_invalid_citation_retry_can_recover(tmp_path):
    llm = FakeLLM().queue(
        _case("fixed", "stats.magic"), _case("fixed"), _case("floating"), _verdict(3000)
    )
    graph, executor = _run(tmp_path, llm)
    await graph.ainvoke({"run_id": "run-4b"})
    assert len(executor.calls) == 1


async def test_missing_data_vetoes_without_llm(tmp_path):
    async def failing_pendle(*_):
        raise DataUnavailable("pendle-gm")

    llm = FakeLLM()
    graph, executor = _run(tmp_path, llm, fetch_pendle=failing_pendle)
    state = await graph.ainvoke({"run_id": "run-5"})
    report = state["report"]
    assert llm.calls == []
    assert executor.calls == []
    assert report.verdict.vetoed is True
    assert report.errors == ["pendle-gm", "missing_data"]


async def test_vetoed_verdict_skips_execution(tmp_path):
    llm = FakeLLM().queue(_case("fixed"), _case("floating"), _verdict(3000, vetoed=True))
    graph, executor = _run(tmp_path, llm)
    state = await graph.ainvoke({"run_id": "run-6"})
    assert executor.calls == []
    assert state["report"].execution.moves == []
    assert state["report"].verdict.vetoed is True


async def test_expired_market_forces_zero_fixed(tmp_path):
    async def expired_pendle(*_):
        return _pendle(expired_fallback=True)

    llm = FakeLLM().queue(_case("fixed"), _case("floating"), _verdict(7000))
    graph, executor = _run(tmp_path, llm, fetch_pendle=expired_pendle)
    state = await graph.ainvoke({"run_id": "run-7"})
    assert state["report"].verdict.target_fixed_bps == 0
    assert executor.calls[0][0] == 0


class _RaisingLLM(FakeLLM):
    """First Case call raises a parse error, then falls back to the queue."""

    def __init__(self, error: Exception):
        super().__init__()
        self.error = error
        self.raised = False

    def with_structured_output(self, model, **kw):
        inner = super().with_structured_output(model, **kw)
        outer = self

        class Wrapper:
            async def ainvoke(self, messages, *a, **k):
                if model is Case and "fixed advocate" in str(messages[0].content) and not outer.raised:
                    outer.raised = True
                    raise outer.error
                return await inner.ainvoke(messages)

        return Wrapper()


async def test_parse_error_counts_as_retry_then_recovers(tmp_path):
    from langchain_core.exceptions import OutputParserException

    llm = _RaisingLLM(OutputParserException("bad json"))
    llm.queue(_case("fixed"), _case("floating"), _verdict(3000))
    graph, executor = _run(tmp_path, llm)
    await graph.ainvoke({"run_id": "run-8"})
    assert len(executor.calls) == 1


async def test_out_of_range_objections_are_dropped(tmp_path):
    verdict = Verdict(
        target_fixed_bps=3000,
        vetoed=False,
        rationale="r",
        objections=[
            Objection(to="fixed", argument_idx=0, reason="ok"),
            Objection(to="fixed", argument_idx=5, reason="out of range"),
            Objection(to="floating", argument_idx=-1, reason="negative"),
        ],
        needs_rebuttal=False,
    )
    llm = FakeLLM().queue(_case("fixed"), _case("floating"), verdict)
    graph, _ = _run(tmp_path, llm)
    state = await graph.ainvoke({"run_id": "run-9"})
    assert [o.reason for o in state["report"].verdict.objections] == ["ok"]
