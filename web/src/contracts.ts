import { arbitrumSepolia } from "viem/chains";
import type { Abi, Address } from "viem";
import exampleDeployments from "../../contracts/deployments/arbitrum-sepolia.example.json";
import usdgAbi from "../../contracts/deployments/abi/MockUSDG.json";
import vaultAbi from "../../contracts/deployments/abi/StrategyVault.json";
import routerAbi from "../../contracts/deployments/abi/AgentRouter.json";
import adapterAbi from "../../contracts/deployments/abi/MockYieldAdapter.json";

export { arbitrumSepolia };

export interface Deployments {
  chainId: number;
  deployedAtBlock: number;
  usdg: Address;
  fixedVault: Address;
  floatingVault: Address;
  fixedAdapter: Address;
  floatingAdapter: Address;
  router: Address;
}

const ZERO = "0x0000000000000000000000000000000000000000";

const realFiles = import.meta.glob("../../contracts/deployments/arbitrum-sepolia.json", {
  eager: true,
  import: "default",
}) as Record<string, Deployments>;

const anvilFiles = import.meta.glob("../public/deployments.*.json", {
  eager: true,
  import: "default",
}) as Record<string, Deployments>;

export const useAnvil = import.meta.env.VITE_CHAIN === "anvil";

function pickDeployments(): Deployments {
  if (useAnvil) {
    const name = import.meta.env.VITE_DEPLOYMENTS_JSON ?? "deployments.anvil.json";
    const match = Object.entries(anvilFiles).find(([path]) => path.endsWith(`/${name}`));
    if (match) return match[1];
  }
  return Object.values(realFiles)[0] ?? (exampleDeployments as Deployments);
}

export const deployments: Deployments = pickDeployments();

export const isDeployed = deployments.router.toLowerCase() !== ZERO;

export const abis = {
  usdg: usdgAbi as Abi,
  vault: vaultAbi as Abi,
  router: routerAbi as Abi,
  adapter: adapterAbi as Abi,
};
