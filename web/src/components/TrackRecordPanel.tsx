const duneUrl: string | undefined = import.meta.env.VITE_DUNE_EMBED_URL || undefined;

export default function TrackRecordPanel() {
  return (
    <section className="panel">
      <h2>Track record</h2>
      {duneUrl && <iframe className="dune" src={duneUrl} title="Dune dashboard" loading="lazy" />}
      <p className="muted small">
        Historical replay: the desk's fix-or-float split against always-fixed and always-floating, on
        recorded Pendle history.
      </p>
      <img className="replay" src="/replay.png" alt="Replay: desk vs always fixed vs always floating" />
    </section>
  );
}
