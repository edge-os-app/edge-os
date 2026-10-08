"use client";

import { AuthRoot, useAuth } from "../lib/auth";
import { Shell } from "./Shell";

export function App() {
  return (
    <AuthRoot>
      <Gate />
    </AuthRoot>
  );
}

function Gate() {
  const auth = useAuth();
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      {auth.fixtureLabel ? (
        <div className="fixture-banner" role="note" data-testid="fixture-banner">{auth.fixtureLabel}</div>
      ) : null}
      {auth.status === "ready" ? <Shell /> : <Signed />}
    </>
  );
}

function Signed() {
  const auth = useAuth();
  return (
    <main id="main" className="center-card stack" style={{ padding: "0 16px" }}>
      <h1 className="brand" style={{ margin: 0 }}>Edge OS</h1>
      {auth.status === "loading" || auth.status === "signing-in" ? (
        <section className="panel" aria-busy="true" role="status">
          <h2>{auth.status === "signing-in" ? "Signing in" : "Checking your session"}</h2>
          <p className="muted">One moment.</p>
        </section>
      ) : auth.status === "unavailable" ? (
        <section className="panel" role="alert">
          <h2>Sign-in is unavailable</h2>
          <p>{auth.unavailableReason ?? "The service cannot verify sign-in right now."}</p>
          <p className="muted">Your saved work is not affected. Reload to try again.</p>
        </section>
      ) : (
        <section className="panel">
          <h2>Sign in to start</h2>
          <p>Research on Monad. Your words and restrictions are kept exactly as you write them.</p>
          <p className="muted">Signing in does not create a wallet, grant permission or move money.</p>
          <div className="btn-row">
            <button className="btn btn-primary" type="button" onClick={auth.login}>Sign in</button>
          </div>
        </section>
      )}
    </main>
  );
}
