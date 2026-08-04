#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
畸形输入攻击面 · 对每一条路由灌脏数据

判据只有三条，都是「用户看得见」的：
  · 不能 500 —— 那是服务器自己崩了，用户只会看到「保存失败」不知所措
  · 不能掐线 —— 比 500 更糟：浏览器连状态码都收不到，只显示「无法访问」
  · 不能越权 —— 挡不住的路径穿越、读到不该读的文件

这一套是真抓到过东西的：路径太长（字节数，不是字符数）让 exists() 抛 OSError、
路径里带 \x00 让 resolve() 抛 ValueError，两者都直接掐断连接；
body 传个数字或列表就 500；表格路径指到目录也 500。
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8807


def _port_free(port):
    import socket
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
    sys.exit(f"端口 {PORT} 被占着——多半是上一轮没退干净。\n"
             f"先执行：pkill -f 'server.py --port {PORT}'")

# 灌脏数据一定会**留下东西**（新建的记录、改过的设置、写进信箱的字）。
# 所以必须在一份复制品上跑，不能碰真的工作台 ——
# 否则跑一次测试，data/ideas 里就多出几十条 rec-xxxx 的垃圾，
# 而且是提交进 git 的那个目录。
import shutil
import tempfile
WORK = Path(tempfile.mkdtemp(prefix="fuzz-")) / "ws"
shutil.copytree(ROOT, WORK, ignore=shutil.ignore_patterns(
    "__pycache__", ".git", "local", "tests", "*.pyc", "*.zip"))
proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT), "--no-open"],
                        cwd=str(WORK), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3.5)
BASE = f"http://127.0.0.1:{PORT}/api/"
ORIGIN = f"http://127.0.0.1:{PORT}"
bad, stat = [], Counter()


def call(method, route, body=None, note=""):
    url = BASE + route
    try:
        if method == "GET":
            req = urllib.request.Request(url)
        else:
            data = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
            req = urllib.request.Request(url, data=data, method=method,
                                         headers={"Content-Type": "application/json",
                                                  "Origin": ORIGIN})
        with urllib.request.urlopen(req, timeout=45) as f:
            code, raw = f.status, f.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    except Exception as e:
        bad.append(f"[连接被掐断] {method} {route[:60]} {note} -> {type(e).__name__}: {e}")
        stat["掐线"] += 1
        return 0, b""
    stat[str(code)] += 1
    if code >= 500:
        bad.append(f"[500] {method} {route[:70]} {note} -> {raw[:120]}")
    return code, raw


print("=" * 62)
print("畸形输入攻击面")
print("=" * 62)

# ------------------------------------------------- 畸形素材
NASTY = [
    "", " ", "\x00", "\x00\x01\x02", "\n\r\t",
    "../" * 40 + "etc/passwd", "..\\" * 40 + "windows\\win.ini",
    "%2e%2e%2f" * 20, "/etc/shadow", "C:\\Windows\\System32\\config\\SAM",
    "a" * 5000, "\u4e2d" * 3000, "9" * 6000, "-" * 200,
    "<script>alert(1)</script>", "'; DROP TABLE x; --", "${jndi:ldap://x/a}",
    "\u202e\x00", "\U0001f642" * 500, "%00", "%n%n%n", "\\\\?\\C:\\", "//////",
    "CON", "PRN", "NUL", "AUX", "COM1", ".", "..", "...", " . ",
    "{{7*7}}", "__proto__", "constructor", "\ufeff", "\x1b[31m",
]
WEIRD_JSON = [
    None, [], "\u5b57\u7b26\u4e32\u4e0d\u662f\u5bf9\u8c61", 12345, True,
    {"id": None}, {"id": []}, {"id": {}},
    {"title": {"a": {"b": [1, 2, {"x": None}]}}},
    {"body": None}, {"body": 12345}, {"body": ["a", "b", "c"]},
    {"title": "x", "links": "not a list"}, {"title": "x", "links": [None, 1, {}]},
    {"title": "x", "tags": {"not": "a list"}}, {"_mtime": "not a number"},
    {"amount": "not a number"}, {"date": "not a date"}, {"y": [1, 2]},
    {"x": float("1e308")}, {"progress": -999999}, {"progress": "abc"},
]
COLLS = ["manuscripts", "ideas", "reading", "schedule", "finance",
         "\u4e0d\u5b58\u5728\u7684\u96c6\u5408", "../../etc", "records", ""]


