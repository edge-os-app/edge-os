# Native controller guard activation pilot

Task CTRL-ACT-L3-01. Base `68cde4d1500c2c0aacdbb75639c4213f40b83092`.
This record separates native host evidence, manual enrollment and checked-send behavior. It does not qualify every live lane.

## Demonstrated setup cause

The lane3 terminal displayed Codex CLI 0.160.1, but its original tools ran under the managed 0.161.0 app-server daemon. Both login and non-login tool shells lacked `TMUX_PANE`; native `tmux-bridge id` failed. No current-session binding or automatic receipt existed. The accepted SessionStart adapter returns without a receipt when native bridge identity fails. Stop permits an unbound session.

Same-session `codex --no-daemon resume SESSION_ID` restored actual worker %5 identity while preserving task, model and worktree. Gate %8 separately recovered. These observations establish the tool-environment defect. Initial native SessionStart invocation was not captured, so they do not prove every reason for the earlier missing event.

The [official daemon contract](https://github.com/openai/codex/blob/main/codex-rs/app-server-daemon/README.md) describes shared environment inheritance. The [native CLI definition](https://github.com/openai/codex/blob/main/codex-rs/tui/src/cli.rs) supplies `--no-daemon`. Current Context7 sources were retrieved on 2026-10-08. No daemon restart, global trust change, environment spoof or package upgrade occurred.

## Repairs found through native delivery

An empty Codex composer with `? for shortcuts` and a warning footer was rejected as foreign input. A regression failed with BLOCKED instead of SUBMITTED. The footer matcher now accepts that observed shortcut row while retaining its existing structural-boundary requirement.

The live gate's 80-column viewport wrapped the Smux header across two rows. The old matcher could not verify the complete own draft. The replacement joins at most two header rows, verifies the actual sender and exact body, then retains existing submission and foreign-draft checks. Longer unknown wraps remain blocked. A separate failing regression covers this observed header and adversarial foreign continuations.

One gate setup relay used manual exact-input recovery after its helper recorded BLOCKED before Enter. The complete saved pointer/hash was visible, Enter was sent once, and the submitted transcript and empty composer were confirmed. The terminal helper row remains BLOCKED. This raw recovery is not a helper-verified delivery.

## Host and source boundaries

Root project hooks still invoke the accepted integrated helper SHA256 `b12f56e199c6b7fb815953af0a3ef0664ab2032e323d25a3fa6a3a0da8d703a7`. Native SessionStart and Stop evidence below belongs to that deployed command. The repaired checked-send CLI uses the task-owned worker helper. AST comparison shows only `_is_native_footer` and `_message_at` changed. This establishes static lifecycle continuity, not native invocation of a replacement hook command. Shared configuration was not changed during proof.

Worker%5 and gate %8 use explicitly labelled manual existing-session bindings. Worker is ACTIVE during work. Gate is AWAITING_EVENT at 0/3 before candidate arrival. Their manual bindings are not automatic receipts. The worker's actual native Stop requested one corrective continuation for its missing report and approved work; the synthetic report obligation was then restored.

New task-owned Codex 0.160.1 and Claude Code 2.1.294 sessions used the unchanged root hook commands and one shared private state directory. Each produced a real matching startup receipt with actual session, pane, cwd, task and approved assignment fingerprint. Probe tasks carry no previous-ticket obligations. The expired unconsumed lane-worker assignment was archived before the existing assign helper legally replaced it. No consumption or receipt row was written by hand.

## Native delivery checks

The final Codex report passed with helper SHA256 `ad7f7d496a55e5b20abb15b83fb0b7a752127d91341c7388d879da1a86c653cb`. Its original report SHA256 is `c3c9f9d01c41eaf32e14bfc58fa90709799b79df30973976f9edd4a8d22067f0`. Seven native capture hashes and both input/submission pairs were independently checked. Actor %321 used Codex 0.160.1, Sol6.1/high and 120×200. Its two targets were 80×200. Missed-Enter recovery submitted the same draft with zero new messages and one Enter. Controlled delayed display submitted once. Both duplicate checks performed zero actions. Native Stop requested one correction for approved work, missing report and unfinished delivery. Original task-owned binding state was restored to AWAITING_EVENT afterward.

The fresh Claude 2.1.294 startup receipt passed. Final Claude native Stop and delivery proof remain pending. Its v3 packet submission is terminal UNCONFIRMED after one Enter. No Enter retry occurred. The builder reports Claude capacity unavailable until about noon on 2026-10-08, Africa/Kinshasa. That is reported availability, not a measured reset time. This record remains incomplete for the two-host acceptance requirement.

 Separate task-owned targets cover missed Enter, controlled delayed display and foreign input. A controlled failed read preserves TYPED without Enter. The native Stop hook must request correction before same-event recovery. Controlled stale captures remain distinct from naturally observed display races. Terminal uncertain events are preserved without another Enter.

The final helper rejected an actual task-owned foreign draft before typing, preserved the exact native capture and performed zero actions on the duplicate event. Both parser repairs retain caller-wide validation, historical event rows and draft ownership.

## Verification and remaining limits

`RUN_LIVE_TMUX=1 python3 -B -m unittest -v tests.test_controller_guard` passed 94 tests, including SessionStart, Stop, checked-send and isolated live tmux cases. No separate `tests/test_controller_session_start.py` exists at the assigned base; lifecycle cases reside in the guard suite.

`python3 -B docs/contracts/p02/check_contract.py` passed 39 fixtures and 10 record examples. `python3 -B -m unittest -v test_p04` from `docs/qualification/p04` passed 16 tests. Both regression failures and subsequent green runs are retained privately. AST and Git whitespace checks passed. The suite retained existing SQLite ResourceWarnings about unclosed connections. No new dependency was added.

Native fork/compaction, crash/sleep recovery, subscription exhaustion and protection of other live lanes remain unqualified. Gate1's stale synthetic pilot binding and P03/P16 state were preserved. Later restoration of that pilot must use its actual current session and task through the assigned gate, rather than copying lane3 state. Local integration and any changed shared hook command remain controller actions after exact-candidate reviews. No push or main merge is authorized.
