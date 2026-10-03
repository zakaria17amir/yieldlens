import asyncio
from datetime import datetime, timedelta

import httpx

from desk.config import Settings
from desk.schemas import AprByPeriod, MarketSnapshot
from desk.tools.http import DataUnavailable, get_json

PERIODS = ("1d", "7d", "30d", "90d")

# The /apy endpoint keys markets by address only; names come from /markets.
GMX_MARKETS = {
    "GM: ETH/USD [WETH-USDC]": "0x70d95587d40A2caf56bd97485aB3Eec10Bee6336",
}


async def fetch_gm_apr(market_name: str, settings: Settings, now: datetime) -> MarketSnapshot:
    address = GMX_MARKETS.get(market_name)
    if address is None:
        raise DataUnavailable(market_name)
    try:
        payloads = await asyncio.gather(
            *(get_json(settings.gmx_apy_url, params={"period": p}) for p in PERIODS)
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise DataUnavailable(market_name) from exc

    bps: dict[str, int] = {}
    for period, payload in zip(PERIODS, payloads, strict=True):
        try:
            bps[period] = round(payload["markets"][address]["apy"] * 10_000)
        except (KeyError, TypeError) as exc:
            raise DataUnavailable(market_name) from exc

    fetched_at = now
    return MarketSnapshot(
        market=market_name,
        current_apr_bps=bps["7d"],
        apr_by_period=AprByPeriod(
            one_d=bps["1d"], seven_d=bps["7d"], thirty_d=bps["30d"], ninety_d=bps["90d"]
        ),
        fetched_at=fetched_at,
        stale=(now - fetched_at) > timedelta(hours=settings.max_age_hours),
    )
