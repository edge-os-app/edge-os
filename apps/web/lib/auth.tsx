"use client";

import dynamic from "next/dynamic";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, setTokenSource, setUnauthorizedHandler } from "./api";

export type AuthStatus = "loading" | "signed-out" | "signing-in" | "ready" | "unavailable";

/**
 * Seam for the automated browser harness. The harness injects an object with this shape before any page script runs
 * (for example a Playwright init script). The implementation and its signing key live only under tests/p03, never in
 * this app. No build flag or environment variable selects it. The app labels the session visibly when it is used.
 */
export interface InjectedTestAuth {
  label: string;
  getAccessToken(): Promise<string | null>;
  signOut?(): void;
}

declare global {
  interface Window {
    __EDGE_OS_TEST_AUTH__?: InjectedTestAuth;
  }
}

export interface AuthValue {
  status: AuthStatus;
  fixtureLabel: string | null;
  unavailableReason: string | null;
  userId: string | null;
  signInMessage: string | null;
  explicitSignOut: boolean;
  login(): void;
  logout(): void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth needs AuthRoot");
  return value;
}

/** The Privy bridge loads only when the production path runs. It makes no network call before then. */
const PrivyBridge = dynamic(() => import("./privy-bridge"), { ssr: false });

interface Source {
  ready: boolean;
  authenticated: boolean;
  getAccessToken(): Promise<string | null>;
  login(): void;
  logout(): void;
  /** Counts sign-in attempts that ended in an error or a closed window. */
  loginErrors?: number;
}

const SIGN_IN_TIMEOUT_MS = 60_000;
const SIGN_IN_FAILED = "Sign-in did not finish. Nothing was changed. Try again.";

export function AuthRoot({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<"detecting" | "fixture" | "privy" | "unconfigured">("detecting");
  const [fixture, setFixture] = useState<InjectedTestAuth | null>(null);
  useEffect(() => {
    const injected = window.__EDGE_OS_TEST_AUTH__;
    if (injected) { setFixture(injected); setMode("fixture"); }
    else if (process.env.NEXT_PUBLIC_PRIVY_APP_ID) setMode("privy");
    else setMode("unconfigured");
  }, []);

  if (mode === "detecting") return <AuthSession source={null} fixtureLabel={null} unavailable={null}>{children}</AuthSession>;
  if (mode === "unconfigured")
    return <AuthSession source={null} fixtureLabel={null} unavailable="Sign-in is not configured for this deployment.">{children}</AuthSession>;
  if (mode === "fixture" && fixture) return <FixtureAuth fixture={fixture}>{children}</FixtureAuth>;
  return (
    <PrivyBridge appId={process.env.NEXT_PUBLIC_PRIVY_APP_ID as string}
      render={(source) => <AuthSession source={source} fixtureLabel={null} unavailable={null}>{children}</AuthSession>} />
  );
}

/** A fixture session that really signs out and back in, so the harness exercises both directions. */
function FixtureAuth({ fixture, children }: { fixture: InjectedTestAuth; children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(true);
  const source = useMemo<Source>(() => ({
    ready: true, authenticated: signedIn, getAccessToken: () => fixture.getAccessToken(),
    login: () => setSignedIn(true), logout: () => { setSignedIn(false); fixture.signOut?.(); },
  }), [fixture, signedIn]);
  return <AuthSession source={source} fixtureLabel={fixture.label} unavailable={null}>{children}</AuthSession>;
}

function AuthSession({ source, fixtureLabel, unavailable, children }: {
  source: Source | null; fixtureLabel: string | null; unavailable: string | null; children: ReactNode;
}) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [userId, setUserId] = useState<string | null>(null);
  const [reason, setReason] = useState<string | null>(unavailable);
  const [signInMessage, setSignInMessage] = useState<string | null>(null);
  const [explicitSignOut, setExplicitSignOut] = useState(false);
  const statusRef = useRef<AuthStatus>("loading");
  const getToken = source?.getAccessToken;
  statusRef.current = status;

  // A sign-in that ends in an error, a closed window or silence must not leave a dead "Signing in" state.
  const endSignIn = useCallback((message: string) => {
    if (statusRef.current !== "signing-in") return;
    setSignInMessage(message);
    setStatus("signed-out");
  }, []);
  const loginErrors = source?.loginErrors ?? 0;
  const seenErrors = useRef(loginErrors);
  useEffect(() => {
    if (loginErrors !== seenErrors.current) { seenErrors.current = loginErrors; endSignIn(SIGN_IN_FAILED); }
  }, [loginErrors, endSignIn]);
  useEffect(() => {
    if (status !== "signing-in") return;
    const timer = setTimeout(() => endSignIn(SIGN_IN_FAILED), SIGN_IN_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [status, endSignIn]);

  useEffect(() => { setTokenSource(getToken ?? (async () => null)); }, [getToken]);
  useEffect(() => { setUnauthorizedHandler(() => { setUserId(null); setStatus("signed-out"); }); }, []);

  useEffect(() => {
    let cancelled = false;
    if (unavailable) { setStatus("unavailable"); setReason(unavailable); return; }
    if (!source || !source.ready) { setStatus("loading"); return; }
    if (!source.authenticated) { setUserId(null); setStatus("signed-out"); return; }
    // Probe the API once the provider is signed in. The API alone decides whether the session is accepted.
    setStatus("loading");
    api.me().then((me) => { if (!cancelled) { setUserId(me.user_id); setSignInMessage(null); setExplicitSignOut(false); setStatus("ready"); } }).catch((error: unknown) => {
      if (cancelled) return;
      if (error instanceof ApiError && error.status === 401) { setStatus("signed-out"); return; }
      setReason(error instanceof ApiError && error.status === 503
        ? "The service cannot verify sign-in right now. Try again soon."
        : "The service could not be reached.");
      setStatus("unavailable");
    });
    return () => { cancelled = true; };
  }, [source?.ready, source?.authenticated, unavailable]); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(() => { setSignInMessage(null); setStatus("signing-in"); source?.login(); }, [source]);
  const logout = useCallback(() => { setUserId(null); setExplicitSignOut(true); setSignInMessage(null); setStatus("signed-out"); source?.logout(); }, [source]);
  const value = useMemo<AuthValue>(
    () => ({ status, fixtureLabel, unavailableReason: reason, userId, signInMessage, explicitSignOut, login, logout }),
    [status, fixtureLabel, reason, userId, signInMessage, explicitSignOut, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
