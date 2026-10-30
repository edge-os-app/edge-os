const SOURCES = ["Swaps · Envio", "Receipts · QuickNode", "Holders · Nansen"];

/** An illustration of the app's report screen with example data. It is a figure, not working UI. */
export function ReportScreen() {
  return (
    <figure className="lp-frame" aria-label="Edge OS report screen, stamped Doesn’t hold up, listing what counts in favor, what points the other way and what is missing. Illustrative example.">
      <div className="lp-screen lp-screen-report">
        <div className="lp-crumbs lp-crumbs-report">
          <span className="lp-crumb-link">Research</span><span className="lp-muted">/</span><strong>Report</strong>
          <span className="lp-pill-note">Illustrative example</span>
        </div>
        <div className="lp-report-head">
          <span className="lp-report-title">Does MOE keep rising after it pumps hard?</span>
          <span className="lp-report-scope">MOE priced in WMON on Monad. Example period Sep 1 to 21, 2026.</span>
        </div>
        <div className="lp-verdict" aria-hidden="true">Doesn’t<br />hold up</div>
        <div className="lp-findings">
          <div className="lp-finding lp-finding-favor">
            <span className="lp-finding-label">Counts in its favor</span>
            <span className="lp-finding-text">Before costs, the explore part was slightly positive (<span className="lp-mono">+0.6%</span>).</span>
          </div>
          <div className="lp-finding lp-finding-against">
            <span className="lp-finding-label">Points the other way</span>
            <span className="lp-finding-text"><span className="lp-mono">18</span> and <span className="lp-mono">9</span> rises found, <span className="lp-mono">30</span> needed. After costs: <span className="lp-mono">−0.1%</span>.</span>
          </div>
          <div className="lp-finding">
            <span className="lp-finding-label">Missing</span>
            <span className="lp-finding-text">Real trading costs and price impact. Token launch age.</span>
          </div>
        </div>
        <div className="lp-sources">
          <span className="lp-finding-label">Sources</span>
          <div className="lp-source-list">
            {SOURCES.map((source) => <span className="lp-source" key={source}>{source}</span>)}
          </div>
        </div>
      </div>
    </figure>
  );
}
