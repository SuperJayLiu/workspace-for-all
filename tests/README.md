# Test suites

Scholar Workspace has three independent test layers. All write-capable tests use disposable copies and must never point at a normal running workspace.

## Core Python — 14 suites

```bash
bash tests/跑全部.sh --python-only
```

The runner copies the repository to a temporary directory, runs every numbered `tests/*.py` file, reports pass/fail from each process exit code, and deletes the copy. It excludes `platform_smoke.py`, which is a separate layer.

Coverage includes backend records and configuration, HTTP and PDF boundaries, recovery, remote access, Overleaf progress, linked records, calendars, literature indexing, concurrency, search, malformed input, and research radar behavior.

## Cross-platform startup smoke

```bash
python3 tests/platform_smoke.py
```

The smoke test creates its own temporary workspace, starts the copied server on a free loopback port, checks `/api/ping`, `/api/bootstrap`, and the main page, terminates it, and removes the copy. GitHub Actions runs this test on Linux, macOS, and Windows.

## Browser UI — 6 suites

Install test-only dependencies:

```bash
npm ci
npx playwright install chromium
bash tests/跑全部.sh --ui-only
```

Set `PW_BROWSER=firefox` or `PW_BROWSER=webkit` after installing that engine to run the same suites there. CI runs Chromium, Firefox, and WebKit.

The runner starts a server only from a second temporary copy. It never connects to a server on the default port. Browser coverage includes core UI safety and scale, mobile/read-only behavior, AI and quick links, layout changes, linked-record navigation, and the English beta switch.

## Local default

```bash
bash tests/跑全部.sh
```

This runs the 14 core suites and then the browser suites when the selected Playwright browser is installed. A missing browser is a documented skip in default mode and an error in `--ui-only` mode.

## Adding a test

- A numbered Python test must exit nonzero on failure; its final printed sentence is not used as a status signal.
- A browser test must set `process.exitCode` or exit nonzero on failure and select the `PW_BROWSER` engine.
- Never write to the source checkout or assume a fixed port.
- Use generic sample content—no names, email addresses, device details, absolute paths, credentials, or private research text.
