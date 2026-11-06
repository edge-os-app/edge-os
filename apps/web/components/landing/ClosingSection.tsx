export function ClosingSection() {
  return (
    <section className="lp-closing" aria-labelledby="close-title">
      <div className="lp-closing-card" data-reveal>
        <h2 id="close-title" className="lp-closing-title">An edge needs a reason, not a lucky chart.</h2>
        <div className="lp-btn-row">
          <a className="lp-btn lp-btn-primary" href="/app">Enter app</a>
          <a className="lp-btn lp-btn-secondary" href="https://github.com/edge-os-app/edge-os" target="_blank" rel="noopener">View the code</a>
        </div>
      </div>
    </section>
  );
}