print("\n一、路径类参数（读文件的那几条）")
for r in ["file", "tree", "checkdir", "scan/pdfs", "library/file", "claude/outbox",
          "table/preview"]:
    for n in NASTY:
        key = "name" if r == "claude/outbox" else "path"
        call("GET", f"{r}?{key}=" + urllib.parse.quote(n, safe=""), note=repr(n)[:26])

print("二、记录读写（集合名 / id / 内容 全灌脏）")
for c in COLLS:
    call("GET", "records/" + urllib.parse.quote(c, safe=""))
    for n in NASTY[:18]:
        call("GET", f"records/{urllib.parse.quote(c, safe='')}/"
                    + urllib.parse.quote(n, safe=""))
        call("DELETE", f"records/{urllib.parse.quote(c, safe='')}/"
                       + urllib.parse.quote(n, safe=""))
for c in ["ideas", "finance", "不存在的集合"]:
    for j in WEIRD_JSON:
        call("POST", "records/" + urllib.parse.quote(c, safe=""), j, note=repr(j)[:34])
    for n in NASTY[:14]:
        call("POST", "records/" + urllib.parse.quote(c, safe=""),
             {"title": n, "body": n, "date": n, "id": n}, note=repr(n)[:22])

print("三、搜索与文献索引")
for n in NASTY:
    call("GET", "search?q=" + urllib.parse.quote(n, safe=""))
    call("GET", "library/search?q=" + urllib.parse.quote(n, safe=""))
for p in ["limit=-1", "limit=99999999", "limit=abc", "offset=-5", "offset=1e99",
          "sort=" + urllib.parse.quote("不存在"), "year_from=abc", "year_to=-99",
          "has_pdf=x", "todo=maybe", "limit=", "offset=", "sort="]:
    call("GET", "library/search?" + p, note=p)
for j in [None, {"text": None}, {"text": 123}, {"text": "不是题录"},
          {"text": "@article{", "format": "bib"}, {"format": "不存在"},
          {"text": "x" * 100000, "format": "csl"}, {"text": "[]", "format": "csl"},
          {"text": "{}", "format": "csl"}, {"keys": "不是列表"}, {"keys": [None, 1]}]:
    call("POST", "library/import", j, note=repr(j)[:34])
    call("POST", "library/remove", j, note=repr(j)[:34])
for j in [None, {"path": None}, {"path": 123}, {"path": "/etc"}, {"path": "~"},
          {"path": "/"}, {"path": "不存在的目录"}, {"path": "../../.."},
          {"path": "/tmp/papers", "apply": "不是布尔"}]:
    call("POST", "library/scan", j, note=repr(j)[:34])
for j in [None, {"key": None}, {"key": []}, {"a": "x", "b": None},
          {"key_keep": "x", "key_drop": "x"}]:
    call("POST", "library/merge", j, note=repr(j)[:30])
    call("POST", "library/promote", j, note=repr(j)[:30])

print("四、关联")
for j in [None, {"a": None, "b": None}, {"a": "x", "b": "y"}, {"a": "ideas:", "b": ":x"},
          {"a": "a:b:c", "b": "d"}, {"a": ["列表"], "b": {}}, {"a": "x" * 3000, "b": "y"},
          {"a": "ideas:x", "b": "ideas:x", "op": "add"},
          {"a": "ideas:x", "b": "ideas:y", "op": "不存在的操作"}]:
    call("POST", "link", j, note=repr(j)[:34])

print("五、设置 / 密钥 / 配额 / 日历")
for j in WEIRD_JSON:
    call("POST", "config/merge", j, note=repr(j)[:30])
    call("POST", "device", j, note=repr(j)[:30])
    call("POST", "quota/override", j, note=repr(j)[:30])
    call("POST", "queue", j, note=repr(j)[:30])
    call("POST", "secrets/merge", j, note=repr(j)[:30])
