#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包成给别人的压缩包
============================================================================

    python3 scripts/打包.py            两个版本都出
    python3 scripts/打包.py --public   只出公开版
    python3 scripts/打包.py --check    只检查，不生成（看看会漏什么进去）

为什么要有这个脚本，而不是手动拖文件夹压缩：
手动压最容易出的两类事故是**漏删**和**漏加** —— 漏删就是把 local/、密钥、
运行时状态、被测试写花的 config 一起发出去；漏加就是新写的模块忘了放进去，
对方下下来一跑就报 ImportError。这两件事都不该靠人记。

两个版本的箴言库**条数完全一样**（417 条，一条不删），区别只是署名：
公开版会把「我说」换成实名、把查不到出处的补成「Jay摘抄」；
个人版原样保留 —— 那是你自己的库，「我说」「摘抄」你自己看得懂。
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT.parent
NAME = "学术工作台"

# ---------------------------------------------------------------- 收谁 / 不收谁

# 整个目录不收
SKIP_DIRS = {
    "local",            # 生活数据、密钥、设备配置、备份 —— 一条都不能出去
    "attachments",      # 你自己的 PDF
    ".git", "__pycache__", ".pytest_cache", ".idea", ".vscode",
    "_to_delete", "_stage", "_restore", "内部文档",   # 内部文档是给我和你看的，不是给用户看的
    "data/presence",    # 局域网互相看见对方在线的心跳文件，装完自己会生成
    "data/_claude/audits",
}

# 单个文件不收
SKIP_FILES = {
    "portal.html",                  # 每次开机自动生成，里面有内网 IP
    "layout-mockup.html",           # 设计稿
    "layout-mockup-v2.html",
    "data/_claude/next-run.json",   # 运行时状态
    "data/_claude/radar-raw.json",
    "data/reports/weekly-2026-W31.md",
}

SKIP_SUFFIX = {".zip", ".pyc", ".pyo", ".log", ".tmp", ".DS_Store"}
SKIP_GLOB = ("*.tmp*", "*.bak", "._*")

# 必须在包里的文件。少一个就说明打包漏了东西 —— 宁可报错也不要发一个跑不起来的包。
MUST_HAVE = [
    "server.py", "services.py", "library.py", "search.py", "pdfmeta.py",
    "radar.py", "升级.py",
    "app/index.html", "app/js/core.js",
    "scripts/journal.py", "scripts/audit.py", "scripts/radar.py", "scripts/primer.py",
    "skills/lit-radar/SKILL.md", "skills/weekly-journal/SKILL.md",
    "tests/跑全部.sh", "tests/19-学术雷达.py",
    "README.md", "使用教程.md", "LICENSE",
    "安装-Mac.command", "安装-Windows.bat", "启动.command", "启动.bat",
    "data/config.json", "data/quotes.json",
]

# 绝不能出现在包里的东西。这是最后一道闸 —— 上面的规则万一写漏了，这里兜住。
FORBIDDEN_PATH = re.compile(r"(^|/)(local|attachments|\.git|__pycache__|_to_delete)(/|$)")
# 包里每个文本文件都会被扫一遍，看有没有长得像密钥的东西
SECRET_PATTERNS = [
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "OpenAI/Anthropic key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "私钥"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
]
# 这些文件本来就在讲「密钥长什么样」，扫到不算数
SECRET_WHITELIST = {"scripts/打包.py", "使用教程.md", "交付说明.md", "README.md",
                    "docs/安装与使用.md", "tests/README.md"}


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def keep(p: Path) -> bool:
    r = rel(p)
    parts = r.split("/")
    for i in range(len(parts)):
        if "/".join(parts[: i + 1]) in SKIP_DIRS or parts[i] in SKIP_DIRS:
            return False
    if r in SKIP_FILES or p.suffix in SKIP_SUFFIX or p.name in SKIP_SUFFIX:
        return False
    for g in SKIP_GLOB:
        if p.match(g):
            return False
    return True


def collect():
    return sorted((p for p in ROOT.rglob("*") if p.is_file() and keep(p)), key=rel)


# ---------------------------------------------------------------- 打包前的清洗

