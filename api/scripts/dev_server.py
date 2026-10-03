"""Dev-only API server. `--fake-runner` replays a canned report with simulated node progress.

For demos and manual UI checks without an LLM key. Never used by the default app.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.main import create_app  # noqa: E402

NODES = [
    "gmx_scout",
    "pendle_scout",
    "stats",
    "fixed_advocate",
    "float_advocate",
    "risk_officer",
    "executor",
    "reporter",
]
CANDIDATES = [
    ROOT / "agents" / "evals" / "golden" / "example_live_run.json",
    ROOT / "web" / "src" / "golden_run.json",
]


def canned_report() -> dict:
    path = next(p for p in CANDIDATES if p.exists())
    return json.loads(path.read_text(encoding="utf-8"))


def make_fake_runner(delay: float):
    async def runner(run_id, on_event):
        for node in NODES:
            on_event({"node": node, "phase": "start", "run_id": run_id})
            await asyncio.sleep(delay)
            on_event({"node": node, "phase": "end", "run_id": run_id})
        report = canned_report()
        report["run_id"] = run_id
        report["created_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return report

    return runner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake-runner", action="store_true", required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--delay", type=float, default=0.6)
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "api" / "data" / "runs")
    args = parser.parse_args()
    app = create_app(make_fake_runner(args.delay), args.runs_dir)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
