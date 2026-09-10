# Plan de mejora UI/UX

**Estado:** Pendiente  
**Alcance:** Refinamiento visual, responsive y de accesibilidad del panel del plugin  
**Objetivo:** Corregir densidad irregular, espacios vacíos, jerarquía tipográfica,
colisiones de texto y feedback inconsistente sin rediseñar el producto ni
modificar su flujo funcional.

## Contexto

La interfaz actual ya usa los componentes y tokens visuales de Omarchy. No
necesita una identidad nueva ni más decoración. Los problemas observados se
originan principalmente en alturas rígidas, padding interno demasiado pequeño,
agrupación visual débil y estados de interfaz que no se comunican de forma
consistente.

El popup de Omarchy ya aporta `Style.spacing.popupPadding`; no se debe añadir un
segundo padding exterior. Los ajustes de margen deben realizarse dentro de las
secciones y superficies del plugin.

## Alcance de archivos

Archivos que deberían cambiar:

- `Panel.qml`: composición, espaciado, tamaños adaptativos, jerarquía,
  acciones, feedback y navegación por teclado.
- `qml/RestorePreview.qml`: altura adaptativa, jerarquía interna y tratamiento
  de advertencias.
- `tests/test_ui_english.py`: pruebas estructurales para conservar las
  decisiones importantes de UI.

Archivos que no deberían cambiar para este trabajo:

- `BarWidget.qml`
- `qml/LayoutctlClient.qml`
- `qml/BridgeProbe.qml`
- backend y contratos JSON
- `manifest.json`
- especificación o arquitectura, salvo que durante la implementación se
  descubra un cambio real de responsabilidad o requisito

`qml/ConfirmDialog.qml` y `qml/ProfileList.qml` son componentes reservados y no
participan en la UI actual. No deben incorporarse sólo para justificar su
existencia.

## Problemas confirmados

### 1. Alturas rígidas y espacio desaprovechado

- La lista de presets siempre mide `Style.space(116)`, aunque sólo tenga uno o
  dos elementos.
- El detalle reserva aproximadamente `Style.space(18)` por aplicación, más de
  lo que ocupa cada línea en la configuración actual.
- La revisión de captura calcula su altura mediante una fórmula fija.
- El preview de restauración siempre reserva `Style.space(116)`, incluso si no
  hay una advertencia que mostrar.

Estas decisiones generan huecos visibles y hacen que el panel llegue al límite
de scroll antes de que sea necesario.

### 2. Padding interno insuficiente

- La lista usa `Style.spacing.xs` como margen interior.
- La tarjeta de detalle usa `Style.spacing.sm`.
- Las filas seleccionadas y el contenido textual quedan visualmente pegados a
  sus bordes.

### 3. Jerarquía y agrupación poco claras

- La columna principal usa el mismo `panelGap` entre todos sus hijos.
- No se diferencia el espacio entre elementos relacionados del espacio entre
  secciones.
- El detalle del preset aparece después de `Restore…` y `Delete`, aunque esa
  información debería ayudar a decidir antes de actuar.
- El resumen `nombre · cantidad`, la etiqueta `Apps in this preset` y la lista
  repiten contexto.

### 4. Tipografía secundaria demasiado pequeña

- Los nombres de las aplicaciones usan `Style.font.caption` aunque sean
  contenido principal.
- El resumen y la etiqueta de la tarjeta tienen prácticamente la misma
  jerarquía.
- Varias opacidades arbitrarias (`0.55`, `0.58`, `0.66`, `0.72`) pueden perder
  contraste en ciertos temas.

### 5. Acciones visualmente desbalanceadas

- `Save` reserva `Style.space(142)`, demasiado ancho para su etiqueta.
- `Restore…` y `Delete` tienen la misma presencia y anchura.
- La confirmación destructiva no ofrece un control `Cancel` explícito.
- Las acciones no se deshabilitan de forma uniforme mientras el cliente está
  ocupado.

### 6. Feedback inconsistente

- Los mensajes de éxito de Save/Delete son reemplazados inmediatamente por
  `Loading presets…` y luego desaparecen.
- `Preparing preview…` puede seguir visible cuando el preview ya se cargó.
- El estado vacío puede comunicarse simultáneamente dentro de la lista y en el
  pie.
- El color de error se decide buscando palabras dentro del texto en vez de
  representar explícitamente el tipo de estado.

### 7. Texto largo y accesibilidad

- Los IDs de perfil pueden tener hasta 64 caracteres, pero el botón de la lista
  no elide su texto.
