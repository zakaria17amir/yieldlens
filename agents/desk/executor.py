from typing import Protocol

from desk.schemas import ExecutionReport


class ExecutorProtocol(Protocol):
    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport: ...
