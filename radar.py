#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学术雷达 · 候选池与校验
============================================================================

这个文件是整条链路里**不允许 AI 插手**的那一半。

分工是这样定的：

    抓取（services.py）  →  候选池（这里）  →  AI 挑选与写作（skill）
                                  ↑                      │
                                  └────── 校验（这里）────┘

为什么 AI 只能站在中间那一段：

语言模型总结文献时最典型的失败不是「说错」，而是「说了一篇不存在的论文」。
它会按印象生成一条看起来完全合理的记录 —— 标题像那么回事、作者确实是这个
领域的人、年份也对得上，但那篇论文根本没有。你拿着标题去搜，搜不到，
才知道白读了一周。而且这种错**看不出来**：周报读起来跟真的一模一样。

光靠提示词说「不许编」是挡不住的。所以这里做两件硬事：

  1. 候选池     AI 能谈论的东西**只有**这个池子里的条目。池子是抓来的，
                每条有稳定指纹。
  2. 校验器     AI 交回来的每一条，都要用指纹回查池子，并逐字段比对
                标题、作者、年份、期刊、链接。对不上就**整条丢掉**，
                并且如实记账「这周有 N 条因为对不上被丢了」。

校验器是普通的字符串比对，不是又一个模型 —— 用 AI 去验 AI 是循环论证，
一个会编的模型完全可能给另一个编出来的条目盖章。

