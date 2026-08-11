# Contributing

Thanks for helping make Scholar Workspace useful to more researchers.

## Before you begin

1. Search existing issues and pull requests.
2. For a substantial feature, open a feature request before investing in an implementation.
3. Keep changes focused and preserve the local-first, readable-file, dependency-light design.
4. Read the [Code of Conduct](CODE_OF_CONDUCT.md) and [Security Policy](SECURITY.md).

## Local setup

The application requires Python 3.9+ and no Python packages:

```bash
python3 server.py
bash tests/跑全部.sh --python-only
```

For UI work:

```bash
npm ci
npx playwright install chromium
bash tests/跑全部.sh --ui-only
```

Tests that write data run against disposable copies. Do not bypass those safeguards by pointing a test at your normal server.

## Project map

- `server.py` and the top-level Python modules: standard-library backend
- `app/`: build-free HTML, CSS, and JavaScript interface
- `data/`: generic examples and user-owned Markdown records
- `local/`: credentials, device paths, logs, backups, and private state; never commit it
- `scripts/`: maintenance and packaging tools
- `tests/`: core, startup, and Playwright regression suites

## Pull-request checklist

- Explain the problem, the chosen approach, and user-visible effects.
- Add or update tests when behavior changes.
- Run the relevant Python and UI suites.
- Update both READMEs and installation docs when commands, requirements, or visible behavior change.
- Include sanitized screenshots for visible UI changes.
- Keep Chinese and English interface strings aligned; describe intentionally untranslated beta areas.
- Avoid unrelated formatting or generated-file changes.

## Privacy checklist

Before committing, inspect both the diff and untracked files:

```bash
git status --short
git diff --check
python3 scripts/打包.py --public --check
```

Never commit personal records, names, email addresses, credentials, API keys, access codes, machine hostnames, IP addresses, absolute paths, runtime reports, logs, files from `local/` or `attachments/`, or device heartbeats from `data/presence/`.

The packaging check intentionally uses Git's tracked-file manifest. Stage intended new files before its final release check; do not use `--include-untracked` for a release.

## Style

- Prefer the Python standard library and plain browser APIs.
- Keep files readable without a build step.
- Preserve user-authored Markdown and backwards compatibility whenever possible.
- Use clear comments for security boundaries, data migration, or non-obvious compatibility code.

By contributing, you agree that your contribution may be distributed under the repository's [MIT License](LICENSE).
