# -*- coding: utf-8 -*-
"""
从 PDF 里提取标题、作者、年份 —— 只用标准库，不装任何东西。
策略（依次尝试，谁先给出可信结果就用谁）：
  1. XMP 元数据里的 dc:title
  2. Info 字典里的 /Title（排除 "Microsoft Word - xxx" 这类垃圾）
  3. 首页正文里字号最大的那几行（真实论文的标题几乎总是首页最大字）
  4. 文件名（兜底，去掉常见的下载后缀）
"""
import re, zlib
from pathlib import Path

JUNK_TITLE = re.compile(
    r"^(microsoft word|untitled|document\d*|print|layout|paper\d*|manuscript|main|ms|draft|\d+)\b",
    re.I)


def _read(path, limit=6 * 1024 * 1024):
    try:
        with open(path, "rb") as f:
            return f.read(limit)
    except Exception:
        return b""


def _decode_pdf_string(s):
    if s.startswith(b"\xfe\xff"):
        try:
            return s[2:].decode("utf-16-be", "replace")
        except Exception:
            pass
    out = []
    i = 0
    while i < len(s):
        c = s[i:i + 1]
        if c == b"\\" and i + 1 < len(s):
            nxt = s[i + 1:i + 2]
            mapping = {b"n": "\n", b"r": "\r", b"t": "\t", b"(": "(", b")": ")", b"\\": "\\"}
            if nxt in mapping:
                out.append(mapping[nxt]); i += 2; continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(chr(int(m.group(), 8))); i += 1 + len(m.group()); continue
            i += 2; continue
        out.append(c.decode("latin-1", "replace"))
        i += 1
    txt = "".join(out)
    # 常见的 latin-1 误读回修
    try:
        txt.encode("latin-1").decode("utf-8")
        txt = txt.encode("latin-1").decode("utf-8")
    except Exception:
        pass
    return txt


def _clean(t):
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t).strip(" \t\r\n-–—*·.")
    t = re.sub(r"^[\d\.\s]{0,6}", "", t) if len(t) > 12 else t
    return t.strip()


def _from_xmp(raw):
    m = re.search(rb"<dc:title>.*?<rdf:li[^>]*>(.*?)</rdf:li>", raw, re.S)
    if m:
        try:
            return _clean(m.group(1).decode("utf-8", "replace"))
        except Exception:
            return ""
    return ""


def _from_info(raw):
    best = ""
    for m in re.finditer(rb"/Title\s*\((.*?)(?<!\\)\)", raw, re.S):
        t = _clean(_decode_pdf_string(m.group(1)))
        if t and len(t) > len(best):
            best = t
    for m in re.finditer(rb"/Title\s*<([0-9A-Fa-f\s]+)>", raw):
        try:
            hexs = re.sub(rb"\s", b"", m.group(1))
            b = bytes.fromhex(hexs.decode())
            t = _clean(_decode_pdf_string(b))
            if t and len(t) > len(best):
                best = t
        except Exception:
            pass
    if best and JUNK_TITLE.match(best):
        return ""
    return best


def _author_year(raw, text):
    author = ""
    m = re.search(rb"/Author\s*\((.*?)(?<!\\)\)", raw, re.S)
    if m:
        author = _clean(_decode_pdf_string(m.group(1)))
    year = ""
    ym = re.search(r"(19[6-9]\d|20[0-4]\d)", text[:1500] if text else "")
    if ym:
        year = ym.group(1)
    else:
        ym = re.search(rb"/CreationDate\s*\(D:(\d{4})", raw)
        if ym:
            year = ym.group(1).decode()
    return author, year


def _decode_stream(chunk):
    """PDF 内容流可能叠了多层过滤器（ASCII85 / Flate / LZW / 原文），逐个试。"""
    import base64
    c = chunk.strip(b"\r\n")
    tries = []
    # ASCII85（常见于 reportlab、TeX 部分工具），可能以 ~> 结尾
    try:
        body = c.split(b"~>")[0]
        tries.append(base64.a85decode(body, adobe=False))
    except Exception:
        pass
    try:
        tries.append(base64.a85decode(c, adobe=True))
    except Exception:
        pass
    tries.append(c)
    for t in tries:
        try:
            return zlib.decompress(t)
        except Exception:
            pass
    for t in tries:
        if b"Tj" in t or b"TJ" in t:
            return t
    return None


