import asyncio
from collections.abc import Callable
from datetime import datetime

from desk.executor import ExecutorProtocol
from desk.reporter import build_report, report_hash
from desk.schemas import ExecutionReport
from desk.state import DeskState


def make_executor_node(executor: ExecutorProtocol, now: Callable[[], datetime]):
    async def executor_node(state: DeskState) -> dict:
        created_at = now()
        digest = report_hash(build_report({**state, "created_at": created_at}, created_at))
        verdict = state["verdict"]
        if verdict.vetoed:
            execution = ExecutionReport(moves=[], skipped=[], gas_used=0)
        else:
            execution = await asyncio.to_thread(executor.execute, verdict.target_fixed_bps, digest)
        return {"execution": execution, "report_hash": digest, "created_at": created_at}

    return executor_node
