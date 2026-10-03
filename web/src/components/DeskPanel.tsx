import { useCallback, useEffect, useRef, useState } from "react";
import { fetchLatest, startRun, subscribeRun } from "../api";
import type { DeskEvent, DeskReport } from "../api";
import goldenRun from "../golden_run.json";
import CaseCard from "./CaseCard";
import ExecutionCard from "./ExecutionCard";
import RunProgress from "./RunProgress";
import type { NodeState } from "./RunProgress";
import VerdictCard from "./VerdictCard";

type Source = "live" | "cached" | "none";

function Badges({ report }: { report: DeskReport }) {
  return (
    <div className="badges">
      {report.pendle?.simulated && <span className="badge warn">SIMULATED MARKET</span>}
      {report.dry_run && <span className="badge">DRY RUN</span>}
      {report.verdict?.vetoed && <span className="badge warn">VETOED</span>}
      {report.pendle?.expired_fallback && <span className="badge warn">EXPIRED MARKET</span>}
    </div>
  );
}

export default function DeskPanel() {
  const [report, setReport] = useState<DeskReport | null>(null);
  const [source, setSource] = useState<Source>("none");
  const [states, setStates] = useState<Record<string, NodeState>>({});
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const unsubscribe = useRef<(() => void) | null>(null);

  const load = useCallback(async () => {
    try {
      const latest = await fetchLatest();
      setReport(latest);
      setSource(latest ? "live" : "none");
    } catch {
      setReport((current) => current ?? (goldenRun as unknown as DeskReport));
      setSource("cached");
    }
  }, []);

  useEffect(() => {
    void load();
    return () => unsubscribe.current?.();
  }, [load]);

  function onEvent(event: DeskEvent) {
    if (event.node && event.type === "node_start") {
      setStates((s) => ({ ...s, [event.node!]: "running" }));
    } else if (event.node && event.type === "node_end") {
      setStates((s) => ({ ...s, [event.node!]: "done" }));
    } else if (event.type === "done") {
      setRunning(false);
      void load();
    } else if (event.type === "error") {
      setRunning(false);
      setMessage(`Run failed: ${event.message ?? "unknown error"}`);
    }
  }

  async function convene() {
    setMessage(null);
    try {
      const result = await startRun();
      if ("error" in result) {
        setMessage("A run is already in progress");
        return;
      }
      setStates({});
      setRunning(true);
      unsubscribe.current?.();
      unsubscribe.current = subscribeRun(result.run_id, onEvent);
    } catch {
      setMessage("Could not reach the desk API");
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Desk</h2>
        {source === "cached" && <span className="badge warn">Cached run (API offline)</span>}
        <div className="spacer" />
        <button disabled={running} onClick={convene}>
          {running ? "Desk in session…" : "Convene desk now"}
        </button>
      </div>
      {message && <p className="status">{message}</p>}
      {(running || Object.keys(states).length > 0) && <RunProgress states={states} />}
      {report === null ? (
        <p className="muted">No desk runs yet. Convene the desk to produce the first verdict.</p>
      ) : (
        <>
          <div className="muted small">
            Run <span className="num">{report.run_id}</span> · {new Date(report.created_at).toUTCString()}
          </div>
          <Badges report={report} />
          {report.stats && (
            <p className="small">
              Floating beat fixed on <span className="num">{report.stats.pct_days_float_beat_fixed.toFixed(1)}%</span>{" "}
              of {report.stats.days} days · gap <span className="num">{report.stats.current_gap_bps} bps</span> · trend{" "}
              {report.stats.trend_30d}
            </p>
          )}
          <div className="grid">
            <CaseCard title="Fixed advocate" data={report.fixed_case} />
            <CaseCard title="Floating advocate" data={report.float_case} />
            <VerdictCard report={report} />
            <ExecutionCard execution={report.execution} dryRun={report.dry_run} />
          </div>
        </>
      )}
    </section>
  );
}