- Algunos textos que contienen datos de perfiles no fuerzan
  `Text.PlainText`.
- `KeyboardPanel` no define `focusTarget`.
- Los `Ui.Button` del panel no se declaran `focusable`, por lo que el recorrido
  completo mediante teclado no está garantizado.

## Plan de implementación

### Paso 1 — Reorganizar la composición principal

En `Panel.qml`:

1. Reducir el ancho objetivo de `Style.space(410)` a `Style.space(380)`, en
   línea con los paneles nativos comparables de Omarchy.
2. Mantener el padding exterior que ya aporta `Ui.KeyboardPanel`.
3. Agrupar el contenido en columnas semánticas:
   - encabezado;
   - guardar preset;
   - presets guardados;
   - feedback final.
4. Usar aproximadamente `Style.spacing.lg` o `Style.spacing.xl` dentro de una
   sección y `Style.spacing.huge` entre secciones.
5. Mover el detalle seleccionado entre la lista y la fila de acciones.

No agregar separadores entre todos los bloques. El espaciado y los encabezados
deben ser suficientes para expresar la estructura sin producir ruido visual.

### Paso 2 — Hacer adaptativas las listas y superficies

1. Calcular la altura de la lista de presets a partir de:
   - padding superior e inferior;
   - altura real de las filas;
   - separación entre filas.
2. Mantener una altura mínima clara para el estado vacío.
3. Permitir que la lista crezca hasta cuatro o cinco filas y activar scroll a
   partir de allí.
4. Calcular el detalle según las filas realmente visibles y conservar un tope
   para presets con muchas aplicaciones.
5. Usar `implicitHeight` del contenido para la revisión de captura, la
   confirmación de borrado y el preview.
6. No reservar altura para bloques invisibles ni para advertencias vacías.

El caso habitual de uno o dos presets debe producir un panel notablemente más
compacto sin perjudicar listas largas.

### Paso 3 — Corregir padding y ritmo visual

1. Aumentar el padding interior de la lista desde `xs` a `md` o `lg`.
2. Usar entre `Style.spacing.lg` y `Style.spacing.xl` en las tarjetas de
   detalle, preview y confirmación.
3. Mantener `Style.spacing.controlHeight` para inputs y botones; coincide con
   el sistema visual de Omarchy.
4. Usar un único gap consistente entre botones relacionados.

### Paso 4 — Afinar la jerarquía tipográfica

Aplicar esta escala:

- título principal: `Style.font.heading`;
- contenido y acciones: `Style.font.body`;
- subtítulo, nombres de aplicaciones y estados: `Style.font.bodySmall`;
- conteos, metadatos y encabezados de sección: `Style.font.caption`.

Además:

1. Conservar `Ui.PanelSectionHeader`, usando textos `SAVE` y `SAVED PRESETS`
   para seguir su patrón nativo de small caps.
2. Mantener el título principal en peso medio.
3. Mostrar los nombres de aplicaciones con `bodySmall`, no `caption`.
4. Definir colores secundarios compartidos derivados del foreground en lugar
   de aplicar opacidades distintas a cada texto.
5. Revisar contraste tanto en temas oscuros como claros.

### Paso 5 — Simplificar el detalle seleccionado

1. Crear una cabecera de una sola fila:
   - nombre visible del preset a la izquierda;
   - cantidad de aplicaciones a la derecha, en estilo secundario.
2. Mostrar inmediatamente debajo la lista de aplicaciones.
3. Eliminar `Apps in this preset`, porque la tarjeta ya comunica ese contexto.
4. Elidir el nombre cuando sea necesario y conservar el valor completo en un
   tooltip.

### Paso 6 — Equilibrar las acciones

1. Reducir el ancho de `Save` a aproximadamente `Style.space(112)` y dejar que
   el campo de nombre ocupe el resto.
2. Dar a `Restore…` el espacio flexible principal.
3. Usar un ancho contenido para `Delete`, conservando `Color.urgent`.
4. Añadir `Cancel` a la confirmación destructiva.
5. Deshabilitar todas las acciones incompatibles mientras
   `LayoutctlClient.running` sea verdadero.
6. Mantener el aspecto nativo de `Ui.Button`; no crear variantes decorativas
   nuevas.

### Paso 7 — Modelar correctamente el feedback

1. Añadir un estado semántico independiente del mensaje, por ejemplo:
   `neutral`, `progress`, `success` y `error`.
