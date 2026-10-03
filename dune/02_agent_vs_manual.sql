-- Same as 01, split by who initiated the move (byAgent is the last 32-byte word of the event data).
-- Parameter: {{router_address}}.
WITH moved AS (
    SELECT
        block_time,
        CAST(bytearray_to_uint256(bytearray_substring(data, 1, 32)) AS double) AS assets,
        bytearray_substring(data, 96, 1) = 0x01 AS by_agent
    FROM arbitrum_sepolia.logs
    WHERE contract_address = from_hex(substr('{{router_address}}', 3))
      AND topic0 = 0x72b6019c7f33fe643036d112cba2cd2c9fe32f18c5de9dfec010c3f080133a7e
)
SELECT
    date_trunc('day', block_time) AS day,
    CASE WHEN by_agent THEN 'agent' ELSE 'manual' END AS initiated_by,
    count(*) AS moves,
    sum(assets) / 1e6 AS usdg_moved
FROM moved
GROUP BY 1, 2
ORDER BY 1, 2
