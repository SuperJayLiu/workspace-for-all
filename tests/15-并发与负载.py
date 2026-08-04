#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发与负载体检

这套测试全部来自一次高负荷压测里真实炸出来的问题，
每一条都对应一个已经修掉的 bug。写下来是为了它们别再回来。

压测规模：11317 条记录 + 5 万条文献索引，12 读 + 4 写 + 3 导入并发。

炸出来的三件事：

1. **临时文件撞名**（server.atomic_write_text 与 library._write_all）
   原来用 `threading.get_ident() & 0xffff` 当临时文件后缀。
   ThreadingHTTPServer 每个请求起一个线程，**线程 id 会被回收复用**，
   再截断到 16 位，两个并发写同一条记录就会撞出同名临时文件，
   先完成的 replace 掉之后，后一个 FileNotFoundError → 500。
   12 个并发写同一条记录，12 次里挂 2 次。

2. **索引并发导入丢数据**（library.Index）
   「读全量 → 合并 → 全量写回」没有互斥，两个导入同时进来，
   后写的会把先写的整批悄悄吃掉 —— 不报错，数据就是没了。

3. **读被写堵死**
   索引加锁之后，一次 5 万条的重写会把所有搜索卡在锁上，
   p99 从 70ms 飙到 35 秒。改成「快照 + 无锁读」。
