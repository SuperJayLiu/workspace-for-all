#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献索引体检

覆盖四种导入格式的解析、去重、搜索上限、跳转链接、导出回 .bib，
以及最要紧的一条：**性能**。

性能为什么要写进测试：把几千条文献按「一篇一个 md」塞进读文献页，
实测切页 2 秒、28581 个 DOM 节点，每次 render() 还重来一遍。
索引层就是为了绕开这件事，所以它的性能承诺必须被锁住，
以后谁改坏了要立刻红。
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import library as L                       # noqa: E402

FAIL = []


def check(name, cond, got=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"   实际={got}"))
    if not cond:
        FAIL.append(name)


print("=" * 62)
print("BibTeX 解析")
BIB = r"""
@article{he2013intermediary,
  title = {Intermediary Asset Pricing},
  author = {He, Zhiguo and Krishnamurthy, Arvind},
  journal = {American Economic Review},
  year = {2013},
  doi = {10.1257/aer.103.2.732},
  file = {Full Text:/Users/me/Zotero/storage/ABC/He_2013.pdf:PDF}
}
@inproceedings{muller2020,
  title = {{\"O}sterreich, Caf{\'e}s and \{Nested\} Braces},
  author = {M{\"u}ller, Hans and Do{\v{s}}en, Ana},
  booktitle = {Proceedings of Something},
  year = {2020},
  doi = {https://doi.org/10.1000/xyz123}
}
@misc{noyear, title = {No Year At All}, author = {Nobody}}
"""
bib = L.parse_bibtex(BIB)
check("解析出 3 条", len(bib) == 3, len(bib))
check("标题正确", bib[0]["t"] == "Intermediary Asset Pricing", bib[0]["t"])
check("作者拆开", bib[0]["a"] == ["He, Zhiguo", "Krishnamurthy, Arvind"], bib[0]["a"])
check("DOI 剥掉花括号", bib[0]["d"] == "10.1257/aer.103.2.732", bib[0]["d"])
check("从 file 字段认出本地 PDF", bib[0]["p"].endswith("He_2013.pdf"), bib[0]["p"])
check("LaTeX 重音还原（Österreich / Cafés）",
      "Österreich" in bib[1]["t"] and "Cafés" in bib[1]["t"], bib[1]["t"])
check("转义花括号 \\{ \\} 保留成真括号", "{Nested}" in bib[1]["t"], bib[1]["t"])
check("作者里的重音（Müller / Došen）",
      bib[1]["a"] == ["Müller, Hans", "Došen, Ana"], bib[1]["a"])
check("DOI 是完整网址时剥成裸 DOI", bib[1]["d"] == "10.1000/xyz123", bib[1]["d"])
check("没有年份也不崩", bib[2]["y"] is None, bib[2]["y"])
check("citekey 保留（复制 \\cite{} 要用）", bib[0]["c"] == "he2013intermediary", bib[0]["c"])

print("\nRIS 解析（EndNote / Web of Science / 知网）")
RIS = """TY  - JOUR
TI  - Liquidity and Leverage
AU  - Adrian, Tobias
AU  - Shin, Hyun Song
PY  - 2010
JO  - Journal of Financial Intermediation
DO  - 10.1016/j.jfi.2008.12.002
UR  - https://example.org/a
KW  - liquidity
ER  -

TY  - CONF
TI  - A Conference Paper
AU  - Someone, A
PY  - 2021
T2  - Proceedings of X
ER  -
"""
ris = L.parse_ris(RIS)
check("解析出 2 条", len(ris) == 2, len(ris))
check("标题 / 年份 / 期刊", (ris[0]["t"], ris[0]["y"], ris[0]["j"]) ==
      ("Liquidity and Leverage", 2010, "Journal of Financial Intermediation"),
      (ris[0]["t"], ris[0]["y"], ris[0]["j"]))
check("多个 AU 合成作者表", ris[0]["a"] == ["Adrian, Tobias", "Shin, Hyun Song"], ris[0]["a"])
check("会议论文类型映射", ris[1]["ty"] == "conferencePaper", ris[1]["ty"])