只用标准库。
"""
import hashlib
import itertools
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

_TMP_SEQ = itertools.count(1)

POOL_MAX = 20000            # 候选池上限，超了从最旧的开始丢
SEEN_KEEP_DAYS = 400        # 「推过了」记多久，避免同一篇年年推


# ============================================================ 指纹

def _norm(s):
    """归一化：大小写、标点、空格、全半角、重音，全部抹平。

    比对必须在归一化之后做，否则 AI 把 “Liquidity and Leverage” 写成
    "Liquidity And Leverage" 就会被判成造假 —— 那是误伤，不是抓贼。
    """
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


def _norm_doi(s):
    s = str(s or "").strip().lower()
    s = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s).strip().strip("{}").rstrip(".")
    return s if s.startswith("10.") else ""


def fingerprint(item):
    """一条候选的稳定指纹。

    有 DOI 用 DOI —— 它是全球唯一的。
    没有就用「归一化标题 + 年份」做哈希；同一篇 working paper 在
    NBER 和 SSRN 上各挂一份，标题一样，这样能认出是同一篇。
    """
    d = _norm_doi(item.get("d") or item.get("doi"))
    if d:
        return "doi:" + d
    t = _norm(item.get("t") or item.get("title"))
    if not t:
        return ""
    y = item.get("y") or item.get("year") or ""
    h = hashlib.sha1(f"{t}|{y}".encode("utf-8")).hexdigest()[:16]
    return "ti:" + h


# ============================================================ 候选池

class Pool:
    """抓回来的东西原样存这里。一行一条 jsonl。

    存原样很重要：校验的时候要拿 AI 说的和**当初抓到的**逐字比，
    如果池子里存的是加工过的版本，就比不出来了。
    """

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def load(self):
        if not self.path.exists():
            return []
        out = []
        try:
            for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    if isinstance(o, dict):
                        out.append(o)
                except Exception:
                    continue          # 坏行跳过，不能让一行毁掉整个池子
        except OSError:
            return []
        return out

    def _write(self, items):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp{os.getpid()}-{next(_TMP_SEQ)}")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                for it in items[-POOL_MAX:]:
                    f.write(json.dumps(it, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    @staticmethod
    def _title_fp(item):
        """只按「标题 + 年份」算的辅助指纹。

        同一篇论文在 Crossref 那份有 DOI、在 NBER 那份没有，
        主指纹一个是 doi:… 一个是 ti:…，光比主指纹会当成两篇 ——
        于是池子里一篇论文占两条，周报里同一篇出现两次。
        所以主指纹之外再比一次标题。
        """
        t = _norm(item.get("t") or item.get("title"))
        if not t:
            return ""
        y = item.get("y") or item.get("year") or ""
        return "ti:" + hashlib.sha1(f"{t}|{y}".encode("utf-8")).hexdigest()[:16]

    def add(self, items, run_id=""):
        """并进池子。已经在里面的只更新「这周又出现了一次」，不重复。"""
        with self._lock:
            cur = self.load()
            by_fp, by_title = {}, {}
            for i, it in enumerate(cur):
                fp = it.get("fp") or fingerprint(it)
                if fp:
                    by_fp[fp] = i
                tf = self._title_fp(it)
                if tf:
                    by_title.setdefault(tf, i)
            added = dup = skipped = 0
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            for raw in (items or []):
                if not isinstance(raw, dict):
                    skipped += 1
                    continue
                fp = fingerprint(raw)
                if not fp:
                    skipped += 1      # 连标题都没有的，留着也没用
                    continue
                idx = by_fp.get(fp)
                if idx is None:
                    tf = self._title_fp(raw)
                    if tf:
                        idx = by_title.get(tf)
                if idx is not None:
                    old = cur[idx]
                    old["seen_runs"] = (old.get("seen_runs") or 0) + 1
                    old["last_seen"] = stamp
                    # 补空字段：NBER 那份可能有摘要，Crossref 那份可能有 DOI
                    for k in ("d", "u", "j", "abstract", "date"):
                        if raw.get(k) and not old.get(k):
                            old[k] = raw[k]
                    srcs = set(old.get("srcs") or ([old.get("src")] if old.get("src") else []))
                    if raw.get("src"):
                        srcs.add(raw["src"])
                    if len(srcs) > 1:
                        old["srcs"] = sorted(x for x in srcs if x)
                    # 合并之后主指纹可能变了（补上了 DOI），重新登记
                    nfp = fingerprint(old)
                    if nfp:
                        old["fp"] = nfp
                        by_fp[nfp] = idx
                    tf2 = self._title_fp(old)
                    if tf2:
                        by_title.setdefault(tf2, idx)
                    dup += 1
                    continue
                it = dict(raw)
                it["fp"] = fp
                it["first_seen"] = stamp
                it["last_seen"] = stamp
                it["seen_runs"] = 1
                it["run_id"] = run_id
                it["status"] = "new"          # new / picked / shown / ignored
                cur.append(it)
                by_fp[fp] = len(cur) - 1
                tf = self._title_fp(it)
                if tf:
                    by_title.setdefault(tf, len(cur) - 1)
                added += 1
            self._write(cur)
            return {"added": added, "duplicate": dup, "skipped": skipped,
                    "total": len(cur)}

    def candidates(self, run_id="", limit=200):
        """这次要交给 AI 挑的候选。只给没推过的。"""
        out = [it for it in self.load()
               if it.get("status") == "new"
               and (not run_id or it.get("run_id") == run_id)]
        out.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
        return out[:limit]

    def mark(self, fps, status):
        """标记一批条目的状态（挑中了 / 已经展示过 / 忽略）。

        指纹一律按字符串处理：调用方传进来的可能是 AI 给的原始值，
        而那可能是字典、列表、数字 —— 直接扔进 set 会抛 unhashable。
        """
        want = set(str(x) for x in (fps or []) if x and isinstance(x, (str, int, float)))
        if not want:
            return 0
        with self._lock:
            cur = self.load()
            n = 0
            for it in cur:
                if (it.get("fp") or "") in want:
                    it["status"] = status
                    n += 1
            self._write(cur)
            return n

    def by_fp(self):
        return {(it.get("fp") or fingerprint(it)): it for it in self.load()}


# ============================================================ 校验器

# 允许 AI 改动标题到什么程度。
# 完全不许动是不现实的：模型经常把破折号换成连字符、去掉副标题的冒号，
# 这些是排版差异不是造假。但也不能太松，否则「换个词」就混过去了。
TITLE_MIN_OVERLAP = 0.85


def _tok(s):
    return [w for w in _norm(s).split(" ") if w]


def _overlap(a, b):
    """两个标题的词重合度（对短标题友好的 Jaccard 变体）。"""
    A, B = set(_tok(a)), set(_tok(b))
    if not A or not B:
        return 0.0
    return len(A & B) / max(len(A), len(B))


def verify(picks, pool, strict_authors=True):
    """核对 AI 挑出来的条目，逐条判定「这条能不能进周报」。

    picks: [{"fp":..., "title":..., "why":..., "authors":[...], "year":..., ...}]
    pool:  Pool 实例，或者 {fp: item} 字典

    返回 {"ok":[...], "rejected":[...], "stats":{...}}。
    ok 里的每一条都带上**池子里那份原始记录**，写周报时用它、
    而不是用 AI 复述的版本 —— 这样连引用都不可能被改动。
    """
    table = pool.by_fp() if hasattr(pool, "by_fp") else dict(pool or {})
    ok, rejected = [], []
    for p in (picks or []):
        if not isinstance(p, dict):
            rejected.append({"pick": p, "reason": "不是一条记录"})
            continue
        # AI 交回来的字段什么类型都可能：fp 给成数字、title 给成 None
        # 都是真见过的。这里全部当字符串处理，不能想当然地 .strip()。
        #
        # 字段名也必须两种都认。技能里让它写 title/authors/year，
        # 但候选池本身用的是 t/a/y，模型看着池子照抄短名是很自然的事。
        # 只认长名的后果不是「报错」，而是**那一条检查静悄悄地不执行了** ——
        # 校验器看起来在工作，实际上放行了一切。这比不做检查更危险。
        fp = str(p.get("fp") or "").strip()
        claimed_title = str(p.get("title") or p.get("t") or "")

        # 1) 得先在池子里找到这一条。三条路，从最硬的证据开始：
        #    指纹 → 自己的 DOI 算出来的指纹 → 标题几乎一模一样。
        src = table.get(fp)
        if not src:
            # DOI 是全球唯一的，模型忘了抄 fp 但给了 DOI 的情况很常见。
            # 不用它就等于把最硬的那个证据扔了，然后退化成模糊的标题比对 ——
            # 结果是真论文被误判成「编的」，周报还会煞有介事地说「AI 编了一条」。
            self_fp = fingerprint(p)
            if self_fp and self_fp in table:
                src, fp = table[self_fp], self_fp
        if not src:
            # 指纹和 DOI 都对不上，最后按标题找一次；几乎一字不差才算。
            hit = None
            for k, v in table.items():
                if _overlap(claimed_title, v.get("t") or "") >= 0.95:
                    hit, fp = v, k
                    break
            if not hit:
                if not claimed_title:
                    rejected.append({"pick": p, "reason": "这条既没有指纹也没有标题",
                                     "detail": "无法核对，直接丢弃"})
                    continue
                rejected.append({"pick": p, "reason": "候选池里没有这一条",
                                 "detail": f"指纹 {fp or '(空)'} 不存在，"
                                           f"DOI 也查不到，标题还匹配不上："
                                           f"{claimed_title[:80]}"})
                continue
            src = hit

        # 2) 标题不能被改写
        ov = _overlap(claimed_title, src.get("t") or "")
        if claimed_title and ov < TITLE_MIN_OVERLAP:
            rejected.append({"pick": p, "reason": "标题和抓到的对不上",
                             "detail": f"AI 写的：{claimed_title[:70]}｜"
                                       f"实际是：{(src.get('t') or '')[:70]}"})
            continue

        # 3) 年份不能编。差一年放过（网络首发与正式见刊常常跨年）
        py, sy = p.get("year") or p.get("y"), src.get("y")
        try:
            if py and sy and abs(int(py) - int(sy)) > 1:
                rejected.append({"pick": p, "reason": "年份对不上",
                                 "detail": f"AI 写 {py}，实际 {sy}"})
                continue
        except (TypeError, ValueError):
            pass

        # 4) 作者不能张冠李戴。只要求「AI 提到的人确实在作者名单里」，
        #    不要求列全 —— 周报里写「He 和 Krishnamurthy 那篇」是正常的。
        pa = p.get("authors")
        if pa is None:
            pa = p.get("a")          # 池子里叫 a，模型照抄短名是常事，见上面那段
        if strict_authors and isinstance(pa, (list, tuple)) and pa:
            # 比「词」，不比「子串」。之前是把真实作者拼成一个大字符串再看姓氏
            # 在不在里面 —— 那样 "Zhiguo He" 的姓 he 会在 "Ashenfelter" 里命中，
            # 于是硬塞进来的作者反而蒙混过关。姓氏短的中文姓（He / Li / Xu）
            # 全都踩这个坑，而这恰恰是最需要盯住的一类人。
            have = set()
            for x in (src.get("a") or []):
                have.update(_tok(x))
            bad = []
            for a in list(pa)[:12]:
                toks = _tok(a)
                # 认「最后一个词块」——英文名里那就是姓。用集合比而不是按位置比，
                # 所以 "Zhiguo He" / "He, Zhiguo" / "Z. He" 都过得去，
                # 而把姓换掉的（"Tobias Bernanke"）和整个人都是新加的
                # （"Ben Bernanke"）都拦得住。
                if toks and toks[-1] not in have:
                    bad.append(str(a))
            if bad:
                rejected.append({"pick": p, "reason": "作者对不上",
                                 "detail": f"AI 提到 {', '.join(bad[:3])}，"
                                           f"但作者是 {', '.join(src.get('a') or [])[:100]}"})
                continue

        # 5) 链接只认抓来的那个。模型很爱「顺手」给一个看起来对的 URL
        item = dict(src)
        item["why"] = str(p.get("why") or p.get("reason") or "")[:400]
        item["rank"] = p.get("rank")
        ok.append(item)

    return {"ok": ok, "rejected": rejected,
            "stats": {"picked": len(picks or []), "passed": len(ok),
                      "dropped": len(rejected)}}


def verdict_line(res):
    """给周报用的一句人话交代。**丢掉的必须说**，不能默默吞掉。"""
    s = res.get("stats") or {}
    if not s.get("dropped"):
        return ""
    reasons = {}
    for r in res.get("rejected") or []:
        reasons[r.get("reason") or "?"] = reasons.get(r.get("reason") or "?", 0) + 1
    detail = "、".join(f"{k} {v} 条" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]))
    return (f"（这次 AI 挑了 {s.get('picked')} 条，有 {s.get('dropped')} 条没通过核对，"
            f"已经丢掉：{detail}。核对是拿抓回来的原始记录逐字比的。）")
