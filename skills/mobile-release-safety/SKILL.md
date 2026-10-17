---
name: mobile-release-safety
description: "Prepare, audit, and stage an iOS or Android release (native, React Native, Expo, or Flutter): version and build numbers, signing and secrets, permissions and privacy manifests, store policy, symbol upload, phased or staged rollout with halt criteria, OTA update scope, and kill switches. Use before submitting to App Store Connect or Google Play, publishing an OTA update, or planning a halt after a crash spike. Not for web or server deploys (use the deployment-safety skill)."
---

# Mobile Release Safety

Ship a build the stores accept, that you can diagnose, and that you can stop.
The stance is **propose, do not push**: submissions, rollout changes, OTA
publishes, and rollbacks are outward-facing and run only after the release
owner approves them.

## When to use

- A store release is being prepared or its configuration audited.
- An OTA update (EAS Update, CodePush) is about to ship.
- A rollout plan, halt criteria, or kill switches are needed, or a crash spike
  after release needs a containment plan.

## When not to use

- Web, backend, or infrastructure deploys: use the `deployment-safety` skill.
- An active incident that needs coordination: use the `incident-triage` skill.
- A signing key, keystore, or API key was committed: use the
  `secret-leak-response` skill first.
- Store "What's New" text or changelogs: use the `release-notes` skill.
- An independent read-only audit of release config: delegate to the
  `mobile-specialist` subagent.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- **Project type and config:** Xcode project or workspace and `Info.plist`,
  `android/app/build.gradle` or `build.gradle.kts`, `AndroidManifest.xml`,
  `app.json` or `app.config.*` and `eas.json` (Expo), `pubspec.yaml` (Flutter).
- **Store state the repository cannot show:** the last uploaded version and
  build number per platform, current rollout percentage, and review status. Ask
  the user.
- **Pipeline:** fastlane lanes, EAS Build and Submit profiles, Xcode Cloud, or CI
  workflows, and how signing credentials reach them.
- **Crash and performance reporting:** Crashlytics, Sentry, Bugsnag, or similar,
  and how symbols reach it.
- **OTA setup:** EAS Update channels and `runtimeVersion` policy, or the CodePush
  server in use (App Center, which hosted CodePush, was retired in 2025).
- **Feature flags or remote config,** and any minimum-version or force-update gate.
- **Halt criteria:** the team's crash-free and ANR targets. Use the project's
  SLO; do not invent one.

## Workflow

1. **Versions and build numbers.**
   - iOS: `CFBundleShortVersionString` (`MARKETING_VERSION`) is the user-facing
     version; `CFBundleVersion` (`CURRENT_PROJECT_VERSION`) is the build number
     and must be higher than every build already uploaded for that version.
     Keep it increasing across versions too.
   - Android: `versionCode` must be greater than every `versionCode` already
     uploaded to any Play track; `versionName` is display only.
   - Flutter: `version: 1.4.0+42` sets the name and the build number.
   - Expo: `version`, `ios.buildNumber`, and `android.versionCode`, unless EAS
     manages them remotely (`appVersionSource` and `autoIncrement` in `eas.json`).
   - Confirm both platforms ship the version the release notes describe.
2. **Signing and secrets.** Distribution certificates and provisioning profiles
   (iOS) and the upload keystore (Android; Play App Signing holds the app signing
   key) come from the CI secret store or a tool such as fastlane match. This
   read-only check should print nothing:

   ```bash
   git ls-files -- '*.jks' '*.keystore' '*.p12' '*.p8' '*.mobileprovision'
   ```

   Also keep `key.properties`, service-account JSON, and App Store Connect API
   keys out of the tree.
3. **Permissions and privacy.**
   - iOS: every protected resource the app or its SDKs access has a specific
     purpose string (`NSCameraUsageDescription`, `NSLocationWhenInUseUsageDescription`,
     and so on); a missing one crashes on access and fails review. Tracking
     needs `NSUserTrackingUsageDescription` and the App Tracking Transparency
     prompt before tracking starts.
   - Privacy manifest: `PrivacyInfo.xcprivacy` is required for App Store
     submissions when the app or an embedded SDK uses a required-reason API
     (for example file timestamps, system boot time, disk space, active
     keyboards, or `UserDefaults`), and SDKs on Apple's list of commonly used
     third-party SDKs must include their own manifests (and signatures when
     shipped as binaries). Apple has enforced this since May 2024, regardless of
     deployment target. Check the declared reasons against actual use, and
     generate the archive's privacy report in Xcode's Organizer to compare with
     the App Store privacy labels.
   - Android: review the merged manifest, not only the app's own, because
     libraries add permissions. Runtime permissions need denial paths, and
     `POST_NOTIFICATIONS` is a runtime permission on Android 13 and later.
     Sensitive permissions (SMS, call log, background location, all-files
     access, package visibility, photo and video access) need Play Console
     declarations. Keep the Data safety form consistent with actual collection.
4. **Store policy and build settings.**
   - Google Play requires new apps and updates to target a recent Android API
     level, and the deadline moves each year. Check the current requirement in
     Play Console policy before comparing it with `targetSdk`.
   - Ship an Android App Bundle to Play. Release builds enable R8:
     `minifyEnabled true` (Groovy) or `isMinifyEnabled = true` (Kotlin DSL), with
     resource shrinking if the project uses it and keep rules for reflection-based
     libraries.
   - Release builds are not debuggable, do not ship dev menus or test endpoints,
     and justify any cleartext traffic or App Transport Security exception.
   - Deep links: `apple-app-site-association` and `assetlinks.json` are served
     over HTTPS without redirects, and `assetlinks.json` lists the SHA-256
     fingerprint of the Play app signing key, not only the upload key.
