import { useReadContracts } from "wagmi";
import { parseUnits } from "viem";
import { abis, deployments, isDeployed } from "../contracts";
import { formatUsdg, splitLabel } from "../format";
import { useTx } from "../useTx";
import { useViewer } from "../viewer";
import DelegationCard from "./DelegationCard";
import type { PolicyView } from "./DelegationCard";
import VaultCard from "./VaultCard";

const FAUCET_AMOUNT = parseUnits("1000", 6);

export default function PositionPanel() {
  const { address: user, readOnly } = useViewer();
  const { router, usdg, fixedVault, floatingVault, fixedAdapter, floatingAdapter } = deployments;
  const owner = user ?? "0x0000000000000000000000000000000000000000";

  const { data, refetch } = useReadContracts({
    allowFailure: true,
    query: { enabled: isDeployed && user !== undefined, refetchInterval: 15_000 },
    contracts: [
      { address: usdg, abi: abis.usdg, functionName: "balanceOf", args: [owner] },
      { address: fixedVault, abi: abis.vault, functionName: "balanceOf", args: [owner] },
      { address: floatingVault, abi: abis.vault, functionName: "balanceOf", args: [owner] },
      { address: router, abi: abis.router, functionName: "assetsOf", args: [owner, fixedVault] },
      { address: router, abi: abis.router, functionName: "assetsOf", args: [owner, floatingVault] },
      { address: router, abi: abis.router, functionName: "policies", args: [owner] },
      { address: fixedVault, abi: abis.vault, functionName: "allowance", args: [owner, router] },
      { address: floatingVault, abi: abis.vault, functionName: "allowance", args: [owner, router] },
      { address: fixedAdapter, abi: abis.adapter, functionName: "aprBps" },
      { address: floatingAdapter, abi: abis.adapter, functionName: "aprBps" },
    ],
  });

  const tx = useTx(() => void refetch());
  const canWrite = isDeployed && !readOnly && user !== undefined;

  const big = (i: number) => (data?.[i]?.result as bigint | undefined) ?? 0n;
  const walletUsdg = big(0);
  const fixedShares = big(1);
  const floatingShares = big(2);
  const fixedAssets = big(3);
  const floatingAssets = big(4);
  const policyTuple = data?.[5]?.result as readonly [boolean, number, number, bigint] | undefined;
  const policy: PolicyView | undefined = policyTuple && {
    enabled: policyTuple[0],
    maxMoveBps: Number(policyTuple[1]),
    cooldown: Number(policyTuple[2]),
    lastMove: Number(policyTuple[3]),
  };
  const approvedFor = (allowance: bigint, shares: bigint) => allowance > 0n && allowance >= shares;
  const approved = approvedFor(big(6), fixedShares) && approvedFor(big(7), floatingShares);
  const apr = (i: number) => {
    const value = data?.[i]?.result as bigint | undefined;
    return value === undefined ? undefined : Number(value);
  };

  const total = fixedAssets + floatingAssets;
  const fixedBps = total === 0n ? 0 : Number((fixedAssets * 10_000n) / total);

  const faucet = () =>
    tx.run("Mint test USDG", [
      { address: usdg, abi: abis.usdg, functionName: "mint", args: [user!, FAUCET_AMOUNT] },
    ]);

  return (
    <section className="panel">
      <h2>Your position</h2>
      {user === undefined ? (
        <p className="muted">Connect a wallet to see and manage your position.</p>
      ) : (
        <>
          {readOnly && <p className="muted small">Viewing {user} read-only (dev).</p>}
          <div className="summary">
            <div>
              <div className="muted small">Total in vaults</div>
              <div className="big num">{formatUsdg(total)} USDG</div>
            </div>
            <div>
              <div className="muted small">Current split</div>
              <div className="big">{total === 0n ? "—" : splitLabel(fixedBps)}</div>
            </div>
            <div>
              <button disabled={!canWrite || tx.busy !== null} onClick={faucet}>
                Mint 1,000 test USDG
              </button>
            </div>
          </div>
          {tx.busy && <p className="status">{tx.busy}… confirm in your wallet</p>}
          {tx.error && <p className="error">{tx.error}</p>}
          <div className="grid">
            <VaultCard
              title="Fixed vault"
              vault={fixedVault}
              other={floatingVault}
              otherTitle="Floating"
              user={user}
              aprBps={apr(8)}
              assets={fixedAssets}
              wallet={walletUsdg}
              canWrite={canWrite}
              tx={tx}
            />
            <VaultCard
              title="Floating vault"
              vault={floatingVault}
              other={fixedVault}
              otherTitle="Fixed"
              user={user}
              aprBps={apr(9)}
              assets={floatingAssets}
              wallet={walletUsdg}
              canWrite={canWrite}
              tx={tx}
            />
            <DelegationCard policy={policy} approved={approved} canWrite={canWrite} tx={tx} />
          </div>
        </>
      )}
    </section>
  );
}
