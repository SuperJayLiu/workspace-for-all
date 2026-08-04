#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全库体检 · 算法部分（不需要 AI，零成本）
查五类：内部矛盾 / 过期未动 / 缺失字段 / 重复记录 / 格式层面的事实错误
用法： python3 scripts/audit.py            输出 JSON
      python3 scripts/audit.py --write     同时写入 data/_claude/audits/
"""
import json, re, sys, difflib
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import importlib.util
spec = importlib.util.spec_from_file_location("srv", ROOT / "server.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)

TODAY = date.today()
NEG = {"rejected", "desk-reject", "withdrawn"}
CLOSE = NEG | {"accepted", "published"}


def d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def days_since(s):
    x = d(s)
    return (TODAY - x).days if x else None


def add(out, level, kind, where, what, fix=""):
    out.append({"level": level, "kind": kind, "where": where, "what": what, "fix": fix})


def check_manuscripts(out):
    for m in srv.list_records("manuscripts"):
        f = f"manuscripts/{m['id']}.md"
        tl = sorted([e for e in (m.get("timeline") or []) if isinstance(e, dict)],
                    key=lambda e: str(e.get("date", "")))
        stage = m.get("stage", "")
        title = (m.get("title") or "")[:28]
        # 1 内部矛盾
        if tl:
            last = tl[-1]
            ev = last.get("event", "")
            if stage in ("submitted", "rnr") and ev in NEG:
                add(out, "高", "内部矛盾", f,
                    f"「{title}」阶段是「{stage}」，但时间线最后一条是「{ev}」（{last.get('date')}）",
                    "把阶段改为 writing，或补一条新的投稿事件")
            if stage == "published" and not any(e.get("event") == "published" for e in tl):
                add(out, "中", "内部矛盾", f, f"「{title}」标为已发表，但时间线里没有 published 事件",
                    "补一条 published 事件，或改回 accepted")
            # current_journal 与时间线不符
            open_j = None
            for e in tl:
                if e.get("event") in ("submitted", "resubmitted"):
                    open_j = e.get("journal", "")
                elif e.get("event") in CLOSE:
                    open_j = None
            cj = (m.get("current_journal") or "").strip()
            if open_j and cj and open_j.strip().lower() != cj.lower():
                add(out, "中", "内部矛盾", f,
                    f"「{title}」当前在投写的是「{cj}」，但时间线显示在「{open_j}」",
                    f"改为「{open_j}」")
            if not open_j and cj:
                add(out, "中", "内部矛盾", f,
                    f"「{title}」写着在投「{cj}」，但时间线里这一轮已经结束了", "清空当前在投期刊")
            # 2 过期未动
            if open_j:
                nd = days_since(tl[-1].get("date"))
                if nd is not None and nd >= 120:
                    add(out, "高", "过期未动", f,
                        f"「{title}」在 {open_j} 已 {nd} 天没有任何消息", "该写催稿信了")
        elif stage not in ("idea",):
            add(out, "低", "缺失", f, f"「{title}」没有任何时间线事件", "至少补一条「启动」")
        # 停滞
        upd = days_since((m.get("updated") or "")[:10])
        if stage not in ("published", "shelved") and upd is not None and upd >= 30:
            add(out, "中", "过期未动", f, f"「{title}」整条记录 {upd} 天没更新过", "确认它是否还在推进")
        # next_action 过期
        na = d(m.get("next_action_due"))
        if na and na < TODAY and stage not in ("published", "shelved"):
            add(out, "中", "过期未动", f,
                f"「{title}」的下一步「{(m.get('next_action') or '')[:20]}」已过期 {(TODAY - na).days} 天",
                "改期或标记完成")
        # 缺失
        if not (m.get("next_action") or "").strip() and stage not in ("published", "shelved"):
            add(out, "低", "缺失", f, f"「{title}」没写下一步", "补上，今日页才能替你盯着")
        # 日期合法性
        for e in tl:
            if e.get("date") and not d(e.get("date")):
                add(out, "高", "事实错误", f, f"「{title}」有一条事件日期无法解析：{e.get('date')}", "改成 YYYY-MM-DD")
            if d(e.get("date")) and d(e.get("date")) > TODAY + timedelta(days=1):
                add(out, "中", "事实错误", f, f"「{title}」有一条事件日期在未来：{e.get('date')}", "确认是否写错年份")


DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")


def check_reading(out):
    recs = srv.list_records("reading")
    for r in recs:
        f = f"reading/{r['id']}.md"
        t = (r.get("title") or "")[:28]
        doi = (r.get("doi") or "").strip()
        if doi and not DOI_RE.match(doi):
            add(out, "中", "事实错误", f, f"「{t}」的 DOI 格式不对：{doi}", "应形如 10.1093/rfs/hhad012")
        y = r.get("year")
        if y and (not str(y).isdigit() or not (1800 <= int(y) <= TODAY.year + 1)):
            add(out, "中", "事实错误", f, f"「{t}」的年份可疑：{y}", "确认年份")
        if r.get("status") == "done" and not (r.get("read_date") or ""):
            add(out, "低", "缺失", f, f"「{t}」标为读完但没有读完日期", "补日期，连续天数与复习队列都依赖它")
        if r.get("status") == "done" and not (r.get("method") or "").strip():
            add(out, "低", "缺失", f, f"「{t}」读完了但没写识别策略/方法", "补上，半年后你会需要它")
        link = (r.get("link") or "")
        if link and not link.startswith(("http://", "https://")):
            add(out, "低", "事实错误", f, f"「{t}」的链接不是合法网址：{link[:40]}", "补全 https://")


def check_dupes(out):
    for coll in ("reading", "journals", "conferences", "ideas", "published"):
        recs = srv.list_records(coll)
        seen = []
        for r in recs:
            t = re.sub(r"[\s\-–—:：,，.。()（）]", "", (r.get("title") or "").lower())
            if not t:
                continue
            for t0, r0 in seen:
                ratio = difflib.SequenceMatcher(None, t, t0).ratio()
                if ratio >= 0.88:
                    add(out, "中", "重复", f"{coll}/{r['id']}.md",
                        f"和「{(r0.get('title') or '')[:26]}」高度相似（{int(ratio * 100)}%）", "确认是否重复录入")
                    break
            seen.append((t, r))


def check_conferences(out):
    for c in srv.list_records("conferences"):
        f = f"conferences/{c['id']}.md"
        t = (c.get("title") or "")[:24]
        dl, st, en = d(c.get("deadline")), d(c.get("start")), d(c.get("end"))
        if dl and st and dl > st:
            add(out, "高", "内部矛盾", f, f"「{t}」的投稿截止（{dl}）晚于会期开始（{st}）", "检查日期")
        if st and en and en < st:
            add(out, "高", "内部矛盾", f, f"「{t}」的结束日期早于开始日期", "检查日期")
        if dl and dl < TODAY and c.get("status") == "watching":
            add(out, "中", "过期未动", f, f"「{t}」截止日已过（{dl}）但状态还是「关注」", "改为已投/放弃")


def check_attachments(out):
    dev = srv.get_device()
    root = (dev.get("paper_root") or "").strip()
    for m in srv.list_records("manuscripts"):
        folder = (m.get("folder") or "").strip()
        if not folder:
            continue
        p = Path(folder).expanduser()
        if not p.is_absolute() and root:
            p = Path(root).expanduser() / folder
        if not p.exists():
            add(out, "中", "缺失", f"manuscripts/{m['id']}.md",
                f"「{(m.get('title') or '')[:24]}」的论文文件夹不存在：{p}", "更新路径或清空")
        pin = (m.get("pinned_figure") or "").strip()
        if pin and not Path(pin).expanduser().exists():
            add(out, "低", "缺失", f"manuscripts/{m['id']}.md", f"钉住的主结果图不存在：{pin}", "重新钉一张")


def main():
    out = []
    check_manuscripts(out)
    check_reading(out)
    check_conferences(out)
    check_dupes(out)
    check_attachments(out)
    # 过滤掉用户忽略过的
    ig_path = srv.CLAUDE / "audit-ignored.json"
    ignored = set()
    if ig_path.exists():
        try:
            ignored = set(json.loads(ig_path.read_text(encoding="utf-8")).get("keys", []))
        except Exception:
            pass
    for o in out:
        o["key"] = f"{o['where']}|{o['kind']}|{o['what'][:40]}"
    out = [o for o in out if o["key"] not in ignored]
    order = {"高": 0, "中": 1, "低": 2}
    out.sort(key=lambda o: (order.get(o["level"], 3), o["kind"]))
    result = {"generated": srv.iso(), "count": len(out),
              "by_level": {lv: sum(1 for o in out if o["level"] == lv) for lv in ("高", "中", "低")},
              "items": out}
    if "--write" in sys.argv:
        p = srv.CLAUDE / "audits" / f"{TODAY.isoformat()}.md"
        lines = [f"# 全库体检 · {TODAY}", "",
                 f"共 {len(out)} 条：高 {result['by_level']['高']} · 中 {result['by_level']['中']} · 低 {result['by_level']['低']}",
                 "", "> 算法部分已完成。引用真伪与语义重复需要 Claude 补充核验。", ""]
        for lv in ("高", "中", "低"):
            items = [o for o in out if o["level"] == lv]
            if not items:
                continue
            lines.append(f"## {lv}（{len(items)}）")
            for o in items:
                lines.append(f"- **[{o['kind']}]** `{o['where']}` {o['what']}")
                if o["fix"]:
                    lines.append(f"  - 建议：{o['fix']}")
            lines.append("")
        p.write_text("\n".join(lines), encoding="utf-8")
        result["written"] = str(p)
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
