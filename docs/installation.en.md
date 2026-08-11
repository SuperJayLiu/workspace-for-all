# Installation and usage

[中文](安装与使用.md)

Scholar Workspace requires Python 3.9 or newer and has no third-party Python runtime dependencies.

## 1. Install Python

Check your version:

```bash
python3 --version
```

- **macOS:** macOS does not guarantee a usable Python 3 installation. Install it from [python.org](https://www.python.org/downloads/macos/) or with Homebrew: `brew install python`.
- **Windows:** install from [python.org](https://www.python.org/downloads/windows/). Select **Add Python to PATH** on the first screen, then run `py -3 --version` in PowerShell.

The reported version must be 3.9 or newer.

## 2. Get Scholar Workspace

### Download a release (recommended)

Open the [latest release](https://github.com/SuperJayLiu/workspace-for-all/releases/latest), download `Scholar-Workspace-vX.Y.Z.zip`, and extract it to a location you intend to keep. Do not run the application from inside the ZIP.

### Use Git

```bash
git clone https://github.com/SuperJayLiu/workspace-for-all.git
cd workspace-for-all
```

## Verify the download (optional but recommended)

Each release includes `SHA256SUMS.txt`.

macOS / Linux:

```bash
shasum -a 256 Scholar-Workspace-vX.Y.Z.zip
cat SHA256SUMS.txt
```

Windows PowerShell:

```powershell
Get-FileHash .\Scholar-Workspace-vX.Y.Z.zip -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

The SHA-256 values must match exactly. With GitHub CLI installed, you can also verify build provenance:

```bash
gh attestation verify Scholar-Workspace-vX.Y.Z.zip --repo SuperJayLiu/workspace-for-all
```

## 3. Start

### Command line

macOS / Linux:

```bash
cd "/path/to/Scholar-Workspace-vX.Y.Z"
python3 server.py
```

Windows PowerShell:

```powershell
cd "C:\path\to\Scholar-Workspace-vX.Y.Z"
py -3 server.py
```

Your browser opens <http://127.0.0.1:8765/>. Closing the terminal stops the service without losing data.

### Double-click launchers

- macOS: `启动.command`
- Windows: `启动.bat`

### Start at login (optional)

- macOS: run `安装-Mac.command`; undo with `卸载自启-Mac.command`
- Windows: run `安装-Windows.bat`; undo with `卸载自启-Windows.bat`

The installers verify Python 3.9+ and install no third-party packages.

## 4. First-run setup

The first launch opens a setup wizard. Every external integration is optional:

- A literature folder can contain Zotero, EndNote, Mendeley, BibTeX, RIS, CSL-JSON, or NBIB exports.
- Git sync should use your own **private repository**.
- AI, calendars, email, Overleaf, and notifications are not required for the core workspace.
- Use the `EN`/`中文` button in the header to switch the English beta interface.

Credentials, access codes, and device paths are stored in `local/`, outside Git. Never push personal data to the public source repository.

## 5. LAN access

Set an access code under Settings → Remote & mobile access before running:

- macOS: `局域网启动.command`
- Windows: `局域网启动.bat`

Remote access is read-only by default. Do not configure router port forwarding or expose the service directly to the internet.

## 6. Upgrade

1. Download and extract the new version to a separate directory.
2. From the old workspace directory, run:

```bash
python3 升级.py "/path/to/new/Scholar-Workspace-vX.Y.Z"
```

Use `--dry-run` to preview the operation. The upgrader backs up first, replaces code, and preserves `data/`, `local/`, and `attachments/`.

## 7. Troubleshooting

- Page does not open: visit <http://127.0.0.1:8765/api/ping> and check that another process is not using port 8765.
- Wrong Python: confirm the launcher resolves to Python 3.9+; prefer `py -3` on Windows.
- macOS blocks a `.command` file: in Finder, right-click and choose Open. Run only files from a verified repository release.
- Verify an installation: run `python3 tests/platform_smoke.py`. It operates entirely in a temporary copy.
- Security concern: follow [SECURITY.md](../SECURITY.md) and report it privately.
