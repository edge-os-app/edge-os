import { ClarifyScreen } from "./ClarifyScreen";
import { CompactPermissionSlip } from "./PermissionSlip";
import { ReportScreen } from "./ReportScreen";

export function HowItWorksSection() {
  return (
    <section id="how" className="lp-how" aria-labelledby="how-title">
      <div className="lp-section-head" data-reveal>
        <p className="lp-eyebrow">How it works</p>
        <h2 id="how-title" className="lp-h2">Ask, check, then go live.</h2>
      </div>

      <ol className="lp-steps">
        <li className="lp-step" data-reveal>
          <div className="lp-step-text">
            <span className="lp-step-label">Step 1</span>
            <h3 className="lp-step-title">Ask.</h3>
            <p className="lp-step-body">Describe your idea in your own words. Edge OS keeps them exactly and asks only what it needs, like what “pumps hard” means.</p>
          </div>
          <ClarifyScreen />
        </li>

        <li className="lp-step" data-reveal>
          <div className="lp-step-text">
            <span className="lp-step-label">Step 2</span>
            <h3 className="lp-step-title">Check.</h3>
            <p className="lp-step-body">The research agent pulls swap history from Envio, receipts through QuickNode and holder data from Nansen, and saves a report with supporting evidence, contrary evidence and what is missing.</p>
            <div className="lp-evidence-note">
              <span className="lp-evidence-stamp" aria-hidden="true">NOT ENOUGH EVIDENCE</span>
              <p className="lp-evidence-text">When data is missing, the result reads “Not enough evidence”, never a rejection.</p>
            </div>
          </div>
          <ReportScreen />
        </li>

        <li className="lp-step" data-reveal>
          <div className="lp-step-text lp-step-text-wide">
            <span className="lp-step-label">Step 3</span>
            <h3 className="lp-step-title">Go live, inside limits.</h3>
            <p className="lp-step-body">Replay supported rules on past prices with hypothetical fills, to see how they would have behaved. Once you choose supported rules and approve their limits, your agent trades on Kuru within that permission.</p>
            <p className="lp-step-body">Routine trades run while you’re offline, with no repeated signatures. Start with a small live trial if you want; your evidence stays labelled for what it is.</p>
            <p className="lp-step-body">Stop new trades, close a position, or remove the agent’s access. You choose each action.</p>
          </div>
          <CompactPermissionSlip />
        </li>
      </ol>

      <div className="lp-product" data-reveal>
        <p className="lp-product-text">See every agent, position and fund in one place, or ask about them in chat.</p>
        <figure className="lp-shot">
          <img
            src="/landing/agent-detail.png" width={896} height={412} loading="lazy"
            alt="Edge OS agent page for Agent D, showing its rule, own wallet, and status facts: agent not running, wallet ready, permission not approved, no stop, no open positions."
          />
        </figure>
      </div>
    </section>
  );
}
