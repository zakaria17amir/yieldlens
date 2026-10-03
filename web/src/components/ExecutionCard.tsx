import type { ExecutionReport } from "../api";
import { vaultName } from "../contracts";
import { formatUsdg, shortAddr } from "../format";
import { activeChain } from "../wagmi";

const explorerUrl = activeChain.blockExplorers?.default.url;

export default function ExecutionCard({
  execution,
  dryRun,
}: {
  execution: ExecutionReport | null;
  dryRun: boolean;
}) {
  if (execution === null) {
    return (
      <div className="card">
        <h3>Execution</h3>
        <p className="muted small">Not executed (run ended before the executor).</p>
      </div>
    );
  }
  const reasons = execution.skipped.reduce<Record<string, number>>((acc, s) => {
    acc[s.reason] = (acc[s.reason] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <div className="card">
      <h3>Execution</h3>
      {dryRun && <p className="muted small">Dry run: no transactions were sent.</p>}
      {execution.moves.length === 0 ? (
        <p className="muted small">No moves.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>User</th>
              <th>Direction</th>
              <th>Amount</th>
              <th>Tx</th>
            </tr>
          </thead>
          <tbody>
            {execution.moves.map((m, i) => (
              <tr key={i}>
                <td className="num">{shortAddr(m.user)}</td>
                <td>
                  {vaultName(m.from_vault)} → {vaultName(m.to_vault)}
                </td>
                <td className="num">{formatUsdg(BigInt(m.assets))}</td>
                <td className="num">
                  {m.tx_hash && explorerUrl ? (
                    <a href={`${explorerUrl}/tx/${m.tx_hash}`} target="_blank" rel="noreferrer">
                      {shortAddr(m.tx_hash)}
                    </a>
                  ) : (
                    (m.tx_hash && shortAddr(m.tx_hash)) ?? "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {execution.skipped.length > 0 && (
        <p className="muted small">
          Skipped {execution.skipped.length}:{" "}
          {Object.entries(reasons)
            .map(([reason, n]) => `${n} ${reason}`)
            .join(", ")}
        </p>
      )}
    </div>
  );
}