def clean_config(raw: dict) -> dict:
    """把 data/config.json 恢复成「干净的出厂设置」。

    为什么需要：跑界面测试的时候，浏览器是真的在点你的设置页，config.json
    会被写进一堆测试值 —— 早期发出去的包里就带着测试写的嵌套垃圾键。
    与其人工挑，不如直接拿 server.py 里的 DEFAULT_CONFIG 当准绳：
    只保留默认配置里有的键，其余一律丢掉。
    """
    sys.path.insert(0, str(ROOT))
    import server as srv  # noqa: E402

    out = json.loads(json.dumps(srv.DEFAULT_CONFIG))
    dropped = sorted(set(raw) - set(out))
    # 界面外观这类无害的个人偏好可以留下，别的都用默认值
    for k in ("theme", "brand", "layout", "quicklinks", "sections",
              "today_horizon_days", "stale_manuscript_days"):
        if k in raw:
            out[k] = raw[k]
    # 新装的人应该从头走一遍向导，且不该继承任何人的身份/路径/密钥相关设置
    out["owner"] = ""
    out["setup"] = {"done": False, "step": 0, "completed_at": ""}
    out["lib_folders"] = []
    out["security"] = json.loads(json.dumps(srv.DEFAULT_CONFIG["security"]))
    return out, dropped


def clean_quotes(raw: dict, public: bool):
    """公开版**一条不删**，只把空着的出处补上一个诚实的署名。

    箴言库里混着四类东西，公开版各按各的署：

      1. 已经有出处的（《道德经》、苏轼、Feynman…）—— 原样不动。
      2. 出处写「我说」的 71 条 —— 是 Jay 自己写的。在他自己的库里
         「我说」很自然，但发给外人看，「我」是谁就没人知道了，所以署实名。
      3. 出处写「摘抄」但其实是这个工作台自带的语料（id 以 jeef 开头的那批，
         当初是为这个工作台写的、不是从别处抄的）—— 署「工作台自带」。
         这批要是也署成「Jay摘抄」，等于把他没抄过的话算到他头上。
      4. 剩下真正查不到出处的 —— 署「Jay摘抄」。

    第 4 类是大头。这些多半是网络流传的无名句子、剧集台词、歌词片段，
    本来就没有可考的作者。`scripts/补出处.py` 已经查过一遍，能查实的都补了
    真实出处；查不实的宁可写「Jay摘抄」，也不安一个看着很像的作者上去 ——
    署错名比不署名坏得多。

    个人版原样保留：那是他自己的库，「我说」「摘抄」他自己看得懂。
    """
    qs = raw.get("quotes") or []
    if not public:
        return raw, {}
    ANON = {"摘抄", ""}
    out, stat = [], {"总数": len(qs), "我说→Jay": 0, "→工作台自带": 0, "→Jay摘抄": 0}
    for q in qs:
        q = dict(q)
        s = (q.get("s") or "").strip()
        if s == "我说":
            q["s"] = "Jay"
            stat["我说→Jay"] += 1
        elif s in ANON:
            if str(q.get("id") or "").startswith("jeef"):
                q["s"] = "工作台自带"
                stat["→工作台自带"] += 1
            else:
                q["s"] = "Jay摘抄"
                stat["→Jay摘抄"] += 1
        out.append(q)
    return dict(raw, quotes=out), stat


# ---------------------------------------------------------------- 出包前的自检

def audit(stage: Path, files):
    """包已经摊在临时目录里了，发出去之前最后扫一遍。"""
    problems = []

    for r in files:
        if FORBIDDEN_PATH.search(r):
            problems.append(f"不该带的路径进包了：{r}")

    have = set(files)
    for m in MUST_HAVE:
        if m not in have:
            problems.append(f"少了必需文件：{m}")

    # 密钥扫描
    for r in files:
        if r in SECRET_WHITELIST:
            continue
        f = stage / r
        if f.suffix in {".png", ".jpg", ".gif", ".pdf", ".ico", ".woff", ".woff2"}:
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat, what in SECRET_PATTERNS:
            m = pat.search(txt)
            if m:
                problems.append(f"{r} 里疑似有 {what}：{m.group(0)[:12]}…")

    # 每个 .py 都得能编译 —— 免得发出去一个语法错的包。
    #
    # 这里**必须**用内置的 compile()，不能图省事去 subprocess 调 py_compile：
    # py_compile 会真的往旁边写 __pycache__/*.pyc，也就是说「自检」这个动作
    # 本身会往待打包的目录里塞进 26 个字节码文件，然后被一起压进包发出去。
    # 第一版就是这么翻的车 —— 检查工具污染了被检查的东西。
    for r in files:
        if r.endswith(".py"):
            try:
                compile((stage / r).read_text(encoding="utf-8"), r, "exec")
            except SyntaxError as e:
                problems.append(f"{r} 语法错：第 {e.lineno} 行 {e.msg}")
            except Exception as e:
                problems.append(f"{r} 读不了：{e}")

    # JSON 都得能解析
    for r in files:
        if r.endswith(".json"):
            try:
                json.loads((stage / r).read_text(encoding="utf-8"))
            except Exception as e:
                problems.append(f"{r} 不是合法 JSON：{e}")

    # 箴言：一条都不能少，而且每条都得有出处。
    # 界面上出处是显示在句子下面那一行的，空着会渲染成一个孤零零的破折号。
    qs = json.loads((stage / "data/quotes.json").read_text(encoding="utf-8"))["quotes"]
    blank = [q for q in qs if not (q.get("s") or "").strip()]
    if blank:
        problems.append(f"有 {len(blank)} 条箴言没有出处，"
                        f"例如：{blank[0].get('t', '')[:30]}")
    empty = [q for q in qs if not str(q.get("t") or "").strip()]
    if empty:
        problems.append(f"有 {len(empty)} 条箴言正文是空的")

    return problems


