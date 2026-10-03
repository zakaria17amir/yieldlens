from datetime import datetime, timedelta

from desk.schemas import MarketSnapshot, PendleSnapshot, Verdict


# Pendle history points are daily, so the newest point is up to a day old on a live market.
HISTORY_GRANULARITY_HOURS = 24


def freshness_errors(
    gmx: MarketSnapshot, pendle: PendleSnapshot, now: datetime, max_age_hours: int
) -> list[str]:
    limit = timedelta(hours=max_age_hours)
    errors = []
    for name, snap in (("gmx", gmx), ("pendle", pendle)):
        if snap.stale or now - snap.fetched_at > limit:
            errors.append(f"{name} data is stale (older than {max_age_hours}h)")
    history_limit = max_age_hours + HISTORY_GRANULARITY_HOURS
    if (
        not pendle.simulated
        and pendle.data_age_hours > history_limit
        and not any(e.startswith("pendle") for e in errors)
    ):
        errors.append(f"pendle history is stale (latest point older than {history_limit}h)")
    return errors


def expiry_blocks_fixed(pendle: PendleSnapshot, now: datetime, min_days: int) -> bool:
    return pendle.expired_fallback or pendle.expiry - now < timedelta(days=min_days)


def enforce(verdict: Verdict, freshness: list[str], expiry_blocked: bool) -> Verdict:
    update: dict = {}
    notes: list[str] = []
    if freshness:
        update["vetoed"] = True
        notes.append("Vetoed by data freshness guard: " + "; ".join(freshness))
    if expiry_blocked:
        update["target_fixed_bps"] = 0
        notes.append("Fixed allocation forced to 0 by expiry guard: Pendle market is expired or expires too soon")
    if notes:
        update["rationale"] = " ".join([verdict.rationale, *notes])
    return verdict.model_copy(update=update)
