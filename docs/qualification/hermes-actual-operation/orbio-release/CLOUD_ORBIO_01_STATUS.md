# CLOUD-ORBIO-01 status

Builder-approved normal cloud session, 2026-10-30. Repository `edge-os-app/edge-os`, branch `cloud/orbio-01-route` (pushed; no PR, no merge, no force push, nothing pushed to `main` or `integration`). Status: DONE. Both internal reviews PASS on the reviewed candidate. The Orbio release is NOT approved and NOT selected.

- Reviewed candidate: `f8f5d6b` (CLOUD-ORBIO-01 review repair). The only commit after it adds this status file.
- Base: `origin/cloud/orbio-release-prep` `446206c` (on CLOUD-02 `617b9e2`), merged with `origin/integration/edge-os-mvp` `275b399` in merge commit `386ad44`. This was a merge, not a rebase.
- Path note: the Orbio draft lives in `docs/qualification/orbio-release/`, not under `hermes-actual-operation/`. This status file is at the path the ticket named.

## Commits

| Commit | What it does |
|---|---|
| `386ad44` | Merges `275b399` into `446206c`. |
| `a419f0d` | Orbio draft at its worst-case price; doc update; real-handshake TLS name and CA tests. |
| `f8f5d6b` | Review repair: one name rule; refuses numeric host forms, dot/empty path segments and unknown gateway config keys; U1–U11 labels. |
| next commit | This status file only. |

## Merge conflicts

There was one conflict, in `scripts/hermes_provider_relay/relay_supervisor.py` `_prepare`.

- Integration (HOST-SHARE-L4) added `os.chmod(root, CHANNEL_ROOT_MODE)` inside the channel-root loop.
- CLOUD-02 moved `destination = self.destination()` to after that loop.

Resolution: both were kept, with integration's chmod inside the loop and CLOUD-02's single destination line after it. Every other HOST-SHARE-L4 line merged cleanly: `RELAY_ROOT_MODE`, `SHARED_FOLDER_MODES`, `PRIVATE_FOLDER_MODE`, `ADMISSION_KEY_MODE` and the folder and key chmods.

Nothing else conflicted:
- `relay_admission.py` and `egress_gateway.py` were not changed by integration after the merge base `00f0582`.
- `hermes_relay_composition.py`, including HERMES-REPIN-L4's one image id per platform, and the HERMES-ROUTE-L4 files come from integration unchanged.
- `git diff 275b399..f8f5d6b -- apps/` is empty.

## Hard rules

1. **Exactly one approved release.**
   - `APPROVED_ACTUAL_RELEASES` holds only `3fa94dd73e53a72ca8af6cda9c8633770de89c262fa5303756c1965bb92fed8f`.
   - `RELEASE_DEFINITIONS` has one entry.
   - Nothing in `scripts/`, `apps/` or `deploy/` references the Orbio draft.
   - The image ids are unchanged: `sha256:42541c05…` (amd64) and `sha256:2d28b6d6…` (arm64).
   - The golden file `test_release_destination_golden.py` is identical to `446206c` and passes. It checks the OpenRouter CONNECT head, SNI and request bytes.
2. **Refused, not ignored.** Each case below is refused and has a test.
   - An unknown or missing routing field.
   - A host, port or path other than the approved record's. A record naming one loads only if its own SHA256 is approved.
   - An IP address, or a numeric form that `getaddrinfo` reads as an address (new).
   - A path with an empty, `.` or `..` segment (new).
   - A gateway config with any key outside `socket`, `receipts`, `destination` and `test_resolution` (new).
   - A CA bundle hash mismatch.
   - In a real loopback handshake, a server certificate for another name (SNI swap) or from another CA. The attempt ends before any request byte or the key is sent (new `test_release_tls_name.py`).
3. **No contact with Orbio.** No key, purchase or provider call. The only outbound attempts were the four refused public GETs described below.

## Orbio draft update

**The pages could not be read.** This session tried to read <https://www.orbio.so>, <https://www.orbio.so/developers>, <https://www.orbio.so/llms.txt> and <https://www.orbio.so/api/v1/models> at 2026-10-30 09:47 UTC. The session's network policy refused all four: curl through the proxy got `CONNECT 403`, and the fetch tool got `ENOTFOUND`. No byte was received from Orbio. A web search returned only summaries of cached pages, and those summaries disagreed with each other, so the draft does not use them as sources.

