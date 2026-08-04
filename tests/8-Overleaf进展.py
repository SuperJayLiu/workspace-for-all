# -*- coding: utf-8 -*-
"""极端测试 8 · Overleaf 写作进展

连不上真的 Overleaf 也要能测：这里用一个本地 git 仓库假扮 Overleaf 项目，
把「clone → 写几笔 → 再同步」整个流程跑一遍，验证字数、增删行、章节、
进展记录的累加逻辑都对。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server as SV  # noqa: E402

FAIL = []


def check(n, c, e=""):
    print(("  ✓ " + n) if c else f"  ✗ {n}  {e}")
    if not c:
        FAIL.append(n)


def git(cwd, *a):
    return subprocess.run(["git"] + list(a), cwd=str(cwd), capture_output=True, text=True)


TEX1 = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
Intermediary constraints matter for asset prices. % 这是注释，不该被数进去
We study whether the effect is nonlinear in China.
\begin{equation}
r_t = \alpha + \beta x_t + \varepsilon_t
\end{equation}
\section{Data}
We use minute-level data.
\end{document}
"""

TEX2 = TEX1.replace("We use minute-level data.",
                    "We use minute-level data from 2019 to 2024. "
                    "本节还补了一段中文说明，用来检验中文字数统计。") + r"""
\section{Results}
The effect is concave.
"""

print("\n=== 0. 准备一个假 Overleaf 项目 ===")
tmp = Path(tempfile.mkdtemp(prefix="ol-test-"))
fake = tmp / "a1b2c3d4e5f6a7b8c9d0e1f2"          # 24 位 id，跟 Overleaf 一样
fake.mkdir()
git(fake, "init", "-q")
git(fake, "config", "user.email", "t@t.t")
git(fake, "config", "user.name", "T")
(fake / "main.tex").write_text(TEX1, encoding="utf-8")
git(fake, "add", "-A")
git(fake, "commit", "-qm", "initial draft")
check("假项目建好了", (fake / ".git").exists())

# 备份真实 secrets 与 progress 目录，测完还原
SEC = ROOT / "local" / "secrets.json"
sec_bak = SEC.read_text(encoding="utf-8") if SEC.exists() else None
prog_dir = ROOT / "data" / "progress"
prog_bak = sorted(p.name for p in prog_dir.glob("*.md")) if prog_dir.exists() else []
ol_dir = SV.OVERLEAF_DIR

_real_repo_url = SV.overleaf_repo_url


def _repo_url_for_test(raw):
    """测试里用本地目录假扮远程仓库；线上仍然只认 overleaf 的地址。"""
    raw = str(raw or "")
    if raw.startswith("/") and (Path(raw) / ".git").exists():
        return raw
    return _real_repo_url(raw)


