#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全工作台搜索 · Workspace-wide search

—— 为什么要重做 ——

原来的搜索是前端拿 bootstrap 里那份内存数据扫一遍，有三个问题：

  1. 搜不到文献索引。5 万条题录压根不在前端，等于全工作台最大的一块内容
     在搜索里是隐形的。
  2. 搜不到功能。用户想找「备份在哪」「怎么配钉钉」，只能自己翻设置页十六张卡。
  3. 跟 bootstrap 体积绑死。记录一多，搜索跟着一起慢。

现在搜四类东西，统一排序：

  记录   所有集合的稿件/文献/想法/日程/生活流水…（用 server 的解析缓存，不重复读盘）
  文献   library.jsonl 里的题录，跳回 Zotero / DOI / 本地 PDF
  箴言   quotes.json
  功能   页面、卡片、设置项 —— 这一类是新的，让搜索框同时是「命令面板」

功能索引写死在下面。它不该从代码里自动抽取：
自动抽取只能拿到卡片标题，而用户搜的是「钉钉」「时区」「token」这种
根本不出现在标题里的词。手写关键词才搜得到。
"""
import re

# ---------------------------------------------------------------- 功能索引
#
# route: 跳到哪一页  card: 跳过去之后要展开并滚动到的卡片（UI.card 的第一个参数）
# kw:    额外关键词，用户实际会打的词，不是卡片标题里的词

FEATURES = [
    # —— 页面
    dict(id="p-today", title="今日", route="today", kw="首页 主页 今天 待办 概览 home"),
    dict(id="p-hub", title="研究总览", route="hub", kw="看板 甘特 生命周期 稿件 进度 kanban gantt"),
    dict(id="p-papers", title="论文库", route="papers", kw="已发表 发表 published 引用"),
    dict(id="p-conf", title="学术会议", route="conferences", kw="截稿 倒计时 投稿 conference deadline"),
    dict(id="p-reading", title="读文献", route="reading", kw="文献 论文 复习 闯关 经验值 reading"),
    dict(id="p-ideas", title="想法画布", route="ideas", kw="灵感 便利贴 idea canvas"),
    dict(id="p-sched", title="日程", route="schedule", kw="日历 月历 安排 calendar schedule"),
    dict(id="p-life", title="生活", route="life", kw="饮食 运动 开支 纪念日 清单 杂务 记账"),
    dict(id="p-ai", title="AI 与额度", route="ai", kw="报告 信箱 头脑风暴 体检 额度 调度器 claude"),
    dict(id="p-set", title="设置与教程", route="settings", kw="配置 偏好 settings"),

    # —— 设置页里的每一张卡（用户最常「找不到」的地方）
    dict(id="c-tutorial", title="完整使用教程", route="settings", card="set-tutorial",
         kw="教程 怎么用 帮助 说明 手册 新手 help"),
    dict(id="c-deco", title="装修模式 · 自定义外观", route="settings", card="set-deco",
         kw="主题 配色 深色 暗色 强调色 布局 隐藏板块 改名 品牌 dark theme"),
    dict(id="c-device", title="本机设置", route="settings", card="set-device",
         kw="论文根目录 路径 备份目录 onedrive 网盘 时区 设备名 快照"),
    dict(id="c-remote", title="远程访问与手机", route="settings", card="set-remote",
         kw="手机 局域网 访问码 只读 解锁 lan 远程 portal 简报 二维码"),
    dict(id="c-peers", title="我的设备", route="settings", card="set-peers",
         kw="多设备 在线 心跳 另一台电脑"),
    dict(id="c-git", title="Git 同步", route="settings", card="set-git",
         kw="github 仓库 token pat 推送 push pull 同步 私有仓库 凭据 密钥"),
    dict(id="c-cal", title="日历订阅", route="settings", card="set-cal",
         kw="outlook google icloud ics 订阅 时区 会议 农历 天气 日历地址"),
    dict(id="c-lib", title="文献索引 · 导入 Zotero", route="reading", card="rd-library",
         kw="zotero mendeley endnote bib ris bibtex citekey 导入 文献库 索引 pdf 跳转"),
    dict(id="c-push", title="推送渠道", route="settings", card="set-push",
         kw="钉钉 dingtalk webhook 加签 提醒 通知 周报推送 邮件推送"),
    dict(id="c-ai", title="AI 直连 API", route="settings", card="set-ai",
         kw="api key 模型 claude chatgpt deepseek 中转 token 计费"),
    dict(id="c-overleaf", title="Overleaf 写作进展", route="settings", card="set-overleaf",
         kw="overleaf latex 写作 字数 进展 git token 论文进度"),
    dict(id="c-mail", title="邮箱收件（手机随手记）", route="settings", card="set-mailin",
         kw="imap 邮箱 收件 授权码 手机记事 发邮件"),
    dict(id="c-sample", title="示例数据", route="settings", card="set-sample",
         kw="示例 样例 隐藏示例 删掉示例 demo"),
    dict(id="c-clean", title="批量清理", route="settings", card="set-clean",
         kw="批量删除 清理 垃圾数据 导入错了"),
    dict(id="c-backup", title="备份时光机", route="settings", card="set-backup",
         kw="备份 快照 恢复 还原 历史版本 time machine 回滚 找回"),
    dict(id="c-import", title="表格导入（Excel / CSV）", route="settings", card="set-import",
         kw="excel csv 导入 表格 xlsx 批量录入"),
    dict(id="c-wizard", title="配置向导", route="settings", card="set-wizard",
         kw="向导 重新配置 初始化 第一次 setup 待办"),
    dict(id="c-diag", title="导出诊断包", route="settings", card="set-diag",
         kw="诊断 报bug 报错 日志 log 出问题 反馈 issue"),

    # —— 其它页面里的重点卡片
    dict(id="c-review", title="复习队列", route="reading", card="rd-review",
         kw="遗忘曲线 间隔重复 复习 该复习了 spaced"),
    dict(id="c-levels", title="关卡 · 主题进度", route="reading", card="rd-levels",
         kw="闯关 主题 进度 目标篇数 level"),
    dict(id="c-gantt", title="甘特图", route="schedule", card="sch-gantt",
         kw="甘特 拖动 工期 时间线 gantt"),
    dict(id="c-quota", title="额度调度器", route="ai", card="ai-quota",
         kw="额度 预算 省钱 自动任务 停产 今晚加把劲 这周别烦我"),
    dict(id="c-inbox", title="Claude 信箱", route="ai", card="ai-inbox",
         kw="信箱 写给 claude 请求 让ai做"),
    dict(id="c-reports", title="AI 报告库", route="ai", card="ai-reports",
         kw="报告 产出 头脑风暴 缺口 体检 审稿人"),
]

# —— 动作：不是页面也不是记录，是「点了会发生一件事」
ACTIONS = [
    dict(id="a-capture", title="快速捕捉一条速记", kw="速记 记一笔 想法 灵感 capture 快捷 c"),
    dict(id="a-new-ms", title="新建稿件", kw="新稿件 加稿件 new manuscript"),
    dict(id="a-new-reading", title="新建文献笔记", kw="新文献 加文献 读了一篇"),
    dict(id="a-new-sched", title="新建日程", kw="新日程 加日程 安排 提醒"),
    dict(id="a-new-idea", title="新建想法", kw="新想法 加想法"),
    dict(id="a-sync", title="立即同步（pull → commit → push）", kw="同步 sync git push 推送"),
    dict(id="a-backup", title="立即备份", kw="备份 快照 backup"),
]


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def search_features(q, limit=8):
    """功能与动作的匹配。词全中就算命中，标题里出现的加权。"""
    q = _norm(q)
    if not q:
        return []
    terms = [t for t in q.split(" ") if t]
    out = []
    for kind, src in (("feature", FEATURES), ("action", ACTIONS)):
        for f in src:
            title = _norm(f["title"])
            hay = title + " " + _norm(f.get("kw"))
            if not all(t in hay for t in terms):
                continue
            score = 60
            if title.startswith(q):
                score += 40
            elif q in title:
                score += 25
            out.append(dict(kind=kind, id=f["id"], title=f["title"],
                            route=f.get("route", ""), card=f.get("card", ""),
                            score=score))
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


# ---------------------------------------------------------------- 记录搜索

# 每个集合里真正值得搜的字段。全字段拼接会把 created/updated/id 也搜进去，
# 打个 "2026" 就命中所有记录，反而没法用。
FIELDS = ["title", "name", "authors", "journal", "current_journal", "target_journal",
          "topic", "question", "background", "method", "data", "findings",
          "contribution", "next_action", "location", "tags", "note", "category",
          "abbrev", "doi", "citekey", "kind", "items", "relates_to", "body"]

COLL_LABEL = {
    "manuscripts": "稿件", "journals": "期刊", "published": "已刊", "conferences": "会议",
    "reading": "文献", "ideas": "想法", "levels": "关卡", "schedule": "日程",
    "reports": "AI 报告", "retros": "复盘", "progress": "写作进展",
    "diet": "饮食", "exercise": "运动", "dates": "日子", "lists": "清单",
    "admin": "事务", "finance": "开支",
}
COLL_VIEW = {
    "manuscripts": "hub", "journals": "settings", "published": "papers",
    "conferences": "conferences", "reading": "reading", "ideas": "ideas",
    "levels": "reading", "schedule": "schedule", "reports": "ai", "retros": "ai",
    "progress": "hub", "diet": "life", "exercise": "life", "dates": "life",
    "lists": "life", "admin": "life", "finance": "life",
}


# 检索串缓存。
#
# 每次按键都要给每条记录拼一遍检索串，10771 条记录时单次搜索 180ms，
# 而且连「备份」这种只该命中功能的查询也得白扫一遍全部记录。
# 按 (集合, id, mtime) 缓存，改过的记录自然失效。
_HAY_CACHE = {}
_HAY_MAX = 80000


def _build_hay(rec):
    parts = []
    for k in FIELDS:
        v = rec.get(k)
        if not v:
            continue
        if isinstance(v, list):
            for x in v:
                parts.append(str(x) if not isinstance(x, dict)
                             else " ".join(str(y) for y in x.values()))
        else:
            parts.append(str(v))
    return _norm(" ".join(parts))


def _hay(rec, coll=""):
    key = (coll, rec.get("id") or "")
    mt = rec.get("_mtime")
    if key[1] and mt is not None:
        hit = _HAY_CACHE.get(key)
        if hit is not None and hit[0] == mt:
            return hit[1]
        h = _build_hay(rec)
        if len(_HAY_CACHE) < _HAY_MAX:
            _HAY_CACHE[key] = (mt, h)
        return h
    return _build_hay(rec)


def _snippet(rec, terms, width=90):
    """截一段包含关键词的上下文，让人一眼看出为什么命中。"""
    body = str(rec.get("body") or "")
    low = body.lower()
    for t in terms:
        i = low.find(t)
        if i >= 0:
            s = max(0, i - width // 3)
            frag = body[s:s + width].replace("\n", " ").strip()
            return ("…" if s > 0 else "") + frag + ("…" if s + width < len(body) else "")
    for k in ("question", "findings", "method", "note"):
        v = rec.get(k)
        if v:
            return str(v)[:width].replace("\n", " ")
    return ""


# 记录快照。
#
# 单次搜索的成本拆开来看：扫描匹配只要 13ms，list_records 要 106ms
# （一万多个文件挨个 stat + 浅拷贝）。而打一个词会连着搜好几次，
# 每次都重新 stat 整个工作台纯属浪费。
#
# 所以给搜索单独留一份短命快照：两秒内复用，两秒后重新取。
# 搜索结果比磁盘晚两秒，没有任何人会察觉；每敲一个字卡 100ms，人人都察觉。
# 注意这**只用于搜索**——编辑、保存、渲染都还是走实时的 list_records。
import threading as _th

_SNAP = {"at": 0.0, "data": None, "colls": None, "gen": 0}
_SNAP_LOCK = _th.Lock()
SNAP_TTL = 2.0


def _snapshot(list_records, collections):
    import time as _t

    def _fresh():
        return (_SNAP["data"] is not None and _SNAP["colls"] == tuple(collections)
                and _t.monotonic() - _SNAP["at"] < SNAP_TTL)

    if _fresh():
        return _SNAP["data"]
    # 重建要加锁，否则十个并发搜索会各自扫一遍全盘（每次 100ms+）。
    # 压测里 10 搜 + 3 写并发时，中位延迟因此到了 3 秒。
    # 拿到锁之后再查一次新鲜度：等锁的那几个直接用别人刚建好的。
    with _SNAP_LOCK:
        if _fresh():
            return _SNAP["data"]
        # 扫盘要 100ms 左右，这中间很可能正好有人存了一条记录。
        # 只把 data 置空是拦不住的：那次失效发生在我们开扫之后、写回之前，
        # 于是我们转手又把「写之前的那一份」当成最新发布出去，
        # 接下来两秒谁都搜不到刚存的东西 —— 正是这套失效机制要防的事。
        # 记下开扫时的代号，写回时对不上就说明期间有人改过，这一份不作数。
        gen = _SNAP["gen"]
        data = {}
        for c in collections:
            try:
                data[c] = list_records(c)
            except Exception:
                data[c] = []
        if _SNAP["gen"] == gen:
            _SNAP.update({"at": _t.monotonic(), "data": data,
                          "colls": tuple(collections)})
        return data


def invalidate_snapshot():
    """写完记录后叫一声，别让搜索在两秒里看不到刚存的东西。"""
    _SNAP["data"] = None
    _SNAP["gen"] = _SNAP["gen"] + 1


def search_records(list_records, collections, q, limit=40):
    q = _norm(q)
    if not q:
        return []
    terms = [t for t in q.split(" ") if t]
    out = []
    snap = _snapshot(list_records, collections)
    for coll in collections:
        recs = snap.get(coll) or []
        for r in recs:
            hay = _hay(r, coll)
            if not all(t in hay for t in terms):
                continue
            title = str(r.get("title") or r.get("name") or "")
            tl = _norm(title)
            # 标题命中远比正文命中有用
            score = 30
            if tl == q:
                score = 100
            elif tl.startswith(q):
                score = 80
            elif q in tl:
                score = 65
            elif all(t in tl for t in terms):
                score = 55
            # 未完成 / 在投的东西更可能是你现在要找的
            if r.get("stage") in ("rnr", "submitted") or r.get("status") in ("reading", "to-read"):
                score += 6
            if r.get("done") is True:
                score -= 8
            out.append(dict(
                kind="record", coll=coll, label=COLL_LABEL.get(coll, coll),
                view=COLL_VIEW.get(coll, "today"), id=r.get("id", ""),
                title=title or "（无题）",
                meta=" · ".join(str(x) for x in [
                    r.get("year") or "", r.get("journal") or r.get("category") or "",
                    r.get("read_date") or r.get("date") or r.get("start")
                    or r.get("deadline") or "",
                ] if x)[:80],
                snippet=_snippet(r, terms),
                score=score,
            ))
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


# ---------------------------------------------------------------- 汇总

def search_all(q, list_records, collections, library=None, quotes=None,
               manager="zotero", open_targets=None, limit=30):
    """把四类结果合到一起，按分数排，但保证每一类都有露脸的机会。"""
    q = (q or "").strip()
    if not q:
        return {"ok": True, "q": "", "groups": [], "total": 0}
    terms = [t for t in _norm(q).split(" ") if t]

    feats = search_features(q, limit=8)
    recs = search_records(list_records, collections, q, limit=40)

    libs = []
    if library is not None:
        try:
            r = library.search(q=q, limit=12)
            for it in r.get("items", []):
                libs.append(dict(
                    kind="library", id=it.get("k", ""), title=it.get("t", ""),
                    meta=" · ".join(str(x) for x in [
                        "; ".join((it.get("a") or [])[:3]), it.get("y") or "",
                        it.get("j") or ""] if x)[:90],
                    citekey=it.get("c", ""),
                    open=(open_targets(it, manager) if open_targets else []),
                    score=50,
                ))
            lib_total = r.get("total", 0)
        except Exception:
            lib_total = 0
    else:
        lib_total = 0

    qs = []
    if quotes:
        for x in quotes:
            hay = _norm(str(x.get("t", "")) + " " + str(x.get("s", "")))
            if all(t in hay for t in terms):
                qs.append(dict(kind="quote", title=x.get("t", ""),
                               meta=x.get("s", ""), score=20))
                if len(qs) >= 5:
                    break

    groups = []
    if feats:
        groups.append({"key": "feature", "label": "功能与设置", "items": feats,
                       "total": len(feats)})
    if recs:
        groups.append({"key": "record", "label": "我的记录", "items": recs[:limit],
                       "total": len(recs)})
    if libs:
        groups.append({"key": "library", "label": "文献索引", "items": libs,
                       "total": lib_total})
    if qs:
        groups.append({"key": "quote", "label": "箴言", "items": qs, "total": len(qs)})
    total = sum(g["total"] for g in groups)
    return {"ok": True, "q": q, "groups": groups, "total": total}
