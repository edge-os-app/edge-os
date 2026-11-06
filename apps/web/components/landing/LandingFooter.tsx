const REPO_URL = "https://github.com/edge-os-app/edge-os";

export function LandingFooter() {
  return (
    <footer className="lp-footer">
      <div className="lp-footer-inner">
        <img src="/landing/lockup.svg" alt="Edge OS" width={120} height={120} />
        <div className="lp-footer-links">
          <a href={REPO_URL} target="_blank" rel="noopener">Edge OS on GitHub</a>
          <span>Built by <a href="https://github.com/degencodebeast" target="_blank" rel="noopener">degencodebeast</a>, solo founder.</span>
        </div>
      </div>
    </footer>
  );
}