def build(version, public, files, check_only=False):
    tag = "-公开版" if public else ""
    stage_root = Path(tempfile.mkdtemp(prefix="pack-"))
    stage = stage_root / NAME
    rels = []

    for p in files:
        r = rel(p)
        dst = stage / r
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        rels.append(r)

    # 清洗 config
    cfg_raw = json.loads((stage / "data/config.json").read_text(encoding="utf-8"))
    cfg, dropped = clean_config(cfg_raw)
    (stage / "data/config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # 清洗箴言
    q_raw = json.loads((stage / "data/quotes.json").read_text(encoding="utf-8"))
    q, qstat = clean_quotes(q_raw, public)
    (stage / "data/quotes.json").write_text(
        json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")

    # 空目录也要在，不然第一次写入会报错
    for d in ("local", "attachments", "data/presence"):
        (stage / d).mkdir(parents=True, exist_ok=True)
        (stage / d / ".gitkeep").write_text("", encoding="utf-8")

    problems = audit(stage, rels)
    print(f"\n=== {NAME} v{version}{tag} ===")
    print(f"  文件 {len(rels)} 个")
    if dropped:
        print(f"  config 里清掉了 {len(dropped)} 个非默认键：{', '.join(dropped[:8])}"
              + ("…" if len(dropped) > 8 else ""))
    if qstat:
        print(f"  箴言 {qstat['总数']} 条全保留；补署名："
              f"「我说」→Jay {qstat['我说→Jay']} 条、"
              f"→工作台自带 {qstat['→工作台自带']} 条、"
              f"→Jay摘抄 {qstat['→Jay摘抄']} 条")
    if problems:
        print("  ✗ 自检没过：")
        for x in problems:
            print("     -", x)
        shutil.rmtree(stage_root, ignore_errors=True)
        return None, problems
    print("  ✓ 自检通过（无密钥 · 无 local/ · 必需文件齐 · py/json 都能读）")

    if check_only:
        shutil.rmtree(stage_root, ignore_errors=True)
        return None, []

    out = OUT_DIR / f"{NAME}-v{version}{tag}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(stage.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(stage_root).as_posix())
    shutil.rmtree(stage_root, ignore_errors=True)

    # 压完再拆开数一遍。前面那些检查看的都是「我打算放什么」，
    # 这一步看的是「实际躺在压缩包里的是什么」—— 只有这个才作数。
    with zipfile.ZipFile(out) as z:
        got = {n[len(NAME) + 1:] for n in z.namelist() if not n.endswith("/")}
    want = set(rels) | {"local/.gitkeep", "attachments/.gitkeep", "data/presence/.gitkeep"}
    extra = sorted(got - want)
    missing = sorted(want - got)
    if extra or missing:
        print("  ✗ 压缩包里的东西和计划的对不上：")
        for x in extra[:10]:
            print("     多了：", x)
        for x in missing[:10]:
            print("     少了：", x)
        return None, ["压缩包内容与计划不符"]
    print(f"  ✓ 压缩包核对无误（{len(got)} 个文件，与计划一致）")
    print(f"  → {out}  ({out.stat().st_size / 1024:.0f} KB)")
    return out, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public", action="store_true", help="只出公开版")
    ap.add_argument("--personal", action="store_true", help="只出个人版")
    ap.add_argument("--check", action="store_true", help="只自检，不生成文件")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    import server as srv
    version = srv.VERSION

    files = collect()
    both = not (args.public or args.personal)
    bad = []
    if args.personal or both:
        _, p = build(version, False, files, args.check)
        bad += p
    if args.public or both:
        _, p = build(version, True, files, args.check)
        bad += p
    print()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
