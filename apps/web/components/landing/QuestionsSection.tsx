const QUESTIONS = [
  { q: "Will the AI make things up?", a: "Findings keep source references, contrary evidence and missing data. You can inspect the reasons before adopting rules." },
  { q: "Do I need to write code?", a: "No. You describe the idea; Edge OS turns supported ideas into exact rules you can read." },
  { q: "Who holds my money?", a: "Each agent has a separate wallet you own. Removing the agent’s access leaves you in control of the funds." },
  { q: "What stops a bad trade?", a: "The agent can only act inside the permission you signed: tokens, size, total limit, expiry and stops. A good report or backtest never grants permission by itself." },
  { q: "Can I stop it?", a: "Yes. Stop new trades, close a position, or remove the agent’s access. You choose each action, and each is explained before you use it." },
];

export function QuestionsSection() {
  return (
    <section id="questions" className="lp-questions" aria-labelledby="q-title">
      <div className="lp-questions-inner">
        <div className="lp-section-head" data-reveal>
          <p className="lp-eyebrow">Questions</p>
          <h2 id="q-title" className="lp-h2">Answers to the real worries.</h2>
        </div>
        <dl className="lp-qa-list" data-reveal>
          {QUESTIONS.map(({ q, a }) => (
            <div className="lp-qa" key={q}><dt>{q}</dt><dd>{a}</dd></div>
          ))}
        </dl>
      </div>
    </section>
  );
}
