"""Historical replay: desk (band rule or graph) vs always-fixed vs always-floating.

Portfolio model: the floating sleeve accrues the day's underlying APY; the fixed sleeve earns the
implied APY locked when it was added (blended on additions). Decisions use trailing 30-day windows
of the recorded Pendle history and are gated by MIN_CHANGE_BPS.
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from desk.config import Settings  # noqa: E402
from desk.evals_support import load_points, rule_target, snapshots  # noqa: E402
from desk.schemas import PendlePoint  # noqa: E402
from desk.tools.stats import fix_vs_float_stats  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
LOOKBACK = 30
START_VALUE = 100.0


def rule_decision(window: list[PendlePoint]) -> int:
    return rule_target(fix_vs_float_stats(*snapshots(window)).pct_days_float_beat_fixed)


async def graph_decision(window: list[PendlePoint]) -> int:
    from desk.evals_support import run_graph_once
    from desk.llm import make_llm

    gmx, pendle = snapshots(window)
    llm = make_llm("large", Settings())
    report = await run_graph_once(gmx, pendle, window[-1].ts, llm)
    return 0 if report.verdict.vetoed else report.verdict.target_fixed_bps


def simulate(
    points: list[PendlePoint],
    decide,
    *,
    start_split: int = 5000,
    min_change_bps: int = 500,
    cadence_days: int = 1,
) -> list[dict]:
    first = points[0]
    fixed = START_VALUE * start_split / 10_000
    floating = START_VALUE - fixed
    fixed_rate = first.implied_apy_bps
    split = start_split
    always_fixed = START_VALUE
    always_floating = START_VALUE
    rows = []
    for i, point in enumerate(points):
        if i > 0:
            fixed *= 1 + fixed_rate / 10_000 / 365
            floating *= 1 + point.underlying_apy_bps / 10_000 / 365
            always_fixed *= 1 + first.implied_apy_bps / 10_000 / 365
            always_floating *= 1 + point.underlying_apy_bps / 10_000 / 365
        if i + 1 >= LOOKBACK and i % cadence_days == 0:
            target = decide(points[i + 1 - LOOKBACK : i + 1])
            if abs(target - split) > min_change_bps:
                value = fixed + floating
                new_fixed = value * target / 10_000
                added = new_fixed - fixed
                if added > 0:
                    fixed_rate = (fixed * fixed_rate + added * point.implied_apy_bps) / new_fixed
                fixed, floating, split = new_fixed, value - new_fixed, target
        rows.append(
            {
                "date": point.ts.date().isoformat(),
                "split_bps": split,
                "desk_value": round(fixed + floating, 6),
                "always_fixed": round(always_fixed, 6),
                "always_floating": round(always_floating, 6),
            }
        )
    return rows


def write_outputs(rows: list[dict], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path, png_path = out_dir / "replay.csv", out_dir / "replay.png"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "split_bps", "desk_value", "always_fixed", "always_floating"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(8, 4))
    dates = [r["date"] for r in rows]
    for key, label in (("desk_value", "desk"), ("always_fixed", "always fixed"), ("always_floating", "always floating")):
        ax.plot(dates, [r[key] for r in rows], label=label)
    ax.set_ylabel("portfolio value")
    ax.set_title("Historical replay (recorded gmETH Pendle history)")
    ax.set_xticks(dates[:: max(1, len(dates) // 6)])
    ax.tick_params(axis="x", rotation=30)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return csv_path, png_path


def run(*, window: int, cadence_days: int, start_split: int, rule_only: bool, out_dir: Path, min_change_bps: int = 500):
    points = load_points()[-window:]
    if rule_only:
        decide = rule_decision
    else:
        def decide(w):
            return asyncio.run(graph_decision(w))

    rows = simulate(
        points, decide, start_split=start_split, min_change_bps=min_change_bps, cadence_days=cadence_days
    )
    return rows, write_outputs(rows, out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=90)
    parser.add_argument("--cadence", default="1d")
    parser.add_argument("--start-split", type=int, default=5000)
    parser.add_argument("--rule-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)
    settings = Settings(_env_file=None)
    rows, (csv_path, png_path) = run(
        window=args.window,
        cadence_days=int(args.cadence.rstrip("d")),
        start_split=args.start_split,
        rule_only=args.rule_only,
        out_dir=args.out_dir,
        min_change_bps=settings.min_change_bps,
    )
    last = rows[-1]
    print(
        f"{csv_path} {png_path} desk={last['desk_value']} "
        f"fixed={last['always_fixed']} floating={last['always_floating']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
