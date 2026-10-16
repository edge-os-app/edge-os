"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useOptionalAuth } from "../lib/auth";
import type { WalletSetupRecord } from "../lib/types";
import { forgetClaim, retainClaim, retainedClaim, walletProviderMode, walletSetupApi, type WalletProviderMode } from "../lib/wallet-setup-api";

export interface WalletSetupRevision { strategyId: string; strategyRevisionId: string }

const NETWORKS = [
  { id: 10143 as const, label: "Monad testnet (10143)" },
  { id: 143 as const, label: "Monad mainnet (143)" },
];

const REASON_COPY: Record<string, string> = {
  CANCELLED_BEFORE_DISPATCH: "Cancelled before any wallet was requested. No creation call was made.",
  PROVIDER_UNAVAILABLE: "The wallet provider did not answer. The outcome is unknown; check the saved setup again.",
  PROVIDER_ERROR: "The wallet provider failed. The outcome is unknown; check the saved setup again.",
  RESPONSE_LOST: "The creation response was lost. No wallet is bound; check the saved setup again.",
  MALFORMED_RESULT: "The provider result was malformed and was not saved. Check the saved setup again.",
  RECONCILE_NO_EXACT_ID: "No exact wallet identity was retained to reconcile. No second creation is attempted.",
  RECONCILE_NO_MATCH: "The wallet could not be matched by an independent lookup. It stays unknown.",
  RECONCILE_WRONG_IDENTITY: "The retained result did not match the independent lookup. It stays unknown.",
  CONFLICTING_WALLET: "That wallet already belongs to another agent of this owner. It was not bound.",
};

const UNSUPPORTED_WALLET = "The wallet that came back is not an Ethereum wallet. Nothing was bound and no second wallet is created.";

function stateTitle(record: WalletSetupRecord): string {
  switch (record.state) {
    case "REQUESTED": return "Saved, not dispatched";
    case "PENDING": return "Creation pending";
    case "UNKNOWN": return "Outcome unknown";
    case "CONFIRMED": return "Wallet confirmed";
    case "FAILED": return record.reason === "CANCELLED_BEFORE_DISPATCH" ? "Cancelled before dispatch" : "Setup failed";
  }
}

/** Request keys are held per agent so a repeated prepare reuses the same key after a lost response. */
function pendingKey(agentId: string): string {
  const storageKey = `edge-os:wallet-setup:${agentId}`;
  try {
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored) return stored;
  } catch { /* storage may be blocked; a repeated identity is still idempotent server-side */ }
  const key = `ui-${crypto.randomUUID()}`;
  try { window.sessionStorage.setItem(storageKey, key); } catch { /* ignore */ }
  return key;
}

