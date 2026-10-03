from datetime import UTC, datetime, timedelta

import httpx

from desk.config import Settings
from desk.schemas import PendlePoint, PendleSnapshot
from desk.tools.http import DataUnavailable, get_json

PAGE_SIZE = 100


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


async def _all_markets(settings: Settings) -> list[dict]:
    markets: list[dict] = []
    skip = 0
    while True:
        page = await get_json(
            f"{settings.pendle_api_url}/v2/markets/all",
            params={"chainId": settings.pendle_chain_id, "limit": PAGE_SIZE, "skip": skip},
        )
        results = page["results"]
        markets.extend(results)
        skip += len(results)
        if not results or skip >= page.get("total", skip):
            return markets


async def discover_gm_market(settings: Settings, now: datetime) -> tuple[dict, bool]:
    try:
        markets = await _all_markets(settings)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise DataUnavailable("pendle-gm") from exc
    try:
        return _select(markets, settings, now)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DataUnavailable("pendle-gm") from exc


def _is_gm(market: dict) -> bool:
    underlying = market.get("underlyingAsset")
    symbol = underlying.get("symbol", "") if isinstance(underlying, dict) else ""
    return market["name"].lower().startswith("gm") or symbol.lower().startswith("gm")


def _select(markets: list[dict], settings: Settings, now: datetime) -> tuple[dict, bool]:
    markets = [m for m in markets if m.get("chainId") == settings.pendle_chain_id]

    if settings.pendle_market_address:
        wanted = settings.pendle_market_address.lower()
        for market in markets:
            if market["address"].lower() == wanted:
                return market, _parse_ts(market["expiry"]) <= now
        raise DataUnavailable("pendle-gm")

    gm = [m for m in markets if _is_gm(m)]
    live = [m for m in gm if _parse_ts(m["expiry"]) > now]
    if live:
        return max(live, key=lambda m: _parse_ts(m["expiry"])), False
    if gm:
        return max(gm, key=lambda m: _parse_ts(m["expiry"])), True
    raise DataUnavailable("pendle-gm")


async def fetch_pendle(settings: Settings, now: datetime) -> PendleSnapshot:
    market, expired_fallback = await discover_gm_market(settings, now)
    expiry = _parse_ts(market["expiry"])
    window_end = min(now, expiry)
    start = window_end - timedelta(days=settings.history_days)
    try:
        payload = await get_json(
            f"{settings.pendle_api_url}/v3/{settings.pendle_chain_id}/markets/{market['address']}/historical-data",
            params={
                "time_frame": "day",
                "timestamp_start": _iso_z(start),
                "fields": "impliedApy,underlyingApy",
            },
        )
        history = [
            PendlePoint(
                ts=_parse_ts(p["timestamp"]),
                implied_apy_bps=round(p["impliedApy"] * 10_000),
                underlying_apy_bps=round(p["underlyingApy"] * 10_000),
            )
            for p in payload["results"]
            if p.get("impliedApy") is not None and p.get("underlyingApy") is not None
        ]
        liquidity_usd = float(market["details"]["liquidity"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise DataUnavailable("pendle-history") from exc
    if not history:
        raise DataUnavailable("pendle-history")

    simulated = settings.simulate_live_market and expired_fallback
    if simulated:
        expired_fallback = False
        expiry = now + timedelta(days=90)

    fetched_at = now
    return PendleSnapshot(
        market=market["name"],
        address=market["address"],
        implied_apy_bps=history[-1].implied_apy_bps,
        underlying_apy_bps=history[-1].underlying_apy_bps,
        expiry=expiry,
        liquidity_usd=liquidity_usd,
        fetched_at=fetched_at,
        stale=(now - fetched_at) > timedelta(hours=settings.max_age_hours),
        expired_fallback=expired_fallback,
        simulated=simulated,
        history=history,
    )
