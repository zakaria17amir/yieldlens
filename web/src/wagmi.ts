import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { defineChain } from "viem";
import { http } from "wagmi";
import { arbitrumSepolia, useAnvil } from "./contracts";

export const anvilChain = defineChain({
  id: 31337,
  name: "Anvil (local)",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: { default: { http: ["http://127.0.0.1:8546"] } },
});

export const activeChain = useAnvil ? anvilChain : arbitrumSepolia;

export const config = getDefaultConfig({
  appName: "YieldLens",
  projectId: import.meta.env.VITE_WALLETCONNECT_PROJECT_ID || "yieldlens-dev",
  chains: [activeChain],
  transports: { [activeChain.id]: http() },
  ssr: false,
});
