// #58 operating-release research labels. The server composes at most one release; every value here comes from it.
// A stand-in release serves stand-in responses on this server; it is never provider data.
import type { HistorySource, TransportSummary } from "./api";

export const RELEASE_CLIENTS = "P07_HTTP_CLIENTS_OPERATING_RELEASE";

export interface OperatingReleaseView {
  release_id: string; sha256: string; kind: "STAND_IN" | "ACTUAL"; evidence_class: string; transport_kind: string;
  history?: {
    source_id: string; source_version: string; limits: Record<string, number>;
    client_bounds: Record<string, number>; endpoint_hosts: Record<string, string>;
    time_basis: Record<string, string>; required_coverage: string;
  };
}

interface ReleaseTransport {
  transport_kind?: string; requests_hashed?: number; endpoint_hosts?: Record<string, string> | null;
  operating_release?: { release_id: string; sha256: string; kind: string };
}

/** The operating release that serves this source, or null for a recorded source. */
export function sourceRelease(source: HistorySource | null): OperatingReleaseView | null {
  return (source as (HistorySource & { release?: OperatingReleaseView }) | null)?.release ?? null;
}

/** The fixed resource bounds a release source must be declared with. */
export function releaseBounds(release: OperatingReleaseView): Record<string, number> | null {
  return release.history ? { ...release.history.limits } : null;
}

export function describeRelease(release: OperatingReleaseView): string {
  const limits = release.history?.limits ?? {};
  const hosts = Object.values(release.history?.endpoint_hosts ?? {}).join(", ");
  const served = release.kind === "STAND_IN"
    ? `Stand-in responses on this server (${release.transport_kind.replaceAll("_", " ").toLowerCase()}), not provider data.`
    : "Provider responses under an approved release.";
  return `Operating release ${release.release_id} (${release.kind.replace("_", "-").toLowerCase()}), ${release.evidence_class}. ${served} `
    + `Fixed by the server: ${limits.provider_requests} provider requests, ${limits.max_pages} pages, ${limits.max_rows} rows, `
    + `${limits.max_bytes} bytes, ${limits.compute_seconds} compute seconds and a ${limits.deadline_seconds} s deadline. `
    + `Endpoint hosts: ${hosts}. Credentials stay on the server.`;
}

/** Release facts in a job's transport summary, or null for other sources. */
export function transportRelease(transport: TransportSummary): ReleaseTransport | null {
  // The shared summary type names only the authored clients label; read the served label as plain text.
  const clients: string | undefined = transport.clients;
  return clients === RELEASE_CLIENTS ? transport as TransportSummary & ReleaseTransport : null;
}

/** The release a saved declaration froze, or null. */
export function declarationRelease(frozen: Record<string, unknown>): { id: string; sha256: string } | null {
  const id = frozen.operating_release_id, sha256 = frozen.operating_release_sha256;
  return typeof id === "string" && typeof sha256 === "string" ? { id, sha256 } : null;
}
