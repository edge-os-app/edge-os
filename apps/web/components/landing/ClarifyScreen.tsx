/** An illustration of the app's clarify screen. It is a figure, not working UI. */
export function ClarifyScreen() {
  return (
    <figure className="lp-frame" aria-label="Edge OS clarify screen: the request in your words, and one question about what pumps hard means">
      <div className="lp-screen">
        <div className="lp-crumbs">
          <span><span className="lp-crumb-link">Research</span> <span className="lp-muted">/</span> <strong>Draft · trading idea</strong></span>
          <span className="lp-muted">Nothing adopted yet</span>
        </div>
        <div className="lp-quote">
          <span className="lp-quote-label">Your words, kept exactly</span>
          <span className="lp-quote-text">“Buy MOE when it pumps hard on big volume. Never more than 20 WMON a trade, and skip anything that launched less than a week ago.”</span>
        </div>
        <div className="lp-question">
          <span className="lp-pill">Missing meaning</span>
          <span className="lp-question-title">What counts as “pumps hard”?</span>
          <span className="lp-question-why">Your request doesn’t give a size or a time window. Pick a suggestion or write your own. Nothing is adopted until you choose.</span>
          <div className="lp-options">
            <span className="lp-option"><span className="lp-radio" aria-hidden="true" /><span>A rise of more than <span className="lp-mono">2%</span> within <span className="lp-mono">5</span> minutes</span></span>
            <span className="lp-option"><span className="lp-radio" aria-hidden="true" /><span>A rise of more than <span className="lp-mono">5%</span> within <span className="lp-mono">15</span> minutes</span></span>
            <span className="lp-option lp-option-chosen"><span className="lp-radio" aria-hidden="true" />My own: more than 3% in 10 minutes</span>
          </div>
        </div>
      </div>
    </figure>
  );
}
