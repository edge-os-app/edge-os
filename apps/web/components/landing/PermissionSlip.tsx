const HERO_TERMS: { label: string; value: string; strong?: boolean }[] = [
  { label: "Strategy", value: "Revision 2 · buy after a rise of more than 2% in 5 min" },
  { label: "Tokens", value: "MOE / WMON on Monad, spot on Kuru" },
  { label: "Most per trade", value: "10 WMON", strong: true },
  { label: "Total limit", value: "100 WMON", strong: true },
  { label: "Expires", value: "Oct 6, 2026 · 11:00 UTC" },
  { label: "Stops when", value: "Losses reach 6 WMON, after 4 attempts, or when you stop it" },
];

const COMPACT_TERMS: { label: string; value: string; strong?: boolean }[] = [
  { label: "Most per trade", value: "10 WMON", strong: true },
  { label: "Total limit", value: "100 WMON", strong: true },
  { label: "Expires", value: "Oct 6 · 11:00 UTC" },
  { label: "Stops at", value: "6 WMON loss · 4 tries" },
];

const POWERS = [
  { name: "Stop new trades", note: "Holdings stay" },
  { name: "Close a position", note: "Reviewed first" },
  { name: "Remove the agent’s access", note: "Funds stay yours" },
];

/** Illustrative example data only. Every slip keeps its "Illustrative" label. */
export function HeroPermissionSlip() {
  return (
    <div className="lp-slip" data-slip>
      <div className="lp-slip-head">
        <div className="lp-slip-meta">
          <span className="lp-slip-kind">Permission slip</span>
          <span>No. D-002 · Illustrative</span>
        </div>
        <p className="lp-slip-title">Agent D may trade</p>
        <p className="lp-slip-rule">Within these limits only. Checked again before every trade.</p>
      </div>
      <div className="lp-tear" aria-hidden="true" />
      <dl className="lp-terms">
        {HERO_TERMS.map((term) => (
          <div className="lp-term" key={term.label}>
            <dt>{term.label}</dt>
            <dd className={term.strong ? "lp-term-strong" : undefined}>{term.value}</dd>
          </div>
        ))}
      </dl>
      <div className="lp-slip-sign">
        <div className="lp-signature">
          <span className="lp-signature-word">you.</span>
          <span className="lp-signature-line" />
          <span className="lp-signature-note">Approved by you · Oct 5, 11:00 UTC</span>
        </div>
        <div className="lp-stamp-slot" data-stamp>
          <div className="lp-stamp" role="img" aria-label="Stamp: approved by you">
            <span className="lp-stamp-mono">EDGE OS</span>
            <span className="lp-stamp-word">Approved</span>
            <span className="lp-stamp-mono">BY YOU</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function CompactPermissionSlip() {
  return (
    <div className="lp-step-visual">
      <div className="lp-slip lp-slip-compact" role="group" aria-label="Permission slip for Agent D, illustrative example">
        <div className="lp-slip-head">
          <span className="lp-slip-title">Agent D may trade</span>
          <span className="lp-slip-meta">No. D-002 · Illustrative</span>
        </div>
        <div className="lp-tear" aria-hidden="true" />
        <dl className="lp-terms-grid">
          {COMPACT_TERMS.map((term) => (
            <div key={term.label}>
              <dt>{term.label}</dt>
              <dd className={term.strong ? "lp-term-strong" : undefined}>{term.value}</dd>
            </div>
          ))}
        </dl>
        <div className="lp-powers">
          <span className="lp-powers-label">You can, at any time</span>
          <ul className="lp-power-list">
            {POWERS.map((power) => (
              <li className="lp-power" key={power.name}><strong>{power.name}</strong><span className="lp-power-note">{power.note}</span></li>
            ))}
          </ul>
        </div>
        <div className="lp-stamp-small" aria-hidden="true">
          <span className="lp-stamp-mono">SIGNED</span>
          <span className="lp-stamp-word">by you</span>
        </div>
      </div>
      <p className="lp-caption lp-caption-small">A good report or a favorable replay never signs this slip. Only you do.</p>
    </div>
  );
}
