#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献索引层 · Library index

—— 为什么要单独一层 ——

实测：把 3000 条文献按现有结构（一篇一个 md）塞进「读文献」页，
切页要 2 秒、页面 28581 个 DOM 节点，而且每次 render() 都重来一遍。
Zotero 库动辄几千上万条，直接镜像进来必卡。

所以分两层：

  索引层（这个文件）  几千上万条题录，一个 jsonl 文件，**不进 bootstrap**，
                     只在你搜索时按需返回前若干条。一行一篇，点开跳回 Zotero/DOI/PDF。
                     定位是「找得到、跳得过去」，不是「在这里读」。

  精读层（data/reading/*.md）  你真正精读过的几十上百篇，带研究问题、识别策略、
                     结论、复习队列、经验值。由索引「提升」而来。

一句话：不逼任何人放弃 Zotero，我们只做那层索引和跳转。

存储用 jsonl（一行一条）而不是一个大 JSON：
git diff 时只显示真正变了的那几行，不会因为加一篇就整文件重写。

只用标准库。
"""
import itertools
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

_TMP_SEQ = itertools.count(1)

MAX_ITEMS = 200000          # 硬上限，防止误导入把磁盘写爆

# 同一篇论文可能同时来自三个地方，冲突时谁说了算。
# Zotero 是你亲手整理、亲手改过的，最可信；
# .bib/.ris 是从数据库导出的，字段规范但可能过时；
# 从 PDF 里抠出来的最不可信 —— 很多 PDF 的元数据就是一串排版软件的默认值。
SOURCE_RANK = {"zotero": 3, "bib": 2, "ris": 2, "csl": 2, "nbib": 2, "pdf": 1}
SOURCE_LABEL = {"zotero": "Zotero", "bib": "BibTeX", "ris": "RIS",
                "csl": "CSL-JSON", "nbib": "PubMed", "pdf": "PDF 文件夹"}
SEARCH_CAP = 500            # 单次搜索最多返回多少条（界面默认只画 50）


# ============================================================ 工具

def _norm_doi(s):
    """DOI 归一化。BibTeX 里常写成 {10.1257/aer...}，花括号必须先剥掉，
    否则去重时同一篇会被当成两篇。"""
    s = str(s or "").strip().strip("{}").strip().lower()
    if not s:
        return ""
    s = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    s = s.strip().strip("{}").strip().rstrip(".")
    return s if s.startswith("10.") else ("" if "/" not in s else s)


def _norm_title(s):
    """标题归一化，用来去重：去掉大小写、标点、多余空格、LaTeX 花括号。"""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = re.sub(r"[{}\\]", "", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


# 重音符号 → 真字符。大小写都要有：BibTeX 里 {\"O}sterreich 和 {\"o}ffentlich 一样常见。
_ACCENT = {
    ("'", "a"): "á", ("'", "e"): "é", ("'", "i"): "í", ("'", "o"): "ó", ("'", "u"): "ú",
    ("'", "A"): "Á", ("'", "E"): "É", ("'", "I"): "Í", ("'", "O"): "Ó", ("'", "U"): "Ú",
    ("'", "c"): "ć", ("'", "n"): "ń", ("'", "s"): "ś", ("'", "y"): "ý",
    ("`", "a"): "à", ("`", "e"): "è", ("`", "i"): "ì", ("`", "o"): "ò", ("`", "u"): "ù",
    ("`", "A"): "À", ("`", "E"): "È", ("`", "O"): "Ò", ("`", "U"): "Ù",
    ('"', "a"): "ä", ('"', "e"): "ë", ('"', "i"): "ï", ('"', "o"): "ö", ('"', "u"): "ü",
    ('"', "A"): "Ä", ('"', "E"): "Ë", ('"', "O"): "Ö", ('"', "U"): "Ü", ('"', "y"): "ÿ",
    ("^", "a"): "â", ("^", "e"): "ê", ("^", "i"): "î", ("^", "o"): "ô", ("^", "u"): "û",
    ("^", "A"): "Â", ("^", "E"): "Ê", ("^", "O"): "Ô", ("^", "U"): "Û",
    ("~", "a"): "ã", ("~", "n"): "ñ", ("~", "o"): "õ",
    ("~", "A"): "Ã", ("~", "N"): "Ñ", ("~", "O"): "Õ",
    ("c", "c"): "ç", ("c", "C"): "Ç", ("v", "s"): "š", ("v", "c"): "č", ("v", "z"): "ž",
    ("v", "S"): "Š", ("v", "C"): "Č", ("v", "Z"): "Ž",
    (".", "z"): "ż", ("=", "a"): "ā", ("=", "e"): "ē", ("u", "a"): "ă",
}
_SPECIAL = {r"\ss": "ß", r"\o": "ø", r"\O": "Ø", r"\ae": "æ", r"\AE": "Æ",
            r"\aa": "å", r"\AA": "Å", r"\l": "ł", r"\L": "Ł", r"\i": "i", r"\j": "j"}
_SIMPLE = {r"\&": "&", r"\%": "%", r"\_": "_", r"\#": "#", r"\$": "$",
           "---": "—", "--": "–", "``": "\u201c", "''": "\u201d", r"\-": ""}

# \{ 和 \} 是「真的花括号」，不能跟 BibTeX 的分组括号一起被剥掉，先藏起来
_ESC_L, _ESC_R, _ESC_B = "\x01", "\x02", "\x03"


def _accent_sub(m):
    return _ACCENT.get((m.group(1), m.group(2)), m.group(2))


def _clean(s):
    """清掉 BibTeX 的分组花括号和 LaTeX 转义，让标题能正常显示、搜索、去重。"""
    s = str(s or "").strip()
    if not s:
        return ""
    s = s.replace("\\\\", _ESC_B).replace(r"\{", _ESC_L).replace(r"\}", _ESC_R)
    for a, b in _SIMPLE.items():
        if a in s:
            s = s.replace(a, b)
    # {\"{O}} / {\"O} / \"{O} / \"O 四种写法都得认
    s = re.sub(r"\{?\\([`'\"^~=.cvu])\s*\{?([A-Za-z])\}?\}?", _accent_sub, s)
    for a, b in sorted(_SPECIAL.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(r"\{?" + re.escape(a) + r"\}?(?![A-Za-z])", b, s)
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)          # 剩下的命令直接丢
    s = s.replace("{", "").replace("}", "")
    s = s.replace(_ESC_L, "{").replace(_ESC_R, "}").replace(_ESC_B, "\\")
    return re.sub(r"\s+", " ", s).strip()


def _year(s):
    if isinstance(s, int):
        return s
    m = re.search(r"(1[6-9]\d{2}|20\d{2}|21\d{2})", str(s or ""))
    return int(m.group(1)) if m else None


def _year_num(v):
    """排序用：任何东西都要能变成一个能比大小的数。"""
    if isinstance(v, int):
        return v
    return _year(v) or 0


def _authors_from_bibtex(s):
    """'Last, First and Other, Name' → ['Last, First', 'Other, Name']"""
    s = _clean(s)
    if not s:
        return []
    parts = re.split(r"\s+and\s+", s, flags=re.IGNORECASE)
    return [p.strip().rstrip(",") for p in parts if p.strip()][:40]


def _mk_item(**kw):
    """统一的一条索引记录。字段名故意用短名——几万条时体积差得出来。"""
    it = {
        "k": kw.get("k") or "",            # 原平台的 key（Zotero itemKey / bib citekey）
        "t": _clean(kw.get("t"))[:400],    # 题目
        "a": kw.get("a") or [],            # 作者
        # 年份必须**在这里**统一成 int/None。各个来源给的类型不一样：
        # 解析器给 int，pdfmeta 从 PDF 元数据里抠出来的是字符串。
        # 混着存进索引，按年份排序时就会 TypeError（str 和 int 比不了），
        # 整个搜索接口 500 —— 而且只有在真导过 PDF 的库里才会犯。
        "y": _year(kw.get("y")) if not isinstance(kw.get("y"), int) else kw.get("y"),
        "j": _clean(kw.get("j"))[:200],    # 期刊 / 出处
        "d": _norm_doi(kw.get("d")),       # DOI
        "u": (kw.get("u") or "").strip()[:500],   # 链接
        "p": (kw.get("p") or "").strip()[:500],   # 本地 PDF 绝对路径（本机有效）
        "pr": split_storage(kw.get("p"))[0][:400],  # 相对 Zotero storage 的部分（跨机器有效）
        "c": (kw.get("c") or "").strip()[:120],   # citekey（Better BibTeX）
        "ty": (kw.get("ty") or "").strip()[:40],  # 类型
        "tg": [str(x)[:40] for x in (kw.get("tg") or [])][:12],   # 标签
        "s": kw.get("s") or "",            # 来源：zotero / bib / ris / csl / nbib
        "lib": str(kw.get("lib") or ""),   # Zotero 库 id（空=个人库）
        "at": kw.get("at") or "",          # 加入时间
        # 下面几个只为「导出回 .bib 时不缺字段」而存，界面上不显示
        "vol": (str(kw.get("vol") or "").strip())[:20],
        "iss": (str(kw.get("iss") or "").strip())[:20],
        "pg": (str(kw.get("pg") or "").strip())[:40],
        "pub": _clean(kw.get("pub"))[:120],
    }
    it = {k: v for k, v in it.items() if v not in ("", [], None) or k in ("y", "at")}
    for k in ("k", "t", "a", "y", "j", "d", "u", "p", "c", "ty", "tg", "s", "lib", "at"):
        it.setdefault(k, [] if k in ("a", "tg") else ("" if k != "y" else None))
    return it


# Zotero 的存储目录每台机器都不一样：
#   Mac   /Users/me/Zotero/storage/ABCD1234/He_2013.pdf
#   Win   C:\\Users\\me\\Zotero\\storage\\ABCD1234\\He_2013.pdf
# 存绝对路径的话，同步到另一台机器 100% 打不开。
# 所以识别出「…/storage/」这一段，只存它后面的相对部分，
# 打开时再拼上本机配置的 Zotero 根目录。
_STORAGE_RE = re.compile(r"[/\\](?:storage|Zotero[/\\]storage)[/\\]", re.I)


def split_storage(path):
    """绝对路径 → (相对 storage 的部分 or ''，原路径)。"""
    s = str(path or "").replace("\\", "/")
    m = _STORAGE_RE.search(s)
    if not m:
        return "", s
    return s[m.end():], s


def resolve_pdf(it, zotero_root=""):
    """把索引里的 PDF 位置还原成本机能用的绝对路径。

    优先用相对路径 + 本机 Zotero 根目录；没配根目录才退回原始绝对路径
    （同一台机器上仍然是对的）。
    """
    rel = it.get("pr")
    if rel and zotero_root:
        root = str(zotero_root).rstrip("/\\")
        if not root.lower().endswith("storage"):
            root = root + "/storage"
        return f"{root}/{rel}"
    return it.get("p") or ""


def dedupe_key(it):
    """去重键：优先 DOI，其次「归一化标题 + 年份」。"""
    if it.get("d"):
        return "doi:" + it["d"]
    t = _norm_title(it.get("t"))
    # 标题本身就不可靠的（从 PDF 里没抠出真题目，只好拿正文头几个字或文件名顶上），
    # 绝不能拿它当去重键：两份毫不相干的 PDF 很容易得到同一个「标题」，
    # 一去重就少掉一篇 —— 而少掉的那篇你根本不会发现。
    # 这种情况下用文件路径当键：宁可多一条待补全，也不能凭空吞掉一篇。
    if it.get("todo_title") and it.get("p"):
        return "path:" + str(it["p"]).lower()
    if not t:
        return ""
    return f"ti:{t}|{it.get('y') or ''}"


# ============================================================ 解析器

def parse_bibtex(text):
    """BibTeX。手写而不是正则一把梭——花括号会嵌套，正则处理不了。"""
    out, n = [], len(text)
    i = 0
    while i < n:
        at = text.find("@", i)
        if at < 0:
            break
        m = re.match(r"@(\w+)\s*[{(]\s*([^,\s]*)\s*,", text[at:at + 400])
        if not m:
            i = at + 1
            continue
        ty = m.group(1).lower()
        citekey = m.group(2).strip()
        if ty in ("comment", "preamble", "string"):
            i = at + 1
            continue
        # 从 { 开始扫到配对的 }
        start = at + m.end() - 1
        depth, j, in_q = 0, at + len(m.group(0)) - 1, False
        # 定位条目起始的那个 { 或 (
        ob = text.find("{", at)
        op = text.find("(", at)
        if ob < 0 or (0 <= op < ob):
            ob = op
        j, depth = ob, 0
        while j < n:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = text[ob + 1:j]
        i = j + 1
        # 拆字段
        fields, k, buf, depth, in_str = {}, None, [], 0, False
        key_buf, mode = [], "key"
        p = body.find(",")
        body = body[p + 1:] if p >= 0 else ""
        for ch in body:
            if mode == "key":
                if ch == "=":
                    k = "".join(key_buf).strip().lower()
                    key_buf, buf, mode = [], [], "val"
                else:
                    key_buf.append(ch)
            else:
                if ch == "{":
                    depth += 1
                    buf.append(ch)
                elif ch == "}":
                    depth -= 1
                    buf.append(ch)
                elif ch == '"' and depth == 0:
                    in_str = not in_str
                elif ch == "," and depth == 0 and not in_str:
                    if k:
                        fields[k] = "".join(buf).strip()
                    k, buf, mode = None, [], "key"
                else:
                    buf.append(ch)
        if k and buf:
            fields[k] = "".join(buf).strip()

        title = fields.get("title") or fields.get("booktitle") or ""
        if not title:
            continue
        out.append(_mk_item(
            k=citekey, c=citekey, ty=ty, s="bib",
            t=title,
            a=_authors_from_bibtex(fields.get("author") or fields.get("editor")),
            y=_year(fields.get("year") or fields.get("date")),
            j=(fields.get("journal") or fields.get("journaltitle")
               or fields.get("booktitle") or fields.get("publisher") or ""),
            d=fields.get("doi"),
            u=_clean(fields.get("url") or ""),
            p=_first_pdf(fields.get("file") or ""),
            vol=_clean(fields.get("volume")), iss=_clean(fields.get("number")),
            pg=_clean(fields.get("pages")), pub=_clean(fields.get("publisher")),
        ))
    return out


def _first_pdf(s):
    """JabRef/Zotero 的 file 字段：'描述:/路径/x.pdf:PDF;...'，挑第一个 pdf 路径。"""
    s = str(s or "")
    if not s:
        return ""
    for chunk in s.split(";"):
        parts = chunk.split(":")
        for pt in parts:
            if pt.lower().endswith(".pdf"):
                return pt.replace("\\:", ":").strip()
    return ""


_RIS_TY = {"JOUR": "journalArticle", "CONF": "conferencePaper", "CPAPER": "conferencePaper",
           "BOOK": "book", "CHAP": "bookSection", "THES": "thesis", "RPRT": "report",
           "UNPB": "manuscript", "ELEC": "webpage"}


def parse_ris(text):
    """RIS：EndNote / Web of Science / Scopus / 知网导出的主力格式。"""
    out, cur = [], None
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = re.match(r"^([A-Z][A-Z0-9])  ?- ?(.*)$", raw)
        if not m:
            if cur is not None and raw.strip() and cur.get("_last"):
                cur[cur["_last"]] = (cur.get(cur["_last"], "") + " " + raw.strip()).strip()
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur = {"ty": _RIS_TY.get(val.upper(), val.lower()), "a": [], "tg": []}
            cur["_last"] = None
            continue
        if cur is None:
            continue
        if tag == "ER":
            if cur.get("t"):
                cur.pop("_last", None)
                out.append(_mk_item(s="ris", **cur))
            cur = None
            continue
        if tag in ("TI", "T1", "CT"):
            cur["t"] = val
            cur["_last"] = "t"
        elif tag in ("AU", "A1", "A2"):
            if len(cur["a"]) < 40:
                cur["a"].append(val)
            cur["_last"] = None
        elif tag in ("PY", "Y1", "DA"):
            cur["y"] = _year(val)
            cur["_last"] = None
        elif tag in ("JO", "JF", "T2", "JA", "J2"):
            if not cur.get("j"):
                cur["j"] = val
            cur["_last"] = "j"
        elif tag == "DO":
            cur["d"] = val
            cur["_last"] = None
        elif tag == "VL":
            cur["vol"] = val
            cur["_last"] = None
        elif tag == "IS":
            cur["iss"] = val
            cur["_last"] = None
        elif tag in ("SP", "EP"):
            cur["pg"] = (cur.get("pg", "") + ("-" if tag == "EP" and cur.get("pg") else "") + val)
            cur["_last"] = None
        elif tag == "PB":
            cur["pub"] = val
            cur["_last"] = None
        elif tag in ("UR", "L1", "L2"):
            if val.lower().endswith(".pdf") and not cur.get("p"):
                cur["p"] = val
            elif not cur.get("u"):
                cur["u"] = val
            cur["_last"] = None
        elif tag == "KW":
            if len(cur["tg"]) < 12:
                cur["tg"].append(val)
            cur["_last"] = None
        else:
            cur["_last"] = None
    return out


def parse_csl_json(text):
    """CSL-JSON：Zotero / Better BibTeX 的原生导出，字段最干净。"""
    try:
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("items") or [data]
    out = []
    for it in data if isinstance(data, list) else []:
        if not isinstance(it, dict):
            continue
        title = it.get("title") or ""
        if not title:
            continue
        auths = []
        for a in (it.get("author") or [])[:40]:
            if isinstance(a, dict):
                nm = a.get("literal") or ", ".join(
                    x for x in [a.get("family"), a.get("given")] if x)
                if nm:
                    auths.append(nm)
        y = None
        iss = it.get("issued") or {}
        dp = (iss.get("date-parts") or [[None]])[0]
        if dp and dp[0]:
            y = _year(dp[0])
        if y is None:
            y = _year(iss.get("raw") or "")
        out.append(_mk_item(
            k=str(it.get("id") or ""), c=str(it.get("citation-key") or it.get("id") or ""),
            ty=str(it.get("type") or ""), s="csl",
            t=title, a=auths, y=y,
            j=it.get("container-title") or it.get("publisher") or "",
            d=it.get("DOI"), u=it.get("URL") or "",
            vol=it.get("volume"), iss=it.get("issue"), pg=it.get("page"),
            pub=it.get("publisher"),
            tg=[str(x) for x in (it.get("keyword") or "").split(",") if x.strip()][:12],
        ))
    return out


def parse_nbib(text):
    """PubMed 的 MEDLINE/nbib 格式，医学与生科的人常用。"""
    out, cur = [], None
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    for blk in blocks:
        if not blk.strip():
            continue
        cur = {"a": [], "tg": [], "ty": "journalArticle"}
        last = None
        for raw in blk.split("\n"):
            m = re.match(r"^([A-Z]{2,4})\s*-\s*(.*)$", raw)
            if not m:
                if last and raw.strip():
                    cur[last] = (cur.get(last, "") + " " + raw.strip()).strip()
                continue
            tag, val = m.group(1), m.group(2).strip()
            if tag == "TI":
                cur["t"] = val
                last = "t"
            elif tag == "AU":
                if len(cur["a"]) < 40:
                    cur["a"].append(val)
                last = None
            elif tag in ("DP", "DEP"):
                cur.setdefault("y", _year(val))
                last = None
            elif tag in ("JT", "TA"):
                cur.setdefault("j", val)
                last = "j"
            elif tag in ("LID", "AID"):
                if "[doi]" in val.lower():
                    cur.setdefault("d", val.split()[0])
                last = None
            elif tag == "PMID":
                cur.setdefault("k", "pmid" + val)
                cur.setdefault("u", f"https://pubmed.ncbi.nlm.nih.gov/{val}/")
                last = None
            elif tag == "MH":
                if len(cur["tg"]) < 12:
                    cur["tg"].append(val)
                last = None
            else:
                last = None
        if cur.get("t"):
            out.append(_mk_item(s="nbib", **cur))
    return out


def parse_zotero_items(items, lib=""):
    """Zotero 本地 API 返回的 JSON 数组。"""
    out = []
    for raw in items or []:
        d = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(d, dict):
            continue
        ty = d.get("itemType") or ""
        if ty in ("attachment", "note", "annotation"):
            continue
        title = d.get("title") or ""
        if not title:
            continue
        auths = []
        for c in (d.get("creators") or [])[:40]:
            nm = c.get("name") or ", ".join(
                x for x in [c.get("lastName"), c.get("firstName")] if x)
            if nm:
                auths.append(nm)
        # Better BibTeX 把 citekey 写在 extra 里：「Citation Key: xxx」
        ck = ""
        m = re.search(r"citation key\s*:\s*(\S+)", d.get("extra") or "", re.I)
        if m:
            ck = m.group(1)
        out.append(_mk_item(
            k=d.get("key") or "", c=ck, ty=ty, s="zotero", lib=lib,
            t=title, a=auths, y=_year(d.get("date")),
            j=d.get("publicationTitle") or d.get("bookTitle")
              or d.get("proceedingsTitle") or d.get("publisher") or "",
            d=d.get("DOI"), u=d.get("url") or "",
            tg=[t.get("tag", "") for t in (d.get("tags") or [])][:12],
        ))
    return out


PARSERS = {"bib": parse_bibtex, "ris": parse_ris, "csl": parse_csl_json, "nbib": parse_nbib}


def sniff(text, filename=""):
    """猜格式。用户不该被要求先搞清自己导出的是什么。"""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in (".bib", ".bibtex"):
        return "bib"
    if ext == ".ris":
        return "ris"
    if ext == ".nbib":
        return "nbib"
    if ext == ".json":
        return "csl"
    head = (text or "")[:4000].lstrip()
    if head.startswith("[") or head.startswith("{"):
        return "csl"
    if re.search(r"^\s*@\w+\s*[{(]", head, re.M):
        return "bib"
    if re.search(r"^TY\s{0,2}- ", head, re.M):
        return "ris"
    if re.search(r"^PMID\s*- ", head, re.M):
        return "nbib"
    return ""


# ============================================================ 索引存取

class Index:
    """jsonl 索引 + 内存缓存 + 搜索。

    缓存按 (mtime, size) 失效。搜索时用预先算好的小写检索串，
    避免每次搜索都重新拼字符串——几万条时这是数量级差别。
    """

    def __init__(self, path):
        self.path = Path(path)
        # 三样东西打包成一个元组一次性替换。分开赋值的话，
        # 读线程可能拿到「新的 items + 旧的 hay」，搜索结果就会串行。
        # 一次元组赋值在 CPython 里是原子的，读端因此完全不用加锁。
        self._snap = ([], [], None)
        # 索引是**一个共享文件**（记录是一记录一文件，不需要这个）。
        # 并发导入时「读全量 → 合并 → 全量写回」必须整体互斥，
        # 否则两个导入同时进来，后写的会把先写的整批悄悄吃掉。
        self._lock = threading.RLock()


    # ---------- 读

    def _stat(self):
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return None

    def load(self):
        return self._snapshot()[0]

    def _snapshot(self):
        """返回 (items, hay)。文件没变时**不加锁**直接返回当前快照 ——
        否则一次 5 万条的导入正在重写文件时，所有搜索都会卡在锁上等它。
        压测实测：加锁读会让 p99 从 70ms 飙到 35 秒。"""
        items, hay, stamp = self._snap
        if self._stat() == stamp:
            return items, hay
        with self._lock:
            self._load_locked()
            return self._snap[0], self._snap[1]

    def _load_locked(self):
        stamp = self._stat()
        if stamp == self._snap[2]:
            return self._snap[0]
        items = []
        if stamp is not None:
            with self.path.open("r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        items.append(json.loads(ln))
                    except Exception:
                        continue          # 坏行跳过，绝不让整个库打不开
        self._snap = (items, [self._haystack(it) for it in items], stamp)
        return items

    @staticmethod
    def _haystack(it):
        return (" ".join([
            str(it.get("t") or ""), " ".join(it.get("a") or []),
            str(it.get("j") or ""), str(it.get("y") or ""),
            str(it.get("c") or ""), str(it.get("d") or ""),
            " ".join(it.get("tg") or []),
        ])).lower()

    # ---------- 写

    def _write_all(self, items):
        """原子写回。临时文件名必须带进程号和线程号 ——
        固定叫 library.tmp 的话，两个并发导入会用同一个临时文件，
        先完成的那个 replace 掉之后，后一个直接 FileNotFoundError。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 同 server.atomic_write_text：线程 id 会被回收复用，不能拿来当唯一后缀
        tmp = self.path.with_name(f"{self.path.name}.tmp{os.getpid()}-{next(_TMP_SEQ)}")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as fh:
                for it in items:
                    fh.write(json.dumps(it, ensure_ascii=False, separators=(",", ":")) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
        self._snap = (items, [self._haystack(it) for it in items], self._stat())

    def add_many(self, new_items, source=""):
        """批量并入，按 DOI / 标题+年份 去重。返回统计。

        整段在锁里：读—合并—写必须是一个不可分割的动作。
        """
        with self._lock:
            return self._add_many_locked(new_items, source)

    def _add_many_locked(self, new_items, source=""):
        cur = list(self.load())
        seen, by_title = {}, {}

        def title_key(x):
            """标题+年份的辅助键。标题不可靠的一律不参与，免得误并。"""
            if x.get("todo_title"):
                return ""
            t = _norm_title(x.get("t"))
            return f"ti:{t}|{x.get('y') or ''}" if t else ""

        def index(idx, x):
            k = dedupe_key(x)
            if k:
                seen[k] = idx
            tk = title_key(x)
            if tk:
                by_title.setdefault(tk, idx)

        for idx, it in enumerate(cur):
            index(idx, it)
        added = updated = skipped = 0
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        for it in new_items:
            if source:
                it["s"] = source
            k = dedupe_key(it)
            if not k:
                skipped += 1
                continue
            # 同一篇论文，.bib 里带 DOI、PDF 里没有 —— 主键一个是 doi:… 一个是 ti:…，
            # 光比主键会当成两篇，于是索引里一篇论文占两行，
            # 而那份能双击打开的本地 PDF 又没挂到带 DOI 的那条上。
            # 所以主键之外再比一次「标题+年份」。
            hit = seen.get(k)
            if hit is None:
                tk = title_key(it)
                if tk:
                    hit = by_title.get(tk)
            if hit is not None:
                old = cur[hit]
                # 同一篇论文常常同时躺在 Zotero、ref.bib 和 PDF 文件夹里。
                # 谁说了算按来源可靠度定：Zotero 是你亲手整理过的，最准；
                # 题录文件次之；从 PDF 里抠出来的元数据最不可靠（常常只有个文件名）。
                # 来源更可靠 → 覆盖；否则只补空字段，绝不动你可能手工修过的内容。
                better = SOURCE_RANK.get(it.get("s") or "", 1) > \
                    SOURCE_RANK.get(old.get("s") or "", 1)
                for f in ("k", "c", "d", "u", "j", "ty", "lib", "vol", "iss", "pg", "pub"):
                    if it.get(f) and (better or not old.get(f)):
                        old[f] = it[f]
                if it.get("t") and better:
                    old["t"] = it["t"]
                if it.get("a") and (better or not old.get("a")):
                    old["a"] = it["a"]
                if it.get("y") and (better or not old.get("y")):
                    old["y"] = it["y"]
                # PDF 路径谁有算谁的：Zotero 那条通常没有本地路径，
                # 而你文件夹里那份 PDF 恰恰是能双击打开的那个
                for f in ("p", "pr"):
                    if it.get(f) and not old.get(f):
                        old[f] = it[f]
                # 记下这一篇还在哪些地方出现过，界面上能看出它是不是三处都有。
                # 必须在改 old["s"] **之前**取，否则原来那个来源就被覆盖没了 ——
                # 一篇同时来自 PDF 和 .bib 的论文会显示成「只来自 .bib」。
                srcs = set(old.get("srcs") or ([old.get("s")] if old.get("s") else []))
                if it.get("s"):
                    srcs.add(it["s"])
                srcs = {x for x in srcs if x}
                if len(srcs) > 1:
                    old["srcs"] = sorted(srcs)
                if better:
                    old["s"] = it["s"]
                    # 有更可靠的来源补进来了，就不再是「待补全」
                    old.pop("todo", None)
                    old.pop("todo_title", None)
                    old.pop("todo_from", None)
                index(hit, old)          # 合并后主键可能变了（补上了 DOI），重新登记
                updated += 1
            else:
                it["at"] = stamp
                cur.append(it)
                index(len(cur) - 1, it)
                added += 1
            if len(cur) >= MAX_ITEMS:
                break
        self._write_all(cur)
        return {"added": added, "updated": updated, "skipped": skipped, "total": len(cur)}

    def remove(self, keys):
        with self._lock:
            keys = set(keys or [])
            before = len(self.load())
            cur = [it for it in self._snap[0] if (it.get("k") or "") not in keys]
            n = before - len(cur)
            self._write_all(cur)
            return {"removed": n, "total": len(cur)}

    def mirror(self, new_items, source, force=False):
        """镜像同步：以来源为准做全量对齐。

        普通导入只加不减，所以你在 Zotero 里删掉的条目会在索引里变成僵尸。
        镜像模式会把「这个来源下、但这次没出现」的条目一并删掉。
        只影响该来源，手工导入的 .bib 和别的来源不受牵连。

        **两道安全闸**（镜像是唯一会大批删数据的操作，必须防呆）：
          · 传进来是空的 —— 一律拒绝。Zotero 那边一次抽风、
            或者拉到一半断网，都可能返回空；照做就是把整个库清空。
          · 要删掉一多半 —— 也拒绝，除非明确 force。
            正常增删不会一次少掉一半，这种情况八成是拉错库了。
        """
        with self._lock:
            cur = self.load()
            keep_other = [it for it in cur if it.get("s") != source]
            before_same = [it for it in cur if it.get("s") == source]
            n_new = len({dedupe_key(it) for it in new_items if dedupe_key(it)})
            if before_same and not n_new:
                return {"ok": False, "refused": "empty",
                        "detail": f"对方一条都没返回，但本地有 {len(before_same)} 条。"
                                  "这更像是拉取出了问题，而不是你真把库清空了 —— 没有动任何数据。",
                        "total": len(cur)}
            if before_same and not force and n_new < len(before_same) * 0.5 \
                    and len(before_same) - n_new >= 20:
                return {"ok": False, "refused": "shrink",
                        "would_remove": len(before_same) - n_new,
                        "detail": f"这次只拉到 {n_new} 条，本地有 {len(before_same)} 条，"
                                  f"照做会删掉 {len(before_same) - n_new} 条。"
                                  "一次少掉一多半通常是拉错了库或者没拉完 —— 先没有动数据。",
                        "total": len(cur)}
            # 已有的同来源条目按去重键索引，用来保留用户可能补过的字段
            old_by_key = {}
            for it in before_same:
                k = dedupe_key(it)
                if k:
                    old_by_key[k] = it
            merged, seen = [], set()
            for it in new_items:
                it["s"] = source
                k = dedupe_key(it)
                if not k or k in seen:
                    continue
                seen.add(k)
                old = old_by_key.get(k)
                if old:
                    for f in ("at",):
                        if old.get(f):
                            it[f] = old[f]
                merged.append(it)
            removed = len(before_same) - len(merged)
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            for it in merged:
                it.setdefault("at", stamp)
            self._write_all(keep_other + merged)
            return {"ok": True,
                    "added": max(0, len(merged) - len(before_same) + max(0, removed)),
                    "removed": max(0, removed), "kept": len(merged),
                    "total": len(keep_other) + len(merged)}

    def merge_pair(self, key_keep, key_drop):
        """把两条合并成一条：工作论文和它正式发表的版本。

        无 DOI 时按「标题 + 年份」去重，所以同一篇 WP 2023 → 发表 2025
        必然是两条。学术圈太常见了，得给个手动合并。
        保留 key_keep 那条，把 key_drop 上有、它没有的字段补过来。
        """
        with self._lock:
            cur = self.load()
            keep = drop = None
            for it in cur:
                if it.get("k") == key_keep:
                    keep = it
                elif it.get("k") == key_drop:
                    drop = it
            if key_keep and key_keep == key_drop:
                return {"ok": False, "detail": "选的是同一条，没什么可合并的。"}
            if keep is None or drop is None:
                return {"ok": False, "detail": "这两条里有一条已经不在索引里了"}
            for f in ("d", "u", "p", "pr", "c", "j", "vol", "iss", "pg", "pub", "ty"):
                if not keep.get(f) and drop.get(f):
                    keep[f] = drop[f]
            if not keep.get("y") and drop.get("y"):
                keep["y"] = drop["y"]
            tg = list(dict.fromkeys((keep.get("tg") or []) + (drop.get("tg") or [])))[:12]
            if tg:
                keep["tg"] = tg
            # 留个痕，免得以后自己也搞不清为什么少了一条
            keep["merged_from"] = (keep.get("merged_from") or []) + [key_drop]
            self._write_all([it for it in cur if it.get("k") != key_drop])
            return {"ok": True, "kept": key_keep, "dropped": key_drop,
                    "total": len(cur) - 1}

    def clear(self, source="", confirm=False):
        """清空（或按来源清空）文献索引。

        不传 source 就是**整库清空** —— 这是全工作台删得最多的一次操作，
        五万条题录一去不复返，而 mirror 那边为了「对方返回空」都设了两道闸。
        所以这里也要求调用方明确说「我知道我在清空整库」，
        否则只回报会删多少条，不动任何数据。
        """
        with self._lock:
            cur = self.load()
            keep = [it for it in cur if source and it.get("s") != source]
            n = len(cur) - len(keep)
            if not source and not confirm:
                return {"ok": False, "refused": "confirm",
                        "would_remove": n, "total": len(cur),
                        "detail": f"这会清空整个文献索引（{n} 条）。确认要清就再来一次并带上 confirm。"}
            self._write_all(keep)
            return {"ok": True, "removed": n, "total": len(keep)}

    # ---------- 查

    def search(self, q="", limit=50, offset=0, sort="year", year_from=None,
               year_to=None, source="", has_pdf=None, todo=None):
        items, hay = self._snapshot()
        q = (q or "").strip().lower()
        terms = [t for t in re.split(r"\s+", q) if t] if q else []
        hits = []
        for i, it in enumerate(items):
            if terms:
                h = hay[i]
                if not all(t in h for t in terms):
                    continue
            # 年份筛选同样不能假设类型（老库里可能存着字符串）
            if year_from and _year_num(it.get("y")) < year_from:
                continue
            if year_to and (_year_num(it.get("y")) or 9999) > year_to:
                continue
            if source and it.get("s") != source:
                continue
            if has_pdf is True and not it.get("p"):
                continue
            # 从 PDF 抠出来的条目元数据往往不全。既然照收，就得让你**一次筛出来**
            # 集中补 —— 否则「照收」跟「悄悄堆了一堆垃圾」没区别。
            if todo is True and not it.get("todo"):
                continue
            if todo is False and it.get("todo"):
                continue
            hits.append(it)
        total = len(hits)
        if sort == "title":
            hits.sort(key=lambda x: _norm_title(x.get("t")))
        elif sort == "added":
            hits.sort(key=lambda x: x.get("at") or "", reverse=True)
        else:
            # 再兜一层：万一有历史数据是字符串年份，也不能让整个搜索崩掉
            hits.sort(key=lambda x: _year_num(x.get("y")), reverse=True)
        limit = max(1, min(int(limit or 50), SEARCH_CAP))
        offset = max(0, int(offset or 0))
        return {"total": total, "items": hits[offset:offset + limit],
                "limit": limit, "offset": offset}

    def stats(self):
        items = self.load()
        by_src, years, pdfs = {}, [], 0
        for it in items:
            by_src[it.get("s") or "?"] = by_src.get(it.get("s") or "?", 0) + 1
            if it.get("y"):
                years.append(it["y"])
            if it.get("p"):
                pdfs += 1
        return {"total": len(items), "by_source": by_src, "with_pdf": pdfs,
                "year_min": min(years) if years else None,
                "year_max": max(years) if years else None}

    def get(self, key):
        for it in self.load():
            if (it.get("k") or "") == key:
                return it
        return None


# ============================================================ 跳转链接

def open_targets(it, manager="zotero", zotero_root=""):
    """一条索引能跳去哪。顺序即优先级，界面按这个顺序摆图标。

    manager 由用户在向导里选：zotero / mendeley / endnote / papers / none。
    不用 Zotero 的人不会看到一个必然打不开的 zotero:// 链接。
    """
    out = []
    if manager == "zotero" and it.get("k") and it.get("s") == "zotero":
        lib = str(it.get("lib") or "")
        uri = (f"zotero://select/groups/{lib}/items/{it['k']}" if lib and lib != "0"
               else f"zotero://select/library/items/{it['k']}")
        out.append({"kind": "zotero", "label": "在 Zotero 中打开", "url": uri, "icon": "📗"})
    elif manager == "zotero" and it.get("c"):
        # Better BibTeX 的 citekey 形式，没有 itemKey 时的退路
        out.append({"kind": "zotero", "label": "在 Zotero 中打开（citekey）",
                    "url": f"zotero://select/items/@{it['c']}", "icon": "📗"})
    p = resolve_pdf(it, zotero_root)
    if p:
        if p.startswith(("http://", "https://")):
            url = p
        else:
            # 关键：**不能**给 file:// —— 浏览器禁止 http 页面跳 file://，
            # 点了完全没反应也不报错。改成走服务端接口把文件读出来回传。
            import urllib.parse as _u
            url = "/api/library/file?path=" + _u.quote(p[7:] if p.startswith("file://") else p)
        out.append({"kind": "pdf", "label": "打开本地 PDF", "url": url, "icon": "📄"})
    if it.get("d"):
        out.append({"kind": "doi", "label": "DOI 页面",
                    "url": "https://doi.org/" + it["d"], "icon": "🔗"})
    if it.get("u"):
        out.append({"kind": "url", "label": "原始链接", "url": it["u"], "icon": "🌐"})
    if not out and it.get("t"):
        import urllib.parse as _up
        out.append({"kind": "search", "label": "Google Scholar 搜一下",
                    "url": "https://scholar.google.com/scholar?q=" + _up.quote(it["t"][:200]),
                    "icon": "🔎"})
    return out


def to_bibtex(items):
    """导出回 .bib —— 进得来也要出得去，不能把人锁住。

    字段要给全：只写 title/author/year/journal 的话，拿去投稿会缺卷期页码，
    等于导出的东西不能直接用。
    """
    TY = {"journalArticle": "article", "article-journal": "article",
          "conferencePaper": "inproceedings", "paper-conference": "inproceedings",
          "inproceedings": "inproceedings", "book": "book",
          "bookSection": "incollection", "chapter": "incollection",
          "thesis": "phdthesis", "report": "techreport", "manuscript": "unpublished",
          "preprint": "misc", "webpage": "misc"}
    out = []
    for it in items:
        key = (it.get("c") or it.get("k")
               or re.sub(r"\W+", "", _norm_title(it.get("t")))[:24] or "item")
        ty = TY.get(it.get("ty"), "article")
        rows = []
        def add(name, val):
            if val not in (None, "", []):
                rows.append(f"  {name} = {{{val}}}")
        add("title", it.get("t"))
        if it.get("a"):
            add("author", " and ".join(it["a"]))
        add("year", it.get("y"))
        # 会议论文的出处字段名不一样，写错了 BibTeX 排不出来
        if ty in ("inproceedings", "incollection"):
            add("booktitle", it.get("j"))
        elif ty in ("phdthesis", "techreport"):
            add("institution", it.get("j"))
        else:
            add("journal", it.get("j"))
        add("volume", it.get("vol"))
        add("number", it.get("iss"))
        add("pages", it.get("pg"))
        add("publisher", it.get("pub"))
        add("doi", it.get("d"))
        add("url", it.get("u"))
        if it.get("tg"):
            add("keywords", ", ".join(it["tg"]))
        add("abstract", it.get("ab"))
        if it.get("p"):
            add("file", it["p"])
        out.append(f"@{ty}{{{key},\n" + ",\n".join(rows) + "\n}\n")
    return "\n".join(out)


# ================================================== 从文件夹一键收进来
#
# 研究者的论文十有八九就散在几个文件夹里：Overleaf 项目旁边一个 ref.bib，
# 下载的 PDF 堆在「文献」里，Zotero 导出的 .ris 躺在下载目录。
# 以前这些都得一个个挑文件手动导，PDF 那一堆更是完全进不了索引。
# 这里的做法是：指一个文件夹，题录文件和 PDF 一起收。

BIB_EXT = {".bib": "bib", ".ris": "ris", ".nbib": "nbib", ".json": "csl"}
SCAN_MAX_PDF = 800          # 一次最多认这么多 PDF，再多就该分文件夹了
SCAN_MAX_BIB = 200          # 题录文件本来也不该有几百个
SCAN_MAX_BIB_BYTES = 40 * 1024 * 1024


def _title_unreliable(t, path, source):
    """这个「标题」到底是不是真的题目。

    pdfmeta 抠不到元数据时会退而求其次：先拿首页排版猜，再不行就用文件名。
    这两种都可能得到一个跟论文题目毫无关系的字符串
    （常见的是版权声明、期刊页眉，甚至正文头一句）。
    认出来很重要 —— 不然它会被当成去重用的标题，把别的论文误并掉。
    """
    t = (t or "").strip()
    if not t or len(t) < 8:
        return True
    if source in ("文件名", "首页排版"):
        return True
    stem = re.sub(r"[_\-]+", " ", Path(path).stem).strip()
    return _norm_title(t) == _norm_title(stem)


def pdf_to_item(meta):
    """pdfmeta.extract() 的结果 → 一条索引记录，并判断要不要标「待补全」。"""
    if not meta.get("ok"):
        return None
    title = meta.get("title") or ""
    authors = [a.strip() for a in re.split(r"[;,]| and ", meta.get("authors") or "")
               if a.strip()][:12]
    it = _mk_item(t=title, a=authors, y=meta.get("year"),
                  p=meta.get("path"), s="pdf", ty="article")
    # 「待补全」不是失败，是**如实说这条元数据不全**。
    # 全塞进索引、再让你一次性筛出来补，比悄悄丢掉一批要好得多 ——
    # 丢掉的那些你永远不会知道自己少了什么。
    missing = []
    if not it.get("y"):
        missing.append("年份")
    if not it.get("a"):
        missing.append("作者")
    if not it.get("d"):
        missing.append("DOI")
    if _title_unreliable(title, meta.get("path") or "", meta.get("source") or ""):
        missing.append(f"题目（现在这个是从{meta.get('source') or '文件'}猜的）")
        # 这条标记很关键：dedupe_key 看到它就改用文件路径做键，
        # 免得两份不相干的 PDF 因为「标题」碰巧一样而被并成一条。
        it["todo_title"] = 1
    if missing:
        it["todo"] = "、".join(missing)
        it["todo_from"] = meta.get("source") or ""
    return it


def scan_folder_items(folder, pdfmeta=None, max_pdf=SCAN_MAX_PDF,
                      max_bib=SCAN_MAX_BIB):
    """把一个文件夹里的题录文件和 PDF 都读成索引记录。

    返回 {"items": [...], "files": [...], "errors": [...], ...}，
    **只解析、不落盘** —— 是否真的导入由调用方决定，
    这样界面可以先把「会加多少条」摆给你看。
    """
    base = Path(str(folder or "")).expanduser()
    if not base.is_dir():
        return {"ok": False, "detail": f"这不是一个文件夹：{base}"}
    items, files, errors = [], [], []
    counts = {"bib": 0, "pdf": 0}

    # --- 题录文件（.bib/.ris/.nbib/.json）
    seen_bib = 0
    for p in sorted(base.rglob("*")):
        if seen_bib >= max_bib:
            break
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        fmt = BIB_EXT.get(p.suffix.lower())
        if not fmt:
            continue
        seen_bib += 1
        try:
            if p.stat().st_size > SCAN_MAX_BIB_BYTES:
                errors.append({"file": str(p), "detail": "文件太大，跳过"})
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            errors.append({"file": str(p), "detail": f"读不了：{e}"})
            continue
        # .json 可能是任何东西（配置、数据），别把不相干的 json 当题录硬解析
        real = sniff(text, p.name)
        if real not in PARSERS:
            continue
        try:
            got = PARSERS[real](text)
        except Exception as e:
            errors.append({"file": str(p), "detail": f"解析失败：{e}"})
            continue
        for it in got:
            it["s"] = real
        items.extend(got)
        counts["bib"] += len(got)
        files.append({"file": str(p), "kind": real, "n": len(got)})

    # --- PDF
    capped = False
    if pdfmeta is not None:
        pdfs, capped = pdfmeta.iter_pdfs(base, max_pdf)
        for p in pdfs:
            try:
                meta = pdfmeta.extract(p)
            except Exception as e:
                errors.append({"file": str(p), "detail": f"读不了：{e}"})
                continue
            it = pdf_to_item(meta)
            if it is None:
                errors.append({"file": str(p), "detail": meta.get("detail") or "不是 PDF"})
                continue
            items.append(it)
            counts["pdf"] += 1

    todo = sum(1 for x in items if x.get("todo"))
    return {"ok": True, "folder": str(base), "items": items, "files": files,
            "errors": errors[:50], "error_count": len(errors),
            "counts": counts, "todo": todo, "capped": capped}
