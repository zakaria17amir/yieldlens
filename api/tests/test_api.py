import asyncio
import json

import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app


async def fake_runner(run_id, on_event):
    on_event({"node": "stats", "phase": "start", "run_id": run_id})
    on_event({"node": "stats", "phase": "end", "run_id": run_id})
    return {"run_id": run_id, "created_at": "2026-10-03T12:00:00Z", "errors": []}


def make_slow_runner(gate: asyncio.Event):
    calls = []

    async def slow_runner(run_id, on_event):
        calls.append(run_id)
        await gate.wait()
        return {"run_id": run_id, "errors": []}

    slow_runner.calls = calls
    return slow_runner


async def failing_runner(run_id, on_event):
    on_event({"node": "stats", "phase": "start", "run_id": run_id})
    raise RuntimeError("boom")


def client_for(app):
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def read_events(client, run_id):
    events = []
    current = None
    async with client.stream("GET", f"/desk/runs/{run_id}/events") as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and current:
                events.append((current, json.loads(line.split(":", 1)[1])))
                if current in ("done", "error"):
                    break
    return events


async def test_health(tmp_path):
    async with client_for(create_app(fake_runner, tmp_path)) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_latest_404_when_empty(tmp_path):
    async with client_for(create_app(fake_runner, tmp_path)) as client:
        assert (await client.get("/desk/latest")).status_code == 404
        assert (await client.get("/desk/runs/nope")).status_code == 404
        assert (await client.get("/desk/runs/..%2Fsecret")).status_code == 404
        assert (await client.get("/desk/runs/nope/events")).status_code == 404


async def test_run_then_latest_returns_report(tmp_path):
    async with client_for(create_app(fake_runner, tmp_path)) as client:
        run_id = (await client.post("/desk/run")).json()["run_id"]
        await read_events(client, run_id)
        latest = await client.get("/desk/latest")
        by_id = await client.get(f"/desk/runs/{run_id}")
    assert latest.status_code == 200 and latest.json()["run_id"] == run_id
    assert by_id.json()["run_id"] == run_id
    assert (tmp_path / f"{run_id}.json").exists()


async def test_events_stream_contains_start_end_done(tmp_path):
    async with client_for(create_app(fake_runner, tmp_path)) as client:
        run_id = (await client.post("/desk/run")).json()["run_id"]
        events = await read_events(client, run_id)
        replay = await read_events(client, run_id)
    assert [name for name, _ in events] == ["node_start", "node_end", "done"]
    assert events[0][1] == {"node": "stats", "phase": "start", "run_id": run_id}
    assert events[-1][1] == {"run_id": run_id}
    assert replay == events


async def test_second_run_while_active_returns_409(tmp_path):
    gate = asyncio.Event()
    runner = make_slow_runner(gate)
    async with client_for(create_app(runner, tmp_path)) as client:
        first = await client.post("/desk/run")
        assert first.status_code == 200
        second = await client.post("/desk/run")
        assert second.status_code == 409
        assert second.json() == {"detail": "run_active"}
        await asyncio.sleep(0.05)
        assert len(runner.calls) == 1
        gate.set()
        await read_events(client, first.json()["run_id"])
        third = await client.post("/desk/run")
        assert third.status_code == 200
        await read_events(client, third.json()["run_id"])


async def test_concurrent_posts_start_exactly_one_run(tmp_path):
    gate = asyncio.Event()
    runner = make_slow_runner(gate)
    async with client_for(create_app(runner, tmp_path)) as client:
        responses = await asyncio.gather(*(client.post("/desk/run") for _ in range(5)))
        codes = sorted(r.status_code for r in responses)
        assert codes == [200, 409, 409, 409, 409]
        await asyncio.sleep(0.05)
        assert len(runner.calls) == 1
        gate.set()
        ok = next(r for r in responses if r.status_code == 200)
        await read_events(client, ok.json()["run_id"])


async def test_runner_exception_emits_error_event(tmp_path):
    async with client_for(create_app(failing_runner, tmp_path)) as client:
        run_id = (await client.post("/desk/run")).json()["run_id"]
        events = await read_events(client, run_id)
        assert [name for name, _ in events] == ["node_start", "error"]
        assert events[-1][1]["run_id"] == run_id and "boom" in events[-1][1]["message"]
        assert (await client.post("/desk/run")).status_code == 200


async def test_cors_allows_local_web_origin(tmp_path):
    async with client_for(create_app(fake_runner, tmp_path)) as client:
        response = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("run_id", ["../x", "a/b", ""])
def test_store_rejects_unsafe_ids(tmp_path, run_id):
    from app.store import ReportStore

    assert ReportStore(tmp_path).get(run_id) is None
