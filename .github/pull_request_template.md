## Summary

Describe the user-visible change and why it is needed.

## Safety and compatibility

- [ ] The change still operates on one active workspace only.
- [ ] Restore still requires an empty workspace and explicit confirmation.
- [ ] No profile or QML value becomes shell source.
- [ ] No sensitive or session data is persisted.
- [ ] Public contract or profile-schema changes are documented, if applicable.

## Verification

- [ ] Tests added or updated where needed.
- [ ] `python -m unittest discover -v` passes.
- [ ] `omarchy plugin validate .` passes for QML or manifest changes.
- [ ] `qmllint` passes when available, or its absence is noted.
- [ ] `CHANGELOG.md` was updated for a user-visible change.
