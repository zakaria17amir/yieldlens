"""Export desk runs (api/data/runs/*.json) to the CSV uploaded to Dune as `yieldlens_desk_history`.

One row per day: the last run of that day (by created_at).
"""

import argparse
import csv
import json
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent
SKIP = {"latest.json", "latest_executed.json"}
COLUMNS = ["date", "target_fixed_bps", "implied_apy_bps", "underlying_apy_bps", "run_id"]


def rows(runs_dir: Path):
    last_per_day: dict[str, tuple[str, dict]] = {}
    for path in sorted(runs_dir.glob("*.json")):
        if path.name in SKIP:
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        verdict, pendle = run.get("verdict"), run.get("pendle")
        if not verdict or not pendle:
            continue
        day, created = run["created_at"][:10], run["created_at"]
        if day not in last_per_day or created >= last_per_day[day][0]:
            last_per_day[day] = (
                created,
                {
                    "date": day,
                    "target_fixed_bps": verdict["target_fixed_bps"],
                    "implied_apy_bps": pendle["implied_apy_bps"],
                    "underlying_apy_bps": pendle["underlying_apy_bps"],
                    "run_id": run["run_id"],
                },
            )
    for day in sorted(last_per_day):
        yield last_per_day[day][1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=AGENTS.parent / "api" / "data" / "runs")
    parser.add_argument("--out", type=Path, default=AGENTS / "replay" / "results" / "desk_history.csv")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows(args.runs_dir))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