try:
    sj = json.loads(sec_bak) if sec_bak else {}
    sj["overleaf"] = {"email": "test@example.com", "token": "olp_faketoken"}
    SEC.write_text(json.dumps(sj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 1. 地址解析：三种写法都要认 ===")
    pid = "a1b2c3d4e5f6a7b8c9d0e1f2"
    for raw, want in [
        (f"https://www.overleaf.com/project/{pid}", f"https://git.overleaf.com/{pid}"),
        (f"https://git.overleaf.com/{pid}", f"https://git.overleaf.com/{pid}"),
        (pid, f"https://git.overleaf.com/{pid}"),
        ("", ""),
        ("随便乱写的东西", ""),
        ("https://www.overleaf.com/read/xyz", ""),
    ]:
        got = SV.overleaf_repo_url(raw)
        check(f"解析 {raw[:38] or '（空）'!r} → {got or '（拒绝）'}", got == want, f"期望 {want}")

    print("\n=== 2. token 绝不能出现在日志里 ===")
    code, out, err = SV._ol_git(None, "clone", "--quiet",
                                "https://x:olp_faketoken@127.0.0.1:1/nope", str(tmp / "nope"))
    check("clone 失败信息里没有明文 token", "olp_faketoken" not in (out + err), (out + err)[:80])
    auth = SV._ol_auth_url(f"https://git.overleaf.com/{pid}")
    check("拼出来的地址带上了凭据", "olp_faketoken" in auth and "test%40example.com" in auth, auth[:60])

    SV.overleaf_repo_url = _repo_url_for_test      # 只在这几步里替换掉
    print("\n=== 3. 首次同步：建立基线 ===")
    r1 = SV.overleaf_sync(url=str(fake))            # 用本地路径假扮远程
    check("首次同步成功", r1.get("ok"), str(r1)[:120])
    if r1.get("ok"):
        check("认出这是第一次", r1["first_time"] is True)
        check("数出了英文词数", r1["words"] > 10, str(r1["words"]))
        check("注释没有被数进去", "注释" not in json.dumps(r1, ensure_ascii=False))
        check("章节抓出来了", set(["Introduction", "Data"]) <= set(r1["sections"]), str(r1["sections"]))
        check("公式没有被当成正文", r1["cjk"] == 0, str(r1["cjk"]))
        base_words = r1["words"]

    print("\n=== 4. 又写了一笔之后再同步 ===")
    (fake / "main.tex").write_text(TEX2, encoding="utf-8")
    (fake / "notes.tex").write_text("\\section{Notes}\n临时笔记。\n", encoding="utf-8")
    git(fake, "add", "-A")
    git(fake, "commit", "-qm", "补数据段与结果段")
    r2 = SV.overleaf_sync(url=str(fake))
    check("第二次同步成功", r2.get("ok"), str(r2)[:120])
    if r2.get("ok"):
        check("发现有新提交", len(r2["commits"]) == 1, str(len(r2["commits"])))
        check("提交说明读到了", r2["commits"][0]["msg"] == "补数据段与结果段", str(r2["commits"][:1]))
        check("算出了净增行数", r2["net"] > 0, str(r2["net"]))
        check("列出了改动的文件", "main.tex" in r2["touched"], str(r2["touched"]))
        check("字数变多了", r2["words"] > base_words, f"{base_words} → {r2['words']}")
        check("中文字数统计生效", r2["cjk"] > 0, str(r2["cjk"]))
        check("新章节被认出来", "Results" in r2["sections"], str(r2["sections"]))

    print("\n=== 5. 没有新提交时不该报错 ===")
    r3 = SV.overleaf_sync(url=str(fake))
    check("重复同步仍然成功", r3.get("ok"), str(r3)[:100])
    check("如实报告「没有变化」", r3.get("changed") is False, str(r3.get("changed")))
    check("字数仍然算得出来", r3.get("words", 0) > 0)

    print("\n=== 6. 进展记录：同一天累加，不重复建 ===")
    mid = "overleaf测试稿件-aaaaaa"
    SV.write_record("manuscripts", {"id": mid, "title": "（测试）Overleaf 稿件",
                                    "stage": "writing", "overleaf_url": str(fake)})
    SV.overleaf_record(mid, r2)
    rec1 = SV.read_record("progress", f"progress-{fake.name}-{SV.today_str()}")
    check("生成了进展记录", bool(rec1), str(rec1)[:80])
    if rec1:
        check("记了提交数", rec1.get("commits") == 1, str(rec1.get("commits")))
        check("记了增删行", rec1.get("added", 0) > 0)
        check("挂到了对应稿件", rec1.get("manuscript") == mid, str(rec1.get("manuscript")))
    SV.overleaf_record(mid, r2)                      # 同一天再来一次
    rec2 = SV.read_record("progress", f"progress-{fake.name}-{SV.today_str()}")
    check("同一天不会新建第二条", len(list((ROOT / "data" / "progress").glob(f"*{fake.name}*"))) == 1)
    check("同一天的数据是累加的", (rec2 or {}).get("commits") == 2, str((rec2 or {}).get("commits")))

    SV.overleaf_repo_url = _real_repo_url
    print("\n=== 7. 错误信息要是人话 ===")
    for raw, kw in [("Authentication failed for 'https://git.overleaf.com/x'", "token"),
                    ("remote: HTTP 403 forbidden", "没权限"),
                    ("repository not found", "找不到"),
                    ("could not resolve host: git.overleaf.com", "连不上")]:
        got = SV._overleaf_err(raw)
        check(f"{raw[:34]} → {got[:24]}", kw in got, got)
    sj["overleaf"] = {"email": "", "token": ""}
    SEC.write_text(json.dumps(sj, ensure_ascii=False, indent=2), encoding="utf-8")
    r = SV.overleaf_sync(url=f"https://www.overleaf.com/project/{pid}")
    check("没填 token 时说人话", not r["ok"] and "token" in r["detail"], str(r)[:90])

finally:
    SV.overleaf_repo_url = _real_repo_url
    if sec_bak is not None:
        SEC.write_text(sec_bak, encoding="utf-8")
    # 清掉测试产生的记录与克隆
    for f in (ROOT / "data" / "progress").glob("*.md"):
        if f.name not in prog_bak:
            f.unlink(missing_ok=True)
    (ROOT / "data" / "manuscripts" / "overleaf测试稿件-aaaaaa.md").unlink(missing_ok=True)
    for t in (ROOT / "local" / "trash").rglob("overleaf测试稿件*"):
        t.unlink(missing_ok=True)
    shutil.rmtree(ol_dir / fake.name, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n（测试数据已清理）")

print("\n" + "=" * 56)
print("Overleaf 进展测试：" + ("全部通过 ✓" if not FAIL else f"{len(FAIL)} 项失败"))
for f in FAIL:
    print("   ✗", f)