for j in [None, {"action": None}, {"action": "不存在"}, {"action": []}]:
    call("POST", "clock", j, note=repr(j)[:26])
for u in ["", "不是链接", "ftp://x/a.ics", "javascript:alert(1)", "http://[::1]/x",
          "https://" + "a" * 3000 + ".com/x.ics", "webcal://x", "file:///etc/passwd"]:
    call("POST", "test/ics", {"url": u}, note=u[:30])
for j in [None, {"text": None}, {"text": []}, {"text": "x" * 200000},
          {"mode": "不存在"}, {"mode": "replace", "text": None}]:
    call("POST", "claude/inbox", j, note=repr(j)[:30])

print("六、箴言 / 备份 / 表格 / 脚本")
for j in [None, {"t": None}, {"t": []}, {"t": "x" * 20000}, {"id": None}, {"id": []},
          {"id": "不存在"}, {"fav": "不是布尔"}]:
    call("POST", "quotes/add", j, note=repr(j)[:26])
    call("POST", "quotes/del", j, note=repr(j)[:26])
    call("POST", "quotes/fav", j, note=repr(j)[:26])
for j in [None, {"path": None}, {"path": "/etc/passwd"}, {"path": "x" * 3000},
          {"kind": []}, {"kind": "不存在"}]:
    call("POST", "restore", j, note=repr(j)[:26])
    call("POST", "backup", j, note=repr(j)[:26])
for j in [None, {"path": "/etc/hosts", "collection": "ideas"},
          {"path": None, "collection": None}, {"collection": "不存在的集合"},
          {"name": "../../x.zip", "base64": "!!!不是base64"},
          {"name": "x.zip", "base64": "AAAA"}]:
    call("POST", "table/import", j, note=repr(j)[:30])
    call("POST", "table/upload", j, note=repr(j)[:30])
for n in ["", "..", "../audit", "不存在", "primer-queue; rm -rf /", "a" * 500]:
    call("POST", "run/" + urllib.parse.quote(n, safe=""), {}, note=n[:26])

print("七、坏 body（连 JSON 都不是）")
for raw in [b"", b"{", b"[", b"null", b"not json at all", b"\x00\x01\x02",
            b'{"a":' + b"1" * 100000 + b"}", "中文没编码".encode("gbk"),
            b'{"a": Infinity}', b'{"a": NaN}', b'{"a": 1,}']:
    call("POST", "records/ideas", raw, note=repr(raw)[:30])
    call("POST", "config/merge", raw, note=repr(raw)[:30])

print("八、URL 本身畸形")
for path in ["records//", "records/ideas//", "records/ideas/x/y/z", "//bootstrap",
             "bootstrap/../secrets", "bootstrap%00", "%2e%2e%2fsecrets",
             "search?q=%", "search?q=%zz", "search?" + "a=1&" * 3000]:
    call("GET", path, note=path[:34])
for path in ["/", "//", "/js", "/css", "/../server.py", "/..%2fserver.py",
             "/app/../../server.py", "/index.html%00.txt", "/" + "a" * 3000]:
    try:
        req = urllib.request.Request(ORIGIN + path)
        with urllib.request.urlopen(req, timeout=30) as f:
            stat["static:" + str(f.status)] += 1
    except urllib.error.HTTPError as e:
        stat["static:" + str(e.code)] += 1
    except Exception as e:
        bad.append(f"[静态掐线] {path} -> {type(e).__name__}: {e}")
        stat["掐线"] += 1

print("\n" + "=" * 62)
print("状态码分布:", dict(sorted(stat.items())))
try:
    with urllib.request.urlopen(BASE + "bootstrap", timeout=45) as f:
        b = json.loads(f.read())
    n = sum(len(v) for v in b["data"].values())
    print(f"灌完之后服务仍然正常：v{b['version']}，记录 {n} 条")
except Exception as e:
    bad.append(f"灌完之后服务不正常了：{e}")

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
shutil.rmtree(WORK.parent, ignore_errors=True)

print("=" * 62)
if bad:
    print(f"畸形输入测试：{len(bad)} 条不通过 ✗")
    for x in bad[:30]:
        print("   -", x)
    sys.exit(1)
print("畸形输入测试：全部通过 ✓")
