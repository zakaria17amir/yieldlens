import type { Case } from "../api";

export default function CaseCard({ title, data }: { title: string; data: Case | null }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {data === null ? (
        <p className="muted small">No case (run ended before the debate).</p>
      ) : (
        <>
          <div className="muted small">
            {data.position} · confidence <span className="num">{Math.round(data.confidence * 100)}%</span>
          </div>
          <div className="bar" aria-label="confidence">
            <div className="bar-fill" style={{ width: `${data.confidence * 100}%` }} />
          </div>
          <ul className="args">
            {data.arguments.map((arg, i) => (
              <li key={i}>
                {arg.claim}
                <span className="chip">{arg.evidence_field}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
