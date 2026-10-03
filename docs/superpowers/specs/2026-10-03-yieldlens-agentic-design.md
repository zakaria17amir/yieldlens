# YieldLens v2 — Autonomous Multi-Agent Fix-or-Float Desk on Arbitrum

**Status:** design approved in conversation, awaiting written review
**Supersedes:** `yieldlens-project-plan.md` (v1, advisory-only)
**Date:** 2026-10-03

---

## 1. Goal

GMX liquidity providers face one recurring decision: keep floating fee yield on GMX, or lock a fixed rate on Pendle. YieldLens v2 is a team of AI agents that makes that decision continuously, argues it out in the open, and executes it on Arbitrum for users who opt in, inside limits those users set on-chain.

The project must satisfy the Arbitrum Open House judging criteria:

| Criterion | How v2 meets it |
|---|---|
| Deployed on an Arbitrum chain | Arbitrum Sepolia (guaranteed). Arbitrum One with real USDG is a v2 seam, not in scope. |
| Smart contract quality | OpenZeppelin ERC-4626 vaults, AccessControl, Pausable. Agents can only move funds between two allowlisted vaults, for opted-in users, within user-set caps. No path to withdraw to an external address. Foundry unit and fuzz tests. |
| Product-market fit | Progressive trust: users can watch the desk, move manually, or delegate with their own caps. Same product serves sceptics and believers; retention comes from the on-chain track record. |
| Innovation | Adversarial agent desk (two advocates, a risk officer that must address every argument) whose decisions are hashed on-chain and auditable from Dune back to the agent transcript. |
| Real problem | The GMX x Pendle integration is live; no tool connects the two yield models into a decision, let alone acts on it. |
| USDG bonus | USDG is the vault asset. Mock USDG on Sepolia (6 decimals, matching the real token); real USDG `0x004B506865409877C9fA29bfb1ebA929984B9bbC` on Arbitrum One behind the same interface. |

Secondary goal: the agent layer must be a credible agentic-AI portfolio piece: typed tool use, orchestration graph, adversarial review, deterministic execution, evals, replay, and observability.

## 2. Non-goals (do not build)

- Real GMX or Pendle adapters (v2; the `IYieldAdapter` seam is the handoff point)
- Arbitrum One deployment
- Any asset other than USDG
- Per-user agent instances or per-user prompts (user preferences are on-chain policy params only)
- Predictive ML models
- Mobile UI, multi-language, notifications

## 3. Architecture overview

```
 ┌──────────────────────── off-chain (Python) ────────────────────────┐
 │  LangGraph "desk"                                                   │
 │  GmxScout ─┐                                                        │
 │            ├► FixedAdvocate ─┐                                      │
 │  PendleScout┘                ├► RiskOfficer ─► Verdict              │
 │            └► FloatAdvocate ─┘      ▲  rebuttal (≤1 round)          │
 │                                     ▼                               │
 │                       Executor (pure code) ─► Reporter              │
 └─────────┬───────────────────────────────────────────┬──────────────┘
           │ moveFor(user, from, to, amount, reportHash)│ DeskReport JSON
           ▼                                           ▼
 ┌──────── on-chain (Arbitrum Sepolia) ───────┐   FastAPI ─► React UI
 │ AgentRouter ──► FixedVault ──► PendleAdapter│           └► Dune
 │      │          FloatingVault► GmxAdapter   │
 │      └── per-user Policy, AGENT_ROLE        │
 └─────────────────────────────────────────────┘
```

## 4. On-chain layer

Stack: Solidity ^0.8.24, Foundry, OpenZeppelin Contracts 5.x.

### 4.1 Contracts

