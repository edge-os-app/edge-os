import { HeroPermissionSlip } from "./PermissionSlip";

export function HeroSection() {
  return (
    <section id="top" className="lp-hero" aria-labelledby="hero-title">
      <div className="lp-hero-copy">
        <h1 id="hero-title" className="lp-hero-title">Test your trade idea. Then let an agent trade it inside your limits.</h1>
        <p className="lp-hero-sub">
          Most meme trades start as a guess, or a bot that holds your keys. Edge OS checks your idea against on-chain evidence,
          tells you when it doesn’t hold, and lets an agent trade only within the permission you sign.
        </p>
        <div className="lp-btn-row">
          <a className="lp-btn lp-btn-primary" href="/app">Enter app</a>
          <a className="lp-btn lp-btn-secondary" href="https://vimeo.com/1235649955" target="_blank" rel="noopener">Watch the pitch</a>
        </div>
        <p className="lp-hero-note">Built for the Monad hackathon · Onchain Finance &amp; Trading.</p>
      </div>
      <figure className="lp-hero-slip">
        <HeroPermissionSlip />
        <figcaption className="lp-caption"><strong>The agent proposes. Your limits decide.</strong> A good report never signs this for you.</figcaption>
      </figure>
    </section>
  );
}
