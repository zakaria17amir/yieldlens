from collections.abc import Awaitable, Callable
from datetime import datetime

from desk.config import Settings
from desk.schemas import MarketSnapshot, PendleSnapshot
from desk.state import DeskState
from desk.tools.http import DataUnavailable


def make_gmx_scout(
    fetch_gmx: Callable[[str, Settings, datetime], Awaitable[MarketSnapshot]],
    settings: Settings,
    now: Callable[[], datetime],
):
    async def gmx_scout(state: DeskState) -> dict:
        try:
            return {"gmx": await fetch_gmx(settings.gmx_market_name, settings, now())}
        except DataUnavailable as exc:
            return {"gmx": None, "errors": [str(exc)]}

    return gmx_scout


def make_pendle_scout(
    fetch_pendle: Callable[[Settings, datetime], Awaitable[PendleSnapshot]],
    settings: Settings,
    now: Callable[[], datetime],
):
    async def pendle_scout(state: DeskState) -> dict:
        try:
            return {"pendle": await fetch_pendle(settings, now())}
        except DataUnavailable as exc:
            return {"pendle": None, "errors": [str(exc)]}

    return pendle_scout