print("\nCSL-JSON 解析（Zotero / Better BibTeX 原生导出）")
CSL = """[
 {"id":"brunnermeier2009","type":"article-journal",
  "title":"Market Liquidity and Funding Liquidity",
  "author":[{"family":"Brunnermeier","given":"Markus"},{"family":"Pedersen","given":"Lasse"}],
  "issued":{"date-parts":[[2009]]},
  "container-title":"Review of Financial Studies","DOI":"10.1093/rfs/hhn098"},
 {"id":"nolit","title":"Institutional Author Paper",
  "author":[{"literal":"World Bank"}],"issued":{"raw":"2018-03"}}
]"""
csl = L.parse_csl_json(CSL)
check("解析出 2 条", len(csl) == 2, len(csl))
check("family/given 合成", csl[0]["a"] == ["Brunnermeier, Markus", "Pedersen, Lasse"], csl[0]["a"])
check("date-parts 取年份", csl[0]["y"] == 2009, csl[0]["y"])
check("机构作者用 literal", csl[1]["a"] == ["World Bank"], csl[1]["a"])
check("raw 日期也能取到年份", csl[1]["y"] == 2018, csl[1]["y"])

print("\nnbib 解析（PubMed）")
NBIB = """PMID- 12345678
TI  - A Medical Paper About Something
      Important
AU  - Smith J
AU  - Doe A
DP  - 2019 Mar
JT  - The Lancet
LID - 10.1016/S0140-6736(19)30000-0 [doi]
MH  - Humans
"""
nb = L.parse_nbib(NBIB)
check("解析出 1 条", len(nb) == 1, len(nb))
check("折行标题被接上", nb and nb[0]["t"].endswith("Important"), nb[0]["t"] if nb else "")
check("从 LID 取 DOI", nb and nb[0]["d"] == "10.1016/s0140-6736(19)30000-0", nb[0]["d"] if nb else "")
check("PMID 变成可点链接", nb and "pubmed" in nb[0]["u"], nb[0]["u"] if nb else "")

print("\n格式自动识别")
check("认出 bib", L.sniff(BIB) == "bib", L.sniff(BIB))
check("认出 ris", L.sniff(RIS) == "ris", L.sniff(RIS))
check("认出 csl", L.sniff(CSL) == "csl", L.sniff(CSL))
check("认出 nbib", L.sniff(NBIB) == "nbib", L.sniff(NBIB))
check("按扩展名也能认", L.sniff("随便什么", "x.ris") == "ris", L.sniff("x", "x.ris"))
check("认不出就明说", L.sniff("这就是一段普通中文，什么都不是") == "", L.sniff("普通中文"))

print("\n索引：写入、去重、搜索")
import tempfile                            # noqa: E402
tmp = Path(tempfile.mkdtemp()) / "library.jsonl"
ix = L.Index(tmp)
st = ix.add_many(bib + ris + csl + nb, source="mix")
check("首次导入全部进库", st["added"] == 8, st)
st2 = ix.add_many(bib, source="bib")
check("同一批再导一次不会翻倍", st2["added"] == 0 and st2["total"] == 8, st2)
check("重复的算作补全", st2["updated"] == 3, st2)

# DOI 相同但标题写法不同 → 应认成同一篇
dupe = [L._mk_item(t="INTERMEDIARY ASSET PRICING (revised)", d="10.1257/aer.103.2.732", y=2013)]
st3 = ix.add_many(dupe)
check("DOI 相同即同一篇", st3["added"] == 0, st3)
# 没有 DOI，靠标题+年份
dupe2 = [L._mk_item(t="a conference paper", y=2021)]
st4 = ix.add_many(dupe2)
check("无 DOI 时按标题+年份去重", st4["added"] == 0, st4)