2. Elegir color y presentación desde ese estado, no inspeccionando el texto.
3. Mantener el estado vacío únicamente dentro de la lista.
4. Limpiar `Preparing preview…` al recibir el plan.
5. Preservar el resultado de Save/Delete durante el refresco posterior.
6. Mostrar progreso mientras existe una operación activa.
7. Presentar el pie centrado y con `bodySmall`, de forma discreta pero legible.

No es necesario implementar un sistema de notificaciones nuevo ni animaciones
adicionales.

### Paso 8 — Prevenir colisiones y completar accesibilidad

1. Elidir visualmente los IDs largos en las filas de presets.
2. Añadir tooltip con el identificador completo.
3. Forzar `Text.PlainText` en nombres de preset, aplicaciones, títulos de
   revisión y demás contenido dinámico.
4. Definir un `focusTarget` apropiado para el panel.
5. Marcar como `focusable` todos los botones interactivos.
6. Asegurar recorrido Tab lógico:
   - nombre del preset;
   - Save;
   - presets;
   - Restore;
   - Delete;
   - controles de confirmación o preview.
7. Permitir cerrar con Escape.
8. Confirmar que Enter y Space activan el control enfocado y que el foco
   visible usa los estados nativos de Omarchy.

### Paso 9 — Refinar `RestorePreview.qml`

1. Sustituir la altura fija por `implicitHeight` calculada desde su columna.
2. Mantener tres niveles como máximo:
   - título de confirmación;
   - resumen de aplicaciones y workspace;
   - advertencia accionable, sólo si existe.
3. No crear una fila vacía cuando `warningText()` devuelve una cadena vacía.
4. Permitir hasta dos líneas para la advertencia sin invadir el botón.
5. Conservar el nombre del preset elidido y disponible como texto completo
   mediante tooltip.
6. Aplicar `Text.PlainText` a todos los datos provenientes del plan.

## Pruebas y validación

### Casos visuales manuales

Validar al menos:

- cero presets;
- uno y dos presets;
- cinco o más presets con scroll;
- ID de preset de 64 caracteres;
- nombre visible de preset de 100 caracteres;
- preset con una, cuatro y diez aplicaciones;
- estado seleccionado y no seleccionado;
- guardado directo;
- revisión de una y varias ventanas webapp;
- confirmación y cancelación de borrado;
- preview sin advertencias;
- preview con advertencia de dos líneas;
- preview vencido;
- operación en progreso, éxito, error y bloqueo;
- tema claro, tema oscuro y escalado de interfaz distinto del predeterminado;
- uso completo sólo con teclado.

### Comandos de validación

Ejecutar al finalizar:

```sh
python -m unittest discover -v
qmllint Panel.qml qml/RestorePreview.qml
omarchy plugin validate .
```

Si `qmllint` no está disponible, registrar esa limitación en la entrega y
realizar la comprobación en la matriz manual de M7.

### Pruebas estructurales sugeridas

Actualizar `tests/test_ui_english.py` para verificar al menos:

- que las superficies principales no vuelvan a depender de las alturas fijas
  eliminadas;
- que los botones principales sean enfocables;
- que el panel declare un objetivo de foco;
- que los datos dinámicos relevantes usen texto plano;
- que el estado visual no se determine buscando fragmentos dentro del mensaje;
- que la lista siga teniendo un límite y scroll para colecciones largas.

## Criterios de aceptación

La mejora se considera terminada cuando:

1. Con uno o dos presets no quedan superficies con grandes huecos sin función.
2. Ningún texto toca visualmente los bordes de su superficie.
3. Los nombres máximos no chocan con botones ni salen del panel.
4. La relación entre título, secciones, contenido y metadatos es clara en todos
   los temas probados.
5. El detalle seleccionado aparece antes de sus acciones y no repite etiquetas
   innecesarias.
6. Restore conserva mayor protagonismo que Delete sin ocultar la naturaleza
   destructiva de esta última.
7. Los estados vacío, progreso, éxito y error no se duplican ni se sobrescriben
   accidentalmente.
8. El flujo completo puede recorrerse, confirmarse, cancelarse y cerrarse con
   teclado.
9. El panel sigue usando exclusivamente componentes y tokens del sistema de
   diseño de Omarchy.
10. La suite, la validación del plugin y las verificaciones QML disponibles
    pasan sin cambiar contratos del backend.

## Fuera de alcance

- Cambiar el comportamiento de captura, planificación o restauración.
- Añadir acciones de gestión nuevas.
- Cambiar el icono de la barra.
- Añadir animaciones, ilustraciones o iconos decorativos.
- Modificar configuraciones instaladas de Omarchy o archivos bajo
  `/usr/share/omarchy`.
- Instalar o habilitar el plugin fuera del repositorio.

