import { request } from "./api";
import type { WalletSetupRecord } from "./types";

/** The wallet the owner's browser received from the Privy SDK. Untrusted until the server's own lookup matches it. */
export interface CreatedWallet {
  id: string | null;
  address: string;
  chainType: string;
  walletIndex: number | null;
}

export type WalletProviderMode = "fixture" | "privy_lookup" | "unavailable";

const path = (agentId: string, action: string) => `/v1/wallet-setup/agents/${encodeURIComponent(agentId)}/${action}`;

/** Any unrecognised provider answer is treated as unavailable, never as a fixture or an actual provider. */
export function walletProviderMode(provider: unknown): WalletProviderMode {
  return provider === "fixture" || provider === "privy_lookup" ? provider : "unavailable";
}

export const walletSetupApi = {
  /** Commits the dispatch intent first. Only the first begin for a setup permits one SDK creation. */
  beginBrowserCreation: (agentId: string) =>
    request<WalletSetupRecord & { create_permitted: boolean }>(path(agentId, "browser-begin"), { method: "POST" })
      .then((r) => r.body),
  completeBrowserCreation: (agentId: string, wallet: { wallet_id: string | null; address: string; wallet_index: number | null; chain_type: string }) =>
    request<WalletSetupRecord>(path(agentId, "complete"), { method: "POST", body: JSON.stringify(wallet) })
      .then((r) => r.body),
};

/**
 * The exact returned wallet is kept per verified owner and agent before completion, so a refresh resumes lookup
 * without creating. A different signed-in owner never reads it. The server also retains the claim.
 */
const claimKey = (ownerId: string, agentId: string) => `edge-os:wallet-claim:${ownerId}:${agentId}`;

/** True when this browser can keep a claim copy. Checked before creation, so a blocked store never loses a wallet. */
export function claimStorageWorks(): boolean {
  const probe = "edge-os:wallet-claim-probe";
  try { window.localStorage.setItem(probe, "1"); window.localStorage.removeItem(probe); return true; } catch { return false; }
}

export function retainClaim(ownerId: string, agentId: string, wallet: CreatedWallet): void {
  try { window.localStorage.setItem(claimKey(ownerId, agentId), JSON.stringify(wallet)); } catch { /* storage blocked */ }
}

export function retainedClaim(ownerId: string | null, agentId: string): CreatedWallet | null {
  if (!ownerId) return null;
  try {
    const raw = window.localStorage.getItem(claimKey(ownerId, agentId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<CreatedWallet>;
    if (typeof value.address !== "string" || typeof value.chainType !== "string") return null;
    return { id: typeof value.id === "string" ? value.id : null, address: value.address, chainType: value.chainType,
      walletIndex: typeof value.walletIndex === "number" ? value.walletIndex : null };
  } catch { return null; }
}

export function forgetClaim(ownerId: string, agentId: string): void {
  try { window.localStorage.removeItem(claimKey(ownerId, agentId)); } catch { /* ignore */ }
}
