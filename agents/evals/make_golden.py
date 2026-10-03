"""Generate golden eval cases from the recorded 90-day Pendle history.

Band rule (deterministic): pct_days_float_beat_fixed >= 60 -> [0, 3000];
<= 40 -> [7000, 10000]; otherwise [3000, 7000]. Veto cases expect `vetoed`.

The recorded gmETH history never has floating beating fixed, so the other two bands are covered by
synthetic variants: `float_win_*` shifts the underlying APY up until floating wins on >= 60% of
days, `mid_band_*` has floating win on exactly the first half of the window (pct = 50).
"""

import json
from datetime import timedelta
from pathlib import Path

from desk.evals_support import BAND_RULE, band_for, load_points, snapshots
from desk.schemas import PendlePoint
from desk.tools.stats import fix_vs_float_stats

OUT = Path(__file__).resolve().parent / "golden"
WINDOW = 30
STRIDE = 3
WINDOW_CASES = 20
FLOAT_WIN_STARTS = (0, 18, 36, 54)
MID_BAND_STARTS = (6, 30, 54)
SHIFT_STEP = 100
MIN_SHIFT = 400


def _pct(window: list[PendlePoint], now) -> float:
    gmx, pendle = snapshots(window, now=now)
    return fix_vs_float_stats(gmx, pendle).pct_days_float_beat_fixed


def _shifted(window: list[PendlePoint], shift: int, count: int | None = None) -> list[PendlePoint]:
    count = len(window) if count is None else count
    return [
        p.model_copy(update={"underlying_apy_bps": p.underlying_apy_bps + (shift if i < count else 0)})
        for i, p in enumerate(window)
    ]


def _case(name, window, now, expected_band, expect_veto, **kw):
    gmx, pendle = snapshots(window, now=now, **kw)
    return {
        "name": name,
        "rule": BAND_RULE,
        "now": now.isoformat(),
        "gmx": gmx.model_dump(mode="json", by_alias=True),
        "pendle": pendle.model_dump(mode="json"),
        "expected_band": list(expected_band),
        "expect_veto": expect_veto,
    }


def _float_win_window(window: list[PendlePoint]) -> list[PendlePoint]:
    shift = MIN_SHIFT
    while True:
        candidate = _shifted(window, shift)
        if _pct(candidate, candidate[-1].ts) >= 60:
            return candidate
        shift += SHIFT_STEP


def _mid_band_window(window: list[PendlePoint]) -> list[PendlePoint]:
    half = len(window) // 2
    return [
        p.model_copy(
            update={"underlying_apy_bps": p.implied_apy_bps + (50 if i < half else -50)}
        )
        for i, p in enumerate(window)
    ]


def build_cases() -> list[dict]:
    points = load_points()
    cases = []

    def add(name, window, expected_band=None, **kw):
        now = window[-1].ts
        band = expected_band or band_for(_pct(window, now))
        cases.append(_case(name, window, now, band, False, **kw))

    for i in range(WINDOW_CASES):
        add(f"window_{i:02d}", points[i * STRIDE : i * STRIDE + WINDOW])
    for i, start in enumerate(FLOAT_WIN_STARTS):
        add(f"float_win_{i:02d}", _float_win_window(points[start : start + WINDOW]))
    for i, start in enumerate(MID_BAND_STARTS):
        add(f"mid_band_{i:02d}", _mid_band_window(points[start : start + WINDOW]))

    window = points[-WINDOW:]
    now = window[-1].ts
    cases.append(_case("stale_gmx", window, now, (0, 10_000), True, gmx_age_hours=13))
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
