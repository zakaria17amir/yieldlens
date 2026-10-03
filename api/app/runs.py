import asyncio
import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

from app.store import ReportStore

Runner = Callable[[str, Callable[[dict], None]], Awaitable[dict]]

TERMINAL = ("done", "error")
PHASE_EVENTS = {"start": "node_start", "end": "node_end"}

logger = logging.getLogger(__name__)


class RunActive(Exception):
    pass


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ") + "-" + secrets.token_hex(2)


class RunManager:
    def __init__(self, runner: Runner, store: ReportStore | None = None):
        self._runner = runner
        self._store = store
        self._lock = asyncio.Lock()
        self._active: str | None = None
        self._buffers: dict[str, list[dict]] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._tasks: set[asyncio.Task] = set()

    @property
    def active_run_id(self) -> str | None:
        return self._active

    def knows(self, run_id: str) -> bool:
        return run_id in self._buffers

    async def start(self) -> str:
        async with self._lock:
            if self._active is not None:
                raise RunActive()
            run_id = new_run_id()
            self._active = run_id
            self._buffers[run_id] = []
            self._subscribers[run_id] = []
            task = asyncio.create_task(self._run(run_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return run_id

    def _emit(self, run_id: str, name: str, data: dict) -> None:
        event = {"event": name, "data": data}
        self._buffers[run_id].append(event)
        for queue in self._subscribers[run_id]:
            queue.put_nowait(event)

    def _on_runner_event(self, run_id: str, raw: dict) -> None:
        name = PHASE_EVENTS.get(raw.get("phase"))
        if name:
            self._emit(run_id, name, raw)

    async def _run(self, run_id: str) -> None:
        try:
            report = await self._runner(run_id, lambda raw: self._on_runner_event(run_id, raw))
            if self._store is not None and isinstance(report, dict):
                self._store.save(report)
        except Exception as exc:
            logger.exception("desk run %s failed", run_id)
            self._active = None
            self._emit(run_id, "error", {"run_id": run_id, "message": str(exc)})
        else:
            self._active = None
            self._emit(run_id, "done", {"run_id": run_id})

    async def subscribe(self, run_id: str) -> AsyncIterator[dict]:
        if run_id not in self._buffers:
            raise KeyError(run_id)
        queue: asyncio.Queue = asyncio.Queue()
        backlog = list(self._buffers[run_id])
        self._subscribers[run_id].append(queue)
        try:
            for event in backlog:
                yield event
                if event["event"] in TERMINAL:
                    return
            while True:
                event = await queue.get()
                yield event
                if event["event"] in TERMINAL:
                    return
        finally:
            self._subscribers[run_id].remove(queue)