r = ix.search(q="liquidity")
check("搜索命中", r["total"] >= 2, r["total"])
r = ix.search(q="liquidity funding")
check("多个词是 AND 不是 OR", r["total"] == 1, r["total"])
r = ix.search(q="Brunnermeier")
check("能搜作者", r["total"] == 1, r["total"])
r = ix.search(q="he2013intermediary")
check("能搜 citekey", r["total"] == 1, r["total"])
r = ix.search(q="", limit=999999)
check("单次返回被上限挡住", len(r["items"]) <= L.SEARCH_CAP, len(r["items"]))
r = ix.search(q="肯定搜不到的词")
check("搜不到返回空而不是报错", r["total"] == 0 and r["items"] == [], r)

print("\n跳转链接：按用户实际在用的软件决定")
zi = L._mk_item(k="ABCD1234", t="X", s="zotero", d="10.1/x", u="https://e.org")
t_z = L.open_targets(zi, "zotero")
check("Zotero 用户第一个是 zotero://",
      t_z[0]["url"] == "zotero://select/library/items/ABCD1234", t_z[0]["url"])
gi = L._mk_item(k="EFGH", t="X", s="zotero", lib="98765")
check("群组库用 groups 形式",
      L.open_targets(gi, "zotero")[0]["url"] == "zotero://select/groups/98765/items/EFGH",
      L.open_targets(gi, "zotero")[0]["url"])
t_n = L.open_targets(zi, "none")
check("不用文献管理器的人不会拿到 zotero:// 死链",
      all(not x["url"].startswith("zotero://") for x in t_n), [x["url"] for x in t_n])
check("退回 DOI", t_n[0]["url"] == "https://doi.org/10.1/x", t_n[0]["url"])
bare = L._mk_item(t="Some Paper With Nothing Else")
check("什么链接都没有时给个 Google Scholar 兜底",
      L.open_targets(bare, "none")[0]["kind"] == "search",
      L.open_targets(bare, "none"))
pdfi = L._mk_item(t="X", p="/Users/me/a.pdf")
# 关键：**不能**是 file://。浏览器禁止 http 页面跳 file://，点了完全没反应，
# 所以必须走服务端把文件读出来回传。
u_pdf = L.open_targets(pdfi, "none")[0]["url"]
check("本地 PDF 不再是 file:// 死链", not u_pdf.startswith("file://"), u_pdf)
check("改成走服务端接口", u_pdf.startswith("/api/library/file?path="), u_pdf)

print("\n导出 .bib 的字段要给全（缺卷期页码就没法直接投稿用）")
rich = L._mk_item(t="A Paper", a=["Smith, J."], y=2020, j="Journal of Finance",
                  d="10.1/x", vol="75", iss="3", pg="1123-1160", pub="Wiley",
                  ty="journalArticle", c="smith2020")
bib1 = L.to_bibtex([rich])
for f in ("volume = {75}", "number = {3}", "pages = {1123-1160}", "doi = {10.1/x}"):
    check(f"含 {f}", f in bib1, bib1[:200])
conf = L._mk_item(t="A Talk", a=["Doe, A."], y=2021, j="Proceedings of X",
                  ty="conferencePaper", c="doe2021")
bib2 = L.to_bibtex([conf])
check("会议论文用 booktitle 而不是 journal",
      "booktitle = {Proceedings of X}" in bib2 and "journal =" not in bib2, bib2[:200])
check("会议论文类型是 inproceedings", "@inproceedings{" in bib2, bib2[:60])
back2 = L.parse_bibtex(bib1)
check("补全字段后仍能被自己解析回来", len(back2) == 1 and back2[0]["t"] == "A Paper", back2)

print("\n导出：进得来也要出得去")
out = L.to_bibtex(ix.load()[:3])
back = L.parse_bibtex(out)
check("导出的 .bib 能被自己重新解析", len(back) == 3, len(back))
check("往返之后标题没丢", back[0]["t"] == ix.load()[0]["t"], (back[0]["t"], ix.load()[0]["t"]))

print("\n坏数据不能把库搞垮")
check("空文本解析成空", L.parse_bibtex("") == [] and L.parse_ris("") == [], "")
check("坏 JSON 不抛异常", L.parse_csl_json("{这不是 json") == [], "")
check("半截 BibTeX 不抛异常", isinstance(L.parse_bibtex("@article{x, title={没有结尾"), list), "")
# 索引文件里混进坏行
with tmp.open("a", encoding="utf-8") as fh:
    fh.write("这不是 json\n{坏的\n")
