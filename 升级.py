#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
升级到新版本 · Upgrade

  python3 升级.py /下载/学术工作台-v4.0.0

把新版本的**代码**换进来，你的**数据一个字都不动**。

为什么需要这个脚本：直接解压覆盖会把 data/ 和 local/ 一起盖掉，
半年的稿件记录、文献笔记、投稿时间线全没。手动挑文件又极容易漏。

它做的事，按顺序：
  1. 先整包备份到 local/backups/升级前-<时间戳>.zip —— 出任何问题都能退回去
  2. 只替换代码文件（server.py / app/ / scripts/ / tests/ / skills/ / 文档）
  3. data/ 和 local/ 原样保留，一个字节不碰
  4. 把新版本 config 里新增的配置项**补**进你的 config（已有的值不覆盖）
  5. 跑一遍数据迁移（如果这个版本需要）
  6. 校验：能不能起得来

带 --dry-run 可以先看它打算做什么，不实际动手。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 这些是「代码」，升级时整体替换
CODE_ITEMS = ["server.py", "services.py", "library.py", "search.py", "pdfmeta.py",
              "app", "scripts", "tests", "skills", "docs",
              "README.md", "使用教程.md", "交付说明.md", "LICENSE",
              "安装-Mac.command", "安装-Windows.bat", "启动.command", "启动.bat",
              "局域网启动.command", "局域网启动.bat",
              "卸载自启-Mac.command", "卸载自启-Windows.bat", "升级.py"]

# 这些是「你的东西」，升级时**永不触碰**
KEEP_ITEMS = ["data", "local", "attachments", ".git", ".gitignore"]


def log(msg):
    print(msg, flush=True)


def backup(dry=False):
    dst_dir = HERE / "local" / "backups"
    dst = dst_dir / f"升级前-{time.strftime('%Y-%m-%d_%H%M')}.zip"
    if dry:
        log(f"  [演练] 会先备份到 {dst}")
        return dst
    dst_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in HERE.rglob("*"):
            rel = p.relative_to(HERE)
            head = rel.parts[0] if rel.parts else ""
            if head in (".git",) or "backups" in rel.parts or "__pycache__" in rel.parts:
                continue
            if p.is_file():
                z.write(p, str(rel))
                n += 1
    log(f"  ✓ 已备份 {n} 个文件 → {dst.name}（{dst.stat().st_size // 1024} KB）")
    return dst


def merge_config(new_root, dry=False):
    """把新版本新增的配置项补进现有 config，已有的值一律不动。"""
    cur_p = HERE / "data" / "config.json"
    new_p = new_root / "data" / "config.json"
    if not cur_p.exists() or not new_p.exists():
        log("  · 没有 config 需要合并")
        return 0
    try:
        cur = json.loads(cur_p.read_text(encoding="utf-8"))
        new = json.loads(new_p.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"  ⚠️ config 读不出来，跳过合并：{e}")
        return 0
    added = []

    def walk(c, n, path=""):
        for k, v in n.items():
            if k not in c:
                c[k] = v
                added.append(path + k)
            elif isinstance(v, dict) and isinstance(c.get(k), dict):
                walk(c[k], v, path + k + ".")

    walk(cur, new)
    if added and not dry:
        cur_p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  {'[演练] 会补' if dry else '✓ 补上'} {len(added)} 个新配置项"
        + (f"：{', '.join(added[:8])}{' …' if len(added) > 8 else ''}" if added else ""))
    return len(added)


