#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学术雷达 · 抓取、候选池、校验、进库

这一套的核心是**第三节**：确认 AI 编造的东西进不了周报。

抓取本身依赖外网，测试里不联网 —— 用真实 API 响应结构做的样本代替。
真实连通性由 `python3 scripts/radar.py --selftest` 在用户自己机器上验。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import library as L                      # noqa: E402
import radar as R                        # noqa: E402
import services as sv                    # noqa: E402

FAIL = []


def check(name, cond, got=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"   实际={got}"))
    if not cond:
        FAIL.append(name)


print("=" * 62)
print("一、解析：真实 API 响应结构 → 统一格式")
# 这是 Crossref 真实返回的形状（字段名、嵌套都照抄自实际响应）
CR = {
    "DOI": "10.3386/w14517",
    "title": ["Intermediary Asset Pricing"],
    "author": [{"given": "Zhiguo", "family": "He", "sequence": "first"},
               {"given": "Arvind", "family": "Krishnamurthy", "sequence": "additional"}],
    "issued": {"date-parts": [[2008, 12]]},
    "created": {"date-parts": [[2008, 12, 3]]},
    "type": "report",
    "publisher": "National Bureau of Economic Research",
}
it = sv._cr_item(CR, hit_by="intermediary", hit_kind="keyword")
check("标题取出来了", it["t"] == "Intermediary Asset Pricing", it["t"])
check("作者拼成了「名 姓」", it["a"] == ["Zhiguo He", "Arvind Krishnamurthy"], it["a"])
check("年份是数字", it["y"] == 2008, it["y"])
check("DOI 归一化成小写", it["d"] == "10.3386/w14517", it["d"])
check("NBER 的 DOI 前缀被认成 working paper", it["ty"] == "working_paper", it["ty"])
check("缺日的日期补成 01", it["date"] == "2008-12-01", it["date"])
check("记下了是哪个关键词命中的", it["hit_by"] == "intermediary", it["hit_by"])
check("期刊为空时退回出版方", "National Bureau" in it["j"], it["j"])
# 边界：字段缺失不能崩
for bad in [{}, {"title": []}, {"author": None}, {"issued": {}},
            {"issued": {"date-parts": [[]]}}, {"DOI": None}, {"title": [None]}]:
    try:
        sv._cr_item(bad)
        ok = True
    except Exception as e:
        ok = False
        got = f"{type(e).__name__}: {e}"
    check(f"残缺响应不崩 {json.dumps(bad, ensure_ascii=False)[:34]}", ok, locals().get("got", ""))

print("\n二、候选池：指纹、去重、状态")
pool = R.Pool(Path(tempfile.mkdtemp()) / "pool.jsonl")
A = {"t": "Liquidity and Leverage", "a": ["Tobias Adrian", "Hyun Song Shin"], "y": 2010,
     "d": "10.1016/j.jfi.2008.12.002", "src": "crossref", "date": "2010-07-01"}
B = {"t": "Financial Intermediaries and the Cross-Section of Asset Returns",
     "a": ["Tobias Adrian"], "y": 2014, "d": "10.1111/jofi.12189", "src": "crossref"}
st = pool.add([A, B], run_id="w1")
check("两条都入池", st["added"] == 2, st)
# 同一篇从另一个源又来一次：不该重复，而且要补上缺的字段
A2 = dict(A, src="nber", abstract="We build a model...", d="")
st2 = pool.add([A2], run_id="w1")
check("同一篇不重复入池", st2["added"] == 0 and st2["duplicate"] == 1, st2)
got = [x for x in pool.load() if "Liquidity" in x["t"]][0]
check("第二个源补上了摘要", bool(got.get("abstract")), got.get("abstract"))
check("记下了它来自哪几个源", set(got.get("srcs") or []) == {"crossref", "nber"}, got.get("srcs"))
check("DOI 没被空值冲掉", got.get("d") == "10.1016/j.jfi.2008.12.002", got.get("d"))
# 没 DOI 的靠标题+年份认
C = {"t": "Some Working Paper", "a": ["X"], "y": 2026, "src": "nber"}
pool.add([C], run_id="w1")
pool.add([dict(C, src="arxiv")], run_id="w1")
check("没 DOI 的也能靠标题去重", len([x for x in pool.load() if x["t"] == "Some Working Paper"]) == 1,
      len([x for x in pool.load() if x["t"] == "Some Working Paper"]))
