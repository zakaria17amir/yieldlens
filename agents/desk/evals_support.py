"""Shared helpers for golden evals and historical replay (no network, no real LLM)."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from desk.config import Settings
from desk.executor import NoopExecutor
from desk.graph import build_graph
from desk.llm import FakeLLM
from desk.schemas import (
    Argument,
    Case,
    DeskReport,
    MarketSnapshot,
    PendleSnapshot,
    Verdict,
)
from desk.tools.evidence import allowed_fields
from desk.tools.stats import fix_vs_float_stats

BAND_RULE = "pct_days_float_beat_fixed >= 60 -> [0, 3000]; <= 40 -> [7000, 10000]; else [3000, 7000]"


def band_for(pct: float) -> tuple[int, int]:
    if pct >= 60:
        return (0, 3000)
    if pct <= 40:
        return (7000, 10000)
    return (3000, 7000)


def rule_target(pct: float) -> int:
    lo, hi = band_for(pct)
    return (lo + hi) // 2


class RuleLLM:
    """Deterministic stand-in for the LLMs: argues from stats and picks the band midpoint."""

    def __init__(self, gmx: MarketSnapshot, pendle: PendleSnapshot):
        self.stats = fix_vs_float_stats(gmx, pendle)
        self.allowed = allowed_fields(self.stats, gmx, pendle)

    def with_structured_output(self, model: type[BaseModel], **_: Any) -> "_RuleStructured":
        return _RuleStructured(self, model)

    def case(self, position: str) -> Case:
        s = self.stats
        fixed_leaning = rule_target(s.pct_days_float_beat_fixed) >= 5000
        confidence = 0.7 if (position == "fixed") == fixed_leaning else 0.4
        if position == "fixed":
            arguments = [
                Argument(
                    claim=f"Floating out-yielded fixed on only {s.pct_days_float_beat_fixed:.1f}% of days",
                    evidence_field="stats.pct_days_float_beat_fixed",
                ),
                Argument(
                    claim=f"Fixed locks {s.breakeven_apr_bps} bps",
                    evidence_field="stats.breakeven_apr_bps",
                ),
            ]
        else:
            arguments = [
                Argument(
                    claim=f"GMX currently pays {s.current_gap_bps} bps versus the fixed rate",
                    evidence_field="stats.current_gap_bps",
                ),
                Argument(
                    claim=f"Floating yield trend over 30 days is {s.trend_30d}",
                    evidence_field="stats.trend_30d",
                ),
            ]
        assert all(a.evidence_field in self.allowed for a in arguments)
        return Case(position=position, confidence=confidence, arguments=arguments)

    def verdict(self) -> Verdict:
        pct = self.stats.pct_days_float_beat_fixed
        return Verdict(
            target_fixed_bps=rule_target(pct),
            vetoed=False,
            rationale=f"Band rule: floating beat fixed on {pct:.1f}% of days",
            objections=[],
            needs_rebuttal=False,
        )


class _RuleStructured:
    def __init__(self, llm: RuleLLM, model: type[BaseModel]):
        self._llm = llm
        self._model = model

    def _respond(self, messages: Any) -> BaseModel:
        if self._model is Verdict:
            return self._llm.verdict()
        text = "".join(str(getattr(m, "content", m)) for m in messages)
        return self._llm.case("fixed" if "the fixed advocate" in text else "floating")

    def invoke(self, messages: Any, *a: Any, **k: Any) -> BaseModel:
        return self._respond(messages)

    async def ainvoke(self, messages: Any, *a: Any, **k: Any) -> BaseModel:
        return self._respond(messages)


class RecordingLLM:
    """Wraps any LLM and records every structured output, in cache-file format."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.recorded: dict[str, list[dict]] = {}

    def with_structured_output(self, model: type[BaseModel], **kw: Any) -> "_RecordingStructured":
        return _RecordingStructured(self, self.inner.with_structured_output(model, **kw), model)


class _RecordingStructured:
    def __init__(self, owner: RecordingLLM, inner: Any, model: type[BaseModel]):
        self._owner = owner
        self._inner = inner
        self._model = model

    async def ainvoke(self, messages: Any, *a: Any, **k: Any) -> BaseModel:
        result = await self._inner.ainvoke(messages, *a, **k)
        self._owner.recorded.setdefault(self._model.__name__, []).append(result.model_dump(mode="json"))
        return result


def cache_payload(name: str, recorded_with: str, recorded: dict[str, list[dict]]) -> dict:
    return {"recorded_with": recorded_with, "case": name, "responses": recorded}


def fake_llm_from_cache(payload: dict) -> FakeLLM:
    models = {"Case": Case, "Verdict": Verdict}
    llm = FakeLLM()
    for model_name, items in payload["responses"].items():
        for item in items:
            llm.queue(models[model_name].model_validate(item))
    return llm


def load_golden(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "name": raw["name"],
        "now": datetime.fromisoformat(raw["now"]),
        "gmx": MarketSnapshot.model_validate(raw["gmx"]),
        "pendle": PendleSnapshot.model_validate(raw["pendle"]),
        "expected_band": tuple(raw["expected_band"]),
        "expect_veto": raw["expect_veto"],
    }


async def run_graph_once(
    gmx: MarketSnapshot, pendle: PendleSnapshot, now: datetime, llm: Any, name: str = "eval"
) -> DeskReport:
    async def fetch_gmx(*_: Any) -> MarketSnapshot:
        return gmx

    async def fetch_pendle(*_: Any) -> PendleSnapshot:
        return pendle

    with tempfile.TemporaryDirectory() as runs_dir:
        graph = build_graph(
            llm_small=FakeLLM(),
            llm_large=llm,
            fetch_gmx=fetch_gmx,
            fetch_pendle=fetch_pendle,
            executor=NoopExecutor(),
            now=lambda: now,
            settings=Settings(runs_dir=runs_dir, _env_file=None),
        )
        state = await graph.ainvoke({"run_id": name})
    return state["report"]
