from typing import Protocol

from desk.schemas import ExecutionReport


class ExecutorProtocol(Protocol):
    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport: ...


class NoopExecutor:
    def list_delegated_users(self) -> list[str]:
        return []

    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport:
        return ExecutionReport(moves=[], skipped=[], gas_used=0)
