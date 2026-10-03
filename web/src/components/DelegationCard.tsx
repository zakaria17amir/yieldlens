import { useEffect, useState } from "react";
import { abis, deployments } from "../contracts";
import { formatBps } from "../format";
import type { TxState } from "../useTx";

export interface PolicyView {
  enabled: boolean;
  maxMoveBps: number;
  cooldown: number;
  lastMove: number;
}

interface Props {
  policy: PolicyView | undefined;
  approved: boolean;
  canWrite: boolean;
  tx: TxState;
}

const MAX_UINT256 = 2n ** 256n - 1n;
const COOLDOWNS = [
  { label: "No cooldown", seconds: 0 },
  { label: "1 hour", seconds: 3600 },
  { label: "6 hours", seconds: 21600 },
  { label: "24 hours", seconds: 86400 },
];

export default function DelegationCard({ policy, approved, canWrite, tx }: Props) {
  const [enabled, setEnabled] = useState(false);
  const [percent, setPercent] = useState(25);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (!policy) return;
    setEnabled(policy.enabled);
    setPercent(Math.round(policy.maxMoveBps / 100));
    setCooldown(policy.cooldown);
  }, [policy?.enabled, policy?.maxMoveBps, policy?.cooldown]);

  const disabled = !canWrite || tx.busy !== null;

  const approveRouter = () =>
    tx.run(
      "Approve router",
      [deployments.fixedVault, deployments.floatingVault].map((vault) => ({
        address: vault,
        abi: abis.vault,
        functionName: "approve",
        args: [deployments.router, MAX_UINT256],
      })),
    );
  const save = () =>
    tx.run("Save policy", [
      {
        address: deployments.router,
        abi: abis.router,
        functionName: "setPolicy",
        args: [enabled, percent * 100, cooldown],
      },
    ]);

  return (
    <div className="card">
      <h3>Agent delegation</h3>
      <p className="muted small">
        Let the desk agent rebalance between the two vaults for you, within the limits below. You can
        revoke at any time.
      </p>
      <dl className="stats">
        <dt>On-chain policy</dt>
        <dd>
          {policy
            ? `${policy.enabled ? "enabled" : "disabled"}, max ${formatBps(policy.maxMoveBps)} per move`
            : "—"}
        </dd>
        <dt>Router share approval</dt>
        <dd>{approved ? "approved" : "not approved"}</dd>
      </dl>
      <div className="row">
        <button disabled={disabled || approved} onClick={approveRouter}>
          Approve router on both vaults
        </button>
      </div>
      <label className="check">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Allow agent moves
      </label>
      <label className="field">
        Max move per run: <span className="num">{percent}%</span>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={percent}
          onChange={(e) => setPercent(Number(e.target.value))}
        />
      </label>
      <label className="field">
        Cooldown
        <select value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))}>
          {COOLDOWNS.map((c) => (
            <option key={c.seconds} value={c.seconds}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <div className="row">
        <button disabled={disabled} onClick={save}>
          Save policy
        </button>
      </div>
    </div>
  );
}
