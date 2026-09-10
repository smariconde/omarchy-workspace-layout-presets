# Omarchy Workspace Layout Presets — Product & Technical Spec

**Status:** Release candidate 0.1.0
**Target:** Omarchy 4.x / Hyprland 0.56+ / default `dwindle` layout  
**Plugin id:** `io.github.smariconde.workspace-layout-presets`
**Scope decision:** one saved profile represents **one workspace only**.

## 1. Product statement

Workspace Layout Presets is a real Omarchy/Quickshell bar plugin that lets a
user save a named arrangement for the current workspace and later restore it
into an empty workspace. A profile describes applications, tiled split shape
and proportions, plus floating-window geometry. It deliberately does **not**
save application documents, browser tabs, credentials, or a whole-desktop
session.

The core promise is:

> Save a workspace as `coding`; later restore `coding` without rearranging or
> closing windows anywhere else on the desktop.

This is a layout preset system, not a session manager and not a replacement
for hibernation.

## 2. Why a per-workspace product

Global session restoration is inherently invasive: it can move windows across
monitors, relaunch apps that are already running, or close a user's unrelated
work. This product instead acts only on an explicitly chosen target workspace.

- Saving reads only the active workspace.
- Restoring targets the active workspace by default.
- Version 1 refuses to restore into a non-empty target workspace.
- It does not modify monitor configuration, Hyprland autostart, global window
  rules, existing workspaces, or other applications.
- Existing workspaces already pinned to monitors by the user's own Omarchy
  configuration stay that way.

This limitation is intentional. It makes the common use case reliable: create
an empty workspace, choose a preset, and get the intended layout there.

## 3. User experience

The plugin is a compact widget in the Omarchy status bar. Clicking it opens a
panel; it does not need an entry in the general Omarchy Trigger menu.

### 3.1 Primary flows

**Save a preset**

1. The user switches to a workspace and arranges its windows.
2. They click the status-bar icon and choose **Save current workspace**.
3. The panel asks for a profile name and shows validation warnings, if any.
4. If a browser window could be either the browser or an installed Omarchy
   webapp, the panel shows its transient title and asks the user to choose the
   launcher. An unambiguous workspace needs no extra confirmation.
5. The plugin writes a versioned profile and confirms the number of tiled,
   floating, and unresolved windows.

**Restore a preset**

1. The user switches to an empty workspace.
2. They open the panel and choose a preset.
3. A concise preview shows how many applications will open, the target
   workspace, and only actionable warnings. The selected preset's app list
   remains visible; internal layout modes and compatibility mechanics are not
   exposed.
4. The user confirms **Restore** in that preview; no second confirmation is shown.
5. The plugin launches only the needed apps into that workspace, reconstructs
   the Dwindle tree, then positions floating windows.

**Manage presets**

The panel offers Rename, Duplicate, Delete, Inspect and Export. Delete always
requires confirmation. Inspect presents the human-readable profile data and
does not execute any command.

### 3.2 Explicit non-goals for V1

- No automatic restore on login.
- No browser tab capture or restoration.
- No whole-desktop or multi-workspace snapshots.
- No restore into non-empty workspaces and no automatic closing of windows.
- No `master`, `scrolling`, group/tabbed, special-workspace or fullscreen
  layout-tree reconstruction beyond retaining a single fullscreen window.
- No system privileges, package installation, changes under `/usr/share`, or
  writes to unrelated Omarchy configuration.

These can be considered only after V1 is stable.

## 4. Functional requirements

### FR-1 — Status-bar panel

The plugin must declare an Omarchy `bar-widget` and appear in the right bar
section by default. The widget opens a keyboard-accessible panel containing
save, list, preview, restore, rename, duplicate and delete actions.

### FR-2 — Capture current workspace

Capture the active workspace through `hyprctl -j activeworkspace`, `hyprctl -j
clients`, and `hyprctl -j monitors`. Capture only clients whose workspace ID
equals the active workspace ID.

For each captured client, record:

- logical application identity and window-match data;
- tiled/floating/fullscreen state;
- rectangle (`at`, `size`) in the workspace's usable coordinate space;
- workspace layout type and monitor fingerprint for compatibility checks;
- a safe launch descriptor, or an explicit `unresolved` status.

