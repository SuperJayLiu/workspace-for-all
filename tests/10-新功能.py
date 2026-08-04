# -*- coding: utf-8 -*-
"""极端测试 10 · 这一轮新功能的服务端部分

覆盖之前没有任何自动化验证的几块：
邮箱收件、领域助读、品牌自定义、示例过滤开关、批量删除、表格导入的列名映射。
"""
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8806
BASE = f"http://127.0.0.1:{PORT}"
FAIL = []


def _port_free(port):
    s = socket.socket()
    s.settimeout(0.8)
    try:
        s.connect(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


if not _port_free(PORT):
    sys.exit(f"端口 {PORT} 已被占用——先执行：pkill -f 'server.py --port {PORT}'")


def check(n, c, e=""):
    print(("  ✓ " + n) if c else f"  ✗ {n}  {e}")
    if not c:
        FAIL.append(n)


def req(path, data=None, method=None, timeout=25):
    if any(ord(c) > 127 for c in path):
        h, sep, qs = path.partition("?")
        path = urllib.parse.quote(h, safe="/") + sep + qs
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, data=body,
                               method=method or ("POST" if body is not None else "GET"),
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": repr(e)}


SEC = ROOT / "local" / "secrets.json"
CFG = ROOT / "data" / "config.json"
sec_bak = SEC.read_text(encoding="utf-8") if SEC.exists() else None
cfg_bak = CFG.read_text(encoding="utf-8") if CFG.exists() else None

proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT), "--no-open"],
                        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
for _ in range(40):
    time.sleep(0.4)
    if req("/api/ping", timeout=4)[0] == 200:
        break