ix2 = L.Index(tmp)
check("索引里的坏行被跳过而不是整库打不开", len(ix2.load()) == 8, len(ix2.load()))

print("\n性能（索引层存在的全部意义）")
N = 5000
big = [L._mk_item(k=f"K{i}", t=f"Paper number {i} about liquidity and momentum",
                  a=[f"Author{i % 300}, X."], y=1990 + i % 36,
                  j="Journal of Finance", d=f"10.9999/perf.{i}") for i in range(N)]
tmp2 = Path(tempfile.mkdtemp()) / "big.jsonl"
ixb = L.Index(tmp2)
t0 = time.time()
ixb.add_many(big, source="perf")
t_add = time.time() - t0
check(f"{N} 条写入 < 10 秒", t_add < 10, f"{t_add:.2f}s")

ixc = L.Index(tmp2)
t0 = time.time()
ixc.load()
t_load = time.time() - t0
check(f"{N} 条冷加载 < 3 秒", t_load < 3, f"{t_load:.2f}s")

t0 = time.time()
for _ in range(20):
    ixc.search(q="liquidity momentum", limit=50)
t_s = (time.time() - t0) / 20
check(f"热搜索单次 < 100ms（实测 {t_s*1000:.1f}ms）", t_s < 0.1, f"{t_s*1000:.1f}ms")

t0 = time.time()
for _ in range(20):
    ixc.search(q="", limit=50)
t_e = (time.time() - t0) / 20
check(f"空查询翻页单次 < 100ms（实测 {t_e*1000:.1f}ms）", t_e < 0.1, f"{t_e*1000:.1f}ms")

r = ixc.search(q="", limit=50)
check("永远只返回一页，不会把 5000 条全吐出来", len(r["items"]) == 50 and r["total"] == N,
      (len(r["items"]), r["total"]))


print("\n十六、文件夹一键导入：.bib / .ris / PDF 一起收")
import pdfmeta as PM                                    # noqa: E402
import zlib as _zl                                      # noqa: E402
_pf = Path(tempfile.mkdtemp())
(_pf / "proj").mkdir(); (_pf / "文献").mkdir()
(_pf / "proj" / "ref.bib").write_text("""
@article{he2013,
  title = {Intermediary Asset Pricing}, author = {He, Zhiguo and Krishnamurthy, Arvind},
  journal = {American Economic Review}, year = {2013}, doi = {10.1257/aer.103.2.732}}
@article{ad2010,
  title = {Liquidity and Leverage}, author = {Adrian, Tobias},
  year = {2010}, doi = {10.1016/j.jfi.2008.12.002}}
""", encoding="utf-8")
(_pf / "文献" / "wos.ris").write_text(
    "TY  - JOUR\nTI  - Intermediary Asset Pricing\nAU  - He, Zhiguo\nPY  - 2013\n"
    "DO  - 10.1257/aer.103.2.732\nER  -\n", encoding="utf-8")
# 不相干的 json 不该被当题录
(_pf / "文献" / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")


def _mkpdf(path, title=None, author=None, year=None, body="Body text."):
    info = b""
    if title:
        info = ("<< /Title (" + title + ")" + (" /Author (" + author + ")" if author else "")
                + (" /CreationDate (D:%s0101000000)" % year if year else "") + " >>").encode("latin-1", "replace")
    comp = _zl.compress(("BT /F1 12 Tf 72 720 Td (" + body + ") Tj ET").encode())
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(comp)).encode() + b" /Filter /FlateDecode >>\nstream\n" + comp + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    if info:
        objs.append(info)
    out = bytearray(b"%PDF-1.4\n"); offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += str(i).encode() + b" 0 obj\n" + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for o in offs:
        out += ("%010d 00000 n \n" % o).encode()
    tr = b"<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R"
    if info:
        tr += b" /Info " + str(len(objs)).encode() + b" 0 R"
    out += b"trailer\n" + tr + b" >>\nstartxref\n" + str(x).encode() + b"\n%%EOF\n"
    Path(path).write_bytes(bytes(out))


