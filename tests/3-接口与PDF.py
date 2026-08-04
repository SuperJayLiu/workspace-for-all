# -*- coding: utf-8 -*-
"""极端测试 · HTTP 层与 PDF"""
import json, os, shutil, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # 工作台目录 = tests 的上一级
PORT = 8801

def _port_free(port):
    """端口被上一轮没关干净的服务占着，测试就会打到旧代码上，结论全是假的。
    用「能不能连上」判断，而不是「能不能 bind」——刚关掉的端口还在 TIME_WAIT，
    bind 会失败但其实没人在听。"""
    import socket
    s = socket.socket()
    s.settimeout(0.8)
    try:
        s.connect(("127.0.0.1", port))
        return False          # 连得上 = 有人在听
    except OSError:
        return True
    finally:
        s.close()


if not _port_free(PORT):
    sys.exit(f"端口 {PORT} 已被占用——很可能是上一轮测试的服务没退干净。\n"
             f"先执行：pkill -f 'server.py --port {PORT}'，再重跑本脚本。")

proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT), "--no-open"],
                        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
time.sleep(3)
BASE = f"http://127.0.0.1:{PORT}"
FAIL = []


def check(n, c, e=""):
    if c:
        print(f"  ✓ {n}")
    else:
        FAIL.append(n)
        print(f"  ✗ {n}  {e}")