**What the draft says instead.** The draft cites all four URLs. It records the ticket's 2026-10-30 pricing facts as given by the builder and not verified here: Liquidity Book tiers from 0% to 50% (about 47.5% at the top), a 5% platform fee on the discounted price, a USD 5 minimum, and "Requests use Orbio's managed OpenRouter account". The pinned model's catalogue entry is UNKNOWN (U6). Before any approval, someone must read the pages from a session or machine that allows `www.orbio.so`.

**Price snapshot.** The draft prices `openai/gpt-6.1-sol` at USD 2.1 / 10.5 per million. That is the list price of 2 / 10 at the 0% tier plus the 5% fee, so 1.05 × list, which is the most a buyer pays per token if the list rate is right. The worst-case reservation is USD 0.180768 (180,768,000 nano-USD), against OpenRouter's USD 0.17216. Re-hashed files:

| File | New SHA256 |
|---|---|
| prices | `4f83b00b…` |
| packet | `db33f21b…` (status still `DRAFT_NOT_APPROVED`) |
| record | `ce309bbd…` |

**Cost in usage data: UNKNOWN (U1).** No public documentation that has been read documents a cost field in the usage data. This session could not read the developer pages, so it does not claim the field is absent.

**Notes added to the draft:**
- A `usage.cost` at the list rate or a discounted rate does not equal the worst-case charge. Such an attempt stays UNKNOWN with full liability, so the ledger never settles low.
- A future record with `max_price` 2 / 10 would be refused by `_rate` against this snapshot.
- The USD 5 minimum is above the shared USD 2.00 ceiling.
- The look-alike sites `orbioagent.world` and `orbio-proposals.xyz` are named as not sources.

## Files changed vs `275b399` (in addition to the CLOUD-02/Orbio files from `446206c`)

| File | Change |
|---|---|
| `scripts/hermes_provider_relay/egress_gateway.py` | `host_name_refusal` (one shared rule) and `CONFIG_FIELDS` |
| `scripts/hermes_provider_relay/relay_admission.py` | uses the shared rule; path segment rule |
| `scripts/hermes_provider_relay/relay_supervisor.py` | merge resolution |
| `docs/qualification/hermes-provider-relay/CONTRACT.md` | A8 bullet for CLOUD-ORBIO-01 |
| `docs/qualification/orbio-release/ORBIO_RELEASE_DRAFT.md`, `orbio_draft_prices.json`, `orbio_draft_packet.json`, `orbio_draft_record.json` | draft update |
| `tests/hermes_provider_relay/test_orbio_release_draft.py` | assertions changed (see below) |
| `tests/hermes_provider_relay/test_release_destination.py` | new tests only |
| `tests/hermes_provider_relay/test_release_tls_name.py` | new file |

## Tests

Run from `apps/api`. Docker was started with `dockerd` and Docker Hub images were pulled through `mirror.gcr.io`, because Docker Hub returned 429.

| Command | Commit | Result |
|---|---|---|
| `uv run --frozen pytest ../../tests/hermes_provider_relay -q -p no:cacheprovider` | `f8f5d6b` | 578 passed, 65 errors (about 38 s) |
| same | merge `386ad44` | 560 passed, 65 errors |
| `uv run --frozen pytest tests -q -p no:cacheprovider -k hermes` | `f8f5d6b` | 426 passed (about 61 s). Covers `test_hermes_actual_release_binding.py`, `test_hermes_relay_composition.py` and the other `test_hermes_*` files |
| `uv run --frozen pytest tests -q -p no:cacheprovider` | merge `386ad44` | 4430 passed, 1 skipped, 1 failed (13 min 54 s) |

On the full-suite run:
- The run was on the merge commit. The later commits do not touch `apps/`, and the Hermes subset was rerun on `f8f5d6b`.
- The one failure is `test_privy_wallet_lookup.py::test_ipc_malformed_or_oversized_frames_get_a_code_only[\x00\x00\x10\x01x…]` with `ConnectionResetError`. It fails the same way on pure `275b399` in a separate worktree, so it is pre-existing on Linux and outside this ticket.

RED then GREEN:
- `test_orbio_release_draft.py`: three tests failed before the draft update and passed after it.
- `test_release_destination.py`: thirteen new cases failed before the repair and passed after it.
- `test_release_tls_name.py`: these tests describe existing behaviour, so they could not fail first. Instead, a temporary mutant with `check_hostname = False` was run, and the name test failed against it. The mutant was then reverted.

