# -*- coding: utf-8 -*-
"""领域助读 · 算法部分

  python3 scripts/primer.py --plan            输出本周该给哪个领域做助读（供 Claude 写内容）
  python3 scripts/primer.py --add <md路径>     把 Claude 写好的助读解析成文献记录，进读文献库
  python3 scripts/primer.py --queue           把「该做助读了」写进自动任务队列

分工跟周报一样：挑领域、去重、建记录、算进度，全是算法干的，不花额度；
Claude 只负责写那几段人类才写得出来的中文重述。
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server as srv  # noqa: E402


def week_key(d=None):
    d = d or datetime.now()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def fields():
    """用户设的关注领域。没设就从研究关键词里退而求其次。"""
    cfg = srv.get_config()
    fs = (cfg.get("reading") or {}).get("fields") or []
    out = []
    for f in fs:
        if isinstance(f, str):
            out.append({"name": f, "active": False})
        elif isinstance(f, dict) and f.get("name"):
            out.append({"name": f["name"], "active": bool(f.get("active"))})
    if not out:
        kws = (cfg.get("profile") or {}).get("keywords") or []
        out = [{"name": k, "active": i == 0} for i, k in enumerate(kws[:3])]
    return out


def plan():
    fs = fields()
    if not fs:
        return {"ok": False, "detail": "还没设关注领域（读文献页 → 领域设置），也没有研究关键词"}
    pick = next((f for f in fs if f.get("active")), fs[0])
    reading = srv.list_records("reading")
    same = [r for r in reading if (r.get("topic") or "").lower() == pick["name"].lower()]
    return {
        "ok": True,
        "week": week_key(),
        "field": pick["name"],
        "fields": fs,
        "keywords": (srv.get_config().get("profile") or {}).get("keywords") or [],
        "existing": [r.get("title") for r in reading if r.get("title")],
        "existing_in_field": [r.get("title") for r in same if r.get("title")],
        "done_in_field": len([r for r in same if r.get("status") == "done"]),
        "outfile": str(srv.CLAUDE / "outbox" / f"primer-{week_key()}-{srv.slugify(pick['name'])}.md"),
    }


HEAD_RE = re.compile(r"^###\s*\d+[.、]\s*(.+?)\s*$", re.M)


def parse_primer(md):
    """从 Claude 写的助读里把论文条目抠出来。
    标题行形如：### 1. He & Krishnamurthy (2013), Intermediary Asset Pricing"""
    items = []
    parts = HEAD_RE.split(md)
    # parts = [前言, 标题1, 正文1, 标题2, 正文2, ...]
    for i in range(1, len(parts) - 1, 2):
        head, body = parts[i].strip(), parts[i + 1]
        m = re.match(r"^(.*?)\s*[（(](\d{4})[）)]\s*[,，、]?\s*(.*)$", head)
        if m:
            authors, year, title = m.group(1).strip(), m.group(2), m.group(3).strip()
        else:
            m2 = re.search(r"\((\d{4})\)", head)
            authors = head.split("(")[0].strip() if m2 else ""
            year = m2.group(1) if m2 else ""
            title = head
        def grab(label):
            mm = re.search(r"\*\*" + label + r"\*\*[：:]\s*(.+?)(?=\n\s*[-*]\s*\*\*|\n#|\Z)", body, re.S)
            return re.sub(r"\s+", " ", mm.group(1)).strip() if mm else ""
        items.append({
            "title": title.strip(" ，,。.") or head,
            "authors": [a.strip() for a in re.split(r"[&、,，和]| and ", authors) if a.strip()],
            "year": year,
            "why_first": grab("为什么先读它"),
            "question": grab("它想回答的问题"),
            "method": grab("它怎么做的"),
            "findings": grab("结论与它的边界"),
            "next_q": grab("读完带着这个问题去看下一篇"),
        })
    return items


def add(path):
    p = Path(path)
    if not p.exists():
        return {"ok": False, "detail": f"找不到 {path}"}
    md = p.read_text(encoding="utf-8")
    field = ""
    mf = re.search(r"^#\s*领域助读\s*·\s*(.+?)\s*·", md, re.M)
    if mf:
        field = mf.group(1).strip()
    items = parse_primer(md)
    if not items:
        return {"ok": False, "detail": "没解析出论文条目——检查一下标题行是不是「### 1. 作者 (年份), 标题」的格式"}
    existing = {(r.get("title") or "").strip().lower() for r in srv.list_records("reading")}
    created = skipped = 0
    order = 0
    for it in items:
        order += 1
        if it["title"].strip().lower() in existing:
            skipped += 1
            continue
        srv.write_record("reading", {
            "title": it["title"],
            "authors": it["authors"],
            "year": it["year"],
            "status": "to-read",
            "level": "deep",
            "topic": field,
            "question": it["question"],
            "method": it["method"],
            "findings": it["findings"],
            "primer_week": week_key(),
            "primer_order": order,
            "source": "primer",
            "body": "\n\n".join(x for x in [
                ("**为什么先读它**：" + it["why_first"]) if it["why_first"] else "",
                ("**读完带着这个问题去看下一篇**：" + it["next_q"]) if it["next_q"] else "",
            ] if x),
        })
        created += 1
    return {"ok": True, "field": field, "created": created, "skipped": skipped,
            "total": len(items), "week": week_key()}


def queue():
    """把「本周该做领域助读」塞进自动任务队列，等额度富余时由 Claude 执行。"""
    p = plan()
    if not p.get("ok"):
        return p
    qpath = srv.QUEUE_PATH
    q = srv._load_json(qpath, {"tasks": []})
    if not isinstance(q.get("tasks"), list):
        q["tasks"] = []
    tag = f"primer-{p['week']}-{p['field']}"
    if any(t.get("tag") == tag for t in q["tasks"]):
        return {"ok": True, "detail": "本周已经排过了", "tag": tag}
    q["tasks"].append({
        "tag": tag, "kind": "field-primer", "cost": 3,
        "title": f"给「{p['field']}」做本周领域助读",
        "skill": "field-primer",
        "created": srv.iso(),
        "expires": "",
    })
    srv._save_json(qpath, q)
    return {"ok": True, "queued": tag}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--add", default="")
    ap.add_argument("--queue", action="store_true")
    a = ap.parse_args()
    if a.add:
        r = add(a.add)
    elif a.queue:
        r = queue()
    else:
        r = plan()
    print(json.dumps(r, ensure_ascii=False, indent=1))
