import json
import logging
from datetime import datetime

import pytest

import desk.run as run_module
from desk.config import Settings
from desk.executor import NoopExecutor
from desk.llm import FakeLLM, make_llm
from desk.run import GatedExecutor, JsonFormatter, _previous_target, run_desk
from desk.schemas import ExecutionReport
from tests.test_graph import _case, _gmx, _pendle, _verdict


class _Recorder:
    def __init__(self, users=("0xabc",)):
        self.users = list(users)
        self.calls = []

    def list_delegated_users(self):
        return self.users

    def execute(self, target, digest):
        self.calls.append(target)
        return ExecutionReport(moves=[], skipped=[], gas_used=0)


@pytest.fixture
def patched_fetchers(monkeypatch):
    async def gmx(*_):
        return _gmx()

    async def pendle(*_):
        return _pendle()

    monkeypatch.setattr(run_module, "fetch_gm_apr", gmx)
    monkeypatch.setattr(run_module, "fetch_pendle", pendle)


def test_make_llm_requires_key():
    with pytest.raises(RuntimeError, match="missing API key for provider anthropic"):
        make_llm("small", Settings(anthropic_api_key=None, _env_file=None))
    with pytest.raises(RuntimeError, match="openai"):
        make_llm("large", Settings(llm_provider="openai", openai_api_key=None, _env_file=None))


def test_make_llm_builds_model_with_key():
    llm = make_llm("small", Settings(anthropic_api_key="k", _env_file=None))
    assert llm.model == "claude-3-5-haiku-latest"


def test_gate_skips_small_change():
    inner = _Recorder()
    out = GatedExecutor(inner, 3000, 500).execute(3500, "0x")
    assert inner.calls == []
    assert [(s.user, s.reason) for s in out.skipped] == [("0xabc", "below_min")]


def test_gate_passes_large_change_and_first_run():
    inner = _Recorder()
    GatedExecutor(inner, 3000, 500).execute(3501, "0x")
    GatedExecutor(inner, None, 500).execute(3000, "0x")
    assert inner.calls == [3501, 3000]


def test_gate_with_noop_has_no_skips():
    out = GatedExecutor(NoopExecutor(), 3000, 500).execute(3100, "0x")
    assert out.skipped == []


async def test_dry_run_reports_events_and_writes_no_executed_marker(tmp_path, patched_fetchers):
    settings = Settings(runs_dir=str(tmp_path), _env_file=None)
    events = []
    llm = FakeLLM().queue(_case("fixed"), _case("floating"), _verdict(3000))
    report = await run_desk(settings, run_id="r1", dry_run=True, llm=llm, on_event=events.append)
    assert report.run_id == "r1" and report.verdict.target_fixed_bps == 3000
    assert report.dry_run is True
    assert {"node": "risk_officer", "phase": "start", "run_id": "r1"} in events
    assert {"node": "reporter", "phase": "end", "run_id": "r1"} in events
    assert (tmp_path / "latest.json").exists()
    assert not (tmp_path / "latest_executed.json").exists()
    assert _previous_target(tmp_path) is None


async def _live_run(tmp_path, target, run_id):
    settings = Settings(runs_dir=str(tmp_path), _env_file=None)
    recorder = _Recorder()
    llm = FakeLLM().queue(_case("fixed"), _case("floating"), _verdict(target))
    report = await run_desk(settings, run_id=run_id, executor=recorder, llm=llm)
    return report, recorder


async def test_gate_uses_last_executed_target_and_boundary(tmp_path, patched_fetchers):
    report, recorder = await _live_run(tmp_path, 3000, "e1")
    assert recorder.calls == [3000] and report.dry_run is False
    assert _previous_target(tmp_path) == 3000

    report, recorder = await _live_run(tmp_path, 3500, "e2")
    assert recorder.calls == [] and report.execution.skipped[0].reason == "below_min"
    assert _previous_target(tmp_path) == 3000

    _, recorder = await _live_run(tmp_path, 3501, "e3")
    assert recorder.calls == [3501]
    assert _previous_target(tmp_path) == 3501


async def test_vetoed_run_does_not_update_executed_marker(tmp_path, patched_fetchers):
    await _live_run(tmp_path, 3000, "v1")
    settings = Settings(runs_dir=str(tmp_path), _env_file=None)
    llm = FakeLLM().queue(_case("fixed"), _case("floating"), _verdict(9000, vetoed=True))
    await run_desk(settings, run_id="v2", executor=_Recorder(), llm=llm)
    assert _previous_target(tmp_path) == 3000


def test_previous_target_tolerates_unreadable_marker(tmp_path):
    (tmp_path / "latest_executed.json").mkdir()
    assert _previous_target(tmp_path) is None


def test_json_formatter_includes_exc_info():
    try:
        raise ValueError("kaboom")
    except ValueError:
        import sys

        record = logging.LogRecord("desk", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert "kaboom" in payload["exc_info"]


def test_json_formatter_fields():
    record = logging.LogRecord("desk", logging.INFO, __file__, 1, "hello", None, None)
    record.run_id = "r1"
    record.node = "stats"
    payload = json.loads(JsonFormatter().format(record))
    assert set(payload) == {"ts", "level", "run_id", "node", "msg"}
    assert payload["run_id"] == "r1" and payload["msg"] == "hello"
    datetime.fromisoformat(payload["ts"])
