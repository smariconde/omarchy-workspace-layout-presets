# Hoja de ruta de desarrollo

**Estado:** candidato `v0.1.0` preparado · próxima sesión: tag y envío al marketplace
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
| Captura y lanzadores | Hecho | fixtures anonimizadas, resolución `.desktop` y revisión segura de webapps ambiguas |
| Inferencia Dwindle | Hecho | inferencia pura de particiones slicing y fallback explícito |
| Planificación | Hecho | `plan` de sólo lectura, bloqueos explícitos y token de un solo uso |
| Restauración | Hecho | replay end-to-end confirmado por el mantenedor en una sesión Omarchy real |
| Interfaz | Hecho para beta funcional | menú desplegable, captura, gestión, preview y confirmaciones conectadas al CLI |
| Validación en Omarchy | Hecho para beta | flujo live confirmado; `omarchy plugin validate .` pasa en Omarchy 4.0.2 |

La suite actual se ejecuta con `python -m unittest discover -v`.

## Hitos

| Hito | Entregable | Depende de | Criterio de salida | Estado |
| --- | --- | --- | --- | --- |
| M0 | Contrato CLI y puente QML → backend | — | El comando puede llamarse con argumentos separados y devuelve resultados JSON que la UI puede consumir | Hecho |
| M1 | Perfiles completos | M0 | Validación profunda y operaciones show/rename/duplicate/delete/export/import cubiertas por tests | Hecho |
| M2 | Captura segura | M1 | Fixtures de Hyprland → perfil válido, sin datos sensibles ni comandos de shell | Hecho |
| M3 | Inferencia Dwindle | M2 | Árbol exacto para geometrías soportadas; `fallback` explícito para las demás | Hecho |
| M4 | Plan de restauración | M1–M3 | `plan` es de sólo lectura y bloquea invariablemente workspaces no vacíos | Hecho |
| M5 | Restauración controlada | M4 | Ejecuta sólo un plan aprobado, verifica el resultado y nunca cierra ventanas | Hecho |
| M6 | Interfaz V1 | M0, M1, M4, M5 | Guardar, gestionar, previsualizar y restaurar desde el widget accesible | Hecho |
| M7 | Hardening y beta | M0–M6 | Suite, validación del plugin, matriz manual y documentación de límites completas | En curso: revisión del marketplace |
| M8 | Boceto del layout en el panel | M1, M3, M6 | Al seleccionar un preset se ve su disposición a escala, sin texto ni porcentajes | Hecho |

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
datos sensibles; `layoutctl capture prepare|commit` mantiene el sobre JSON.

**Evidencia:** `backend/capture.py`, `backend/capture_review.py`,
`backend/capture_store.py`, `backend/launchers.py`, `tests/test_capture.py`,
`tests/test_capture_review.py`, `tests/test_capture_store.py` y
`tests/test_launchers.py`.

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

### M5 — Restauración controlada — Hecho

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
- [x] Probar el executor real en un workspace descartable con la atestación
  verificada y revisar la identificación de ventanas repetidas.

**Cierre:** `restore` ejecuta exclusivamente un plan aprobado y vigente, o
bloquea sin cambiar nada.

**Progreso de esta sesión:** el probe QML ahora genera una atestación efímera
privada después de un dispatch exitoso; el flujo normal lo ejecuta al confirmar
**Restore** y `layoutctl restore` la valida contra la versión actual antes de
habilitar el replay. La interfaz no depende de evidencia creada manualmente.
Los launchers `.desktop` que usan `%f`, `%F`, `%u` o `%U` se ejecutan sin esos
argumentos cuando el preset no aporta archivos ni URLs; un error de compilación
queda contenido en el contrato JSON.
La espera posterior a cada lanzamiento toma una instantánea de las direcciones
del workspace y sólo acepta una ventana nueva, evitando que dos webapps con la
misma clase `Brave-browser` satisfagan accidentalmente la misma espera.
La primera prueba manual completa reveló dos diferencias semánticas: el focus
por clase elegía la webapp repetida incorrecta y la fracción 0–1 se enviaba sin
convertir a la escala exacta 0.1–1.9 de Dwindle. El replay ahora conserva la
dirección observada por `windowId`, enfoca por la dirección exacta de la ventana,
convierte el ratio y comprueba la geometría final en vez de declarar éxito sólo
por contar clases.
Una prueba con Chromium reveló que los launchers de aplicaciones también se
ejecutaban con el timeout de cinco segundos reservado para dispatches breves;
cuando Chromium iniciaba un proceso nuevo, ese timeout lo terminaba. Los
launchers ahora se crean sin espera, con `shell=False`, descriptores cerrados y
una sesión independiente, mientras el executor sigue detectando la ventana por
la nueva dirección de Hyprland con un plazo independiente de 30 segundos para
aplicaciones lentas.
El mantenedor confirmó el flujo end-to-end en su máquina Omarchy, incluido el
replay controlado desde la interfaz. Con esa evidencia se cierra M5; cada nueva
release debe repetir la matriz de compatibilidad de `spec.md`.

