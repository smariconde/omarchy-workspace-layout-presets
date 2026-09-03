# Guía para agentes

## Propósito y fuentes de verdad

Este repositorio implementa un widget de Omarchy para guardar y restaurar la
disposición de **un solo workspace**. No es un gestor de sesiones.

Leer en este orden antes de cambiar comportamiento:

1. `README.md` para el estado y los comandos de desarrollo.
2. `spec.md` para alcance, requisitos y límites de seguridad.
3. `docs/architecture.md` para propiedad de componentes y contratos.
4. `docs/development-plan.md` para elegir un bloque pequeño y conocer el
   estado actual.

`spec.md` define qué se construye. `docs/architecture.md` define cómo se
separa. `docs/development-plan.md` sólo gestiona orden y progreso: no duplicar
requisitos en él.

## Límites de seguridad

- Cada perfil representa un workspace. Nunca implementar captura o restore de
  escritorio completo, autostart ni restore automático.
- Restaurar exclusivamente en el workspace activo y vacío. Nunca cerrar,
  mover o reorganizar ventanas que ya existen.
- Los perfiles son datos, no programas. No guardar ni leer líneas de comando
  de `/proc`, PIDs, URLs, pestañas, rutas de documentos, credenciales,
  variables de entorno ni historial.
- No construir shell source a partir de perfiles ni enviarlo a `bar.run()`.
  La frontera QML → backend debe usar ejecutable y argumentos separados; el
  primer trabajo pendiente es comprobar y documentar esa integración.
- Antes de cualquier cambio de escritorio, generar un plan de sólo lectura y
  requerir confirmación explícita. Una restauración parcial debe informar el
  resultado, nunca intentar un rollback destructivo.
- No escribir en `~/.config/omarchy`, instalar, habilitar ni copiar el plugin
  fuera del repositorio sin una petición explícita de la persona usuaria.

## Convenciones técnicas

- El backend usa Python de biblioteca estándar; no introducir dependencias sin
  una decisión explícita y documentada.
- `layoutctl` es la frontera tipada entre QML y backend. Sus entradas y salidas
  deben ser estables, JSON y cubiertas por pruebas.
- `profile_store.py` es el único módulo que decide rutas y escribe perfiles.
  Conservar ids validados, permisos privados y escritura atómica.
- Mantener la lógica de Hyprland fuera de QML. QML presenta datos y controla
  interacción; el backend captura, planifica y restaura.
- Mantener los algoritmos puros separados de I/O cuando sea posible, sobre
  todo la inferencia Dwindle y geometría floating.

## Flujo de trabajo

1. Tomar una sola sesión o subtarea de la hoja de ruta.
2. Revisar los requisitos y fixtures relacionados antes de editar.
3. Añadir o ajustar pruebas junto con el cambio. Para I/O de Hyprland, preferir
   fixtures anonimizadas y adaptadores simulables.
4. Ejecutar `python -m unittest discover -v` antes de entregar.
5. Para cambios QML o de manifiesto, ejecutar también `qmllint` y
   `omarchy plugin validate .` cuando estén disponibles en un entorno Omarchy.
6. Actualizar `docs/development-plan.md` al completar un hito o cambiar la
   siguiente sesión. Actualizar la especificación o arquitectura sólo cuando
   cambie su responsabilidad respectiva.

## Calidad y alcance

- No rellenar módulos reservados con llamadas no verificadas a Hyprland o
  Quickshell. Primero crear el contrato, fixture o spike que las valide.
- Cada bloqueo debe ser explícito y seguro: un perfil inválido, launcher no
  resoluble, layout no soportado o workspace ocupado impide restaurar.
- Mantener las modificaciones pequeñas y cohesionadas; no mezclar refactors
  irrelevantes con una función.
- Preservar cambios existentes de otras personas y no usar operaciones Git
  destructivas.
