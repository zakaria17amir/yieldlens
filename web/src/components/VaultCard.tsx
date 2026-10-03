import { useState } from "react";
import { parseUnits } from "viem";
import type { Address } from "viem";
import { abis, deployments } from "../contracts";
import { formatBps, formatUsdg, shortAddr } from "../format";
import type { TxState } from "../useTx";

interface Props {
  title: string;
  vault: Address;
  other: Address;
  otherTitle: string;
  user: Address | undefined;
  aprBps: number | undefined;
  assets: bigint;
  wallet: bigint;
  canWrite: boolean;
  approved: boolean;
  tx: TxState;
}

const NO_REPORT = `0x${"00".repeat(32)}` as const;

function parseAmount(text: string): bigint | null {
  try {
    const value = parseUnits(text, 6);
    return value > 0n ? value : null;
  } catch {
    return null;
  }
}

export default function VaultCard({
  title,
  vault,
  other,
  otherTitle,
  user,
  aprBps,
  assets,
  wallet,
  canWrite,
  approved,
  tx,
}: Props) {
  const [amount, setAmount] = useState("10");
  const parsed = parseAmount(amount);
  const disabled = !canWrite || parsed === null || tx.busy !== null || !user;

  const deposit = () =>
    tx.run(`Deposit to ${title}`, [
      { address: deployments.usdg, abi: abis.usdg, functionName: "approve", args: [vault, parsed!] },
      { address: vault, abi: abis.vault, functionName: "deposit", args: [parsed!, user!] },
    ]);
  const withdraw = () =>
    tx.run(`Withdraw from ${title}`, [
      { address: vault, abi: abis.vault, functionName: "withdraw", args: [parsed!, user!, user!] },
    ]);
  const move = () =>
    tx.run(`Move to ${otherTitle}`, [
      {
        address: deployments.router,
        abi: abis.router,
        functionName: "moveSelf",
        args: [vault, other, parsed!, NO_REPORT],
      },
    ]);

  return (
    <div className="card">
      <h3>{title}</h3>
      <div className="muted small">
        {shortAddr(vault)}
        {aprBps !== undefined && <> · simulated APR {formatBps(aprBps)}</>}
      </div>
      <dl className="stats">
        <dt>Your position</dt>
        <dd className="num">{formatUsdg(assets)} USDG</dd>
        <dt>Wallet USDG</dt>
        <dd className="num">{formatUsdg(wallet)}</dd>
      </dl>
      <label className="field">
        Amount (USDG)
        <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" />
      </label>
      <div className="row">
        <button disabled={disabled || wallet < (parsed ?? 0n)} onClick={deposit}>
          Deposit
        </button>
        <button disabled={disabled || assets < (parsed ?? 0n)} onClick={withdraw}>
          Withdraw
        </button>
        <button disabled={disabled || !approved || assets < (parsed ?? 0n)} onClick={move}>
          Move → {otherTitle}
        </button>
        {!approved && <span className="muted small">Approve the router first</span>}
      </div>
    </div>
  );
}
