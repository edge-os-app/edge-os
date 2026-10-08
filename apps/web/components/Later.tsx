export function Later({ area }: { area: string }) {
  return (
    <div className="stack">
      <h1>{area}</h1>
      <section className="panel" role="status">
        <h2>Not available in this build</h2>
        <p>This build covers Research only. {area} comes in a later slice. Nothing here can move money or change permission.</p>
        <p className="muted">Your saved research is under Research.</p>
      </section>
    </div>
  );
}
