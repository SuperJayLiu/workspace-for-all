#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全工作台搜索 + 这一轮新增/修复的功能

每一条都对应一个具体问题：

  · 搜索只扫内存记录 —— 搜不到 5 万条文献索引，也搜不到「备份在哪」
  · 本地 PDF 给的是 file:// —— 浏览器禁止 http 页面跳 file://，点了没反应
  · 导出 .bib 缺卷期页码 —— 拿去投稿不能直接用
  · Zotero 里删掉的条目在索引里变僵尸
  · 工作论文与正式发表版被当成两篇
  · Zotero 存储路径写死绝对路径 —— 换台机器 100% 打不开
  · 首屏把所有记录连正文一起塞过来
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import library as L                      # noqa: E402
import search as SE                      # noqa: E402
import server as S                       # noqa: E402

FAIL = []


def check(name, cond, got=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"   实际={got}"))
    if not cond:
        FAIL.append(name)


print("=" * 62)
print("一、搜功能与设置（原来完全搜不到）")
CASES = [
    ("备份", "备份时光机"), ("钉钉", "推送渠道"), ("token", "Git 同步"),
    ("zotero", "文献索引"), ("复习", "复习队列"), ("甘特", "甘特图"),
    ("额度", "额度调度器"), ("诊断", "导出诊断包"), ("excel", "表格导入"),
    ("时区", None), ("遗忘曲线", "复习队列"), ("暗色", "装修模式"),
    ("授权码", "邮箱收件"), ("找回", "备份时光机"), ("报bug", "导出诊断包"),
]
for q, want in CASES:
    r = SE.search_features(q)
    if want:
        check(f"搜「{q}」首条是「{want}」", r and want in r[0]["title"],
              r[0]["title"] if r else "没结果")
    else:
        check(f"搜「{q}」有结果", bool(r), r)
# 动作类（「立即备份」）本来就不该有 route —— 它不跳页面，是执行一件事
_f = SE.search_features("备份")
check("功能类结果都有跳转目标",
      all(x.get("route") for x in _f if x["kind"] == "feature"),
      [(x["kind"], x.get("route")) for x in _f])
check("动作类结果被单独标成 action",
      any(x["kind"] == "action" for x in _f), [x["kind"] for x in _f])
check("卡片类结果带 card 键", any(x.get("card") for x in SE.search_features("备份")), "")
check("搜不到就返回空，不硬凑", SE.search_features("完全不相干的火星文zzz") == [], "")
check("空查询不返回全部", SE.search_features("") == [], "")

print("\n二、搜记录：标题命中要排在正文命中前面")
RECS = {
    "manuscripts": [
        {"id": "a", "title": "流动性与杠杆", "stage": "rnr"},
        {"id": "b", "title": "别的题目", "body": "正文里提到流动性这个词"},
    ],
    "reading": [{"id": "c", "title": "Liquidity and Leverage",
                 "authors": ["Adrian, T."], "year": 2010}],
}
res = SE.search_records(lambda c: RECS.get(c, []), list(RECS), "流动性")
check("两条都命中", len(res) == 2, len(res))
check("标题命中排前面", res[0]["id"] == "a", [x["id"] for x in res])
check("带上集合标签", res[0]["label"] == "稿件", res[0]["label"])
check("正文命中给出片段", any(x["snippet"] for x in res if x["id"] == "b"),
      [x["snippet"] for x in res])
res2 = SE.search_records(lambda c: RECS.get(c, []), list(RECS), "流动性 杠杆")
check("多个词是 AND", len(res2) == 1 and res2[0]["id"] == "a", [x["id"] for x in res2])
res3 = SE.search_records(lambda c: RECS.get(c, []), list(RECS), "Adrian")
check("能搜作者", len(res3) == 1, res3)
# id / 时间戳不该被搜到，否则打个年份就命中所有记录
res4 = SE.search_records(lambda c: RECS.get(c, []), list(RECS), "a")
check("不会因为 id 是 'a' 就命中", all(x["id"] != "a" or "流动" in x["title"] for x in res4), "")

print("\n三、四类结果汇总")
tmp = Path(tempfile.mkdtemp())
ix = L.Index(tmp / "library.jsonl")
ix.add_many([L._mk_item(k="LB1", t="Funding Liquidity and Market Liquidity",
                        a=["Brunnermeier, M."], y=2009, d="10.1/fl")], source="bib")
