# YieldLens demo script (3 minutes)

Setup before recording: web app open on the Position panel with a funded test wallet (or the local anvil setup from the README), API running (`uv run uvicorn app.main:app`, or `scripts/dev_server.py --fake-runner` if no LLM key is available), desk in `--simulate-live-market` mode, Dune dashboard and Arbiscan tabs ready.

| Time | Beat | Say / show |
| --- | --- | --- |
| 0:00 | 1. The problem | "If you provide liquidity on GMX you earn a floating fee yield. Pendle will lock a fixed rate instead. Deciding when to switch is a judgement call nobody automates. YieldLens is a desk of AI agents that makes that call in the open, and acts on it only inside limits you set on-chain." |
| 0:20 | 2. Get a position | Connect wallet. Click "Mint 1,000 test USDG". Deposit 300 USDG into the Floating vault. Point at the position and the current split. |
| 0:50 | 3. Delegate with a cap | Approve the router on both vaults. In the delegation card enable agent moves, drag the cap to 25%, set a 1 hour cooldown, Save policy. "This policy is on-chain. The agent can never move more than 25% of my position per run." |
| 1:10 | 4. Convene the desk | Click "Convene desk now". Watch the node list light up. Show the two advocates' cases with their evidence chips, the Risk Officer's objections, the rebuttal round if it happened, then the verdict and target split. Say plainly: "Pendle has no live GM market today, so this run replays the last expired market and is labelled SIMULATED MARKET; the mechanics are real, the market data is a replay." |
| 1:55 | 5. The move and the audit trail | In Move history show the agent's `Moved` row (agent badge). Open the transaction on Arbiscan and show the `reportHash` in the event; show the same hash in the run's JSON / the Desk panel. "Any move can be traced to the exact transcript that justified it." |
| 2:20 | 6. Track record | Open the Dune dashboard: moves per day, agent vs manual, delegations over time. Then the replay chart; say honestly that over 90 days the desk landed between always-fixed and always-floating and that it demonstrates the mechanics, not an edge. |
| 2:45 | 7. Guardrails | One slide: "A stolen agent key can only call `moveFor` for users who opted in, between two fixed vaults, within each user's cap and cooldown, with the user as receiver. It cannot withdraw to an external address, and the admin can pause or revoke it instantly." |

Fallbacks: if the API is offline the Desk panel shows the cached run with a "Cached run (API offline)" badge; if the Sepolia deploy is not done, record against local anvil and say so.
