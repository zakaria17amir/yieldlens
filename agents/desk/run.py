import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler

from desk.config import Settings
from desk.executor import ExecutorProtocol, NoopExecutor
from desk.graph import build_graph
from desk.llm import make_llm
from desk.reporter import new_run_id
from desk.schemas import DeskReport, ExecutionReport, Skip
from desk.tools.gmx import fetch_gm_apr
from desk.tools.pendle import fetch_pendle

NODES = {
    "gmx_scout",
    "pendle_scout",
    "stats",
    "fixed_advocate",
    "float_advocate",
    "risk_officer",
    "prepare_rebuttal",
    "executor",
    "reporter",
}

logger = logging.getLogger("desk")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "run_id": getattr(record, "run_id", None),
                "node": getattr(record, "node", None),
                "msg": record.getMessage(),
            }
        )


def configure_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class GatedExecutor:
    """Skips execution when the new target is within min_change_bps of the previous run's.

    Known limitation: only targets are compared, not users' actual positions, so users who
    drifted or were skipped earlier are not rebalanced until the target moves.
    """

    def __init__(self, inner: ExecutorProtocol, previous_target: int | None, min_change_bps: int):
        self._inner = inner
        self._previous = previous_target
        self._min_change = min_change_bps

    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport:
        if self._previous is not None and abs(target_fixed_bps - self._previous) < self._min_change:
            list_users = getattr(self._inner, "list_delegated_users", None)
            users = list_users() if callable(list_users) else []
            return ExecutionReport(
                moves=[],
                skipped=[Skip(user=u, reason="below_min") for u in users],
                gas_used=0,
            )
        return self._inner.execute(target_fixed_bps, report_hash)


def _previous_target(runs_dir: Path) -> int | None:
    path = runs_dir / "latest.json"
    if not path.exists():
        return None
    try:
        previous = DeskReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("could not parse %s; skipping change gate", path)
        return None
    if previous.verdict is None or previous.verdict.vetoed:
        return None
    return previous.verdict.target_fixed_bps


class _NodeEvents(AsyncCallbackHandler):
    def __init__(self, run_id: str, on_event: Callable[[dict], None] | None):
        self._run_id = run_id
        self._on_event = on_event
        self._active: dict[Any, str] = {}

    def _emit(self, phase: str, node: str | None) -> None:
        if node not in NODES:
            return
        logger.info(phase, extra={"run_id": self._run_id, "node": node})
        if self._on_event:
            self._on_event({"node": node, "phase": phase, "run_id": self._run_id})

    async def on_chain_start(self, serialized, inputs, *, run_id, metadata=None, name=None, **kw: Any):
        if metadata and metadata.get("langgraph_node") == name and name in NODES:
            self._active[run_id] = name
            self._emit("start", name)

    async def on_chain_end(self, outputs, *, run_id, **kw: Any):
        node = self._active.pop(run_id, None)
        if node:
            self._emit("end", node)


async def run_desk(
    settings: Settings,
    *,
    run_id: str | None = None,
    executor: ExecutorProtocol | None = None,
    on_event: Callable[[dict], None] | None = None,
    dry_run: bool = False,
    llm: Any = None,
) -> DeskReport:
    configure_logging()
    now = lambda: datetime.now(UTC)  # noqa: E731
    run_id = run_id or new_run_id(now())
    if executor is None:
        if dry_run:
            executor = NoopExecutor()
        else:
            from desk.executor import Executor

            executor = Executor.from_settings(settings)
    gated = GatedExecutor(executor, _previous_target(Path(settings.runs_dir)), settings.min_change_bps)
    graph = build_graph(
        llm_small=llm or make_llm("small", settings),
        llm_large=llm or make_llm("large", settings),
        fetch_gmx=fetch_gm_apr,
        fetch_pendle=fetch_pendle,
        executor=gated,
        now=now,
        settings=settings,
    )
    state = await graph.ainvoke(
        {"run_id": run_id}, config={"callbacks": [_NodeEvents(run_id, on_event)]}
    )
    return state["report"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="desk.run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--simulate-live-market", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.simulate_live_market:
        settings = settings.model_copy(update={"simulate_live_market": True})
    report = asyncio.run(run_desk(settings, dry_run=args.dry_run))
    verdict = report.verdict
    line = (
        f"target_fixed_bps={verdict.target_fixed_bps} vetoed={verdict.vetoed}"
        if verdict
        else "no verdict"
    )
    print(f"{report.run_id} {line}")


if __name__ == "__main__":
    main()
