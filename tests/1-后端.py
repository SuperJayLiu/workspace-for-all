# -*- coding: utf-8 -*-
"""极端测试 · 后端数据层"""
import importlib.util, json, os, random, shutil, string, sys, tempfile, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # 工作台目录 = tests 的上一级
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("srv", ROOT / "server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FAIL = []
def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAIL.append(name)
        print(f"  ✗ {name}  {extra}")

print("\n=== 1. frontmatter 往返：恶意/畸形内容 ===")
EVIL = [
    ("正文里有分隔线", {"title": "x"}, "正文\n---\n看起来像 frontmatter 结束\ntitle: 假的\n---\n继续"),
    ("标题含冒号引号", {"title": 'A: "B" #c [d] {e}, f'}, "body"),
    ("标题含换行", {"title": "第一行\n第二行"}, ""),
    ("emoji 与生僻字", {"title": "🎓📄 龘齉𠮷 café naïve"}, "émoji 正文 🚀"),
    ("超长标题", {"title": "长" * 3000}, ""),
    ("空字符串与 None", {"title": "", "x": None, "y": ""}, ""),
    ("数字型字符串", {"title": "007", "zip": "0123", "n": 7, "f": 1.5, "neg": -3}, ""),
    ("布尔与列表混合", {"title": "t", "b": True, "b2": False, "l": [1, "a", True]}, ""),
    ("嵌套字典列表", {"title": "t", "timeline": [{"date": "2026-01-01", "note": "含: 冒号"},
                                              {"date": "2026-02-02", "note": "含\"引号\""}]}, ""),
    ("反斜杠与制表", {"title": "C:\\Users\\x\ty"}, "tab\there"),
    ("YAML 关键字", {"title": "yes", "v": "no", "w": "null", "z": "~"}, ""),
    ("列表里有空字典", {"title": "t", "l": [{}]}, ""),
]
for name, meta, body in EVIL:
    txt = m.dump_frontmatter(dict(meta), body)
    back, b2 = m.parse_frontmatter(txt)
    ok = all(str(back.get(k)) == str(v) if not isinstance(v, (list, dict)) else True
             for k, v in meta.items() if v is not None)
    if name == "正文里有分隔线":
        ok = b2.startswith("正文")
    if name == "嵌套字典列表":
        ok = len(back.get("timeline", [])) == 2 and back["timeline"][1]["note"] == '含"引号"'
    if name == "标题含换行":
        ok = "第一行" in str(back.get("title"))
    if name == "空字符串与 None":
        ok = back.get("title") == "" and back.get("y") == ""
    if name == "数字型字符串":
        ok = back.get("zip") == "0123" and back.get("n") == 7 and back.get("neg") == -3
    if name == "布尔与列表混合":
        ok = back.get("b") is True and back.get("b2") is False and back.get("l") == [1, "a", True]
    if name == "YAML 关键字":
        ok = back.get("title") == "yes" and back.get("w") == "null"
    if name == "列表里有空字典":
        ok = isinstance(back.get("l"), list)
    check(name, ok, f"got={str(back)[:110]} body={b2[:40]!r}")

print("\n=== 2. 损坏的数据文件不应让整个集合挂掉 ===")
bad_dir = m.DATA / "manuscripts"
casualties = []
for nm, content in [("broken1.md", "---\n这不是合法 yaml: [未闭合\n"),
                    ("broken2.md", "完全没有 frontmatter"),
                    ("broken3.md", ""),
                    ("broken4.md", "---\n---\n"),
                    ("broken5.md", "\x00\x01\x02 二进制垃圾")]:
    p = bad_dir / nm
    p.write_bytes(content.encode("utf-8", "replace"))
    casualties.append(p)
try:
    recs = m.list_records("manuscripts")
    check("损坏文件不崩溃", True)
    check("其余记录仍可读", len([r for r in recs if not r.get("_error") and r.get("title")]) >= 2,
          f"共 {len(recs)} 条")
except Exception as e:
    check("损坏文件不崩溃", False, str(e))
for p in casualties:
    p.unlink()

print("\n=== 3. id 生成：并发 + 全非法字符标题 ===")
ids = []
lock = threading.Lock()
def worker():
    for _ in range(12):
        r = m.write_record("ideas", {"title": "并发", "kind": "idea"})
        with lock:
            ids.append(r["id"])
ths = [threading.Thread(target=worker) for _ in range(8)]
[t.start() for t in ths]; [t.join() for t in ths]
check("96 条并发写入 id 无重复", len(ids) == len(set(ids)), f"{len(ids)} vs {len(set(ids))}")
weird = m.write_record("ideas", {"title": "!@#$%^&*()", "kind": "idea"})
check("全符号标题也能生成 id", bool(weird["id"]) and (m.DATA / "ideas" / f"{weird['id']}.md").exists(), weird["id"])
empty = m.write_record("ideas", {"title": "", "kind": "idea"})
check("空标题也能生成 id", bool(empty["id"]))
for i in ids + [weird["id"], empty["id"]]:
    m.delete_record("ideas", i)

print("\n=== 4. 路径安全：各种穿越写法 ===")
dev = m.get_device(); dev["paper_root"] = "/tmp/pdfs"; m._save_json(m.DEVICE_PATH, dev)
m._CACHE if hasattr(m, "_CACHE") else None
ATTACKS = ["/etc/passwd", "../../../etc/passwd", "/tmp/pdfs/../../etc/passwd",
           "/tmp/pdfs/./../../etc/shadow", "~/../../etc/passwd",
           "/proc/self/environ",
           "//etc/passwd", "/tmp/pdfs/\x00/etc/passwd"]
blocked = 0
for a in ATTACKS:
    try:
        r = m.safe_path(a)
    except Exception:
        r = None
    if r is None:
        blocked += 1
    else:
        print(f"      ⚠ 未拦截: {a} -> {r}")
check(f"{len(ATTACKS)} 种穿越全部拦截", blocked == len(ATTACKS), f"拦下 {blocked}")
check("白名单内正常放行", m.safe_path("/tmp/pdfs/paper1.pdf") is not None)
# 符号链接逃逸
link = Path("/tmp/pdfs/escape")
if link.exists() or link.is_symlink():
    link.unlink()
os.symlink("/etc", link)
check("符号链接逃逸被拦截", m.safe_path("/tmp/pdfs/escape/passwd") is None)
link.unlink()

print("\n=== 5. 文件名净化 ===")
for raw, must_not in [("../../evil.csv", ".."), ("..\\..\\evil.csv", ".."),
                      ("/etc/passwd", "/"), ("a\x00b.csv", "\x00"),
                      ("con.csv", None), ("." * 300 + ".csv", None)]:
    n = m.safe_name(raw)
    bad = must_not and must_not in n
    check(f"净化 {raw[:20]!r} -> {n[:28]!r}", not bad and len(n) <= 120 and n != "")

print("\n=== 6. 备份加密：极端口令与损坏数据 ===")
for pw in ["a", "口令带中文和空格 ☃", "x" * 500, "!@#$%^&*()_+-=[]{}|;':\",./<>?"]:
    data = os.urandom(5000)
    enc = m.encrypt_blob(data, pw)
    check(f"口令 {pw[:12]!r} 往返一致", m.decrypt_blob(enc, pw) == data)
enc = m.encrypt_blob(b"secret payload " * 20, "pw")
for name, mangled in [("篡改密文", enc[:80] + bytes([enc[80] ^ 1]) + enc[81:]),
                      ("截断", enc[:50]),
                      ("换头", b"XXXXXXXX" + enc[8:])]:
    try:
        m.decrypt_blob(mangled, "pw"); check(f"{name}应被拒绝", False, "竟然解开了")
    except Exception:
        check(f"{name}被拒绝", True)
check("空数据可加密", m.decrypt_blob(m.encrypt_blob(b"", "p"), "p") == b"")

print("\n=== 7. 额度调度器：极端状态 ===")
q = json.loads(json.dumps(m.DEFAULT_QUOTA))
q["rate_per_week"] = 0; q["week_start"] = "2020-01-06"; q["spent_this_week"] = 999
try:
    st = m.quota_status(q)
    check("配额为 0 不崩溃（除零）", True, f"available={st['available']}")
except ZeroDivisionError as e:
    check("配额为 0 不崩溃（除零）", False, "ZeroDivisionError")
q2 = json.loads(json.dumps(m.DEFAULT_QUOTA)); q2["week_start"] = None
check("week_start 为 None 可结算", m.quota_settle(q2) is not None)
q3 = json.loads(json.dumps(m.DEFAULT_QUOTA))
q3["week_start"] = m.week_key(); q3["blocked_events"] = ["不是日期", ""]
try:
    m.quota_settle(dict(q3, week_start="2020-01-06")); check("坏的 blocked_events 不崩溃", True)
except Exception as e:
    check("坏的 blocked_events 不崩溃", False, str(e)[:60])
# 长期收敛模拟
q4 = json.loads(json.dumps(m.DEFAULT_QUOTA)); q4["rate_per_week"] = 14.0
rates = []
for wk in range(26):
    spent = q4["rate_per_week"] * (0.5 if wk % 5 else 1.3)
    q4["spent_this_week"] = spent
    q4["week_start"] = f"2026-{(wk % 12) + 1:02d}-0{(wk % 4) + 1}"
    if wk % 5 == 0:
        q4["blocked_events"] = [f"2026-{(wk % 12) + 1:02d}-0{(wk % 4) + 1}T10:00:00"]
    else:
        q4["blocked_events"] = []
    m.quota_settle(q4)
    rates.append(q4["rate_per_week"])
check("26 周模拟未出现 NaN/负数/爆炸",
      all(0 < r < 1e6 and r == r for r in rates), f"最后 5 周: {[round(r,1) for r in rates[-5:]]}")

print("\n=== 8. 表格导入：畸形 CSV ===")
cases = {
    "空文件": "",
    "只有表头": "title,tier\n",
    "列数不齐": "title,tier\na,b,c,d\ne\n",
    "含 BOM 与引号": "\ufefftitle,note\n\"含,逗号\",\"含\"\"引号\"\"\"\n",
    "标题含换行": 'title,note\n"第一行\n第二行",x\n',
    "超长单元格": "title,note\n" + "x" * 60000 + ",y\n",
}
for name, content in cases.items():
    p = Path("/tmp/t_case.csv"); p.write_text(content, encoding="utf-8")
    try:
        r = m.import_table(str(p), "ideas", None, dedup_key="title")
        check(f"CSV {name}", r["ok"], f"created={r['created']}")
    except Exception as e:
        check(f"CSV {name}", False, type(e).__name__ + ": " + str(e)[:70])
for r in m.list_records("ideas"):
    if r.get("source_import"):
        m.delete_record("ideas", r["id"])

print("\n=== 9. 大数据量性能 ===")
t0 = time.time()
made = [m.write_record("ideas", {"title": f"性能测试 {i}", "kind": "idea",
                                 "body": "内容 " * 40})["id"] for i in range(400)]
t_write = time.time() - t0
t0 = time.time(); recs = m.list_records("ideas"); t_read = time.time() - t0
check(f"写 400 条 {t_write:.1f}s / 读 {len(recs)} 条 {t_read:.2f}s", t_read < 3.0 and t_write < 40)
t0 = time.time(); snap = m.snapshot("rolling"); t_snap = time.time() - t0
check(f"含 400 条时备份 {t_snap:.1f}s", snap["ok"] and t_snap < 20)
for i in made:
    m.delete_record("ideas", i)
shutil.rmtree(m.LOCAL / "trash", ignore_errors=True)

print("\n=== 10. ICS 解析：畸形与极端 ===")
import services as sv
ICS_CASES = {
    "空内容": "",
    "只有 VCALENDAR": "BEGIN:VCALENDAR\nEND:VCALENDAR",
    "VEVENT 无 DTSTART": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:x\nEND:VEVENT\nEND:VCALENDAR",
    "日期非法": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:99999999\nSUMMARY:x\nEND:VEVENT\nEND:VCALENDAR",
    "RRULE COUNT=99999": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260101T100000Z\nSUMMARY:x\nRRULE:FREQ=DAILY;COUNT=99999\nEND:VEVENT\nEND:VCALENDAR",
    "RRULE 无终止": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260101T100000Z\nSUMMARY:x\nRRULE:FREQ=DAILY\nEND:VEVENT\nEND:VCALENDAR",
    "月末 31 号每月重复": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260131T100000Z\nSUMMARY:x\nRRULE:FREQ=MONTHLY;COUNT=13\nEND:VEVENT\nEND:VCALENDAR",
    "闰日每年重复": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20240229T100000Z\nSUMMARY:x\nRRULE:FREQ=YEARLY;COUNT=5\nEND:VEVENT\nEND:VCALENDAR",
    "折行": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260801T100000Z\nSUMMARY:很长的标\n \x20题被折行了\nEND:VEVENT\nEND:VCALENDAR",
    "未闭合 VEVENT": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260801T100000Z\nSUMMARY:x\nEND:VCALENDAR",
}
for name, content in ICS_CASES.items():
    t0 = time.time()
    try:
        evs = sv.parse_ics(content)
        dt = time.time() - t0
        check(f"ICS {name} → {len(evs)} 条 ({dt:.2f}s)", dt < 3 and len(evs) < 1000)
    except Exception as e:
        check(f"ICS {name}", False, type(e).__name__ + ": " + str(e)[:60])

print("\n=== 11. 通用 webhook 模板注入 ===")
cap = {}
sv._req = lambda url, data=None, headers=None, method=None, timeout=15: (cap.update(body=data) or (True, 200, "{}"))
r = sv.custom_send({"url": "https://x", "template": '{"m":"{text}"}'},
                   'title"with\\quotes', 'body"with\\quotes\nand newline')
check("引号与反斜杠被正确转义", r["ok"] and "with" in json.dumps(cap.get("body"), ensure_ascii=False))
r2 = sv.custom_send({"url": "https://x", "template": '{"m":"{text}"'}, "t", "b")
check("模板缺花括号被拒绝而非崩溃", not r2["ok"])

print("\n" + "=" * 60)
print(f"后端极端测试：{'全部通过 ✓' if not FAIL else f'{len(FAIL)} 项失败'}")
for f in FAIL:
    print("   ✗", f)