check("连标题都没有的被跳过", pool.add([{"a": ["无名"]}])["skipped"] == 1, "")
check("坏数据不入池", pool.add([None, 123, "字符串"])["skipped"] == 3, "")
# 候选与状态
cands = pool.candidates(run_id="w1")
check("候选里都是没推过的", all(x["status"] == "new" for x in cands), "")
pool.mark([cands[0]["fp"]], "shown")
check("推过的会被标记", len([x for x in pool.load() if x["status"] == "shown"]) == 1, "")
check("推过的不再出现在候选里",
      cands[0]["fp"] not in {x["fp"] for x in pool.candidates(run_id="w1")}, "")

print("\n三、校验器：AI 编造的东西一条都不能进周报")
# —— 这是整套东西的关键。以下每一条都是模型真实会犯的错。
pool2 = R.Pool(Path(tempfile.mkdtemp()) / "p2.jsonl")
REAL = [
    {"t": "Intermediary Asset Pricing: New Evidence from Many Asset Classes",
     "a": ["Zhiguo He", "Bryan Kelly", "Asaf Manela"], "y": 2017,
     "j": "Journal of Financial Economics", "d": "10.1016/j.jfineco.2017.08.002"},
    {"t": "Liquidity and Leverage", "a": ["Tobias Adrian", "Hyun Song Shin"], "y": 2010,
     "j": "Journal of Financial Intermediation", "d": "10.1016/j.jfi.2008.12.002"},
    {"t": "A Macroeconomic Model with Financially Constrained Producers and Intermediaries",
     "a": ["Vadim Elenev", "Tim Landvoigt", "Stijn Van Nieuwerburgh"], "y": 2021,
     "j": "Econometrica", "d": "10.3982/ecta16438"},
]
pool2.add(REAL, run_id="w1")
fp = {x["t"]: R.fingerprint(x) for x in REAL}

good = [
    {"fp": fp["Liquidity and Leverage"], "title": "Liquidity and Leverage",
     "authors": ["Adrian", "Shin"], "year": 2010, "why": "跟中介约束直接相关"},
    # 排版差异（连字符、大小写）不该被误判成造假
    {"fp": fp["A Macroeconomic Model with Financially Constrained Producers and Intermediaries"],
     "title": "A Macroeconomic Model With Financially-Constrained Producers and Intermediaries",
     "authors": ["Elenev"], "year": 2021, "why": "宏观金融"},
    # 忘了带指纹但标题是真的 —— 也不该误判
    {"fp": "", "title": "Intermediary Asset Pricing: New Evidence from Many Asset Classes",
     "authors": ["He", "Kelly"], "year": 2017, "why": "经典"},
]
bad = [
    ("整篇论文不存在",
     {"fp": "doi:10.1111/jofi.13999",
      "title": "Intermediary Constraints and the Cross-Section of Currency Returns",
      "authors": ["Zhiguo He", "Arvind Krishnamurthy"], "year": 2024, "why": "最新"}),
    ("指纹是真的但标题换成了另一篇",
     {"fp": fp["Liquidity and Leverage"], "title": "Leverage Cycles and the Anxious Economy",
      "authors": ["Adrian"], "year": 2010, "why": "相关"}),
    ("塞了个没参与的大牌作者",
     {"fp": fp["Intermediary Asset Pricing: New Evidence from Many Asset Classes"],
      "title": "Intermediary Asset Pricing: New Evidence from Many Asset Classes",
      "authors": ["Zhiguo He", "John Cochrane"], "year": 2017, "why": "重要"}),
    ("年份被改（会让你引错）",
     {"fp": fp["A Macroeconomic Model with Financially Constrained Producers and Intermediaries"],
      "title": "A Macroeconomic Model with Financially Constrained Producers and Intermediaries",
      "authors": ["Elenev"], "year": 2016, "why": "宏观"}),
    ("整条是空壳",
     {"fp": "ti:0000000000000000", "title": "A Plausible Sounding Paper on Constraints",
      "authors": ["Someone Famous"], "year": 2025, "why": "看起来相关"}),
]
res = R.verify(good + [b[1] for b in bad], pool2)
check(f"真的三条全部放行（排版差异、缺指纹都不误伤）", res["stats"]["passed"] == 3,
      f"{res['stats']['passed']} 条：{[x['t'][:30] for x in res['ok']]}")
