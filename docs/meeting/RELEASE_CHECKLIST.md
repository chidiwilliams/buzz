# Meeting Windows release evidence

Keep version `1.4.5` synchronized in `pyproject.toml`, `Makefile`, and
`buzz/__version__.py`. If an isolated upgrade smoke demonstrates that the same
version cannot upgrade correctly, stop for a version decision. Do not infer a
version bump from the existence of a hardening PR.

Record each category separately, using **PASS**, **FAIL**, **NOT EXECUTED**, or
**BASELINE/ENVIRONMENT**, with exact command, source revision and evidence path.
A test pass is not packaging, installation, Actions, or release evidence.

## Before staging and independent review

- Run `uv run pytest tests/widgets/meeting_product_e2e_test.py
  tests/windows_release_script_test.py`.
- Run `uv run python scripts/run_meeting_release_mutations.py --output
  <external-evidence-directory>`. Record each mutation's KILLED / SURVIVES /
  NOT TESTED outcome and its captured oracle. This opt-in harness modifies only
  in-memory behavior in disposable subprocesses. A named assertion/guard must
  fail before the harness records a kill and ends that mutant process; an
  unrelated exception, startup failure, crash, or timeout is not a kill.
  Unmutated E2Es run normal resource cleanup. Mutation evidence is not shutdown
  smoke evidence.
- Run meeting/domain, meeting widgets, final transcription, Notes/provider
  lifetime, minutes, application/main-window close, Settings/keyring and summary
  repository tests; run remaining widgets with separate failure accounting.
- Run Ruff check/format check and `uv run python -m py_compile` on changed Python
  files, plus `git diff --check`. Distinguish existing legacy formatting debt.
- Record baseline comparison for failures; clipboard, missing Latvian `buzz.mo`,
  model download/cache timing and existing style debt must not be silently
  fixed or counted green.
- Inspect the full diff, status and staged-file list. No stage, commit or push
  is part of implementation. Independent review and final review precede
  **READY TO STAGE**.

## GitHub Actions execution

- After an explicitly authorized PR push, inspect actual PR run URLs and status.
  A configured workflow or an empty run list does not prove CI execution.
- After merge, explicitly run CI using `workflow_dispatch` on final `main` when
  authorized. Preserve run URL, resolved SHA, jobs and artifact links.
- If repository/platform availability prevents execution, record exactly:
  `CI CONFIGURED` / `GITHUB ACTIONS EXECUTION UNAVAILABLE`.
- `meeting-v...` tags still publish GitHub release artifacts, but must never
  enter `publish_pypi`. Existing PR/push triggers remain active.

## Local Windows package

- Run the authoritative final-main build only after FINAL review and merge,
  against a clean final `main` checkout at the validated merge SHA.
- Use a clean dedicated checkout/worktree on `main` with initialized submodules
  and the existing Windows build prerequisites. Do not repurpose a dirty
  development checkout or reuse September 2 artifacts.
- Invoke the script in that checkout after setting the validated SHA as data:
  `$env:BUZZ_VALIDATED_SHA = "<FINAL_MERGE_SHA>"`, then
  `.\Build-BuzzMeeting-Installer-V4.cmd`.
  The script resolves its own repository, fetches `origin/main`, rejects a
  different remote SHA, non-main branch and tracked/staged dirt, permits only a
  safe fast-forward, and checks final HEAD before building. Git Bash inherits
  that repository. Missing/malformed SHA fails with usage; no SHA is embedded.
- The script preserves the targeted CTC Ruff-cache check/removal and delegates
  packaging to `uv run make bundle_windows`. Do not bypass Makefile CTC identity,
  ONEDIR, PE/helper, Qt-plugin or installer validators.
- A feature-branch implementation build may use the canonical command directly;
  it cannot pass the release script's final-main gate. Record HEAD **and the
  uncommitted diff**, if any. Never label such a build a validated merge-SHA build.
- Record exact source SHA, cleanliness, tool versions, command/exit code and build
  log. Preserve installer checksum and all generated `.bin` siblings together.

## Installed application, isolated profiles, and AI

- Launch the newly built installer, complete installation, then launch Buzz from
  its shortcut without a CLI. Verify Meeting Mode, AI Notes and Export Minutes UI.
- Use a disposable Windows account/profile or another verified reversible data
  sandbox. Preserve the developer's actual Buzz data and settings. Test a fresh
  state: launch → New Meeting → short controlled capture → Stop/save → Library
  reopen → final transcript → AI Notes.
- Mandatory no-network Manual path: Copy AI Request → import a schema-valid
  response → persist notes → explicitly select those notes → export minutes.
  Reopen the meeting and verify the stored summary and exported contents.
- Where practical, configure a hermetic localhost OpenAI-compatible server and
  verify the **installed/frozen** worker/provider → persistence path. No paid key
  or production credential is required. Mark it NOT EXECUTED separately when
  unavailable; source-level provider tests cannot substitute for it.
- For upgrade, use a preserved copy of data from an earlier validated build in
  an isolated profile. Inventory Library rows, audio files/references, final
  transcripts, speaker reviews, summaries and persistent settings before and
  after installation. Never mutate the sole historical copy. No schema migration
  is required merely because a release is being produced.

## GitHub Release: post-merge only

- Only after independent review, fixes, final review, authorized staging/merge,
  and final-main package/install/fresh-profile/upgrade smokes may a final tag be
  authorized. Use the existing `meeting-v...` convention and actual release date.
- Verify tag target equals the validated final-main SHA, checkout is clean, and
  installer SHA/checksums are recorded. Include generated `.bin` siblings.
- Release notes must describe the integrated Meeting Mode → AI Notes → Minutes
  workflow. The old preview's “unintegrated” descriptions and artifacts are not
  final-main evidence. Record release/tag URLs and asset hashes separately.
