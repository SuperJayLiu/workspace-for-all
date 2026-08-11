#!/usr/bin/env python3
"""Build a deterministic, privacy-audited Scholar Workspace ZIP.

Normal builds use Git's tracked-file manifest, so an editor backup, runtime
report, device heartbeat, or other untracked file cannot slip into a release.
`--include-untracked` exists only for validating a not-yet-staged development
tree; the same allowlist and privacy audit still apply.
"""
import argparse
import ast
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = ROOT.parent

ALLOWED_DIRS = {"app", "data", "docs", "scripts", "skills", "tests"}
ALLOWED_TOP_FILES = {
    "server.py", "services.py", "library.py", "search.py", "pdfmeta.py", "radar.py", "升级.py",
    "README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
    "CHANGELOG.md", "ROADMAP.md", "LICENSE", "使用教程.md", "交付说明.md",
    "package.json", "package-lock.json",
    "安装-Mac.command", "安装-Windows.bat", "启动.command", "启动.bat",
    "局域网启动.command", "局域网启动.bat", "卸载自启-Mac.command", "卸载自启-Windows.bat",
}
SKIP_DIRS = {
    "local", "attachments", ".git", "node_modules", "__pycache__", ".pytest_cache",
    ".idea", ".vscode", "_to_delete", "_stage", "_restore", "内部文档",
    "data/presence", "data/_claude/audits",
}
SKIP_FILES = {
    "portal.html", "layout-mockup.html", "layout-mockup-v2.html",
    "data/_claude/next-run.json", "data/_claude/radar-raw.json",
}
SKIP_SUFFIXES = {".zip", ".pyc", ".pyo", ".log", ".tmp", ".DS_Store"}
MUST_HAVE = {
    "server.py", "services.py", "library.py", "search.py", "pdfmeta.py", "radar.py", "升级.py",
    "app/index.html", "app/js/core.js", "app/js/i18n.js",
    "scripts/journal.py", "scripts/audit.py", "scripts/radar.py", "scripts/primer.py",
    "skills/lit-radar/SKILL.md", "skills/weekly-journal/SKILL.md",
    "tests/跑全部.sh", "tests/platform_smoke.py", "tests/19-学术雷达.py", "tests/21-后端隐私与恢复.py",
    "README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE",
    "安装-Mac.command", "安装-Windows.bat", "启动.command", "启动.bat",
    "data/config.json", "data/quotes.json",
}

SECRET_PATTERNS = [
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "AI API key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
]
PERSONAL_PATH_PATTERNS = [
    re.compile(r"/Users/(?!(?:me|you|username|your-name|example)/)[A-Za-z0-9._-]+/"),
    re.compile(r"/home/(?!(?:user|me|you|username|example)/)[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\(?!(?:你|me|you|username|your-name|example)\\)[^\\\r\n]+\\", re.IGNORECASE),
]

PUBLIC_QUOTA = {
    "rate_per_week": 14.0, "week_start": "", "spent_this_week": 0.0,
    "history": [], "runs": [], "blocked_events": [], "activity": {},
    "overrides": {"tonight_boost": False, "silent_week": False}, "unread_reports": 0,
}
PUBLIC_QUEUE = {"progress": "", "tasks": []}


def rel(path):
    return path.relative_to(ROOT).as_posix()


