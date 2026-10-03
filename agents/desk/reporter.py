import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from web3 import Web3

from desk.schemas import DeskReport
from desk.state import DeskState


def canonical_json(report: DeskReport) -> str:
    data = report.model_dump(mode="json", by_alias=True)
    data["execution"] = None
    data["report_hash"] = None
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def report_hash(report: DeskReport) -> str:
    digest = Web3.keccak(text=canonical_json(report)).hex()
    return "0x" + digest.removeprefix("0x")


def build_report(state: DeskState, now: datetime) -> DeskReport:
    report = DeskReport(
        run_id=state["run_id"],
        created_at=now,
        gmx=state.get("gmx"),
        pendle=state.get("pendle"),
        stats=state.get("stats"),
        fixed_case=state.get("fixed_case"),
        float_case=state.get("float_case"),
        verdict=state.get("verdict"),
        rebuttal_round=state.get("rebuttal_round", 0),
        execution=state.get("execution"),
        errors=list(state.get("errors", [])),
    )
    return report.model_copy(update={"report_hash": report_hash(report)})


def new_run_id(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H-%M-%SZ") + "-" + secrets.token_hex(2)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def save_report(report: DeskReport, runs_dir: Path) -> Path:
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    text = report.model_dump_json(by_alias=True, indent=2)
    path = runs_dir / f"{report.run_id}.json"
    _write_atomic(path, text)
    _write_atomic(runs_dir / "latest.json", text)
    return path
