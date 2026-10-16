import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InvestigationReview } from "../components/InvestigationReview";

// #58 RESEARCH-RUNTIME-LOCAL: an operating-release source declares with its fixed limits and labels stand-in facts.
const mocks = vi.hoisted(() => ({ historySources: vi.fn(), historyList: vi.fn(), historySave: vi.fn(), jobs: vi.fn(),
  ApiError: class extends Error { status = 503; detail = "Unavailable"; code = "service_unavailable"; } }));
vi.mock("../lib/api", () => ({
  ApiError: mocks.ApiError,
  api: {
    investigationProposal: async () => { throw new mocks.ApiError("none"); },
    investigations: async () => ({ declarations: [] }),
    effectRuns: async () => ({ runs: [] }),
    historySources: (...args: unknown[]) => mocks.historySources(...args),
    historyInvestigations: (...args: unknown[]) => mocks.historyList(...args),
    saveHistoryInvestigation: (...args: unknown[]) => mocks.historySave(...args),
    investigationJobs: (...args: unknown[]) => mocks.jobs(...args),
    get: async () => ({ intake: { content: { original_request: "test request" } } }),
    researchBudget: async () => null,
    nansenReports: async () => ({ available: false, jobs: [] }),
  },
}));

const LIMITS = { provider_requests: 27, compute_seconds: 30, max_pages: 2, max_rows: 200, max_bytes: 1048576, deadline_seconds: 600 };
const RELEASE = { release_id: "stand-in-native/1", sha256: "a".repeat(64), kind: "STAND_IN", evidence_class: "RELEASE_STAND_IN_RESPONSE",
  transport_kind: "LOOPBACK_HTTP", history: { source_id: "release-stand-in/1", source_version: "envio-hypersync/1", limits: LIMITS,
    client_bounds: {}, endpoint_hosts: { ENVIO_HYPERSYNC: "127.0.0.1", QUICKNODE_JSON_RPC: "127.0.0.1" },
    time_basis: { event_time: "BLOCK_TIMESTAMP", collection_time: "APPLICATION_CLOCK" }, required_coverage: "COMPLETE_SCAN" } };
const SOURCE = { source_id: "release-stand-in/1", title: "Stand-in release over native-syn-qualified/1 (not provider data)",
  evidence_class: "RELEASE_STAND_IN_RESPONSE", content_label: "SYNTHETIC_FIXTURE", profile_version: "p07.market_dataset_profile/1",
  profile_sha256: "f".repeat(64), market: { network: "MONAD", pool_address: "0xd1d1", base_asset: "0xd3d3", quote_asset: "0xd2d2" },
  window: { start: "2026-09-25T10:00:00Z", end: "2026-09-25T12:00:00Z" }, history_provider: "ENVIO_HYPERSYNC",
  page_requests_recorded: 2, available: true, release: RELEASE,
  transport: { history_provider: "ENVIO_HYPERSYNC", provider_version: "envio-hypersync/1", corroboration_provider: "QUICKNODE_JSON_RPC",
    corroboration_sample_size: 24, provider_requests_needed: 27, clients: "P07_HTTP_CLIENTS_OPERATING_RELEASE" } };
const DECLARATION = {
  declaration: { record_id: "rel-decl-1", schema_version: "p08.investigation-declaration/3", created_at: "",
    content: { schema_version: "p08.investigation-declaration/3", original_request: "test request",
      declaration_state: "PRE_OUTCOME_DECLARED", outcome_labels_read: false,
      edge_spec: { hypothesis: "Rises continue", claim: { status: "DESCRIPTIVE_ONLY", text: "Describe only." } },
      configuration: { source: { source_id: SOURCE.source_id, profile_sha256: SOURCE.profile_sha256, evidence_class: SOURCE.evidence_class },
        market: SOURCE.market, window: SOURCE.window, direction: "DESCRIPTIVE", resource_bounds: LIMITS, evaluation_plan: [], partitions: [] },
      rule_map: { rules: [], binding_state: "PENDING_DATASET_QUALIFICATION", control: "UNTRIGGERED_DECISIONS" },
      frozen: { configuration_sha256: "c".repeat(64), rule_map_sha256: "r".repeat(64), source_profile_sha256: "f".repeat(64),
        frozen_at: "", operating_release_id: "stand-in-native/1", operating_release_sha256: "a".repeat(64) } } },
  access_history: [{ event: "DECLARATION_SAVED", provider_queries: 0, outcome_labels_read: false }],
};

