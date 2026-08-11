# Security Policy

## Supported versions

Security fixes are applied to the latest released version. Users should upgrade to the newest GitHub Release before reporting a problem that may already be fixed.

## Report a vulnerability privately

Do not publish credentials, personal data, access codes, or exploit details in an issue.

Use [GitHub private vulnerability reporting](https://github.com/SuperJayLiu/workspace-for-all/security/advisories/new). If that form is unavailable, open a minimal issue requesting a private contact channel without including sensitive details.

Please include the affected version, operating system, reproduction steps, impact, and any suggested mitigation. You should receive an initial acknowledgement within seven days. No bounty program is currently offered.

## Deployment boundary

Scholar Workspace is designed for a trusted personal computer. The default service listens on `127.0.0.1`. LAN mode requires an access code and is read-only until explicitly unlocked. Do not expose the service directly to the public internet.

Secrets, device paths, logs, backups, and personal life data belong in `local/`, which Git ignores. Large attachments belong in `attachments/`. Before publishing a fork, inspect the complete Git history as well as current and untracked files.
