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
│   ├── plan_store.py         # Single-use approval tokens for a planned restore
│   ├── profile_store.py      # Schema validation and atomic profile operations
│   └── atomic_json.py        # Private, all-or-nothing JSON write primitive
├── tests/
│   ├── fixtures/             # Captured Hyprland and profile JSON fixtures
│   ├── test_infer_dwindle.py
│   ├── test_profile_store.py
│   ├── test_plan_store.py
│   └── test_restore_plan.py
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

`approved-plan-id` es un token opaco emitido y guardado por `plan` (ver M4). No
codifica operaciones, argumentos de lanzamiento ni geometría, y `restore` no
aceptará otra fuente de instrucciones. El token está asociado al perfil y al
workspace objetivo que se comprobó vacío; se invalida al usarlo o al vencer su
ventana de aprobación. Hasta M5, `restore` devuelve el error JSON
`unimplemented` y no toca Hyprland.

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

### Captura segura (M2)

`capture.py` concentra las cuatro consultas de sólo lectura a Hyprland,
siempre mediante arrays fijos: `activeworkspace`, `clients`, `monitors` y
`getoption general:layout`. Su adaptador es inyectable para que las fixtures
anonimizadas cubran la transformación sin una sesión gráfica. La captura exige
un workspace regular activo, su único monitor asociado y el layout `dwindle`.

Sólo conserva el nombre del workspace, el conector y rectángulo útil del
monitor, clase de ventana, estado tiled/floating y geometría floating
normalizada. No conserva títulos, direcciones de ventana, PID ni otros campos
presentes en `hyprctl`. El descriptor de lanzamiento se resuelve únicamente a
un identificador de un `.desktop` de tipo `Application` con `Exec`; `Exec`
nunca se guarda ni se ejecuta en esta etapa. La falta de un descriptor y las
instancias repetidas son advertencias explícitas.

La inferencia M3 trabaja sólo con geometría tiled y no lee ni persiste campos
adicionales de Hyprland. Acepta particiones binarias *slicing*: cada corte
vertical u horizontal debe abarcar todo el rectángulo de su nodo. Los cortes
equivalentes se resuelven de forma determinista (vertical antes que horizontal
y luego por coordenada). El ratio es la fracción que ocupa el lado nuevo,
medida en el centro del espacio entre ventanas. Si no existe un árbol slicing,
la captura conserva el orden estable de nodos, marca
`layoutConfidence: "fallback"` y añade una advertencia explícita; de otro modo
guarda el ancla y los splits inferidos con `layoutConfidence: "exact"`.

Un estado fullscreen, un layout no soportado, datos geométricos inválidos o
más de diez ventanas de cada tipo bloquean la captura antes de escribir. El ID
opaco se deriva del nombre visible normalizado a minúsculas ASCII y la creación
no sobrescribe un perfil existente.

### Plan de restauración (M4)

`restore.py` produce el plan y es el único módulo que albergará sintaxis de
dispatch de Hyprland. `build_plan` es puro: recibe el perfil validado y las
mismas cuatro respuestas JSON que usa la captura, y devuelve una vista previa
sin tocar el escritorio. `plan_profile` añade la lectura del perfil, las
consultas de sólo lectura y la emisión del token.

Un plan bloquea antes de existir si el layout activo no es `dwindle`
(`unsupported_layout`), el workspace activo es especial
(`unsupported_workspace`), no hay un monitor utilizable
(`monitor_unavailable`), el workspace objetivo contiene alguna ventana
(`workspace_not_empty`) o ninguna ventana del perfil tiene lanzador seguro
(`nothing_to_restore`). Un perfil que ya no valida es `error`, no un plan.

El plan expone `entries` (`launch` o `skip` por ventana), `steps`,
`layoutMode`, `target` y `summary`. `layoutMode` es `tree` sólo cuando el
perfil es `exact` y todas sus ventanas tiled tienen lanzador; si una ventana
tiled queda sin resolver, degrada a `order` con la advertencia
`tree_incomplete` en vez de reconstruir un árbol incompleto. Las ventanas
floating se escalan desde la geometría normalizada al rectángulo útil actual y
se recortan para seguir alcanzables (`geometry_clamped`); un monitor distinto
al guardado añade `monitor_changed`.

`plan_store.py` guarda cada aprobación bajo
`$XDG_RUNTIME_DIR/omarchy-workspace-layout-presets/plans/<token>.json`, con el
directorio de datos como único respaldo. El registro contiene sólo `planId`,
`profileId`, `profileDigest`, `createdAt`, `expiresAt` y el `target`
comprobado: ninguna operación, argumento ni geometría. `restore` reconstruirá
el plan desde el perfil validado, comprobará que el digest y las condiciones
siguen vigentes y consumirá el token, que es de un solo uso y caduca a los 300
segundos. Un plan bloqueado no emite token.

`atomic_json.py` concentra la escritura privada (`0600`) y atómica que usan
tanto `profile_store` como `plan_store`; cada almacén conserva sus rutas, su
validación y su vocabulario de errores.

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

Como QML ejecuta el archivo por ruta absoluta y no como módulo, `layoutctl.py`
añade el directorio del plugin a `sys.path` cuando se invoca sin paquete y usa
importaciones `backend.*` en ambos modos. Una prueba ejecuta el archivo como
proceso independiente para que esa vía no vuelva a romperse en silencio.

## Desarrollo

La secuencia, estado y criterios de salida viven en
[`development-plan.md`](development-plan.md). Esta arquitectura conserva sólo
los límites entre componentes y los contratos que deben mantenerse estables.
