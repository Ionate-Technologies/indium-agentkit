---
name: internationalize-ui
description: "Prepare web or mobile UI and user-facing messages for multiple languages and regions with the project's i18n library: message catalogs with stable keys, ICU plurals and select, locale-aware dates, numbers, currencies, and lists, UTC storage with explicit time zones, right-to-left layouts, text expansion, locale fallback, and pseudo-localization tests. Use when adding a language, extracting hard-coded strings, or fixing plurals, formats, time zones, or RTL layouts. Not for building the feature itself (use the frontend-ship or mobile-feature skill)."
---

# Internationalize UI

Make every user-visible string translatable and every value formatted for the
reader's locale, without breaking layouts. The stance is **whole messages in,
formatted values out**: translators receive complete sentences with every
plural form, and code never concatenates text or formats dates, numbers, or
money by hand.

## When to use

- Adding a language or region, or preparing an app for its first translation.
- Extracting hard-coded strings, or adding a feature to an already localized app.
- Bugs such as "1 items", dates in the wrong order or time zone, untranslated
  fragments, clipped labels in longer languages, or a broken right-to-left layout.

## When not to use

- Building the screen or flow itself: use the `frontend-ship` skill for web or
  the `mobile-feature` skill for mobile, and apply this skill to its strings.
- Auditing accessibility, including language attributes: use the
  `accessibility-audit` skill.
- Running whole journeys per locale: use the `e2e-test-suite` skill for the
  harness.
- Adding a new i18n library or polyfill: use the `evaluate-new-dependency`
  skill first.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- **Library and catalogs** (table below), the source language, and the locales
  to support.
- **Locale selection today:** user setting, URL, `Accept-Language`, device
  language, and the default.
- **Translation source:** in-house translators, a vendor, or a translation
  management system, and how catalogs flow in and out of the repository.
- **Time handling:** the date library in use, and whether stored times are UTC
  instants, local times with a zone, or plain dates.
- **Checks:** no-literal-string lint rules (for example `eslint-plugin-i18next`
  or Android Lint's `HardcodedText`), catalog validation, screenshot tests, and
  the commands from `AGENTS.md`, `CLAUDE.md`, package scripts, or the `Makefile`.
- **Indexing:** whether public pages are indexed by search engines; only then do
  locale URLs and `hreflang` matter.

| Signal | Library | Message format |
| --- | --- | --- |
| `i18next`, `react-i18next`, `next-i18next` | i18next | JSON with `_one`, `_other` plural key suffixes; ICU only with the `i18next-icu` plugin |
| `react-intl`, `@formatjs/*`, `next-intl`, `@lingui/*` | FormatJS, next-intl, Lingui | ICU MessageFormat |
| `vue-i18n` | Vue I18n | Its own syntax; plural forms separated by `\|` |
| `@angular/localize`, `i18n` attributes | Angular i18n | XLIFF or JSON from `ng extract-i18n`; ICU in templates |
| `res/values*/strings.xml` | Android resources | `<string>` and `<plurals>` per `values-xx` folder |
| `*.xcstrings`, `*.strings`, `*.stringsdict` | Apple platforms | String Catalogs, `String(localized:comment:)` |
| `l10n.yaml`, `*.arb`, `flutter_localizations` | Flutter gen-l10n | ARB files with ICU syntax and `@key` metadata |

## Workflow

1. **Inventory hard-coded text.** Look for JSX text and string props (`title`,
   `placeholder`, `aria-label`, `alt`), template literals that build sentences,
   toasts and error messages, server messages shown verbatim, native layout
   files, notification text, and images with baked-in text. Turn on the
   project's no-literal-string lint rule if it has one, and run a pseudo-locale
   (step 10) to see what stays untranslated. Leave logs, analytics event names,
   and test IDs alone.
2. **Extract with stable, context-specific keys.**
   - Name keys by place and meaning (`checkout.payButton.label`), not by the
     English text, so a copy edit does not orphan every translation.
   - Never reuse one key in two contexts. "Open" on a button (a verb) and
     "Open" as a status (an adjective) translate differently in many languages;
     give each its own key even when the English matches.
   - When the meaning of a source string changes, use a new key so translators
     see it as new. A typo fix can keep the key; check how the project's
     translation tool treats edited source text.
   - Add a translator comment wherever meaning is not obvious: where the string
     appears, what each placeholder holds, and any length limit (FormatJS
     `description`, Apple `comment:`, ARB `@key` `description`, an XML comment
     above an Android string).
3. **Write whole messages.**
   - Plurals use ICU, never `count === 1 ? ... : ...` in code:
     `{count, plural, =0 {No messages} one {# message} other {# messages}}`.
     CLDR defines up to six categories (`zero`, `one`, `two`, `few`, `many`,
     `other`): English uses two, Russian and Polish more, Arabic all six,
     Japanese only `other`. Use `=0` for a dedicated "none" message; the `zero`
     category applies only in some languages, and in French 0 takes `one`.
   - Select covers grammatical variants: `{role, select, admin {...} other {...}}`,
     always with an `other` branch.
   - Interpolate values into one complete sentence. Never assemble a sentence
     from fragments (`t('deleted') + ' ' + name`), because word order differs
     between languages. For a link or bold text inside a sentence, use the
     library's rich-text tags (FormatJS `<link>terms</link>` with a tag
     handler, the react-i18next `Trans` component) instead of splitting it.
   - Follow the library's own plural mechanics. i18next selects `_one`,
     `_other`, and other suffixed keys from `count`. vue-i18n picks among
     `|`-separated forms; check its docs for custom plural rules in languages
     such as Russian. Android `<plurals>` is read with
     `getQuantityString(id, count, count)`: the first `count` chooses the form
     and the second fills the placeholder, and the `zero` quantity is ignored
     in English.
