import { useAccount } from "wagmi";
import { isAddress } from "viem";
import type { Address } from "viem";

export interface Viewer {
  address: Address | undefined;
  readOnly: boolean;
}

// Dev-only: `?as=0x...` shows a read-only position when no wallet is connected.
function devViewingAddress(): Address | undefined {
  if (!import.meta.env.DEV) return undefined;
  const value = new URLSearchParams(window.location.search).get("as");
  return value && isAddress(value) ? value : undefined;
}

export function useViewer(): Viewer {
  const { address } = useAccount();
  if (address) return { address, readOnly: false };
  const viewing = devViewingAddress();
  return { address: viewing, readOnly: viewing !== undefined };
}