**Could not run: 65 Docker tests.** They need builder-only inputs that are absent in a cloud clone:
- 60 run `git rev-parse` on `/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent`. These are in `test_relay_through_pinned_hermes.py`, `test_relay_through_egress_gateway.py`, `test_pinned_hermes_actual_shape.py` and others.
- 4 need `HERMES_APP_IMAGE_RECEIPT`.
- 1 needs `HERMES_OPERATOR_IMAGE_RECEIPT` (`test_relay_operator.py` Docker CLI test).

**PostgreSQL** was available: the harness started `postgres:18.6-trixie` in Docker.

**Lint:** the `apps/api` ruff config reports I001 on the new tests, the same as on 29 existing relay test files. No lint gate covers these folders. `ruff --select F` passes on the changed relay files.

## Assertions changed

- `test_orbio_release_draft.py::test_the_draft_hash_chain_names_its_packet_prices_and_ca_bundle`:
  - The draft prices assertion changed from 2 / 10 to 2.1 / 10.5, because the snapshot is now the worst case.
  - The assertion that the draft prices equal the adopted prices apart from `provider` was removed. It no longer holds by design, and the new worst-case test replaces it.
  - A canonical-JSON check was added.
- Added: `test_the_draft_price_is_the_worst_case_a_buyer_pays_for_the_pinned_model` and `test_the_draft_cites_orbios_public_pages_and_no_look_alike`.
- No assertion in CLOUD-02, integration or golden tests changed. `test_release_destination.py` only gained tests.

## Reviews

Two new independent subagents with no shared context reviewed the work. Both PASS on `f8f5d6b`.

**Spec reviewer: PASS.** It checked the ticket item by item against `git diff 275b399..HEAD`.
- First round on `a419f0d`: PASS with three minors, all fixed in `f8f5d6b`:
  - the "no code changed" sentence did not name its base;
  - `UNKNOWN 1.n` references read like section numbers;
  - the builder must accept that the pages were not read.
- Re-check on `f8f5d6b`: PASS with no new findings.
- It independently confirmed the four refused CONNECTs in the proxy log, the hash chain, the price arithmetic and that integration behaviour was preserved.

**Standards and security reviewer: PASS.** It tried to make the relay send to another host:
- unknown, missing or extra routing fields;
- extra destination or record fields;
- other hosts (IP literals, `[::1]`, upper case, trailing dot, `xn--`, numeric forms);
- other ports and paths (including CRLF and `%2e`);
- unapproved records (including the Orbio draft and the approved bytes plus a newline);
- a forged supervisor release;
- a CA bundle hash swap, and a server certificate from another CA or for another name through a real gateway socket;
- gateway configs with no destination, several destinations or extra keys;
- about 20 CONNECT smuggling forms.

All were refused except the approved positive controls, and the OpenRouter bytes are unchanged.
- First round on `a419f0d`: four minors. Findings 1, 2 and 4 are fixed in `f8f5d6b`:
  - numeric host forms such as `16843009` passed the name check;
  - `//x` and `..` path segments were accepted;
  - unknown gateway config keys were ignored.
- Re-check on `f8f5d6b`: PASS with no new findings.

**Deferred follow-up:** the reviewer's finding 3, that `ActualRelease.endpoint_url` leaves out the port. It does not change where requests go, because sending uses `destination` with its port. Changing it would change the adopted release's route identity and evidence labels, so it needs its own ticket.

## Skills

The repository-named Python skills (`python-pro`, `python-code-style`, `python-anti-patterns`, `python-error-handling`, `codebase-design`, `ponytail`) are not in this cloud session's catalog. Their constraints were applied by hand:
- smallest change and reuse of existing modules;
- one shared rule instead of two copies;
- error-path tests;
- no new dependencies.

## Open for the builder

1. Accept or reject the use of builder-given 2026-10-30 Orbio facts that this session could not verify. To read the pages from a cloud session, `www.orbio.so` must be allowed in that session's network settings.
2. Read `/api/v1/models` for `openai/gpt-6.1-sol`, its list rates and any override, before any approval. The draft's section 7 lists the approval steps.
3. Decide the deferred `endpoint_url` port follow-up.
