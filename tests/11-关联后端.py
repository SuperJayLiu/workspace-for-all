# -*- coding: utf-8 -*-
"""极端测试 11 · 跨库关联的服务端部分

双向写、去重、自关联、路径穿越、悬空清理，以及「关联要落在 frontmatter 里」——
最后这条是刻意的：关系不能只活在某个索引里，换个编辑器打开也得看得见。
"""
import json, socket, subprocess, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; PORT = 8811; BASE = f"http://127.0.0.1:{PORT}"
FAIL = []
def check(n, c, e=""):
    print(("  ✓ " + n) if c else f"  ✗ {n}  {e}")
    if not c: FAIL.append(n)
def req(path, data=None, method=None, t=20):
    if any(ord(c) > 127 for c in path):
        h, sep, qs = path.partition("?"); path = urllib.parse.quote(h, safe="/") + sep + qs
    b = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE+path, data=b, method=method or ("POST" if b is not None else "GET"),
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=t) as resp: return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode() or "{}")
        except Exception: return e.code, {}
    except Exception as e: return 0, {"error": repr(e)}
p = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT), "--no-open"], cwd=str(ROOT),
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
for _ in range(40):
    time.sleep(.35)
    if req("/api/ping", t=4)[0] == 200: break
made = []
try:
    print("\n=== 跨库关联（服务端） ===")
    _, m = req("/api/records/manuscripts", data={"title": "关联测试·稿件", "stage": "drafting"})
    _, i = req("/api/records/ideas", data={"title": "关联测试·想法", "kind": "idea"})
    _, rd = req("/api/records/reading", data={"title": "关联测试·文献", "status": "to-read"})
    made = [("manuscripts", m["id"]), ("ideas", i["id"]), ("reading", rd["id"])]
    A, B, C = f"manuscripts:{m['id']}", f"ideas:{i['id']}", f"reading:{rd['id']}"
    st, r = req("/api/link", data={"a": B, "b": A})
    check("建立关联", r.get("ok"), str(r)[:110])
    _, ma = req("/api/records/manuscripts/" + urllib.parse.quote(m["id"]))
    _, ia = req("/api/records/ideas/" + urllib.parse.quote(i["id"]))
    check("想法这头记下了", A in (ia.get("links") or []), str(ia.get("links")))
    check("稿件那头也记下了（双向）", B in (ma.get("links") or []), str(ma.get("links")))
    st, r = req("/api/link", data={"a": B, "b": A})
    _, ia2 = req("/api/records/ideas/" + urllib.parse.quote(i["id"]))
    check("重复关联不会变两条", (ia2.get("links") or []).count(A) == 1, str(ia2.get("links")))
    st, r = req("/api/link", data={"a": A, "b": A})
    check("不能关联自己", r.get("ok") is False and "自己" in r.get("detail", ""), str(r)[:90])
    st, r = req("/api/link", data={"a": B, "b": "../../etc/passwd"})
    check("路径穿越的 ref 被挡", r.get("ok") is False, str(r)[:90])
    st, r = req("/api/link", data={"a": B, "b": "manuscripts:../../x"})
    check("集合合法但 id 穿越也被挡", r.get("ok") is False, str(r)[:90])
    st, r = req("/api/link", data={"a": B, "b": "nosuchcoll:x"})
    check("不存在的集合被挡", r.get("ok") is False, str(r)[:90])
    st, r = req("/api/link", data={"a": B, "b": "manuscripts:根本没有这条"})
    check("不存在的记录说人话", r.get("ok") is False and "找不到" in r.get("detail", ""), str(r)[:90])
    req("/api/link", data={"a": B, "b": C})
    _, ib = req("/api/records/ideas/" + urllib.parse.quote(i["id"]))
    check("一条可以连多条", len(ib.get("links") or []) == 2, str(ib.get("links")))
    st, r = req("/api/link", data={"a": B, "b": A, "op": "remove"})
    _, ic = req("/api/records/ideas/" + urllib.parse.quote(i["id"]))
    _, mc = req("/api/records/manuscripts/" + urllib.parse.quote(m["id"]))
    check("解除是双向的", A not in (ic.get("links") or []) and B not in (mc.get("links") or []),
          f"{ic.get('links')} / {mc.get('links')}")
    # 删掉文献，想法那头的箭头要自己消失
    req("/api/records/reading/" + urllib.parse.quote(rd["id"]), method="DELETE")
    _, idl = req("/api/records/ideas/" + urllib.parse.quote(i["id"]))
    check("删掉一头，另一头不留悬空箭头", C not in (idl.get("links") or []), str(idl.get("links")))
    made = [x for x in made if x[0] != "reading"]
    st, r = req("/api/link/gc", data={})
    check("全库扫一遍不报错", r.get("ok") is True, str(r)[:90])
    # 关联字段要真的写进 markdown，用别的编辑器也看得见
    req("/api/link", data={"a": B, "b": A})
    txt = (ROOT / "data" / "ideas" / (i["id"] + ".md")).read_text(encoding="utf-8")
    check("关联落在 frontmatter 里（不是藏在数据库）", "links:" in txt and m["id"] in txt, txt[:160])
finally:
    for coll, rid in made:
        req(f"/api/records/{coll}/" + urllib.parse.quote(rid), method="DELETE")
    for coll, rid in made:
        for t in (ROOT / "local" / "trash" / coll).glob(f"*{rid}*"): t.unlink(missing_ok=True)
    for t in (ROOT / "local" / "trash" / "reading").glob("*关联测试*"): t.unlink(missing_ok=True)
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: p.kill()
print("\n" + ("全部通过 ✓" if not FAIL else f"{len(FAIL)} 项失败：" + "; ".join(FAIL)))

sys.exit(1 if FAIL else 0)