"""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []


def check(name, cond, got=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"   实际={got}"))
    if not cond:
        FAIL.append(name)


print("=" * 62)
print("一、临时文件名必须全局唯一（线程 id 会被复用）")

import server as S                       # noqa: E402
import library as L                      # noqa: E402

names = set()
lock = threading.Lock()


def grab(n):
    for _ in range(n):
        nm = f".tmp{os.getpid()}-{next(S._TMP_SEQ)}"
        with lock:
            names.add(nm)


N_TH, N_EACH = 16, 200
ths = [threading.Thread(target=grab, args=(N_EACH,)) for _ in range(N_TH)]
[t.start() for t in ths]
[t.join() for t in ths]
check(f"{N_TH*N_EACH} 次取名零重复", len(names) == N_TH * N_EACH, len(names))
check("library 用的是同一套计数器风格",
      "_TMP_SEQ" in Path(ROOT / "library.py").read_text(encoding="utf-8"), "")
src = Path(ROOT / "server.py").read_text(encoding="utf-8")
check("server 里不再用 get_ident() 拼临时名",
      "get_ident() & 0xffff" not in src, "还留着")

print("\n二、并发写同一个文件：不能报错、不能写出半截文件")
tmpdir = Path(tempfile.mkdtemp())
target = tmpdir / "same.md"
errs = []


def writer(i):
    try:
        S.atomic_write_text(target, f"内容 {i}\n" + "x" * 5000)
    except Exception as e:
        with lock:
            errs.append(repr(e)[:90])


ths = [threading.Thread(target=writer, args=(i,)) for i in range(40)]
[t.start() for t in ths]
[t.join() for t in ths]
check("40 个并发写零异常", not errs, errs[:3])
txt = target.read_text(encoding="utf-8")
check("落盘内容完整（不是两次写的拼接）",
      txt.startswith("内容 ") and len(txt) == len("内容 0\n") + 5000 or
      txt.count("内容") == 1, f"长度 {len(txt)}，出现 {txt.count('内容')} 次")
leftover = list(tmpdir.glob("*.tmp*"))
check("没有残留临时文件", not leftover, leftover[:3])

print("\n三、索引并发导入：一条都不能丢")
ixp = tmpdir / "library.jsonl"
ix = L.Index(ixp)
BATCH, THREADS = 60, 8


def importer(t):
    items = [L._mk_item(k=f"T{t}-{i}", t=f"并发导入 {t} 号线程第 {i} 条",
                        y=2020, d=f"10.4444/c.{t}.{i}") for i in range(BATCH)]
    ix.add_many(items, source=f"t{t}")


ths = [threading.Thread(target=importer, args=(t,)) for t in range(THREADS)]
[t.start() for t in ths]
[t.join() for t in ths]
got = len(ix.load())
check(f"{THREADS} 个线程各导 {BATCH} 条，一条不丢（应 {THREADS*BATCH}）",
      got == THREADS * BATCH, got)
raw = sum(1 for _ in ixp.open(encoding="utf-8"))
check("落盘行数与内存条数一致", raw == got, (raw, got))
keys = [it["k"] for it in ix.load()]
check("没有重复 key", len(keys) == len(set(keys)), len(keys) - len(set(keys)))

print("\n四、写正在进行时，读不能被堵死")
big = [L._mk_item(k=f"B{i}", t=f"大批量 {i} liquidity momentum", y=2000 + i % 26,
                  d=f"10.3333/b.{i}") for i in range(20000)]
ix2 = L.Index(tmpdir / "big.jsonl")
ix2.add_many(big, source="big")
slow_done = threading.Event()
read_lat = []


def big_write():
    for _ in range(3):
        ix2.add_many([L._mk_item(k=f"X{time.time_ns()}", t="又一条", y=2024,
                                 d=f"10.2222/{time.time_ns()}")], source="x")
    slow_done.set()


def reader():
    while not slow_done.is_set():
        t0 = time.time()
        ix2.search(q="liquidity", limit=50)
        read_lat.append((time.time() - t0) * 1000)
        time.sleep(0.005)


tw = threading.Thread(target=big_write)
tr = threading.Thread(target=reader)
tw.start(); tr.start(); tw.join(); tr.join()
read_lat.sort()
worst = read_lat[-1] if read_lat else 0
check(f"重写 2 万条期间，搜索最慢 {worst:.0f}ms < 2000ms",
      worst < 2000, f"{worst:.0f}ms（共 {len(read_lat)} 次）")

print("\n五、记录解析缓存：快，但绝不能给旧内容")
coll_dir = tmpdir / "reading"
coll_dir.mkdir(exist_ok=True)
for i in range(50):
    (coll_dir / f"c-{i}.md").write_text(f"---\ntitle: 原始 {i}\n---\n\n正文", encoding="utf-8")
orig_dir = S.coll_dir


def fake_dir(name):
    return coll_dir if name == "reading" else orig_dir(name)


S.coll_dir = fake_dir
try:
    S._REC_CACHE.clear()
    a = S.list_records("reading")
    check("首次读到 50 条", len(a) == 50, len(a))
    t0 = time.time(); S.list_records("reading"); cold_warm = (time.time() - t0) * 1000
    check(f"第二次走缓存（{cold_warm:.1f}ms）", cold_warm < 100, f"{cold_warm:.1f}ms")
    time.sleep(0.01)
    (coll_dir / "c-7.md").write_text("---\ntitle: 改过了\n---\n\n新正文", encoding="utf-8")
    b = {x["id"]: x["title"] for x in S.list_records("reading")}
    check("改过的文件立刻反映出来", b.get("c-7") == "改过了", b.get("c-7"))
    (coll_dir / "c-8.md").unlink()
    check("删掉的文件立刻消失", len(S.list_records("reading")) == 49,
          len(S.list_records("reading")))
    (coll_dir / "c-99.md").write_text("---\ntitle: 新增\n---\n\n", encoding="utf-8")
    check("新增的文件立刻出现", len(S.list_records("reading")) == 50,
          len(S.list_records("reading")))
    got = S.list_records("reading")
    got[0]["title"] = "调用方乱改的"
    check("调用方就地改写不会污染缓存",
          S.list_records("reading")[0]["title"] != "调用方乱改的",
          S.list_records("reading")[0]["title"])
finally:
    S.coll_dir = orig_dir

print("\n六、首屏永远不能夹带整个索引")
boot_src = src[src.find('if route == "bootstrap"'):][:2500]
check("bootstrap 只放 libraryCount 计数", "libraryCount" in boot_src, "")
check("bootstrap 不调用 search / 不塞 items",
      "library/search" not in boot_src and '"items"' not in boot_src, "")

print("=" * 62)
if FAIL:
    print(f"并发与负载测试：{len(FAIL)} 条不通过 ✗")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("并发与负载测试：全部通过 ✓")