allr = SE.search_all("liquidity", lambda c: RECS.get(c, []), list(RECS),
                     library=ix, quotes=[{"t": "liquidity 是一切的开始", "s": "某人"}],
                     open_targets=L.open_targets)
keys = [g["key"] for g in allr["groups"]]
check("记录组在", "record" in keys, keys)
check("文献索引组在", "library" in keys, keys)
check("箴言组在", "quote" in keys, keys)
lg = [g for g in allr["groups"] if g["key"] == "library"][0]
check("文献结果带跳转选项", bool(lg["items"][0].get("open")), lg["items"][0])
allf = SE.search_all("备份", lambda c: RECS.get(c, []), list(RECS), library=ix)
check("功能组永远排第一", allf["groups"][0]["key"] == "feature",
      [g["key"] for g in allf["groups"]])
check("空查询返回空结果而不是全部",
      SE.search_all("", lambda c: RECS.get(c, []), list(RECS))["total"] == 0, "")

print("\n四、本地 PDF：不能是 file://（浏览器禁止 http 页面跳 file://）")
it = L._mk_item(t="X", p="/Users/me/Zotero/storage/AB12/He_2013.pdf")
u = [x for x in L.open_targets(it, "none") if x["kind"] == "pdf"][0]["url"]
check("不是 file:// 死链", not u.startswith("file://"), u)
check("走服务端接口", u.startswith("/api/library/file?path="), u)

print("\n五、Zotero 存储路径跨设备")
check("识别出相对 storage 的部分", it.get("pr") == "AB12/He_2013.pdf", it.get("pr"))
check("Mac 上拼回来",
      L.resolve_pdf(it, "/Users/me/Zotero") == "/Users/me/Zotero/storage/AB12/He_2013.pdf",
      L.resolve_pdf(it, "/Users/me/Zotero"))
check("Windows 上拼回来",
      L.resolve_pdf(it, "C:/Users/me/Zotero") == "C:/Users/me/Zotero/storage/AB12/He_2013.pdf",
      L.resolve_pdf(it, "C:/Users/me/Zotero"))
check("根目录已经指到 storage 也不会拼两次",
      L.resolve_pdf(it, "/Users/me/Zotero/storage").count("storage") == 1,
      L.resolve_pdf(it, "/Users/me/Zotero/storage"))
out_it = L._mk_item(t="Y", p="/somewhere/paper.pdf")
check("不在 storage 下的退回原路径",
      L.resolve_pdf(out_it, "/Users/me/Zotero") == "/somewhere/paper.pdf",
      L.resolve_pdf(out_it, "/Users/me/Zotero"))

print("\n六、镜像同步：Zotero 里删掉的要跟着删，手工导入的不能误伤")
ix2 = L.Index(tmp / "m.jsonl")
ix2.add_many([L._mk_item(k=f"Z{i}", t=f"Z{i}", d=f"10.1/z{i}", y=2020) for i in range(5)],
             source="zotero")
ix2.add_many([L._mk_item(k="B1", t="手工导入", d="10.2/b", y=2021)], source="bib")
st = ix2.mirror([L._mk_item(k=f"Z{i}", t=f"Z{i}", d=f"10.1/z{i}", y=2020) for i in (0, 1, 2)],
                "zotero")
by = ix2.stats()["by_source"]
check("Zotero 侧从 5 条对齐到 3 条", by.get("zotero") == 3, by)
check("删掉了 2 条", st["removed"] == 2, st)
check("手工导入的 .bib 不受影响", by.get("bib") == 1, by)
check("普通导入仍然只加不减",
      ix2.add_many([L._mk_item(k="Z9", t="Z9", d="10.1/z9", y=2020)],
                   source="zotero")["total"] == 5, ix2.stats())

print("\n七、工作论文与正式发表版合并")
ix3 = L.Index(tmp / "wp.jsonl")
ix3.add_many([L._mk_item(k="WP", t="Same Paper", y=2023, j="Working Paper"),
              L._mk_item(k="PUB", t="Same Paper", y=2025, j="Journal of Finance",
                         d="10.9/p", vol="80", pg="1-40")], source="bib")
check("年份不同确实会被当成两条", len(ix3.load()) == 2, len(ix3.load()))
r = ix3.merge_pair("PUB", "WP")
check("合并成功", r.get("ok"), r)
check("只剩一条", len(ix3.load()) == 1, len(ix3.load()))
kept = ix3.load()[0]
check("保留的是正式发表版", kept["k"] == "PUB", kept["k"])
check("留下了合并痕迹", kept.get("merged_from") == ["WP"], kept.get("merged_from"))
check("合并不存在的条目会明确报错",
      ix3.merge_pair("PUB", "根本没有这条").get("ok") is False, "")
