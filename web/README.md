# YieldLens web

React + Vite + wagmi UI: position and delegation controls, desk transcript with live progress, move history and track record.

```bash
npm i
cp .env.example .env
npm run dev          # http://localhost:5173
npm test -- --run
npm run build
```

## Environment (`.env`)

| Variable | Purpose |
| --- | --- |
| `VITE_API_URL` | Desk API base URL (default `http://localhost:8000`) |
| `VITE_WALLETCONNECT_PROJECT_ID` | WalletConnect project id |
| `VITE_DUNE_EMBED_URL` | Dune dashboard embedded in the Track Record panel (hidden if empty) |
| `VITE_CHAIN=anvil` | Use a local Anvil chain on port 8546 instead of Arbitrum Sepolia |

Contract addresses come from `../contracts/deployments/arbitrum-sepolia.json`; until it exists the example file is used and the page shows a "contracts not deployed" banner. With `VITE_CHAIN=anvil` addresses are read from `public/deployments.anvil.json` (git-ignored; copy the JSON written by `forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8546 --broadcast`).

## Dev helpers

- `?as=0x…` (dev server only): shows that address's position read-only when no wallet is connected.
- Demo without an LLM key: in `../api` run `uv run python scripts/dev_server.py --fake-runner` and the "Convene desk now" button replays a canned run. If the API is down the Desk panel falls back to `src/golden_run.json` with a "Cached run (API offline)" badge.
