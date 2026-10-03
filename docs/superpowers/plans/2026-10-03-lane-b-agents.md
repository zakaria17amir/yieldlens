# Lane B — Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A LangGraph "desk" that pulls GMX and Pendle data, has two advocates argue, lets a Risk Officer decide, executes per-user moves through `AgentRouter`, and writes a hashed `DeskReport`; plus evals and replay.

**Architecture:** Typed Pydantic state; deterministic tools for all numbers; LLM nodes only produce `Case` and `Verdict` objects through structured output; code-level validators enforce evidence citations, staleness and expiry; a pure-code `Executor` plans and sends `moveFor` calls.

**Tech Stack:** Python 3.12, `uv`, LangGraph, langchain-core, langchain-anthropic, langchain-openai, Pydantic v2, web3.py 7, httpx, respx, pytest, pytest-asyncio, matplotlib (replay only).

**Spec:** `docs/superpowers/specs/2026-10-03-yieldlens-agentic-design.md` §5. Shared interfaces: `2026-10-03-00-overview.md`.

## Global Constraints

See overview. Additionally: every LLM node uses `llm.with_structured_output(Model)`; a parse/validation failure retries once then raises `DeskAborted`; no LLM node may compute a number that is not already present in state; all HTTP calls go through `desk/tools/http.py:get_json(url, params)` so tests can mock with `respx`.

## Review Focus

Overview items 1, 2 pinned in B8; item 4 pinned in B4.

## Task order

