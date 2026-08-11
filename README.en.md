# Scholar Workspace

[中文](README.md) · [Installation](docs/installation.en.md) · [Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md)

[![Tests](https://github.com/SuperJayLiu/workspace-for-all/actions/workflows/tests.yml/badge.svg)](https://github.com/SuperJayLiu/workspace-for-all/actions/workflows/tests.yml)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A local-first workspace for academic work with no runtime dependencies. Manage manuscripts, journals, conferences, literature, ideas, and schedules in a browser while keeping your data as readable Markdown files on your own disk.

- No cloud account, subscription, or database
- Python standard-library backend and plain JavaScript frontend
- Simplified Chinese interface with a persistent English beta switch
- Zotero, EndNote, Mendeley, BibTeX, RIS, NBIB, and CSL-JSON indexing
- Optional AI tasks, research radar, and private Git-based device sync

> The public repository and release packages contain generic samples only—no maintainer records, accounts, device details, paths, credentials, or usage history.

## Product preview

![Scholar Workspace daily overview with generic sample data](docs/assets/overview.png)

| Research pipeline | Mobile reading review |
|---|---|
| ![Research projects, progress, and stage board](docs/assets/research.png) | ![Mobile reading and review interface](docs/assets/mobile-reading.png) |

These screenshots were captured in a disposable demo environment using only the repository's generic samples and a `Demo device` label.

## Start in one minute

Requires **Python 3.9 or newer**. There is nothing to install with `pip`.

```bash
git clone https://github.com/SuperJayLiu/workspace-for-all.git
cd workspace-for-all
python3 server.py
```

Your browser opens <http://127.0.0.1:8765/>. A first-run wizard explains every optional setting.

You can instead download the [latest release](https://github.com/SuperJayLiu/workspace-for-all/releases/latest), extract it, and double-click:

- macOS: `安装-Mac.command` to install and enable login startup, or `启动.command` to run once
- Windows: `安装-Windows.bat` or `启动.bat`

Each release includes `SHA256SUMS.txt` and a GitHub build-provenance attestation. See the [installation guide](docs/installation.en.md#verify-the-download-optional-but-recommended).

## What it covers

| Area | What it does |
|---|---|
| Manuscript pipeline | Track started → submitted → R&R → accepted and calculate actual review times |
| Literature index | Import common reference exports and link to DOI, PDF, or your reference manager |
| Research graph | Link ideas, manuscripts, papers, conferences, and scheduled work in both directions |
| Reading review | Structured notes with a 1 / 7 / 30 / 90-day review queue |
| Automation | Optional consistency audits, weekly reports, method scans, and literature radar |
| Multiple devices | Sync through your own private Git repository while local secrets stay local |

## Data and privacy

| Path | Contents | Tracked by Git? |
|---|---|---|
| `data/` | Academic records, configuration, and generic examples | Yes |
| `local/` | Credentials, personal logs, backups, device paths, and logs | **No** |
| `attachments/` | Large attachments | **No** |
| `app/` | Build-free frontend | Yes |

`local/` and `attachments/` are ignored by Git. The public packager also builds from Git's file manifest, resets runtime state, and scans for secrets, machine paths, and device state.

For personal multi-device sync, create a **private repository** for your data. Never push personal records back to this public source repository.

## Tests and development

```bash
# 14 core Python suites; live data is never touched
bash tests/跑全部.sh --python-only

# 6 browser suites
npm ci
npx playwright install chromium
bash tests/跑全部.sh --ui-only

# Local default: core, plus UI when a browser is installed
bash tests/跑全部.sh
```

The independent cross-platform startup smoke test is:

```bash
python3 tests/platform_smoke.py
```

Every write-capable check uses a disposable copy. GitHub Actions covers Python 3.9/3.13, Linux/macOS/Windows startup, and Chromium, Firefox, and WebKit UI tests.

## Documentation and community

- [Installation and usage](docs/installation.en.md)
- [Detailed tutorial (Chinese)](使用教程.md)
- [Contributing](CONTRIBUTING.md)
- [Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md)
- [Security](SECURITY.md) · [Code of Conduct](CODE_OF_CONDUCT.md)
- [Test guide](tests/README.md)

## Known limitations

- The English interface is beta; some less-common explanatory text remains untranslated.
- Automated WebKit coverage is a useful Safari compatibility signal, not a substitute for real Safari and device testing.
- LAN access requires an access code and is read-only by default. Do not expose the local server directly to the public internet.

## License

[MIT](LICENSE) © 2026 Scholar Workspace contributors