_self = ix3.merge_pair("PUB", "PUB")
check("自己跟自己合并会被拦住，而不是把自己删掉",
      _self.get("ok") is False and len(ix3.load()) == 1, (_self, len(ix3.load())))
check("并且给的是看得懂的理由", "同一条" in _self.get("detail", ""), _self.get("detail"))

print("\n八、导出 .bib 字段齐全")
b = L.to_bibtex(ix3.load())
for f in ("volume = {80}", "pages = {1-40}", "doi = {10.9/p}"):
    check(f"含 {f}", f in b, b[:220])
check("导出能被自己解析回来", len(L.parse_bibtex(b)) == 1, b[:120])

print("\n九、首屏瘦身：**根本不带 body**，生活流水只带近期")
# 这一节的设计换过一次，原因值得记下来：
# 原来是把 body 截成 160 字、照样放在 body 这个字段里。结果「一份看起来正常、
# 其实是残缺的 body」顺着十几条路径被原样存回磁盘（编辑器、拖便利贴、勾完成、
# 拖甘特条、项目页笔记框、想法升级成稿件……），补了一处又冒出一处。
# 现在首屏不带 body，只带 _preview（下划线开头，write_record 一定会剥掉），
# 于是「把截断的正文存回去」这件事在结构上就不可能发生。
long_body = "正" * 900
short_body = "很短的正文"
data = {
    "manuscripts": [{"id": "m1", "title": "稿", "body": long_body}],
    "ideas": [{"id": "i1", "title": "便利贴", "body": long_body}],
    "reading": [{"id": "rd1", "title": "文献", "body": long_body}],
    "schedule": [{"id": "s1", "title": "短正文", "body": short_body}],
    "reports": [{"id": "r1", "title": "报告", "body": long_body}],
    "retros": [{"id": "rt1", "title": "复盘", "body": long_body}],
    "finance": [{"id": f"f{i}", "title": "开支", "date": f"2020-01-{(i % 28) + 1:02d}"}
                for i in range(900)],
    "lists": [{"id": "l1", "title": "没有日期的清单"}],
}
slim = S.slim_bootstrap({k: [dict(x) for x in v] for k, v in data.items()})
for _c in ("manuscripts", "ideas", "reading", "schedule"):
    check(f"{_c}：首屏根本没有 body 这个字段（存不回去截断的正文）",
          "body" not in slim[_c][0], list(slim[_c][0].keys()))
    check(f"{_c}：打了 _body_more，界面知道要去取全文",
          slim[_c][0].get("_body_more") is True, slim[_c][0].get("_body_more"))
check("**短**正文也照样不带、照样打标记 —— "
      "「短的就原样给」听着无害，其实界面会以为手上这份是全的",
      "body" not in slim["schedule"][0] and slim["schedule"][0].get("_body_more") is True,
      slim["schedule"][0])
check("卡片要显示片段的（稿件）给 _preview",
      len(slim["manuscripts"][0].get("_preview") or "") <= S.BODY_PREVIEW,
      slim["manuscripts"][0].get("_preview"))
check("便利贴也给 _preview", bool(slim["ideas"][0].get("_preview")), "")
check("不显示片段的（文献/日程）连 _preview 都不给，白白占体积",
      "_preview" not in slim["reading"][0] and "_preview" not in slim["schedule"][0], "")
check("_preview 是下划线开头的 —— write_record 会剥掉，写不进文件",
      all(k.startswith("_") for k in ("_preview", "_body_more")), "")
for _c in ("reports", "retros"):
    check(f"{_c} 的正文**不**动（正文就是内容本身，卡片直接显示）",
          slim[_c][0].get("body") == long_body, len(slim[_c][0].get("body") or ""))
check("很老的生活流水不进首屏", len(slim["finance"]) < 900, len(slim["finance"]))
check("生活流水有上限", len(slim["finance"]) <= S.LIFE_MAX, len(slim["finance"]))
check("没有日期的清单永远保留", len(slim["lists"]) == 1, slim["lists"])
check("原始数据没被就地改坏", len(data["manuscripts"][0]["body"]) == len(long_body),
      len(data["manuscripts"][0]["body"]))