Never store PID, window address, command lines from `/proc`, browser URLs,
tabs, environment variables, terminal history, or document paths in a saved
profile. They are transient, may contain secrets, and are not needed for a
layout preset.

Omarchy webapps commonly share the default browser's window class. Capture may
use a window title transiently to suggest an installed webapp, but must require
user review before assigning it and must never write that title to a profile or
capture draft. Capture drafts are private, expire after five minutes, and store
only profile-safe data plus the bounded desktop IDs offered for each node.

### FR-3 — Dwindle tree inference

For up to 10 tiled windows, infer a binary Dwindle tree from their rectangles.
The output must contain an anchor plus ordered split operations, each with:

- focus node;
- split direction (`left`, `right`, `up`, `down`);
- new node;
- normalized split ratio.

If the geometry cannot be unambiguously represented as a Dwindle tree, the
save still succeeds but marks the profile `layoutConfidence: "fallback"` and
explains that only launch/order restoration is available. The user must see
this warning before relying on the preset.

### FR-4 — Floating windows

Floating windows restore their state and geometry relative to the saved
workspace usable rectangle. Coordinates and sizes must be scaled to the
current target monitor's usable rectangle, then clamped so the window remains
reachable onscreen.

### FR-5 — Safe launch resolution

The plugin must prefer `.desktop` application IDs and a structured argument
array. It must not save or execute a shell command string scraped from a
process command line.

Launch resolution order:

1. a valid desktop entry whose `StartupWMClass` or app ID matches the window;
2. a user-reviewed installed `.desktop` ID for ambiguous browser/webapp windows;
3. unresolved — restoration skips the entry and reports it clearly.

An unresolved window never causes a restore to fail destructively.
Desktop IDs may contain spaces because Omarchy names webapp files from their
display names, but they must remain a single non-traversing filename component.
Profiles store only that ID; restore rereads the installed desktop entry and
constructs argv without invoking a shell.

### FR-6 — Preview and restore

Before any restore, present a plan with `launch`, `skip`, `warning` and
`blocked` entries. The restore action is enabled only when:

- Hyprland version and layout are supported;
- the active target workspace is empty;
- the profile schema is valid;
- no profile entry requires unsafe command execution.

The target workspace is focused before each controlled placement. The plugin
rebuilds tiled windows in recorded order using Hyprland's Lua dispatch bridge:
focus the exact previously observed window address -> `preselect` direction ->
place the new window -> translate its normalized side fraction to Hyprland's
exact split-ratio scale. It then enables and positions floating windows.

At the end, the plugin compares the resulting client identities and tiled
geometry to the planned state and presents a concise success/partial-success
report. A matching application count alone is not considered success.

### FR-7 — Profile data and export

Store profiles under:

```text
$XDG_DATA_HOME/omarchy-workspace-layout-presets/profiles/
```

Use `$HOME/.local/share/omarchy-workspace-layout-presets/profiles/` when
`XDG_DATA_HOME` is unset. Keep UI settings under
`$XDG_CONFIG_HOME/omarchy-workspace-layout-presets/`.

Profiles are human-readable JSON, schema-versioned and atomically written:
write to a private sibling temporary file, `fsync`, validate, then rename.
Export creates a copy chosen by the user; import validates first and never
overwrites without a clear conflict choice.

## 5. Profile format (V1)

```json
{
  "schemaVersion": 1,
  "name": "coding",
  "createdAt": "2026-09-02T12:00:00Z",
  "source": {
    "hyprlandLayout": "dwindle",
    "workspace": { "name": "3" },
    "monitor": { "connector": "HDMI-A-2", "usableWidth": 1920, "usableHeight": 1048 }
  },
  "layoutConfidence": "exact",
  "tiled": {
    "anchor": "editor",
    "nodes": [
      {
        "id": "editor",
        "app": { "desktopId": "code", "wmClass": "Code", "ordinal": 1 },
        "launch": { "kind": "desktop", "desktopId": "code" }
      },
      {
        "id": "terminal",
        "app": { "desktopId": "kitty", "wmClass": "kitty", "ordinal": 1 },
        "launch": { "kind": "desktop", "desktopId": "kitty" }
      }
    ],
    "splits": [
      { "focus": "editor", "direction": "right", "new": "terminal", "ratio": 0.58 }
    ]
  },
  "floating": [],
  "warnings": []
}
```

