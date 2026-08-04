#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周报与 AI 手帐 · 算法部分
  python3 scripts/journal.py --week     汇总上周全部事实，输出 JSON（供 Claude 写叙述）
  python3 scripts/journal.py --render   合成周报 md + 手帐 html，并按配置推送
叙述由 Claude 写入 data/_claude/journal-narrative.json 后再 --render。
"""
import json, sys, html
from datetime import date, datetime, timedelta
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("srv", ROOT / "server.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)
try:
    import services as sv
except Exception:
    sv = None

EVENT_T = {"started": "启动", "draft": "初稿完成", "submitted": "投稿", "desk-reject": "编辑部退稿",
           "rejected": "拒稿", "rnr": "R&R", "resubmitted": "返修再投", "accepted": "接收",
           "published": "发表", "withdrawn": "撤稿", "note": "备注"}
STAGE_T = {"idea": "选题", "writing": "写作", "analysis": "分析", "submitted": "在投",
           "rnr": "R&R", "accepted": "接收", "published": "已发表", "shelved": "搁置"}


def week_bounds(ref=None):
    ref = ref or date.today()
    monday = ref - timedelta(days=ref.weekday())
    last_monday = monday - timedelta(days=7)
    return last_monday, monday - timedelta(days=1), monday


def iso_week(d0):
    y, w, _ = d0.isocalendar()
    return f"{y}-W{w:02d}"


def in_range(s, a, b):
    try:
        x = date.fromisoformat(str(s)[:10])
    except Exception:
        return False
    return a <= x <= b


def gather(a, b):
    """把上周发生的一切汇总成事实 JSON。只做统计，不做判断。"""
    cfg = srv.get_config()
    ms = srv.list_records("manuscripts")
    events = []
    for m in ms:
        for e in (m.get("timeline") or []):
            if isinstance(e, dict) and in_range(e.get("date"), a, b):
                events.append({"date": e.get("date"), "manuscript": m.get("title"),
                               "event": EVENT_T.get(e.get("event"), e.get("event")),
                               "journal": e.get("journal", ""), "note": (e.get("note") or "")[:120]})
    events.sort(key=lambda x: str(x["date"]))

    read = [r for r in srv.list_records("reading")
            if r.get("status") == "done" and in_range(r.get("read_date"), a, b)]
    xp_map = (cfg.get("reading") or {}).get("xp", {"skim": 1, "deep": 3, "critical": 5})
    xp = sum(xp_map.get(r.get("level"), 1) for r in read)

    done = [s for s in srv.list_records("schedule")
            if s.get("done") and in_range(s.get("start"), a, b)]
    ideas = [i for i in srv.list_records("ideas") if in_range((i.get("created") or "")[:10], a, b)]
    ex = [e for e in srv.list_records("exercise") if in_range(e.get("date"), a, b)]
    diet = [e for e in srv.list_records("diet") if in_range(e.get("date"), a, b)]
    reports = [r for r in srv.list_records("reports") if in_range(r.get("date"), a, b)]

    # Overleaf 写作进展：这周到底往论文里写进去了多少
    prog = [p for p in srv.list_records("progress") if in_range(p.get("date"), a, b)]
    writing = {
        "days": len({str(p.get("date"))[:10] for p in prog}),
        "commits": sum(int(p.get("commits") or 0) for p in prog),
        "added": sum(int(p.get("added") or 0) for p in prog),
        "removed": sum(int(p.get("removed") or 0) for p in prog),
        "projects": sorted({p.get("title") or p.get("project") or "" for p in prog} - {""}),
        "touched": sorted({t for p in prog for t in (p.get("touched") or [])})[:8],
        "messages": [m for p in prog for m in (p.get("messages") or [])][-8:],
        "words": max([int(p.get("words") or 0) for p in prog] or [0]),
    }

    # 上上周对比
    pa, pb = a - timedelta(days=7), b - timedelta(days=7)
    prev_ex = sum(int(e.get("minutes") or 0) for e in srv.list_records("exercise")
                  if in_range(e.get("date"), pa, pb))
    prev_read = len([r for r in srv.list_records("reading")
                     if r.get("status") == "done" and in_range(r.get("read_date"), pa, pb)])

    active = [m for m in ms if m.get("stage") not in ("published", "shelved")]
    stale_days = cfg.get("stale_manuscript_days", 7)

    def days_since_update(m):
        tl = sorted([e for e in (m.get("timeline") or []) if isinstance(e, dict)],
                    key=lambda e: str(e.get("date", "")))
        d0 = tl[-1].get("date") if tl else (m.get("updated") or "")[:10]
        try:
            return (date.today() - date.fromisoformat(str(d0)[:10])).days
        except Exception:
            return None

    stalled = [{"title": m.get("title"), "days": days_since_update(m), "stage": STAGE_T.get(m.get("stage"), "")}
               for m in active if (days_since_update(m) or 0) >= stale_days]

    # 在投时长与历史均值
    in_review = []
    for m in ms:
        tl = sorted([e for e in (m.get("timeline") or []) if isinstance(e, dict)],
                    key=lambda e: str(e.get("date", "")))
        sub = None
        for e in tl:
            if e.get("event") in ("submitted", "resubmitted"):
                sub = e
            elif e.get("event") in ("rejected", "desk-reject", "rnr", "accepted", "withdrawn", "published"):
                sub = None
        if sub:
            try:
                dd = (date.today() - date.fromisoformat(str(sub.get("date"))[:10])).days
            except Exception:
                dd = None
            in_review.append({"title": m.get("title"), "journal": sub.get("journal", ""),
                              "days": dd, "since": sub.get("date")})

    # 未来两周的截止
    horizon = date.today() + timedelta(days=14)
    upcoming = []
    for c in srv.list_records("conferences"):
        if c.get("deadline") and date.today() <= (date.fromisoformat(str(c["deadline"])[:10]) if c.get("deadline") else date.today()) <= horizon:
            upcoming.append({"what": (c.get("title") or "") + " 投稿截止", "date": c.get("deadline")})
    for m in ms:
        if m.get("next_action_due"):
            try:
                dd = date.fromisoformat(str(m["next_action_due"])[:10])
                if date.today() <= dd <= horizon:
                    upcoming.append({"what": f'{m.get("title")} · {m.get("next_action", "")}', "date": m["next_action_due"]})
            except Exception:
                pass
    for adm in srv.list_records("admin"):
        if adm.get("date") and not adm.get("done"):
            try:
                dd = date.fromisoformat(str(adm["date"])[:10])
                if date.today() <= dd <= horizon:
                    upcoming.append({"what": adm.get("title"), "date": adm["date"]})
            except Exception:
                pass
    upcoming.sort(key=lambda x: str(x["date"]))

    # 关卡进度
    levels = []
    for l in srv.list_records("levels"):
        got = [r for r in srv.list_records("reading")
               if (r.get("topic") or "").strip() == (l.get("title") or "").strip() and r.get("status") == "done"]
        levels.append({"title": l.get("title"), "done": len(got), "target": l.get("target") or 10,
                       "pct": min(100, round(len(got) / max(1, l.get("target") or 10) * 100))})

    return {
        "week": iso_week(a), "from": a.isoformat(), "to": b.isoformat(),
        "writing": writing,
        "events": events,
        "reading": {"count": len(read), "xp": xp, "prev_count": prev_read,
                    "titles": [r.get("title") for r in read]},
        "done_tasks": [{"title": s.get("title"), "date": s.get("start"), "minutes": s.get("minutes")} for s in done],
        "ideas": [{"title": i.get("title"), "kind": i.get("kind")} for i in ideas],
        "exercise": {"count": len(ex), "minutes": sum(int(e.get("minutes") or 0) for e in ex),
                     "prev_minutes": prev_ex},
        "diet": {"count": len(diet), "kcal": sum(int(e.get("kcal") or 0) for e in diet if e.get("kcal"))},
        "ai_reports": [{"title": r.get("title"), "kind": r.get("kind"), "status": r.get("status")} for r in reports],
        "stalled": stalled, "in_review": in_review, "upcoming": upcoming, "levels": levels,
        "active_count": len(active),
        "quote": pick_quote(a),
    }


def pick_quote(a):
    try:
        q = json.loads((srv.DATA / "quotes.json").read_text(encoding="utf-8"))["quotes"]
        favs = [x for x in q if x.get("fav")] or q
        return favs[(a.toordinal() // 7) % len(favs)]
    except Exception:
        return {"t": "", "s": ""}


# ------------------------------------------------------------------ 渲染

def narrative():
    p = srv.CLAUDE / "journal-narrative.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def md_report(f, n):
    L = [f"# 本周开局 · {f['week']}", "",
         f"> 统计区间 {f['from']} — {f['to']}", ""]
    if f["quote"].get("t"):
        L += [f"> 「{f['quote']['t']}」　—— {f['quote'].get('s', '')}", ""]
    if n.get("did"):
        L += ["## 上周你做了什么", "", n["did"], ""]
    else:
        L += ["## 上周（自动统计）", "",
              f"稿件事件 {len(f['events'])} 条 · 读完文献 {f['reading']['count']} 篇（+{f['reading']['xp']} XP）"
              f" · 完成记录 {len(f['done_tasks'])} 条 · 运动 {f['exercise']['count']} 次共 {f['exercise']['minutes']} 分钟", ""]
    w = f.get("writing") or {}
    if w.get("commits"):
        L += ["### ✍️ 写作进展（Overleaf）", "",
              f"- 动笔 {w['days']} 天 · {w['commits']} 次提交 · 净 "
              f"{'+' if w['added'] - w['removed'] >= 0 else ''}{w['added'] - w['removed']} 行"
              + (f" · 正文约 {w['words']} 词" if w.get("words") else ""), ]
        if w.get("projects"):
            L.append(f"- 涉及：{'、'.join(w['projects'])}")
        if w.get("touched"):
            L.append(f"- 动过的文件：{'、'.join(w['touched'])}")
        if w.get("messages"):
            L.append("- 你自己写的提交说明：" + "；".join(w["messages"][-4:]))
        L.append("")
    if f["events"]:
        L.append("### 稿件动态")
        for e in f["events"]:
            L.append(f"- {e['date']} **{e['event']}** {e['journal']} —— {(e['manuscript'] or '')[:40]}")
        L.append("")
    if n.get("key"):
        L += ["## 本周关键", "", n["key"], ""]
    elif f["upcoming"]:
        L += ["## 未来两周的截止", ""]
        for u in f["upcoming"]:
            L.append(f"- {u['date']} {u['what']}")
        L.append("")
    if f["stalled"]:
        L += ["### ⚠️ 停滞", ""] + [f"- {s['title']}（{s['days']} 天没动 · {s['stage']}）" for s in f["stalled"]] + [""]
    if f["in_review"]:
        L += ["### 在投", ""] + [f"- {r['title']} · {r['journal']} 已 {r['days']} 天" for r in f["in_review"]] + [""]
    if n.get("noticed"):
        L += ["## 我注意到", "", n["noticed"], ""]
    return "\n".join(L)


def html_journal(f, n):
    q = f["quote"]
    e = html.escape
    lv = "".join(
        f'<div class="lv"><div class="ring" style="--p:{l["pct"]}"><span>{l["pct"]}%</span></div>'
        f'<div class="lvt">{e(str(l["title"]))}<i>{l["done"]}/{l["target"]} 篇</i></div></div>'
        for l in f["levels"])
    tl = "".join(
        f'<div class="ti"><b>{e(str(ev["date"])[5:])}</b><span class="tv">{e(ev["event"])}'
        f'{" · " + e(ev["journal"]) if ev["journal"] else ""}</span>'
        f'<div class="tm">{e((ev["manuscript"] or "")[:44])}</div></div>'
        for ev in f["events"]) or '<div class="none">这周稿件没有新事件</div>'
    w = f.get("writing") or {}
    wcommits = int(w.get("commits") or 0)
    wnet = int(w.get("added") or 0) - int(w.get("removed") or 0)
    wdays = int(w.get("days") or 0)
    wline = ""
    if wcommits:
        wline = ('<h2>写作进展</h2><p class="narr">这周动笔 %d 天，%d 次提交，正文净 %+d 行%s。%s</p>'
                 % (wdays, wcommits, wnet,
                    ("，全文约 %d 词" % w["words"]) if w.get("words") else "",
                    ("动过：" + e("、".join(w.get("touched") or [])[:80])) if w.get("touched") else ""))
    dx = f["exercise"]["minutes"] - f["exercise"]["prev_minutes"]
    dr = f["reading"]["count"] - f["reading"]["prev_count"]
    arrow = lambda v: ("▲" if v > 0 else "▼" if v < 0 else "—") + (f" {abs(v)}" if v else "")
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>手帐 · {f['week']}</title><style>
:root{{--ink:#2b2b28;--paper:#fdfbf5;--line:#e6e0d2;--accent:#8a6d3b;--red:#b5483d;--green:#4a7c59;--blue:#3d5a80}}
*{{box-sizing:border-box}}
body{{margin:0;background:#efeae0;color:var(--ink);font-family:"Songti SC","STSong","KaiTi","Noto Serif SC",Georgia,serif;
 display:flex;justify-content:center;padding:26px 14px}}
.page{{width:min(760px,100%);background:var(--paper);border-radius:6px;padding:34px 38px 42px;
 box-shadow:0 2px 18px rgba(80,70,50,.18);position:relative;
 background-image:repeating-linear-gradient(transparent,transparent 31px,rgba(180,170,150,.16) 32px)}}
.page:before{{content:"";position:absolute;left:26px;top:0;bottom:0;width:1px;background:rgba(190,80,70,.22)}}
h1{{font-size:23px;margin:0 0 2px;letter-spacing:.04em}}
.sub{{font-size:11.5px;color:#95897a;margin-bottom:18px;letter-spacing:.06em}}
.quote{{border-left:3px solid var(--accent);padding:6px 0 6px 13px;margin:16px 0 20px;font-size:15px;line-height:1.95}}
.quote i{{display:block;font-size:11px;color:#95897a;font-style:normal;margin-top:5px}}
.nums{{display:flex;gap:9px;flex-wrap:wrap;margin:14px 0 20px}}
.num{{flex:1;min-width:88px;border:1px solid var(--line);border-radius:5px;padding:9px 11px;background:rgba(255,255,255,.55)}}
.num b{{display:block;font-size:25px;line-height:1.2;font-family:Georgia,serif}}
.num span{{font-size:10.5px;color:#95897a}}
.num em{{font-size:10px;font-style:normal;color:var(--accent);margin-left:4px}}
h2{{font-size:13.5px;margin:22px 0 9px;letter-spacing:.1em;color:var(--accent);
 border-bottom:1px solid var(--line);padding-bottom:4px}}
.narr{{font-size:14px;line-height:2.05;text-indent:2em;margin:0 0 6px}}
.ti{{padding:6px 0;border-bottom:1px dashed var(--line);font-size:12.5px;display:flex;gap:9px;align-items:baseline;flex-wrap:wrap}}
.ti b{{font-family:Georgia,serif;color:var(--accent);flex:0 0 42px}}
.tv{{font-weight:600}}
.tm{{width:100%;font-size:11px;color:#95897a;padding-left:51px}}
.none{{font-size:12px;color:#a49a8a;padding:8px 0}}
.lvs{{display:flex;gap:14px;flex-wrap:wrap}}
.lv{{display:flex;gap:9px;align-items:center;margin:5px 0}}
.ring{{--p:0;width:42px;height:42px;border-radius:50%;display:grid;place-items:center;font-size:10.5px;font-weight:700;
 color:var(--accent);background:conic-gradient(var(--accent) calc(var(--p)*1%),#e6e0d2 0);font-family:Georgia,serif}}
.ring span{{width:33px;height:33px;border-radius:50%;background:var(--paper);display:grid;place-items:center}}
.lvt{{font-size:12.5px}} .lvt i{{display:block;font-size:10.5px;color:#95897a;font-style:normal}}
ul{{margin:4px 0;padding-left:20px;font-size:12.5px;line-height:1.9}}
.foot{{margin-top:26px;padding-top:10px;border-top:1px solid var(--line);font-size:10.5px;color:#a49a8a;
 display:flex;justify-content:space-between}}
@media print{{body{{background:#fff;padding:0}}.page{{box-shadow:none}}}}
</style></head><body><div class="page">
<h1>本周开局 · {f['week']}</h1>
<div class="sub">{f['from']} — {f['to']}　|　学术工作台手帐</div>
{f'<div class="quote">{e(q["t"])}<i>—— {e(q.get("s",""))}</i></div>' if q.get("t") else ""}
<div class="nums">
  <div class="num"><b>{len(f['events'])}</b><span>稿件事件</span></div>
  <div class="num"><b>{f['reading']['count']}</b><span>读完文献<em>{arrow(dr)}</em></span></div>
  <div class="num"><b>{f['reading']['xp']}</b><span>经验值</span></div>
  <div class="num"><b>{f['exercise']['minutes']}</b><span>运动分钟<em>{arrow(dx)}</em></span></div>
  <div class="num"><b>{len(f['done_tasks'])}</b><span>完成记录</span></div>
  {f'<div class="num"><b>{wnet:+d}</b><span>论文净增行<em>{wdays} 天动笔</em></span></div>' if wcommits else ""}
</div>
{f'<h2>上周你做了什么</h2><p class="narr">{e(n["did"])}</p>' if n.get("did") else ""}
{wline}
<h2>稿件动态</h2>{tl}
{f'<h2>本周关键</h2><p class="narr">{e(n["key"])}</p>' if n.get("key") else ""}
{"<h2>未来两周</h2><ul>" + "".join(f"<li>{e(str(u['date'])[5:])}　{e(str(u['what'])[:48])}</li>" for u in f['upcoming'][:8]) + "</ul>" if f['upcoming'] else ""}
{"<h2>停滞提醒</h2><ul>" + "".join(f"<li>{e(str(s['title'])[:40])}　已 {s['days']} 天没动</li>" for s in f['stalled']) + "</ul>" if f['stalled'] else ""}
{f'<h2>关卡</h2><div class="lvs">{lv}</div>' if lv else ""}
{f'<h2>我注意到</h2><p class="narr">{e(n["noticed"])}</p>' if n.get("noticed") else ""}
<div class="foot"><span>学术工作台 · 自动生成</span><span>{srv.today_str()}</span></div>
</div></body></html>"""


def main():
    a, b, _ = week_bounds()
    f = gather(a, b)
    if "--week" in sys.argv:
        print(json.dumps(f, ensure_ascii=False, indent=1))
        return
    if "--render" in sys.argv:
        n = narrative()
        md = md_report(f, n)
        rp = srv.DATA / "reports" / f"weekly-{f['week']}.md"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text("---\ntitle: 本周开局 " + f["week"] +
                      "\nkind: weekly\nsource: auto\ndate: " + srv.today_str() +
                      "\nstatus: unread\n---\n\n" + md, encoding="utf-8")
        jd = srv.LOCAL / "journal"
        jd.mkdir(parents=True, exist_ok=True)
        hp = jd / f"{f['week']}.html"
        hp.write_text(html_journal(f, n), encoding="utf-8")
        out = {"ok": True, "report": str(rp), "journal": str(hp), "week": f["week"]}
        if "--push" in sys.argv and sv:
            secrets = srv.get_secrets()
            title = f"本周开局 · {f['week']}"
            brief = md.split("## ")[0] + "\n\n" + (n.get("key") or "")
            out["push"] = sv.push_all(secrets, title, brief[:1800])
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    print(json.dumps({"usage": "--week | --render [--push]"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