# 体积：这才是做这件事的理由
_full = len(json.dumps(data, ensure_ascii=False).encode())
_slim = len(json.dumps(slim, ensure_ascii=False).encode())
check(f"首屏明显更小（{_full} → {_slim} 字节）", _slim < _full * 0.6, (_full, _slim))

print("\n九·再续、只有流水能按时间裁，册子类一条都不能少")
# 这一组全是真出过的事故：
#   生日存 1962 年、靠 yearly 每年提醒，按「近 180 天」一裁，整张「重要日子」卡变空；
#   逾期没做的旧待办同样凭空消失，而那恰恰是最该被看见的几条。
book = {
    "dates": [{"id": "d1", "title": "妈妈生日", "date": "1962-05-12", "yearly": True},
              {"id": "d2", "title": "结婚纪念", "date": "2019-09-03", "yearly": True}],
    "admin": [{"id": "a1", "title": "逾期没做的事", "date": "2020-03-01", "done": False}],
    "lists": [{"id": f"l{i}", "title": f"买菜{i}"} for i in range(S.LIFE_MAX + 120)],
}
m2 = {}
slim2 = S.slim_bootstrap({k: [dict(x) for x in v] for k, v in book.items()}, m2)
check("很老的「重要日子」不会被裁掉", len(slim2["dates"]) == 2, len(slim2["dates"]))
check("逾期的生活事务不会被裁掉", len(slim2["admin"]) == 1, len(slim2["admin"]))
check("清单超过上限也一条不少", len(slim2["lists"]) == len(book["lists"]), len(slim2["lists"]))
for _c in ("dates", "admin", "lists"):
    check(f"{_c} 没被标成残缺", not m2[_c].get("partial"), m2[_c])

print("\n九·三续、裁过的必须如实上报，界面才不会拿残缺数据当合计")
m3 = {}
S.slim_bootstrap({"finance": [{"id": f"f{i}", "title": "开支", "amount": 10,
                               "date": f"2020-01-{(i % 28) + 1:02d}"} for i in range(900)]}, m3)
fm = m3["finance"]
check("上报了真实总数", fm.get("total") == 900, fm)
check("上报了实际带回多少", fm.get("shown") == len(S.slim_bootstrap(
    {"finance": [{"id": f"f{i}", "date": f"2020-01-{(i % 28) + 1:02d}"} for i in range(900)]})["finance"]), fm)
check("明确标了 partial，界面据此改口径", fm.get("partial") is True, fm)
check("告诉界面是从哪天起算的", bool(fm.get("since")), fm)
# 没裁的不该冒出 partial —— 否则界面会永远挂着「加载全部」
m4 = {}
S.slim_bootstrap({"finance": [{"id": "f1", "amount": 1,
                               "date": datetime.now().strftime("%Y-%m-%d")}]}, m4)
check("没裁就不标 partial", not m4["finance"].get("partial"), m4["finance"])

print("\n九·续、截断的正文必须能完整取回来（否则编辑一保存就丢字）")
import tempfile as _tf, os as _os
_root = Path(_tf.mkdtemp())
(_root / "manuscripts").mkdir()
_long = "这是一段很长的正文。" * 200
(_root / "manuscripts" / "big.md").write_text(
    "---\ntitle: 长正文稿件\n---\n\n" + _long, encoding="utf-8")
_orig = S.coll_dir
S.coll_dir = lambda n: (_root / "manuscripts") if n == "manuscripts" else _orig(n)
try:
    S._REC_CACHE.clear()
    recs = S.list_records("manuscripts")
    check("单条读取拿到的是完整正文", len(recs[0]["body"]) >= len(_long), len(recs[0]["body"]))
    slim1 = S.slim_bootstrap({"manuscripts": [dict(x) for x in recs]})
    check("首屏那份不带 body", "body" not in slim1["manuscripts"][0],
          list(slim1["manuscripts"][0].keys()))
    check("带 _body_more 标记，界面据此去取全文",
          slim1["manuscripts"][0].get("_body_more") is True, "")
    check("只给一小段 _preview 供卡片显示",
          len(slim1["manuscripts"][0].get("_preview") or "") <= S.BODY_PREVIEW,
          len(slim1["manuscripts"][0].get("_preview") or ""))
    # 单条接口（编辑器/AI/展开全文 都走它）必须给全量
    one = S.read_record("manuscripts", "big")
    check("单条接口给的是完整正文", len(one["body"]) >= len(_long), len(one["body"]))
    check("单条接口不带 _body_more", "_body_more" not in one, one.keys())
