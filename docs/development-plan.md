# Hoja de ruta de desarrollo

**Estado:** M0 completado · próxima sesión: M1
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
| Almacenamiento de perfiles | Parcial | ids seguros, JSON validado superficialmente y escritura atómica |
| CLI | Parcial | `layoutctl profile list` |
| Captura, inferencia y lanzadores | Pendiente | módulos reservados |
| Planificación y restauración | Pendiente | módulo reservado |
| Interfaz | Pendiente | componentes reservados |
| Validación en Omarchy | Pendiente | aún no ejecutada |

La suite actual se ejecuta con `python -m unittest discover -v`.

## Hitos

| Hito | Entregable | Depende de | Criterio de salida | Estado |
| --- | --- | --- | --- | --- |
| M0 | Contrato CLI y puente QML → backend | — | El comando puede llamarse con argumentos separados y devuelve resultados JSON que la UI puede consumir | Hecho |
| M1 | Perfiles completos | M0 | Validación profunda y operaciones show/rename/duplicate/delete/export/import cubiertas por tests | Pendiente |
| M2 | Captura segura | M1 | Fixtures de Hyprland → perfil válido, sin datos sensibles ni comandos de shell | Pendiente |
| M3 | Inferencia Dwindle | M2 | Árbol exacto para geometrías soportadas; `fallback` explícito para las demás | Pendiente |
| M4 | Plan de restauración | M1–M3 | `plan` es de sólo lectura y bloquea invariablemente workspaces no vacíos | Pendiente |
| M5 | Restauración controlada | M4 | Ejecuta sólo un plan aprobado, verifica el resultado y nunca cierra ventanas | Pendiente |
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

## Secuencia posterior

1. M1: terminar el modelo y la gestión de perfiles.
2. M2: capturar workspace, monitor, clientes y lanzadores desde fixtures.
3. M3: inferir Dwindle y conectar su fallback a captura.
4. M4: producir y aprobar planes de sólo lectura.
5. M5: restaurar tiled, floating y fullscreen permitido, con verificación.
6. M6: construir la UI sólo sobre las operaciones ya probadas.
7. M7: endurecer, probar en máquinas reales y publicar la beta.

## Cierre de cada sesión

1. Ejecutar las pruebas afectadas y `python -m unittest discover -v`.
2. Actualizar la tabla de estado y la siguiente sesión si el hito avanzó.
3. Actualizar `spec.md` sólo si cambió un requisito; actualizar
   `architecture.md` sólo si cambió una decisión o límite de componentes.
4. No instalar, habilitar ni copiar el plugin a la configuración de Omarchy
   durante el desarrollo sin autorización explícita.