def req(path, data=None, method=None, raw=None, headers=None, timeout=25):
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    # 浏览器会自动百分号编码；urllib 不会，非 ASCII 路径要自己编
    if any(ord(c) > 127 for c in path):
        head, sep, qs = path.partition("?")
        path = urllib.parse.quote(head, safe="/") + sep + qs
    r = urllib.request.Request(BASE + path, data=body, method=method or ("POST" if body is not None else "GET"),
                               headers=headers or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


print("\n=== 1. 畸形请求 ===")
deep = json.dumps(eval("{'a':" * 60 + "1" + "}" * 60)).encode()
before = json.loads(req("/api/bootstrap")[1])["data"]["ideas"]
for name, kw, want in [
    ("非 JSON 正文", dict(path="/api/records/ideas", raw=b"not json at all"), {400}),
    ("空正文 POST", dict(path="/api/records/ideas", raw=b""), {400}),
    ("JSON 是数组", dict(path="/api/records/ideas", raw=b"[1,2,3]"), {400}),
    ("JSON 是字符串", dict(path="/api/records/ideas", raw=b'"hello"'), {400}),
    ("超深嵌套", dict(path="/api/config/merge", raw=deep), {200, 400}),
    ("未知集合", dict(path="/api/records/不存在的集合", data={"title": "x"}), {404}),
    ("未知路由", dict(path="/api/completely/unknown"), {404}),
    ("GET 记录不存在", dict(path="/api/records/ideas/根本没有这个id"), {404}),
    ("删除不存在", dict(path="/api/records/ideas/nope", method="DELETE"), {404}),
    ("run 未知任务", dict(path="/api/run/rm-rf", data={}), {404}),
    ("超长 URL 参数", dict(path="/api/tree?path=" + "a" * 8000), {200, 400, 403}),
    ("控制字符路径", dict(path="/api/file?path=%00%01%02"), {400, 403}),
]:
    st, body = req(**kw)
    check(f"{name} → HTTP {st}", st in want, f"期望 {sorted(want)}，body={body[:70]}")
after = json.loads(req("/api/bootstrap")[1])["data"]["ideas"]
check("畸形请求没有污染数据库", len(after) == len(before), f"{len(before)} → {len(after)}")

print("\n=== 2. 大负载 ===")
big = {"title": "大", "body": "字" * 400000}
t0 = time.time(); st, body = req("/api/records/ideas", data=big); dt = time.time() - t0
check(f"400KB 正文 → {st} ({dt:.1f}s)", st == 200 and dt < 20)
try:
    rid = json.loads(body)["id"]
    st2, b2 = req(f"/api/records/ideas/{rid}")
    ln = len(json.loads(b2).get("body", ""))
    check("大记录读回内容完整", st2 == 200 and ln == 400000, str(ln))
    req(f"/api/records/ideas/{rid}", method="DELETE")
except Exception as e:
    check("大记录读回内容完整", False, str(e)[:60])
st, _ = req("/api/table/upload", data={"name": "big.csv", "base64": ""})
check("空上传被处理", st == 200)

print("\n=== 3. 并发 ===")
results = []
def hammer():
    st, _ = req("/api/bootstrap", timeout=40)
    results.append(st)
ths = [threading.Thread(target=hammer) for _ in range(30)]
t0 = time.time(); [t.start() for t in ths]; [t.join() for t in ths]
check(f"30 并发 bootstrap（{time.time()-t0:.1f}s）", all(s == 200 for s in results),
      f"{results.count(200)}/30")
w = []
def cwrite(i):
    st, b = req("/api/records/ideas", data={"title": f"并发 HTTP {i}", "kind": "idea"})
    w.append((st, json.loads(b)["id"] if st == 200 else None))
ths = [threading.Thread(target=cwrite, args=(i,)) for i in range(25)]
[t.start() for t in ths]; [t.join() for t in ths]
ids = [x[1] for x in w if x[1]]
check("25 并发写入 id 不重复", len(ids) == len(set(ids)) == 25, f"{len(ids)}/{len(set(ids))}")
for i in ids:
    req(f"/api/records/ideas/{i}", method="DELETE")

print("\n=== 4. 目录穿越（HTTP 层） ===")
for atk in ["/api/file?path=/etc/passwd",
            "/api/file?path=%2Fetc%2Fpasswd",
            "/api/file?path=..%2F..%2F..%2Fetc%2Fpasswd",
            "/api/file?path=%252e%252e%252f%252e%252e%252fetc%252fpasswd",
            "/api/tree?path=/etc",
            "/api/tree?path=/",
            "/api/scan/pdfs?path=/etc"]:
    st, body = req(atk)
    leaked = "root:x:" in body or "/bin/bash" in body
    check(f"拦截 {atk[:50]}", not leaked, "泄漏!" if leaked else "")
for atk in ["/../server.py", "/..%2Fserver.py", "/js/../../server.py", "/%2e%2e/services.py"]:
    st, body = req(atk)
    leaked = "import argparse" in body or "def main(" in body
    check(f"静态穿越 {atk[:28]}", not leaked, "泄漏!" if leaked else f"HTTP {st}")

print("\n=== 5. 密钥不泄漏 ===")
req("/api/secrets/merge", data={"github": {"token": "SUPER_SECRET_TOKEN_XYZ"},
                                "push": {"dingtalk_secret": "SECRETSIGN123"}})
for path in ["/api/bootstrap", "/api/secrets/status", "/api/git/status", "/api/quota"]:
    st, body = req(path)
    check(f"{path} 不含明文密钥",
          "SUPER_SECRET_TOKEN_XYZ" not in body and "SECRETSIGN123" not in body)
req("/api/secrets/merge", data={"github": {}, "push": {}})

print("\n=== 6. PDF 极端输入 ===")
sys.path.insert(0, str(ROOT))
import pdfmeta
tmp = Path("/tmp/pdfedge"); tmp.mkdir(exist_ok=True)
(tmp / "empty.pdf").write_bytes(b"")
(tmp / "notpdf.pdf").write_bytes(b"I am definitely not a PDF" * 100)
(tmp / "truncated.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Title (Cut off")
(tmp / "hugehdr.pdf").write_bytes(b"%PDF-1.4\n/Title (" + b"A" * 200000 + b")\n")
(tmp / "badstream.pdf").write_bytes(b"%PDF-1.4\nstream\n" + os.urandom(50000) + b"\nendstream\n")
(tmp / "nullbytes.pdf").write_bytes(b"%PDF-1.4\n" + bytes(10000))
t0 = time.time()
r = pdfmeta.scan_folder(str(tmp))
dt = time.time() - t0
check(f"6 个畸形 PDF 不崩溃（{dt:.1f}s）", r["ok"] and dt < 30, str(r)[:80])
titles = [i.get("title", "") for i in r["items"]]
check("标题长度被截断", all(len(t) <= 260 for t in titles), str(max((len(t) for t in titles), default=0)))
check("非 PDF 被识别出来", any(not i.get("ok") for i in r["items"]))
shutil.rmtree(tmp, ignore_errors=True)

print("\n=== 7. 备份 / 恢复往返 ===")
st, b = req("/api/backup", data={"kind": "manual"})
snap = json.loads(b)
check("手动备份成功", snap.get("ok"), str(snap)[:80])
st, b = req("/api/backups")
check("备份列表可读", st == 200 and isinstance(json.loads(b), list))
if snap.get("ok"):
    st, b = req("/api/restore", data={"path": snap["path"]})
    check("恢复成功", json.loads(b).get("ok"), b[:110])
    st, b = req("/api/bootstrap")
    check("恢复后数据完整", st == 200 and len(json.loads(b)["data"]["manuscripts"]) >= 2)
    st, b = req("/api/restore", data={"path": "/etc/passwd"})
    check("恢复非备份文件被拒", not json.loads(b).get("ok"))

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
print("\n" + "=" * 56)
print("HTTP/PDF 极端测试：" + ("全部通过 ✓" if not FAIL else f"{len(FAIL)} 项失败"))
for f in FAIL:
    print("   ✗", f)
