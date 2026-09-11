# Omarchy Plugin Marketplace submission

Use this draft only after the release has been committed, tagged, pushed, and
published as a GitHub Release. The repository owner must personally confirm
every checklist statement before opening the issue.

## Re-verifying a new commit

The initial listing review raised a blocker on commit `c59ce43`: the
installable root contained `AGENTS.md` and `CLAUDE.md`, which are agent-control
instruction channels inside the installed plugin scope. Both were untracked in
`v0.2.0`; their documentation now lives in `docs/repository-guide.md` and
`CONTRIBUTING.md`, and `tools/check_release_payload.py` fails the suite and CI
if any assistant instruction file reappears anywhere in the tracked tree.

After pushing a new release, use the marketplace verification form to request
validation and the security baseline for the exact new default-branch HEAD.
State the commit SHA explicitly; the review pins one commit, not a branch name.

## Listing metadata

- **Category:** `Productivity`
- **Tags:** `hyprland`, `quickshell`, `workspaces`
- **Suggested missing tag:** none

## Issue title

```text
[Plugin]: Workspace Layout Presets
```

## Issue body

```markdown
### Repository URL

https://github.com/smariconde/omarchy-workspace-layout-presets

### Category

Productivity

### Tags

hyprland, quickshell, workspaces

### Suggest a missing tag

_No response_

### Maintainer notes

A deliberately small and safety-focused workspace preset widget. It saves one
active Dwindle workspace and restores it only into an empty active workspace.
It has no autostart, automatic restore, shell command profiles, network access,
install hooks, privileges, or third-party runtime dependencies.

Tested live on Omarchy 4.0.2 with Quickshell 0.3.1 and Hyprland 0.56.2. The
repository includes 145 automated tests, a documented security boundary, and
a read-only preview plus fresh compatibility checks before every restore. The
installable tree carries no coding-assistant instruction files, and a
recursive guard in the test suite and CI keeps it that way.

### Submission checklist

- [ ] The repository is public and contains installation and removal instructions.
- [ ] I have documented the plugin license and any external dependencies.
- [ ] I confirm that I own or have permission to submit this plugin and its preview assets.
- [ ] The plugin does not overwrite user configuration without explicit consent.
- [ ] I understand that approval is for listing and is not a security review.
```

After confirming the statements, change each box to `[x]` and open the official
submission form:

<https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml>
