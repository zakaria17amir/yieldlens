from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from desk.config import Settings
from desk.reporter import build_report, save_report
from desk.state import DeskState


def make_reporter_node(settings: Settings, now: Callable[[], datetime]):
    async def reporter_node(state: DeskState) -> dict:
        report = build_report(state, state.get("created_at") or now())
        save_report(report, Path(settings.runs_dir))
        return {"report": report, "report_hash": report.report_hash}

    return reporter_node