def _first_page_lines(raw, max_lines=40):
    """把最先出现的几个内容流解压，按字号分组抽取文本行。"""
    lines = []
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            continue
        data = _decode_stream(raw[start:end])
        if data is None or (b"Tj" not in data and b"TJ" not in data):
            continue
        size = 0.0
        cur = []
        for tm in re.finditer(rb"/[A-Za-z0-9]+\s+([\d.]+)\s+Tf|\((?:[^()\\]|\\.)*\)\s*Tj|\[(?:[^\[\]\\]|\\.)*\]\s*TJ|(TD|Td|T\*|ET)",
                              data, re.S):
            tok = tm.group(0)
            if tm.group(1):
                try:
                    size = float(tm.group(1))
                except Exception:
                    size = 0.0
            elif tok.endswith(b"Tj"):
                s = re.match(rb"\((.*)\)\s*Tj", tok, re.S)
                if s:
                    cur.append(_decode_pdf_string(s.group(1)))
            elif tok.endswith(b"TJ"):
                parts = re.findall(rb"\((?:[^()\\]|\\.)*\)", tok, re.S)
                cur.append("".join(_decode_pdf_string(p[1:-1]) for p in parts))
            else:
                if cur:
                    txt = _clean("".join(cur))
                    if txt:
                        lines.append((size, txt))
                    cur = []
        if cur:
            txt = _clean("".join(cur))
            if txt:
                lines.append((size, txt))
        if len(lines) >= max_lines:
            break
    return lines


def _from_layout(lines):
    """标题 = 首页字号最大、长度合理、且不是页眉页脚的那一（几）行。"""
    if not lines:
        return "", ""
    head = lines[:40]
    cand = [(sz, t) for sz, t in head
            if 8 <= len(t) <= 220
            and not re.match(r"^(abstract|introduction|keywords|jel|www\.|http|doi|©|copyright|electronic copy)", t, re.I)
            and not re.match(r"^\d+$", t)]
    if not cand:
        return "", ""
    top = max(sz for sz, _ in cand)
    if top <= 0:
        return _clean(cand[0][1]), ""
    same = [t for sz, t in cand if sz >= top - 0.6]
    title = _clean(" ".join(same[:3]))
    text = " ".join(t for _, t in head)
    return title, text


def extract(path):
    p = Path(path)
    raw = _read(p)
    if not raw.startswith(b"%PDF"):
        return {"ok": False, "file": p.name, "detail": "不是 PDF"}
    lines = _first_page_lines(raw)
    layout_title, text = _from_layout(lines)
    title = _from_xmp(raw) or _from_info(raw)
    source = "元数据"
    if not title or len(title) < 8:
        title, source = layout_title, "首页排版"
    if not title:
        title = re.sub(r"[_\-]+", " ", p.stem)
        title = re.sub(r"\s*\(\d+\)$", "", title).strip()
        source = "文件名"
    author, year = _author_year(raw, text)
    return {"ok": True, "file": p.name, "path": str(p), "title": _clean(title)[:260],
            "authors": author[:160], "year": year, "source": source,
            "size_kb": round(p.stat().st_size / 1024) if p.exists() else 0,
            "snippet": _clean(text)[:400]}


def iter_pdfs(folder, limit=300, max_walk=200000):
    """按需吐出 PDF 路径，**不把整块盘先列成一个大列表**。

    原来是 sorted(base.rglob("*.pdf"))[:limit]：sorted 会先把符合条件的
    每一个路径都算出来，才轮到 [:limit] 生效。指到家目录或磁盘根，
    这一句就要走遍整个文件系统 —— 几分钟起步，内存几百 MB，
    而最后只用得上前 300 条。
    """
    base = Path(folder).expanduser()
    got, walked = [], 0
    for p in base.rglob("*.pdf"):
        walked += 1
        if walked > max_walk:
            break
        try:
            if p.is_file():
                got.append(p)
        except OSError:
            continue
        if len(got) >= limit * 4:      # 多取一些再排序，兼顾稳定顺序与耗时
            break
    return sorted(got)[:limit], walked > max_walk


def scan_folder(folder, limit=300):
    out = []
    base = Path(folder).expanduser()
    if not base.exists():
        return {"ok": False, "detail": f"目录不存在：{base}", "items": []}
    pdfs, capped = iter_pdfs(base, limit)
    for p in pdfs:
        try:
            out.append(extract(p))
        except Exception as e:
            out.append({"ok": False, "file": p.name, "path": str(p), "detail": str(e)[:80]})
    r = {"ok": True, "folder": str(base), "count": len(out), "items": out}
    if capped:
        r["capped"] = True
        r["note"] = "这个目录太大，只扫了一部分。建议指到更具体的论文文件夹。"
    return r
