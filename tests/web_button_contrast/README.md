# Primary button contrast check

Real-Chromium regression for `.btn-primary` text contrast (at least 4.5) through hover, active, busy-disabled under the pointer, re-enable during the default transition, keyboard focus and reduced motion. It loads `apps/web/app/organic.css` then `apps/web/app/app.css`, the order used by `apps/web/app/layout.tsx`, into a minimal page. It proves the stylesheet behavior, not the mounted application journey.

It reuses the locked `tests/p03` Playwright and axe packages. No new dependency.

```sh
(cd tests/p03 && npm ci)
ln -s ../p03/node_modules tests/web_button_contrast/node_modules
BUTTON_CONTRAST_EVIDENCE_DIR=/tmp/button-contrast \
  tests/p03/node_modules/.bin/playwright test -c tests/web_button_contrast/playwright.config.mjs
```

Projects: `desktop-1280` and `mobile-390-hover-none` (touch emulation, `(hover: none)` asserted). Each enabled sample is read in the page on every animation frame until the button's transitions finish; the first sample is taken in the same task as the state change.