| Contract | Base | Purpose |
|---|---|---|
| `MockUSDG` | `ERC20` | 6 decimals, open `mint` for testnet. |
| `IYieldAdapter` | interface | `deposit(uint256) returns (uint256)`, `withdraw(uint256) returns (uint256)`, `totalAssets() view returns (uint256)`. |
| `MockGmxAdapter`, `MockPendleAdapter` | `IYieldAdapter`, `Ownable` | Hold USDG, accrue simulated yield at an owner-set APR (`setAprBps`) using elapsed time, so balances move visibly in the demo. Only the owning vault can call `deposit`/`withdraw`. |
| `StrategyVault` | `ERC4626`, `Ownable` | One per strategy. `totalAssets()` = adapter `totalAssets()`. Deposits forward to adapter; withdrawals pull from adapter. Deployed twice: `FixedVault` (Pendle adapter) and `FloatingVault` (GMX adapter). |
| `AgentRouter` | `AccessControl`, `Pausable`, `ReentrancyGuard` | The only contract agents call. Holds per-user policy. Allowlist of vaults set by `DEFAULT_ADMIN_ROLE`. |

### 4.2 AgentRouter interface

```solidity
struct Policy { bool enabled; uint16 maxMoveBps; uint32 cooldown; uint64 lastMove; }

function setPolicy(bool enabled, uint16 maxMoveBps, uint32 cooldown) external;
function moveSelf(address fromVault, address toVault, uint256 assets, bytes32 reportHash) external;
function moveFor(address user, address fromVault, address toVault, uint256 assets, bytes32 reportHash)
    external onlyRole(AGENT_ROLE) whenNotPaused;
function setVaultAllowed(address vault, bool allowed) external onlyRole(DEFAULT_ADMIN_ROLE);

event PolicySet(address indexed user, bool enabled, uint16 maxMoveBps, uint32 cooldown);
event Moved(address indexed user, address indexed fromVault, address indexed toVault,
            uint256 assets, bytes32 reportHash, bool byAgent);
```

`moveFor` checks, in order: not paused; both vaults allowlisted and distinct; `policy.enabled`; `block.timestamp >= lastMove + cooldown`; `assets <= (userTotalAssets * maxMoveBps) / 10_000` where `userTotalAssets` = sum of `convertToAssets(balanceOf(user))` across both vaults; then `redeem` from `fromVault` on the user's behalf (user has approved router for shares), `deposit` into `toVault` with the user as receiver, update `lastMove`, emit `Moved`. Funds never leave the two vaults and the receiver is always `user`.

`moveSelf` skips policy checks but requires the same allowlist and uses the same event with `byAgent=false`.

Admin can `pause()`, `revokeRole(AGENT_ROLE, agent)`, and change the allowlist. There is no admin function that moves user funds.

### 4.3 Tests (Foundry)

- `StrategyVault`: deposit/mint/withdraw/redeem round-trips; `totalAssets` tracks adapter accrual; share price rises after time passes; only vault can call adapter.
- `AgentRouter`: `moveFor` reverts when paused, policy disabled, over cap, within cooldown, vault not allowlisted, same vault, caller lacks role. Succeeds at exactly the cap and exactly at cooldown expiry. `moveSelf` ignores policy but respects allowlist. Events emitted with correct fields.
- Fuzz: random `(maxMoveBps, assets, balances)` never lets `moveFor` exceed cap; random time never lets it bypass cooldown.
- Invariant: sum of USDG held by both adapters equals sum of both vaults' `totalAssets` (minus simulated accrual).
- Deploy script for Sepolia writes addresses to `deployments/arbitrum-sepolia.json` consumed by agents, API and web.

## 5. Agent layer