`ordinal` distinguishes repeated application instances only as a best effort.
The UI must flag repeated, indistinguishable windows at save time; exact
identity cannot be guaranteed after a reboot without app-specific support.

## 6. Architecture

```text
BarWidget.qml
  └─ Panel.qml                 UI, accessibility, confirmations, notifications
       └─ layoutctl             one small, typed backend command
            ├─ capture          prepares/commits safe capture and webapp review
            ├─ plan             produces a JSON-only preview; changes nothing
            ├─ restore          executes an approved plan and returns structured results
            └─ profile          list/show/rename/duplicate/delete/export/import
```

### 6.1 Plugin files

```text
omarchy-workspace-layout-presets/
  manifest.json
  BarWidget.qml
  Panel.qml
  qml/
    ProfileList.qml
    RestorePreview.qml
    ConfirmDialog.qml
  backend/
    layoutctl.py
    capture.py
    infer_dwindle.py
    launchers.py
    restore.py
    profile_store.py
  tests/
    fixtures/
    test_infer_dwindle.py
    test_profile_store.py
    test_restore_plan.py
  README.md
  LICENSE
```

Use Python 3 standard library for the backend unless a dependency delivers a
clear safety benefit. QML must invoke it with argument arrays, receive JSON,
and never build shell snippets from profile values. Keep all Hyprland dispatch
syntax centralized in `restore.py`.

### 6.2 Plugin manifest

The initial manifest has one kind, `bar-widget`, and no autostart service.
Use reverse-domain ownership for its ID and semantic versioning. It must pass
`omarchy plugin validate` before release.

### 6.3 Compatibility guard

On capture and restore, detect:

- an active Hyprland socket and parseable `hyprctl` JSON;
- Hyprland version meeting the tested minimum;
- `dwindle` as active layout;
- support for the exact Lua bridge dispatches used by this Omarchy version;
- a valid, non-special, numeric or named regular workspace.

On failure, show why and perform no state change. Never fall back to legacy
dispatch syntax silently.

## 7. Security and conflict rules

1. The plugin runs unsandboxed inside `omarchy-shell`; treat every profile,
   window title, desktop entry and subprocess result as untrusted input.
2. Use JSON parsing and argument arrays only. No `eval`, `sh -c`, command
   interpolation, or unquoted dispatch construction from profile fields.
3. Validate profile names, IDs, geometry, ratios, desktop IDs and schema
   before writing or restoring.
4. Default restore only touches an empty, explicitly active workspace.
5. Never close, kill, relocate, or reuse a window outside that workspace.
6. Never enable automatic restore, edit `~/.config/hypr/autostart.lua`, or
   alter `shell.json` outside normal plugin enablement in V1.
7. Do not read browser session stores or `/proc/<pid>/cmdline` for profile
   persistence.
8. A failed launch, timeout, or invalid profile produces a partial-result
   report; it does not clear the workspace or retry indefinitely.
9. All destructive profile actions require confirmation; a restore itself is
   non-destructive under the V1 empty-workspace rule.

## 8. Inspiration and deliberate adaptations

### Desktop Preset

Adopt:

- inference of a Dwindle split tree from rectangles;
- replay through focus + `preselect` + placement;
- reapplication of a split ratio after later child splits can disturb it;
- dry-run/preview as a first-class operation;
- an explicit fallback when layout inference is ambiguous.

Do not adopt:

- `install.sh` changes to user autostart/menu configuration;
- loading with `--clear` as a normal workflow;
- a plaintext format that embeds arbitrary shell command strings;
- collecting process command lines as the primary launcher source;
- automatic launch on login in V1.

### Workspace Restorer

Adopt:

- an Omarchy `bar-widget` manifest and QML panel interaction;
- named profiles and a clear profile-management UI;
- monitor/workspace-aware capture, structured notifications and result
  reporting;
- careful validation of values sent to Hyprland.

Do not adopt:

- global desktop restore semantics;
- moving matching windows from other workspaces;
- browser tab capture;
- treating stored `splitRatio` as sufficient to rebuild a tiled layout without
  reconstructing the split tree.