B1 → B2 → B3 → B4 → B7 (reporter; the graph's executor node needs `report_hash`) → B5 → B6 → B8 → B9. B2–B4 and B7 are independent of each other and may run in parallel after B1.

---

## File structure

```
agents/
  pyproject.toml
  desk/
    __init__.py
    config.py            # Settings (pydantic-settings) with the defaults from the overview
    schemas.py           # all Pydantic models + DeskState
    state.py             # DeskState TypedDict
    llm.py               # make_llm(tier) -> BaseChatModel ; FakeLLM for tests
    graph.py             # build_graph(...)
    run.py               # run_desk(settings) entrypoint + CLI
    nodes/
      scouts.py          # gmx_scout, pendle_scout
      stats.py           # stats node (wraps tools.stats)
      advocates.py       # fixed_advocate, float_advocate
      risk.py            # risk_officer
      executor.py        # executor node (wraps desk.executor.Executor)
      reporter.py
    tools/
      http.py
      gmx.py
      pendle.py
      stats.py
      risk.py
      evidence.py
    executor.py          # Executor class, plan_move
    reporter.py          # build_report, report_hash, save_report
    prompts/
      advocate.md, risk_officer.md, scout.md, reporter.md
  evals/
    golden/*.json
    run_evals.py
  replay/
    replay.py
  tests/
    fixtures/            # recorded API responses
    test_schemas.py test_stats.py test_gmx.py test_pendle.py test_evidence.py
    test_risk_tools.py test_graph.py test_executor.py test_reporter.py test_evals.py
```

---

### Task B1: Project setup, schemas, config

**Files:**
- Create: `agents/pyproject.toml`, `agents/desk/{__init__,config,schemas,state}.py`, `agents/tests/test_schemas.py`, `.github/workflows/agents.yml`

**Interfaces:**
- Produces (in `schemas.py`, all Pydantic v2):
  ```python
  class AprByPeriod(BaseModel): one_d: int | None = Field(alias="1d"); seven_d: int | None = Field(alias="7d"); thirty_d: int | None = Field(alias="30d"); ninety_d: int | None = Field(alias="90d")
  class MarketSnapshot(BaseModel): market: str; current_apr_bps: int; apr_by_period: AprByPeriod; fetched_at: datetime; stale: bool = False
  class PendlePoint(BaseModel): ts: datetime; implied_apy_bps: int; underlying_apy_bps: int
  class PendleSnapshot(BaseModel): market: str; address: str; implied_apy_bps: int; underlying_apy_bps: int; expiry: datetime; liquidity_usd: float; fetched_at: datetime; stale: bool = False; expired_fallback: bool = False; history: list[PendlePoint]
  class FixVsFloatStats(BaseModel): days: int; pct_days_float_beat_fixed: float; current_gap_bps: int; breakeven_apr_bps: int; trend_30d: Literal["up","down","flat"]
  class Argument(BaseModel): claim: str; evidence_field: str
  class Case(BaseModel): position: Literal["fixed","floating"]; confidence: float = Field(ge=0, le=1); arguments: list[Argument] = Field(min_length=1, max_length=5)
  class Objection(BaseModel): to: Literal["fixed","floating"]; argument_idx: int; reason: str
  class Verdict(BaseModel): target_fixed_bps: int = Field(ge=0, le=10000); vetoed: bool; rationale: str; objections: list[Objection]; needs_rebuttal: bool
  class Move(BaseModel): user: str; from_vault: str; to_vault: str; assets: int; tx_hash: str | None = None
  class Skip(BaseModel): user: str; reason: Literal["policy_disabled","cooldown","no_balance","no_allowance","below_min","tx_failed"]
  class ExecutionReport(BaseModel): moves: list[Move]; skipped: list[Skip]; gas_used: int
  class DeskReport(BaseModel): run_id: str; created_at: datetime; gmx: MarketSnapshot|None; pendle: PendleSnapshot|None; stats: FixVsFloatStats|None; fixed_case: Case|None; float_case: Case|None; verdict: Verdict|None; rebuttal_round: int; report_hash: str|None; execution: ExecutionReport|None; errors: list[str]
  class DeskAborted(Exception): ...
  ```
- `state.py`: `DeskState(TypedDict, total=False)` with the fields from spec §5.1 plus `objections_for_fixed: list[Objection]`, `objections_for_float: list[Objection]`, `report_hash: str | None`.
- `config.py`: `Settings(BaseSettings)` with `anthropic_api_key`, `openai_api_key`, `llm_provider: Literal["anthropic","openai"]="anthropic"`, `model_small`, `model_large`, `gmx_apy_url="https://arbitrum-api.gmxinfra.io/apy"`, `pendle_api_url="https://api-v2.pendle.finance/core"`, `pendle_chain_id=42161`, `pendle_market_address: str|None=None`, `gmx_market_name="GM: ETH/USD [WETH-USDC]"`, `max_age_hours=12`, `min_days_to_expiry=14`, `min_change_bps=500`, `history_days=90`, `rpc_url`, `agent_private_key`, `deployments_path="../contracts/deployments/arbitrum-sepolia.json"`, `runs_dir="../api/data/runs"`.

- [ ] **Step 1:** `uv init agents --python 3.12 --no-workspace`; add deps listed in Tech Stack; add `pytest`, `pytest-asyncio`, `respx` as dev deps; `[tool.pytest.ini_options] asyncio_mode = "auto"`.
- [ ] **Step 2: Write failing tests** `test_schemas.py`:
  - `test_case_requires_at_least_one_argument()` — `Case(position="fixed", confidence=.5, arguments=[])` raises `ValidationError`.
  - `test_verdict_bps_bounds()` — `target_fixed_bps=10001` raises.
  - `test_desk_report_round_trips_json()` — build a full report from the overview example, `DeskReport.model_validate_json(r.model_dump_json(by_alias=True))` equals `r`.
  - `test_apr_by_period_alias()` — `AprByPeriod.model_validate({"7d": 1840})` → `seven_d == 1840`.
- [ ] **Step 3:** `uv run pytest tests/test_schemas.py` → FAIL.
- [ ] **Step 4:** Implement `schemas.py`, `state.py`, `config.py`.
- [ ] **Step 5:** `uv run pytest tests/test_schemas.py` → PASS.
- [ ] **Step 6:** `.github/workflows/agents.yml`: on `agents/**`; `astral-sh/setup-uv@v3`; `uv sync`; `uv run pytest -m "not anvil and not live"`.
- [ ] **Step 7:** Commit `feat(agents): project setup and typed schemas`.

---

### Task B2: Deterministic stats tool

**Files:**
- Create: `agents/desk/tools/stats.py`
- Test: `agents/tests/test_stats.py`

**Interfaces:**
- Produces: `fix_vs_float_stats(gmx: MarketSnapshot, pendle: PendleSnapshot, trend_threshold_bps: int = 50) -> FixVsFloatStats`.
- Definitions: `days = len(pendle.history)`; `pct_days_float_beat_fixed = 100 * count(p.underlying_apy_bps > p.implied_apy_bps) / days` (0.0 if `days == 0`); `current_gap_bps = gmx.current_apr_bps - pendle.implied_apy_bps`; `breakeven_apr_bps = pendle.implied_apy_bps`; `trend_30d`: mean of `underlying_apy_bps` over last 7 points minus mean over the 7 points ending 30 points earlier → `"up"` if `> +threshold`, `"down"` if `< -threshold`, else `"flat"`; `"flat"` if fewer than 37 points.

- [ ] **Step 1: Write failing tests** with a helper `_pendle(history: list[tuple[int,int]])`:
  - `test_pct_days_counts_strict_wins()` — history `[(1500,1800),(1500,1500),(1500,1400),(1500,1600)]` (implied, underlying) → `50.0`.
  - `test_gap_uses_gmx_current_vs_implied()` — gmx 1840, implied 1500 → `340`.
  - `test_trend_up_down_flat()` — synthetic 40-point ramps for each label.
  - `test_empty_history_is_safe()` — `days == 0`, pct `0.0`, trend `"flat"`.
- [ ] **Step 2:** `uv run pytest tests/test_stats.py` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest tests/test_stats.py` → PASS.
- [ ] **Step 5:** Commit `feat(agents): deterministic fix-vs-float stats`.

---

### Task B3: Data tools — GMX and Pendle (fixture-driven)

**Files:**
- Create: `agents/desk/tools/{http,gmx,pendle}.py`, `agents/tests/fixtures/{gmx_apy_7d.json,pendle_markets_all.json,pendle_history.json}`
- Test: `agents/tests/test_gmx.py`, `agents/tests/test_pendle.py`

**Interfaces:**
- `http.py`: `async def get_json(url: str, params: dict | None = None, timeout: float = 20) -> Any` using one module-level `httpx.AsyncClient`.
- `gmx.py`: `async def fetch_gm_apr(market_name: str, settings: Settings, now: datetime) -> MarketSnapshot` — calls `settings.gmx_apy_url` once per period in `("1d","7d","30d","90d")`, finds the market by name, converts fractional APY to bps (`round(apy * 10_000)`), `current_apr_bps = seven_d`. Raises `DataUnavailable(market_name)` if the market key is absent.
- `pendle.py`: `async def discover_gm_market(settings: Settings, now: datetime) -> tuple[dict, bool]` — GET `{pendle_api_url}/v2/markets/all`, filter `chainId == 42161` and market `name` or underlying `symbol` starts with `"GM"` (case-insensitive) ; prefer unexpired with latest expiry; else most recently expired with `expired_fallback=True`; raises `DataUnavailable("pendle-gm")` if none. If `settings.pendle_market_address` is set, select that address instead.
  `async def fetch_pendle(settings: Settings, now: datetime) -> PendleSnapshot` — uses discovery, then GET `{pendle_api_url}/v3/{chainId}/markets/{address}/historical-data` with `time_frame=day`, `timestamp_start=now-history_days`, `fields=impliedApy,underlyingApy`; fills `history`, `implied_apy_bps`/`underlying_apy_bps` from the last point, `expiry`, `liquidity_usd` from the market record.
- Both set `stale = (now - fetched_at) > max_age_hours` — always `False` on a live fetch; the field exists so cached snapshots can be judged.

- [ ] **Step 1 (discovery, record once):** `curl -s "https://arbitrum-api.gmxinfra.io/apy?period=7d" > tests/fixtures/gmx_apy_7d.json`; `curl -s "https://api-v2.pendle.finance/core/v2/markets/all" > tests/fixtures/pendle_markets_all.json`; find the GM market address in it; `curl` its v3 historical-data for 90 days into `tests/fixtures/pendle_history.json`. If no unexpired GM market exists, record the most recent expired one and note it in the test file docstring. Trim fixtures to the relevant entries if over 200 KB.
- [ ] **Step 2: Write failing tests** using `respx.mock` to serve the fixtures:
  - `test_fetch_gm_apr_parses_bps()` — `current_apr_bps` equals `round(fixture_value * 10000)`; `apr_by_period.seven_d` set.
  - `test_fetch_gm_apr_unknown_market_raises()` → `DataUnavailable`.
  - `test_discover_prefers_unexpired_gm_market()` — with a fixture containing one expired and one live GM market, returns the live one and `False`.
  - `test_discover_falls_back_to_expired()` — only expired → `(…, True)`.
  - `test_fetch_pendle_builds_history()` — `len(history) == len(fixture points)`; `implied_apy_bps == round(last.impliedApy*10000)`.
- [ ] **Step 3:** `uv run pytest tests/test_gmx.py tests/test_pendle.py` → FAIL.
- [ ] **Step 4:** Implement the three modules.
- [ ] **Step 5:** `uv run pytest tests/test_gmx.py tests/test_pendle.py` → PASS. Also one `@pytest.mark.live` test per tool that hits the real API (skipped in CI).
- [ ] **Step 6:** Commit `feat(agents): GMX and Pendle data tools with recorded fixtures`.

---

### Task B4: Evidence validator and risk tools

**Files:**
- Create: `agents/desk/tools/evidence.py`, `agents/desk/tools/risk.py`
- Test: `agents/tests/test_evidence.py`, `agents/tests/test_risk_tools.py`

**Interfaces:**
- `evidence.py`: `allowed_fields(stats, gmx, pendle) -> set[str]` — dotted leaf paths such as `stats.current_gap_bps`, `gmx.apr_by_period.7d`, `pendle.implied_apy_bps` (exclude `history`, `fetched_at`). `invalid_citations(case: Case, allowed: set[str]) -> list[int]` — indices of arguments whose `evidence_field` is not allowed.
- `risk.py`: `freshness_errors(gmx, pendle, now, max_age_hours) -> list[str]` (non-empty if either snapshot `stale` or `fetched_at` older than limit); `expiry_blocks_fixed(pendle, now, min_days) -> bool` (`True` if `expired_fallback` or `expiry - now < min_days`); `enforce(verdict: Verdict, freshness: list[str], expiry_blocked: bool) -> Verdict` — returns a copy with `vetoed=True` if `freshness` non-empty, and `target_fixed_bps=0` if `expiry_blocked`, appending the reason to `rationale`.

- [ ] **Step 1: Write failing tests:**
  - `test_allowed_fields_contains_leaves_not_history()`.
  - `test_invalid_citations_flags_made_up_fields()` — `evidence_field="stats.magic"` → `[0]`.
  - `test_freshness_flags_old_snapshot()` — `fetched_at = now - 13h` → one error.
  - `test_expiry_blocks_within_14_days()` and `test_expiry_blocks_expired_fallback()`.
  - `test_enforce_zeroes_fixed_when_expiry_blocked()` — LLM said 7000 → `0`. *(Review Focus 4)*
  - `test_enforce_vetoes_on_stale()`.
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS.
- [ ] **Step 5:** Commit `feat(agents): evidence and risk guards`.

---

### Task B5: Graph skeleton with FakeLLM

**Files:**
- Create: `agents/desk/llm.py`, `agents/desk/graph.py`, `agents/desk/nodes/{scouts,stats,advocates,risk,executor,reporter}.py`, `agents/desk/prompts/*.md`
- Test: `agents/tests/test_graph.py`

**Interfaces:**
- `llm.py`: `make_llm(tier: Literal["small","large"], settings) -> BaseChatModel`; `class FakeLLM` whose `.with_structured_output(Model)` returns a runnable yielding the next queued instance for that `Model` (queue per model class; raises `AssertionError` if empty).
- `graph.py`: `build_graph(*, llm_small, llm_large, fetch_gmx, fetch_pendle, executor, now: Callable[[], datetime], settings) -> CompiledStateGraph`. Dependency-injected so tests pass fakes. Nodes and edges exactly as spec §5.2; parallelism via LangGraph fan-out (`START → gmx_scout, pendle_scout → stats`; `stats → fixed_advocate, float_advocate → risk_officer`).
- Node contracts:
  - `gmx_scout` / `pendle_scout`: call the injected fetchers; on `DataUnavailable` append to `errors` and leave snapshot `None`. (Scout LLM calls are not needed for correctness; scouts are code in v1. The `scout.md` prompt is used only to produce a one-line `market_note: str` in state for the UI. Keep it optional.)
  - `stats`: if either snapshot is `None` → `errors += ["missing_data"]`, verdict `Verdict(target_fixed_bps=0, vetoed=True, rationale="missing data", objections=[], needs_rebuttal=False)` and jump to `reporter`.
  - `fixed_advocate` / `float_advocate`: prompt from `advocate.md` + JSON of `stats, gmx(without history), pendle(without history)` + prior objections if `rebuttal_round == 1`; structured output `Case`; validate `position` matches node and `invalid_citations == []`, else retry once then `DeskAborted`.
  - `risk_officer`: compute `freshness_errors`, `expiry_blocks_fixed` first and include in prompt; structured output `Verdict`; then `enforce(...)`. Routing: if `verdict.needs_rebuttal and rebuttal_round == 0` → set `rebuttal_round = 1`, split objections into `objections_for_fixed/float`, go to both advocates; else → `executor`.
  - `executor`: if `verdict.vetoed` → `execution = ExecutionReport([], [], 0)`; else call injected `executor.execute(verdict.target_fixed_bps, report_hash)` where `report_hash` is computed here by `reporter.report_hash(build_report(state))` before execution.
  - `reporter`: `build_report(state)`, `save_report`, returns `report`.

- [ ] **Step 1: Write failing tests** with `FakeLLM` and fake fetchers returning fixture-based snapshots, `FakeExecutor` recording calls:
  - `test_happy_path_no_rebuttal()` — queue one `Case` each and a `Verdict(needs_rebuttal=False, target=3000)`; final state has `report.verdict.target_fixed_bps == 3000`, `rebuttal_round == 0`, executor called once with `3000` and a 66-char hash.
  - `test_rebuttal_round_runs_advocates_twice()` — first `Verdict(needs_rebuttal=True)`, second `needs_rebuttal=False`; advocates' LLM queue consumed twice; `rebuttal_round == 1`; second verdict wins.
  - `test_forced_decision_after_one_rebuttal()` — both verdicts `needs_rebuttal=True`; graph still reaches executor; no third advocate call.
  - `test_invalid_citation_retries_then_aborts()` — queue two bad `Case`s → `DeskAborted`; executor never called.
  - `test_missing_data_vetoes_without_llm()` — `fetch_pendle` raises `DataUnavailable`; no LLM calls; report `vetoed`, `errors == ["pendle-gm", "missing_data"]`.
  - `test_vetoed_verdict_skips_execution()`.
- [ ] **Step 2:** run → FAIL. **Step 3:** implement graph, nodes, prompts (prompts: role, the honesty rules from spec §5.3 in plain words, the JSON schema is supplied by structured output). **Step 4:** run → PASS.
- [ ] **Step 5:** Commit `feat(agents): LangGraph desk with adversarial review loop`.

---

### Task B6: Real LLM nodes (`live` tests)

**Files:**
- Modify: `agents/desk/llm.py` (Anthropic/OpenAI factories), `agents/desk/run.py`
- Test: `agents/tests/test_graph_live.py` (`@pytest.mark.live`)

**Interfaces:**
- `run.py`: `async def run_desk(settings: Settings, *, run_id: str | None = None, executor: Executor | None = None, on_event: Callable[[dict], None] | None = None) -> DeskReport` — uses the given `run_id` or `reporter.new_run_id(now)`, builds graph with real LLMs and fetchers, streams node events to `on_event` (`{"node": name, "phase": "start"|"end", "run_id": ...}`), applies `MIN_CHANGE_BPS` gate by reading `runs_dir/latest.json` (skip executor with `Skip(reason="below_min")` for all users if `abs(new - previous) < min_change_bps`), writes `runs/{run_id}.json` and `runs/latest.json`. CLI: `uv run python -m desk.run [--dry-run]` (`--dry-run` uses a `NoopExecutor`).

- [ ] **Step 1: Write live test** `test_live_desk_produces_valid_report()` — runs `run_desk(dry_run)`; asserts `report.verdict is not None`, both cases have only valid citations, total tokens logged < 60k.
- [ ] **Step 2:** Implement factories (`ChatAnthropic` / `ChatOpenAI`, temperature 0) and `run.py`. Logging: stdlib `logging` with a JSON formatter (`{"ts","level","run_id","node","msg"}`) configured in `run.py`; LangSmith is enabled purely by the standard `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` env vars, no code.
- [ ] **Step 3:** `uv run pytest -m live tests/test_graph_live.py -s` → PASS with real keys; paste one full report into `agents/evals/golden/example_live_run.json` for the UI fallback.
- [ ] **Step 4:** Commit `feat(agents): live LLM wiring and run entrypoint`.

---

### Task B7: Reporter and report hash

**Files:**
- Create: `agents/desk/reporter.py`
- Test: `agents/tests/test_reporter.py`

**Interfaces:**
- `build_report(state: DeskState, now: datetime) -> DeskReport`; `canonical_json(report: DeskReport) -> str` (execution and report_hash nulled, `sort_keys=True`, `separators=(",",":")`, datetimes as ISO-8601 Z); `report_hash(report) -> str` = `"0x" + keccak(canonical_json).hex()`; `save_report(report, runs_dir) -> Path` writes `{run_id}.json` and overwrites `latest.json`; `new_run_id(now) -> str` = `now.strftime("%Y-%m-%dT%H-%M-%SZ") + "-" + 4 hex`.

- [ ] **Step 1: Write failing tests:**
  - `test_hash_ignores_execution_and_hash_fields()` — same report with/without `execution` hashes equal.
  - `test_hash_is_deterministic_across_key_order()`.
  - `test_hash_matches_solidity_keccak()` — compare with `web3.Web3.keccak(text=canonical)`.
  - `test_save_writes_run_and_latest()`.
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS.
- [ ] **Step 5:** Commit `feat(agents): deterministic report hashing and persistence`.

---

### Task B8: Executor against Anvil

**Files:**
- Create: `agents/desk/executor.py`, `agents/tests/conftest.py` (anvil fixture), `agents/tests/test_executor.py`

**Interfaces:**
- Pure function: `plan_move(fixed_assets: int, floating_assets: int, policy: Policy, target_fixed_bps: int, now: int, allowance_ok: bool) -> Move | Skip` where `Policy` is a small dataclass mirroring the contract struct. Logic: `total = fixed+floating`; if `total == 0` → `Skip("no_balance")`; if not `policy.enabled` → `Skip("policy_disabled")`; if `now < lastMove + cooldown` → `Skip("cooldown")`; if not `allowance_ok` → `Skip("no_allowance")`; `desired_fixed = total * target / 10000`; `delta = desired_fixed - fixed`; `cap = total * maxMoveBps // 10000`; `assets = min(abs(delta), cap)`; if `assets == 0` → `Skip("below_min")`; direction from sign of `delta`.
- `class Executor`: `__init__(w3: Web3, deployments: dict, abis: dict, agent_key: str)`; `list_delegated_users(from_block) -> list[str]` (distinct `PolicySet` emitters whose latest `enabled` is true); `user_state(user) -> tuple[int,int,Policy,bool]` (`assetsOf` ×2, `policies`, allowance check on the `from` side computed for both vaults: allowance ok iff `allowance(user, router) >= balanceOf(user)` on both vaults); `execute(target_fixed_bps, report_hash) -> ExecutionReport` — plans for each user, sends `moveFor` with `eth_estimateGas` + 20%, waits receipt, records `tx_hash` or `Skip("tx_failed")`, sums `gas_used`; stops sending once `gas_used + estimate > settings.max_gas_per_run` (add to `Settings`, default `3_000_000`) and marks remaining users `Skip("gas_cap")` (add `"gas_cap"` to the `Skip.reason` literal in B1).
- `conftest.py`: session fixture `anvil` that starts `anvil --port 8546`, runs `forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8546 --broadcast` with Anvil account 0 as deployer and account 1 as agent, loads the written JSON; marked `@pytest.mark.anvil`.

- [ ] **Step 1: Write failing unit tests** for `plan_move` (no chain):
  - `test_plan_zero_balance_skips_no_balance()` *(Review Focus 1)*
  - `test_plan_missing_allowance_skips()` *(Review Focus 2)*
  - `test_plan_clips_to_cap()` — 1000 fixed / 9000 floating, target 10000, cap 2500 → `Move(assets=2500, floating→fixed)`.
  - `test_plan_direction_toward_floating()`.
  - `test_plan_cooldown_skips()`.
  - `test_execute_stops_at_gas_cap()` (anvil) — `max_gas_per_run=1` → every user `Skip("gas_cap")`, no tx sent.
- [ ] **Step 2: Write failing anvil tests:**
  - `test_execute_moves_delegated_user()` — alice deposits 100e6 floating, approves router shares, `setPolicy(true, 5000, 0)`; `execute(10000, hash)` → one `Move` with tx hash; on-chain `assetsOf(alice, fixed)` ≈ 50e6.
  - `test_execute_skips_user_without_allowance()` — bob deposits but does not approve → `Skip("no_allowance")`, no tx sent.
  - `test_execute_reports_tx_failed_on_revert()` — simulate by revoking `AGENT_ROLE` before execute → `Skip("tx_failed")` per user, run does not raise.
- [ ] **Step 3:** `uv run pytest tests/test_executor.py` → FAIL. **Step 4:** implement. **Step 5:** `uv run pytest tests/test_executor.py -m "anvil or not anvil"` → PASS (requires `anvil` and `forge` on PATH).
- [ ] **Step 6:** Commit `feat(agents): deterministic executor with policy-aware planning`.

---

### Task B9: Evals and replay

**Files:**
- Create: `agents/evals/golden/*.json` (20 cases), `agents/evals/run_evals.py`, `agents/replay/replay.py`, `agents/tests/test_evals.py`

**Interfaces:**
- Golden case file: `{"name": str, "gmx": MarketSnapshot, "pendle": PendleSnapshot, "expected_band": [lo_bps, hi_bps], "expect_veto": bool}`. Derive the 20 cases from the recorded 90-day Pendle history by slicing windows (use `tests/fixtures/pendle_history.json`), plus 3 synthetic: stale GMX, expiring market, expired fallback. Expected band rule (deterministic, documented in the file header): `pct ≥ 60 → [0, 3000]`, `pct ≤ 40 → [7000, 10000]`, else `[3000, 7000]`; veto cases expect `vetoed`.
- `run_evals.py`: `--mode cached|live`. Cached mode uses `FakeLLM` loaded from `evals/cache/{case}.json` (recorded once in live mode). Outputs `evals/results/latest.json` with `in_band_rate`, `veto_accuracy`, `citation_validity_rate`, `mean_tokens`, `mean_latency_s`, and prints a table. Exit 1 if `in_band_rate < 0.8` or `veto_accuracy < 1.0`.
- `replay.py`: `--window 90 --cadence 1d --start-split 5000` — steps through the history, calls the graph in cached mode (or the deterministic band rule with `--rule-only`), applies `MIN_CHANGE_BPS`, accrues each day's yield at `underlying_apy` for the floating sleeve and `implied_apy` (locked at entry) for the fixed sleeve; writes `replay/results/replay.csv` (`date, split_bps, desk_value, always_fixed, always_floating`) and `replay/results/replay.png`.

- [ ] **Step 1: Write failing tests** `test_evals.py`: `test_golden_files_validate()` (all 20 parse), `test_run_evals_cached_passes_thresholds()`, `test_replay_rule_only_produces_csv_and_png()`.
- [ ] **Step 2:** run → FAIL. **Step 3:** implement; record the live cache once (`uv run python evals/run_evals.py --mode live --record`). **Step 4:** run → PASS.
- [ ] **Step 5:** Add `uv run python evals/run_evals.py --mode cached` to `agents.yml`.
- [ ] **Step 6:** Commit `feat(agents): golden evals and historical replay`.
