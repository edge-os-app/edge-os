import type { Bundle, EffectRunBody, EffectRunResult, InvestigationProposal, InvestigationSaveResult,
  PublicationResult, RequestSummary, Sample } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, public detail: string, public findings: { path: string; detail: string }[] = []) {
    super(`${status} ${code}`);
  }
}

export type TokenSource = () => Promise<string | null>;

let tokenSource: TokenSource = async () => null;
let onUnauthorized: () => void = () => {};

/** Wire the single token function. Production wires Privy's getAccessToken. Nothing else supplies a token. */
export function setTokenSource(source: TokenSource): void { tokenSource = source; }
export function setUnauthorizedHandler(handler: () => void): void { onUnauthorized = handler; }

export function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");
}

const REQUEST_TIMEOUT_MS = 30_000;

async function send(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${apiBase()}${path}`, { ...init, headers, cache: "no-store", signal: controller.signal });
  } finally { clearTimeout(timer); }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<{ status: number; body: T }> {
  let response: Response;
  try {
    response = await send(path, init, await tokenSource());
    if (response.status === 401) {
      const first = await response.clone().json().catch(() => ({}));
      if (first.code === "auth_expired") response = await send(path, init, await tokenSource());
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw new ApiError(0, "timeout", "The service did not answer in time. Check the saved record before repeating a change.");
    throw new ApiError(0, "network_error", "The service could not be reached.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) onUnauthorized();
    const findings = Array.isArray(body.findings) ? body.findings : [];
    throw new ApiError(response.status, body.code ?? "error", findings[0]?.detail ?? "The request failed.", findings);
  }
  return { status: response.status, body: body as T };
}

export const api = {
  me: () => request<{ user_id: string }>("/v1/me").then((r) => r.body),
  interpreter: () => request<{ interpreter: { kind: string; id: string; notice: string }; samples: Sample[] }>("/v1/interpreter").then((r) => r.body),
  list: () => request<{ requests: RequestSummary[]; has_more: boolean }>("/v1/research/requests").then((r) => r.body),
  get: (id: string) => request<Bundle>(`/v1/research/requests/${id}`).then((r) => r.body),
  investigationProposal: (id: string) => request<InvestigationProposal>(`/v1/research/requests/${id}/investigation-proposal`).then((r) => r.body),
  investigations: (id: string) => request<{ declarations: InvestigationSaveResult["declaration"][]; access_history: InvestigationSaveResult["access_history"] }>(`/v1/research/requests/${id}/investigations`).then((r) => r.body),
  investigation: (id: string, declarationId: string) => request<InvestigationSaveResult>(`/v1/research/requests/${id}/investigations/${declarationId}`).then((r) => r.body),
  saveInvestigation: (id: string, body: unknown) => request<InvestigationSaveResult>(`/v1/research/requests/${id}/investigations`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  effectRuns: (id: string) => request<{ runs: EffectRunResult[] }>(`/v1/research/requests/${id}/effect-runs`).then((r) => r.body),
  effectRun: (id: string, runId: string) => request<EffectRunResult>(`/v1/research/requests/${id}/effect-runs/${runId}`).then((r) => r.body),
  adoptEffectRun: (id: string, declarationId: string, body: EffectRunBody) =>
    request<EffectRunResult>(`/v1/research/requests/${id}/investigations/${declarationId}/effect-runs`,
      { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  executeEffectRun: (id: string, runId: string, body: { operation_id: string; idempotency_key: string }) =>
    request<EffectRunResult>(`/v1/research/requests/${id}/effect-runs/${runId}/attempts`,
      { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  submit: (body: unknown) => request<Bundle>("/v1/research/requests", { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  answer: (id: string, body: { previous_revision_id: string; question_id: string; choice_id: string }) =>
    request<Bundle>(`/v1/research/requests/${id}/clarifications`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  publish: (strategyId: string, body: unknown) =>
    request<PublicationResult>(`/v1/strategies/${strategyId}/revisions`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  revision: (strategyId: string, revisionId: string) =>
    request<{ revision_id: string; content_sha256: string; manifest_sha256: string; created_at: string; stored_hash_matches_content: boolean; stored_manifest_hash_matches_content: boolean }>(
      `/v1/strategies/${strategyId}/revisions/${revisionId}`).then((r) => r.body),
  operation: (id: string) => request<PublicationResult>(`/v1/operations/${id}`).then((r) => r.body),
};
