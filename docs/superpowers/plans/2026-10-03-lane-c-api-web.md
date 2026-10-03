# Lane C — API and Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI service that runs the desk and streams progress, and a one-page React app with Desk, Your Position and Track Record panels.

**Architecture:** The API owns a single `RunManager` (one active run, SSE fan-out, JSON report store) and calls `desk.run.run_desk` through an injectable `Runner` so it is testable without agents. The web app reads contracts from `contracts/deployments/`, talks to the API with `fetch` + `EventSource`, and to the chain with wagmi.

**Tech Stack:** FastAPI, uvicorn, sse-starlette, httpx (tests); React 18, Vite 5, TypeScript, wagmi v2, viem, @rainbow-me/rainbowkit, @tanstack/react-query, vitest.

**Spec:** `docs/superpowers/specs/2026-10-03-yieldlens-agentic-design.md` §6–7. Shared interfaces: `2026-10-03-00-overview.md`.

## Global Constraints

See overview. Additionally: the web app never holds any private key; `VITE_API_URL` and `VITE_WALLETCONNECT_PROJECT_ID` are the only web env vars; API CORS allows `http://localhost:5173` and the deployed web origin from `WEB_ORIGIN` env.

## Review Focus

Overview item 5 pinned in Task C1.

---

## File structure

```
api/
  pyproject.toml
  app/
    __init__.py
    main.py            # create_app(runner) -> FastAPI
    runs.py            # RunManager
    store.py           # ReportStore(runs_dir)
  data/runs/.gitkeep
  tests/test_api.py
web/
  package.json  vite.config.ts  tsconfig.json  index.html  .env.example
  src/
    main.tsx  App.tsx  wagmi.ts
    contracts.ts       # addresses + ABIs from ../contracts/deployments
    api.ts             # fetchLatest, startRun, subscribeRun
    format.ts          # bps/usdg formatting helpers
    components/
      DeskPanel.tsx  CaseCard.tsx  VerdictCard.tsx  RunProgress.tsx
      PositionPanel.tsx  VaultCard.tsx  DelegationCard.tsx  MoveHistory.tsx
      TrackRecordPanel.tsx
    golden_run.json    # copied from agents/evals/golden/example_live_run.json
  src/__tests__/format.test.ts  src/__tests__/api.test.ts
```

---

### Task C1: FastAPI service

**Files:**
- Create: `api/pyproject.toml`, `api/app/{__init__,main,runs,store}.py`, `api/data/runs/.gitkeep`, `.github/workflows/api.yml`
- Test: `api/tests/test_api.py`

**Interfaces:**
- `store.py`: `class ReportStore: __init__(runs_dir: Path); latest() -> dict | None; get(run_id) -> dict | None`. Reads JSON files written by the agents' `save_report` (same `runs_dir`, default `api/data/runs`).
- `runs.py`: `Runner = Callable[[str, Callable[[dict], None]], Awaitable[dict]]` (receives `run_id` and `on_event`, returns the report dict; the default runner calls `desk.run.run_desk(settings, run_id=run_id, on_event=on_event)`). `class RunManager: __init__(runner: Runner); async start() -> str` (raises `RunActive` if a run is in flight; creates `run_id`, launches `asyncio.create_task`); `subscribe(run_id) -> AsyncIterator[dict]` (replays buffered events then live ones; ends after `done`/`error`); `active_run_id -> str | None`.
- `main.py`: `create_app(runner: Runner | None = None, runs_dir: Path | None = None) -> FastAPI`; default runner imports `desk.run.run_desk` lazily (agents package installed as a path dependency `desk @ ../agents`). Endpoints exactly as the overview: `POST /desk/run` → `{"run_id"}` or 409 `{"detail":"run_active"}`; `GET /desk/runs/{run_id}/events` SSE; `GET /desk/latest` (404 if none); `GET /desk/runs/{run_id}` (404); `GET /health`.

