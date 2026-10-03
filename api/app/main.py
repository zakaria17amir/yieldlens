import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict
from sse_starlette.sse import EventSourceResponse

from app.runs import Runner, RunActive, RunManager
from app.store import ReportStore

LOCAL_WEB_ORIGIN = "http://localhost:5173"


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    runs_dir: Path = Path("data/runs")
    web_origin: str | None = None


def default_runner(runs_dir: Path) -> Runner:
    async def runner(run_id, on_event):
        from desk.config import Settings
        from desk.run import run_desk

        settings = Settings().model_copy(update={"runs_dir": str(runs_dir.resolve())})
        report = await run_desk(settings, run_id=run_id, on_event=on_event)
        return report.model_dump(mode="json", by_alias=True)

    return runner


def create_app(runner: Runner | None = None, runs_dir: Path | None = None) -> FastAPI:
    settings = ApiSettings()
    runs_dir = Path(runs_dir) if runs_dir is not None else settings.runs_dir
    store = ReportStore(runs_dir)
    manager = RunManager(runner or default_runner(runs_dir), store)

    app = FastAPI(title="YieldLens desk API")
    origins = [LOCAL_WEB_ORIGIN]
    if settings.web_origin:
        origins.append(settings.web_origin)
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"]
    )

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/desk/run")
    async def start_run():
        try:
            return {"run_id": await manager.start()}
        except RunActive:
            return JSONResponse({"detail": "run_active"}, status_code=409)

    @app.get("/desk/latest")
    async def latest():
        report = store.latest()
        if report is None:
            raise HTTPException(404, "no_reports")
        return report

    @app.get("/desk/runs/{run_id}")
    async def get_run(run_id: str):
        report = store.get(run_id)
        if report is None:
            raise HTTPException(404, "run_not_found")
        return report

    @app.get("/desk/runs/{run_id}/events")
    async def run_events(run_id: str):
        if manager.knows(run_id):
            source = manager.subscribe(run_id)
        elif store.get(run_id) is not None:
            source = _finished(run_id)
        else:
            raise HTTPException(404, "run_not_found")

        async def stream():
            async for event in source:
                yield {"event": event["event"], "data": json.dumps(event["data"])}

        return EventSourceResponse(stream())

    return app


async def _finished(run_id: str):
    yield {"event": "done", "data": {"run_id": run_id}}


app = create_app()
