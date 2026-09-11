# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [0.2.0] - 2026-09-10

### Added

- Selecting a preset shows a wordless sketch of the saved arrangement beside
  the application names, drawn at the recorded proportions and shaped like the
  monitor the preset was captured on.
- A preset whose geometry could not be inferred exactly presents its sketch as
  approximate instead of implying a shape that was never measured.
- `profile show` returns an additive `layout` field holding normalized
  rectangles. The CLI `contractVersion` remains 1.

### Changed

- The expansion from a stored split tree back into rectangles moved into
  `backend/layout_preview.py`. Restore verification and the panel sketch now
  share it, so one ratio convention governs what is drawn and what is checked.

### Removed

- `AGENTS.md` and `CLAUDE.md` no longer ship in the installable tree. The
  contributor documentation they held moved to `docs/repository-guide.md` and
  `CONTRIBUTING.md`.
- The unused `production/` directory, left over from the first commit.

### Security

- Installing the plugin clones this repository, so a committed
  coding-assistant instruction file would become an instruction channel inside
  the user's environment. `tools/check_release_payload.py` now fails the test
  suite and CI if one appears anywhere in the tracked tree.
- The layout sketch carries proportions only. No application name, window
  class, path, or launch argument crosses into it.

## [0.1.0] - 2026-09-10

### Added

- Omarchy bar widget for saving and managing named workspace presets.
- Safe capture of the active workspace using JSON-only Hyprland queries.
- Exact Dwindle split inference for supported slicing layouts, with an explicit
  fallback for unsupported geometry.
- Floating-window geometry restoration relative to the target monitor.
- Desktop-entry-only application launching, including explicit review for
  ambiguous browser-hosted webapps.
- Read-only restore previews and short-lived, single-use approval tokens.
- Guarded restore into an empty active workspace with partial-result reporting.
- Profile inspect, rename, duplicate, delete, export, and import operations.
- Automated tests for the CLI contract, storage, capture, planning, replay, and
  QML integration boundaries.

### Security

- Profiles reject unknown or executable fields and never store process command
  lines, URLs, document paths, credentials, environment variables, or history.
- QML invokes a fixed executable with separate arguments; profile content is
  never evaluated as shell source.
- Restore revalidates the profile, workspace, Hyprland version, layout, and Lua
  bridge evidence immediately before replay.

[Unreleased]: https://github.com/smariconde/omarchy-workspace-layout-presets/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/smariconde/omarchy-workspace-layout-presets/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/smariconde/omarchy-workspace-layout-presets/releases/tag/v0.1.0