- [ ] **Step 1: Write failing tests** with `httpx.AsyncClient(transport=ASGITransport(app))` and a `fake_runner` that emits two events then returns a minimal report dict, plus a `slow_runner` gated on an `asyncio.Event`:
  - `test_health()`.
  - `test_latest_404_when_empty()`.
  - `test_run_then_latest_returns_report()` — start, drain events, `GET /desk/latest` has the `run_id`.
  - `test_events_stream_contains_start_end_done()` — read SSE lines; event names in order `node_start, node_end, done`.
  - `test_second_run_while_active_returns_409()` *(Review Focus 5)* — start `slow_runner`, second `POST` → 409; release event; third `POST` → 200.
  - `test_runner_exception_emits_error_event()`.
- [ ] **Step 2:** `cd api && uv run pytest` → FAIL. **Step 3:** implement. **Step 4:** → PASS.
- [ ] **Step 5:** `api.yml` workflow: `uv sync && uv run pytest` on `api/**` or `agents/**`.
- [ ] **Step 6:** Commit `feat(api): desk run manager with SSE progress`.

---

### Task C2: Scheduler workflow

**Files:**
- Create: `.github/workflows/desk-cron.yml`

- [ ] **Step 1:** Workflow on `schedule: cron "0 */6 * * *"` and `workflow_dispatch`; single step `curl -fsS -X POST "$API_URL/desk/run"` with `API_URL` from repo variables; tolerate 409 (`|| [ $? -eq 22 ]` is not precise — use `curl -s -o /dev/null -w "%{http_code}"` and accept 200 or 409).
- [ ] **Step 2:** Human step: set `API_URL` repo variable once the API is hosted. Commit `chore: scheduled desk runs`.

---

### Task C3: Web scaffold, wallet, contracts, Position panel

**Files:**
- Create: `web/*` scaffold, `web/src/{main,App,wagmi,contracts,format}.ts(x)`, `web/src/components/{PositionPanel,VaultCard,DelegationCard}.tsx`, `.github/workflows/web.yml`
- Test: `web/src/__tests__/format.test.ts`

**Interfaces:**
- `contracts.ts`: `export const deployments = deploymentsJson as Deployments` (import from `../../contracts/deployments/arbitrum-sepolia.json`); `export const abis = { usdg, vault, router, adapter }` from the ABI JSONs; `export const arbitrumSepolia` chain from `viem/chains`.
- `format.ts`: `formatBps(bps: number) -> string` (`1840 → "18.40%"`), `formatUsdg(raw: bigint) -> string` (6 decimals, 2 dp, thousands separators), `splitLabel(fixedBps: number) -> string` (`3000 → "30% fixed / 70% floating"`), `shortAddr(a) -> "0x1234…abcd"`.
- Position panel reads via wagmi `useReadContracts`: USDG balance, both vaults `balanceOf` + `convertToAssets`, `router.policies(user)`, share allowances to router. Writes: `usdg.mint(self, 1000e6)` (testnet faucet button), `approve` + `deposit` per vault, `withdraw` per vault, `moveSelf` (amount + direction), `approve(router, max)` on both vault shares, `setPolicy(enabled, maxMoveBps, cooldown)`.

- [ ] **Step 1:** `npm create vite@latest web -- --template react-ts`; install `wagmi viem @tanstack/react-query @rainbow-me/rainbowkit`; dev `vitest`. Set `resolve.alias` is not needed; Vite can import JSON across the repo root via relative path — enable `server.fs.allow: [".."]`.
- [ ] **Step 2: Write failing tests** `format.test.ts` for the four helpers with the examples above.
- [ ] **Step 3:** `npm test` → FAIL. **Step 4:** implement `format.ts`. **Step 5:** → PASS.
- [ ] **Step 6:** Implement `wagmi.ts` (RainbowKit `getDefaultConfig`, chain Arbitrum Sepolia only), `contracts.ts`, `App.tsx` layout (three stacked panels, header with ConnectButton and a "Sepolia" badge), `PositionPanel` with `VaultCard` ×2 and `DelegationCard`. Use plain CSS modules; no UI kit.
- [ ] **Step 7:** Manual verification with the Lane A deployment (or an Anvil fork): connect, mint, deposit to floating, approve router, enable delegation, `moveSelf` 10 USDG to fixed; balances update. Record a screenshot to `docs/screenshots/position.png`.
- [ ] **Step 8:** `web.yml`: `npm ci && npm test && npm run build`. Commit `feat(web): wallet, vault position and delegation controls`.