check(f"编造/篡改五条全部拦下", res["stats"]["dropped"] == 5, res["stats"])
reasons = [r["reason"] for r in res["rejected"]]
for label, _ in bad:
    check(f"拦下：{label}", len(res["rejected"]) == 5, "")
    break
check("给出了具体拦截理由", len(set(reasons)) >= 3, reasons)
check("周报里会如实交代丢了几条", "没通过核对" in R.verdict_line(res), R.verdict_line(res))
check("放行的用的是池子里的原始记录（引用不可能被改）",
      all(x["t"] in {r["t"] for r in REAL} for x in res["ok"]),
      [x["t"][:40] for x in res["ok"]])
check("AI 给的理由被保留下来", all("why" in x for x in res["ok"]), "")
# 空输入 / 脏输入
for junk in ([], None, [None], ["字符串"], [{}], [{"fp": None}]):
    r2 = R.verify(junk, pool2)
    check(f"脏输入不崩 {json.dumps(junk, ensure_ascii=False)[:22]}", isinstance(r2.get("ok"), list), r2)
check("全是垃圾时一条都不放行", R.verify([{}, {"fp": "x"}], pool2)["stats"]["passed"] == 0, "")

# ---------------------------------------------------------------------------
print("\n三之二、换个字段名写，检查一样要生效")
# 技能里写的是 title/authors/year，但候选池自己用的是 t/a/y。
# 模型对着池子照抄短名是很自然的事。如果校验器只认长名，后果不是报错，
# 而是**那条检查静悄悄地不跑了** —— 看起来在把关，实际上全放行。
# 这比不做检查更糟，因为周报会理直气壮地说「已核对」。
alias_bad = {"fp": fp["Intermediary Asset Pricing: New Evidence from Many Asset Classes"],
             "t": "Intermediary Asset Pricing: New Evidence from Many Asset Classes",
             "a": ["Zhiguo He", "Ben Bernanke"], "y": 2017, "why": "重要"}
ra = R.verify([alias_bad], pool2)
check("用短字段名 a 塞假作者，照样拦得下", ra["stats"]["passed"] == 0,
      f"放行了 {ra['stats']['passed']} 条：{ra['rejected']}")
check("拦截理由说的是作者",
      any("作者" in x["reason"] for x in ra["rejected"]), ra["rejected"])

alias_good = {"fp": fp["Liquidity and Leverage"], "t": "Liquidity and Leverage",
              "a": ["Tobias Adrian", "Hyun Song Shin"], "y": 2010, "why": "相关"}
check("短字段名写对了也不该误伤", R.verify([alias_good], pool2)["stats"]["passed"] == 1, "")

print("\n三之三、只给 DOI、没给指纹")
# DOI 是全球唯一的，是最硬的证据。模型忘了抄 fp 但给了 DOI 很常见。
# 不拿它去查，就等于把最硬的证据扔了、退化成模糊的标题比对，
# 于是真论文被判成「编的」—— 周报还会煞有介事地说「AI 编了一条」。
# 误伤和放水一样坏：一个让你错过真东西，一个让你读到假东西。
doi_only = {"d": "10.1016/j.jfi.2008.12.002",
            "title": "Liquidity and Leverage", "authors": ["Adrian"], "year": 2010, "why": "x"}
rd = R.verify([doi_only], pool2)
check("只给 DOI 也能在池子里查到（不误判成造假）", rd["stats"]["passed"] == 1, rd["rejected"])

# 真 DOI + 被改写的标题：应当因为「标题对不上」被拦，而不是「池子里没有」——
# 理由说错了，人就没法判断到底是模型编的还是抓取漏了。
doi_retitled = {"d": "10.1016/j.jfi.2008.12.002",
                "title": "Leverage Cycles and the Anxious Economy",
                "authors": ["Adrian"], "year": 2010, "why": "x"}
