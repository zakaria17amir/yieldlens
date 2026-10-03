# YieldLens API

FastAPI service that runs the desk on demand and streams node progress over SSE.

```bash
uv sync
uv pip install -e ../agents   # the desk package; only needed by the default runner
uv run uvicorn app.main:app --port 8000
```

Environment: `RUNS_DIR` (default `data/runs`), `WEB_ORIGIN` (extra CORS origin), plus the agents' own settings (`AGENT_PRIVATE_KEY`, LLM keys, `RPC_URL`).
Tests use a fake runner and do not need the agents package.