---

### Task C4: Desk panel with live progress and golden fallback

**Files:**
- Create: `web/src/api.ts`, `web/src/components/{DeskPanel,CaseCard,VerdictCard,RunProgress}.tsx`, `web/src/golden_run.json`
- Test: `web/src/__tests__/api.test.ts`

**Interfaces:**
- `api.ts`: `fetchLatest(): Promise<DeskReport | null>` (404 → `null`; network error → `throw`), `startRun(): Promise<{run_id: string} | {error: "run_active"}>`, `subscribeRun(runId, onEvent: (e: DeskEvent) => void): () => void` using `EventSource`. `type DeskReport` mirrors the overview JSON; `type DeskEvent = {type: "node_start"|"node_end"|"done"|"error", node?: string, run_id: string}`.
- `DeskPanel`: on mount `fetchLatest()`; if it throws, load `golden_run.json` and show a "Cached run (API offline)" badge. "Convene desk now" → `startRun`; on `run_active` show "A run is already in progress"; subscribe and render `RunProgress` (node list with states idle/running/done); on `done` refetch latest.
- `CaseCard` renders position, confidence bar, arguments with `evidence_field` as a chip; `VerdictCard` renders target split, veto badge, rationale, objections grouped by `to`, and `rebuttal_round`.

- [ ] **Step 1: Write failing tests** `api.test.ts` with a mocked `fetch`: `fetchLatest` returns `null` on 404 and throws on network error; `startRun` maps 409 to `{error:"run_active"}`.
- [ ] **Step 2:** → FAIL. **Step 3:** implement `api.ts`. **Step 4:** → PASS.
- [ ] **Step 5:** Implement components. Copy `agents/evals/golden/example_live_run.json` to `web/src/golden_run.json` (or a hand-written report matching the overview example if B6 is not done yet).
- [ ] **Step 6:** Manual verification against the running API: trigger a run, watch node progress, verdict appears; stop the API, reload, cached badge appears. Screenshots to `docs/screenshots/desk.png`.
- [ ] **Step 7:** Commit `feat(web): desk panel with live agent progress`.

---

### Task C5: Move history and Track Record panel

**Files:**
- Create: `web/src/components/{MoveHistory,TrackRecordPanel}.tsx`
- Modify: `web/src/components/PositionPanel.tsx`

**Interfaces:**
- `MoveHistory`: `viem` `getLogs` for `Moved` filtered by `user == connected`, from `deployments.deployedAtBlock`; rows: time, direction, amount, `byAgent` badge, `reportHash` short with link `#/report/{hash}` that opens the matching run from `GET /desk/latest` or `/desk/runs/{id}` (match on `report_hash`; if not found show the hash only).
- `TrackRecordPanel`: `<iframe>` of the Dune dashboard URL from `VITE_DUNE_EMBED_URL` (hidden if unset) and `<img src="/replay.png">` copied from `agents/replay/results/replay.png` into `web/public/` by Lane D.

- [ ] **Step 1:** Implement both components (no unit tests; verified manually).
- [ ] **Step 2:** Manual verification: after a `moveFor` from Lane B's executor against the Sepolia deployment, the row appears with the agent badge and resolves to the run. Screenshot `docs/screenshots/history.png`.
- [ ] **Step 3:** Commit `feat(web): move history and track record`.
