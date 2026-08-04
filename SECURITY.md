# Security

## Report a vulnerability

Please do not post credentials, personal data, or exploit details in a public issue. Use GitHub's private vulnerability reporting feature for this repository when available. Otherwise, open a minimal issue asking the maintainer for a private contact channel, without including sensitive details.

## Deployment boundary

Scholar Workspace is designed to run on a trusted personal computer. The default service listens on `127.0.0.1`. LAN mode must use an access code and is read-only by default. Do not expose the service directly to the public internet.

Secrets, device paths, logs, backups, and personal life data belong in `local/`, which is ignored by Git. Large attachments belong in `attachments/`, which is also ignored. Before publishing a fork, review the complete Git history as well as the current files.
