-- Users with delegation enabled over time: a user counts on a day if their latest PolicySet up to that day has enabled = true.
-- Parameter: {{router_address}}. PolicySet topic0 = keccak("PolicySet(address,bool,uint16,uint32)").
WITH events AS (
    SELECT
        CAST(block_time AS date) AS d,
        bytearray_substring(topic1, 13, 20) AS usr,
        bytearray_substring(data, 32, 1) = 0x01 AS enabled,
        block_number,
        index AS log_index
    FROM arbitrum_sepolia.logs
    WHERE contract_address = from_hex(substr('{{router_address}}', 3))
      AND topic0 = 0xa18ace2fa02284c1307437fb279d27fc7333c25dffdade2bc433e2c3dd8569d2
),
last_per_day AS (
    SELECT d, usr, enabled,
           row_number() OVER (PARTITION BY usr, d ORDER BY block_number DESC, log_index DESC) AS rn
    FROM events
),
state_changes AS (
    SELECT d, usr, enabled FROM last_per_day WHERE rn = 1
),
days AS (
    SELECT day AS d
    FROM UNNEST(sequence((SELECT min(d) FROM events), current_date, INTERVAL '1' DAY)) AS t(day)
),
latest AS (
    SELECT days.d, s.usr, s.enabled,
           row_number() OVER (PARTITION BY days.d, s.usr ORDER BY s.d DESC) AS rn
    FROM days
    JOIN state_changes s ON s.d <= days.d
)
SELECT d AS day, count(*) FILTER (WHERE enabled) AS delegated_users
FROM latest
WHERE rn = 1
GROUP BY d
ORDER BY d
