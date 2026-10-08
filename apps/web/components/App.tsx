"use client";

import { useEffect, useRef } from "react";
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
  const heading = useRef<HTMLHeadingElement>(null);
  const message = useRef<HTMLParagraphElement>(null);
  const waiting = auth.status === "signing-in";
  // After an explicit sign-out, or when sign-in ends in a message, focus lands on what the person needs to read.
  useEffect(() => {
    if (auth.status !== "signed-out") return;
    if (auth.signInMessage) message.current?.focus();
    else if (auth.explicitSignOut) heading.current?.focus();
  }, [auth.status, auth.signInMessage, auth.explicitSignOut]);
  return (
    <main id="main" className="center-card stack" style={{ padding: "0 16px" }}>
      <h1 className="brand" style={{ margin: 0 }}>Edge OS</h1>
      {auth.status === "loading" ? (
        <section className="panel" aria-busy="true" role="status">
          <h2>Checking your session</h2>
          <p className="muted">One moment.</p>
        </section>
      ) : auth.status === "unavailable" ? (
        <section className="panel" role="alert">
          <h2>Sign-in is unavailable</h2>
          <p>{auth.unavailableReason ?? "The service cannot verify sign-in right now."}</p>
          <p className="muted">Your saved work is not affected.</p>
          <div className="btn-row"><button className="btn btn-primary" type="button" onClick={() => window.location.reload()}>Reload and try again</button></div>
        </section>
      ) : (
        <section className="panel">
          <h2 ref={heading} tabIndex={-1}>Sign in to start</h2>
          <p>Research on Monad. Your words and restrictions are kept exactly as you write them.</p>
          <p className="muted">Signing in does not create a wallet, grant permission or move money.</p>
          {auth.signInMessage ? <p role="alert" className="status err" ref={message} tabIndex={-1}>{auth.signInMessage}</p> : null}
          {waiting && !auth.signInSlow ? <p role="status" className="muted">Waiting for sign-in to finish.</p> : null}
          {waiting && auth.signInSlow ? <p role="status" className="muted">Still waiting. If the sign-in window is closed or stuck, press Try again.</p> : null}
          <div className="btn-row">
            <button className="btn btn-primary" type="button" onClick={() => { if (!waiting || auth.signInSlow) auth.login(); }} aria-disabled={(waiting && !auth.signInSlow) || undefined}>
              {waiting ? (auth.signInSlow ? "Try again" : "Signing in…") : "Sign in"}
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
