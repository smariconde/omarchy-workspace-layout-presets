# Repository guide

Orientation for anyone working on this repository: what the project is, which
document owns which decision, where each module lives, and which invariants a
change may never break. It is a map, not a specification — every requirement
lives in the documents named below.

## What this is

An Omarchy 4.x / Quickshell bar widget (plugin id
`io.github.smariconde.workspace-layout-presets`) that saves the arrangement of
**one** Hyprland `dwindle` workspace as a named profile and restores it only
into an empty active workspace. It is not a session manager.

## Commands

```sh
python -m unittest discover -v                    # full suite (run from repo root)
python -m unittest tests.test_capture -v          # one module
python -m unittest tests.test_capture.CaptureTests.test_name -v   # one test
python tools/check_release_payload.py             # installable-tree guard
```

Backend modules use relative imports (`from .infer_dwindle import ...`), so
always run from the repository root. Python standard library only — no
dependencies, no test runner beyond `unittest`. CI runs the same discover
command on Python 3.11 through 3.14.

In a real Omarchy session, QML and manifest changes also need `qmllint` and
`omarchy plugin validate .`. `tests/test_qml_process_probe.py` launches `qs`
against `qml_process_probe.qml` and self-skips without Quickshell plus a live
Wayland socket.

## Documentation hierarchy

Five documents own different things; keep them from drifting into each other:

- [../spec.md](../spec.md) — what is built: scope, requirements, safety limits.
- [architecture.md](architecture.md) — how it splits: component ownership and
  the stable contracts (CLI v1 envelope, profile V1 schema, QML/backend bridge).
- [development-plan.md](development-plan.md) — order and progress only
  (milestone table, next session). Never duplicate requirements here.
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — contribution rules; read it before
  changing behavior.
- This guide — orientation and the module map.

A contract decision goes into `architecture.md` **before** it appears in code.
Update `spec.md` only when a requirement changed, `development-plan.md` only
when a milestone advanced.