_mkpdf(_pf / "文献" / "He_2013.pdf", "Intermediary Asset Pricing", "He, Zhiguo", 2013)
_mkpdf(_pf / "文献" / "Barber_2000.pdf", "Trading Is Hazardous to Your Wealth", "Barber, Brad", 2000)
_mkpdf(_pf / "文献" / "download_a.pdf")           # 抠不出元数据
_mkpdf(_pf / "文献" / "download_b.pdf")           # 同上，内容一样

sc = L.scan_folder_items(_pf, pdfmeta=PM)
check("扫得动", sc.get("ok"), sc.get("detail"))
check("认出 .bib 里的 2 条 + .ris 里的 1 条", sc["counts"]["bib"] == 3, sc["counts"])
check("认出 4 个 PDF", sc["counts"]["pdf"] == 4, sc["counts"])
check("不相干的 json 没被当题录",
      all("settings.json" not in f["file"] or f["n"] == 0 for f in sc["files"]), sc["files"])
check("元数据不全的被标了「待补全」", sc["todo"] >= 2, sc["todo"])

_ixf = L.Index(Path(tempfile.mkdtemp()) / "f.jsonl")
_order = {"pdf": 0}
_st = _ixf.add_many(sorted(sc["items"], key=lambda x: _order.get(x.get("s") or "", 1)))
_all = _ixf.load()
_iap = [x for x in _all if "Intermediary Asset" in (x.get("t") or "")]
check("同一篇论文只留一条（.bib/.ris/PDF 三处合并）", len(_iap) == 1, len(_iap))
check("合并后 DOI 来自题录文件", _iap[0].get("d") == "10.1257/aer.103.2.732", _iap[0].get("d"))
check("合并后本地 PDF 路径还在（点开能直接看）", bool(_iap[0].get("p")), _iap[0].get("p"))
check("记下了它来自哪几处", set(_iap[0].get("srcs") or []) >= {"pdf", "bib"}, _iap[0].get("srcs"))
_junk = [x for x in _all if x.get("todo_title")]
check("两个抠不出元数据的 PDF **没有**被并成一条（并了就等于丢一篇）",
      len(_junk) == 2, [x.get("p") for x in _junk])
check("它们各自留着自己的文件路径",
      len({x.get("p") for x in _junk}) == 2, [x.get("p") for x in _junk])

_st2 = _ixf.add_many(sorted(L.scan_folder_items(_pf, pdfmeta=PM)["items"],
                            key=lambda x: _order.get(x.get("s") or "", 1)))
check("再扫一遍不会重复加", _st2["added"] == 0 and _st2["total"] == _st["total"], _st2)

# Zotero 后到要压过 PDF 抠出来的字段
_ixf.add_many([L._mk_item(k="ZK", t="Trading Is Hazardous to Your Wealth",
                          a=["Barber, Brad M.", "Odean, Terrance"], y=2000,
                          j="Journal of Finance", d="10.1111/0022-1082.00226")], source="zotero")
_b = [x for x in _ixf.load() if "Hazardous" in (x.get("t") or "")][0]
check("Zotero 的信息压过 PDF 的", _b.get("s") == "zotero" and _b.get("d"), (_b.get("s"), _b.get("d")))
check("Zotero 覆盖后仍保留本地 PDF 路径", bool(_b.get("p")), _b.get("p"))
check("补全之后「待补全」标记消失", not _b.get("todo"), _b.get("todo"))
check("但仍记得它也来自 PDF 文件夹", "pdf" in (_b.get("srcs") or []), _b.get("srcs"))

# 反向：先 Zotero 后 PDF，不能被 PDF 的烂元数据覆盖
_ix2 = L.Index(Path(tempfile.mkdtemp()) / "g.jsonl")
_ix2.add_many([L._mk_item(k="ZK2", t="Liquidity and Leverage", a=["Adrian, Tobias"],
                          y=2010, j="Journal of Financial Intermediation",
                          d="10.1016/j.jfi.2008.12.002")], source="zotero")
