# Hermes application launcher: local verification recipe, identities and limits

Task `HERMES-LIVE-PATH-L1-20261015-LOCAL-v1`. Base `19e6063ec72fc676e479a1d9f477c2af3e23020a`. Status: LOCAL. This note approves nothing: no release, provider, model, price, key, network, spending, deployment, hosting or recording. Both registries (`RELEASE_DEFINITIONS`, `APPROVED_ACTUAL_RELEASES`) stay empty, so the launcher refuses by default. Every positive result below uses a SYNTHETIC record that is approved only inside a test.

## 1. Launcher

`scripts/hermes_app_mount/serve_relay_application.py`, `main(argv=None) -> int`. Run it from `apps/api` with the API's Python, the usual `EDGE_OS_*` environment and `EDGE_OS_INTERPRETER=hermes_local`:

```
python ../../scripts/hermes_app_mount/serve_relay_application.py \
    --handoff-path <operator handoff.json> --handoff-sha256 <its SHA256> --run-id <stable process id> --port <1-65535>
```

| Step | Behavior |
|---|---|
| Arguments | `--port` must be a whole number from 1 to 65535; argparse exits 2 before settings are read. |
| Open | `open_hermes_application(settings, handoff_path=..., handoff_sha256=..., run_id=...)`. Its `MountRefused` (production, another interpreter, two approved definitions, any handoff fault) prints `refused: <reason>` and returns 2. |
| No release | `None` (the default) prints `refused: no approved Hermes relay application release: nothing to serve` and returns 2. The handoff is not opened; no engine, key, socket or Docker effect occurs. |
| Serve | `create_app(settings, hermes_runner=opened.runner, hermes_config=opened.config)`, one JSON line (`serving` release id, host, port, pid, number of startup recoveries), then `uvicorn.run(app, host="127.0.0.1", port=..., log_level="warning")`. |
| Exit | App creation and serving sit inside `try/finally`; `opened.close()` runs exactly once and disposes only the application's own engine. The relay operator owns relay start and shutdown; the launcher never stops, restarts or removes relay resources. |

The interpreter label (`/v1/interpreter` and every request bundle) keeps `{kind, id, notice}`. A `LIVE` configuration shows `HERMES_LIVE_RELEASE`, the release id, and a notice naming the release, provider, model and model budget that says it describes the configuration only and does not show a completed model call. The local fake provider label is unchanged. See `docs/qualification/hermes-application-release/CONTRACT.md` section 7.

## 2. What the checks prove

| Case | Check | Observation required |
|---|---|---|
| Empty ordinary registries | `apps/api/tests/test_hermes_application_launcher.py` | exit 2 before the handoff, an engine or the server |
| Production, other interpreter, invalid port, wrong handoff | same file | exit 2 at the existing boundary; nothing created |
| App creation or server exception | same file | `close` once; the operator's relay is not touched |
| Serving | same file | exact runner/config pair, `127.0.0.1`, the given port, `close` once after serving |
| Labels | same file | fake label unchanged; LIVE label names release/provider/model, claims no call, keeps SYNTHETIC visible |
| Image identity | `apps/api/tests/test_hermes_relay_composition.py` | the definition and the handoff bind one Docker image id; tags, registry digests and other ids refused; the job launches by that id |
| Request options and cache field | `tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py` (pure) | AUTHORED adds nothing; every bound field maps to the Hermes option that sends it; cache field exact across record, body, runner and binding |
| Synthetic accepted request | same file, `-k test_docker_` | genuine pinned job, guard, file channel, composition and PostgreSQL ledger; only `relay_service.send_once` and test-local approval data are replaced; exactly one counted send |
| Wire | same | the captured send body has every bound field (`stream`, `provider`, `reasoning`, `response_format`, `prompt_cache_options`), `model`, `max_tokens` and `session_id = p05-<attempt>`, and its SHA256 equals the bytes the job's guard admitted |
| Save and reopen | same | HTTP 201, one attempt and reservation, matching SQL owner/request/grant, exact charge, unchanged reopened head and attempts, another owner 404 |
| Cost mismatch or lost reply | same | no accepted text, full reservation UNKNOWN, retry 409, reopen sends nothing |
| Isolation and cleanup | same | job network blocked and no credential mounted; leak scan clean; no owned container left; no foreign container, network or volume removed; default bridge id unchanged |

