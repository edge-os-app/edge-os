export function MoeExample() {
  return (
    <section className="panel" aria-labelledby="moe-title" data-testid="moe-example">
      <span className="eyebrow">Imported example · not run by this application</span>
      <h2 id="moe-title">What happens after MOE rises in price?</h2>
      <p>
        This is a saved result copied from the project’s recorded Probe A investigation. This application did not run it and
        has no study worker. Opening it starts nothing.
      </p>
      <dl className="kv">
        <dt>Subject</dt><dd>MOE / WMON pool on Monad, research window Sep 25–30, 2026</dd>
        <dt>Variants tried</dt><dd>Four, declared before any outcome was read</dd>
        <dt>Finding</dt><dd>Every variant had too few samples (INSUFFICIENT_SAMPLE)</dd>
        <dt>Result</dt><dd>Unresolved. No supported strategy. No permission to trade.</dd>
        <dt>Source</dt><dd className="mono">docs/prototypes/EDGE_OS_PROBE_A_RESULT.md</dd>
      </dl>
    </section>
  );
}
