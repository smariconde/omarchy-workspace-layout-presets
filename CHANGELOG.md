# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

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

[Unreleased]: https://github.com/smariconde/omarchy-workspace-layout-presets/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/smariconde/omarchy-workspace-layout-presets/releases/tag/v0.1.0

