import operator
from datetime import datetime
from typing import Annotated, TypedDict

from desk.schemas import (
    Case,
    DeskReport,
    ExecutionReport,
    FixVsFloatStats,
    MarketSnapshot,
    Objection,
    PendleSnapshot,
    Verdict,
)


class DeskState(TypedDict, total=False):
    run_id: str
    gmx: MarketSnapshot | None
    pendle: PendleSnapshot | None
    stats: FixVsFloatStats | None
    market_note: str | None
    fixed_case: Case | None
    float_case: Case | None
    verdict: Verdict | None
    rebuttal_round: int
    objections_for_fixed: list[Objection]
    objections_for_float: list[Objection]
    execution: ExecutionReport | None
    report: DeskReport | None
    report_hash: str | None
    errors: Annotated[list[str], operator.add]
    created_at: datetime
