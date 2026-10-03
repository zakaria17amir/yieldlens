"""GMX tool tests.

Fixtures recorded 2026-10-03 from https://arbitrum-api.gmxinfra.io/apy?period={1d,7d,30d,90d}.
The response keys markets by address; names come from https://arbitrum-api.gmxinfra.io/markets.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from desk.config import Settings
from desk.tools.gmx import GMX_MARKETS, fetch_gm_apr
from desk.tools.http import DataUnavailable

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
NAME = "GM: ETH/USD [WETH-USDC]"
PERIODS = ("1d", "7d", "30d", "90d")


def _fixture(period: str) -> dict:
    return json.loads((FIXTURES / f"gmx_apy_{period}.json").read_text())


def _mock_all(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        period = request.url.params["period"]
        return httpx.Response(200, json=_fixture(period))

    respx.get(settings.gmx_apy_url).mock(side_effect=handler)


@respx.mock
async def test_fetch_gm_apr_parses_bps():
    settings = Settings()
    _mock_all(settings)
    snap = await fetch_gm_apr(NAME, settings, NOW)
    address = GMX_MARKETS[NAME]
    expected_7d = round(_fixture("7d")["markets"][address]["apy"] * 10_000)
    assert snap.current_apr_bps == expected_7d
    assert snap.apr_by_period.seven_d == expected_7d
    assert snap.apr_by_period.one_d == round(_fixture("1d")["markets"][address]["apy"] * 10_000)
    assert snap.apr_by_period.ninety_d == round(_fixture("90d")["markets"][address]["apy"] * 10_000)
    assert snap.fetched_at == NOW
    assert snap.stale is False


@respx.mock
async def test_fetch_gm_apr_unknown_market_raises():
    settings = Settings()
    _mock_all(settings)
    with pytest.raises(DataUnavailable):
        await fetch_gm_apr("GM: NOPE/USD", settings, NOW)


@respx.mock
async def test_fetch_gm_apr_address_missing_from_response_raises():
    settings = Settings()
    respx.get(settings.gmx_apy_url).mock(return_value=httpx.Response(200, json={"markets": {}}))
    with pytest.raises(DataUnavailable):
        await fetch_gm_apr(NAME, settings, NOW)


@respx.mock
async def test_fetch_gm_apr_http_error_raises():
    settings = Settings()
    respx.get(settings.gmx_apy_url).mock(return_value=httpx.Response(503))
    with pytest.raises(DataUnavailable):
        await fetch_gm_apr(NAME, settings, NOW)


@pytest.mark.live
async def test_fetch_gm_apr_live():
    snap = await fetch_gm_apr(NAME, Settings(), datetime.now(UTC))
    assert snap.current_apr_bps >= 0
