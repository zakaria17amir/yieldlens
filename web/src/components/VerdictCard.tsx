import type { DeskReport } from "../api";
import { splitLabel } from "../format";

export default function VerdictCard({ report }: { report: DeskReport }) {
  const verdict = report.verdict;
  if (!verdict) return null;
  const groups = (["fixed", "floating"] as const).map((to) => ({
    to,
    items: verdict.objections.filter((o) => o.to === to),
  }));
  return (
    <div className="card verdict">
      <h3>Risk officer verdict</h3>
      <div className="big">
        {verdict.vetoed ? "No move" : splitLabel(verdict.target_fixed_bps)}
        {verdict.vetoed && <span className="badge warn">VETOED</span>}
      </div>
      <p>{verdict.rationale}</p>
      {groups.map(
        ({ to, items }) =>
          items.length > 0 && (
            <div key={to}>
              <div className="muted small">Objections to the {to} case</div>
              <ul className="args">
                {items.map((o, i) => (
                  <li key={i}>
                    #{o.argument_idx + 1}: {o.reason}
                  </li>
                ))}
              </ul>
            </div>
          ),
      )}
      <div className="muted small">
        Rebuttal rounds: <span className="num">{report.rebuttal_round}</span>
        {report.report_hash && <> · report hash <span className="num">{report.report_hash.slice(0, 10)}…</span></>}
      </div>
      {report.errors.length > 0 && (
        <ul className="args error">
          {report.errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
