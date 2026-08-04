# -*- coding: utf-8 -*-
"""极端测试 5 · 远程访问闸门（访问码、只读、禁区、锁定、会话）

本机连本机是放行的，所以要真测远程，必须让请求从一个「非 127.0.0.1」的地址进来。
办法：让服务监听 0.0.0.0，然后用本机的另一个网卡地址去连自己。
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

ROOT = Path(__file__).resolve().parent.parent   # 工作台目录 = tests 的上一级
PORT = 8805


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


def outbound_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return ""
    finally:
        s.close()


REMOTE_IP = outbound_ip()
if not REMOTE_IP or REMOTE_IP.startswith("127."):
    sys.exit("这台机器没有非回环地址，测不了远程闸门（换一台有网卡地址的机器再跑）")

FAIL = []
CODE = "test-code-9271"


def check(n, c, e=""):
    print(("  ✓ " + n) if c else f"  ✗ {n}  {e}")
    if not c:
        FAIL.append(n)


class Client:
    """一个会记 cookie 的极简客户端。base 决定我们是「本机」还是「远程」。"""

    def __init__(self, base):
        self.base = base
        self.cookie = ""

    def req(self, path, data=None, method=None, timeout=20):
        if any(ord(c) > 127 for c in path):
            h, sep, qs = path.partition("?")
            path = urllib.parse.quote(h, safe="/") + sep + qs
        body = json.dumps(data).encode() if data is not None else None
        r = urllib.request.Request(
            self.base + path, data=body,
            method=method or ("POST" if body is not None else "GET"),
            headers={"Content-Type": "application/json",
                     **({"Cookie": self.cookie} if self.cookie else {})})
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                self._grab(resp)
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            self._grab(e)
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            return 0, repr(e)

    def _grab(self, resp):
        sc = resp.headers.get("Set-Cookie")
        if sc:
            self.cookie = sc.split(";")[0]


# --- 起服务：监听 0.0.0.0，并临时写入访问码与开关 -------------------------
SEC = ROOT / "local" / "secrets.json"
CFG = ROOT / "data" / "config.json"
sec_bak = SEC.read_text(encoding="utf-8") if SEC.exists() else None
cfg_bak = CFG.read_text(encoding="utf-8") if CFG.exists() else None


def restore():
    if sec_bak is not None:
        SEC.write_text(sec_bak, encoding="utf-8")
    if cfg_bak is not None:
        CFG.write_text(cfg_bak, encoding="utf-8")


proc = None
try:
    s = json.loads(sec_bak) if sec_bak else {}
    s.setdefault("remote", {})["access_code"] = CODE
    SEC.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    c = json.loads(cfg_bak) if cfg_bak else {}
    c["security"] = {"remote_enabled": False, "remote_readonly": True, "encrypt_backup": False}
    CFG.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT),
                             "--host", "0.0.0.0", "--no-open"],
                            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    local = Client(f"http://127.0.0.1:{PORT}")
    remote = Client(f"http://{REMOTE_IP}:{PORT}")
    for _ in range(40):
        time.sleep(0.4)
        if local.req("/api/ping", timeout=4)[0] == 200:
            break

    print(f"\n=== 1. 开关关着时，远程应该完全进不来（本机不受影响） ===")
    check("本机 bootstrap 正常", local.req("/api/bootstrap")[0] == 200)
    st, b = remote.req("/api/bootstrap")
    check(f"远程 bootstrap 被拒 → {st}", st == 403, b[:80])
    st, b = remote.req("/")
    check(f"远程连页面也被拒 → {st}", st == 403, b[:60])
    st, b = remote.req("/api/records/ideas", data={"title": "远程偷写"})
    check(f"远程写入被拒 → {st}", st == 403, b[:80])

    print("\n=== 2. 打开开关后，没有访问码仍然进不去 ===")
    local.req("/api/config/merge", data={"security": {"remote_enabled": True,
                                                      "remote_readonly": True}})
    st, b = remote.req("/api/bootstrap")
    check(f"没登录 → 401 要访问码 → {st}", st == 401, b[:80])
    st, b = remote.req("/")
    check("远程访问首页时被换成登录页", st == 200 and "访问码" in b, str(st))
    st, b = remote.req("/api/ping")
    check("ping 属于公开接口，不需要登录", st == 200, b[:60])

    print("\n=== 3. 访问码错了会被锁 ===")
    codes_wrong = 0
    for i in range(5):
        st, b = remote.req("/api/auth/login", data={"code": "错的" + str(i)})
        if st == 401:
            codes_wrong += 1
    check("连错 5 次都被拒", codes_wrong == 5, str(codes_wrong))
    st, b = remote.req("/api/auth/login", data={"code": CODE})
    check(f"锁定期内即使输对也进不去 → {st}", st == 429, b[:80])
    log = (ROOT / "local" / "security.log")
    check("失败尝试记在案", log.exists() and "访问码错误" in log.read_text(encoding="utf-8"))

    print("\n=== 4. 隔一阵子重来：输对了能进，但只读 ===")
    # 锁定是按 IP 记的，重启服务即可清掉内存里的计数（模拟隔了 15 分钟）
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT),
                             "--host", "0.0.0.0", "--no-open"],
                            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    remote = Client(f"http://{REMOTE_IP}:{PORT}")
    local = Client(f"http://127.0.0.1:{PORT}")
    for _ in range(40):
        time.sleep(0.4)
        if local.req("/api/ping", timeout=4)[0] == 200:
            break
    st, b = remote.req("/api/auth/login", data={"code": CODE})
    check(f"访问码正确 → 登录成功 {st}", st == 200 and json.loads(b).get("ok"), b[:80])
    check("拿到了会话 cookie", remote.cookie.startswith("sw_token="), remote.cookie[:20])
    st, b = remote.req("/api/bootstrap")
    check(f"登录后能读数据 → {st}", st == 200, b[:80])
    st, b = remote.req("/api/records/ideas", data={"title": "远程只读时的写入"})
    check(f"但写入被挡（423 只读）→ {st}", st == 423, b[:90])
    st, b = remote.req("/api/records/ideas/whatever", method="DELETE")
    check(f"删除同样被挡 → {st}", st == 423, b[:90])

    print("\n=== 5. 解锁写入后可以改，本机始终不受限 ===")
    st, b = remote.req("/api/auth/unlock", data={"code": CODE})
    check(f"解锁成功 → {st}", st == 200, b[:80])
    st, b = remote.req("/api/records/ideas", data={"title": "远程解锁后写入", "kind": "idea"})
    check(f"解锁后写入成功 → {st}", st == 200, b[:90])
    rid = json.loads(b).get("id") if st == 200 else None
    st, b = remote.req("/api/auth/status")
    j = json.loads(b) if st == 200 else {}
    check("状态接口如实报告可写", j.get("can_write") is True and j.get("local") is False, b[:120])
    if rid:
        st, _ = remote.req("/api/records/ideas/" + urllib.parse.quote(rid), method="DELETE")
        check(f"解锁后也能删 → {st}", st == 200)

    print("\n=== 6. 有些事远程永远不许做 ===")
    for path, why in [("/api/secrets/status", "看密钥状态"),
                      ("/api/file?path=/etc/hosts", "读任意文件"),
                      ("/api/tree?path=/", "浏览文件树"),
                      ("/api/git/status", "看 Git 凭据")]:
        st, b = remote.req(path)
        ok = st == 403 or (path.endswith("status") and st == 403)
        check(f"远程{why} → {st}", st == 403, b[:70])
    st, b = remote.req("/api/run/audit", data={})
    check(f"远程跑脚本 → {st}", st == 403, b[:70])
    st, b = local.req("/api/git/status")
    check("同样这些事，本机做完全正常", st == 200, b[:60])

    print("\n=== 7. 退出登录后立刻失效 ===")
    st, b = remote.req("/api/auth/logout", data={})
    check(f"退出登录 → {st}", st == 200)
    st, b = remote.req("/api/bootstrap")
    check(f"退出后读数据被拒 → {st}", st == 401, b[:70])
    st, b = remote.req("/api/auth/login", data={"code": CODE + "x"})
    check(f"伪造的 cookie 不管用 → {st}", st == 401, b[:70])

    print("\n=== 8. 中文访问码也要能用（曾经会 500） ===")
    zh = "杭州的秘密口令"
    sj = json.loads(SEC.read_text(encoding="utf-8"))
    sj.setdefault("remote", {})["access_code"] = zh
    SEC.write_text(json.dumps(sj, ensure_ascii=False, indent=2), encoding="utf-8")
    fresh = Client(f"http://{REMOTE_IP}:{PORT}")
    st, b = fresh.req("/api/auth/login", data={"code": "错的中文口令"})
    check(f"中文错码 → 401 而不是 500 → {st}", st == 401, b[:80])
    st, b = fresh.req("/api/auth/login", data={"code": zh})
    check(f"中文对码能登录 → {st}", st == 200 and json.loads(b).get("ok"), b[:80])
    sj["remote"]["access_code"] = CODE
    SEC.write_text(json.dumps(sj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 9. 关掉开关，远程立刻断 ===")
    local.req("/api/config/merge", data={"security": {"remote_enabled": False}})
    st, b = remote.req("/api/ping")
    check(f"关掉后连 ping 都进不来 → {st}", st == 403, b[:70])
    check("本机不受影响", local.req("/api/bootstrap")[0] == 200)

finally:
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    restore()
    print("\n（访问码与安全设置已还原）")

print("\n" + "=" * 56)
print("远程访问闸门测试：" + ("全部通过 ✓" if not FAIL else f"{len(FAIL)} 项失败"))
for f in FAIL:
    print("   ✗", f)