describe("operating-release source", () => {
  it("shows the release, fixes the bounds and declares with the release limits exactly", async () => {
    const user = userEvent.setup();
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE] });
    mocks.historyList.mockResolvedValue({ declarations: [] });
    mocks.historySave.mockResolvedValue(DECLARATION);
    mocks.jobs.mockResolvedValue({ jobs: [] });
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await screen.findByRole("option", { name: SOURCE.title });
    await user.selectOptions(screen.getByLabelText("Recorded source"), SOURCE.source_id);
    const release = screen.getByTestId("history-source-release");
    expect(release).toHaveTextContent("Operating release stand-in-native/1 (stand-in), RELEASE_STAND_IN_RESPONSE.");
    expect(release).toHaveTextContent("Stand-in responses on this server (loopback http), not provider data.");
    expect(release).toHaveTextContent("27 provider requests, 2 pages, 200 rows, 1048576 bytes, 30 compute seconds and a 600 s deadline");
    expect(release).toHaveTextContent("Endpoint hosts: 127.0.0.1, 127.0.0.1. Credentials stay on the server.");
    const requests = screen.getByLabelText("Bound provider_requests");
    expect(requests).toHaveValue("27");
    expect(requests).toHaveAttribute("readonly");
    await user.type(screen.getByLabelText("Your hypothesis in your own words"), "Rises continue");
    await user.type(screen.getByLabelText("Rule 1 lookback buckets"), "2");
    await user.type(screen.getByLabelText("Rule 1 return threshold"), "0.004");
    await user.type(screen.getByLabelText("Rule 1 volume threshold"), "100");
    await user.click(screen.getByRole("checkbox", { name: /before any data is read/ }));
    await user.click(screen.getByRole("button", { name: "Save history declaration" }));
    await screen.findByText(/Declaration saved before any collection/);
    const body = mocks.historySave.mock.calls[0][1];
    expect(body.configuration.resource_bounds).toEqual(LIMITS);
    expect(body.configuration.source.evidence_class).toBe("RELEASE_STAND_IN_RESPONSE");
    expect(body.configuration.permitted_access).toEqual(["RELEASE_STAND_IN_RESPONSE"]);
    expect(await screen.findByTestId("history-declaration-release")).toHaveTextContent(`stand-in-native/1 · ${"a".repeat(64)}`);
  });

  it("labels a release job's transport facts as stand-in responses with hashes kept", async () => {
    const user = userEvent.setup();
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE] });
    mocks.historyList.mockResolvedValue({ declarations: [DECLARATION] });
    const dataset = { dataset_id: "ds-r", content_sha256: "s", hashes_verified: {}, summary: { source_id: SOURCE.source_id,
      status: "COMPLETE", stop_reason: "COMPLETE", verdict: { overall: "QUALIFIED" }, binding_state: "QUALIFIED_BINDING",
      unavailable_states: [], provider_requests: { ENVIO_HYPERSYNC: 2, QUICKNODE_JSON_RPC: 25 },
      provider_requests_state: "MEASURED_CLIENT_CALLS", evidence_class: "RELEASE_STAND_IN_RESPONSE", content_label: "SYNTHETIC_FIXTURE" },
      transport: { envio_pages_framed: 2, client_calls: { ENVIO_HYPERSYNC: 2, QUICKNODE_JSON_RPC: 25 }, chain_id: 143, chain_network: "MONAD",
        corroboration: { class: "COMPLETE", sample_size: 24, population_size: 24, mismatches: 0 }, corroboration_reason: null,
        recorded_declarations: ["decimals"], clients: "P07_HTTP_CLIENTS_OPERATING_RELEASE",
        client_classes: { ENVIO_HYPERSYNC: "HttpEnvioQueryClient", QUICKNODE_JSON_RPC: "HttpQuickNodeRpcClient" },
        transport_label: "RELEASE_LOOPBACK_HTTP_TRANSPORT", transport_kind: "LOOPBACK_HTTP", requests_hashed: 27,
        endpoint_hosts: { ENVIO_HYPERSYNC: "127.0.0.1", QUICKNODE_JSON_RPC: "127.0.0.1" },
        operating_release: { release_id: "stand-in-native/1", sha256: "a".repeat(64), kind: "STAND_IN" } } };
    mocks.jobs.mockResolvedValue({ jobs: [{ job_id: "job-r", declaration_id: "rel-decl-1", request_key: "k", operation_id: "o",
      state: "REPORTED", terminal_reason: null, budget: { reserved: { provider_requests: 27 }, consumed: { provider_requests: 27 } },
      deadline_at: "", cancel_requested_at: null, created_at: "", events: [], dataset, report: null }] });
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await user.click(await screen.findByRole("button", { name: "Open this declaration" }));
    const facts = await screen.findByTestId("history-transport");
    expect(facts).toHaveTextContent("Operating release stand-in-native/1 through the accepted P07 HTTP clients (HttpEnvioQueryClient, HttpQuickNodeRpcClient) over loopback http.");
    expect(facts).toHaveTextContent("Stand-in responses, not provider data; 27 request hashes kept; endpoint hosts 127.0.0.1, 127.0.0.1:");
    expect(facts).not.toHaveTextContent("Authored HTTP responses");
    expect(screen.queryByTestId("history-payload-binding")).toBeNull(); // an unbound dataset shows no binding line
  });

  it("shows a bound job's payload binding and a mismatch reason, never upgrading the saved verdict", async () => {
    const user = userEvent.setup();
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE] });
    mocks.historyList.mockResolvedValue({ declarations: [DECLARATION] });
    const binding = (status: string, reason: string | null) => ({ status, required_by: "RELEASE_BINDING", reason,
      evidence_class: "SYNTHETIC", handoff_sha256: "e".repeat(64), report_sha256: status === "PASS" ? "9".repeat(64) : null,
      checker_sha256: "1".repeat(64), claim_limit: "Payload binding only." });
    const job = (id: string, status: string, reason: string | null) => ({ job_id: id, declaration_id: "rel-decl-1",
      request_key: id, operation_id: "o", state: "REPORTED", terminal_reason: null,
      budget: { reserved: { provider_requests: 7 }, consumed: { provider_requests: 7 } }, deadline_at: "",
      cancel_requested_at: null, created_at: "", events: [], report: null,
      dataset: { dataset_id: `ds-${id}`, content_sha256: "s", hashes_verified: {}, transport: null,
        summary: { source_id: SOURCE.source_id, status: "COMPLETE", stop_reason: "COMPLETE", verdict: { overall: "QUALIFIED" },
          binding_state: "QUALIFIED_BINDING", unavailable_states: [], provider_requests: null,
          provider_requests_state: "MEASURED_CLIENT_CALLS", evidence_class: "RELEASE_STAND_IN_RESPONSE",
          content_label: "SYNTHETIC_FIXTURE" },
        payload_binding: binding(status, reason) } });
    mocks.jobs.mockResolvedValue({ jobs: [job("job-pass", "PASS", null), job("job-bad", "MISMATCH", "BUCKET_2:PAYLOAD_DIFFERS")] });
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await user.click(await screen.findByRole("button", { name: "Open this declaration" }));
    const lines = await screen.findAllByTestId("history-payload-binding");
    expect(lines.map((line) => line.getAttribute("data-status"))).toEqual(["PASS", "MISMATCH"]);
    expect(lines[0]).toHaveTextContent(`Payload binding: PASS against the SYNTHETIC handoff ${"e".repeat(64)}; report ${"9".repeat(64)}.`);
    expect(lines[0]).toHaveTextContent("not provider provenance");
    expect(lines[1]).toHaveTextContent("Payload binding: MISMATCH (BUCKET_2:PAYLOAD_DIFFERS)");
    expect(lines[1]).toHaveTextContent("cannot supply a market or a replay. Its saved verdict and data stay unchanged.");
    expect(screen.getAllByText(/QUALIFIED, QUALIFIED_BINDING/)).toHaveLength(2); // the saved verdict is shown as saved
  });
});
