# Contributing

Thanks for helping improve Scholar Workspace.

## Before opening a change

1. Check existing issues and pull requests to avoid duplicate work.
2. Keep changes focused and preserve the local-first, dependency-light design.
3. Never commit personal records, credentials, API keys, machine paths, or files from `local/` and `attachments/`.

## Run the checks

```bash
bash tests/跑全部.sh
```

The Python suites require only Python 3.9+. Browser tests run automatically when Playwright and Chromium are available:

```bash
npm i -D playwright
npx playwright install chromium
bash tests/跑全部.sh
```

## Pull requests

Describe what changed, why it changed, and how it was tested. Add or update tests when behavior changes. Screenshots are useful for visible interface changes.

By contributing, you agree that your contribution may be distributed under the repository's [MIT License](LICENSE).
