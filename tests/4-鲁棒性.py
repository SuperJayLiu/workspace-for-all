# -*- coding: utf-8 -*-
"""极端测试 4 · 记录 id 注入、状态文件损坏、崩溃恢复、跨平台文件名、时间边界"""
import json, os, shutil, signal, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # 工作台目录 = tests 的上一级
PORT = 8803

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

BASE = f"http://127.0.0.1:{PORT}"
FAIL = []


def check(n, c, e=""):
    print(("  ✓ " + n) if c else f"  ✗ {n}  {e}")
    if not c:
        FAIL.append(n)


def req(path, data=None, method=None, raw=None, timeout=25):
    if any(ord(ch) > 127 for ch in path):
        h, sep, qs = path.partition("?")
        path = urllib.parse.quote(h, safe="/") + sep + qs
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    r = urllib.request.Request(BASE + path, data=body,
                               method=method or ("POST" if body is not None else "GET"),
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, repr(e)


def boot(port=PORT):
    p = subprocess.Popen([sys.executable, "server.py", "--port", str(port), "--no-open"],
                         cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(40):
        time.sleep(0.4)
        if req("/api/bootstrap", timeout=4)[0] == 200:
            return p
    return p


proc = boot()

print("\n=== 1. 记录 id 注入（会写到数据目录之外吗） ===")
canary = ROOT.parent / "PWNED_CANARY.md"
if canary.exists():
    canary.unlink()
EVIL = [
    "../../PWNED_CANARY",
    "..%2F..%2FPWNED_CANARY",
    "/tmp/PWNED_CANARY",
    "..\\..\\PWNED_CANARY",
    "....//....//PWNED_CANARY",
    "a/../../PWNED_CANARY",
    ".",
    "..",
    "",
    "con",
    "nul",
    "COM1",
    "尾部空格 ",
    "尾部点.",
    "x" * 400,
    "带\x00空字节",
]
for bad in EVIL:
    st, b = req("/api/records/ideas", data={"id": bad, "title": "注入测试"})
    ok = st in (400, 404) or (st == 200 and json.loads(b).get("id") != bad)
    check(f"id={bad[:22]!r} 被拒或被改写 → {st}", ok, b[:80])
time.sleep(0.3)
check("数据目录外没有被写入文件", not canary.exists() and not Path("/tmp/PWNED_CANARY.md").exists())
for f in list((ROOT / "data" / "ideas").glob("*")):
    if "PWNED" in f.name or f.name.startswith(("con.", "nul.", "COM1.")):
        check("数据目录内没有非法文件名", False, f.name)
        break
else:
    check("数据目录内没有非法文件名", True)

print("\n=== 2. 记录 id 注入（读取与删除） ===")
for bad in ["../../data/config", "/etc/passwd", "../../../local/secrets", ".."]:
    st, b = req("/api/records/ideas/" + urllib.parse.quote(bad, safe=""))
    check(f"GET {bad[:24]} → {st}", st == 404, b[:70])
    st, b = req("/api/records/ideas/" + urllib.parse.quote(bad, safe=""), method="DELETE")
    check(f"DEL {bad[:24]} → {st}", st == 404, b[:70])
secrets = ROOT / "local" / "secrets.json"
check("secrets.json 仍在原处未被搬走", secrets.exists())

print("\n=== 3. 记录字段注入 frontmatter ===")
nasty = {
    "title": "---\nid: 冒名顶替\n---\n正文伪造",
    "note": "值里有: 冒号 和 # 井号 和 --- 分隔线",
    "multi": "第一行\n第二行\n---\n第三行",
    "tags": ["a: b", "c\nd", "---"],
    "num_str": "007",
    "year_str": "1984",
    "bool_str": "true",
    "null_str": "null",
    "emoji": "🎉🧬𝒜",
    "body": "正文\n---\n看起来像分隔线",
}
st, b = req("/api/records/ideas", data=nasty)
check("含 YAML 毒值的记录可保存", st == 200, b[:90])
if st == 200:
    rid = json.loads(b)["id"]
    st2, b2 = req("/api/records/ideas/" + urllib.parse.quote(rid))
    got = json.loads(b2) if st2 == 200 else {}
    for k in ["title", "note", "multi", "num_str", "year_str", "bool_str", "null_str", "emoji", "body"]:
        check(f"字段 {k} 原样读回", got.get(k) == nasty[k], repr(got.get(k))[:70])
    check("tags 原样读回", got.get("tags") == nasty["tags"], repr(got.get("tags"))[:70])
    check("id 未被正文里的伪造 frontmatter 顶替", got.get("id") == rid, str(got.get("id")))
    req("/api/records/ideas/" + urllib.parse.quote(rid), method="DELETE")

print("\n=== 4. 崩溃后能否重启（半截文件、损坏状态） ===")
proc.send_signal(signal.SIGKILL)
proc.wait()
JUNK_RECORDS = ["半截文件-aaaaaa.md", "空文件-bbbbbb.md", "乱码-cccccc.md"]
broken = {
    ROOT / "data" / "config.json": '{"theme": {"mode": "dar',
    ROOT / "local" / "device.json": "not json at all",
    ROOT / "data" / "_claude" / "quota.json": '[]',
    ROOT / "data" / "_claude" / "queue.json": 'null',
    ROOT / "data" / "quotes.json": '{"broken": true}',
}
backups = {p: (p.read_text(encoding="utf-8") if p.exists() else None) for p in broken}
# 再在磁盘上留一份，万一测试进程被强杀（finally 都跑不到），也能手工拷回来
SAFETY = ROOT / "local" / "tests-safety"
SAFETY.mkdir(parents=True, exist_ok=True)
for p, orig in backups.items():
    if orig is not None:
        (SAFETY / p.name).write_text(orig, encoding="utf-8")
print(f"  （已把原始配置另存到 {SAFETY}，测试结束会自动删掉）")


def restore_everything():
    """无论中间出什么事，配置一定要还原——绝不能把用户的工作台留在损坏状态。"""
    for p, orig in backups.items():
        try:
            if orig is None:
                p.unlink(missing_ok=True)
            else:
                p.write_text(orig, encoding="utf-8")
        except Exception as e:
            print("   !! 还原失败", p, e)
    for f in JUNK_RECORDS:
        try:
            (ROOT / "data" / "ideas" / f).unlink(missing_ok=True)
        except Exception:
            pass
    ok_all = all((p.read_text(encoding="utf-8") if p.exists() else None) == orig
                 for p, orig in backups.items())
    if ok_all:
        for f in SAFETY.glob("*.json"):
            f.unlink(missing_ok=True)
        try:
            SAFETY.rmdir()
        except Exception:
            pass
    else:
        print(f"  !! 配置没能全部还原，原件还在 {SAFETY}，请手工拷回")


try:
    for p, junk in broken.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(junk, encoding="utf-8")
    (ROOT / "data" / "ideas" / "半截文件-aaaaaa.md").write_text("---\ntitle: 没闭合\n", encoding="utf-8")
    (ROOT / "data" / "ideas" / "空文件-bbbbbb.md").write_text("", encoding="utf-8")
    (ROOT / "data" / "ideas" / "乱码-cccccc.md").write_bytes(os.urandom(2000))
    proc = boot()
    st, b = req("/api/bootstrap", timeout=25)
    check("五个状态文件全坏掉仍能启动", st == 200, b[:120])
    if st == 200:
        boot_data = json.loads(b)
        check("坏记录不会拖垮整个集合", isinstance(boot_data["data"].get("ideas"), list))
        check("config 被当成对象而不是崩溃", isinstance(boot_data.get("config"), dict))
        check("quota 被当成对象", isinstance(boot_data.get("quota"), dict))
    st, b = req("/api/quotes")
    check("箴言库损坏时有兜底", st == 200 and isinstance(json.loads(b).get("quotes"), list), b[:80])
    st, b = req("/api/quotes/add", data={"t": "损坏后仍能新增"})
    check("箴言库损坏后仍能新增", st == 200, b[:80])
finally:
    try:
        proc.send_signal(signal.SIGKILL); proc.wait()
    except Exception:
        pass
    restore_everything()
proc = boot()
check("恢复原状态文件后仍正常", req("/api/bootstrap")[0] == 200)

print("\n=== 5. 冲突检测（两台设备改同一条） ===")
st, b = req("/api/records/ideas", data={"title": "冲突测试原始", "kind": "idea"})
rec = json.loads(b)
mt = rec["_mtime"]
time.sleep(2.2)   # mtime 是整秒粒度，且判定留了 1 秒容差，必须跨过 2 秒
req("/api/records/ideas", data=dict(rec, title="B 设备改的"))     # 对方先改
st2, b2 = req("/api/records/ideas", data=dict(rec, title="A 设备改的", _mtime=mt))
check("旧 _mtime 提交触发 409 而不是覆盖", st2 == 409, f"{st2} {b2[:70]}")
if st2 == 409:
    c = json.loads(b2)
    check("409 里带着两份内容供选择",
          c.get("mine", {}).get("title") == "A 设备改的" and c.get("theirs", {}).get("title") == "B 设备改的",
          json.dumps(c, ensure_ascii=False)[:100])
plain = {k: v for k, v in rec.items() if k != "_mtime"}
st3, b3 = req("/api/records/ideas", data=dict(plain, title="A 认输，覆盖保存"))
check("不带 _mtime 时正常保存（单机场景不受影响）", st3 == 200, b3[:70])
req("/api/records/ideas/" + urllib.parse.quote(rec["id"]), method="DELETE")

print("\n=== 6. 时间与周边界 ===")
sys.path.insert(0, str(ROOT))
import server as SV
from datetime import datetime, timedelta
cases = [datetime(2026, 1, 1), datetime(2025, 12, 31), datetime(2026, 12, 31),
         datetime(2024, 2, 29), datetime(2026, 3, 29, 2, 30), datetime(2026, 7, 29)]
ok = True
for d in cases:
    try:
        wk = SV.week_key(d)
        datetime.fromisoformat(wk)
    except Exception as e:
        ok = False
        print("     week_key 失败", d, e)
check("跨年/闰日/夏令时的周键都合法", ok)
mon = [SV.week_key(datetime(2026, 1, 1) + timedelta(days=i)) for i in range(21)]
check("同一周内 week_key 一致（每 7 天一变）", len(set(mon)) == 4, str(sorted(set(mon))))

print("\n=== 7. 删除进回收站，可人工找回 ===")
st, b = req("/api/records/ideas", data={"title": "待删除的重要想法", "body": "别真删了"})
rid = json.loads(b)["id"]
req("/api/records/ideas/" + urllib.parse.quote(rid), method="DELETE")
trash = list((ROOT / "local" / "trash" / "ideas").glob(f"{rid}*"))
check("删除的记录进了 local/trash", len(trash) == 1, str(trash))
if trash:
    check("回收站里的内容完整", "别真删了" in trash[0].read_text(encoding="utf-8"))
    trash[0].unlink()

print("\n=== 8. 连续重启 5 次不丢数据 ===")
st, b = req("/api/records/ideas", data={"title": "重启存活测试", "body": "x" * 5000})
rid = json.loads(b)["id"]
survived = True
for i in range(5):
    proc.send_signal(signal.SIGKILL); proc.wait()
    proc = boot()
    st, b = req("/api/records/ideas/" + urllib.parse.quote(rid))
    if st != 200 or len(json.loads(b).get("body", "")) != 5000:
        survived = False
        print("     第", i + 1, "次重启后异常", st)
        break
check("5 次强杀重启后记录仍完整", survived)
req("/api/records/ideas/" + urllib.parse.quote(rid), method="DELETE")
for t in (ROOT / "local" / "trash" / "ideas").glob(f"{rid}*"):
    t.unlink()

print("\n=== 9. 收尾：注入测试留下的文件名必须是干净的 ===")
sys.path.insert(0, str(ROOT))
import server as SV2
leftovers = [f for f in (ROOT / "data" / "ideas").glob("*.md")
             if "注入测试" in f.read_text(encoding="utf-8", errors="ignore")[:200]]
bad_names = [f.name for f in leftovers if SV2.safe_rid(f.stem) != f.stem]
check("留下的文件名跨平台安全（无尾部空格/点、无保留名）", not bad_names, str(bad_names))
for f in leftovers:
    f.unlink()
for t in (ROOT / "local" / "trash" / "ideas").glob("*"):
    if "注入测试" in t.read_text(encoding="utf-8", errors="ignore")[:200]:
        t.unlink()

proc.send_signal(signal.SIGKILL)
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
print("\n" + "=" * 56)
print("鲁棒性极端测试：" + ("全部通过 ✓" if not FAIL else f"{len(FAIL)} 项失败"))
for f in FAIL:
    print("   ✗", f)
