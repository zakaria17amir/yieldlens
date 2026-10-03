# YieldLens v2 — autonomous fix-or-float desk on Arbitrum

GMX liquidity providers face one recurring decision: keep floating fee yield on GMX, or lock a fixed rate on Pendle. YieldLens v2 is a team of AI agents that makes that decision continuously, argues it out in the open, and executes it on Arbitrum for users who opt in, inside limits those users set on-chain.

Spec: [docs/superpowers/specs/2026-10-03-yieldlens-agentic-design.md](docs/superpowers/specs/2026-10-03-yieldlens-agentic-design.md)

| Lane | Folder | Plan |
| --- | --- | --- |
| A — contracts | `contracts/` | [lane-a-contracts](docs/superpowers/plans/2026-10-03-lane-a-contracts.md) |
| B — agents | `agents/` | [lane-b-agents](docs/superpowers/plans/2026-10-03-lane-b-agents.md) |
| C — api + web | `api/`, `web/` | [lane-c-api-web](docs/superpowers/plans/2026-10-03-lane-c-api-web.md) |
| D — dune + docs | `dune/`, `docs/` | [lane-d-dune-docs](docs/superpowers/plans/2026-10-03-lane-d-dune-docs.md) |

## Deploy to Arbitrum Sepolia

Human step; needs a funded deployer key on Arbitrum Sepolia (chainId 421614).

```bash
cd contracts
export ARBITRUM_SEPOLIA_RPC_URL=...      # RPC endpoint
export DEPLOYER_PRIVATE_KEY=0x...        # deployer / vault owner / router admin
export AGENT_ADDRESS=0x...               # address of the agent key (gets AGENT_ROLE)
export ETHERSCAN_API_KEY=...         # Etherscan V2 key (also valid for Arbiscan)
forge script script/Deploy.s.sol --rpc-url arbitrum_sepolia --broadcast \n  --verify --verifier etherscan --etherscan-api-key $ETHERSCAN_API_KEY --chain 421614
# fallback (legacy Arbiscan API): --verify --etherscan-api-key $ARBISCAN_API_KEY --verifier-url https://api-sepolia.arbiscan.io/api
./export-abis.sh
```

The script writes `contracts/deployments/arbitrum-sepolia.json` (commit it). ABIs live in `contracts/deployments/abi/`; `arbitrum-sepolia.example.json` shows the shape with zero addresses.

**Trust model.** The router admin is trusted: it can pause, grant and revoke the agent role, and set the vault pair exactly once (migration means deploying a new router). Use a multisig as admin in production. The agent key can only move opted-in users between the two configured vaults, within each user's cap and cooldown, and the user is always the receiver. `MockUSDG` and `MockYieldAdapter` are testnet-only: the mock token is an unrestricted faucet with a per-call mint cap.

**Migration.** The vault pair is set once per router. To migrate, deploy a new router, pause the old one, and have users revoke their vault-share approvals on the old router.

| Contract | Address |
| --- | --- |
| MockUSDG | pending deploy |
| Fixed vault (ylFIX) | pending deploy |
| Floating vault (ylFLT) | pending deploy |
| Fixed adapter | pending deploy |
| Floating adapter | pending deploy |
| AgentRouter | pending deploy |
