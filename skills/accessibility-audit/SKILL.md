---
name: accessibility-audit
description: "Audit a web interface against WCAG 2.2 Level AA with automated axe-core scans plus manual keyboard and screen reader passes, mapping every finding to a success criterion with evidence and producing an accessibility-audit-report. Use when asked to audit accessibility, check WCAG, ADA, or Section 508 readiness, or review contrast, focus, ARIA, forms, or screen reader support before a release. Not for building or fixing UI (use the frontend-ship skill)."
---

# Accessibility Audit

Find the barriers that stop people from completing tasks, map each one to a
WCAG 2.2 success criterion, and back it with evidence. The stance is **scans are
a starting point, not a verdict**: never claim conformance from automated
results alone.

## When to use

- An audit of pages, flows, or design-system components is requested.
- A release, redesign, or procurement review needs an accessibility report.
- Users or testers reported a barrier and the scope of the problem is unknown.

## When not to use

- Building or remediating UI: use the `frontend-ship` skill, then re-audit.
- An independent read-only audit to run in parallel: delegate to the
  `accessibility-checker` subagent.
- General UI code review (state, rendering, bundle size): delegate to the
  `frontend-reviewer` subagent.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- **Scope:** routes, components, and critical flows (sign-in, sign-up, checkout,
  search, primary forms), plus the states to cover: errors, empty results, open
  dialogs and menus, and narrow viewports.
- **Target:** WCAG 2.2 AA unless a contract or policy names another (for example
  WCAG 2.1 AA, EN 301 549, or Section 508, which references WCAG 2.0 AA). WCAG
  2.2 has been a W3C Recommendation since October 2023.
- **How to run the app:** dev server command, seed data, and test accounts for
  authenticated pages.
- **Existing tooling:** axe in tests (`@axe-core/playwright`, `jest-axe`,
  `vitest-axe`), lint plugins (`eslint-plugin-jsx-a11y`,
  `eslint-plugin-vuejs-accessibility`), Storybook's accessibility addon,
  Lighthouse CI, or pa11y.
- **Design tokens** for color, focus styles, and spacing.
- **Assistive technology available:** VoiceOver (macOS, iOS), NVDA (Windows),
  TalkBack (Android). If none is available, say so in the report.

## Workflow

1. **Scope and baseline.** List every page, flow, and state you will audit and
   record the commit. Group by flow, because barriers matter where they block a
   task.
2. **Automated scan.** Run axe in the project's browser harness (example below)
   for each state, not only the initial load: open the dialog, trigger the
   validation errors, then scan. Treat `violations` as candidate findings and
   `incomplete` ("needs review") results as manual checks. Run lint plugins and
   any existing Lighthouse or pa11y configuration as extra signals.
3. **Keyboard pass.** Use only the keyboard through each flow:
   - Everything is operable (2.1.1) with no trap (2.1.2).
   - Focus order is logical (2.4.3) and focus is always visible (2.4.7).
   - Sticky headers, cookie banners, and chat widgets do not hide the focused
     element (2.4.11 Focus Not Obscured, Minimum).
   - A skip link or landmarks let users bypass repeated blocks (2.4.1).
   - Dialogs take focus, close on Escape, and return focus to the trigger.
   - Focus or input does not trigger an unexpected change of context (3.2.1, 3.2.2).
4. **Screen reader smoke test.** At least one pairing, such as VoiceOver with
   Safari or NVDA with Firefox or Chrome. Check page title (2.4.2), page language
   (3.1.1), landmarks and heading navigation (1.3.1), names, roles, and states of
   controls (4.1.2), image alternatives (1.1.1), labels and instructions (3.3.2),
   error identification and suggestions (3.3.1, 3.3.3), and status messages that
   are announced without moving focus (4.1.3). Without a screen reader, inspect
   the browser's accessibility tree and list the screen reader pass under Areas
   not tested.
5. **Visual and layout checks.** Contrast (see below), use of color (1.4.1),
   200% text resize (1.4.4), reflow at 320 CSS px width without two-dimensional
   scrolling (1.4.10), text spacing overrides (1.4.12), content on hover or focus
   that is dismissible and persistent (1.4.13), orientation (1.3.4), and
   auto-moving content that can be paused (2.2.2).
6. **WCAG 2.2 additions.** Check each explicitly; axe automates little of this:
   - 2.4.11 Focus Not Obscured (Minimum), AA: covered in the keyboard pass.
   - 2.5.7 Dragging Movements, AA: every drag action (sliders, sortable lists,
     maps) has a single-pointer alternative.
   - 2.5.8 Target Size (Minimum), AA: pointer targets are at least 24 by 24 CSS
     px, or undersized targets are spaced so that a 24 px circle centered on
     each does not intersect another target or another undersized target's
     circle. Exceptions: an
     equivalent control elsewhere, inline links in text, user-agent controls,
     and essential presentations.
   - 3.2.6 Consistent Help, A: help mechanisms (contact details, chat, help
     links) appear in the same relative order on each page that has them.
   - 3.3.7 Redundant Entry, A: information already entered in the same process
     is filled in or selectable, unless re-entry is essential or for security.
   - 3.3.8 Accessible Authentication (Minimum), AA: no cognitive function test
     such as remembering or transcribing a code without an alternative. Allow
     paste and password managers. Transcription or puzzle CAPTCHAs need an
     alternative; object-recognition CAPTCHAs are allowed at AA.
   - 4.1.1 Parsing was removed in WCAG 2.2. Report markup errors only when they
     cause a real failure, under 1.3.1 or 4.1.2.
