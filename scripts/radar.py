#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学术雷达 · 抓取端
============================================================================

每周跑一次：按你设的关键词和关键人去几个源捞新东西，原样存进候选池。

**这一步不经过 AI。** 理由见 radar.py 顶部那段。简单说：让模型上网找论文，
它会编出不存在的论文，而且编得看不出来。抓取交给死代码，AI 只负责在
抓回来的东西里挑、并写成人话。

用法：
    python3 scripts/radar.py             抓一次，存进候选池
    python3 scripts/radar.py --selftest  只测各个源通不通（不写任何数据）
    python3 scripts/radar.py --days 14   往回捞两周（默认 8 天）
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar as R                                    # noqa: E402
import server as srv                                 # noqa: E402
import services as sv                                # noqa: E402


def load_cfg():
    c = srv.get_config() or {}
    rad = c.get("radar") or {}
    prof = c.get("profile") or {}
    return {
        # 关键词：雷达自己的设置优先，没设就沿用「研究方向」里的
        "keywords": [x for x in (rad.get("keywords") or prof.get("keywords") or []) if x][:12],
        # 关键人：[{"name": "...", "orcid": "...", "note": "..."}]
        "people": [x for x in (rad.get("people") or []) if isinstance(x, dict)][:20],
        "sources": rad.get("sources") or ["crossref", "nber", "arxiv"],
        "per_keyword": int(rad.get("per_keyword") or 12),
        "mailto": (rad.get("mailto") or "").strip(),
    }


