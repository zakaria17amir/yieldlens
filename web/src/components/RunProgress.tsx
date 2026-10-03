export const NODE_ORDER = [
  "gmx_scout",
  "pendle_scout",
  "stats",
  "fixed_advocate",
  "float_advocate",
  "risk_officer",
  "prepare_rebuttal",
  "executor",
  "reporter",
] as const;

export type NodeState = "idle" | "running" | "done";

export default function RunProgress({ states }: { states: Record<string, NodeState> }) {
  return (
    <ol className="progress">
      {NODE_ORDER.map((node) => {
        const state = states[node] ?? "idle";
        return (
          <li key={node} className={`node ${state}`}>
            <span className="dot" />
            {node.replace("_", " ")}
            <span className="muted small"> {state}</span>
          </li>
        );
      })}
    </ol>
  );
}