finally:
    S.coll_dir = _orig
    S._REC_CACHE.clear()

# 编辑器只是**其中一条**写回路径。patchRec 才是高频的那条：
# 拖便利贴、勾完成、拖甘特条、记一次复习，全都是「取内存那份 + 改一个字段 + 整份存回去」。
# 它要是不先取全量，随手拖一下就把笔记删掉一半，而且不报错。
src_core = (ROOT / "app" / "js" / "core.js").read_text(encoding="utf-8")
check("patchRec 在不改正文时会先取全量",
      "_body_more" in src_core and "ensureFull" in src_core, "")
check("saveRec 留了最后一道网（还带着标记就不写 body）",
      "宁可不写 body" in src_core or "delete rec.body" in src_core, "")

# 服务端配合：提交里没有 body 就保留磁盘原文
_r2 = Path(_tf.mkdtemp())
(_r2 / "ideas").mkdir()
(_r2 / "ideas" / "keep.md").write_text(
    "---\ntitle: 原标题\n---\n\n" + ("原有正文。" * 200), encoding="utf-8")
_o2 = S.coll_dir
S.coll_dir = lambda n: (_r2 / "ideas") if n == "ideas" else _o2(n)
try:
    S._REC_CACHE.clear()
    S.write_record("ideas", {"id": "keep", "title": "只改了标题"})
    after = S.read_record("ideas", "keep")
    check("提交不带 body → 磁盘正文原样保留", len(after["body"]) > 900, len(after["body"]))
    check("要改的字段确实改了", after["title"] == "只改了标题", after["title"])
    S.write_record("ideas", {"id": "keep", "title": "这次带了", "body": "换成这句"})
    after2 = S.read_record("ideas", "keep")
    check("提交带了 body → 按要求覆盖", after2["body"].strip() == "换成这句", after2["body"][:30])
    made = S.write_record("ideas", {"title": "全新的，没有旧文可留"})
    check("新建记录不带 body 也不出错", made.get("id") and made.get("body") == "", made.get("body"))
    # 内部字段绝不能写进 md：写进去之后会被当成真字段读回来，从此永远带着
    S.write_record("ideas", {"id": "inner", "title": "t", "body": "正文",
                             "_body_more": True, "_collection": "ideas",
                             "_mtime": 1, "_anything": "x"})
    _raw = (_r2 / "ideas" / "inner.md").read_text(encoding="utf-8")
    for _f in ("_body_more", "_collection", "_mtime", "_anything"):
        check(f"{_f} 没被写进文件", _f not in _raw, _raw[:120])
finally:
    S.coll_dir = _o2
    S._REC_CACHE.clear()

src_ui = (ROOT / "app" / "js" / "ui.js").read_text(encoding="utf-8")
check("编辑器打开前也会取全量",
      "_body_more" in src_ui and "records/${encodeURIComponent(coll)}" in src_ui, "")
check("取不到全量时宁可不打开编辑器，也不让截断内容被保存",
      "为避免把正文截断保存" in src_ui, "")
src_ai = (ROOT / "app" / "js" / "mod-ai.js").read_text(encoding="utf-8")
check("喂给 AI 的上下文也取全量", "_body_more" in src_ai, "")
src_ms = (ROOT / "app" / "js" / "mod-academic.js").read_text(encoding="utf-8")
check("卡片上截断处有「展开全文」", "data-fullbody" in src_ms, "")

print("\n十、诊断包：能查问题，但不含任何记录内容")
diag = S.build_diagnostics()
check("含版本", "工作台版本" in diag, "")
check("含各集合条数", "manuscripts:" in diag, "")
check("含 Python 与平台", "Python：" in diag, "")
check("明说不含记录内容", "不含任何记录内容" in diag, "")
for leak in ("Intermediary", "流动性与杠杆", "10.1257/"):
    check(f"不含记录内容（{leak}）", leak not in diag, "")
import re as _re
check("没有裸露的 token", not _re.search(r"gh[pous]_[A-Za-z0-9]{20,}", diag), "")

print("\n十·续、搜索快照：快，但不能让刚存的东西搜不到")
import time as _t2
_calls = {"n": 0}
_store = {"ideas": [{"id": "s1", "title": "原有的一条"}]}


