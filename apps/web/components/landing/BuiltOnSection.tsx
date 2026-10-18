// Text only. No sponsor logos, and nothing that implies endorsement.
const PARTS = [
  { name: "Monad", role: "The chain" },
  { name: "Kuru", role: "Spot trades" },
  { name: "Envio", role: "Swap history" },
  { name: "Nansen", role: "Holder data" },
  { name: "Privy", role: "Wallets" },
];

export function BuiltOnSection() {
  return (
    <section className="lp-built" aria-labelledby="built-title">
      <h2 id="built-title" className="lp-built-title" data-reveal>Built on Monad</h2>
      <ul className="lp-built-list" data-reveal>
        {PARTS.map((part) => (
          <li key={part.name}><span className="lp-built-name">{part.name}</span><span className="lp-built-role">{part.role}</span></li>
        ))}
      </ul>
    </section>
  );
}