The relay code runs in the test process in the Docker case so that its provider send can be replaced. The job, its container, the file channel, the guard, the relay admission and body checks, the host runners and the ledger are the accepted code. The relay's own container topology and egress gateway are proved by the accepted relay tests, not here.

## 3. Pure check recipe (no Docker, database or network)

Run with the read-only integration API interpreter, this candidate's own source first on the path, no bytecode and no pytest cache. `DOCKER_HOST` names a socket that does not exist, so an accidental Docker call fails.

```
cd apps/api
env PYTHONDONTWRITEBYTECODE=1 DOCKER_HOST=unix:///nonexistent/docker.sock <api python> -B -m pytest -p no:cacheprovider -q \
    tests/test_hermes_application_launcher.py tests/test_hermes_relay_composition.py \
    -k "not (sent_once or provider_cost or interrupted_attempt or two_instances or no_longer_names)"
cd ../..
env PYTHONDONTWRITEBYTECODE=1 DOCKER_HOST=unix:///nonexistent/docker.sock PYTHONPATH=apps/api/src:scripts/p03 \
    <api python> -B -m pytest -p no:cacheprovider -q --rootdir=. -c /dev/null \
    tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py -k "not test_docker_" \
    tests/hermes_provider_relay/test_relay_actual_release.py tests/hermes_provider_relay/test_relay_admission.py \
    tests/hermes_provider_relay/test_relay_turn_runner_actual.py tests/hermes_provider_relay/test_relay_service_actual.py
```

## 4. Runtime recipe (separate capacity grants; not run in the source stage)

1. Build once. From `apps/api`, one `PinnedHermesImage(<run id>, <new private workdir>).build()` of the committed candidate (pinned Hermes `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, clean). Keep the image and its `source_identity.json` receipt for every later actor; do not rebuild per actor. Record candidate and tree, `hermes_turn_job.py`, `Dockerfile`, `uv.lock` and `pyproject.toml` SHA256, the image id and the build log.
2. Shape proof. From the repository root, with the session PostgreSQL fixture and `HERMES_APP_IMAGE_RECEIPT=<receipt>`: `tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py` (all 21 tests: 18 pure, 3 Docker). The module reuses the receipted image by id and checks that the image's `/opt/p05/hermes_turn_job.py` has the candidate's SHA256.
3. Application and composition. From `apps/api`: `tests/test_hermes_application_launcher.py` (15), `tests/test_hermes_relay_composition.py` (73, including 10 mounted), `tests/test_hermes_research_flow.py` (68, the fake label and saved path).
4. Unchanged AUTHORED callers through the new job. Direct `tests/hermes_interpretation/test_pinned_hermes.py::test_authored_case_through_actual_hermes[concrete-thesis]` and `[provider-503]`; guarded `tests/hermes_interpretation/provider_safeguards/test_pinned_hermes_guard.py::test_a_valid_turn_is_admitted_once_charged_exactly_and_leaks_nothing` and `::test_the_guard_in_the_container_refuses_a_request_that_differs_from_the_policy`; transport `tests/hermes_job_support/test_transport_job_through_pinned_hermes.py::test_one_admitted_request_reaches_the_transport_with_the_host_credential_and_every_identity_is_the_attempt` and `::test_a_request_the_guard_refuses_never_reaches_the_transport_and_frees_its_reservation`; relay `tests/hermes_provider_relay/test_relay_application_mount.py` (2). These modules use their directory's session image fixture, which builds from the candidate and removes its own tag at the end of the session (section 5).

Each actor records its own commands, process imports, timing, exit status, failures, artifact hashes and cleanup. A supplied result is not another actor's execution.

## 5. Limits

- Synthetic only. The record, schema, price snapshot, CA bundle and key are test inputs; the provider reply is authored. Nothing here shows that OpenRouter, the routed provider or the documented `prompt_cache_options` setting behave this way, or how a real call is billed. E1-COST1 keeps any other cost UNKNOWN with full liability.
- The relay process in the Docker shape proof runs on the host, not in its container, so that only its send is replaced. Its egress gateway is not used.
- Reopening in a second application instance is not process-crash recovery.
- The unchanged AUTHORED Docker modules build their own session image (their fixtures are outside this task's lease). With an unchanged build context the build should reuse Docker's layer cache, but each such session still runs a build. Reusing one receipted image there needs a lease on those fixtures or a controller decision.
- Browser display of the new label is a separate check.
- Activation still needs an approved record and definition in one reviewed change, the qualification packet, the ledger price row decision, the operator start and deployment authority.