def _counting(c):
    # 真实的 list_records 每次返回**新的**列表；这里也必须如此，
    # 否则往原列表里追加会直接被快照看到，测不出该测的东西
    _calls["n"] += 1
    return list(_store.get(c, []))


SE.invalidate_snapshot()
SE.search_records(_counting, ["ideas"], "原有")
n1 = _calls["n"]
for _ in range(5):
    SE.search_records(_counting, ["ideas"], "原有")
check("连续搜索复用快照，不反复扫盘", _calls["n"] == n1, (_calls["n"], n1))
# 写入之后必须立刻可见
_store["ideas"].append({"id": "s2", "title": "刚刚新增的独特词"})
r_before = SE.search_records(_counting, ["ideas"], "刚刚新增")
check("不失效的话新记录确实看不到（这正是要防的）", len(r_before) == 0, r_before)
SE.invalidate_snapshot()
r_after = SE.search_records(_counting, ["ideas"], "刚刚新增")
check("失效之后立刻能搜到", len(r_after) == 1, r_after)
src_srv = (ROOT / "server.py").read_text(encoding="utf-8")
check("写记录后会让快照失效",
      src_srv.count("searchmod.invalidate_snapshot()") >= 2, "")
check("删记录后也会失效", "def delete_record" in src_srv
      and "invalidate_snapshot" in src_srv.split("def delete_record")[1][:400], "")
check("快照 TTL 是短的（秒级）", SE.SNAP_TTL <= 5, SE.SNAP_TTL)

print("\n十一、镜像同步的安全闸（唯一会大批删数据的操作）")
ix4 = L.Index(tmp / "guard.jsonl")
ix4.add_many([L._mk_item(k=f"G{i}", t=f"G{i}", d=f"10.1/g{i}", y=2020) for i in range(200)],
             source="zotero")
r0 = ix4.mirror([], "zotero")
check("对方返回空 → 拒绝，不删任何东西", r0.get("refused") == "empty", r0)
check("拒绝之后数据原封不动", len(ix4.load()) == 200, len(ix4.load()))
r1 = ix4.mirror([L._mk_item(k="G0", t="G0", d="10.1/g0", y=2020)], "zotero")
check("只拉回一小撮 → 也拒绝", r1.get("refused") == "shrink", r1)
check("告诉你会删多少条", r1.get("would_remove") == 199, r1)
check("这时数据也没动", len(ix4.load()) == 200, len(ix4.load()))
r2 = ix4.mirror([L._mk_item(k="G0", t="G0", d="10.1/g0", y=2020)], "zotero", force=True)
check("明确 force 才真的执行", r2.get("ok") and len(ix4.load()) == 1, (r2, len(ix4.load())))
# 正常的小幅增删不该被闸住
ix5 = L.Index(tmp / "normal.jsonl")
ix5.add_many([L._mk_item(k=f"N{i}", t=f"N{i}", d=f"10.1/n{i}", y=2020) for i in range(50)],
             source="zotero")
r3 = ix5.mirror([L._mk_item(k=f"N{i}", t=f"N{i}", d=f"10.1/n{i}", y=2020) for i in range(48)],
                "zotero")
check("正常删两条不会被闸住", r3.get("ok") and r3["removed"] == 2, r3)

print("\n十二、手机速记要能在「远程只读」下用（否则 jot 页等于没做）")
import time as _time
_tok = "t16"
S.SESSIONS[_tok] = {"ip": "192.168.1.50", "until": _time.time() + 999,
                    "write_until": _time.time() - 10, "ua": "phone"}
# 直接换掉 get_config，不去改它返回的字典 ——
# 那个字典是不是缓存的、每次调用是不是同一个对象，不该由测试来假设。
# （最初就是靠假设写的，在开发目录里碰巧成立，在解压出来的包里就崩了。）
_real_cfg = S.get_config


def _fake_cfg(*a, **k):
    c = dict(_real_cfg())
    c["security"] = {"remote_enabled": True, "remote_readonly": True}
    return c


S.get_config = _fake_cfg


class _Fake:
    client_ip = "192.168.1.50"

    def __init__(self, headers=None):
        self.headers = dict(headers or {"Host": "192.168.1.9:8765"})

    def _cookie_token(self):
        return _tok


def _mk(headers=None):
    f = _Fake(headers)
    f.cross_site = S.Handler.cross_site.__get__(f, _Fake)
    return S.Handler.gate.__get__(f, _Fake)


