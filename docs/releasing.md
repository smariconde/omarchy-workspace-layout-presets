# Release process

The plugin follows Semantic Versioning and uses `manifest.json` as the single
runtime source of truth for its version.

## When to change the version

- **Patch** (`0.1.0` → `0.1.1`): compatible bug fixes, safety hardening, or
  small UI corrections.
- **Minor** (`0.1.0` → `0.2.0`): compatible user-visible features or broader
  platform support.
- **Major** (`1.0.0` → `2.0.0`): incompatible changes to installed behavior,
  configuration, the public CLI contract, or profile compatibility.

Before `1.0.0`, a breaking beta change increments the minor number. Profile
schema changes are separate from plugin versions and require an explicit,
non-destructive migration design.

Commits and pull requests do not each get a new version. Add user-visible work
to the `Unreleased` section of `CHANGELOG.md`, then choose one version for the
group of changes when publishing a release.

## Cutting a release

1. Confirm the worktree contains only the intended release changes.
2. Complete the manual compatibility matrix in `spec.md` against the supported
   Omarchy and Hyprland versions.
3. Run:

   ```sh
   python -m unittest discover -v
   omarchy plugin validate .
   qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml qml/*.qml
   ```

   If `qmllint` is unavailable, record that fact in the release notes and do
   not claim it passed.

4. Set the new SemVer value in `manifest.json`.
5. Move the relevant entries from `Unreleased` to a dated version in
   `CHANGELOG.md` and update its comparison links.
6. Run the tests again. They verify release metadata and the permanent plugin
   ID as well as application behavior.
7. Commit the release and create a matching annotated tag:

   ```sh
   git tag -a v0.1.0 -m "Workspace Layout Presets 0.1.0"
   git push origin main
   git push origin v0.1.0
   ```

8. Create a GitHub Release from the tag using the matching changelog entry.
9. For the first release, submit the repository to the Omarchy Plugin
   Marketplace. For later versions, use the marketplace verification form to
   publish the exact newer commit.

The tag, GitHub Release, `manifest.json`, and changelog heading must all use the
same version.
