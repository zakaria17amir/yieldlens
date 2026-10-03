/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CHAIN?: string;
  readonly VITE_DEPLOYMENTS_JSON?: string;
  readonly VITE_WALLETCONNECT_PROJECT_ID?: string;
  readonly VITE_API_URL?: string;
  readonly VITE_DUNE_EMBED_URL?: string;
}
