const PROBLEMS = [
  "A backtest that hides costs or luck.",
  "A model that turns “buy when it pumps” into rules you never meant.",
  "A bot that trades without proving the idea had an edge.",
];

export function ProblemSection() {
  return (
    <section className="lp-problem" aria-labelledby="problem-title">
      <div className="lp-problem-grid" data-reveal>
        <div className="lp-stack-17">
          <p className="lp-eyebrow">The problem</p>
          <h2 id="problem-title" className="lp-h2" style={{ textWrap: "balance" }}>A meme token on Monad jumps hard in five minutes. Do you buy?</h2>
        </div>
        <div className="lp-problem-body">
          <p className="lp-lead">
            Most traders guess. Some hand the guess to a bot that holds their keys. The research is spread across a chart, a feed,
            a notebook and a wallet, and nobody can say later why the trade happened.
          </p>
          <ul className="lp-problem-list">
            {PROBLEMS.map((problem) => (
              <li key={problem}><span className="lp-ring" aria-hidden="true" /><span>{problem}</span></li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
