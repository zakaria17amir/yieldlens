import { useEffect, useState } from "react";
import { parseAbiItem } from "viem";
import type { Address } from "viem";
import { usePublicClient } from "wagmi";
import { fetchLatest } from "../api";
import { deployments, vaultName } from "../contracts";
import { formatUsdg } from "../format";

const MOVED = parseAbiItem(
  "event Moved(address indexed user, address indexed fromVault, address indexed toVault, uint256 assets, bytes32 reportHash, bool byAgent)",
);
const ZERO_HASH = `0x${"00".repeat(32)}`;
const MAX_ROWS = 25;
const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface Row {
  key: string;
  block: bigint;
  time: string;
  direction: string;
  assets: bigint;
  byAgent: boolean;
  reportHash: string;
}

export default function MoveHistory({ user, refreshKey }: { user: Address; refreshKey: number }) {
  const client = usePublicClient();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<{ hash: string | null; runId: string } | null>(null);

  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    (async () => {
      try {
        const logs = await client.getLogs({
          address: deployments.router,
          event: MOVED,
          args: { user },
          fromBlock: BigInt(deployments.deployedAtBlock),
          toBlock: "latest",
        });
        const recent = logs.slice(-MAX_ROWS).reverse();
        const blocks = [...new Set(recent.map((l) => l.blockNumber))];
        const stamps = new Map<bigint, string>();
        await Promise.all(
          blocks.map(async (n) => {
            const block = await client.getBlock({ blockNumber: n });
            stamps.set(n, new Date(Number(block.timestamp) * 1000).toLocaleString());
          }),
        );
        if (cancelled) return;
        setRows(
          recent.map((l) => ({
            key: `${l.transactionHash}-${l.logIndex}`,
            block: l.blockNumber,
            time: stamps.get(l.blockNumber) ?? `block ${l.blockNumber}`,
            direction: `${vaultName(l.args.fromVault!)} → ${vaultName(l.args.toVault!)}`,
            assets: l.args.assets!,
            byAgent: l.args.byAgent!,
            reportHash: l.args.reportHash!,
          })),
        );
        setError(null);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, user, refreshKey]);

  useEffect(() => {
    fetchLatest()
      .then((report) => report && setLatest({ hash: report.report_hash, runId: report.run_id }))
      .catch(() => setLatest(null));
  }, [refreshKey]);

  return (
    <div className="card history">
      <h3>Move history</h3>
      {error && <p className="error small">Could not load history: {error}</p>}
      {rows === null && !error && <p className="muted small">Loading…</p>}
      {rows !== null && rows.length === 0 && <p className="muted small">No moves yet.</p>}
      {rows !== null && rows.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Direction</th>
              <th>Amount</th>
              <th>By</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td>{r.time}</td>
                <td>{r.direction}</td>
                <td className="num">{formatUsdg(r.assets)}</td>
                <td>
                  <span className={`badge ${r.byAgent ? "" : "muted-badge"}`}>{r.byAgent ? "agent" : "manual"}</span>
                </td>
                <td className="num">
                  {r.reportHash === ZERO_HASH ? (
                    "—"
                  ) : latest && latest.hash === r.reportHash ? (
                    <a href={`${API_URL}/desk/latest`} target="_blank" rel="noreferrer" title={r.reportHash}>
                      {r.reportHash.slice(0, 10)}… (run {latest.runId})
                    </a>
                  ) : (
                    <span title={r.reportHash}>{r.reportHash.slice(0, 10)}…</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
