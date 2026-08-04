# Scholar Workspace

[中文](README.md) · [Installation guide (Chinese)](docs/安装与使用.md) · [Contributing](CONTRIBUTING.md)

[![Tests](https://github.com/SuperJayLiu/scholar-workspace/actions/workflows/tests.yml/badge.svg)](https://github.com/SuperJayLiu/scholar-workspace/actions/workflows/tests.yml)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A local-first, dependency-free workspace for academic work. Manage manuscripts, journals, conferences, literature, ideas, and schedules in a browser while keeping your data as readable Markdown files on your own disk.

- No cloud account, subscription, database, or build step
- Python standard-library backend and plain JavaScript frontend
- Literature indexing from Zotero, EndNote, Mendeley, `.bib`, `.ris`, CSL-JSON, and `.nbib`
- Bidirectional links across manuscripts, ideas, papers, conferences, and schedules
- Optional AI tasks, literature radar, and private Git-based device sync

> The interface is currently Simplified Chinese. This source repository contains only generic sample data—no maintainer records, accounts, paths, credentials, or usage history.

## Start in one minute

Requires **Python 3.9+**. There is nothing to install with `pip`.

```bash
git clone https://github.com/SuperJayLiu/scholar-workspace.git
cd scholar-workspace
python3 server.py
```

Your browser opens <http://127.0.0.1:8765/>. A first-run wizard explains every optional setting.

You can also double-click the platform launcher:

- macOS: `安装-Mac.command` to install and enable auto-start, or `启动.command` to run once
- Windows: `安装-Windows.bat` or `启动.bat`

## What it covers

| Area | What it does |
|---|---|
| Manuscript pipeline | Track started → submitted → R&R → accepted and calculate actual review times |
| Literature index | Import common reference exports and link to DOI, PDF, or your reference manager |
| Research graph | Link ideas, manuscripts, papers, conferences, and scheduled work in both directions |
| Reading review | Structured notes with a 1 / 7 / 30 / 90-day review queue |
| Automation | Optional consistency audits, weekly reports, method scans, and literature radar |
| Multiple devices | Sync academic data through your own private Git repository while local secrets stay local |

## Data and privacy

| Path | Contents | Tracked by Git? |
|---|---|---|
| `data/` | Academic records, configuration, and generic examples | Yes |
| `local/` | Credentials, personal logs, backups, device paths, and logs | **No** |
| `attachments/` | Large attachments | **No** |
| `app/` | Build-free frontend | Yes |

`local/` and `attachments/` are ignored by Git. Diagnostic exports contain only version, platform, record counts, and redacted status—not record contents.

For personal multi-device sync, create a **private repository** for your own data. Never push personal records back to this public source repository.

## Tests and development

Run the core checks:

```bash
bash tests/跑全部.sh
```

The 13 Python suites have no dependencies. Five browser suites require Playwright and are skipped when it is unavailable:

```bash
npm i -D playwright
npx playwright install chromium
bash tests/跑全部.sh
```

Tests run against a temporary copy and do not modify your workspace data. GitHub Actions runs the core suite for every push and pull request.

## Documentation

- [Full installation and usage guide (Chinese)](docs/安装与使用.md)
- [Detailed tutorial (Chinese)](使用教程.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Test guide](tests/README.md)

## Known limitations

- The UI is currently Simplified Chinese only.
- Chromium on macOS and Linux has the strongest test coverage; Windows and Safari need more real-world verification.
- LAN access requires an access code and is read-only by default. Do not expose the local server directly to the public internet.

## License

[MIT](LICENSE) © 2026 Scholar Workspace contributors
