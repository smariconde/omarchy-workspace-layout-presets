# Omarchy Workspace Layout Presets

An Omarchy bar widget for saving a named arrangement of one workspace and
safely restoring it only into an empty active workspace.

## Status

Foundation only. The repository contains a valid `bar-widget` manifest, an
inert QML entry point, a dependency-free `profile list` backend command, and
standard-library tests. Capture and restore are intentionally not implemented.

## Safety model

- One explicitly active workspace per profile; never a whole-desktop session.
- No autostart, no automatic restore, and no edit of Omarchy configuration.
- No shell command strings, `/proc` command lines, documents, browser tabs, or
  credentials in profiles.
- Restore will be designed to block on a non-empty target workspace.

## Development

Run the current test suite with:

```sh
python -m unittest discover -v
```

The planned validation command is:

```sh
omarchy plugin validate .
```

This repository does not install, enable, or copy the plugin into an Omarchy
configuration directory.

## Documentación

- [Especificación](spec.md): alcance, requisitos y límites de seguridad.
- [Arquitectura](docs/architecture.md): componentes y contratos.
- [Hoja de ruta](docs/development-plan.md): estado, hitos y próxima sesión.
- [Guía para agentes](AGENTS.md): reglas de contribución y trabajo seguro.