`spec.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, and this guide are
written in English. `docs/architecture.md`, `docs/development-plan.md`, and
commit-adjacent prose are written in Spanish. Code, docstrings, and inline
comments are always English. Match what you are editing.

## Architecture

```
BarWidget.qml / Panel.qml / qml/*   presentation and interaction only
        │  fixed executable + argv array (never a shell string)
backend/layoutctl.py                typed JSON CLI boundary, one JSON object per call
        ├── capture.py              hyprctl JSON → validated profile
        │     ├── infer_dwindle.py  pure rectangle → binary split tree
        │     └── launchers.py      .desktop resolution (id only, never Exec)
        ├── layout_preview.py       pure split tree → normalized rectangles
        ├── restore.py              read-only planning; sole home for dispatch syntax
        │     └── plan_store.py     single-use approval tokens in the runtime dir
        └── profile_store.py        sole owner of profile paths, validation, atomic writes
              └── atomic_json.py    shared private, all-or-nothing write primitive
```

Milestones M0–M6 and M8 are done. M5 has a guarded replay executor, fresh
QML-generated bridge attestation, asynchronous desktop-entry launch, exact
window-address tracking and result verification. The panel and profile
management QML are functional.

QML runs `backend/layoutctl.py` by absolute path, so it inserts the plugin
directory into `sys.path` when invoked without a package and imports
`backend.*` in both modes. A test runs the file as a subprocess to keep that
path working.

### `layoutctl` contract (stable, v1)

Every invocation writes exactly one JSON object on stdout, success or failure:

```json
{"contractVersion": 1, "status": "ok|error|blocked", "data": {}, "warnings": [], "blocked": [], "error": null}
```

`warnings` and `blocked` entries are `{code, message}`. A `blocked` response
never changed anything. Exit codes: 0 ok, 1 operation error, 2 invalid
arguments, 3 declared-but-unimplemented. Build responses only through
`result_ok` / `result_error` / `result_blocked` / `result_unimplemented` in
[../backend/layoutctl.py](../backend/layoutctl.py) — argparse errors are
funnelled back into the envelope via the `ArgumentParser.error` override rather
than exiting.

`execute()` takes injectable callables (`profile_lister`, `capture_workspace`)
so CLI tests never touch Hyprland or the filesystem.

### Profile schema V1

`validate_profile` in [../backend/profile_store.py](../backend/profile_store.py)
is a **closed** schema: unknown fields are rejected, on purpose, so profiles
cannot become a side channel for command lines, URLs, documents, or session
data. Tiled nodes form an anchor plus exactly `len(nodes)-1` splits that each
add one remaining node; ratios are finite and strictly in (0, 1); floating
geometry is normalized to (0, 1). Max 10 tiled and 10 floating windows.
Profiles live at
`$XDG_DATA_HOME/omarchy-workspace-layout-presets/profiles/<id>.json`; every
storage function takes an `environment` mapping so tests can point at a temp
directory.

`profile show` also returns a `layout` sketch built by
[../backend/layout_preview.py](../backend/layout_preview.py), the sole owner of
the inverse of Dwindle inference (split tree → normalized rectangles);
`restore.py` reuses it to rebuild expected geometry, so the ratio convention
lives in one place. The sketch carries proportions only, never application
identity, and reports `mode: "approximate"` with an even grid when
`layoutConfidence` is `fallback`, rather than expanding synthetic splits.
`qml/LayoutMap.qml` paints those rectangles and computes no geometry.

`profile_store` is the only module that turns an id into a path or writes a
file. Writes are atomic, private-mode, and never overwrite —
duplicate/import/export answer `blocked` with `already_exists` instead.

### Capture

[../backend/capture.py](../backend/capture.py) issues exactly four read-only
queries (`activeworkspace`, `clients`, `monitors`, `getoption general:layout`)
through an injectable `HyprctlReader`; `SystemHyprctlReader` runs fixed
`hyprctl -j` argv arrays with an allowlist of subjects. Tests drive it from
anonymized fixtures in [../tests/fixtures/](../tests/fixtures/) with no
graphical session.

Only allowed fields survive capture: workspace name, monitor connector and
usable rectangle, window class, tiled/floating state, normalized floating
geometry. Never titles, addresses, PIDs, `/proc` command lines, or
desktop-entry `Exec`.

### Planning

[../backend/restore.py](../backend/restore.py) reuses those same four read-only
queries. `build_plan` is pure and raises `PlanBlocked` (workspace occupied,
unsupported layout, special workspace, unusable monitor, nothing launchable) or
`PlanError` (invalid profile); `plan_profile` adds profile loading, the
queries, and token issuance. A blocked plan issues no token.

The approval token records only `profileId`, a profile digest, timestamps, and
the verified target — never operations, launch arguments, or geometry.
`restore` rebuilds the plan from the validated profile, re-checks the
conditions, and consumes the single-use record, which expires after 300
seconds.

`infer_dwindle` accepts only slicing partitions (each cut spans its node's full
rectangle), resolves ties deterministically (vertical before horizontal, then
by coordinate), and measures ratios at the gap centre. When no slicing tree
exists, capture keeps a stable node order, sets `layoutConfidence: "fallback"`,
and emits an explicit warning — it never invents a tree.

## Non-negotiable safety rules

These are product invariants, not preferences. The full list, and the review
expectations around it, live in [../CONTRIBUTING.md](../CONTRIBUTING.md).

- One workspace per profile. No whole-desktop capture, no autostart, no
  automatic restore.
- Restore only into the active, empty workspace; never close, move, or
  rearrange existing windows. A partial restore reports its result — it never
  attempts a destructive rollback.
- Profiles are data, never programs. No shell source is ever built from profile
  content, and QML passes only fixed executables plus argument arrays created
  in source. Do not add a generic "run this command" method to
  `qml/LayoutctlClient.qml`.
- Every failure mode blocks explicitly and early: invalid profile, unresolvable
  launcher, unsupported layout, non-empty workspace, fullscreen, over-limit
  window counts.
- Keep Hyprland logic out of QML, and keep pure algorithms (Dwindle inference,
  floating geometry) separate from I/O.
- Do not write to `~/.config/omarchy`, or install/enable/copy the plugin
  outside this repository, without an explicit request from the person running
  the change.
- Do not fill reserved modules with unverified Hyprland or Quickshell calls;
  build the contract, fixture, or spike that validates them first.

## Installable-tree hygiene

Installing the plugin clones this repository into the Omarchy plugin directory,
so every tracked file ships to end users. Files that configure a coding
assistant are therefore not contributor notes here — inside an installed plugin
they are an instruction channel in someone else's environment, and the Omarchy
Plugin Marketplace rejects payloads that contain them.

Keep such files out of version control. `tools/check_release_payload.py`
enforces this recursively over the tracked tree, `.gitignore` keeps the common
names from being staged by accident, and `tests/test_release_payload.py` runs
the same check as part of the suite. Local, untracked assistant configuration
is fine; it just never gets committed.

Ordinary contributor documentation belongs in neutrally named files such as
this guide, `CONTRIBUTING.md`, or anything under `docs/`.