def migrate(dry=False):
    """数据迁移。每一版加一段，判断条件要写成幂等的（跑两遍不出错）。"""
    done = []
    # v3.9.2 → 之后：文献索引从「一篇一个 md」改成 jsonl，早期版本没有这个文件
    lib = HERE / "data" / "library.jsonl"
    if not lib.exists():
        if not dry:
            lib.parent.mkdir(parents=True, exist_ok=True)
            lib.write_text("", encoding="utf-8")
        done.append("建立空的文献索引 data/library.jsonl")
    # reading.manager：老版本没有这个键，界面会退回默认 zotero，这里显式写上
    cfg_p = HERE / "data" / "config.json"
    if cfg_p.exists():
        try:
            cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
            if "manager" not in (cfg.get("reading") or {}):
                if not dry:
                    cfg.setdefault("reading", {})["manager"] = "zotero"
                    cfg_p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
                done.append("补上 reading.manager")
        except Exception:
            pass
    for d in done:
        log(f"  {'[演练] ' if dry else '✓ '}{d}")
    if not done:
        log("  · 这一版不需要数据迁移")
    return done


def replace_code(new_root, dry=False):
    changed, missing = [], []
    for item in CODE_ITEMS:
        src = new_root / item
        dst = HERE / item
        if not src.exists():
            if dst.exists():
                missing.append(item)
            continue
        if dry:
            changed.append(item)
            continue
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
            if item.endswith((".command", ".sh")):
                os.chmod(dst, 0o755)
        changed.append(item)
    log(f"  {'[演练] 会替换' if dry else '✓ 已替换'} {len(changed)} 项代码")
    if missing:
        log(f"  ⚠️ 新版本里没有这些（可能已被移除，你这边的会保留）：{', '.join(missing)}")
    return changed


def verify():
    """能不能起得来。起不来就当场说，别等用户双击才发现。"""
    try:
        r = subprocess.run([sys.executable, "-c",
                            "import sys; sys.path.insert(0, %r); import server" % str(HERE)],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            log("  ✗ 新代码加载失败：\n" + (r.stderr or "")[-600:])
            return False
        log("  ✓ 新代码能正常加载")
        return True
    except Exception as e:
        log(f"  ✗ 校验时出错：{e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="升级学术工作台，数据原样保留")
    ap.add_argument("new_version", help="新版本解压后的目录（里面应有 server.py）")
    ap.add_argument("--dry-run", action="store_true", help="只看会做什么，不实际改动")
    ap.add_argument("--no-backup", action="store_true", help="跳过备份（不建议）")
    a = ap.parse_args()

    new_root = Path(a.new_version).expanduser().resolve()
    if not (new_root / "server.py").exists():
        log(f"✗ {new_root} 里没有 server.py，这不像是新版本的目录。")
        log("  应该指向解压后那个含 server.py 的文件夹。")
        sys.exit(1)
    if new_root == HERE:
        log("✗ 新版本目录和当前目录是同一个。")
        sys.exit(1)

    def ver(root):
        try:
            for ln in (root / "server.py").read_text(encoding="utf-8").split("\n")[:80]:
                if ln.startswith("VERSION"):
                    return ln.split("=", 1)[1].strip().strip('"\' ')
        except Exception:
            pass
        return "?"

    log(f"当前版本 {ver(HERE)} → 新版本 {ver(new_root)}")
    log(f"工作台目录：{HERE}")
    if a.dry_run:
        log("（演练模式，不会真的改动任何东西）\n")

    log("\n1/5 备份")
    if a.no_backup:
        log("  · 按你的要求跳过了")
    else:
        backup(a.dry_run)

    log("\n2/5 替换代码（data/ 与 local/ 不动）")
    replace_code(new_root, a.dry_run)

    log("\n3/5 合并新增配置项")
    merge_config(new_root, a.dry_run)

    log("\n4/5 数据迁移")
    migrate(a.dry_run)

    log("\n5/5 校验")
    if a.dry_run:
        log("  · 演练模式跳过")
    elif not verify():
        log("\n升级没成功。你的数据没有丢——local/backups/ 里那个「升级前」压缩包")
        log("解开就是升级前的完整状态。")
        sys.exit(1)

    log("\n完成。" + ("（这只是演练，什么都没改）" if a.dry_run
                      else "重新启动工作台即可。数据一条没动。"))


if __name__ == "__main__":
    main()