rt = R.verify([doi_retitled], pool2)
check("真 DOI 配改写过的标题：拦下", rt["stats"]["passed"] == 0, rt)
check("而且理由说的是标题对不上，不是「池子里没有」",
      any("标题" in x["reason"] for x in rt["rejected"]),
      [x["reason"] for x in rt["rejected"]])

# 假 DOI 不能因为「格式像 DOI」就蒙混过关
fake_doi = {"d": "10.1016/j.jfineco.2026.99.999", "title": "A Very Plausible Title on Constraints",
            "authors": ["Zhiguo He"], "year": 2026, "why": "x"}
check("编的 DOI 查不到就是查不到", R.verify([fake_doi], pool2)["stats"]["passed"] == 0, "")

print("\n三之四、短姓氏不能靠子串蒙混")
# 曾经的写法是把真实作者拼成一整个字符串，再看姓氏在不在里面。
# 于是 "He" 会在 "Ashenfelter" 里命中 —— 而 He / Li / Xu / Wu 这些
# 恰恰是最需要盯住的一类名字。必须按词块比，不能按子串比。
pool3 = R.Pool(Path(tempfile.mkdtemp()) / "p3.jsonl")
pool3.add([{"t": "Estimating the Payoff to Schooling", "a": ["Orley Ashenfelter", "Alan Krueger"],
            "y": 1994, "j": "AER", "d": "10.9999/aer.1994.1"}], run_id="w1")
sub = {"d": "10.9999/aer.1994.1", "title": "Estimating the Payoff to Schooling",
       "authors": ["Orley Ashenfelter", "Zhiguo He"], "year": 1994, "why": "x"}
rs = R.verify([sub], pool3)
check("姓 He 不会因为 Ashenfelter 里有 he 就被放行", rs["stats"]["passed"] == 0,
      f"放行了：{rs['ok']}")

print("\n四、进库：合并到文献索引，不覆盖你自己整理的东西")
ix = L.Index(Path(tempfile.mkdtemp()) / "lib.jsonl")
# 先有一条你从 Zotero 同步来的，字段是你整理过的
ix.add_many([L._mk_item(k="ZK", t="Liquidity and Leverage", a=["Adrian, Tobias", "Shin, Hyun Song"],
                        y=2010, j="J. Fin. Intermediation（我改过的简称）",
                        d="10.1016/j.jfi.2008.12.002")], source="zotero")
picked = [L._mk_item(t=x["t"], a=x["a"], y=x["y"], j=x["j"], d=x["d"]) for x in res["ok"]]
st3 = ix.add_many(picked, source="radar")
check("新的进来了", st3["added"] >= 1, st3)
ll = [x for x in ix.load() if "Liquidity" in x["t"]][0]
check("同一篇不会变成两条", len([x for x in ix.load() if "Liquidity" in x["t"]]) == 1, "")
check("雷达不覆盖你从 Zotero 整理过的字段",
      "我改过的简称" in (ll.get("j") or ""), ll.get("j"))
check("来源仍然记作 zotero（雷达优先级更低）", ll.get("s") == "zotero", ll.get("s"))
check("但记下了雷达也看到过它", "radar" in (ll.get("srcs") or []), ll.get("srcs"))

print("\n四之二、走真的 HTTP 接口（AI 实际打交道的是这一层）")
# 上面几节测的是 radar.py 这个模块。但 AI 是通过 /api/radar/submit 跟它说话的，
# 中间隔着一层路由 —— 那一层曾经把 accepted 里的作者、年份、期刊都裁掉了，
# 只留 fp/t/d/u。模块测试全绿，实际却让周报没法写引用，只能凭印象补作者，
# 而「凭印象补」正是这整套校验要挡的事。所以这一层必须单独测。
import shutil, subprocess, time, urllib.request, urllib.error, socket   # noqa: E402

HPORT = 8808


def _free(port):
    s = socket.socket(); s.settimeout(0.8)
    try:
        s.connect(("127.0.0.1", port)); return False
    except OSError:
        return True
    finally:
        s.close()