_ix2.add_many([L._mk_item(t="Liquidity and Leverage", y=2010, p="/x/LL.pdf", s="pdf")])
_l = _ix2.load()[0]
check("PDF 不会把 Zotero 的期刊字段冲掉", _l.get("j") == "Journal of Financial Intermediation", _l.get("j"))
check("PDF 只是把本地路径挂上去", _l.get("p") == "/x/LL.pdf", _l.get("p"))
check("来源仍然是 Zotero", _l.get("s") == "zotero", _l.get("s"))

# 大目录不能把整块盘翻一遍
_big = Path(tempfile.mkdtemp())
for i in range(30):
    _mkpdf(_big / f"p{i}.pdf", f"Paper {i}", "A", 2020)
_pdfs, _capped = PM.iter_pdfs(_big, limit=5)
check("PDF 扫描有上限", len(_pdfs) == 5, len(_pdfs))

print("\n十七、年份类型必须统一（混着 str 和 int，一排序整个搜索就 500）")
# 各来源给的类型不一样：解析器给 int，pdfmeta 从 PDF 元数据里抠出来是字符串。
# 这个 bug 只有在「真的导过 PDF」的库里才犯，普通测试库碰不到。
_iy = L.Index(Path(tempfile.mkdtemp()) / "y.jsonl")
_iy.add_many([
    L._mk_item(t="Int Year", y=2013, d="10.1/a"),
    L._mk_item(t="Str Year", y="2010", d="10.1/b"),
    L._mk_item(t="Empty Year", y="", d="10.1/c"),
    L._mk_item(t="Garbage Year", y="n.d.", d="10.1/d"),
    L._mk_item(t="PDF Date", y="D:20200101000000", d="10.1/e"),
])
_ys = [x.get("y") for x in _iy.load()]
check("存进去的年份全是 int 或 None",
      all(v is None or isinstance(v, int) for v in _ys), _ys)
check("字符串年份被转成了数字", 2010 in _ys, _ys)
check("PDF 那种日期格式也认得出年份", 2020 in _ys, _ys)
check("认不出的留 None，不硬编一个", _ys.count(None) == 2, _ys)
for _s in ("year", "added", "title"):
    try:
        _r = _iy.search(sort=_s)
        check(f"按{_s}排序不炸", _r["total"] == 5, _r["total"])
    except Exception as e:
        check(f"按{_s}排序不炸", False, f"{type(e).__name__}: {e}")
check("年份区间筛选不炸", _iy.search(year_from=2011, year_to=2021)["total"] == 2,
      _iy.search(year_from=2011, year_to=2021)["total"])
# 就算历史数据里已经混进了字符串，也不能让搜索整个挂掉
_bad = Path(tempfile.mkdtemp()) / "bad.jsonl"
_bad.write_text('{"k":"a","t":"X","y":"2001","d":"10.1/x","s":"pdf"}\n'
                '{"k":"b","t":"Y","y":2002,"d":"10.1/y","s":"bib"}\n', encoding="utf-8")
try:
    _rb = L.Index(_bad).search(sort="year")
    check("老库里混着字符串年份，搜索照样能用", _rb["total"] == 2, _rb["total"])
except Exception as e:
    check("老库里混着字符串年份，搜索照样能用", False, f"{type(e).__name__}: {e}")

print("\n十七·续、只看待补全")
_it = L.Index(Path(tempfile.mkdtemp()) / "t.jsonl")
_it.add_many([L._mk_item(t="齐全的", y=2020, d="10.1/ok"),
              dict(L._mk_item(t="缺东西的", y=2021, d="10.1/no"), todo="DOI、年份")])
check("只看待补全 → 只出那一条", _it.search(todo=True)["total"] == 1, _it.search(todo=True)["total"])
check("只看齐全的 → 只出另一条", _it.search(todo=False)["total"] == 1, _it.search(todo=False)["total"])
check("不筛就都出", _it.search()["total"] == 2, _it.search()["total"])

print("=" * 62)
if FAIL:
    print(f"文献索引测试：{len(FAIL)} 条不通过 ✗")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("文献索引测试：全部通过 ✓")