Stack: Python 3.12, LangGraph, Pydantic v2, web3.py, httpx. Provider via env (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`); two model tiers in config: `small` (scouts, reporter) and `large` (advocates, risk officer).

### 5.1 Shared state

```python
class DeskState(TypedDict):
    run_id: str
    gmx: MarketSnapshot | None
    pendle: PendleSnapshot | None
    stats: FixVsFloatStats | None
    fixed_case: Case | None
    float_case: Case | None
    verdict: Verdict | None
    rebuttal_round: int           # 0 or 1
    execution: ExecutionReport | None
    report: DeskReport | None
    errors: list[str]
```

### 5.2 Agents

| Node | LLM | Tools | Output schema |
|---|---|---|---|
| `gmx_scout` | small | `fetch_gm_apr_history(market, days) -> list[AprPoint]` | `MarketSnapshot{market, apr_series, current_apr_bps, fetched_at, stale: bool}` |
| `pendle_scout` | small | `fetch_pendle_market(market) -> dict` | `PendleSnapshot{market, implied_apy_bps, underlying_apy_bps, expiry, liquidity_usd, fetched_at, stale: bool}` |
| `stats` | none | `fix_vs_float_stats(gmx, pendle) -> FixVsFloatStats` | `{days, pct_days_float_beat_fixed, current_gap_bps, breakeven_apr_bps, trend_30d}` |
| `fixed_advocate` | large | read-only access to `stats`, `gmx`, `pendle` | `Case{position: "fixed", confidence: 0-1, arguments: list[Argument{claim, evidence_field}]}` |
| `float_advocate` | large | same | `Case{position: "floating", ...}` |
| `risk_officer` | large | `policy_check()`, `data_freshness(gmx, pendle)`, `expiry_check(pendle)` | `Verdict{target_fixed_bps: 0-10000, vetoed: bool, rationale, objections: list[Objection{to: "fixed"\|"floating", argument_idx, reason}], needs_rebuttal: bool}` |
| `executor` | none | `list_delegated_users()`, `user_positions(user)`, `plan_move(user, target_fixed_bps, policy)`, `send_move_for(...)`, `wait_receipt(tx)` | `ExecutionReport{moves: list[Move], skipped: list[Skip{user, reason}], tx_hashes, gas_used}` |
| `reporter` | small | `write_report(path)`, `keccak(json)` | `DeskReport{run_id, snapshots, stats, cases, verdict, execution, created_at}`; `report_hash` |

Graph edges: `gmx_scout` and `pendle_scout` run in parallel → `stats` → `fixed_advocate` and `float_advocate` in parallel → `risk_officer` → if `needs_rebuttal and rebuttal_round == 0`: back to both advocates with objections attached, `rebuttal_round = 1`, then `risk_officer` again (forced decision, `needs_rebuttal` ignored) → `executor` → `reporter` → END. Advocates run in parallel in both rounds; nothing in the graph is sequential that does not need to be.

Executor runs only if `not verdict.vetoed` and the verdict's `target_fixed_bps` differs from the previous run's by more than `MIN_CHANGE_BPS` (config, default 500). The `report_hash` passed to `moveFor` is computed from the report *before* execution fields are filled (so the hash commits to the decision, not the outcome); the final report includes both hash and execution.

### 5.3 Honesty rules (enforced in code, not prompts)

- Every `Argument.evidence_field` must name a real field in `stats`/`gmx`/`pendle`; a validator rejects cases that cite nonexistent evidence.
- All LLM outputs use structured output with the Pydantic schema; parse failure retries once, then the run aborts with `errors` populated and no execution.
- Scouts mark `stale=True` if data is older than `MAX_AGE_HOURS` (config, default 12). Risk Officer tool `data_freshness` forces `vetoed=True` if either is stale.
- `expiry_check` vetoes fixed allocation above 0 if the Pendle market expires within `MIN_DAYS_TO_EXPIRY` (default 14).
- Executor is deterministic and re-implements the user policy checks locally so it never submits a transaction the contract will revert.

### 5.4 Evals and replay

- `agents/evals/golden/` — about 20 hand-checked historical snapshot pairs with expected `target_fixed_bps` band from the deterministic rule. Eval runs the graph with a fake Executor and reports: verdict-in-band rate, veto correctness on stale/expiring fixtures, evidence-citation validity rate, mean tokens and latency per run.
- `agents/replay/` — runs the graph over a historical window at a fixed cadence with a simulated portfolio; outputs CSV and a chart comparing desk P&L vs always-fixed vs always-floating. Chart goes in README and Dune.
- Evals run in CI on a cached, deterministic model response set (recorded with the provider's seed where available), so CI is free and stable; a manual job runs them live.

### 5.5 Observability

Structured JSON logs per node with `run_id`. Optional LangSmith via env. Each `DeskReport` is stored at `api/data/runs/{run_id}.json`; the on-chain `reportHash` lets anyone verify a report against the `Moved` event.

## 6. API layer

FastAPI, Python, same virtualenv as agents.

| Endpoint | Purpose |
|---|---|
| `POST /desk/run` | Start a desk run; returns `run_id`. Rate limited to one concurrent run. |
| `GET /desk/runs/{run_id}/events` | Server-sent events stream of node progress for the UI. |
| `GET /desk/latest` | Latest `DeskReport`. |
| `GET /desk/runs/{run_id}` | A specific report. |
| `GET /health` | |

Scheduler: a GitHub Actions cron (every 6 h) calls `POST /desk/run`. Reports stored as JSON files; no database in scope.

The agent private key lives only in the API environment (`AGENT_PRIVATE_KEY`). It is never in the repo, the web app, or logs.

## 7. Web layer

React + Vite + TypeScript, wagmi v2, RainbowKit, viem. ABIs and addresses imported from `contracts/deployments/arbitrum-sepolia.json`.

Single page, three panels:

1. **Desk** — latest report: two advocate cases side by side with confidence and arguments, Risk Officer verdict, target split, objections and rebuttals. "Convene desk now" button triggers `POST /desk/run` and streams node progress.
2. **Your position** — USDG balance, mint test USDG, shares and asset value in each vault, deposit/withdraw per vault, manual move, delegation toggle with `maxMoveBps` and cooldown controls, approve-router step, and a history list from `Moved` events for the connected wallet.
3. **Track record** — embedded Dune dashboard and the replay chart image.

Demo fallback: if the API is unreachable, the Desk panel loads a bundled `golden_run.json` and labels it as cached.

## 8. Dune

Queries over Sepolia decoded events (or raw logs if decoding is unavailable on Sepolia): `Moved` volume per day, split between agent and manual moves, per-user delegation counts from `PolicySet`, and the desk's target split over time joined with GMX and Pendle APR series uploaded via Dune's CSV upload. Saved query SQL lives in `dune/`.

## 9. Repository layout

```
contracts/        Foundry project: src/, test/, script/, deployments/
agents/           desk/ (graph, nodes, tools, schemas), evals/, replay/, tests/
api/              FastAPI app, data/runs/
web/              React app
dune/             saved query SQL
docs/superpowers/ specs/, plans/
.github/workflows ci.yml (forge test, pytest, eval-cached, web build), desk-cron.yml
```

## 10. Build approach

Lead-and-lanes: one lead plans and reviews; implementation is split into lanes that map to top-level folders and run in parallel where independent. Every lane uses TDD. Every lane's diff gets an independent review before merge; the contracts lane gets an additional security-focused review.

Order of work (each step becomes a plan phase):

1. Repo scaffold, CI skeleton, shared `deployments` schema.
2. Contracts (in parallel with 3): mocks, vaults, router, tests, Sepolia deploy.
3. Agent core: schemas, deterministic tools, graph with fake LLM in tests, evals harness.
4. Agent LLM nodes and real data tools; golden fixtures; executor against a local Anvil fork of the deployed contracts.
5. API: endpoints, SSE, scheduler workflow.
6. Web: wallet, position panel, desk panel, delegation flow.
7. Dune queries and dashboard; replay chart; README; demo video.

Human owners: approve spec and plans, review diffs, hold deployer and agent keys, deploy, record demo.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Agent key compromise | Router can only move between two allowlisted vaults with receiver = user, under user caps; role revocable; pausable. |
| LLM flakiness during demo | Cached golden run in the UI; cached model responses in CI. |
| Agents burn gas on noise | `MIN_CHANGE_BPS` threshold, per-run gas cap, cron cadence. |
| Pendle has no Sepolia deployment | Mock adapter behind `IYieldAdapter`; stated plainly in README with the v2 path. |
| Share price rounding on router moves | Use `redeem` of exact shares then `deposit` of received assets; tests assert user never loses more than 1 wei per move. |
| Scope creep toward real protocol execution | Non-goals section; the adapter interface is the agreed boundary. |

## 12. Open items to verify during planning

- GMX V2 Arbitrum Sepolia deployment status and whether its fee-APR data is available for testnet markets (affects whether `GmxAdapter` could be real instead of mock; default remains mock).
- Pendle public API endpoints and rate limits for the GM markets.
- Whether Dune decodes Arbitrum Sepolia contracts; fallback is raw-log queries.
