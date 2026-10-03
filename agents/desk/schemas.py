from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AprByPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    one_d: int | None = Field(default=None, alias="1d")
    seven_d: int | None = Field(default=None, alias="7d")
    thirty_d: int | None = Field(default=None, alias="30d")
    ninety_d: int | None = Field(default=None, alias="90d")


class MarketSnapshot(BaseModel):
    market: str
    current_apr_bps: int
    apr_by_period: AprByPeriod
    fetched_at: datetime
    stale: bool = False


class PendlePoint(BaseModel):
    ts: datetime
    implied_apy_bps: int
    underlying_apy_bps: int


class PendleSnapshot(BaseModel):
    market: str
    address: str
    implied_apy_bps: int
    underlying_apy_bps: int
    expiry: datetime
    liquidity_usd: float
    fetched_at: datetime
    stale: bool = False
    expired_fallback: bool = False
    history: list[PendlePoint]


class FixVsFloatStats(BaseModel):
    days: int
    pct_days_float_beat_fixed: float
    current_gap_bps: int
    breakeven_apr_bps: int
    trend_30d: Literal["up", "down", "flat"]


class Argument(BaseModel):
    claim: str
    evidence_field: str


class Case(BaseModel):
    position: Literal["fixed", "floating"]
    confidence: float = Field(ge=0, le=1)
    arguments: list[Argument] = Field(min_length=1, max_length=5)


class Objection(BaseModel):
    to: Literal["fixed", "floating"]
    argument_idx: int
    reason: str


class Verdict(BaseModel):
    target_fixed_bps: int = Field(ge=0, le=10000)
    vetoed: bool
    rationale: str
    objections: list[Objection]
    needs_rebuttal: bool


class Move(BaseModel):
    user: str
    from_vault: str
    to_vault: str
    assets: int
    tx_hash: str | None = None


class Skip(BaseModel):
    user: str
    reason: Literal[
        "policy_disabled",
        "cooldown",
        "no_balance",
        "no_allowance",
        "below_min",
        "tx_failed",
        "gas_cap",
    ]


class ExecutionReport(BaseModel):
    moves: list[Move]
    skipped: list[Skip]
    gas_used: int


class DeskReport(BaseModel):
    run_id: str
    created_at: datetime
    gmx: MarketSnapshot | None = None
    pendle: PendleSnapshot | None = None
    stats: FixVsFloatStats | None = None
    fixed_case: Case | None = None
    float_case: Case | None = None
    verdict: Verdict | None = None
    rebuttal_round: int = 0
    report_hash: str | None = None
    execution: ExecutionReport | None = None
    errors: list[str] = Field(default_factory=list)


class DeskAborted(Exception):
    pass