5. **Symbols.** Without them, crash reports are unreadable.
   - iOS: upload the archive's dSYMs with the crash tool's documented step.
   - Android: upload the R8 mapping file (`app/build/outputs/mapping/release/mapping.txt`)
     to the crash tool, and confirm Play Console shows a deobfuscation file for
     the release.
   - Flutter: builds with `--obfuscate --split-debug-info=<dir>` need those
     symbol files kept and uploaded. React Native: upload JavaScript source maps,
     including for each OTA update.
6. **OTA scope.** EAS Update and CodePush may ship JavaScript and asset changes
   only. They must not add or change native code, and must not change the app's
   primary purpose or add features inconsistent with what was reviewed and
   advertised. Apple allows
   downloaded interpreted code within those limits (App Review Guideline 2.5.2
   and the Developer Program License Agreement), and Google Play's policy
   restricts self-updating outside Play except for code run in an interpreter or
   virtual machine; check the current policy text for edge cases. The update's
   `runtimeVersion` (Expo) or target binary version (CodePush) must match the
   installed binaries it targets; a native change means a new store build.
   Publish to a preview or staging channel first.
7. **Rollout plan and halt criteria.** Write the plan before submitting:
   - iOS phased release for automatic updates runs over 7 days (1, 2, 5, 10, 20,
     50, then 100 percent), can be paused (up to 30 days in total), and can be
     released to everyone early. Users can still update manually from the App
     Store. A shipped iOS version cannot be rolled back; the fix is a new build,
     with expedited review if warranted.
   - Google Play staged rollout releases to a chosen percentage of users; raise
     it step by step, and halt it if a gate fails. Halting stops more users from
     receiving that release; users who already have it keep it. The fix is a new
     release with a higher `versionCode`.
   - Gates come from the team's SLOs: crash-free users or sessions, ANR rate,
     new top crashes, and key business metrics, compared with the previous
     release at the same rollout stage. Google Play's Android vitals also
     publishes bad-behavior thresholds; check the current values.
   - Kill switches: risky new features sit behind remote flags that default to
     off when config cannot load. Old app versions stay installed for months, so
     backend changes must stay compatible with them; use a minimum-version gate
     only for unavoidable breaks.
8. **Pre-submission checks.** Build the release variant, install it on physical
   devices (oldest supported OS and newest), and smoke-test the critical flows.
   Test an upgrade from the current store version (stored data, keychain or
   keystore, database migrations), offline and slow network, permission denial,
   dark mode, large font sizes, and tablets if supported. For an accessibility
   pass, use the `accessibility-audit` skill's criteria with VoiceOver and
   TalkBack.
9. **Propose, then monitor.** Present the submission, rollout, OTA publish, and
   any halt or rollback as proposed commands, each with a same-line
   `# requires approval` comment. After approval, watch the gates at each step
   and propose the next step or a pause. For an OTA regression, propose the
   provider's documented rollback, such as republishing the previous update or
   rolling back to the embedded bundle (check `eas update --help` for your CLI
   version). Never run any of these automatically.

## Example rollout plan

Illustrative; the numbers come from the team's SLOs.

```markdown
Release 4.12.0 (iOS build 412003, Android versionCode 412003)
- Gate per step: crash-free users at or above the team SLO, no new top-5 crash,
  ANR rate not above the previous release, after at least 24 h of data
- iOS: phased release on; pause if a gate fails; fix forward with a new build
- Android: staged rollout 5% then 20% then 50% then 100%; halt if a gate fails
- OTA: none during the rollout window
- Kill switches: checkout_v2 (off by default if remote config fails to load)
- Owner and approver: release manager on call
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  store uploads and submissions, rollout changes, OTA publishes, rollbacks,
  remote flag changes, and cloud builds that spend credits.
- Never weaken a test, check, or threshold to make work pass.
- Never commit or print signing material, keystore passwords, or service-account
  keys. If one is already tracked, stop and use the `secret-leak-response` skill.
- Do not run commands that change project configuration (for example
  `eas update:configure` or `eas build:configure`) as verification; propose them
  as changes.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
fastlane lanes, or the `Makefile`. Run each check separately and report its real
result; never chain alternatives with `||`.

- Lint, type-check, and unit tests pass.
- The release variant builds locally or in CI (for example
  `./gradlew bundleRelease`, an Xcode archive through the project's fastlane
  lane, or `flutter build appbundle` and `flutter build ipa`).
- Read-only config checks: `npx expo config --type public` shows the expected
  versions and `runtimeVersion` (Expo); `npx expo-doctor` reports no blocking
  issues (Expo); fastlane `precheck` passes if the project uses it.
- The secret check in step 2 prints nothing.
- Symbols for the build appear in the crash tool after the first upload.

## Report

- **Release:** platforms, version names, build numbers, and commit.
- **Checks:** versioning, signing, permissions and privacy, store policy,
  symbols, and OTA scope, each pass, fail, or not verified, with evidence.
- **Rollout plan:** steps, gates, kill switches, and owner.
- **Proposed actions:** each outward-facing command, marked `# requires approval`.
- **Not verified:** store-side state, device coverage, or policy details that
  could not be checked from here.

## Optional delegation

The `mobile-specialist` subagent can audit manifests, privacy declarations,
signing, shrinking, and OTA configuration read-only while you prepare the
rollout plan. Re-check any blocking finding before acting on it.
