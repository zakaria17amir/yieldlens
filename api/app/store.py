import json
import os
import re
from pathlib import Path

RUN_ID = re.compile(r"^[0-9A-Za-z_-]+$")


class ReportStore:
    def __init__(self, runs_dir: Path):
        self._dir = Path(runs_dir)

    def _read(self, path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def latest(self) -> dict | None:
        return self._read(self._dir / "latest.json")

    def get(self, run_id: str) -> dict | None:
        if not RUN_ID.fullmatch(run_id) or run_id == "latest":
            return None
        return self._read(self._dir / f"{run_id}.json")

    def save(self, report: dict) -> None:
        """Persist a report in the agents' layout; no-op if the run was already saved."""
        run_id = report["run_id"]
        if not RUN_ID.fullmatch(run_id):
            raise ValueError(f"unsafe run_id {run_id!r}")
        path = self._dir / f"{run_id}.json"
        if path.exists():
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(report, indent=2, ensure_ascii=False)
        for target in (path, self._dir / "latest.json"):
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(text, encoding="utf-8", newline="\n")
            os.replace(tmp, target)
