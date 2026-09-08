# Hoja de ruta de desarrollo

**Estado:** M5 en curso · próxima sesión: spike de dispatches en sesión Omarchy
**Objetivo:** una primera beta de perfiles de layout para un workspace
`dwindle` en Omarchy 4.x.

## Cómo usar este documento

Es el tablero de ejecución y de estado, no otra especificación. Antes de
empezar una sesión, leer el requisito correspondiente en
[`spec.md`](../spec.md) y el límite de componentes en
[`architecture.md`](architecture.md). Al terminar, actualizar únicamente el
estado y la siguiente sesión de esta hoja de ruta.

Una sesión debe terminar con un cambio acotado, pruebas ejecutadas y un
criterio de salida verificable. Si aparece una decisión que modifica el
contrato, registrarla primero en la arquitectura; no esconderla en código.

## Estado actual

| Área | Estado | Evidencia |
| --- | --- | --- |
| Manifiesto y puntos de entrada | Hecho | `manifest.json`, QML inerte |
| Almacenamiento de perfiles | Hecho | esquema V1 profundo, operaciones atómicas y sin sobrescritura |
| CLI | Hecho para perfiles | list/show/rename/duplicate/delete/export/import con JSON estable |
| Captura y lanzadores | Hecho | fixtures anonimizadas, adaptador `hyprctl` de sólo lectura y resolución `.desktop` |
| Inferencia Dwindle | Hecho | inferencia pura de particiones slicing y fallback explícito |
| Planificación | Hecho | `plan` de sólo lectura, bloqueos explícitos y token de un solo uso |
| Restauración | En curso | revalidación, atestación efímera, executor argv y verificación conectados; falta la prueba end-to-end del replay |
| Interfaz | Pendiente | componentes reservados |
| Validación en Omarchy | Pendiente | aún no ejecutada |

La suite actual se ejecuta con `python -m unittest discover -v`.

## Hitos

| Hito | Entregable | Depende de | Criterio de salida | Estado |
| --- | --- | --- | --- | --- |
| M0 | Contrato CLI y puente QML → backend | — | El comando puede llamarse con argumentos separados y devuelve resultados JSON que la UI puede consumir | Hecho |
| M1 | Perfiles completos | M0 | Validación profunda y operaciones show/rename/duplicate/delete/export/import cubiertas por tests | Hecho |
| M2 | Captura segura | M1 | Fixtures de Hyprland → perfil válido, sin datos sensibles ni comandos de shell | Hecho |
| M3 | Inferencia Dwindle | M2 | Árbol exacto para geometrías soportadas; `fallback` explícito para las demás | Hecho |
| M4 | Plan de restauración | M1–M3 | `plan` es de sólo lectura y bloquea invariablemente workspaces no vacíos | Hecho |
| M5 | Restauración controlada | M4 | Ejecuta sólo un plan aprobado, verifica el resultado y nunca cierra ventanas | En curso |
| M6 | Interfaz V1 | M0, M1, M4, M5 | Guardar, gestionar, previsualizar y restaurar desde el widget accesible | Pendiente |
| M7 | Hardening y beta | M0–M6 | Suite, validación del plugin, matriz manual y documentación de límites completas | Pendiente |

## Próximas sesiones

### M0.1 — Contrato de `layoutctl` — Hecho

- Definir la envoltura JSON común para éxito, error, advertencia y bloqueo.
- Fijar argumentos y códigos de salida de `capture`, `plan`, `restore` y
  `profile`.
- Diseñar un identificador de plan aprobado que no acepte instrucciones de
  restauración arbitrarias desde QML.
- Añadir pruebas de parsing y documentar el resultado en la arquitectura.

**Cierre:** contrato escrito y pruebas que fijan sus argumentos y respuestas.

**Evidencia:** `backend/layoutctl.py`, `tests/test_layoutctl.py` y el contrato
CLI v1 en `docs/architecture.md`.

### M0.2 — Spike de proceso QML — Hecho

- Verificar en la versión objetivo de Omarchy/Quickshell un proceso con argv,
  stdout y código de salida observables desde QML.
- Mostrar el resultado de `layoutctl profile list` en una prueba QML mínima.
- Ejecutar `omarchy plugin validate .` y `qmllint` en un entorno Omarchy real.

**Cierre:** integración elegida y documentada. Si no permite argv y lectura de
resultado de forma segura, rediseñar M0 antes de iniciar M1.

**Evidencia:** `qml/LayoutctlClient.qml` usa `Process` con argv fijo;
`tests/test_qml_process_probe.py` ejecuta el probe real en Quickshell 0.3.1 y
comprueba stdout JSON y código de salida. `omarchy plugin validate .` pasa.

### M1 — Perfiles completos — Hecho

- Validar en profundidad el esquema V1: identidad, descriptores de launcher
  seguros, árbol Dwindle, geometría floating y advertencias.
- Implementar `show`, `rename`, `duplicate`, `delete`, `export` e `import`.
- Exigir `--confirm` al borrar y bloquear conflictos de importación, duplicado
  o exportación sin sobrescribir ningún archivo.

**Cierre:** los perfiles inválidos o con datos ajenos al esquema se rechazan;
las operaciones de gestión responden exclusivamente el sobre JSON del contrato
y están cubiertas por pruebas de almacenamiento y CLI.

**Evidencia:** `backend/profile_store.py`, `backend/layoutctl.py`,
`tests/test_profile_store.py`, `tests/test_layoutctl.py`.

### M2 — Captura segura — Hecho

- Consultar exclusivamente JSON de `hyprctl` para workspace activo, clientes,
  monitores y layout activo mediante un adaptador simulable.
- Conservar sólo los campos permitidos por el perfil V1 y normalizar la
  geometría floating al rectángulo útil del monitor.
