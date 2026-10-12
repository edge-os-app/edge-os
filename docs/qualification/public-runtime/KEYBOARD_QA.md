# F5: keyboard QA (owned surfaces) and screen-reader status

Scope: the surfaces this milestone owns. These are the connected-agent form, Funding (`AgentFunding`), and the read-only "Saved connected state" panel (`ServiceAccountState`). Actions and Authority use the same button and focus styles; Tab order and focus visibility were checked on Funding. The research, adoption and replay surfaces are not in this lease and keep their earlier status.

## Method

`tests/p03/runtime.spec.mjs` (test "F5: keyboard-only pass …") runs inside the mapped verifier at 1280px and 390px:

1. It opens `/#/funds?agent=<saved agent>` as a signed-in test owner.
2. It focuses the Agent ID field and presses Tab 40 times. At each stop it records the element, its name, its region and whether a focus indicator is visible (outline wider than 0 or a box shadow).
3. It asserts that "Open agent", the Asset select and "Check deposits" are reached, and that every stop has a visible indicator.
4. It moves to "Check deposits" with Tab only and presses Enter. The write completes and no alert is shown.

The stop list for each width is saved in the run evidence as `ui/keyboard-qa.json`.

## Result

Local PASS at 1280px and 390px (verifier run `r58rt111402`). The pass criteria above are assertions, so a PASS of the verifier step "projection panel, failed read-back pause and keyboard pass" means every criterion held at both widths.

- **Tab cycle (37 stops, same order at both widths):** Agent ID → Open agent → Asset select → Amount → Check deposits → Load more records → Skip to content → Research → Agents → Positions → Funds → Sign out → Agents → Positions → Funds. The cycle then repeats.
- **Disabled controls:** "Save reviewed deposit" is disabled while the amount is empty, so Tab skips it. That is expected.
- **Focus indicator:** every stop had a visible indicator.
- **Enter:** Enter on "Check deposits" ran the write without an alert.
- **Panel without stops:** the read-only "Saved connected state" panel has no interactive element unless a load fails ("Try again").

## Screen reader

NOT_RUN. No screen reader (VoiceOver, NVDA) was operated in this session; the automated browser cannot stand in for one. Automated axe checks (WCAG 2 A/AA, serious and critical) run on the projection page at both widths. A manual screen-reader pass stays open before public use.
