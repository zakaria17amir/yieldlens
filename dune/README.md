# Dune track record

Four queries over the `AgentRouter` events on Arbitrum Sepolia.

| File | Chart |
| --- | --- |
| `01_moves_per_day.sql` | Moves and USDG moved per day |
| `02_agent_vs_manual.sql` | Same, split agent vs manual (`byAgent`) |
| `03_delegations.sql` | Users with delegation enabled over time (latest `PolicySet` per user) |
| `04_target_split_vs_apr.sql` | Desk target split against fixed/floating APY, with moves overlaid |

## Parameters

- `router_address` (text): the deployed `AgentRouter` address from `contracts/deployments/arbitrum-sepolia.json`. The Sepolia deploy is a human step that has not happened yet, so the address is a Dune parameter rather than hard-coded.
- `dune_user` (text, query 04 only): the Dune account that uploaded `yieldlens_desk_history`.

## Data source finding

- Dune's documented catalog (docs.dune.com data catalog and the Sim API chain list) covers Arbitrum One and Arbitrum Nova; no documentation page for an Arbitrum Sepolia dataset was found. A public community query titled "Recent 2-Hour Arbitrum Sepolia Transactions" suggests a raw `arbitrum_sepolia` schema has existed, but the page could not be opened (HTTP 403) and availability was not verified (no Dune account was available to run `SHOW SCHEMAS`).
- Decoded tables for this router are not assumed. The queries therefore read raw logs from `arbitrum_sepolia.logs` filtered by `contract_address` and `topic0`, so no ABI submission is needed. Topic hashes were produced with:

  ```bash
  cast keccak "Moved(address,address,address,uint256,bytes32,bool)"
  # 0x72b6019c7f33fe643036d112cba2cd2c9fe32f18c5de9dfec010c3f080133a7e
  cast keccak "PolicySet(address,bool,uint16,uint32)"
  # 0xa18ace2fa02284c1307437fb279d27fc7333c25dffdade2bc433e2c3dd8569d2
  ```

- Event layout used: `Moved` topics are `[topic0, user, fromVault, toVault]` and data is `assets | reportHash | byAgent` (32-byte words; `byAgent` is read from its last byte). `PolicySet` topics are `[topic0, user]` and data is `enabled | maxMoveBps | cooldown`.
- The SQL has not been executed against Dune.
- On-chain `Moved` events carry no "simulated" flag, so moves caused by simulated-market runs are indistinguishable from others in Dune. Only the run JSON (`pendle.simulated`) records that.

### Fallback if `arbitrum_sepolia` is not available in Dune

Export the router logs and upload them as a table:

```bash
cast logs --rpc-url $ARBITRUM_SEPOLIA_RPC_URL --from-block <deployedAtBlock> --address <router> --json > router_logs.json
```

Convert to CSV with columns `block_time, block_number, index, contract_address, topic0, topic1, topic2, topic3, data` and upload as `yieldlens_router_logs`; then replace `arbitrum_sepolia.logs` in the four queries with `dune.<user>.dataset_yieldlens_router_logs`. The `from_hex`/`bytearray_*` expressions stay valid if the hex columns are uploaded as `varbinary`.

## Desk history upload (query 04)

```bash
cd agents
python replay/export_dune.py        # reads ../api/data/runs/*.json, writes replay/results/desk_history.csv
```

The CSV has one row per day (the last run of that day by `created_at`). Upload it to Dune as `yieldlens_desk_history` (`date, target_fixed_bps, implied_apy_bps, underlying_apy_bps, run_id`); query 04 ignores `run_id`. The "SIMULATED MARKET" demo mode feeds the APY columns from the expired market's history; runs are labelled in their JSON.

## Dashboard

Creating the dashboard and setting its embed URL as `VITE_DUNE_EMBED_URL` in `web/.env.example` / `web/.env` needs a Dune account and a deployed router, so it is a human step. Until then the web Track Record panel shows only the committed replay chart.