- Resolver launchers sólo a IDs de `.desktop`; informar instancias repetidas,
  launchers no resolubles y fallback de árbol sin ejecutar nada.
- Bloquear antes de escribir ante workspace/layout/monitor inválidos,
  fullscreen no representable, geometría inválida, límites excedidos o una
  colisión de ID de perfil.

**Cierre:** fixtures de Hyprland generan un perfil validado, atómico y sin
datos sensibles; `layoutctl capture <name>` mantiene el sobre JSON.

**Evidencia:** `backend/capture.py`, `backend/launchers.py`,
`tests/test_capture.py`, `tests/test_launchers.py`.

### M3 — Inferencia Dwindle — Hecho

- Inferir un árbol binario sólo para geometrías tiled representables como
  cortes completos verticales u horizontales.
- Calcular ratios en el centro de los gaps y emitir una secuencia determinista
  de ancla y operaciones de split.
- Conservar el perfil válido de fallback y una advertencia explícita cuando la
  geometría es escalonada, solapada o no admite un árbol slicing.

**Cierre:** las geometrías soportadas se guardan con
`layoutConfidence: "exact"`; las demás no inventan un árbol de restauración.

**Evidencia:** `backend/infer_dwindle.py`, `backend/capture.py`,
`tests/test_infer_dwindle.py`, `tests/test_capture.py`.

### M4 — Plan de restauración — Hecho

- Construir la vista previa desde el perfil validado y las mismas consultas de
  sólo lectura de la captura, sin tocar el escritorio.
- Bloquear explícitamente workspace ocupado, layout no soportado, workspace
  especial, monitor inutilizable y perfil sin lanzadores resolubles.
- Escalar y recortar la geometría floating al monitor objetivo y degradar a
  orden de lanzamiento cuando el árbol no puede reconstruirse.
- Emitir un token opaco de un solo uso que guarda las condiciones comprobadas
  y no instrucciones.

**Cierre:** `plan` responde el sobre JSON con vista previa o bloqueo, un plan
bloqueado no emite token y ninguna consulta modifica Hyprland.

**Evidencia:** `backend/restore.py`, `backend/plan_store.py`,
`backend/atomic_json.py`, `tests/test_restore_plan.py`,
`tests/test_plan_store.py`, `tests/test_layoutctl.py`. Verificado además
contra un Hyprland real: el workspace activo ocupado responde `blocked` con
`workspace_not_empty` sin escribir ningún plan.

### M5 — Restauración controlada — En curso

- [x] Comprobar el contrato del guardián de compatibilidad de `spec.md` §6.3:
  versión mínima, layout activo y evidencia separada para el puente Lua.
- [x] Ejecutar un spike en una sesión Omarchy real que verifique los dispatches
  exactos de focus, `preselect`, colocación y ratio. El focus pasó con el probe
  QML; `preselect r`, apertura tiled y `splitratio 1.0 exact` pasaron
  manualmente en el workspace 4.
- [x] Preparar `qml_hyprland_dispatch_probe.qml`, que verifica de forma no
  destructiva el puente `hyprctl dispatch` → Lua enfocando el workspace activo.
- [x] Ejecutar el probe en Omarchy: `hl.dsp.focus(...)` respondió `success: true`.
- [x] Verificar en un workspace de prueba la geometría floating: `float(set)`,
  `move({ x = 100, y = 100, relative = false })` y
  `resize({ x = 600, y = 400, relative = false })` funcionaron en el
  workspace 4 sin afectar el workspace 1.
- [x] Resolver `.desktop` a argv en `backend.launchers` sin shell, sin field
  codes no resueltos y rechazando entradas que requieren `sh -c`.
- [x] Compilar el plan a acciones explícitas de replay en `backend.restore`
  sin ejecutar todavía: lanzamientos argv y dispatches Lua para tiled/floating.
- [x] Preparar la revalidación pura del digest del perfil y de las condiciones
  del workspace antes de consumir un token.
- [x] Consumir el token sólo después de esa revalidación, y rechazar cualquier
  aprobación caducada o ya usada.
- [x] Compilar y reproducir acciones mediante un executor inyectable con
  `argv`, reenfoque del workspace objetivo y espera de ventanas.
- [x] Verificar el resultado contra el plan y devolver un informe de éxito
  parcial sin cerrar ni mover ninguna ventana.
- [x] Conectar el probe QML a una atestación efímera de runtime y exigirla
  durante `layoutctl restore`.
- [ ] Probar el executor real en un workspace descartable con la atestación
  verificada y revisar la identificación de ventanas repetidas.

**Cierre:** `restore` ejecuta exclusivamente un plan aprobado y vigente, o
bloquea sin cambiar nada.

**Progreso de esta sesión:** el probe QML ahora genera una atestación efímera
privada después de un dispatch exitoso; `layoutctl restore` la valida contra la
versión actual antes de habilitar el replay. La suite tiene 76 pruebas (2 se
omiten sin sesión Wayland).
Queda pendiente la prueba end-to-end del replay controlado.

## Secuencia posterior

1. M5: restaurar tiled y floating con verificación.
2. M6: construir la UI sólo sobre las operaciones ya probadas.
3. M7: endurecer, probar en máquinas reales y publicar la beta.

## Cierre de cada sesión

1. Ejecutar las pruebas afectadas y `python -m unittest discover -v`.
2. Actualizar la tabla de estado y la siguiente sesión si el hito avanzó.
3. Actualizar `spec.md` sólo si cambió un requisito; actualizar
   `architecture.md` sólo si cambió una decisión o límite de componentes.
4. No instalar, habilitar ni copiar el plugin a la configuración de Omarchy
   durante el desarrollo sin autorización explícita.