## 9. Acceptance criteria

### MVP gate

- [ ] `omarchy plugin validate` accepts the repository manifest.
- [ ] Plugin can be added from a local Git checkout, enabled, disabled,
  updated and removed without modifying packaged Omarchy files.
- [ ] Status-bar widget opens a usable, keyboard-accessible panel.
- [ ] A workspace with 1–5 unique tiled apps saves and restores the same
  Dwindle split topology and ratios within a 2% tolerance.
- [ ] Floating windows restore scaled geometry and remain fully reachable.
- [ ] A target workspace containing any client blocks restore with no change.
- [ ] An invalid, tampered or old-schema profile is rejected safely.
- [ ] Missing/unresolved apps yield a partial-success report; no existing
  client is closed or moved.
- [ ] Capturing/restoring neither reads nor writes browser tabs, terminal
  history, `/proc` command lines, user documents or credentials.
- [ ] Tests cover geometry inference, profile validation, path safety, launch
  planning and dispatch argument escaping.

### Manual compatibility matrix

Test each release against:

| Case | Expected result |
|---|---|
| One tiled window | Restores as sole tiled window |
| Two vertical and two horizontal splits | Topology and ratio match |
| Nested 2x2 Dwindle layout | Ratio survives second-pass correction |
| One floating window | State, scaled position and size match |
| Duplicate terminal windows | Warning at save; no false exact guarantee |
| Missing desktop entry | Preview marks unresolved; restore remains safe |
| Active workspace non-empty | Restore disabled; nothing moves |
| Changed monitor resolution | Ratios retained; floating window clamped |
| Unsupported Hyprland dispatch | Clear block message; no mutation |

## 10. Delivery roadmap

### Milestone 0 — Foundation

- Create the Git repository, MIT license, README, manifest and CI.
- Add fixture-driven geometry/tree tests before writing UI.
- Build a no-op bar widget and backend `profile list` command.

### Milestone 1 — Safe capture and inspection

- Capture current workspace to validated JSON.
- Implement list, inspect, rename, duplicate, delete and export.
- Flag non-Dwindle, duplicate-window and unresolved-launch conditions.
- No launch or restore yet.

### Milestone 2 — Exact empty-workspace restore

- Implement `plan` and preview.
- Restore unique tiled Dwindle windows and floating windows into an empty
  active workspace.
- Add timeouts, final verification and structured partial-success reporting.

### Milestone 3 — Release hardening

- Exercise the manual compatibility matrix on the target machine.
- Audit subprocess boundaries and profile parser.
- Add version guard and release notes.
- Publish a tagged release; install through `omarchy plugin add <repo-url>`.

### Explicitly deferred

- Restore into non-empty workspaces (merge/replace modes).
- Profile collections spanning multiple workspaces/monitors.
- Auto-load after login.
- App-specific extensions such as terminal working directories or browser
  tabs.

## 11. Repository and maintenance policy

- Keep the plugin as a public Git repository with tagged, reviewed releases.
- Develop from a local Git checkout and install it through Omarchy's plugin
  mechanism, not by copying into `/usr/share/omarchy`.
- Before every update, review the diff shown by `omarchy plugin update`.
- Pin supported Omarchy/Hyprland versions in the README and CI fixtures.
- Bump the profile schema only through an explicit migration; retain original
  profiles until migration succeeds.
- Do not claim marketplace publication until the plugin has passed the MVP
  gate and has a documented maintenance owner.

## 12. Source material reviewed

- [`laleshii/omarchy-desktop-preset`](https://github.com/laleshii/omarchy-desktop-preset)
  (MIT): Dwindle tree inference, replay, ratio correction, fallback behavior
  and known single-workspace limitations.
- [`Davedes83/workspace-restorer`](https://github.com/Davedes83/workspace-restorer)
  (MIT): Omarchy bar-widget manifest, QML profile UX, monitor/workspace
  capture and restore reporting.
- [Omarchy shell plugin contract](https://github.com/basecamp/omarchy/blob/master/shell/README.md):
  manifest discovery, `omarchy plugin add/update/validate`, and unsandboxed
  execution model.
