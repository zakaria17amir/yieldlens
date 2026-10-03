-- Moves per day through the AgentRouter (all users, agent and manual).
-- Parameter: {{router_address}} (text, e.g. 0xabc...). Moved topic0 = keccak("Moved(address,address,address,uint256,bytes32,bool)").
WITH moved AS (
    SELECT
        block_time,
        bytearray_to_uint256(bytearray_substring(data, 1, 32)) AS assets
    FROM arbitrum_sepolia.logs
    WHERE contract_address = from_hex(substr('{{router_address}}', 3))
      AND topic0 = 0x72b6019c7f33fe643036d112cba2cd2c9fe32f18c5de9dfec010c3f080133a7e
)
SELECT
    date_trunc('day', block_time) AS day,
    count(*) AS moves,
    sum(assets) / 1e6 AS usdg_moved
FROM moved
GROUP BY 1
ORDER BY 1