4. **Format values with the locale.**
   - Web and JavaScript: `Intl.DateTimeFormat`, `Intl.NumberFormat`,
     `Intl.RelativeTimeFormat`, `Intl.ListFormat` ("A, B, and C"), and
     `Intl.Collator`, or the library's wrappers over them. iOS:
     `formatted()` styles or `DateFormatter` templates. Android: `java.time`
     `DateTimeFormatter.ofLocalizedDate` and `NumberFormat`. Flutter: `DateFormat`
     and `NumberFormat` from the `intl` package.
   - Pass the locale explicitly. `toLocaleString()` with no arguments uses the
     runtime default, which differs between server and browser and causes
     hydration mismatches in server-rendered apps.
   - Use styles or skeletons (`dateStyle: 'medium'`), not fixed patterns such as
     `MM/dd/yyyy`. In pattern-based APIs, `YYYY` is the week-based year and shows
     the wrong year around New Year; calendar years use `yyyy`.
   - The currency comes from the data, not the locale: show the order's currency
     in the reader's format. Keep money in integer minor units; minor digits vary
     (0 for JPY, 3 for KWD).
   - Sort with locale collation (`Intl.Collator`, `localeCompare`) and use
     locale-aware case mapping (`toLocaleLowerCase('tr')` for Turkish dotted and
     dotless i).
   - Parsing typed numbers and dates is locale-specific (`1.234,5` in German),
     and `Intl` has no parser. Use locale-aware inputs or the platform's parser,
     and never parse formatted output.
   - In React Native, check which `Intl` APIs your JavaScript engine supports
     before relying on them, and add FormatJS polyfills only for what is missing.
5. **Store UTC, display local, keep zones explicit.**
   - Store and transmit instants in UTC as ISO 8601 with `Z` or an offset.
     Display them in the user's zone, passed explicitly as an IANA name
     (`timeZone: 'Europe/Berlin'`) from the profile or the device
     (`Intl.DateTimeFormat().resolvedOptions().timeZone`).
   - Store a user's zone as an IANA name, never a fixed offset; offsets change
     with daylight saving time.
   - A future event in local time (09:00 in Berlin next spring) stores the local
     time plus the IANA zone and converts when shown, because zone rules can
     change before the date.
   - A date without a time (birthday, due date) is stored as a date
     (`2026-03-29`), not as midnight UTC, which shows the previous day to users
     west of UTC.
   - "Same time tomorrow" is a calendar addition in the user's zone, not plus 24
     hours. Test around daylight-saving transitions.