def collect(days=8, cfg=None):
    """去各个源抓一遍，返回 (条目列表, 每个源的战报)。

    战报很重要：某个源挂了必须能说出来，而不是让周报静悄悄少一块 ——
    「这周这个方向没新东西」和「这周没抓成」是完全不同的两件事，
    而用户只看周报的话，这两者长得一模一样。
    """
    cfg = cfg or load_cfg()
    since = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")
    items, report = [], []
    kws, people = cfg["keywords"], cfg["people"]
    srcs = set(cfg["sources"])

    # ---------- Crossref：按关键词
    if "crossref" in srcs and kws:
        got = fail = 0
        for kw in kws:
            r = sv.crossref_recent(query=kw, since=since,
                                   rows=cfg["per_keyword"], mailto=cfg["mailto"])
            if not r.get("ok"):
                fail += 1
                continue
            for raw in r["items"]:
                items.append(sv._cr_item(raw, hit_by=kw, hit_kind="keyword"))
                got += 1
        report.append({"source": "Crossref · 关键词", "n": got, "ok": fail < len(kws),
                       "detail": f"{len(kws) - fail}/{len(kws)} 个关键词查成功"})

    # ---------- Crossref：按人
    #
    # 只有填了 ORCID 才追得准。Crossref 的 query.author 是**模糊匹配** ——
    # 实测搜 "Zhiguo He" 会把所有姓 He 的人都返回来，完全不能用来盯人。
    # 没填 ORCID 的退化成「姓名查询 + 姓氏复核」，并且**标明可能不准**，
    # 好让周报如实说清楚，而不是假装追到了那个人。
    if "crossref" in srcs and people:
        exact = fuzzy = 0
        for p in people:
            name = (p.get("name") or "").strip()
            orcid = (p.get("orcid") or "").strip()
            if not name and not orcid:
                continue
            if orcid:
                r = sv.crossref_recent(orcid=orcid, since=since,
                                       rows=cfg["per_keyword"], mailto=cfg["mailto"])
                kind = "author"
            else:
                r = sv.crossref_recent(query=name, since=since,
                                       rows=cfg["per_keyword"], mailto=cfg["mailto"])
                kind = "author_fuzzy"
            if not r.get("ok"):
                continue
            last = name.split()[-1].lower() if name.split() else ""
            for raw in r["items"]:
                it = sv._cr_item(raw, hit_by=name or orcid, hit_kind=kind)
                if kind == "author_fuzzy":
                    if last and not any(last in a.lower() for a in it["a"]):
                        continue
                    it["uncertain"] = "按姓名匹配，没有 ORCID，可能不是同一个人"
                    fuzzy += 1
                else:
                    exact += 1
                items.append(it)
        report.append({"source": "Crossref · 关键人", "n": exact + fuzzy, "ok": True,
                       "detail": (f"精确（ORCID）{exact} 条"
                                  + (f"，姓名匹配 {fuzzy} 条（可能不准）" if fuzzy else ""))})

    # ---------- NBER：新 working paper
    if "nber" in srcs:
        r = sv.nber_new(60)
        if r.get("ok"):
            kw_low = [k.lower() for k in kws]
            names = [(p.get("name") or "").split()[-1].lower()
                     for p in people if (p.get("name") or "").split()]
            hit = 0
            for it in r["items"]:
                blob = (it["t"] + " " + it.get("abstract", "")).lower()
                who = " ".join(it["a"]).lower()
                k = next((x for x in kw_low if x and x in blob), "")
                n = next((x for x in names if x and x in who), "")
                if not k and not n:
                    continue                # NBER 每周几十篇，不相关的不进池子
                it = dict(it, hit_by=(k or n),
                          hit_kind=("keyword" if k else "author_fuzzy"))
                if n and not k:
                    it["uncertain"] = "按姓氏匹配，可能不是同一个人"
                items.append(it)
                hit += 1
            report.append({"source": "NBER", "n": hit, "ok": True,
                           "detail": f"本周列出 {len(r['items'])} 篇，命中你的关注 {hit} 篇"})
        else:
            report.append({"source": "NBER", "n": 0, "ok": False,
                           "detail": r.get("detail", "拉取失败")})

    # ---------- arXiv
    if "arxiv" in srcs and kws:
        try:
            ax = sv.arxiv_search(kws, max_results=8)
            n = 0
            for a in (ax.get("items") or []):
                items.append({
                    "t": (a.get("title") or "")[:400],
                    "a": a.get("authors") or [],
                    "y": int(str(a.get("published") or "")[:4] or 0) or None,
                    "j": "arXiv", "d": "", "u": a.get("url") or "",
                    "ty": "working_paper", "date": a.get("published") or "",
                    "abstract": (a.get("summary") or "")[:800],
                    "src": "arxiv", "hit_by": a.get("keyword") or "", "hit_kind": "keyword",
                })
                n += 1
            report.append({"source": "arXiv", "n": n, "ok": True, "detail": ""})
        except Exception as e:
            report.append({"source": "arXiv", "n": 0, "ok": False, "detail": str(e)[:120]})

    return items, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fetch", action="store_true", help="兼容旧的调用方式，可以不带")
    args = ap.parse_args()
    cfg = load_cfg()

    if args.selftest:
        r = sv.radar_selftest(cfg["sources"], mailto=cfg["mailto"])
        print("学术雷达 · 源自检")
        print("=" * 56)
        for s in r["sources"]:
            print(f"  {'✓' if s['ok'] else '✗'} {s['source']:10s} {s['n']} 条  "
                  f"{s.get('detail') or s.get('note') or ''}")
        print("=" * 56)
        print(" ", r["summary"])
        if not r["ok"]:
            print("\n  一个源都连不上，最常见的原因是公司/学校的网络代理挡了外网 API。")
            print("  换个网络再试；或者在设置里只留能连通的那些源。")
        return 0 if r["ok"] else 1

    if not cfg["keywords"] and not cfg["people"]:
        print(json.dumps({"ok": False,
                          "detail": "还没设关键词或关键人 —— 去「设置 → 学术雷达」填几个。"},
                         ensure_ascii=False))
        return 1

    run_id = time.strftime("%Y-W%V")
    t0 = time.time()
    items, report = collect(args.days, cfg)
    pool = R.Pool(srv.CLAUDE / "radar-pool.jsonl")
    st = pool.add(items, run_id=run_id)
    alive = [x for x in report if x.get("ok")]

    out = {
        "ok": bool(alive),
        "run_id": run_id, "days": args.days,
        "keywords": cfg["keywords"],
        "people": [p.get("name") or p.get("orcid") for p in cfg["people"]],
        "fetched": len(items), **st,
        "sources": report,
        "ms": round((time.time() - t0) * 1000),
        # 全挂的时候必须说清楚。周报那边看到这个就该写「这周没抓到」，
        # 而不是拿旧数据凑一份看起来一切正常的报告。
        "detail": ("" if alive else
                   "所有源都没抓到东西 —— 多半是网络问题。这周雷达没有产出，"
                   "不要用旧数据充数。"),
    }
    (srv.CLAUDE / "radar-raw.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if alive else 1


if __name__ == "__main__":
    sys.exit(main())
