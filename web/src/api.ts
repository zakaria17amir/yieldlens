export interface AprByPeriod {
  "1d"?: number | null;
  "7d"?: number | null;
  "30d"?: number | null;
  "90d"?: number | null;
}

export interface MarketSnapshot {
  market: string;
  current_apr_bps: number;
  apr_by_period: AprByPeriod;
  fetched_at: string;
  stale: boolean;
}

export interface PendleSnapshot {
  market: string;
  address: string;
  implied_apy_bps: number;
  underlying_apy_bps: number;
  expiry: string;
  liquidity_usd: number;
  fetched_at: string;
  stale: boolean;
  expired_fallback: boolean;
  simulated: boolean;
  data_age_hours: number;
  history: { ts: string; implied_apy_bps: number; underlying_apy_bps: number }[];
}

export interface Stats {
  days: number;
  pct_days_float_beat_fixed: number;
  current_gap_bps: number;
  breakeven_apr_bps: number;
  trend_30d: "up" | "down" | "flat";
}

export interface Argument {
  claim: string;
  evidence_field: string;
}

export interface Case {
  position: "fixed" | "floating";
  confidence: number;
  arguments: Argument[];
}

export interface Objection {
  to: "fixed" | "floating";
  argument_idx: number;
  reason: string;
}

export interface Verdict {
  target_fixed_bps: number;
  vetoed: boolean;
  rationale: string;
  objections: Objection[];
  needs_rebuttal: boolean;
}

export interface Move {
  user: string;
  from_vault: string;
  to_vault: string;
  assets: number;
  tx_hash: string | null;
}

export type SkipReason =
  | "policy_disabled"
  | "cooldown"
  | "no_balance"
  | "no_allowance"
  | "below_min"
  | "tx_failed"
  | "gas_cap";

export interface ExecutionReport {
  moves: Move[];
  skipped: { user: string; reason: SkipReason }[];
  gas_used: number;
}

export interface DeskReport {
  run_id: string;
  created_at: string;
  gmx: MarketSnapshot | null;
  pendle: PendleSnapshot | null;
  stats: Stats | null;
  fixed_case: Case | null;
  float_case: Case | null;
  verdict: Verdict | null;
  rebuttal_round: number;
  report_hash: string | null;
  execution: ExecutionReport | null;
  errors: string[];
  dry_run: boolean;
}

export type DeskEventType = "node_start" | "node_end" | "done" | "error";

export interface DeskEvent {
  type: DeskEventType;
  run_id: string;
  node?: string;
  phase?: "start" | "end";
  message?: string;
}

const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchLatest(): Promise<DeskReport | null> {
  const response = await fetch(`${API_URL}/desk/latest`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`GET /desk/latest failed: ${response.status}`);
  return (await response.json()) as DeskReport;
}

export async function startRun(): Promise<{ run_id: string } | { error: "run_active" }> {
  const response = await fetch(`${API_URL}/desk/run`, { method: "POST" });
  if (response.status === 409) return { error: "run_active" };
  if (!response.ok) throw new Error(`POST /desk/run failed: ${response.status}`);
  return (await response.json()) as { run_id: string };
}

const EVENT_TYPES: DeskEventType[] = ["node_start", "node_end", "done", "error"];

export function subscribeRun(runId: string, onEvent: (e: DeskEvent) => void): () => void {
  const source = new EventSource(`${API_URL}/desk/runs/${runId}/events`);
  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (raw) => {
      const data = (raw as MessageEvent).data;
      if (typeof data !== "string") {
        onEvent({ type: "error", run_id: runId, message: "connection lost" });
        source.close();
        return;
      }
      onEvent({ ...JSON.parse(data), type });
      if (type === "done" || type === "error") source.close();
    });
  }
  return () => source.close();
}
