"""Pendle tool tests.

Fixtures recorded 2026-10-03:
- markets: https://api-v2.pendle.finance/core/v2/markets/all?chainId=42161&limit=100&skip=0 (trimmed to 3 markets)
- history: https://api-v2.pendle.finance/core/v3/42161/markets/0x358925d171380e05b12036a2bf7051704cb85fab/historical-data
  ?time_frame=day&timestamp_start=2025-10-31T00:00:00.000Z&fields=impliedApy,underlyingApy
No unexpired GM market exists on Pendle Arbitrum on that date. The fixture holds two expired GM markets
(gmETH expiry 2026-01-29, GM ARB-USDC expiry 2024-03-28) and one live non-GM market (USDai).
"""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from desk.config import Settings
from desk.tools.http import DataUnavailable
from desk.tools.pendle import discover_gm_market, fetch_pendle
from desk.tools.risk import expiry_blocks_fixed

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
GM_ETH = "0x358925d171380e05b12036a2bf7051704cb85fab"
MARKETS_URL = "https://api-v2.pendle.finance/core/v2/markets/all"
HISTORY_URL = f"https://api-v2.pendle.finance/core/v3/42161/markets/{GM_ETH}/historical-data"


def _markets() -> dict:
    return json.loads((FIXTURES / "pendle_markets_all.json").read_text())


def _history() -> dict:
    return json.loads((FIXTURES / "pendle_history.json").read_text())


def _serve_markets(payload: dict) -> None:
    respx.get(MARKETS_URL).mock(return_value=httpx.Response(200, json=payload))


def _with_live_gm() -> dict:
    payload = _markets()
    live = copy.deepcopy(next(m for m in payload["results"] if m["address"] == GM_ETH))
    live["address"] = "0x" + "ab" * 20
    live["expiry"] = (NOW + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payload["results"].append(live)
    payload["total"] += 1
    return payload


@respx.mock
async def test_discover_prefers_unexpired_gm_market():
    _serve_markets(_with_live_gm())
    market, fallback = await discover_gm_market(Settings(), NOW)
    assert market["address"] == "0x" + "ab" * 20
    assert fallback is False


@respx.mock
async def test_discover_falls_back_to_expired():
    _serve_markets(_markets())
    market, fallback = await discover_gm_market(Settings(), NOW)
    assert market["address"] == GM_ETH
    assert fallback is True


@respx.mock
async def test_discover_honours_configured_address():
    _serve_markets(_with_live_gm())
    settings = Settings(pendle_market_address=GM_ETH.upper().replace("0X", "0x"))
    market, fallback = await discover_gm_market(settings, NOW)
    assert market["address"] == GM_ETH
    assert fallback is True


@respx.mock
async def test_discover_raises_without_gm_market():
    payload = _markets()
    payload["results"] = [m for m in payload["results"] if not m["name"].lower().startswith("gm")]
    _serve_markets(payload)
    with pytest.raises(DataUnavailable):
        await discover_gm_market(Settings(), NOW)


@respx.mock
async def test_fetch_pendle_builds_history():
    _serve_markets(_markets())
    route = respx.get(HISTORY_URL).mock(return_value=httpx.Response(200, json=_history()))
    snap = await fetch_pendle(Settings(), NOW)
    points = _history()["results"]
    assert len(snap.history) == len(points)
    assert snap.implied_apy_bps == round(points[-1]["impliedApy"] * 10_000)
    assert snap.underlying_apy_bps == round(points[-1]["underlyingApy"] * 10_000)
    assert snap.expired_fallback is True
    assert snap.expiry == datetime(2026, 1, 29, tzinfo=UTC)
    assert snap.liquidity_usd == pytest.approx(43413.820237143336)
    assert snap.stale is False
    assert snap.data_age_hours == pytest.approx((NOW - snap.history[-1].ts).total_seconds() / 3600)
    params = route.calls.last.request.url.params
    assert params["time_frame"] == "day"
    assert params["fields"] == "impliedApy,underlyingApy"
    assert params["timestamp_start"] == "2025-10-31T00:00:00.000Z"


@respx.mock
async def test_fetch_pendle_empty_history_raises():
    _serve_markets(_markets())
    respx.get(HISTORY_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    with pytest.raises(DataUnavailable):
        await fetch_pendle(Settings(), NOW)


@pytest.mark.live
async def test_fetch_pendle_live():
    snap = await fetch_pendle(Settings(), datetime.now(UTC))
    assert snap.history


@respx.mock
async def test_simulate_live_market_relabels_expired():
    _serve_markets(_markets())
    respx.get(HISTORY_URL).mock(return_value=httpx.Response(200, json=_history()))
    snap = await fetch_pendle(Settings(simulate_live_market=True), NOW)
    assert snap.simulated is True
    assert snap.expired_fallback is False
    assert snap.expiry == NOW + timedelta(days=90)
    assert expiry_blocks_fixed(snap, NOW, 14) is False
    assert len(snap.history) == len(_history()["results"])


@respx.mock
async def test_simulate_flag_off_keeps_expired_fallback():
    _serve_markets(_markets())
    respx.get(HISTORY_URL).mock(return_value=httpx.Response(200, json=_history()))
    snap = await fetch_pendle(Settings(), NOW)
    assert snap.simulated is False
    assert expiry_blocks_fixed(snap, NOW, 14) is True


@respx.mock
async def test_discover_matches_underlying_symbol():
    payload = _markets()
    payload["results"] = [m for m in payload["results"] if not m["name"].lower().startswith("gm")]
    payload["results"][0]["underlyingAsset"] = {"symbol": "GM-ETH"}
    _serve_markets(payload)
    market, _ = await discover_gm_market(Settings(), NOW)
    assert market["address"] == payload["results"][0]["address"]


@respx.mock
async def test_discover_malformed_record_raises_data_unavailable():
    payload = _markets()
    del payload["results"][0]["expiry"]
    _serve_markets(payload)
    with pytest.raises(DataUnavailable):
        await discover_gm_market(Settings(), NOW)
