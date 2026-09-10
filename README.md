# Omarchy Workspace Layout Presets

An Omarchy bar widget for saving a named arrangement of one workspace and
safely restoring it only into an empty active workspace.

## Status

Milestone 6 implemented. The repository contains a functional `bar-widget`
menu, a verified Quickshell-to-backend argv
bridge, validated atomic profile management, fixture-driven safe capture, pure
Dwindle tree inference for supported slicing geometries, and guarded restore
replay. Capture uses JSON-only Hyprland queries and desktop-entry IDs; it does
not persist process command lines or execute launchers. Browser-hosted Omarchy
webapps are reviewed only when their shared browser class is ambiguous; the
saved profile contains the selected desktop-entry ID, never its URL. `plan` previews a
restore and refuses a non-empty workspace; `restore` revalidates and consumes
a single-use token after the QML client records fresh, short-lived evidence
for the exact Lua bridge as part of the confirmed restore flow.

## Safety model

- One explicitly active workspace per profile; never a whole-desktop session.
- No autostart, no automatic restore, and no edit of Omarchy configuration.
- No shell command strings, `/proc` command lines, documents, browser tabs, or
  credentials in profiles.
- Planning blocks on a non-empty target workspace, and an approved plan is a
  single-use token that carries verified conditions, never instructions.

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
