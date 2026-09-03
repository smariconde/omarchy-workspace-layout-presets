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
profile list|show|rename|duplicate|delete --confirm|export|import
```

The restore command is deliberately separate from planning so the UI can show
launch, skip, warning, and blocked entries before a state-changing action.

## Contrato CLI v1 (M0)

La UI invoca exclusivamente un ejecutable fijo y un array de argumentos. No
compone una línea de shell, y el contenido de un perfil nunca se convierte en
argumentos nuevos ni en código. La gramática pública es:

```text
layoutctl capture <name>
layoutctl plan <profile-id>
layoutctl restore <approved-plan-id>
layoutctl profile list
layoutctl profile show <profile-id>
layoutctl profile rename <profile-id> <name>
layoutctl profile duplicate <profile-id> <new-profile-id>
layoutctl profile delete <profile-id> --confirm
layoutctl profile export <profile-id> <destination>
layoutctl profile import <source>
```

Cada invocación escribe exactamente un objeto JSON en stdout, tanto en éxito
como en error. La forma común es:

```json
{
  "contractVersion": 1,
  "status": "ok | error | blocked",
  "data": {},
  "warnings": [],
  "blocked": [],
  "error": null
}
```

`warnings` y `blocked` contienen objetos con `code` y `message`; una respuesta
`blocked` nunca realiza cambios. Una respuesta `error` lleva el detalle en
`error` (`code`, `message`). Los códigos de proceso son 0 para éxito, 1 para
un error de operación, 2 para argumentos inválidos y 3 para un comando
declarado pero todavía no implementado.

`approved-plan-id` será un token opaco emitido y guardado por `plan` en M4. No
codifica operaciones, argumentos de lanzamiento ni geometría, y `restore` no
aceptará otra fuente de instrucciones. El token estará asociado al perfil y al
workspace objetivo que se comprobó vacío; se invalidará después de usarlo o
si cambian las condiciones comprobadas. Hasta M4, `plan` y `restore` devuelven
el error JSON `unimplemented` y no tocan Hyprland.

### Perfil V1 y operaciones de almacenamiento (M1)

`profile_store.py` valida el perfil completo antes de escribirlo, importarlo o
devolverlo con `show`. El esquema es cerrado: campos desconocidos se rechazan
para evitar que los perfiles acumulen líneas de comando, documentos, URLs u
otros datos de sesión. Cada ventana tiene un `id` seguro, `app`
(`desktopId` opcional, `wmClass`, `ordinal`) y un `launch` de tipo `desktop`
con un `desktopId` validado o de tipo `unresolved`. Los nodos tiled forman un
árbol con un ancla y operaciones que añaden cada nodo una sola vez; los ratios
son finitos y están estrictamente entre 0 y 1. Las ventanas floating usan
`geometry` normalizada (`x`, `y`, `width`, `height`) entre 0 y 1.

Los IDs de perfil se convierten exclusivamente en nombres bajo el directorio
de perfiles. `show`, `rename` y `duplicate` devuelven el perfil validado.
`delete` exige el argumento literal `--confirm`; sin él responde `blocked`
con `confirmation_required` y no llama al almacenamiento. Duplicate, import y
export crean archivos privados con escritura atómica sin sobrescritura; si el
destino ya existe responden `blocked` con `already_exists`. Import deriva el
ID del nombre base seguro del archivo elegido por la persona usuaria y bloquea
cualquier colisión.

### Integración QML → backend (M0.2)

En Omarchy 4.x con Quickshell 0.3.1, `qml/LayoutctlClient.qml` usa
`Quickshell.Io.Process`: su propiedad `command` recibe un array y no invoca un
shell. El único comando expuesto por ahora es el array fijo:

```text
[<ruta-local-del-plugin>/backend/layoutctl.py, "profile", "list"]
```

La ruta se resuelve desde el propio archivo QML y se acepta sólo si es una URL
`file:` local; `layoutctl.py` es ejecutable. `StdioCollector` espera el fin de
stdout y el manejador `onExited` entrega a QML el código de salida, el objeto
JSON ya parseado (o `null` si no es válido) y stderr. El proceso no se ejecuta
en modo detached: Quickshell lo termina al recargar o cerrar la shell.

Las futuras operaciones deben ser métodos explícitos del cliente con arrays
creados en código. No se añadirá un método genérico que reciba un comando, una
cadena de shell o argumentos derivados de perfiles.

## Desarrollo

La secuencia, estado y criterios de salida viven en
[`development-plan.md`](development-plan.md). Esta arquitectura conserva sólo
los límites entre componentes y los contratos que deben mantenerse estables.
