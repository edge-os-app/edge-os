"use client";

import { useCallback, useEffect, useState } from "react";
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
  const [error, setError] = useState("");

  const load = useCallback(async (id: string) => {
    if (!id) { setRecord(null); setPhase("empty"); return; }
    setBusy(true); setError("");
    try {
      setRecord(await api.walletSetup(id));
      setPhase("loaded");
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 404) { setRecord(null); setPhase("empty"); }
      else { setError(failure instanceof ApiError ? failure.detail : "The wallet setup could not be loaded."); setPhase("error"); }
    } finally { setBusy(false); }
  }, []);

  useEffect(() => { setAgent(agentId ?? ""); }, [agentId]);
  useEffect(() => { if (agentId) void load(agentId); }, [agentId, load]);

  const run = useCallback(async (action: () => Promise<WalletSetupRecord>, fallback: string) => {
    setBusy(true); setError("");
    try {
      setRecord(await action());
      setPhase("loaded");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : fallback);
    } finally { setBusy(false); }
  }, []);

  const canPrepare = Boolean(revision) && /^[A-Za-z0-9_-]{1,64}$/.test(agent);
  const prepare = () => {
    if (!revision || !canPrepare) return;
    void run(() => api.prepareWalletSetup(agent, {
      network_id: network, strategy_id: revision.strategyId,
      strategy_revision_id: revision.strategyRevisionId, request_key: pendingKey(agent),
    }), "The wallet setup was not saved.");
  };

  return (
    <section className="panel" aria-label="Agent wallet setup">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Agent wallet setup</h2>
        {onClose ? <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" onClick={onClose}>Close setup</button> : null}
      </div>
      <p className="muted">This build uses an authored local fixture. It is not a real wallet or provider. Creation adds no funding, signer, mandate, position or trading action.</p>

      {!agentId && (
        <div>
          <label htmlFor="wallet-setup-agent">Agent ID</label>
          <div className="btn-row">
            <input id="wallet-setup-agent" className="input" value={agent} maxLength={64} style={{ minHeight: 44 }}
              onChange={(event) => setAgent(event.target.value)} />
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button"
              aria-disabled={busy || !agent || undefined} onClick={() => void load(agent)}>
              {busy ? "Checking…" : "Check saved setup"}
            </button>
          </div>
        </div>
      )}
      {agentId && <p><strong>Agent.</strong> <code>{agentId}</code></p>}

      <p role="status" aria-live="polite" className="visually-hidden">{busy ? "Working on the wallet setup." : ""}</p>
      {error ? <p role="alert" className="status err">{error}</p> : null}

      {phase === "loading" && <p role="status" className="muted">Checking the saved setup…</p>}
      {phase === "error" && <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
        onClick={() => void load(agent)}>Try again</button>}

      {!record && phase !== "loading" && phase !== "error" && (
        <div>
          <h3>No wallet setup saved</h3>
          {revision ? (
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
                  aria-disabled={busy || !canPrepare || undefined} onClick={prepare}>
                  {busy ? "Saving…" : "Save wallet setup"}
                </button>
                <span className="muted">Saving records the setup before any creation. It creates no wallet yet.</span>
              </div>
            </div>
          ) : (
            <p className="muted">Choose an exact saved strategy revision in Research to set up a wallet for this agent.</p>
          )}
        </div>
      )}

      {record && (
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

          {record.state === "REQUESTED" && record.cancellation_intent === "NONE" && (
            <>
              <div className="btn-row">
                <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" aria-disabled={busy || undefined}
                  onClick={() => void run(() => api.dispatchWalletSetup(record.agent_id), "The wallet request was not sent.")}>
                  {busy ? "Creating…" : "Create wallet now"}
                </button>
                <span className="muted">One creation attempt. A repeat never creates a second wallet.</span>
              </div>
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
                onClick={() => void run(() => api.cancelWalletSetup(record.agent_id), "The cancellation was not saved.")}>
                Cancel before creating
              </button>
            </>
          )}

          {(record.state === "PENDING" || record.state === "UNKNOWN") && (
            <div className="btn-row">
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" aria-disabled={busy || undefined}
                onClick={() => void run(() => api.resumeWalletSetup(record.agent_id), "The saved setup could not be checked.")}>
                {busy ? "Checking…" : "Check the saved setup again"}
              </button>
              <span className="muted">This only reads the saved setup. It never replays a creation.</span>
            </div>
          )}

          {record.state === "CONFIRMED" && record.cancellation_intent === "NONE" && (
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
              onClick={() => void run(() => api.cancelWalletSetup(record.agent_id), "The cancellation was not saved.")}>
              Record cancellation intent
            </button>
          )}
        </div>
      )}
    </section>
  );
}