_gate = _mk()
try:
    check("速记（只追加）放行", _gate("capture", "POST") is None, _gate("capture", "POST"))
    check("改记录仍然要解锁", (_gate("records/ideas", "POST") or [0])[0] == 423,
          _gate("records/ideas", "POST"))
    check("删记录仍然要解锁",
          (_gate("records/manuscripts/x/delete", "POST") or [0])[0] == 423, "")
    check("导入文献仍然要解锁", (_gate("library/import", "POST") or [0])[0] == 423, "")
    check("读接口本来就放行", _gate("search", "GET") is None, "")
    for r_ in ("tex/sync", "library/file", "secrets", "library/zotero/sync",
               "table/preview", "table/import", "library/clear", "claude/outbox"):
        check(f"{r_} 远程永远禁止", (_gate(r_, "POST") or [0])[0] == 403, _gate(r_, "POST"))
finally:
    S.get_config = _real_cfg
    S.SESSIONS.pop(_tok, None)

print("\n十三、跨站请求：别的网页不能借浏览器操作本机工作台")
# 本机请求一律放行，所以「谁在发这个请求」是唯一的分界线。
# 用户随便开一个网页，那个网页就能对 127.0.0.1:8765 发 POST；
# no-cors 拿不到回应，但**副作用照样发生**（新建、删除、恢复备份）。
_HOST = "127.0.0.1:8765"


def _cs(origin, method="POST", host=_HOST):
    f = _Fake({"Host": host, "Origin": origin} if origin is not None else {"Host": host})
    return S.Handler.cross_site.__get__(f, _Fake)(method)


check("同源的写请求放行", _cs("http://127.0.0.1:8765") is False, _cs("http://127.0.0.1:8765"))
check("恶意网站的写请求被判为跨站", _cs("https://evil.example") is True, "")
check("同主机不同端口也算跨站", _cs("http://127.0.0.1:9999") is True, "")
check("Origin: null（沙箱 iframe / file:// 页）当跨站拒掉", _cs("null") is True, _cs("null"))
check("不带 Origin 的（curl / 手机 App）照旧放行", _cs(None) is False, _cs(None))
check("读请求不受影响", _cs("https://evil.example", "GET") is False, "")
check("DELETE 同样受保护", _cs("https://evil.example", "DELETE") is True, "")
_g_cross = S.Handler.gate.__get__(
    type("F2", (_Fake,), {"cross_site": S.Handler.cross_site})(
        {"Host": _HOST, "Origin": "https://evil.example"}), _Fake)
check("闸门直接拒掉跨站写请求", (_g_cross("records/ideas", "POST") or [0])[0] == 403,
      _g_cross("records/ideas", "POST"))
check("本机同源写请求照常通过",
      S.Handler.gate.__get__(
          type("F3", (_Fake,), {"client_ip": "127.0.0.1",
                                "cross_site": S.Handler.cross_site})(
              {"Host": _HOST, "Origin": "http://127.0.0.1:8765"}), _Fake)(
          "records/ideas", "POST") is None, "")


print("\n十四、这一轮堵掉的读文件/删数据的口子")
import shutil as _sh
_sec = Path(tempfile.mkdtemp())
(_sec / "data" / "_claude" / "outbox").mkdir(parents=True)
(_sec / "data" / "_claude" / "outbox" / "周报.md").write_text("正常内容", encoding="utf-8")
(_sec / "local").mkdir(parents=True, exist_ok=True)
(_sec / "local" / "secrets.json").write_text('{"github":{"token":"ghp_XXX"}}', encoding="utf-8")
_oldC, _oldR, _oldL = S.CLAUDE, S.ROOT, S.LOCAL
S.CLAUDE, S.ROOT, S.LOCAL = _sec / "data" / "_claude", _sec, _sec / "local"
try:
    # safe_name 只取文件名本身，所以穿越串会被压成一个不存在的文件名
    for evil in ["../../../local/secrets.json", "../../../../../../etc/passwd",
                 "..%2f..%2flocal%2fsecrets.json", "/etc/passwd", r"..\..\local\secrets.json"]:
        nm = S.safe_name(evil, "")
        p = S.CLAUDE / "outbox" / nm
        got = p.read_text(encoding="utf-8") if p.is_file() else ""
        check(f"读不到 {evil[:26]}", "ghp_XXX" not in got and "root:x:" not in got, got[:40])
    check("正常的文件名照样能读", (S.CLAUDE / "outbox" / S.safe_name("周报.md")).read_text(
        encoding="utf-8") == "正常内容", "")
