# Contributing

Bug reports, documentation improvements, tests, and focused pull requests are
welcome.

## Before proposing a change

Open an issue before implementing a large feature or a change to the profile or
CLI contracts. Small fixes can go directly to a pull request.

Read these documents in order:

1. `README.md`
2. `spec.md`
3. `docs/architecture.md`
4. `docs/development-plan.md`

## Scope and safety

Every contribution must preserve these rules:

- One preset represents one workspace, never a whole desktop session.
- Restore operates only in the active, empty workspace.
- Existing windows are never closed, moved, or reorganized.
- No autostart or automatic restore.
- Profiles never contain shell commands, PIDs, URLs, browser tabs, document
  paths, credentials, environment variables, or history.
- QML passes a fixed executable and separate arguments; profile data never
  becomes shell source.
- A blocked or partial restore must be reported without destructive rollback.
- The backend remains Python standard-library-only unless a dependency is
  discussed and accepted first.

Changes outside these boundaries require an explicit design decision before
implementation.

## Development workflow

Create a branch, keep the change focused, and add or update tests alongside the
implementation. Then run:

```sh
python -m unittest discover -v
omarchy plugin validate .
```

For QML or manifest changes, also run this when `qmllint` is available:

```sh
qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml qml/*.qml
```

Live desktop behavior should be tested in a disposable workspace. Do not use
real browser sessions, private documents, or credentials as fixtures or review
evidence.

## Pull requests

A pull request should:

- explain the user-visible behavior and motivation;
- identify any safety or compatibility impact;
- include tests or explain why none are needed;
- update `CHANGELOG.md` under **Unreleased** for user-visible changes;
- update the relevant specification or architecture document only when its
  contract actually changes;
- avoid unrelated refactors.

Do not bump the release version in ordinary pull requests. The maintainer does
that once when cutting a release.

## Reporting security issues

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).