made = []          # 测试产生的记录，跑完删掉
try:
    print("\n=== 1. 邮箱收件（没配 / 配错都要说人话，不能崩） ===")
    st, r = req("/api/mail/status")
    check("状态接口可用", st == 200, str(r)[:80])
    check("状态接口不吐明文密码", "imap_password" not in json.dumps(r), json.dumps(r)[:90])
    st, r = req("/api/mail/intake", data={})
    check("没开启时明确说没开启", st == 200 and r.get("ok") is False and "没开启" in r.get("detail", ""),
          str(r)[:90])
    req("/api/secrets/merge", data={"push": {"inbox": {
        "enabled": True, "imap_host": "127.0.0.1", "imap_port": "1",
        "imap_user": "x@y.z", "imap_password": "nope"}}})
    t0 = time.time()
    st, r = req("/api/mail/intake", data={}, timeout=60)
    dt = time.time() - t0
    check(f"连不上时给人话而不是堆栈（{dt:.1f}s）",
          st == 200 and r.get("ok") is False and "连不上" in r.get("detail", ""), str(r)[:110])
    st, r = req("/api/mail/status")
    check("配置能读回来", r.get("imap_host") == "127.0.0.1" and r.get("has_pw") is True, str(r)[:90])
    req("/api/secrets/merge", data={"push": {"inbox": {"enabled": False}}})

    print("\n=== 2. 领域助读 ===")
    st, r = req("/api/run/primer-plan", data={})
    d = r.get("data") or {}
    check("没设领域时说清楚要去哪儿设", d.get("ok") is False and "领域" in d.get("detail", ""), str(d)[:90])
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    cfg.setdefault("reading", {})["fields"] = [{"name": "test-field-一", "active": True},
                                               {"name": "test-field-二", "active": False}]
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    st, r = req("/api/run/primer-plan", data={})
    d = r.get("data") or {}
    check("挑中标了 active 的那个领域", d.get("field") == "test-field-一", str(d)[:110])
    check("把已有文献列出来供去重", isinstance(d.get("existing"), list))
    st, r = req("/api/run/primer-queue", data={})
    d = r.get("data") or {}
    check("能排进自动任务队列", d.get("ok") and d.get("queued"), str(d)[:90])
    st, r = req("/api/run/primer-queue", data={})
    d = r.get("data") or {}
    check("同一周不会重复排", "已经排过" in str(d.get("detail", "")), str(d)[:90])
    qp = ROOT / "data" / "_claude" / "queue.json"
    qd = json.loads(qp.read_text(encoding="utf-8"))
    qd["tasks"] = [t for t in qd.get("tasks", []) if not str(t.get("tag", "")).startswith("primer-")]
    qp.write_text(json.dumps(qd, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 3. 品牌名可自定义、示例开关会存下来 ===")
    req("/api/config/merge", data={"brand": {"title": "老王的工作台", "sub": "Lab Bench"},
                                   "hide_samples": True})
    st, b = req("/api/bootstrap")
    c = b.get("config") or {}
    check("名称存下来了", (c.get("brand") or {}).get("title") == "老王的工作台", str(c.get("brand")))
    check("隐藏示例的开关存下来了", c.get("hide_samples") is True, str(c.get("hide_samples")))
    check("示例数据本身没被删", len(b["data"]["manuscripts"]) >= 1)
    req("/api/config/merge", data={"hide_samples": False})

    print("\n=== 4. 批量删除：一次删多条都要真删掉 ===")
    ids = []
    for i in range(5):
        st, r = req("/api/records/ideas", data={"title": f"批量删除测试 {i}", "kind": "idea"})
        if st == 200:
            ids.append(r["id"])
    check("先建了 5 条", len(ids) == 5, str(len(ids)))
    okn = 0
    for i in ids:
        st, _ = req("/api/records/ideas/" + urllib.parse.quote(i), method="DELETE")
        if st == 200:
            okn += 1
    check("5 条全部删掉", okn == 5, str(okn))
    st, b = req("/api/bootstrap")
    left = [x for x in b["data"]["ideas"] if str(x.get("title", "")).startswith("批量删除测试")]
    check("库里一条不剩", not left, str(len(left)))
    trash = list((ROOT / "local" / "trash" / "ideas").glob("*批量删除测试*"))
    check("都躺在回收站里，捞得回来", len(trash) == 5, str(len(trash)))
    for t in trash:
        t.unlink(missing_ok=True)

    print("\n=== 5. 表格导入：列名自动映射 + 没标题的行要跳过 ===")
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Conference Name", "CfP Close (Deadline)", "Location", "Notes"])
    w.writerow(["Test Conf A", "2026-09-01", "Paris", "备注一"])
    w.writerow(["Test Conf B", "2026-10-15", "Tokyo", ""])
    w.writerow(["", "2026-11-01", "空标题行", "应该被跳过"])
    import base64
    st, up = req("/api/table/upload", data={"name": "t10.csv",
                                            "base64": base64.b64encode(buf.getvalue().encode()).decode(),
                                            "collection": "conferences"})
    check("上传能读出表头", st == 200 and len(up.get("headers") or []) == 4, str(up)[:110])
    g = up.get("guess") or {}
    check("会议名 → 标题", g.get("Conference Name") == "title", str(g))
    check("截稿列 → deadline", g.get("CfP Close (Deadline)") == "deadline", str(g))
    check("地点列 → location", g.get("Location") == "location", str(g))
    st, im = req("/api/table/import", data={"path": up["path"], "collection": "conferences",
                                            "mapping": g, "dedup_key": "title"})
    check("导入两条、跳过一条空标题", im.get("created") == 2 and im.get("skipped") == 1, str(im)[:110])
    st, b = req("/api/bootstrap")
    got = [x for x in b["data"]["conferences"] if str(x.get("title", "")).startswith("Test Conf")]
    check("字段真的落对了位置",
          bool(got) and got[0].get("deadline") in ("2026-09-01", "2026-10-15") and got[0].get("location"),
          json.dumps(got[:1], ensure_ascii=False)[:140])
    check("没有「未命名」被造出来",
          not [x for x in b["data"]["conferences"] if "未命名" in str(x.get("title", ""))])
    st, im2 = req("/api/table/import", data={"path": up["path"], "collection": "conferences",
                                             "mapping": g, "dedup_key": "title"})
    check("重复导入是更新不是新增", im2.get("created") == 0 and im2.get("updated") == 2, str(im2)[:100])
    for x in got:
        req("/api/records/conferences/" + urllib.parse.quote(x["id"]), method="DELETE")
    for t in (ROOT / "local" / "trash" / "conferences").glob("*Test*"):
        t.unlink(missing_ok=True)

    print("\n=== 6. 箴言库 ===")
    st, r = req("/api/quotes")
    qs = r.get("quotes") or []
    # 不要断言具体条数。箴言库是用户自己的东西 —— 他可以删到只剩几十条，
    # 发出去的公开版也裁掉了没有出处的条目。写死「> 300」等于在断言
    # 「这份库是 Jay 那份」，别人拿到包第一天跑体检就红一条，
    # 然后开始怀疑是代码坏了。该测的是「读得到、结构对」，不是「有多大」。
    check(f"箴言库读得到（{len(qs)} 条）", len(qs) >= 10, str(len(qs)))
    check("每条都有正文", all(str(x.get("t", "")).strip() for x in qs))
    check("中英文都有", any(not any("一" <= c <= "鿿" for c in x["t"]) for x in qs)
          and any(any("一" <= c <= "鿿" for c in x["t"]) for x in qs))

    print("\n=== 7. 同步状态：没推上去必须看得见，日志里不能留 token ===")
    st, g = req("/api/git/status")
    check("状态接口可用", st == 200, str(g)[:80])
    if g.get("repo"):
        check("会报告有没有上游", "never_pushed" in g and "ahead" in g, str(g)[:120])
        check("远程地址里的凭据被打码", "@" not in str(g.get("remote", "")).split("://")[-1].split("/")[0]
              or "***" in str(g.get("remote", "")), str(g.get("remote"))[:90])
    else:
        check("不是仓库时也不崩", g.get("repo") is False)
    sys.path.insert(0, str(ROOT))
    import server as _srv
    m = _srv._mask("https://me:ghp_ABCdef123456@github.com/a/b.git 失败 github_pat_11ZZZaaa")
    check("URL 里的密码被抹掉", "ghp_ABCdef123456" not in m, m)
    check("裸 token 也被抹掉", "11ZZZaaa" not in m and "github_pat_***" in m, m)
    check("打码后还看得出是谁", "me:***@github.com" in m, m)
    _srv.sync_log("测试写一行 ghp_SHOULDNOTAPPEAR")
    txt = (ROOT / "local" / "sync.log").read_text(encoding="utf-8")
    check("写日志时同样打码", "ghp_SHOULDNOTAPPEAR" not in txt and "ghp_***" in txt, txt[-90:])
    check("日志尾巴读得到", any("测试写一行" in x for x in _srv.sync_tail(5)))

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    if sec_bak is not None:
        SEC.write_text(sec_bak, encoding="utf-8")
    if cfg_bak is not None:
        CFG.write_text(cfg_bak, encoding="utf-8")
    print("\n（配置已还原，测试记录已清理）")

print("\n" + "=" * 56)
print("新功能测试：" + ("全部通过 ✓" if not FAIL else f"{len(FAIL)} 项失败"))
for f in FAIL:
    print("   ✗", f)
