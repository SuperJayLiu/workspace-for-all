#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
演示数据生成器 · Demo seed

给每个模块都造一份互相自洽的模拟数据，用来演示和自测：
稿件生命周期、期刊档案、已发表、会议、文献与复习队列、闯关、想法画布、
日程、写作进展、AI 报告、复盘、以及生活线（饮食/运动/开支/纪念日/清单/杂务）。

  python3 scripts/demo_seed.py --write        写入
  python3 scripts/demo_seed.py --write --wipe 先清掉旧的演示数据再写
  python3 scripts/demo_seed.py --clean        只清掉演示数据

所有记录 id 一律以 demo- 开头，frontmatter 里带 demo: true，
所以清理时不会误伤你自己的真实记录。

注意：这个脚本只写「进 git 的学术数据」和「不进 git 的生活数据」，
不碰密钥、不碰配置、不碰 local/backups。
"""
import argparse
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOCAL = ROOT / "local"

random.seed(20260731)
TODAY = date.today()


def d(off):
    return (TODAY + timedelta(days=off)).isoformat()


def dt(off, hh=9, mm=0):
    return (datetime.combine(TODAY + timedelta(days=off), datetime.min.time())
            .replace(hour=hh, minute=mm)).isoformat(timespec="seconds")


def yaml_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return '""'
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if "\n" in s:
        return "|\n" + "\n".join("  " + ln for ln in s.split("\n"))
    if any(c in s for c in ':#{}[]",\'') or s.strip() != s or s == "":
        return json.dumps(s, ensure_ascii=False)
    return s


def dump(rec, body=""):
    lines = ["---"]
    for k, v in rec.items():
        if isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            elif all(isinstance(x, dict) for x in v):
                lines.append(f"{k}:")
                for item in v:
                    first = True
                    for kk, vv in item.items():
                        lines.append(("  - " if first else "    ") + f"{kk}: {yaml_val(vv)}")
                        first = False
            else:
                lines.append(f"{k}:")
                for x in v:
                    lines.append(f"  - {yaml_val(x)}")
        else:
            lines.append(f"{k}: {yaml_val(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + (body or "")


WRITTEN = []


def put(coll, rid, rec, body="", local=False):
    # 生活数据在 local/life/<集合> 下，不是 local/<集合> ——
    # 写错一层的话服务端读不到，界面上会是空的
    base = (LOCAL / "life" / coll) if local else (DATA / coll)
    base.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec["id"] = rid
    rec["demo"] = True
    rec.setdefault("created", dt(-120))
    rec.setdefault("updated", dt(0))
    (base / f"{rid}.md").write_text(dump(rec, body), encoding="utf-8")
    WRITTEN.append(f"{'local' if local else 'data'}/{coll}/{rid}.md")


# ============================================================ 学术线

def seed_journals():
    js = [
        ("journal-of-finance", "Journal of Finance", "JF", 7.5, "金融学三大刊之一。桌拒率高，进外审后中位数约 3 个月。",
         ["资产定价", "公司金融"], "https://onlinelibrary.wiley.com/journal/15406261", 90),
        ("review-of-financial-studies", "Review of Financial Studies", "RFS", 6.8,
         "对识别策略要求最细，喜欢机制证据充分的稿子。", ["资产定价", "中介"], "https://academic.oup.com/rfs", 75),
        ("journal-of-financial-economics", "Journal of Financial Economics", "JFE", 6.1,
         "偏实证，审稿轮次少但一轮要求重。", ["公司金融", "微观结构"], "https://www.sciencedirect.com/journal/journal-of-financial-economics", 60),
        ("management-science", "Management Science", "MS", 4.9, "跨学科，金融板块审得快。",
         ["行为金融", "市场设计"], "https://pubsonline.informs.org/journal/mnsc", 55),
        ("jfqa", "Journal of Financial and Quantitative Analysis", "JFQA", 3.4,
         "稳，回复及时，适合扎实但不惊艳的稿子。", ["实证资产定价"], "https://www.cambridge.org/core/journals/jfqa", 70),
    ]
    for rid, name, abbr, jif, note, tags, url, days in js:
        put("journals", f"demo-{rid}", {
            "title": name, "abbrev": abbr, "impact_factor": jif, "tier": "A" if jif > 6 else "B",
            "typical_first_response_days": days, "tags": tags, "link": url,
            "submission_url": url, "open_access": False,
        }, f"## 投稿经验\n\n{note}\n")


MS = [
    dict(rid="demo-ms-intermediary", title="Intermediary Constraints and the Cross-Section of Returns",
         stage="rnr", target="Journal of Finance", current="Journal of Finance",
         next_action="补 Section 4 的机制检验", next_due=d(6),
         tl=[("投稿", "Journal of Finance", -280, "首投"),
             ("R&R", "Journal of Finance", -150, "三个审稿人，两个正面"),
             ("返修再投", "Journal of Finance", -70, "补了两组稳健性"),
             ("备注", "Journal of Finance", -12, "编辑说还需要一轮外审")],
         body="用中介资产定价框架解释横截面收益。识别靠交易商资本约束的外生冲击。"),
    dict(rid="demo-ms-attention", title="Retail Attention and Price Discovery in Chinese Markets",
         stage="submitted", target="Review of Financial Studies", current="Review of Financial Studies",
         next_action="等外审", next_due=d(35),
         tl=[("投稿", "Management Science", -400, "首投"),
             ("拒稿", "Management Science", -320, "编辑桌拒，说贡献不够一般化"),
             ("投稿", "Review of Financial Studies", -40, "大改后转投")],
         body="用小程序普及做技术扩散的自然实验，看散户注意力如何影响价格发现。"),
    dict(rid="demo-ms-funding", title="Funding Liquidity and the Term Structure of Volatility",
         stage="draft", target="Journal of Financial Economics", current="",
         next_action="把 Table 5 重做成分组回归", next_due=d(-3),
         tl=[], body="还在写。核心结果已经稳定，缺一个干净的识别。"),
    dict(rid="demo-ms-shelved", title="Cross-Border Spillovers in Repo Markets",
         stage="shelved", target="", current="", next_action="", next_due="",
         tl=[("备注", "", -500, "数据拿不到，先搁置")], body="等能拿到 SFTR 数据再说。"),
]


def seed_manuscripts():
    for m in MS:
        put("manuscripts", m["rid"], {
            "title": m["title"], "stage": m["stage"],
            "authors": ["我", "合作者 A"] + (["合作者 B"] if m["stage"] == "rnr" else []),
            "target_journal": m["target"], "current_journal": m["current"],
            "next_action": m["next_action"], "next_action_due": m["next_due"],
            "overleaf": "https://www.overleaf.com/project/demo" if m["stage"] != "shelved" else "",
            "timeline": [{"kind": k, "journal": j, "date": d(off), "note": n} for k, j, off, n in m["tl"]],
        }, f"## 一句话\n\n{m['body']}\n")


def seed_published():
    put("published", "demo-pub-liquidity", {
        "title": "Liquidity Provision under Funding Stress",
        "authors": ["我", "合作者 C"], "journal": "Journal of Financial and Quantitative Analysis",
        "year": TODAY.year - 1, "volume": "58", "issue": "4", "pages": "1523-1560",
        "doi": "10.1017/S0022109022000999", "citations": 14,
        "link": "https://doi.org/10.1017/S0022109022000999",
    }, "## 摘要\n\n危机期间做市商的流动性供给行为。\n")
    put("published", "demo-pub-early", {
        "title": "A Note on Realized Volatility Estimators",
        "authors": ["我"], "journal": "Finance Research Letters",
        "year": TODAY.year - 3, "doi": "10.1016/j.frl.2023.10000", "citations": 5,
    }, "## 摘要\n\n博一时的小文章。\n")


def seed_conferences():
    cs = [
        ("afa", "AFA Annual Meeting 2027", d(120), d(210), "Chicago, USA", "submitted", "已投，等结果"),
        ("wfa", "Western Finance Association 2027", d(24), d(160), "Napa, USA", "planned", "打算投中介那篇"),
        ("cfrc", "中国金融研究会议 CFRC 2027", d(-5), d(90), "北京", "missed", "截稿日过了，明年再说"),
        ("emg", "EFA Annual Meeting 2027", d(58), d(200), "Milan, Italy", "planned", ""),
    ]
    for rid, name, dl, dt_, loc, status, note in cs:
        put("conferences", f"demo-conf-{rid}", {
            "title": name, "deadline": dl, "meeting_date": dt_, "location": loc,
            "status": status, "link": "https://example.org/conf",
        }, note and f"## 备注\n\n{note}\n")


READING = [
    ("he-krishnamurthy-2013", "Intermediary Asset Pricing", ["He, Zhiguo", "Krishnamurthy, Arvind"],
     2013, "American Economic Review", "10.1257/aer.103.2.732", "done", "critical",
     "intermediary asset pricing", -40),
    ("adrian-shin-2010", "Liquidity and Leverage", ["Adrian, Tobias", "Shin, Hyun Song"],
     2010, "Journal of Financial Intermediation", "10.1016/j.jfi.2008.12.002", "done", "deep",
     "intermediary asset pricing", -22),
    ("brunnermeier-2009", "Market Liquidity and Funding Liquidity",
     ["Brunnermeier, Markus", "Pedersen, Lasse"], 2009, "Review of Financial Studies",
     "10.1093/rfs/hhn098", "done", "critical", "intermediary asset pricing", -9),
    ("barber-odean-2008", "All That Glitters: The Effect of Attention",
     ["Barber, Brad", "Odean, Terrance"], 2008, "Review of Financial Studies",
     "10.1093/rfs/hhm079", "done", "deep", "投资者注意力", -3),
    ("da-2011", "In Search of Attention", ["Da, Zhi", "Engelberg, Joseph", "Gao, Pengjie"],
     2011, "Journal of Finance", "10.1111/j.1540-6261.2011.01679.x", "reading", "skim",
     "投资者注意力", -1),
    ("hong-stein-1999", "A Unified Theory of Underreaction", ["Hong, Harrison", "Stein, Jeremy"],
     1999, "Journal of Finance", "10.1111/0022-1082.00184", "to-read", "skim", "投资者注意力", None),
    ("gabaix-2020", "In Search of the Origins of Financial Fluctuations", ["Gabaix, Xavier"],
     2020, "Working Paper", "", "to-read", "skim", "需求体系", None),
]


def seed_reading():
    for rid, title, auth, yr, jn, doi, status, lvl, topic, off in READING:
        rec = {
            "title": title, "authors": auth, "year": yr, "journal": jn, "doi": doi,
            "link": f"https://doi.org/{doi}" if doi else "",
            "status": status, "level": lvl, "topic": topic,
        }
        body = ""
        if status == "done":
            rec["read_date"] = d(off)
            # 复习记录：制造几条已到期的，好让复习队列不是空的
            revs = [{"gap": g, "date": d(off + g)} for g in (1, 7) if off + g <= 0]
            if revs:
                rec["reviews"] = revs
            body = ("## 研究问题\n\n这篇要回答什么。\n\n## 识别策略 / 方法\n\n用了什么变异。\n\n"
                    "## 主要结论\n\n三句话说清。\n\n## 贡献与局限\n\n对我那篇稿子的用处。\n")
        put("reading", f"demo-rd-{rid}", rec, body)


def seed_levels():
    put("levels", "demo-lvl-intermediary", {
        "title": "intermediary asset pricing", "goal": 15, "status": "active",
    }, "## 目标\n\n把中介资产定价这条线读透，支撑第一篇稿子。\n")
    put("levels", "demo-lvl-attention", {
        "title": "投资者注意力", "goal": 10, "status": "active",
    }, "## 目标\n\n注意力那篇的文献基础。\n")


def seed_ideas():
    ideas = [
        ("nonlinear", "中介约束在中国市场是否也呈非线性？", "idea", "new", 40, 40, ["中介", "中国"]),
        ("wechat", "用微信小程序普及做技术扩散的自然实验", "idea", "adopted", 300, 60, ["注意力"]),
        ("repo", "回购市场的跨境溢出能不能用 SFTR 数据做？", "question", "new", 560, 40, ["数据"]),
        ("gabaix", "Gabaix 那套需求体系能不能接到中介框架上？", "ref", "new", 40, 240, ["理论"]),
        ("referee", "审稿人 2 提的那个反驳，其实是个独立的题", "idea", "new", 300, 240, ["选题"]),
        ("dropped", "用推特情绪做预测", "idea", "rejected", 560, 240, ["否决"]),
    ]
    for rid, title, kind, status, x, y, tags in ideas:
        put("ideas", f"demo-idea-{rid}", {
            "title": title, "kind": kind, "status": status,
            "source": "组会讨论", "tags": tags, "x": x, "y": y,
        })


def seed_schedule():
    items = [
        ("groupmeeting", "系里组会", -0, 13, 0, False),
        ("coauthor", "跟合作者过 Table 5", 0, 16, 30, False),
        ("seminar", "外来讲座：Gabaix", 1, 15, 0, False),
        ("deadline", "把 R&R 回复信初稿发给合作者", 4, 10, 0, False),
        ("teaching", "本科课答疑", 2, 11, 0, False),
        ("done1", "交年度进展报告", -2, 14, 0, True),
        ("done2", "改完 Section 3", -1, 20, 0, True),
    ]
    for rid, title, off, hh, mm, done in items:
        put("schedule", f"demo-sch-{rid}", {
            "title": title, "start": d(off), "time": f"{hh:02d}:{mm:02d}",
            "done": done, "kind": "meeting" if not done else "task",
        })


def seed_progress():
    """Overleaf 写作进展：连续两周，好让「写作进展」卡片有曲线。"""
    for i in range(14):
        off = -13 + i
        words = random.randint(-200, 900)
        put("progress", f"demo-prog-{d(off)}", {
            "title": f"{d(off)} 写作进展", "date": d(off),
            "project": "Intermediary Constraints", "words_delta": words,
            "lines_added": max(0, words // 8 + random.randint(0, 20)),
            "lines_removed": random.randint(0, 15),
            "sections": random.sample(["Introduction", "Model", "Data", "Results",
                                       "Robustness", "Conclusion"], k=random.randint(1, 3)),
        })


def seed_reports():
    put("reports", "demo-rep-brainstorm", {
        "title": "头脑风暴 · 中介约束这条线还能往哪走", "kind": "brainstorm",
        "source": "auto", "date": d(-4), "status": "unread",
        "ref": "manuscripts:demo-ms-intermediary",
    }, """## 1. 把约束换成异质性交易商

