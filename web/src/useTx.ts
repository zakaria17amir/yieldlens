import { useState } from "react";
import { useConfig, useWriteContract } from "wagmi";
import { waitForTransactionReceipt } from "wagmi/actions";
import type { Abi, Address } from "viem";

export interface WriteCall {
  address: Address;
  abi: Abi;
  functionName: string;
  args: readonly unknown[];
}

export interface TxState {
  busy: string | null;
  error: string | null;
  run: (label: string, calls: WriteCall[]) => Promise<void>;
}

export function useTx(onDone: () => void): TxState {
  const config = useConfig();
  const { writeContractAsync } = useWriteContract();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(label: string, calls: WriteCall[]) {
    setBusy(label);
    setError(null);
    try {
      for (const call of calls) {
        const hash = await writeContractAsync(call as Parameters<typeof writeContractAsync>[0]);
        await waitForTransactionReceipt(config, { hash });
      }
    } catch (e) {
      setError((e as { shortMessage?: string; message: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(null);
      onDone();
    }
  }

  return { busy, error, run };
}
