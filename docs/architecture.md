# Plugin structure

```text
.
├── manifest.json             # Omarchy bar-widget contract
├── BarWidget.qml             # Compact bar entry point and panel trigger
├── Panel.qml                 # Accessible panel flow and notifications
├── qml/
│   ├── ProfileList.qml       # List, inspect, rename, duplicate, delete
│   ├── RestorePreview.qml    # Read-only launch/skip/warning/blocked plan
│   └── ConfirmDialog.qml     # Required destructive-action confirmation
├── backend/
│   ├── layoutctl.py          # Typed JSON CLI boundary called with argv arrays
│   ├── capture.py            # hyprctl JSON capture and profile construction
│   ├── infer_dwindle.py      # Rectangle-to-binary-tree inference
│   ├── launchers.py          # Desktop-entry-only launch resolution
│   ├── restore.py            # Plan, guarded replay, verification
│   └── profile_store.py      # Schema validation and atomic profile operations
├── tests/
│   ├── fixtures/             # Captured Hyprland and profile JSON fixtures
│   ├── test_infer_dwindle.py # planned with Milestone 1
│   ├── test_profile_store.py
│   └── test_restore_plan.py  # planned with Milestone 2
└── .github/workflows/tests.yml
```

## Boundaries

`BarWidget.qml` owns the small bar affordance. `Panel.qml` owns interaction,
accessibility, confirmations, and rendering JSON returned by `layoutctl`.
The backend owns all Hyprland and filesystem interactions. QML passes only
fixed executable paths and argument arrays; it never constructs shell source
from a profile.

`layoutctl` exposes these future JSON-only command families:

```text
capture <name>
plan <profile-id>
restore <approved-plan-id>
profile list|show|rename|duplicate|delete|export|import
```

The restore command is deliberately separate from planning so the UI can show
launch, skip, warning, and blocked entries before a state-changing action.

## Desarrollo

La secuencia, estado y criterios de salida viven en
[`development-plan.md`](development-plan.md). Esta arquitectura conserva sólo
los límites entre componentes y los contratos que deben mantenerse estables.
