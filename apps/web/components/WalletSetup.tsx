"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { WalletSetupRecord } from "../lib/types";

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
  const [mode, setMode] = useState<"fixture" | "unavailable" | null>(null);
  // Every read gets a sequence number so a late response for an older agent can never overwrite the current one.
  const readSeq = useRef(0);

  useEffect(() => {
    let current = true;
    api.walletProvider().then((info) => { if (current) setMode(info.provider); })
      .catch(() => { if (current) setMode("unavailable"); }); // fail safe: never claim a fixture that is not confirmed
    return () => { current = false; };
  }, []);

  const load = useCallback(async (id: string) => {
    const seq = (readSeq.current += 1);
    setError("");
    setUncertain(false);
    setRecord(null);
    if (!id) { setPhase("empty"); return; }
    setBusy(true);
    setPhase("loading");
    try {
      const saved = await api.walletSetup(id);
      if (seq !== readSeq.current) return; // a newer read superseded this one
      setRecord(saved); setPhase("loaded");
    } catch (failure) {
      if (seq !== readSeq.current) return;
      if (failure instanceof ApiError && failure.status === 404) { setRecord(null); setPhase("empty"); }
      else { setError(failure instanceof ApiError ? failure.detail : "The wallet setup could not be loaded."); setPhase("error"); }
    } finally {
      if (seq === readSeq.current) setBusy(false);
    }
  }, []);

  useEffect(() => { setAgent(agentId ?? ""); }, [agentId]);
  useEffect(() => { if (agentId) void load(agentId); }, [agentId, load]);

  // Read the exact saved setup. It never mutates. Used after an uncertain mutation and by the retry button.
  const check = useCallback(async (id: string) => {
    if (!id) return;
    const seq = (readSeq.current += 1);
    setBusy(true);
    try {
      const saved = await api.walletSetup(id);
      if (seq !== readSeq.current) return;
      setRecord(saved); setPhase("loaded"); setUncertain(false); setError("");
    } catch (failure) {
      if (seq !== readSeq.current) return;
      if (failure instanceof ApiError && failure.status === 404) {
        setRecord(null); setPhase("empty"); setUncertain(false); setError("");
      } else {
        setError("The saved setup could not be checked. The outcome stays unconfirmed until a read succeeds.");
      }
    } finally {
      if (seq === readSeq.current) setBusy(false);
    }
  }, []);

  // A mutation. If its response is lost or the call fails, the outcome is uncertain: read the saved
  // setup before offering any further creation. Until that read succeeds, creation stays suppressed.
  const run = useCallback(async (id: string, action: () => Promise<WalletSetupRecord>, fallback: string) => {
    if (busy || uncertain) return;
    setBusy(true); setError("");
    try {
      setRecord(await action());
      setPhase("loaded");
    } catch (failure) {
      setUncertain(true);
      setError(failure instanceof ApiError && failure.status !== 0
        ? failure.detail
        : "The outcome is not confirmed. The saved setup is being checked before any further action.");
      const seq = (readSeq.current += 1);
      try {
        const saved = await api.walletSetup(id);
        if (seq === readSeq.current) { setRecord(saved); setPhase("loaded"); setUncertain(false); setError(""); }
      } catch (readFailure) {
        if (seq !== readSeq.current) return;
        if (readFailure instanceof ApiError && readFailure.status === 404) {
          setRecord(null); setPhase("empty"); setUncertain(false);
        } else {
          setError("The outcome is not confirmed and the saved setup could not be checked. Check it again before any further action.");
        }
      }
    } finally { setBusy(false); }
  }, [busy, uncertain]);

  const canPrepare = Boolean(revision) && /^[A-Za-z0-9_-]{1,64}$/.test(agent) && mode === "fixture";
  const prepare = () => {
    if (!revision || !canPrepare) return;
    void run(agent, () => api.prepareWalletSetup(agent, {
      network_id: network, strategy_id: revision.strategyId,
      strategy_revision_id: revision.strategyRevisionId, request_key: pendingKey(agent),
    }), "The wallet setup was not saved.");
  };

  const creationAvailable = mode === "fixture";
  const blocked = busy || uncertain;

  return (
    <section className="panel" aria-label="Agent wallet setup">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Agent wallet setup</h2>
        {onClose ? <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" onClick={onClose}>Close setup</button> : null}
      </div>
      {mode === null && <p className="muted">Checking the wallet provider…</p>}
      {mode === "fixture" && <p className="muted">This build uses an authored local fixture. It is not a real wallet or provider. Creation adds no funding, signer, mandate, position or trading action.</p>}
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
                  onClick={() => void run(record.agent_id, () => api.dispatchWalletSetup(record.agent_id), "The wallet request was not sent.")}>
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
                onClick={() => void run(record.agent_id, () => api.resumeWalletSetup(record.agent_id), "The saved setup could not be checked.")}>
                {busy ? "Checking…" : "Check the saved setup again"}
              </button>
              <span className="muted">This only reads the saved setup. It never replays a creation.</span>
            </div>
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
