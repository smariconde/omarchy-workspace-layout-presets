# Security Policy

## Supported versions

Security fixes are provided for the latest published release. Users should
update with:

```sh
omarchy plugin update io.github.smariconde.workspace-layout-presets
```

## Reporting a vulnerability

Please do not disclose a vulnerability in a public issue. Use GitHub's
[private vulnerability reporting form](https://github.com/smariconde/omarchy-workspace-layout-presets/security/advisories/new).

Include the affected version, Omarchy and Hyprland versions, reproduction
steps, potential impact, and any suggested mitigation. Do not include real
credentials, private profile contents, browser data, or unrelated system logs.

You should receive an acknowledgement within seven days. A fix and disclosure
timeline will be coordinated according to severity and reproducibility.

## Security boundary

This plugin runs with the permissions of the current user, as all third-party
Omarchy plugins do. It does not require `sudo`, install hooks, network access,
or background services. Restore launches only locally installed `.desktop`
entries and refuses unsafe or unverified inputs.

