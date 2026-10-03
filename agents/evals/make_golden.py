"""Generate golden eval cases from the recorded 90-day Pendle history.

Band rule (deterministic): pct_days_float_beat_fixed >= 60 -> [0, 3000];
<= 40 -> [7000, 10000]; otherwise [3000, 7000]. Veto cases expect `vetoed`.
"""

import json
from datetime import timedelta
from pathlib import Path

from desk.evals_support import BAND_RULE, band_for
from desk.schemas import AprByPeriod, MarketSnapshot, PendlePoint, PendleSnapshot
from desk.tools.stats import fix_vs_float_stats

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "tests" / "fixtures" / "pendle_history.json"
OUT = Path(__file__).resolve().parent / "golden"
WINDOW = 30
STRIDE = 3
WINDOW_CASES = 20
ADDRESS = "0x358925d171380e05b12036a2bf7051704cb85fab"


def _points() -> list[PendlePoint]:
    from datetime import datetime

    raw = json.loads(HISTORY.read_text(encoding="utf-8"))["results"]
    return [
        PendlePoint(
            ts=datetime.fromisoformat(p["timestamp"]),
            implied_apy_bps=round(p["impliedApy"] * 10_000),
            underlying_apy_bps=round(p["underlyingApy"] * 10_000),
        )
        for p in raw
    ]


def _snapshots(window, now, *, expiry, gmx_age_hours=0, expired_fallback=False):
    last = window[-1]
    gmx = MarketSnapshot(
        market="ETH/USD [ETH-ETH]",
        current_apr_bps=last.underlying_apy_bps,
        apr_by_period=AprByPeriod(
            one_d=last.underlying_apy_bps,
            seven_d=last.underlying_apy_bps,
            thirty_d=last.underlying_apy_bps,
            ninety_d=last.underlying_apy_bps,
        ),
        fetched_at=now - timedelta(hours=gmx_age_hours),
    )
    pendle = PendleSnapshot(
        market="gmETH (WETH-WETH)",
        address=ADDRESS,
        implied_apy_bps=last.implied_apy_bps,
        underlying_apy_bps=last.underlying_apy_bps,
        expiry=expiry,
        liquidity_usd=1_000_000.0,
        fetched_at=now,
        expired_fallback=expired_fallback,
        history=list(window),
    )
    return gmx, pendle


def _case(name, window, now, expected_band, expect_veto, **kw):
    gmx, pendle = _snapshots(window, now, **kw)
    return {
        "name": name,
        "rule": BAND_RULE,
        "now": now.isoformat(),
        "gmx": gmx.model_dump(mode="json", by_alias=True),
        "pendle": pendle.model_dump(mode="json"),
        "expected_band": list(expected_band),
        "expect_veto": expect_veto,
    }


def build_cases() -> list[dict]:
    points = _points()
    cases = []
    for i in range(WINDOW_CASES):
        window = points[i * STRIDE : i * STRIDE + WINDOW]
        now = window[-1].ts
        pct = fix_vs_float_stats(*_snapshots(window, now, expiry=now + timedelta(days=120))).pct_days_float_beat_fixed
        cases.append(
            _case(f"window_{i:02d}", window, now, band_for(pct), False, expiry=now + timedelta(days=120))
        )
    window = points[-WINDOW:]
    now = window[-1].ts
    pct = fix_vs_float_stats(*_snapshots(window, now, expiry=now + timedelta(days=120))).pct_days_float_beat_fixed
    cases.append(
        _case("stale_gmx", window, now, (0, 10_000), True, expiry=now + timedelta(days=120), gmx_age_hours=13)
    )
    cases.append(_case("expiring_market", window, now, (0, 0), False, expiry=now + timedelta(days=7)))
    cases.append(
        _case(
            "expired_fallback",
            window,
            now,
            (0, 0),
            False,
            expiry=now - timedelta(days=60),
            expired_fallback=True,
        )
    )
    return cases


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for case in build_cases():
        (OUT / f"{case['name']}.json").write_text(
            json.dumps(case, indent=1) + "\n", encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
