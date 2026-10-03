# YieldLens — GMX × Pendle Fix-or-Float Advisor

> **Superseded (2026-10-03):** v1 advisory-only plan. The current design is the autonomous multi-agent desk in `docs/superpowers/specs/2026-10-03-yieldlens-agentic-design.md`. Kept for the problem research and judging-criteria rationale.

**Arbitrum Open House Singapore Buildathon** | General track, built on Arbitrum Sepolia
**Team:** 2 people, both new to web3 | **Timeline:** 2 weeks (buffer built in before the Oct 4 deadline)

---

## One-liner

GMX liquidity providers can see, in one place, whether locking their yield on Pendle right now beats staying on GMX's floating fee APR — and act on that decision through a minimal, audited-standard on-chain vault on Arbitrum.

---

## The problem

GMX's GM/GLP tokens are directly supported as yield-bearing assets on Pendle, which lets any GMX liquidity provider tokenize their yield into a fixed-rate Principal Token (PT) or a floating-rate Yield Token (YT). This integration is real and live — but no existing tool helps a GMX LP actually decide whether to use it.

- GMX-only analytics (dashboards, backtests, ROI predictors) stop at GMX's own fee/APR metrics and don't touch Pendle at all.
- Pendle's own app shows the current implied-vs-underlying APY for a market, but with no protocol-specific trend context (e.g., *why* is GMX's underlying yield moving the way it is).
- Generic Dune dashboards for GMX/Arbitrum activity are descriptive, not decision-oriented.

The two data sources — GMX's floating fee APR and Pendle's fixed/implied yield curve — live in separate mental models with nothing connecting them into a single recommendation. That's the gap.

**No direct competitor was found for this specific comparison during initial research — this is treated as a real gap, not proven demand. Worth a quick sanity check with anyone at the hackathon who's actually used GMX or Pendle before committing fully.**

---

## Target user

GMX GM/GLP liquidity providers who are aware Pendle exists but don't have a clear, data-backed signal on whether tokenizing their yield is currently a good trade.

---

## Core value proposition

One view that shows:
1. Your current floating APR on GMX (GM/GLP)
2. The fixed rate you could lock in right now via Pendle
3. A plain-language verdict based on recent history ("floating has beaten fixed in 8 of the last 10 weeks")
4. A way to act on that decision on-chain, through a simple vault

---

## MVP scope (frozen — build this, nothing more, for the 2-week version)

### Off-chain: data + decision layer (this is the actual differentiator)
- Pull historical GMX GM/GLP fee-APR data (GMX public API, or Dune)
- Pull current Pendle PT/YT implied-APY vs. underlying-APY for the matching GMX markets (Pendle public API)
- Compute a simple signal: "floating has beaten fixed X% of the last N days," plus the current gap between the two
- A plain-language verdict line — no ML model needed for the MVP

### On-chain: Arbitrum Sepolia
- An ERC-4626 vault, extending OpenZeppelin's audited base rather than writing custom deposit/withdraw accounting from scratch — this directly serves the "minimal security vulnerabilities" judging criterion
- Two functions beyond the ERC-4626 standard: `commitFixed()` / `commitFloating()` — records the user's choice as an on-chain event
- The vault does **not** execute real GMX/Pendle trades itself — it records intent, it doesn't move funds between protocols. That's the deliberate scope cut that keeps this feasible in 2 weeks.

### Frontend
- Wallet connect (wagmi / RainbowKit)
- One screen: the off-chain verdict displayed next to a deposit/commit button that calls the vault
- A Dune dashboard tab querying your own contract's emitted events alongside GMX/Pendle data — closes the loop (consuming *and* feeding Dune), which is a strong demo beat

### Explicitly out of scope for the MVP (v2 ideas, don't build these now)
- Auto-rebalancing or automated execution of the fix/float decision
- Keeper bots
- Support for assets beyond GMX/Pendle
- Any predictive ML model (the plain-language verdict from historical stats is enough)

---

## Why this satisfies the judging criteria

| Criterion | How YieldLens addresses it |
|---|---|
| **Smart contract quality** | ERC-4626 base (audited, standard) instead of custom accounting logic — minimizes the surface area for beginner security mistakes |
| **Product-market fit** | Real GMX LPs face this exact fixed-vs-floating decision today; the tool answers a question people already have to make |
| **Innovation and creativity** | The GMX × Pendle intersection is a real, live integration that (per initial research) nobody has built a decision layer on top of |
| **Real problem solving** | Directly reduces the friction of comparing two different yield models across two protocols |
| **Deployment requirement** | Deployed on Arbitrum Sepolia — satisfies "must be deployed on an Arbitrum chain" |

Also relevant: the buildathon reserves at least 1 of 3 prizes for a project on Arbitrum itself (not only Robinhood Chain) — this project targets that lane deliberately, given the team's web3 experience level and the 2-week timeline.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Contracts | Solidity + OpenZeppelin ERC-4626, Foundry | Foundry iterates faster than Hardhat for a tight timeline; ERC-4626 avoids custom accounting risk |
| Chain | Arbitrum Sepolia | Testnet — no real-money risk while both of you are still learning |
| Data pipeline | Python, GMX public API + Pendle public API | Plays to existing data/automation experience |
| Data / dashboard | Dune | Hackathon sponsor tool; queries your own contract events + GMX/Pendle data |
| Frontend | React + wagmi + RainbowKit | Standard, well-documented wallet-connect stack |
| Backend | Skip unless needed — a static JSON refreshed by the pipeline script is enough for a hackathon MVP; add FastAPI only if the frontend genuinely needs a live endpoint | Don't build infrastructure the demo doesn't require |

---

## Two-week plan

| Days | Work | Owner |
|---|---|---|
| 1–2 | Learn GMX fee-APR mechanics and Pendle's PT/YT/implied-APY model well enough to explain to each other out loud. In parallel, contract-owner starts the OpenZeppelin ERC-4626 quickstart + Foundry basics. | Both / split |
| 3–5 | Off-chain data pipeline: pull and align GMX + Pendle data by matching underlying asset | Data owner |
| 6–9 | Vault contract: extend ERC-4626, write tests, deploy to Arbitrum Sepolia. Don't cut this short — contract quality is a scored criterion. | Contract owner |
| 10–12 | Frontend: wire wallet connect, verdict display, vault calls together | Both |
| 13–14 | Dune dashboard, polish, record demo video, buffer time | Both |

---

## Key risks

- **Getting the yield comparison math right is the hard part, not the plumbing.** Budget real time in days 1–2 to understand both yield models correctly before writing code that compares them.
- **No proven demand yet** — the gap is evidence-based (the integration exists, no tool connects the two sides of it) but not user-validated. A quick conversation with a real GMX/Pendle user during the buildathon would de-risk this.
- **Pendle's supported-asset list can change** — confirm GMX's GM/GLP tokens are still listed as supported Pendle assets before building further; this is the load-bearing assumption for the whole idea.
- **Scope creep on the contract side** — the temptation will be to make the vault actually execute trades. Resist it; the MVP records intent, it doesn't move funds.

---

## First concrete action

Both of you spend an hour today on: (1) Pendle's docs on GLP/GM as a supported asset, and (2) GMX's fee/APR mechanics. Confirm the exact underlying assets Pendle currently lists for GMX before committing further — the whole idea depends on that pairing still being live. Then split ownership: one of you starts the ERC-4626/Foundry quickstart tonight, the other starts pulling GMX + Pendle data into a notebook to sanity-check that the fix-vs-float signal actually shows something interesting on real historical data. If the signal is flat or boring, better to know on day 1 than day 10.
