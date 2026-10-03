from typing import Any

from desk.schemas import Case, FixVsFloatStats, MarketSnapshot, PendleSnapshot

EXCLUDED_KEYS = {"history", "fetched_at", "address"}


def _leaves(prefix: str, value: Any) -> set[str]:
    if isinstance(value, dict):
        out: set[str] = set()
        for key, child in value.items():
            if key not in EXCLUDED_KEYS:
                out |= _leaves(f"{prefix}.{key}", child)
        return out
    if isinstance(value, list):
        return set()
    return set() if value is None else {prefix}


def allowed_fields(
    stats: FixVsFloatStats, gmx: MarketSnapshot, pendle: PendleSnapshot
) -> set[str]:
    allowed: set[str] = set()
    for name, model in (("stats", stats), ("gmx", gmx), ("pendle", pendle)):
        allowed |= _leaves(name, model.model_dump(by_alias=True))
    return allowed


def invalid_citations(case: Case, allowed: set[str]) -> list[int]:
    return [i for i, arg in enumerate(case.arguments) if arg.evidence_field not in allowed]
