export function LandingHeader() {
  return (
    <header className="lp-header">
      <a className="lp-logo" href="#top" aria-label="Edge OS home">
        <span className="lp-logo-mark" aria-hidden="true">
          <img src="/landing/icon.svg" alt="" width={72} height={72} />
        </span>
        <span className="lp-wordmark">Edge <span className="lp-wordmark-os">OS</span></span>
      </a>
      <nav className="lp-nav" aria-label="Page">
        <a className="lp-nav-link" href="#how">How it works</a>
        <a className="lp-nav-link" href="#questions">Questions</a>
        <a className="lp-btn lp-btn-primary lp-btn-small" href="/app">Enter app</a>
      </nav>
    </header>
  );
}