6. **Support right-to-left.**
   - Web: set `lang` and `dir` on the root (`<html lang="ar" dir="rtl">`) and
     update both when the locale changes. Use logical CSS properties
     (`margin-inline-start`, `padding-inline-end`, `inset-inline-start`,
     `border-inline-start`, `text-align: start`) and the framework's logical
     utilities if it has them (for example Tailwind's `ms-*` and `me-*`).
     Flexbox and grid already follow `dir`.
   - Mobile: `android:supportsRtl="true"` with `start` and `end` attributes on
     Android; leading and trailing constraints on iOS; `EdgeInsetsDirectional`
     and `AlignmentDirectional` in Flutter; `start` and `end` style props in
     React Native, where switching direction with `I18nManager` needs an app
     restart.
   - Mirror directional icons (back and forward arrows, chevrons, progress along
     the reading direction). Do not mirror logos, checkmarks, clocks, media
     playback controls, or pictures of real objects.
   - Mixed-direction text: use `dir="auto"` on user-generated content and wrap
     interpolated names in `<bdi>` (or Unicode isolates) so punctuation lands in
     the right place. Phone numbers, code, and URLs stay left to right.
7. **Leave room for longer text.**
   - Translations often run longer than English, and short labels can double. A
     common rule of thumb is 30 to 50 percent growth for sentences; use your
     translators' data where you have it.
   - Avoid fixed widths and heights on text; let buttons and labels wrap.
     Truncate only where the full text is reachable (a tooltip or detail view),
     and never truncate prices, warnings, or legal text.
   - Allow taller line heights for scripts with tall glyphs or stacked
     diacritics (Thai, Vietnamese, Arabic), and confirm the fonts cover every
     supported script.
8. **Negotiate the locale and fall back.**
   - Order: the user's explicit choice (saved to the profile so it follows them),
     then the URL or app setting, then `Accept-Language`, `navigator.languages`,
     or the device's preferred languages, then the default. Never infer language
     from IP address or location.
   - Match BCP 47 tags with fallback (`pt-BR`, then `pt`, then the default)
     using the library's matcher (for example `@formatjs/intl-localematcher`),
     and fall back per missing key, never to a raw key on screen. Log missing
     keys in development and CI.
   - On mobile, honor the platform's per-app language setting (iOS, and Android
     13 and later with a locale config) rather than only an in-app picker.
9. **Run the translation workflow.**
   - One source-language catalog in the repository is the source of truth.
     Extraction or generation (for example `formatjs extract`,
     `ng extract-i18n`, Xcode's build-time String Catalog extraction, or
     `flutter gen-l10n`) runs in CI and fails on missing or unused keys where
     the tooling allows.
   - Do not translate brand and product names, code identifiers, URLs,
     placeholders, or user-generated content; mark fixed strings untranslatable
     (Android `translatable="false"`). Legal and regulated text needs review in
     each locale.
   - Uploading strings to a vendor or translation system is outward-facing; ask
     first. Machine translation is a draft: ship it only where the project's
     policy allows, and mark it for review.
   - Every translation keeps the source's placeholders and valid ICU syntax.
10. **Test with pseudo-localization.**
    - A pseudo-locale swaps letters for accented look-alikes, pads each message,
      and brackets it: `[Ŝàvé çĥàñĝéš ~~~~]`. Plain English on screen is
      hard-coded; a missing closing bracket means truncation; two bracket pairs
      in one sentence mean concatenation.
    - Transform only literal text; keep placeholders, ICU syntax, and markup
      intact, or the messages break.
    - Built-in options: Android's `en-XA` (accented) and `ar-XB` (right-to-left)
      pseudolocales, enabled with `pseudoLocalesEnabled` on a debug build type;
      Xcode scheme options for double-length, accented, bounded, and
      right-to-left pseudolanguages; a pseudo-locale option in FormatJS's compile
      step (check `formatjs compile --help` for your version).
    - Walk the main screens in the pseudo-locale and an RTL locale at a large
      text size, checking for clipping, overlap, and wrong mirroring.