export function WalletSetup({ agentId, revision, onClose }: {
  agentId?: string;
  revision?: WalletSetupRevision | null;
  onClose?: () => void;
}) {
  const [agent, setAgent] = useState(agentId ?? "");
  const [network, setNetwork] = useState<143 | 10143>(10143);
  const [record, setRecord] = useState<WalletSetupRecord | null>(null);
  const [phase, setPhase] = useState<"loading" | "empty" | "loaded" | "error">(agentId ? "loading" : "empty");
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<WalletProviderMode | null>(null);
  const auth = useOptionalAuth();
  const createEmbeddedWallet = auth?.createEmbeddedWallet ?? null;
  const ownerId = auth?.userId ?? null;
  // One sequence for every operation that changes what the panel shows. A late response, from an older
  // read or an older mutation, can never overwrite the current selection.
  const viewSeq = useRef(0);

  useEffect(() => {
    let current = true;
    api.walletProvider().then((info) => { if (current) setMode(walletProviderMode(info.provider)); })
      .catch(() => { if (current) setMode("unavailable"); }); // fail safe: never claim a fixture that is not confirmed
    return () => { current = false; };
  }, []);

  const load = useCallback(async (id: string) => {
    const seq = (viewSeq.current += 1);
    setError("");
    setUncertain(false);
    setRecord(null);
    if (!id) { setPhase("empty"); return; }
    setBusy(true);
    setPhase("loading");
    try {
      const saved = await api.walletSetup(id);
      if (seq !== viewSeq.current) return; // a newer read superseded this one
      setRecord(saved); setPhase("loaded");
    } catch (failure) {
      if (seq !== viewSeq.current) return;
      if (failure instanceof ApiError && failure.status === 404) { setRecord(null); setPhase("empty"); }
      else { setError(failure instanceof ApiError ? failure.detail : "The wallet setup could not be loaded."); setPhase("error"); }
    } finally {
      if (seq === viewSeq.current) setBusy(false);
    }
  }, []);

  useEffect(() => { setAgent(agentId ?? ""); }, [agentId]);
  useEffect(() => { if (agentId) void load(agentId); }, [agentId, load]);

  // Read the exact saved setup. It never mutates. Used after an uncertain mutation and by the retry button.
  const check = useCallback(async (id: string) => {
    if (!id) return;
    const seq = (viewSeq.current += 1);
    setBusy(true);
    try {
      const saved = await api.walletSetup(id);
      if (seq !== viewSeq.current) return;
      setRecord(saved); setPhase("loaded"); setUncertain(false); setError("");
    } catch (failure) {
      if (seq !== viewSeq.current) return;
      if (failure instanceof ApiError && failure.status === 404) {
        setRecord(null); setPhase("empty"); setUncertain(false); setError("");
      } else {
        setError("The saved setup could not be checked. The outcome stays unconfirmed until a read succeeds.");
      }
    } finally {
      if (seq === viewSeq.current) setBusy(false);
    }
  }, []);

  // A mutation. If its response is lost or the call fails, the outcome is uncertain: read the saved
  // setup before offering any further creation. Until that read succeeds, creation stays suppressed.
  const run = useCallback(async (id: string, action: () => Promise<WalletSetupRecord>, fallback: string) => {
    if (busy || uncertain) return;
    const seq = (viewSeq.current += 1);
    setBusy(true); setError("");
    try {
      const saved = await action();
      if (seq !== viewSeq.current) return; // a newer selection or read superseded this mutation
      setRecord(saved);
      setPhase("loaded");
    } catch (failure) {
      if (seq !== viewSeq.current) return; // the pending outcome stays tied to its original agent
      setUncertain(true);
      setError(failure instanceof ApiError && failure.status !== 0
        ? failure.detail
        : "The outcome is not confirmed. The saved setup is being checked before any further action.");
      try {
        const saved = await api.walletSetup(id);
        if (seq !== viewSeq.current) return;
        setRecord(saved); setPhase("loaded"); setUncertain(false); setError("");
      } catch (readFailure) {
        if (seq !== viewSeq.current) return;
        if (readFailure instanceof ApiError && readFailure.status === 404) {
          setRecord(null); setPhase("empty"); setUncertain(false);
        } else {
          setError("The outcome is not confirmed and the saved setup could not be checked. Check it again before any further action.");
        }
      }
    } finally {
      if (seq === viewSeq.current) setBusy(false);
    }
  }, [busy, uncertain]);

  const actualCreation = mode === "privy_lookup" && createEmbeddedWallet !== null;
  const canPrepare = Boolean(revision) && /^[A-Za-z0-9_-]{1,64}$/.test(agent) && (mode === "fixture" || actualCreation);
  const prepare = () => {
    if (!revision || !canPrepare) return;
    void run(agent, () => api.prepareWalletSetup(agent, {
      network_id: network, strategy_id: revision.strategyId,
      strategy_revision_id: revision.strategyRevisionId, request_key: pendingKey(agent),
    }), "The wallet setup was not saved.");
  };

  const creationAvailable = mode === "fixture" || actualCreation;

  // Send the retained returned wallet for the server's independent lookup. It never creates. Without a claim kept
  // in this browser for this owner, the server resumes from the claim it retained itself.
  const completeRetained = async (agentId: string): Promise<WalletSetupRecord> => {
    const claim = retainedClaim(ownerId, agentId);
    if (!claim) return api.resumeWalletSetup(agentId);
    if (claim.chainType !== "ethereum") { setError(UNSUPPORTED_WALLET); return api.walletSetup(agentId); }
    const saved = await walletSetupApi.completeBrowserCreation(agentId, { wallet_id: claim.id, address: claim.address, wallet_index: claim.walletIndex });
    if (saved.state === "CONFIRMED" && ownerId) forgetClaim(ownerId, agentId);
    return saved;
  };

  // The server commits the intent first and permits one SDK call only. A refused or repeated begin creates nothing.
  const createActual = async (agentId: string): Promise<WalletSetupRecord> => {
    if (retainedClaim(ownerId, agentId)) return completeRetained(agentId);
    const begun = await walletSetupApi.beginBrowserCreation(agentId);
    if (!begun.create_permitted || !createEmbeddedWallet || !ownerId) return begun;
    const wallet = await createEmbeddedWallet();
    retainClaim(ownerId, agentId, wallet);
    return completeRetained(agentId);
  };
  const blocked = busy || uncertain;

  return (
    <section className="panel" aria-label="Agent wallet setup">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Agent wallet setup</h2>
        {onClose ? <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" onClick={onClose}>Close setup</button> : null}
      </div>
      {mode === null && <p className="muted">Checking the wallet provider…</p>}
      {mode === "fixture" && <p className="muted">This build uses an authored local fixture. It is not a real wallet or provider. Creation adds no funding, signer, mandate, position or trading action.</p>}
      {actualCreation && <p className="muted">This creates one additional wallet in your own Privy account for this agent. It adds no funding, signer, mandate, position or trading action.</p>}
      {mode === "privy_lookup" && !createEmbeddedWallet && <p className="muted">Sign in with Privy to create this agent's wallet.</p>}
      {mode === "unavailable" && <p className="muted">Real wallet creation is unavailable in this build. No provider is configured, so no wallet can be created. It adds no funding, signer, mandate, position or trading action.</p>}

      {!agentId && (
        <div>
          <label htmlFor="wallet-setup-agent">Agent ID</label>
          <div className="btn-row">
            <input id="wallet-setup-agent" className="input" value={agent} maxLength={64} style={{ minHeight: 44 }}
              onChange={(event) => setAgent(event.target.value)} />
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" data-testid="wallet-setup-check"
              disabled={!agent} onClick={() => void load(agent)}>
              {busy ? "Checking…" : "Check saved setup"}
            </button>
          </div>
        </div>
      )}
      {agentId && <p><strong>Agent.</strong> <code>{agentId}</code></p>}

      <p role="status" aria-live="polite" className="visually-hidden">{busy ? "Working on the wallet setup." : ""}</p>
      {error ? <p role="alert" className="status err">{error}</p> : null}
      {uncertain && (
        <div className="btn-row">
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
            onClick={() => void check(record?.agent_id ?? agent)}>Check the saved setup</button>
          <span className="muted">The last action's outcome is not confirmed. Creation stays paused until this read succeeds.</span>
        </div>
      )}

      {phase === "loading" && <p role="status" className="muted">Checking the saved setup…</p>}
      {phase === "error" && <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={!agent}
        onClick={() => void load(agent)}>Try again</button>}

      {!uncertain && !record && phase !== "loading" && phase !== "error" && (
        <div>
          <h3>No wallet setup saved</h3>
          {!revision ? (
            <p className="muted">Choose an exact saved strategy revision in Research to set up a wallet for this agent.</p>
          ) : !creationAvailable ? (
            <p className="muted">A durable setup can be saved here only when wallet creation is available. This build uses no provider, so creation is refused.</p>
          ) : (
            <div>
              <p>The setup binds this exact saved revision. It never uses a first or latest wallet.</p>
              <dl className="kv">
                <dt>Strategy revision</dt><dd className="mono">{revision.strategyRevisionId}</dd>
              </dl>
              <label htmlFor="wallet-setup-network">Requested network</label>
              <select id="wallet-setup-network" className="input" style={{ minHeight: 44 }} value={network}
                onChange={(event) => setNetwork(Number(event.target.value) as 143 | 10143)}>
                {NETWORKS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
              <div className="btn-row">
                <button className="btn btn-primary" style={{ minHeight: 44 }} type="button"
                  disabled={blocked || !canPrepare} onClick={prepare}>
                  {busy ? "Saving…" : "Save wallet setup"}
                </button>
                <span className="muted">Saving records the setup before any creation. It creates no wallet yet.</span>
              </div>
            </div>
          )}
        </div>
      )}

      {!uncertain && record && (
        <div>
          <h3 data-testid="wallet-setup-state">{stateTitle(record)}</h3>
          <dl className="kv">
            <dt>Agent</dt><dd>{record.agent_id}</dd>
            <dt>Requested network</dt><dd>{record.network_id}</dd>
            <dt>Strategy revision</dt><dd className="mono">{record.strategy_revision_id}</dd>
            <dt>Cancellation intent</dt><dd>{record.cancellation_intent}</dd>
            <dt>Wallet</dt><dd className="mono" data-testid="wallet-setup-wallet">{record.wallet_id ?? "Not bound"}</dd>
            <dt>Updated</dt><dd><time dateTime={record.updated_at}>{record.updated_at}</time></dd>
          </dl>
          <p>Requested network is an application binding. It does not prove provider-chain enforcement.</p>
          {record.reason ? <p className="muted">{REASON_COPY[record.reason] ?? record.reason}</p> : null}

          {creationAvailable && record.state === "REQUESTED" && record.cancellation_intent === "NONE" && (
            <>
              <div className="btn-row">
                <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={blocked}
                  onClick={() => void run(record.agent_id, () => actualCreation ? createActual(record.agent_id) : api.dispatchWalletSetup(record.agent_id), "The wallet request was not sent.")}>
                  {busy ? "Creating…" : "Create wallet now"}
                </button>
                <span className="muted">One creation attempt. A repeat never creates a second wallet.</span>
              </div>
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={blocked}
                onClick={() => void run(record.agent_id, () => api.cancelWalletSetup(record.agent_id), "The cancellation was not saved.")}>
                Cancel before creating
              </button>
            </>
          )}

          {(record.state === "PENDING" || record.state === "UNKNOWN") && (
            <div className="btn-row">
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={blocked}
                onClick={() => void run(record.agent_id, () => actualCreation ? completeRetained(record.agent_id) : api.resumeWalletSetup(record.agent_id), "The saved setup could not be checked.")}>
                {busy ? "Checking…" : "Check the saved setup again"}
              </button>
              <span className="muted">This only reads the saved setup. It never replays a creation.</span>
            </div>
          )}

          {record.state === "CONFIRMED" && (
            <p className="btn-row">
              <a className="btn btn-secondary" style={{ minHeight: 44 }} href={`#/funds?agent=${encodeURIComponent(record.agent_id)}`}>Fund this agent</a>
              <a className="btn btn-secondary" style={{ minHeight: 44 }} href={`#/agents?agent=${encodeURIComponent(record.agent_id)}`}>Review bounded authority</a>
              <a className="btn btn-secondary" style={{ minHeight: 44 }} href={`#/positions?agent=${encodeURIComponent(record.agent_id)}`}>Agent actions</a>
            </p>
          )}

          {record.state === "CONFIRMED" && record.cancellation_intent === "NONE" && (
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={blocked}
              onClick={() => void run(record.agent_id, () => api.cancelWalletSetup(record.agent_id), "The cancellation was not saved.")}>
              Record cancellation intent
            </button>
          )}
        </div>
      )}
    </section>
  );
}
