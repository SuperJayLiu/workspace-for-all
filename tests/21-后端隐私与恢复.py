#!/usr/bin/env python3
"""Regression tests for privacy boundaries, recovery, concurrency and Git safety."""
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S


FAIL = []


def check(name, ok, detail=""):
    if not ok:
        FAIL.append(name)
        print("  ✗", name, detail)
    else:
        print("  ✓", name)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


with tempfile.TemporaryDirectory(prefix="workspace-backend-safety-") as td:
    root = Path(td) / "workspace"
    data = root / "data"
    local = root / "local"
    claude = data / "_claude"
    for d in (data, local / "life", claude, root / ".git"):
        d.mkdir(parents=True, exist_ok=True)

    # Redirect every mutable module path before exercising the backend.
    S.ROOT, S.APP, S.DATA, S.LOCAL, S.CLAUDE = root, root / "app", data, local, claude
    S.CONFIG_PATH = data / "config.json"
    S.DEVICE_PATH = local / "device.json"
    S.SECRETS_PATH = local / "secrets.json"
    S.QUOTA_PATH = claude / "quota.json"
    S.QUEUE_PATH = claude / "queue.json"
    S.QUOTES_PATH = data / "quotes.json"
    S.DONE_MARKS = local / "done-marks.json"
    S.SYNC_LOG = local / "sync.log"
    S.LIB_PATH = data / "library.jsonl"
    S._LIB = None
    S._REC_CACHE.clear()

    cfg = json.loads(json.dumps(S.DEFAULT_CONFIG))
    save_json(S.CONFIG_PATH, cfg)
    save_json(S.DEVICE_PATH, S.DEFAULT_DEVICE)
    save_json(S.SECRETS_PATH, {})
    save_json(S.QUOTA_PATH, S.DEFAULT_QUOTA)
    save_json(S.QUEUE_PATH, {"tasks": []})

    # Browser file routes must never cross into secrets or Git metadata.
    secret = local / "secrets.json"
    git_config = root / ".git" / "config"
    git_config.write_text("credential=secret", encoding="utf-8")
    check("safe_path blocks local secrets", S.safe_path(secret) is None)
    check("safe_path blocks .git/config", S.safe_path(git_config) is None)
    check("open_local_file blocks Git metadata", S.open_local_file(str(git_config))[0] is None)
    imports = local / "imports"
    imports.mkdir()
    rogue_table = imports / "rogue.csv"
    rogue_table.write_text("title\nrogue\n", encoding="utf-8")
    check("unregistered LOCAL/imports file stays denied",
          S.safe_path(rogue_table) is None and S.safe_table_path(rogue_table) is None)
    uploaded_table = imports / "uploaded.csv"
    uploaded_table.write_text("title\nallowed\n", encoding="utf-8")
    check("registered API table upload is narrowly allowed",
          S.remember_uploaded_table(uploaded_table)
          and S.safe_table_path(uploaded_table) == uploaded_table.resolve()
          and S.safe_path(uploaded_table) is None)
    wrong_suffix = imports / "uploaded.md"
    wrong_suffix.write_text("secret", encoding="utf-8")
    check("uploaded-table exception enforces suffix",
          not S.remember_uploaded_table(wrong_suffix) and S.safe_table_path(wrong_suffix) is None)
    S.APP.mkdir(exist_ok=True)
    sibling = root / "app-evil"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret", encoding="utf-8")

    class StaticProbe:
        def _send(self, code, *_args, **_kwargs):
            self.code = code
            return code

    probe = StaticProbe()
    S.Handler.static(probe, "/../app-evil/secret.txt")
    check("static route rejects prefix-sibling traversal", probe.code == 404)
    session = S.new_session("192.0.2.10", "test")
    check("remote session is bound to its login IP",
          S.get_session(session, "192.0.2.10") is not None
          and S.get_session(session, "192.0.2.11") is None)

    # Exact revisions plus a per-record lock reject stale writes immediately.
    first = S.write_record("ideas", {"title": "revision", "body": "one"})
    second = S.write_record("ideas", {**first, "body": "two"}, first["_mtime"], first["_rev"])
    stale_rejected = False
    try:
        S.write_record("ideas", {**first, "body": "stale"}, first["_mtime"], first["_rev"])
    except S.Conflict:
        stale_rejected = True
    check("stale exact revision is rejected", stale_rejected)
    check("latest record survives conflict", S.read_record("ideas", first["id"])["body"] == "two")
    check("revision changes after save", second["_rev"] != first["_rev"])

    # Encryption must fail closed, and snapshot names must never collide.
    cfg = S.get_config()
    cfg["security"]["encrypt_backup"] = True
    save_json(S.CONFIG_PATH, cfg)
    enc = S.snapshot("daily")
    check("encrypted backup without password fails", not enc.get("ok"))
    check("failed encryption leaves no plaintext ZIP",
          not list((local / "backups" / "rolling").glob("workspace_*_daily.zip")))
    cfg["security"]["encrypt_backup"] = False
    save_json(S.CONFIG_PATH, cfg)
    a, b = S.snapshot("manual"), S.snapshot("manual")
    check("same-second snapshots have distinct names",
          a.get("ok") and b.get("ok") and a.get("path") != b.get("path"))

    # A restore replaces the captured trees; post-snapshot files must disappear.
    extra = data / "ideas" / "created-after-backup.md"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("extra", encoding="utf-8")
    backup = local / "backups" / "rolling" / "workspace_restore_fixture.zip"
    backup.parent.mkdir(parents=True, exist_ok=True)
    clean_cfg = json.loads(json.dumps(S.DEFAULT_CONFIG))
    with zipfile.ZipFile(backup, "w") as z:
        z.writestr("data/config.json", json.dumps(clean_cfg))
        z.writestr("data/ideas/from-backup.md", "---\ntitle: restored\n---\n\nbody")
        z.writestr("local/life/diet/from-backup.md", "---\ntitle: meal\n---\n")
    restored = S.restore_snapshot(str(backup))
    check("restore succeeds", restored.get("ok"), restored)
    check("restore removes files absent from snapshot", not extra.exists())
    check("restore installs captured data", (data / "ideas" / "from-backup.md").exists())

    # Source origin is always blocked; a confirmed private remote is required.
    original_git = S.git
    calls = []

    def source_git(*args, **_kwargs):
        calls.append(args)
        if args[:2] == ("rev-parse", "--is-inside-work-tree"):
            return 0, "true", ""
        if args[:3] == ("remote", "get-url", "origin"):
            return 0, "https://github.com/SuperJayLiu/workspace-for-all.git", ""
        return 0, "", ""

    S.git = source_git
    blocked = S.git_sync("must not publish")
    check("public source origin blocks sync", not blocked.get("ok") and blocked.get("blocked") == "sync-policy")
    check("public source block happens before add", not any(x and x[0] == "add" for x in calls))

    private_remote = "https://github.com/example/private-data.git"
    clean_cfg["git"] = {"private_sync_confirmed": True, "confirmed_remote": private_remote}
    save_json(S.CONFIG_PATH, clean_cfg)
    calls.clear()

    def failed_push_git(*args, **_kwargs):
        calls.append(args)
        if args[:2] == ("rev-parse", "--is-inside-work-tree"):
            return 0, "true", ""
        if args[:3] == ("remote", "get-url", "origin"):
            return 0, private_remote, ""
        if args and args[0] == "commit":
            return 1, "nothing to commit, working tree clean", ""
        if args and args[0] == "push":
            return 1, "", "network failed"
        return 0, "", ""

    S.git = failed_push_git
    failed = S.git_sync("push must fail")
    check("push exit code 1 is reported as failure", failed.get("ok") is False)
    S.git = original_git

    upgrade_source = (Path(__file__).resolve().parent.parent / "升级.py").read_text(encoding="utf-8")
    check("upgrader replaces top-level radar.py", '"radar.py"' in upgrade_source.split("CODE_ITEMS", 1)[1].split("]", 1)[0])


if FAIL:
    print(f"后端隐私与恢复测试：{len(FAIL)} 项失败")
    raise SystemExit(1)
print("后端隐私与恢复测试：全部通过 ✓")