11. **Locale URLs and SEO, only for indexed public pages.** Put the locale in
    the path or subdomain (`/fr/pricing`), add `hreflang` alternates including
    `x-default`, give each locale its own canonical URL, and offer a language
    switcher instead of forcing redirects from `Accept-Language`. Skip this for
    signed-in app screens.

## Worked example: plural message, money, and time (illustrative TypeScript)

Uses `intl-messageformat` from FormatJS; react-intl, next-intl, and i18next with
its ICU plugin apply the same rules.

```ts
import { IntlMessageFormat } from 'intl-messageformat';

// Source catalog entry (en): one whole sentence per plural form, with context.
export const en = {
  'cart.summary': {
    message:
      '{count, plural, =0 {Your cart is empty.} one {# item, total {total}} other {# items, total {total}}}',
    description: 'Cart footer. count is the number of items; total is a formatted price.',
  },
};
// Wrong: `${count} item${count === 1 ? '' : 's'}` hard-codes English plural rules.
// Wrong: t('total') + ': ' + amount splits a sentence translators cannot reorder.

type Order = { itemCount: number; totalMinor: number; currency: string; updatedAt: string };

export function cartSummary(locale: string, message: string, order: Order): string {
  // The currency comes from the order; the locale only decides how it looks.
  const money = new Intl.NumberFormat(locale, { style: 'currency', currency: order.currency });
  const digits = money.resolvedOptions().maximumFractionDigits ?? 2; // 0 for JPY
  const total = money.format(order.totalMinor / 10 ** digits);
  // Libraries cache compiled messages; avoid compiling on every render.
  return new IntlMessageFormat(message, locale).format({ count: order.itemCount, total }) as string;
}

export function lastUpdated(locale: string, timeZone: string, order: Order): string {
  // updatedAt is a UTC instant from the API, for example '2026-10-17T14:05:00Z'.
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone })
    .format(new Date(order.updatedAt));
}

// cartSummary('de-DE', de['cart.summary'].message, order) uses the German
// catalog, German plural rules, and German number format for the same order.
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including uploads to translation vendors or management systems.
- Never weaken a test, check, or threshold to make work pass.
- Ask before adding an i18n library, polyfill, or font.
- Never hard-code plural rules, date patterns, decimal separators, or currency
  symbols, and never change a source string's meaning while keeping its key.
- Remove unused keys only after confirming that no platform or service sharing
  the catalog still uses them.
- Never store a local time without its zone, or a plain date as a timestamp.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Lint, including any no-literal-string rule, and type-check pass.
- Every message in every catalog compiles; placeholders match the source; each
  shipped locale has every key or a deliberate fallback.
- Unit tests render plurals for counts such as 0, 1, 2, 5, and 21 in the source
  language and in at least one language with more categories (for example
  Russian or Arabic), plus each `select` branch.
- Formatting tests pass an explicit locale and time zone, run under a fixed
  process time zone, and cover a daylight-saving transition. `Intl` output can
  contain non-breaking spaces (U+00A0, U+202F) and changes between ICU
  versions, so assert with `formatToParts` or normalize spaces rather than
  comparing raw strings from another environment.
- The main screens pass in a pseudo-locale and an RTL locale at large text size
  (screenshots where the project has screenshot tests).
- The build succeeds for every locale (for example Angular builds one output per
  locale).

## Report

- **Library and locales:** library, source language, locales, and fallback chain.
- **Strings:** keys added or changed, hard-coded strings left with reasons, and
  translator comments added.
- **Formatting and time:** values moved to locale formatting, and the time
  storage model per field (UTC instant, local time plus zone, or plain date).
- **Layout:** RTL and text-expansion fixes.
- **Translation handoff:** catalogs ready for translation, and anything sent
  outside the repository (only with approval).
- **Verification:** each command and its result, and the pseudo-locale and RTL
  screens checked.
- **Not verified:** locales, scripts, devices, or assistive technologies not
  exercised.

## Optional delegation

The `frontend-builder` or `mobile-builder` subagent can extract strings in
assigned paths once the key scheme is agreed. The `accessibility-checker`
subagent can check `lang`, `dir`, and accessible names in translated UI, and the
`test-writer` subagent can add plural and formatting tests. The workflow above
stays complete for a single agent.