**新角度**：现有做法把中介当成一个代表性主体，可以拆成受约束/不受约束两类。
**为什么现在可行**：监管报送数据在 2019 年后可得。
**需要什么数据**：交易商层面的杠杆与资本充足率。
**最可能的反驳**：两类划分是内生的，得先解决选择问题。

## 2. 用期限结构做交叉验证

**新角度**：如果中介约束是真的，波动率期限结构应该同步变化。
**最可能的反驳**：期限结构还受预期通胀影响，需要剥离。

## 3. 反过来做证伪

**新角度**：找一段中介资本充足但收益仍异常的时期。
**最可能的反驳**：可能只是样本太短。
""")
    put("reports", "demo-rep-critique", {
        "title": "以审稿人视角攻击「注意力」那篇", "kind": "critique",
        "source": "claude", "date": d(-2), "status": "unread",
        "ref": "manuscripts:demo-ms-attention",
    }, """## 严重

1. **识别**：小程序普及不是随机的，先富裕地区先普及，跟股票参与度高度相关。
   *补救*：用运营商基站升级时点做工具变量。

## 中等

2. **样本**：只有 2019–2022，正好跨疫情。*补救*：加入 2023–2025。
3. **机制**：说是注意力，但没排除流动性渠道。*补救*：加换手率分解。