finally:
    S.CLAUDE, S.ROOT, S.LOCAL = _oldC, _oldR, _oldL

# 恢复备份只认备份目录里的 workspace_*.zip —— 它会往工作台目录里解压，
# 路径能随便指的话，任何「能往磁盘上放文件」的途径都变成了改代码。
for bad_p in ["/tmp/evil.zip", "~/Downloads/workspace_x.zip", "", "/etc/passwd",
              str(S.LOCAL / "imports" / "workspace_evil.zip")]:
    r_ = S.restore_snapshot(bad_p)
    check(f"拒绝恢复 {bad_p[:34] or '(空路径)'}", r_.get("ok") is False, r_)

# 扫描目录会把该目录加进「允许打开」白名单，太靠上的一律不加
from pathlib import Path as _P
_home = _P.home()
for broad in [str(_home), str(_home / "Documents"), str(_home / "Downloads"), "/"]:
    check(f"{broad} 不入白名单", S.is_sane_scan_root(broad) is False, "")
check("具体的论文目录可以入白名单",
      S.is_sane_scan_root(str(_home / "Papers" / "econ")) is True, "")

# 文献索引整库清空要明确确认
_lib = Path(tempfile.mkdtemp()) / "library.jsonl"
_ix = L.Index(_lib)
_ix.add_many([L._mk_item(k=f"k{i}", t=f"论文{i}", y=2020, d=f"10.5/x{i}")
              for i in range(30)], source="bib")
_r = _ix.clear()
check("不带 confirm 不清空", _r.get("ok") is False and _r.get("refused") == "confirm", _r)
check("先告诉你会删多少条", _r.get("would_remove") == 30, _r)
check("数据一条没少", len(_ix.load()) == 30, len(_ix.load()))
_r2 = _ix.clear(confirm=True)
check("带了 confirm 才真清", _r2.get("removed") == 30 and len(_ix.load()) == 0, _r2)

print("\n十五、坏文件不能让一条记录永久救不回来")
_bad = Path(tempfile.mkdtemp())
(_bad / "manuscripts").mkdir()
(_bad / "manuscripts" / "broken.md").write_text(
    "---\nb:\n  b:\n- k: 1\n---\n\n正文还在这儿\n", encoding="utf-8")
(_bad / "manuscripts" / "bignum.md").write_text(
    "---\ntitle: 长编号\nisbn: " + "9" * 5000 + "\n---\n\n内容\n", encoding="utf-8")
_o2 = S.coll_dir
S.coll_dir = lambda n: (_bad / "manuscripts") if n == "manuscripts" else _o2(n)
try:
    S._REC_CACHE.clear()
    r1 = S.read_record("manuscripts", "broken")
    check("坏 frontmatter 也能读出来（不是 500）", r1 is not None, r1)
    check("正文没丢", "正文还在这儿" in (r1 or {}).get("body", ""), (r1 or {}).get("body", "")[:40])
    r2 = S.read_record("manuscripts", "bignum")
    check("超长数字当字符串处理，读得出来", r2 is not None and len(str(r2.get("isbn"))) == 5000,
          type((r2 or {}).get("isbn")).__name__)
    check("存得回去（不再抛 ValueError）",
          bool(S.dump_frontmatter({"title": "x", "isbn": "9" * 5000}, "")), "")
    S._REC_CACHE.clear()
    check("列表里也不会因为一个坏文件整批失败",
          len(S.list_records("manuscripts")) == 2, len(S.list_records("manuscripts")))
finally:
    S.coll_dir = _o2
    S._REC_CACHE.clear()

# 日历链接不能指向本机/元数据地址，否则「测试日历」变成替人探测内网的工具
import services as _SV                                          # noqa: E402
for u_ in ["http://127.0.0.1:23119/api/", "http://localhost:9200/_cat",
           "http://169.254.169.254/latest/meta-data/"]:
    check(f"挡住 {u_[:36]}", bool(_SV._private_host(u_)), _SV._private_host(u_))
for u_ in ["https://outlook.office365.com/owa/calendar/x/calendar.ics",
           "http://192.168.1.20/cal.ics"]:
    check(f"放行 {u_[:36]}", not _SV._private_host(u_), _SV._private_host(u_))

print("=" * 62)
if FAIL:
    print(f"搜索与新功能测试：{len(FAIL)} 条不通过 ✗")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("搜索与新功能测试：全部通过 ✓")