if not _free(HPORT):
    print(f"  ! 端口 {HPORT} 被占着，跳过 HTTP 这一节"
          f"（先跑 pkill -f 'server.py --port {HPORT}'）")
else:
    WORK = Path(tempfile.mkdtemp(prefix="radar-http-")) / "ws"
    shutil.copytree(ROOT, WORK, ignore=shutil.ignore_patterns(
        "__pycache__", ".git", "local", "tests", "*.pyc", "*.zip"))
    # 用我们自己的池子，别用工作台里可能已有的
    (WORK / "data/_claude").mkdir(parents=True, exist_ok=True)
    hp = R.Pool(WORK / "data/_claude/radar-pool.jsonl")
    hp.add(REAL, run_id="w1")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(HPORT), "--no-open"],
                            cwd=str(WORK), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        BASE = f"http://127.0.0.1:{HPORT}"
        for _ in range(40):
            try:
                urllib.request.urlopen(BASE + "/api/ping", timeout=2).read()
                break
            except Exception:
                time.sleep(0.5)

        def post(path, obj):
            req = urllib.request.Request(
                BASE + path, data=json.dumps(obj).encode(),
                headers={"Content-Type": "application/json", "Origin": BASE})
            try:
                with urllib.request.urlopen(req, timeout=30) as f:
                    return f.status, json.loads(f.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode() or "{}")

        st, r = post("/api/radar/submit", {"picks": [
            {"fp": fp["Liquidity and Leverage"], "title": "Liquidity and Leverage",
             "authors": ["Adrian", "Shin"], "year": 2010, "why": "相关"},
            {"title": "A Paper That Does Not Exist At All", "year": 2026, "why": "编的"},
        ], "ingest": False})
        check("接口通", st == 200 and r.get("ok"), f"{st} {str(r)[:120]}")
        acc = r.get("accepted") or []
        check("真的那条放行了", len(acc) == 1, r)
        if acc:
            a = acc[0]
            # 引用要素一个都不能少 —— 少了周报就只能靠模型的记忆去补
            for k, label in (("t", "标题"), ("a", "作者"), ("y", "年份"),
                             ("j", "期刊"), ("d", "DOI"), ("fp", "指纹")):
                check(f"回给 AI 的记录带着{label}", bool(a.get(k)), a)
            check("作者是池子里的原文，不是 AI 复述的那两个姓",
                  a.get("a") == ["Tobias Adrian", "Hyun Song Shin"], a.get("a"))
            check("AI 写的理由保留着", a.get("why") == "相关", a.get("why"))
        rej = r.get("rejected") or []
        check("编的那条被拦下", len(rej) == 1, rej)
        check("拦下的能看出是哪一条（不然没法判断是编的还是抓漏了）",
              bool(rej and rej[0].get("t")), rej)
        check("有一句给周报用的交代", "没通过核对" in (r.get("note") or ""), r.get("note"))

        # 脏输入不能把接口打成 500
        for junk in ({"picks": "不是列表"}, {"picks": [1, 2, 3]}, {"picks": [{"fp": {}}]},
                     {}, {"picks": [None]}):
            st2, _ = post("/api/radar/submit", junk)
            check(f"脏输入不至于 500：{json.dumps(junk, ensure_ascii=False)[:30]}",
                  st2 < 500, st2)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(WORK.parent, ignore_errors=True)

print("\n五、抓取失败必须如实说，不能拿旧数据充数")
r = sv.radar_selftest(["crossref", "nber", "arxiv"])
check("自检返回每个源的状态", len(r["sources"]) == 3, r)
check("每条都有明确的 ok 判定", all(isinstance(x["ok"], bool) for x in r["sources"]), "")
check("有一句人话总结", bool(r.get("summary")), r.get("summary"))
# 自检不能虚报成功：连不上的源 n 必须是 0 且 ok 为假
for s in r["sources"]:
    if not s["ok"]:
        check(f"{s['source']} 连不上时条数是 0（不虚报）", s["n"] == 0, s)

print("=" * 62)
if FAIL:
    print(f"学术雷达测试：{len(FAIL)} 条不通过 ✗")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("学术雷达测试：全部通过 ✓")