## 轻微

4. 图 3 的置信区间没说明是怎么算的。
""")
    put("reports", "demo-rep-audit", {
        "title": "全库体检 · " + d(-1), "kind": "audit", "source": "auto",
        "date": d(-1), "status": "read",
    }, """## 内部矛盾（高）

- `demo-ms-attention`：stage 写 `submitted`，但 timeline 最后一条是「投稿 RFS」——一致，无问题。

## 过期未动（中）

- `demo-ms-funding`：next_action_due 已过期 3 天。

## 引用真伪

- 抽查 7 条文献，DOI 全部可解析。

**只提议，未修改任何记录。**
""")


def seed_retros():
    put("retros", "demo-retro-q2", {
        "title": f"{TODAY.year} 上半年复盘", "date": d(-30), "period": "H1",
    }, """## 做成了什么

- 中介那篇进了 R&R
- 注意力那篇转投 RFS

## 没做成

- Funding 那篇卡在识别上，三个月没动

## 下半年只做三件事

1. 把 R&R 回完
2. Funding 那篇要么找到识别要么砍掉
3. 每周至少精读两篇
""")


# ============================================================ 生活线（不进 git）

def seed_life():
    for i in range(21):
        off = -20 + i
        put("diet", f"demo-diet-{d(off)}", {
            "title": f"{d(off)} 饮食", "date": d(off),
            "breakfast": random.choice(["燕麦 + 鸡蛋", "包子豆浆", "跳过"]),
            "lunch": random.choice(["食堂套餐", "三明治", "剩菜"]),
            "dinner": random.choice(["自己做", "外卖", "跟人吃"]),
            "kcal": random.randint(1700, 2600),
        }, local=True)
        if i % 2 == 0:
            put("exercise", f"demo-ex-{d(off)}", {
                "title": random.choice(["跑步", "游泳", "健身房", "骑车"]),
                "date": d(off), "minutes": random.choice([30, 40, 45, 60]),
                "distance_km": round(random.uniform(3, 10), 1),
                "note": random.choice(["还行", "有点累", "状态不错", ""]),
            }, local=True)
    cats = ["房租", "餐饮", "书籍", "交通", "会议注册费", "订阅", "咖啡"]
    for i in range(26):
        off = -25 + i
        put("finance", f"demo-fin-{i:03d}", {
            "title": random.choice(cats), "date": d(off),
            "amount": round(random.uniform(3, 320), 2), "currency": "GBP",
            "category": random.choice(cats),
            "kind": "expense",
        }, local=True)
    for rid, title, dd, kind in [
        ("bday-mom", "妈妈生日", d(23), "birthday"),
        ("anniv", "来这边读书满四年", d(58), "anniversary"),
        ("visa", "签证到期", d(150), "deadline"),
    ]:
        put("dates", f"demo-date-{rid}", {"title": title, "date": dd, "kind": kind,
                                          "repeat": "yearly" if kind != "deadline" else ""},
            local=True)
    put("lists", "demo-list-books", {
        "title": "想读的书", "items": ["《随机漫步的傻瓜》", "《薛兆丰经济学讲义》", "《置身事内》"],
    }, local=True)
    put("lists", "demo-list-buy", {
        "title": "要买的东西", "items": ["显示器支架", "机械键盘轴体", "咖啡豆"],
    }, local=True)
    for rid, title, off, done in [
        ("visa-renew", "预约签证续签", 30, False),
        ("insurance", "续保", -4, True),
        ("bank", "改银行地址", 10, False),
    ]:
        put("admin", f"demo-admin-{rid}", {"title": title, "due": d(off), "done": done},
            local=True)


# ============================================================ 文献索引演示

def seed_library(n=400):
    """给索引也造点数据，好演示搜索、跳转、提升。"""
    try:
        sys.path.insert(0, str(ROOT))
        import library as lib
    except Exception as e:
        print("  跳过文献索引（library.py 未加载）：", e)
        return
    JS = ["Journal of Finance", "Review of Financial Studies", "Journal of Financial Economics",
          "American Economic Review", "Econometrica", "Journal of Political Economy",
          "Quarterly Journal of Economics", "Management Science"]
    W = ["intermediary", "liquidity", "momentum", "volatility", "credit", "attention",
         "microstructure", "governance", "monetary policy", "arbitrage", "funding", "demand system"]
    NAMES = ["He", "Krishnamurthy", "Adrian", "Shin", "Brunnermeier", "Pedersen", "Gabaix",
             "Koijen", "Barber", "Odean", "Da", "Engelberg", "Hong", "Stein", "Fama", "French"]
    items = []
    for i in range(n):
        w1, w2 = random.sample(W, 2)
        auth = [f"{random.choice(NAMES)}, {chr(65 + i % 26)}." for _ in range(random.randint(1, 3))]
        items.append(lib._mk_item(
            k=f"DEMO{i:05d}", c=f"demo{i:04d}", ty="journalArticle", s="demo",
            t=f"{w1.title()} and {w2} in the cross-section of returns ({i})",
            a=auth, y=random.randint(1995, 2026), j=random.choice(JS),
            d=f"10.9999/demo.{i}", u=f"https://example.org/demo/{i}",
            tg=random.sample(["资产定价", "中介", "注意力", "流动性", "方法"], k=random.randint(0, 2)),
        ))
    ix = lib.Index(DATA / "library.jsonl")
    st = ix.add_many(items, source="demo")
    print(f"  文献索引：新增 {st['added']} 条，共 {st['total']} 条")


# ============================================================ 清理

def clean():
    n = 0
    for base in (DATA, LOCAL / "life"):
        if not base.exists():
            continue
        for p in base.rglob("demo-*.md"):
            p.unlink()
            n += 1
    libp = DATA / "library.jsonl"
    if libp.exists():
        try:
            sys.path.insert(0, str(ROOT))
            import library as lib
            st = lib.Index(libp).clear("demo")
            print(f"  文献索引：清掉 {st['removed']} 条演示题录")
        except Exception:
            pass
    print(f"清掉 {n} 个演示记录文件")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入演示数据")
    ap.add_argument("--wipe", action="store_true", help="写入前先清掉旧的演示数据")
    ap.add_argument("--clean", action="store_true", help="只清理")
    ap.add_argument("--library", type=int, default=400, help="文献索引造多少条")
    a = ap.parse_args()
    if a.clean:
        clean()
        return
    if not a.write:
        ap.print_help()
        return
    if a.wipe:
        clean()
    seed_journals(); seed_manuscripts(); seed_published(); seed_conferences()
    seed_reading(); seed_levels(); seed_ideas(); seed_schedule()
    seed_progress(); seed_reports(); seed_retros(); seed_life()
    seed_library(a.library)
    print(f"写入 {len(WRITTEN)} 个记录文件")
    from collections import Counter
    for k, v in sorted(Counter(w.split("/")[1] for w in WRITTEN).items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