def git_manifest(include_untracked=False):
    args = ["git", "ls-files", "-z"]
    if include_untracked:
        args = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    result = subprocess.run(args, cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("a Git worktree is required for safe packaging")
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def allowed(relative):
    path = Path(relative)
    if path.name.startswith("._") or path.name.endswith((".bak", "~")):
        return False
    if path.suffix in SKIP_SUFFIXES or relative in SKIP_FILES:
        return False
    if relative.startswith("data/reports/weekly-"):
        return False
    parts = path.parts
    for index in range(len(parts)):
        if "/".join(parts[: index + 1]) in SKIP_DIRS or parts[index] in SKIP_DIRS:
            return False
    return (len(parts) == 1 and relative in ALLOWED_TOP_FILES) or (parts and parts[0] in ALLOWED_DIRS)


def collect(include_untracked=False):
    files = []
    for relative in git_manifest(include_untracked):
        if not allowed(relative):
            continue
        path = ROOT / relative
        if path.is_symlink():
            raise RuntimeError(f"refusing to package symlink: {relative}")
        if path.is_file():
            files.append(path)
    return sorted(files, key=rel)


def literal_assignment(path, variable):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError(f"could not find literal {variable} in {path.name}")


def application_version():
    version = literal_assignment(ROOT / "server.py", "VERSION")
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise RuntimeError(f"server VERSION is not strict semver: {version!r}")
    return version


def clean_config(stage):
    defaults = literal_assignment(stage / "server.py", "DEFAULT_CONFIG")
    defaults["owner"] = ""
    defaults["setup"] = {"done": False, "step": 0, "completed_at": ""}
    defaults["lib_folders"] = []
    if isinstance(defaults.get("profile"), dict):
        defaults["profile"] = {"name": "", "city": "", "lat": None, "lon": None, "field": "", "keywords": []}
    (stage / "data/config.json").write_text(
        json.dumps(defaults, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def source_config_problems():
    """Fail closed when the repository factory config drifts from server defaults."""
    defaults = literal_assignment(ROOT / "server.py", "DEFAULT_CONFIG")
    source = json.loads((ROOT / "data/config.json").read_text(encoding="utf-8"))
    unknown = sorted(set(source) - set(defaults))
    missing = sorted(set(defaults) - set(source))
    problems = []
    if unknown:
        problems.append(f"data/config.json has unknown top-level keys: {', '.join(unknown)}")
    if missing:
        problems.append(f"data/config.json is missing default top-level keys: {', '.join(missing)}")
    return problems


def reset_runtime_state(stage):
    states = {
        "data/_claude/quota.json": PUBLIC_QUOTA,
        "data/_claude/queue.json": PUBLIC_QUEUE,
    }
    for relative, value in states.items():
        path = stage / relative
        if path.exists():
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for relative in ("data/_claude/inbox.md",):
        path = stage / relative
        if path.exists():
            path.write_text("", encoding="utf-8")


def audit(stage, relative_files):
    problems = []
    have = set(relative_files)
    for required in sorted(MUST_HAVE - have):
        problems.append(f"missing required file: {required}")
    forbidden_runtime = [r for r in relative_files if r.startswith("data/presence/") or r.startswith("data/reports/weekly-")]
    problems.extend(f"runtime state must not be packaged: {r}" for r in forbidden_runtime)

    for relative in relative_files:
        path = stage / relative
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, label in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                problems.append(f"{relative} contains a possible {label}: {match.group(0)[:12]}…")
        for pattern in PERSONAL_PATH_PATTERNS:
            match = pattern.search(text)
            if match:
                problems.append(f"{relative} contains a machine-specific user path: {match.group(0)[:60]}")
        if relative.endswith(".py"):
            try:
                compile(text, relative, "exec")
            except SyntaxError as exc:
                problems.append(f"{relative} has invalid Python syntax at line {exc.lineno}: {exc.msg}")
        if relative.endswith((".json", ".webmanifest")):
            try:
                json.loads(text)
            except Exception as exc:
                problems.append(f"{relative} is invalid JSON: {exc}")

    config = json.loads((stage / "data/config.json").read_text(encoding="utf-8"))
    if config.get("owner") or config.get("lib_folders") or any((config.get("profile") or {}).values()):
        problems.append("public config still contains identity or machine-path fields")
    quota = json.loads((stage / "data/_claude/quota.json").read_text(encoding="utf-8"))
    if quota != PUBLIC_QUOTA:
        problems.append("AI quota runtime state was not reset")
    quotes = json.loads((stage / "data/quotes.json").read_text(encoding="utf-8")).get("quotes", [])
    if any(not str(item.get("t") or "").strip() or not str(item.get("s") or "").strip() for item in quotes):
        problems.append("every bundled quote must have text and attribution")
    return problems


def build(public, files, output_dir, check_only=False):
    version = application_version()
    root_name = f"Scholar-Workspace-v{version}" if public else f"学术工作台-v{version}"
    archive_name = f"{root_name}.zip"
    source_problems = source_config_problems()
    if source_problems:
        print(f"\n=== {root_name} ===")
        for problem in source_problems:
            print(f"  ✗ {problem}")
        return None, source_problems
    with tempfile.TemporaryDirectory(prefix="scholar-package-") as temporary:
        stage_root = Path(temporary)
        stage = stage_root / root_name
        relative_files = []
        for source in files:
            relative = rel(source)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            relative_files.append(relative)

        clean_config(stage)
        reset_runtime_state(stage)
        for directory in ("local", "attachments", "data/presence"):
            path = stage / directory
            path.mkdir(parents=True, exist_ok=True)
            (path / ".gitkeep").write_text("", encoding="utf-8")

        problems = audit(stage, relative_files)
        print(f"\n=== {root_name} ===")
        print(f"  files: {len(relative_files)}")
        if problems:
            print("  ✗ package audit failed")
            for problem in problems:
                print(f"    - {problem}")
            return None, problems
        print("  ✓ allowlist, privacy, syntax, JSON, config, and runtime-state checks passed")
        if check_only:
            return None, []

        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / archive_name
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(
                        path.relative_to(stage_root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0)
                    )
                    info.create_system = 3
                    mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                    info.external_attr = (stat.S_IFREG | mode) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

        expected = set(relative_files) | {"local/.gitkeep", "attachments/.gitkeep", "data/presence/.gitkeep"}
        with zipfile.ZipFile(output) as archive:
            prefix = root_name + "/"
            actual = {name[len(prefix):] for name in archive.namelist() if name.startswith(prefix) and not name.endswith("/")}
        if actual != expected:
            output.unlink(missing_ok=True)
            return None, [f"archive manifest mismatch: {len(actual - expected)} extra, {len(expected - actual)} missing"]
        print(f"  ✓ archive manifest verified ({len(actual)} files)")
        print(f"  → {output} ({output.stat().st_size / 1024:.0f} KB)")
        return output, []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", action="store_true", help="build only the sanitized public archive")
    parser.add_argument("--personal", action="store_true", help="build only the personal-name archive")
    parser.add_argument("--check", action="store_true", help="audit the staged contents without writing a ZIP")
    parser.add_argument("--include-untracked", action="store_true", help="development only: include allowlisted, nonignored untracked files")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    try:
        files = collect(args.include_untracked)
    except Exception as exc:
        print(f"✗ cannot create safe package manifest: {exc}", file=sys.stderr)
        return 1
    both = not (args.public or args.personal)
    problems = []
    if args.personal or both:
        _, found = build(False, files, args.output_dir.resolve(), args.check)
        problems.extend(found)
    if args.public or both:
        _, found = build(True, files, args.output_dir.resolve(), args.check)
        problems.extend(found)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