7. **Verify and rate each finding.** Reproduce it, then record the criterion
   and level, the element (selector, component, and `path:line` when the source
   is available), the evidence (axe rule id, keyboard steps, screen reader
   output, measured contrast), the user impact, and a concrete fix. Rate by
   effect on the task in this flow, not by axe's per-rule impact label:
   - **Critical:** blocks a core task for some users (an unlabeled submit
     button, a keyboard trap in checkout).
   - **Serious:** major difficulty with a workaround.
   - **Moderate:** inconvenience that does not stop the task.
   - **Minor:** best-practice gaps, such as more than one `h1` or a skipped
     heading level that does not hide structure. A single `h1` per page is a
     best practice, not a WCAG requirement.
8. **Write the report** below. Remediate only if asked, then re-run the scan and
   the manual steps that found each issue.

## Reference: axe scan in Playwright

Illustrative. Place it where the project keeps browser tests; relative URLs
need `baseURL` in the Playwright config.

```ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const WCAG22_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

test('checkout has no detectable WCAG 2.2 AA violations', async ({ page }, testInfo) => {
  await page.goto('/checkout');
  await expect(page.getByRole('main')).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(WCAG22_AA).analyze();
  await testInfo.attach('axe-results', {
    body: JSON.stringify(results, null, 2),
    contentType: 'application/json',
  });
  expect(results.violations).toEqual([]);
});

test('payment dialog has no detectable violations when open', async ({ page }) => {
  await page.goto('/checkout');
  await page.getByRole('button', { name: 'Add card' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();

  const results = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags(WCAG22_AA)
    .analyze();
  expect(results.violations).toEqual([]);
});
```

## Contrast

Compute contrast from relative luminance, or use a tool that does:

1. For each sRGB channel, take the 8-bit value divided by 255 as c. Linearize:
   if c is at most 0.04045, the linear value is c / 12.92; otherwise it is
   ((c + 0.055) / 1.055) ^ 2.4. Older WCAG text uses 0.03928; no 8-bit value
   falls between the two thresholds.
2. L = 0.2126 × R + 0.7152 × G + 0.0722 × B, using the linear values.
3. Ratio = (L1 + 0.05) / (L2 + 0.05), where L1 is the lighter color.

Thresholds:

- 4.5:1 for normal text (1.4.3, AA).
- 3:1 for large text: at least 18 pt (24 CSS px) regular or 14 pt (about
  18.7 CSS px) bold (1.4.3, AA).
- 3:1 for user interface components, their states and focus indicators, and
  graphics needed to understand content (1.4.11, AA).
- 7:1 for normal text and 4.5:1 for large text at AAA (1.4.6), only when the
  target requires AAA.
- Disabled controls, pure decoration, and logos are exempt.

For example, `#767676` on white is 4.54:1 and passes for normal text. Measure
text over images, gradients, or translucent layers at the worst point.

## Guardrails

- Audit only by default. Do not change source files unless asked; when asked,
  revert or delete only files you created or changed in this session.
- Ask before destructive, irreversible, outward-facing, or production actions.
  Run scans against local or staging environments, and never submit real forms
  that send email, charge cards, or change production data.
- Never weaken a test, check, or threshold to make work pass, including
  disabling axe rules or excluding regions without a recorded reason.
- Never claim WCAG conformance from automated tools. Automated rules can fully
  test only a minority of success criteria; say which criteria were checked
  manually and which were not tested.
- Do not paste personal data from test accounts into the report.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The axe tests run and their results are attached or summarized per state.
- Each reported finding was reproduced at least once and cites a criterion.
- Every criterion in the target is marked pass, fail, not applicable, or not
  tested in the conformance summary.
- After remediation, the scan and the manual steps that found each issue pass.

## Report

Return the audit in this structure. Save it where the project keeps such
documents (for example `docs/accessibility/`), or return it in the conversation
if the user did not ask for a file. Never write it into a templates directory.

<!-- handoff: accessibility-audit-report -->
```markdown
# Accessibility audit report

## Scope

Routes, components, flows, and states audited; commit; WCAG version and level;
tools, browsers, and assistive technology used.

## Conformance summary

| Criterion | Level | Result | Notes |
| --- | --- | --- | --- |
| 2.5.8 Target Size (Minimum) | AA | fail | Icon buttons in the toolbar are 20 by 20 px. |

## Findings

Grouped as Critical, Serious, Moderate, and Minor. Each finding: issue,
criterion, element or `path:line`, evidence, user impact, remediation.

## Areas not tested

Pages, states, assistive technology, or criteria not covered, and the risk.

## Handoff

**Changed contract:** none for an audit, or the remediation changes made.

**Files / systems affected:** routes, components, and tokens involved.

**Evidence and tests:** scans, manual passes, and their results.

**Risks / rollback:** risks of the proposed fixes.

**What the next agent needs:** remediation priorities and open questions.
```

## Optional delegation

The `accessibility-checker` subagent can audit separate routes or components in
parallel and return findings mapped to criteria. Reproduce each of its findings
before including it in the report.