### M6 — Interfaz V1 — Hecho

- [x] Abrir y cerrar el panel desde el widget de la barra.
- [x] Listar y seleccionar perfiles mediante layoutctl.
- [x] Guardar el workspace activo con nombre.
- [x] Inspeccionar, renombrar, duplicar, exportar, importar y borrar con confirmación.
- [x] Generar preview de sólo lectura y exigir confirmación antes de restaurar.
- [x] Mostrar bloqueos, advertencias y resultados parciales del backend.

**Cierre:** el flujo completo de la beta funcional está disponible desde el menú.

**Ajuste de UX:** **Restore…** crea el preview y **Restore** confirma y ejecuta.
Se eliminó la segunda confirmación **Restore here**; un preview vencido exige
generar otro. El detalle y el preview muestran sólo nombres de apps, cantidad,
workspace objetivo y advertencias accionables; modos internos, clases de
ventana, monitor, categorías y mensajes técnicos del backend quedan ocultos.
Los resultados de procesos se notifican en el
siguiente ciclo de eventos para que Save y Delete puedan refrescar la lista
sin ser rechazados por el estado transitorio `running` de Quickshell. Además,
cada instancia vuelve a listar perfiles al abrirse para reflejar cambios
hechos desde otro workspace.

Las ventanas de Brave/Chromium que pueden ser una webapp abren una revisión
inline con `Ui.SearchableDropdown`: el título se usa sólo como pista transitoria, la
persona confirma un `.desktop` instalado o elige no restaurar esa ventana, y
el perfil guarda únicamente ese ID. Los nombres Omarchy con espacios son
válidos sin permitir traversal. Las capturas inequívocas conservan el guardado
directo sin un paso adicional.

**Nota de validación:** `omarchy plugin validate .` pasa en este entorno;
`qmllint` no está instalado. El mantenedor confirmó el flujo QML live en
Omarchy 4.0.2 con Quickshell 0.3.1.

### M7 — Hardening y beta — En curso

- [x] Ejecutar la suite completa y validar el manifest en Omarchy.
- [x] Confirmar el flujo end-to-end en una sesión real.
- [x] Fijar el ID público `io.github.smariconde.workspace-layout-presets`.
- [x] Documentar instalación, uso, desinstalación, dependencias y límites.
- [x] Añadir SemVer, changelog, política de releases y versión visible en UI.
- [x] Añadir guía de contribución, reporte privado de seguridad y templates.
- [x] Añadir una portada compatible con el marketplace.
- [x] Crear el commit y tag `v0.1.0`, publicar la GitHub Release y enviar el
  repositorio al marketplace.
- [x] Sacar del árbol instalable los ficheros de instrucciones para asistentes
  (`AGENTS.md`, `CLAUDE.md`), trasladar su documentación a nombres neutros y
  añadir `tools/check_release_payload.py` como guarda recursiva en la suite y
  en CI. Bloqueo de seguridad señalado por la revisión del marketplace sobre
  el commit `c59ce43`.
- [ ] Publicar `v0.2.0` y pedir validación y línea base de seguridad para el
  nuevo HEAD exacto de la rama por defecto.

**Cierre:** el tag publicado coincide con `manifest.json`, la release contiene
las notas de `CHANGELOG.md` y el marketplace acepta el commit validado.

### M8 — Boceto del layout en el panel — Hecho

- [x] Extraer la expansión «árbol de splits → rectángulos» a `layout_preview.py`
  y reutilizarla desde `restore.py`, para que exista una sola semántica del
  ratio.
- [x] Añadir el campo aditivo `layout` a `profile show`, con modo `exact` o
  `approximate` y la relación de aspecto del monitor de origen.
- [x] Dibujar `qml/LayoutMap.qml` junto a la lista de nombres, sin etiquetas ni
  porcentajes.
- [x] Cubrir la expansión, el contrato y las invariantes de interfaz con
  pruebas.
- [x] Verificar en una sesión real de Omarchy con perfiles guardados.

**Cierre:** al seleccionar un preset, el panel muestra su disposición a escala
y un perfil `fallback` se presenta como aproximado.

## Secuencia posterior

1. Crear el tag `v0.2.0` y la GitHub Release siguiendo `docs/releasing.md`.
2. Pedir al marketplace validación y línea base de seguridad para el nuevo
   commit exacto de `main`.

## Cierre de cada sesión

1. Ejecutar las pruebas afectadas y `python -m unittest discover -v`.
2. Actualizar la tabla de estado y la siguiente sesión si el hito avanzó.
3. Actualizar `spec.md` sólo si cambió un requisito; actualizar
   `architecture.md` sólo si cambió una decisión o límite de componentes.
4. No instalar, habilitar ni copiar el plugin a la configuración de Omarchy
   durante el desarrollo sin autorización explícita.
