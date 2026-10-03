# Lane D — Dune, Replay Chart, Docs and Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop: on-chain events and desk decisions visible in Dune, the replay chart in the UI and README, and a README that lets a judge run everything.

**Architecture:** Saved Dune SQL in `dune/`, a CSV upload of desk decisions and APR series produced by a small export script, and documentation.

**Tech Stack:** Dune (DuneSQL), Python (export script in `agents/replay`).

**Spec:** `docs/superpowers/specs/2026-10-03-yieldlens-agentic-design.md` §8, §11. Shared interfaces: `2026-10-03-00-overview.md`.

**Depends on:** Lane A deployed to Sepolia, Lane B replay results, Lane C running.

## Global Constraints

See overview. No secrets in SQL or docs; README lists the real USDG Arbitrum One address only as a v2 note.

## Review Focus

None beyond the overview; this lane produces no executable logic with inputs from users.

---

### Task D1: Dune queries

**Files:**
- Create: `dune/README.md`, `dune/01_moves_per_day.sql`, `dune/02_agent_vs_manual.sql`, `dune/03_delegations.sql`, `dune/04_target_split_vs_apr.sql`

- [ ] **Step 1:** Check whether Dune indexes Arbitrum Sepolia (`arbitrum_sepolia` schema) and whether the router can be decoded via Dune's contract submission; record the answer in `dune/README.md`. If not indexed, queries 01–03 read raw logs by topic hash `keccak("Moved(address,address,address,uint256,bytes32,bool)")` and `keccak("PolicySet(address,bool,uint16,uint32)")`; if indexed but undecoded, submit the ABI and use the decoded tables.
- [ ] **Step 2:** Write the four queries:
  - 01: `date_trunc('day', block_time)`, count and sum of `assets/1e6` from `Moved`.
  - 02: same split by `byAgent`.
  - 03: distinct users whose latest `PolicySet.enabled = true`, over time.
  - 04: join an uploaded CSV table `yieldlens_desk_history` (`date, target_fixed_bps, implied_apy_bps, underlying_apy_bps`) with 01 to chart the desk's target split against the two APRs.
- [ ] **Step 3:** Add `agents/replay/export_dune.py`: reads `api/data/runs/*.json`, writes `replay/results/desk_history.csv` in the schema above (one row per run; APRs from each run's `pendle` snapshot). Upload to Dune as `yieldlens_desk_history`.
- [ ] **Step 4:** Create the dashboard with the four charts; put its embed URL in `web/.env.example` as `VITE_DUNE_EMBED_URL`.
- [ ] **Step 5:** Commit `feat(dune): queries and desk history export`.

---

### Task D2: Replay chart into the UI and README

**Files:**
- Copy: `agents/replay/results/replay.png` → `web/public/replay.png`, `docs/replay.png`
- Modify: `README.md`

- [ ] **Step 1:** Run `uv run python replay/replay.py --window 90 --cadence 1d` in `agents/`; copy the PNG to both locations.
- [ ] **Step 2:** README section "Does the desk beat always-fixed / always-floating?" with the chart, the exact replay command, and a one-paragraph honest caveat (mock yield accrual on Sepolia; replay uses historical Pendle series; no trading costs modelled).
- [ ] **Step 3:** Commit `docs: replay results`.

---

### Task D3: README and runbook

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Sections: What it is (one paragraph + architecture diagram from the spec §3); Judging criteria table (from spec §1); Deployed addresses (Arbitrum Sepolia, from `deployments/arbitrum-sepolia.json`) with Arbiscan links; Guardrails (what an agent key can and cannot do); How the desk works (graph picture + the honesty rules); Evals (latest `evals/results/latest.json` numbers); Run locally (contracts: `forge test`; agents: `uv sync && uv run pytest`, `uv run python -m desk.run --dry-run`; api: `uv run uvicorn app.main:app`; web: `npm i && npm run dev`); Env vars table; v2 roadmap (real adapters, Arbitrum One with USDG `0x004B506865409877C9fA29bfb1ebA929984B9bbC`, per-user agents).
- [ ] **Step 2:** A second person follows "Run locally" on a clean clone and reports any missing step; fix.
- [ ] **Step 3:** Commit `docs: README and runbook`.

---

### Task D4: Demo script and recording

**Files:**
- Create: `docs/demo-script.md`

- [ ] **Step 1:** Write the 3-minute script: (1) problem in one sentence; (2) connect wallet, mint USDG, deposit to floating; (3) enable delegation with a 25% cap; (4) "Convene desk now" — show the two advocates, the Risk Officer objection, the rebuttal, the verdict; (5) show the agent's `Moved` row in history and the same `reportHash` on Arbiscan and in the run JSON; (6) Dune track record and replay chart; (7) guardrails slide: what a stolen agent key can't do.
- [ ] **Step 2:** Record; link the video in README.
- [ ] **Step 3:** Commit `docs: demo script`.
