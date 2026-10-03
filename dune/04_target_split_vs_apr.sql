-- Desk target split against the two APRs, next to on-chain moves.
-- Parameters: {{router_address}}, {{dune_user}} (the Dune account that uploaded the CSV).
-- Upload agents/replay/results/desk_history.csv (python agents/replay/export_dune.py) as table yieldlens_desk_history:
-- columns date, target_fixed_bps, implied_apy_bps, underlying_apy_bps.
WITH moved AS (
    SELECT
        CAST(block_time AS date) AS d,
        count(*) AS moves,
        sum(bytearray_to_uint256(bytearray_substring(data, 1, 32))) / 1e6 AS usdg_moved
    FROM arbitrum_sepolia.logs
    WHERE contract_address = from_hex(substr('{{router_address}}', 3))
      AND topic0 = 0x72b6019c7f33fe643036d112cba2cd2c9fe32f18c5de9dfec010c3f080133a7e
    GROUP BY 1
)
SELECT
    CAST(h.date AS date) AS day,
    h.target_fixed_bps / 100.0 AS target_fixed_pct,
    h.implied_apy_bps / 100.0 AS fixed_apy_pct,
    h.underlying_apy_bps / 100.0 AS floating_apy_pct,
    coalesce(m.moves, 0) AS moves,
    coalesce(m.usdg_moved, 0) AS usdg_moved
FROM dune.{{dune_user}}.dataset_yieldlens_desk_history AS h
LEFT JOIN moved AS m ON m.d = CAST(h.date AS date)
ORDER BY 1
