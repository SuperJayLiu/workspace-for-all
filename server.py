#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学术工作台 · 本地服务 / Scholar Workspace local service
------------------------------------------------------
只用 Python 标准库。Mac 与 Windows 通用。
  python3 server.py            启动，默认 http://127.0.0.1:8765
  python3 server.py --port N   换端口
  python3 server.py --no-open  不自动打开浏览器

它负责：提供界面、读写数据文件、定时备份、Git 同步、
额度调度、活动画像、表格导入、附件与图表读取。
"""
import argparse, base64, contextlib, csv, hashlib, hmac, html, io, itertools, json, mimetypes, os, re, shutil, socket
import traceback
import uuid
import subprocess, sys, threading, time, webbrowser, zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, quote as urllib_quote

try:
    import pdfmeta
except Exception:
    pdfmeta = None
try:
    import services as sv
except Exception as _e:  # 缺文件也不至于起不来
    sv = None
    sys.stderr.write(f"[warn] services.py 未加载: {_e}\n")
try:
    import library as lib
except Exception as _e:
    lib = None
    sys.stderr.write(f"[warn] library.py 未加载: {_e}\n")
try:
    import radar
except Exception as _e:
    radar = None
    sys.stderr.write(f"[warn] radar.py 未加载: {_e}\n")
try:
    import search as searchmod
except Exception as _e:
    searchmod = None
    sys.stderr.write(f"[warn] search.py 未加载: {_e}\n")

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
DATA = ROOT / "data"          # 进 git
LOCAL = ROOT / "local"        # 不进 git（生活数据、密钥、备份、设备配置）
CLAUDE = DATA / "_claude"

# 集合（进 git 的学术数据）
COLLECTIONS = ["manuscripts", "journals", "published", "conferences",
               "reading", "ideas", "levels", "retros", "schedule", "reports",
               "progress"]          # progress：每天的写作进展（Overleaf 同步出来的）
# 本机集合（生活数据，永不进 git）
LOCAL_COLLECTIONS = ["diet", "exercise", "dates", "lists", "admin", "finance"]

VERSION = "3.11.0"

LIB_PATH = DATA / "library.jsonl"
_LIB = None


def get_library():
    """文献索引单例。带 mtime 缓存，重复搜索不会反复读盘。"""
    global _LIB
    if lib is None:
        return None
    if _LIB is None:
        _LIB = lib.Index(LIB_PATH)
    return _LIB

# ---------------------------------------------------------------- utilities

def now_local():
    return datetime.now().astimezone()

def iso(dt=None):
    return (dt or now_local()).isoformat(timespec="seconds")

def today_str():
    return now_local().strftime("%Y-%m-%d")

def slugify(text, fallback="item"):
    # 标题不一定是字符串：同步进来的数据、脚本写的、手改坏的 frontmatter
    # 都可能给个 dict 或数字。这里不能想当然地 .strip()。
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    text = text.strip().lower()
    text = re.sub(r"[^\w一-鿿\- ]+", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return (text[:60] or fallback)

def ensure_dirs():
    for c in COLLECTIONS:
        (DATA / c).mkdir(parents=True, exist_ok=True)
    for c in LOCAL_COLLECTIONS:
        (LOCAL / "life" / c).mkdir(parents=True, exist_ok=True)
    CLAUDE.mkdir(parents=True, exist_ok=True)
    (CLAUDE / "audits").mkdir(exist_ok=True)
    (CLAUDE / "outbox").mkdir(exist_ok=True)
    (LOCAL / "backups" / "rolling").mkdir(parents=True, exist_ok=True)
    (ROOT / "attachments").mkdir(exist_ok=True)
    sweep_temp_files()


def sweep_temp_files():
    """上次被强杀（合盖、断电）留下的半截临时文件，启动时清掉。"""
    n = 0
    for base in (DATA, LOCAL, CLAUDE):
        try:
            for t in base.rglob("*.tmp*"):
                if t.is_file() and time.time() - t.stat().st_mtime > 60:
                    t.unlink(missing_ok=True)
                    n += 1
        except Exception:
            pass
    if n:
        sys.stderr.write(f"[info] 清理了 {n} 个上次未写完的临时文件\n")

def allowed_roots():
    """/api/file 与 /api/tree 只允许访问这些目录之下的东西。"""
    dev = get_device()
    roots = [ROOT]
    cands = [dev.get("paper_root"), dev.get("onedrive_backup_dir"), dev.get("attachment_root")]
    cands += [x for x in (dev.get("paper_roots") or []) if isinstance(x, str)]
    # 用户自己挂上来的表格：表格预览/导入要读它，所以得在白名单里，
    # 但也**只有**它 —— 而不是像以前那样随便给个绝对路径就读
    for x in (dev.get("watch_spreadsheets") or []):
        p = x.get("path") if isinstance(x, dict) else x
        if isinstance(p, str):
            cands.append(str(Path(p).expanduser().parent))
    try:
        cands += [x for x in (_load_json(CONFIG_PATH, {}).get("pdf_folders") or [])
                  if isinstance(x, str)]
    except Exception:
        pass
    for v in cands:
        v = (v or "").strip()
        if v and not v.startswith(("http://", "https://")):
            try:
                roots.append(Path(v).expanduser().resolve())
            except Exception:
                pass
    return roots


def is_sane_scan_root(p):
    """这个目录适不适合被记进「允许打开」白名单。

    磁盘根、家目录、以及 ~ 下面那些什么都装的大目录（Documents、Downloads…）
    一旦入了白名单，/api/file 就能读它们下面的任何东西 —— 包括 ~/.ssh。
    而且这件事是悄悄发生的：界面上看不出来，也没有地方能撤回。
    论文目录总归更具体一层，用这个当门槛不会挡住正常用法。
    """
    try:
        p = Path(p).expanduser().resolve()
        home = Path.home().resolve()
    except Exception:
        return False
    if p == p.parent or p == home:          # 磁盘根 / 家目录
        return False
    broad = {"documents", "downloads", "desktop", "library", "onedrive",
             "dropbox", "google drive", "icloud drive", "文档", "下载", "桌面"}
    if p.parent == home and p.name.lower() in broad:
        return False
    return len(p.parts) > 2


# 绝大多数文件系统单个路径段上限是 255 **字节**。
# 注意是字节不是字符：250 个汉字 = 750 字节，照样超。
# 超了之后 exists()/stat()/resolve() 会抛 OSError，
# 而这些调用散落在好几条路由里，逐个 try 迟早漏一处 —— 所以在入口就挡掉。
MAX_PATH_SEG = 255
MAX_PATH_LEN = 1024


def path_too_long(s):
    if len(str(s or "").encode("utf-8", "ignore")) > MAX_PATH_LEN * 4:
        return True
    for seg in re.split(r"[/\\]", str(s or "")):
        if len(seg.encode("utf-8", "ignore")) > MAX_PATH_SEG:
            return True
    return False


def safe_path(raw):
    """把用户给的路径解析成绝对路径，并确认它落在允许的根目录内。"""
    s = str(raw or "")
    # 过长或含控制字符的路径连 resolve 都会抛 OSError（文件名过长），直接挡在门外
    if len(s) > MAX_PATH_LEN or any(ord(c) < 32 for c in s) or path_too_long(s):
        return None
    try:
        p = Path(s).expanduser().resolve()
    except Exception:
        return None
    for r in allowed_roots():
        try:
            if p == r or r in p.parents:
                return p
        except Exception:
            continue
    return None


RESERVED_FIELDS = {"id", "body", "_collection", "created", "updated", "_error"}


def safe_name(raw, default="upload.dat"):
    """只取文件名本身，挡掉路径穿越。"""
    name = str(raw or "").replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[^\w.\-一-鿿 ()]+", "_", name)
    return name[:120] or default


def coll_dir(name):
    if name in COLLECTIONS:
        return DATA / name
    if name in LOCAL_COLLECTIONS:
        return LOCAL / "life" / name
    raise KeyError(name)

def is_local_coll(name):
    return name in LOCAL_COLLECTIONS

# ------------------------------------------------- frontmatter (mini YAML)
# 只支持我们自己写出的子集：标量、列表、字典列表、多行文本块。

def _parse_scalar(s):
    s = s.strip()
    if s == "":
        return ""
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if s[0] in "[{" or (s[0] == '"' and s[-1:] == '"'):
        try:
            return json.loads(s)
        except Exception:
            return s.strip('"')
    # 位数限制：Python 3.11 起 int(超长数字串) 会直接抛 ValueError（4300 位上限）。
    # 一条长 ISBN、一段基因序列、Excel 里一列被当成数字的长编号都能触发，
    # 结果是这条记录**存不进也读不出**（500），而用户只看到「保存失败」。
    # 长到这个地步的东西本来也不是数字，当字符串留着就对了。
    if len(s) <= 4300 and re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except ValueError:
            return s
    if len(s) <= 4300 and re.fullmatch(r"-?\d*\.\d+", s):
        try:
            return float(s)
        except ValueError:
            return s
    return s


def _fm_scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "" or re.search(r'[:#\-\[\]{}",\n]', s) or s.strip() != s:
        return json.dumps(s, ensure_ascii=False)
    # 字符串若长得像数字/布尔/null，必须加引号，否则读回来会变类型
    # （题目「1984」、卷号「007」、ISSN「00221082」都会中招）
    if _parse_scalar(s) != s:
        return json.dumps(s, ensure_ascii=False)
    return s

def _dump_value(key, val, indent=0):
    pad = "  " * indent
    if isinstance(val, list):
        if not val:
            return f"{pad}{key}: []\n"
        out = f"{pad}{key}:\n"
        for item in val:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    if first:
                        out += f"{pad}  - {k}: {_fm_scalar(v) if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False)}\n"
                        first = False
                    else:
                        out += f"{pad}    {k}: {_fm_scalar(v) if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False)}\n"
                if first:
                    out += f"{pad}  - {{}}\n"
            else:
                out += f"{pad}  - {_fm_scalar(item)}\n"
        return out
    if isinstance(val, dict):
        out = f"{pad}{key}:\n"
        for k, v in val.items():
            out += _dump_value(k, v, indent + 1)
        return out
    return f"{pad}{key}: {_fm_scalar(val)}\n"

def parse_frontmatter(text):
    """返回 (meta dict, body str)。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    head = text[3:end].strip("\n")
    body = text[end + 4:]
    if body.startswith("\n"):      # 结束行的换行
        body = body[1:]
    if body.startswith("\n"):      # dump 时固定写入的空行
        body = body[1:]
    meta = {}
    stack = [(-1, meta)]
    cur_list_key, cur_list_owner = None, None
    lines = head.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.strip().startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        owner = stack[-1][1]
        if line.startswith("- "):
            item = line[2:]
            # 「当前正在往哪个列表里塞」必须连**是谁的**一起记。
            # 只记 key 的话，缩进一退、owner 换成了另一个字典，
            # 而那个字典里同名的键装的是 dict，setdefault 就把 dict 还回来，
            # 紧接着 .append 抛 AttributeError —— 这条记录从此读不出也存不进。
            # 手写、别的机器同步过来、AI 写坏的 .md 都会走到这里，所以要挡死。
            target = None
            if cur_list_key is not None and cur_list_owner is owner:
                target = owner.setdefault(cur_list_key, [])
                if not isinstance(target, list):
                    target = None
            if target is None:
                i += 1
                continue
            if ":" in item and not item.startswith('"'):
                k, v = item.split(":", 1)
                d = {k.strip(): _parse_scalar(v)}
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    ni = len(nxt) - len(nxt.lstrip(" "))
                    if not nxt.strip() or ni <= indent or nxt.strip().startswith("- "):
                        break
                    if ":" in nxt:
                        k2, v2 = nxt.strip().split(":", 1)
                        d[k2.strip()] = _parse_scalar(v2)
                    j += 1
                target.append(d)
                i = j
                continue
            target.append(_parse_scalar(item))
            i += 1
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v == "":
                # 可能是嵌套字典或列表的开头
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                ni = len(nxt) - len(nxt.lstrip(" ")) if nxt.strip() else 0
                if nxt.strip().startswith("- "):
                    owner[k] = []
                    cur_list_key, cur_list_owner = k, owner
                elif nxt.strip() and ni > indent:
                    owner[k] = {}
                    stack.append((indent, owner[k]))
                    cur_list_key, cur_list_owner = None, None
                else:
                    owner[k] = ""
                    cur_list_key, cur_list_owner = None, None
            else:
                owner[k] = _parse_scalar(v)
                cur_list_key, cur_list_owner = None, None
        i += 1
    return meta, body

def dump_frontmatter(meta, body):
    out = "---\n"
    for k, v in meta.items():
        out += _dump_value(k, v)
    out += "---\n\n" + (body or "")
    return out

# ---------------------------------------------------------------- records

_ID_LOCK = threading.Lock()

def new_id(collection, title=None):
    """稳定且不会碰撞的记录 id：语义 slug + 时间戳 + 递增后缀。"""
    base = slugify(title or "", "rec")
    with _ID_LOCK:
        stamp = format(int(time.time() * 1000) % 0xFFFFFF, "x")
        cand = f"{base}-{stamp}" if base else f"rec-{stamp}"
        n = 0
        while (coll_dir(collection) / f"{cand}.md").exists():
            n += 1
            cand = f"{base}-{stamp}{n}" if base else f"rec-{stamp}{n}"
        # 立即占位，避免同一毫秒内并发写入撞车
        coll_dir(collection).mkdir(parents=True, exist_ok=True)
        (coll_dir(collection) / f"{cand}.md").touch()
    return cand

WIN_RESERVED = {"con", "prn", "aux", "nul", "clock$"} | \
    {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
_ID_OK = re.compile(r"^[^\W_][\w\-. ]{0,119}$", re.UNICODE)


def safe_rid(rid):
    """记录 id 会直接拼成文件名，必须挡住 ../、绝对路径、控制字符和 Windows 保留名。
    （Windows 上一个非法文件名会让整个仓库 checkout 失败，两台机器就此断联。）"""
    s = str(rid or "").strip()
    if not s or "/" in s or "\\" in s or "\x00" in s or s in (".", ".."):
        return None
    if s != os.path.basename(s) or s.rstrip(". ") != s:
        return None
    if not _ID_OK.match(s):
        return None
    if s.split(".")[0].lower() in WIN_RESERVED:
        return None
    return s


_TMP_SEQ = itertools.count(1)      # 进程内单调递增，next() 在 CPython 里是原子的


def atomic_write_text(path, text):
    """先写临时文件再原子替换：合盖睡觉、强杀进程、断电都不会留下半截文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 后缀必须**全局唯一**。原来用 threading.get_ident()&0xffff 是不够的：
    # ThreadingHTTPServer 每个请求起一个线程，线程 id 会被回收复用，
    # 再截断到 16 位，两个并发写同一条记录就可能撞出同名临时文件，
    # 先完成的那个 replace 走之后，后一个直接 FileNotFoundError。
    # 压测复现：12 个并发写同一条记录，12 次里挂 2 次。
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}-{next(_TMP_SEQ)}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)          # 同目录内替换，POSIX 与 Windows 都是原子的
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def read_record(collection, rid):
    rid = safe_rid(rid)
    if not rid:
        return None
    p = coll_dir(collection) / f"{rid}.md"
    if not p.exists():
        return None
    # 文件坏了也要能读出来、能被覆盖修好。
    # 以前这里直接抛，于是「打开这条」和「保存这条」双双 500 ——
    # 一个坏字符就让这条记录在界面里彻底救不回来，只能去 Finder 里手改。
    # errors="replace" 让非 UTF-8 字节不至于炸；解析失败就退回「只有正文」，
    # 用户至少还能看见内容，改完一存就恢复正常。
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"id": rid, "_collection": collection, "body": "",
                "_error": f"读不出来：{e}", "title": rid}
    try:
        meta, body = parse_frontmatter(raw)
    except Exception as e:
        meta, body = {"title": rid, "_error": f"这条的 frontmatter 有问题：{e}"}, raw
    if not isinstance(meta, dict):
        meta, body = {"title": rid, "_error": "frontmatter 不是键值对"}, raw
    meta["id"] = rid
    meta["_collection"] = collection
    meta["body"] = body
    meta["_mtime"] = round(p.stat().st_mtime, 3)
    return meta

# 解析缓存：键是文件路径，值是 (mtime_ns, size, 解析好的记录)。
#
# 为什么需要：压测到 11317 条记录时，bootstrap 要 580ms，其中九成花在
# 解析 frontmatter 上（同样样本：stat 3ms、读盘 10ms、解析 35ms）。
# 而 bootstrap 在「提升文献」「同步」「恢复备份」之后都会重来一次，
# 每次都把没变的一万条重新解析一遍纯属浪费。
#
# 用 (mtime_ns, size) 判定失效而不是只看 mtime：某些文件系统 mtime 精度粗，
# 同一秒内改回同样长度的内容会漏判，加上 size 能挡掉绝大多数。
_REC_CACHE = {}
_REC_CACHE_MAX = 60000


def list_records(collection):
    d = coll_dir(collection)
    out = []
    if not d.exists():
        return out
    for p in sorted(d.glob("*.md")):
        try:
            st = p.stat()
            # new_id 会先 touch 一个占位文件防止并发撞车；正在写入的空壳不该显示出来
            if st.st_size == 0:
                if time.time() - st.st_mtime > 300:
                    p.unlink(missing_ok=True)      # 五分钟还是空的 = 上次写到一半没写完
                continue
            key = str(p)
            hit = _REC_CACHE.get(key)
            if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
                # 返回浅拷贝：调用方（比如批量操作）往记录上挂字段时，
                # 不能污染缓存里那一份
                out.append(dict(hit[2]))
                continue
            raw = p.read_text(encoding="utf-8", errors="replace")
            try:
                meta, body = parse_frontmatter(raw)
            except Exception as e:
                # 一个坏文件不该让整批读取失败，也不该让这条记录从列表里消失 ——
                # 消失了用户就再也点不到它，连修都没法修
                meta, body = {"title": p.stem, "_error": f"frontmatter 有问题：{e}"}, raw
            if not isinstance(meta, dict):
                meta, body = {"title": p.stem, "_error": "frontmatter 不是键值对"}, raw
            meta["id"] = p.stem
            meta["_collection"] = collection
            meta["body"] = body
            meta["_mtime"] = round(st.st_mtime, 3)
            # 缓存满了就不再往里塞（不淘汰旧的，因为条目本身很小、
            # 而工作台的记录总数是有限的），但**删掉的文件要及时清掉**，
            # 否则批量删完一轮，缓存会一直占着那些再也用不到的条目。
            if len(_REC_CACHE) < _REC_CACHE_MAX:
                _REC_CACHE[key] = (st.st_mtime_ns, st.st_size, meta)
            out.append(dict(meta))
        except Exception as e:
            out.append({"id": p.stem, "_collection": collection,
                        "title": p.stem, "_error": str(e), "body": ""})
    return out

class Conflict(Exception):
    def __init__(self, mine, theirs):
        self.mine, self.theirs = mine, theirs


class BadBody(Exception):
    """请求正文不合法 → 400，而不是让它继续往下走。"""


MAX_BODY = 64 * 1024 * 1024      # 64MB：附件上传够用，又挡得住内存炸弹
# 静态资源整份读进内存再发，所以要有上限。app/ 下最大的文件也就几百 KB，
# 但这个目录用户是能往里放东西的，放进去一个 4GB 的 PDF 就是一次 OOM。
MAX_STATIC = 64 * 1024 * 1024
# 回传本机文件（PDF 等）也是整份读进内存。上限放宽些，但必须有。
MAX_SERVE_FILE = 512 * 1024 * 1024


def write_record(collection, rec, expect_mtime=None):
    d = coll_dir(collection)
    d.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    # id 会变成文件名：先净化，再一路用净化后的值（否则「尾部空格 」这类会写出
    # Windows 打不开的文件，git 一同步另一台机器就 checkout 失败）
    if rec.get("id"):
        clean = safe_rid(rec["id"])
        if not clean:
            raise BadBody("记录 id 不合法：" + str(rec["id"])[:60])
        rec["id"] = clean
    # 另一台设备（或 Claude）在你编辑期间改过这条记录 → 交给用户选，绝不静默覆盖
    rid_check = rec.get("id")
    if rid_check and expect_mtime:
        f = d / f"{rid_check}.md"
        # 用浮点 mtime + 1 秒容差：整秒截断会把冲突盲区放大到 2 秒，
        # 两台设备前后脚保存就会有一方被静默覆盖
        try:
            expect = float(expect_mtime)
        except Exception:
            expect = 0.0
        if f.exists() and expect and f.stat().st_mtime > expect + 1.0:
            raise Conflict(rec, read_record(collection, rid_check))
    # 下划线开头的一律是内部字段（_mtime 冲突检测、_collection 归属、
    # _body_more 首屏截断标记…），绝不能写进 md 文件。
    # 写进去之后会被当成真字段读回来，从此这条记录永远带着它。
    for _k in [k for k in rec if isinstance(k, str) and k.startswith("_")]:
        rec.pop(_k, None)
    # body 整个不在提交里 = 调用方明确表示「别动正文」，保留磁盘上那份。
    # 这是前端最后一道网的服务端配合：宁可不改，也不能写进截断的正文。
    if "body" in rec:
        body = rec.pop("body", "")
        # 正文必须是字符串。写进来的不一定是界面 —— 也可能是 Claude、
        # 别的脚本、另一台机器同步过来的。给个数字或列表就 500 的话，
        # 用户看到的只是「保存失败」，完全不知道是哪一条、为什么。
        if body is None:
            body = ""
        elif not isinstance(body, str):
            body = json.dumps(body, ensure_ascii=False, indent=2) \
                if isinstance(body, (dict, list)) else str(body)
    else:
        old_rec = read_record(collection, rec.get("id")) if rec.get("id") else None
        body = (old_rec or {}).get("body", "")
        if not isinstance(body, str):
            body = str(body or "")
    rid = rec.pop("id", None) or new_id(collection, rec.get("title") or rec.get("name"))
    rec.setdefault("created", iso())
    rec["updated"] = iso()
    f = d / f"{rid}.md"
    atomic_write_text(f, dump_frontmatter(rec, body))
    rec["id"] = rid
    rec["body"] = body
    rec["_collection"] = collection
    rec["_mtime"] = round(f.stat().st_mtime, 3)
    # 搜索为了省 stat 会缓存两秒的记录快照。刚存完就搜却搜不到，
    # 用户只会觉得「存丢了」，所以写完立刻让它失效。
    if searchmod is not None:
        try:
            searchmod.invalidate_snapshot()
        except Exception:
            pass
    return rec

def delete_record(collection, rid):
    if searchmod is not None:
        try:
            searchmod.invalidate_snapshot()
        except Exception:
            pass
    rid = safe_rid(rid)
    if not rid:
        return False
    p = coll_dir(collection) / f"{rid}.md"
    if p.exists():
        trash = LOCAL / "trash" / collection
        trash.mkdir(parents=True, exist_ok=True)
        # 回收站是删除的唯一一份后悔药，所以文件名一定要撞不上。
        # 只用秒级时间戳的话，「删掉 → 重建同名 → 再删」发生在同一秒里，
        # 后一份会把前一份直接盖掉，那份就真没了。
        stamp = f"{rid}-{int(time.time())}"
        dest = trash / f"{stamp}.md"
        n = 1
        while dest.exists():
            dest = trash / f"{stamp}-{n}.md"
            n += 1
        _REC_CACHE.pop(str(p), None)
        shutil.move(str(p), str(dest))
        return True
    return False

# ---------------------------------------------------------------- settings

def _load_json(path, default):
    """读 JSON。文件坏了、或者内容压根不是预期的类型（比如被写成了数组），
    都退回默认值——一个坏文件不该让整个工作台打不开。"""
    try:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            if type(obj) is type(default) or default is None:
                return obj
            sys.stderr.write(f"[warn] {path.name} 内容类型不对（{type(obj).__name__}），已按默认值处理\n")
    except Exception as e:
        sys.stderr.write(f"[warn] {path.name} 读取失败（{e}），已按默认值处理\n")
    return json.loads(json.dumps(default))

def _save_json(path, obj):
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


# 这些 JSON 小文件全是「读进来 → 改一处 → 整份写回去」的用法。
# 单次写是原子的，但**读到写之间没有锁**，而这个服务器一个请求一个线程，
# 后台调度线程每分钟还会自己动一次配额。两边同时读到同一份旧数据，
# 后写的那个就把先写的那次改动整份盖掉 ——
# 打卡记录、配额降速（AIMD 那个乘性退避）、刚在设置里改的选项，都这么无声消失过。
#
# 用「按文件一把可重入锁」把读-改-写包成一次事务。
# 可重入是必需的：事务里常常会再调 get_config() 这种也要拿同一把锁的函数。
_JSON_LOCKS = {}
_JSON_LOCKS_GUARD = threading.Lock()


def json_lock(path):
    key = str(path)
    with _JSON_LOCKS_GUARD:
        lk = _JSON_LOCKS.get(key)
        if lk is None:
            lk = _JSON_LOCKS[key] = threading.RLock()
        return lk


@contextlib.contextmanager
def json_txn(path, default):
    """with json_txn(QUOTA_PATH, DEFAULT_QUOTA) as q: q[...] = ...  —— 出了 with 才落盘。

    with 块里抛异常就**不写**，避免把改了一半的状态留在磁盘上。
    """
    with json_lock(path):
        obj = _load_json(path, default)
        yield obj
        _save_json(path, obj)

CONFIG_PATH = DATA / "config.json"          # 共享设置（进 git）
DEVICE_PATH = LOCAL / "device.json"         # 本机设置（不进 git）
SECRETS_PATH = LOCAL / "secrets.json"       # 密钥（不进 git）
QUOTA_PATH = CLAUDE / "quota.json"          # 额度调度器状态（进 git）
QUEUE_PATH = CLAUDE / "queue.json"          # 自动任务队列（进 git）
QUOTES_PATH = DATA / "quotes.json"          # 箴言库（进 git）


def log_ai_call(provider, result):
    """API 是按量付费的，用了多少要能查。只记条数和 token，不记内容。"""
    path = LOCAL / "ai-usage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    u = result.get("usage") or {}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": iso(), "provider": provider,
                             "model": result.get("model"),
                             "in": u.get("in"), "out": u.get("out")},
                            ensure_ascii=False) + "\n")


def ai_usage_summary(days=30):
    path = LOCAL / "ai-usage.jsonl"
    if not path.exists():
        return {"calls": 0, "in": 0, "out": 0, "days": days}
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    calls = tin = tout = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        if str(d.get("at", "")) < cut:
            continue
        calls += 1
        tin += int(d.get("in") or 0)
        tout += int(d.get("out") or 0)
    return {"calls": calls, "in": tin, "out": tout, "days": days}



# 「这件事这周/今天已经做过了」要落盘，不能只记在内存里 ——
# 否则每重启一次服务，周报就会被重新推一遍（用户会连收好几条一模一样的）
DONE_MARKS = LOCAL / "done-marks.json"


def already_done(tag):
    try:
        return tag in (_load_json(DONE_MARKS, {}) or {})
    except Exception:
        return False


def mark_done(tag):
    try:
        with json_txn(DONE_MARKS, {}) as d:
            d[tag] = iso()
            if len(d) > 400:                   # 只留最近的，不让它无限长
                keep = dict(sorted(d.items(), key=lambda kv: kv[1])[-200:])
                d.clear()
                d.update(keep)
    except Exception:
        pass



def mail_intake(limit=20):
    """把邮箱里的新邮件变成「待分类」的想法。标题当内容，正文附在下面。"""
    if sv is None:
        return {"ok": False, "detail": "services 未加载"}
    cfg = (get_secrets().get("push") or {}).get("inbox") or {}
    if not cfg.get("enabled"):
        return {"ok": False, "detail": "邮箱收件没开启"}
    r = sv.imap_fetch(cfg, limit)
    if not r.get("ok"):
        return r
    made = 0
    for it in r["items"]:
        title = (it.get("subject") or "").strip() or (it.get("body") or "")[:60].strip()
        if not title:
            continue
        body = (it.get("body") or "").strip()
        write_record("ideas", {
            "title": title[:200], "kind": "idea", "status": "new", "source": "mail",
            "body": (body[:3000] + ("\n\n—— 来自邮件 " + str(it.get("date") or ""))) if body
                    else "—— 来自邮件 " + str(it.get("date") or ""),
        })
        made += 1
    return {"ok": True, "fetched": len(r["items"]), "created": made}


# ------------------------------------------------------ 文献索引：Zotero 与提升

ZOTERO_BASE = "http://127.0.0.1:23119/api"


def build_diagnostics():
    """一键诊断包：给「我这儿坏了」这句话配上可以查的证据。

    刻意**不含任何记录内容** —— 不含标题、正文、文献题录、生活数据。
    只有版本、环境、各集合的条数、最近的同步日志和错误。
    用户能放心发出来，我们也能真的定位问题。
    """
    cfg, dev = get_config(), get_device()
    def _count(c):
        try:
            return len(list_records(c))
        except Exception:
            return -1
    lines = []
    A = lines.append
    A("# 学术工作台 · 诊断包")
    A("")
    A("这份文件**不含任何记录内容**（没有标题、没有正文、没有文献、没有生活数据），")
    A("只有版本、环境和数量统计，可以直接贴到 issue 里。")
    A("")
    A("## 版本与环境")
    A(f"- 工作台版本：{VERSION}")
    A(f"- Python：{sys.version.split()[0]}  平台：{sys.platform}")
    A(f"- 生成时间：{iso()}")
    try:
        A(f"- 本机时区：{datetime.now().astimezone().tzinfo}")
    except Exception:
        pass
    A(f"- 模块加载：services={'ok' if sv else '未加载'} · library={'ok' if lib else '未加载'} · "
      f"search={'ok' if searchmod else '未加载'} · pdfmeta={'ok' if pdfmeta else '未加载'}")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Europe/London")
        A("- 系统时区库（zoneinfo）：可用")
    except Exception as e:
        A(f"- 系统时区库（zoneinfo）：**不可用** —— {str(e)[:80]}（Windows 常见，日历会退回用日历自带的规则）")
    A("")
    A("## 数据规模（只有条数）")
    for c in COLLECTIONS:
        A(f"- {c}: {_count(c)}")
    for c in LOCAL_COLLECTIONS:
        A(f"- {c}（本机）: {_count(c)}")
    ix = get_library()
    if ix is not None:
        try:
            st = ix.stats()
            A(f"- 文献索引: {st.get('total')} 条，来源 {st.get('by_source')}")
        except Exception as e:
            A(f"- 文献索引: 读取出错 {str(e)[:80]}")
    A("")
    A("## 配置（只有开关状态，没有任何密钥或地址）")
    A(f"- 已完成向导：{(cfg.get('setup') or {}).get('done')}")
    A(f"- 日历订阅数：{len((cfg.get('calendar') or {}).get('ics') or [])}")
    A(f"- 文献管理器：{(cfg.get('reading') or {}).get('manager')}")
    A(f"- 远程访问：{(cfg.get('security') or {}).get('remote_enabled')} · "
      f"只读 {(cfg.get('security') or {}).get('remote_readonly')}")
    A(f"- 自动任务：{(cfg.get('autotasks') or {}).get('enabled')}")
    st = secrets_status()
    A(f"- 已配置的凭据（只列有没有）：{ {k: bool(v) for k, v in st.items()} }")
    A(f"- 论文根目录是否已设：{bool(dev.get('paper_root'))} · "
      f"备份目录是否已设：{bool(dev.get('onedrive_backup_dir'))}")
    A("")
    A("## Git 状态")
    try:
        g = git_status()
        A(f"- 是仓库：{g.get('repo')} · 分支：{g.get('branch')} · 未提交 {g.get('dirty')} 处 · "
          f"领先 {g.get('ahead')} 个提交 · 从未推送过：{g.get('never_pushed')}")
        A(f"- 远程地址是否已设：{bool(g.get('remote'))}")
    except Exception as e:
        A(f"- 读不出来：{str(e)[:120]}")
    A("")
    A("## 最近的同步日志（已自动抹掉 token）")
    try:
        lg = (LOCAL / "sync.log")
        tail = lg.read_text(encoding="utf-8", errors="replace").splitlines()[-40:] if lg.exists() else []
        A("```")
        for x in tail:
            A(_mask(x))
        if not tail:
            A("（没有日志）")
        A("```")
    except Exception as e:
        A(f"（读不出来：{str(e)[:80]}）")
    return "\n".join(lines) + "\n"


def open_local_file(path_str):
    """打开/回传一个本机文件。

    为什么必须走服务端：浏览器**禁止 http 页面跳 file:// 链接**——
    点了没反应，也不报错，用户以为是软件坏了。所以由服务端读文件回传。

    安全上只放行两类：文献索引里登记过的 PDF、以及「论文根目录」下的文件。
    否则任何人拿到这台机器的页面就能读你整块硬盘。
    """
    p = Path(os.path.expanduser((path_str or "").strip()))
    if not p.is_absolute() or not p.exists() or not p.is_file():
        return None, "文件不在了：" + str(path_str)[:200]
    try:
        rp = p.resolve()
    except Exception:
        return None, "路径解析不了"
    allowed = []
    dev = get_device() or {}
    for d in (dev.get("paper_root"), dev.get("onedrive_backup_dir")):
        if d:
            try:
                allowed.append(Path(os.path.expanduser(d)).resolve())
            except Exception:
                pass
    allowed.append(ROOT.resolve())
    ix = get_library()
    known = set()
    if ix is not None:
        for it in ix.load():
            if it.get("p"):
                try:
                    known.add(str(Path(os.path.expanduser(it["p"])).resolve()))
                except Exception:
                    pass
    if str(rp) not in known and not any(
            str(rp) == str(a) or str(rp).startswith(str(a) + os.sep) for a in allowed):
        return None, ("这个文件不在允许范围内。只允许打开文献索引里登记过的 PDF，"
                      "或者「设置 → 本机设置 → 论文根目录」底下的文件。")
    return rp, ""



def zotero_probe():
    """探一下本机 Zotero 开没开、那个开关勾没勾。

    Zotero 7+ 在 23119 端口提供只读本地 API，但要用户在
    「设置 → 高级 → 允许本机其它程序与 Zotero 通信」里勾上，否则 403。
    """
    if sv is None:
        return {"ok": False, "detail": "services.py 未加载"}
    try:
        import urllib.request
        req = urllib.request.Request(ZOTERO_BASE + "/users/0/items?limit=1",
                                     headers={"Zotero-API-Version": "3"})
        with urllib.request.urlopen(req, timeout=4) as r:
            n = r.headers.get("Total-Results")
            return {"ok": True, "running": True, "total": int(n) if n and n.isdigit() else None}
    except Exception as e:
        s = str(e)
        if "403" in s:
            return {"ok": False, "running": True, "detail":
                    "Zotero 在跑，但没允许外部程序通信。去 Zotero「设置 → 高级」，"
                    "勾上「允许本机上的其它应用程序与 Zotero 通信」，再点一次。"}
        if "refused" in s.lower() or "111" in s or "10061" in s:
            return {"ok": False, "running": False, "detail":
                    "连不上 Zotero（127.0.0.1:23119）。确认 Zotero 桌面版正开着，"
                    "而且是 7.0 以上的版本。"}
        return {"ok": False, "running": False, "detail": f"连不上：{s[:160]}"}


def zotero_sync(ix, body):
    """分批把 Zotero 库拉进索引。

    官方文档明确写了本地 API「返回完整数据集、默认不分页」——
    一万条一次性拉回来，JSON 解析就能把内存顶起来。所以这里强制分页，
    每批 100 条，边拉边攒，最后一次性落盘。
    """
    import urllib.request
    limit = 100
    start = 0
    got, pages = [], 0
    hard_cap = int(body.get("max") or 50000)
    t0 = time.time()
    while True:
        url = f"{ZOTERO_BASE}/users/0/items?limit={limit}&start={start}&itemType=-attachment%20||%20note"
        try:
            req = urllib.request.Request(url, headers={"Zotero-API-Version": "3"})
            with urllib.request.urlopen(req, timeout=25) as r:
                chunk = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if not got:
                pr = zotero_probe()
                return {"ok": False, "detail": pr.get("detail") or f"拉取失败：{str(e)[:160]}"}
            break
        if not chunk:
            break
        got.extend(chunk)
        pages += 1
        start += limit
        if len(got) >= hard_cap or len(chunk) < limit:
            break
        if time.time() - t0 > 120:      # 库特别大时先落一部分，别把请求挂死
            break
    items = lib.parse_zotero_items(got)
    if body.get("mirror"):
        # 以 Zotero 为准全量对齐：你在 Zotero 里删掉的，这边也删掉。
        # 普通同步只加不减，删掉的条目会在索引里变僵尸。
        st = ix.mirror(items, "zotero", force=bool(body.get("force")))
        if not st.get("ok"):
            st.update({"fetched": len(got), "parsed": len(items), "mirrored": True})
            return st
    else:
        st = ix.add_many(items, source="zotero")
    st.update({"ok": True, "fetched": len(got), "parsed": len(items),
               "mirrored": bool(body.get("mirror")),
               "pages": pages, "ms": round((time.time() - t0) * 1000)})
    return st


def promote_to_reading(it):
    """把索引里的一条题录「提升」成精读笔记。

    索引是几千条的题录表，精读笔记是你真读过的那几十上百篇。
    提升过来只带题录字段，研究问题/方法/结论留空等你自己填 ——
    这些本来就是别的软件不会有、也代替不了你的东西。
    """
    for r in list_records("reading"):
        if it.get("d") and lib._norm_doi(r.get("doi")) == it["d"]:
            return {"ok": True, "already": True, "id": r.get("id"),
                    "detail": "这篇已经在精读笔记里了"}
        if lib._norm_title(r.get("title")) == lib._norm_title(it.get("t")) and r.get("title"):
            return {"ok": True, "already": True, "id": r.get("id"),
                    "detail": "这篇已经在精读笔记里了"}
    rec = {
        "title": it.get("t") or "（未命名）",
        "authors": it.get("a") or [],
        "year": it.get("y"),
        "journal": it.get("j") or "",
        "doi": it.get("d") or "",
        "link": it.get("u") or "",
        "status": "to-read",
        "level": "skim",
        "topic": (it.get("tg") or [""])[0],
        "source": "library",
        "lib_key": it.get("k") or "",
        "citekey": it.get("c") or "",
        "body": "",
    }
    saved = write_record("reading", rec)
    return {"ok": True, "already": False, "id": saved.get("id")}


# 首屏只该带「画得出界面」的东西。
#
# 压测 11317 条记录时 bootstrap 有 4.88MB，大头是两块：
#   · 每条记录的 body（正文）—— 列表页一个字都不显示，点开才要
#   · 生活流水（开支/饮食/运动）—— 逐日累积、永不停止，三年就是几千条
# 正文改成按需拉（records/<coll>/<id> 本来就能拿全量），
# 生活流水只带最近这一段，翻旧账时再单独请求。
BODY_KEEP = {"reports", "retros"}          # 这两类的正文就是内容本身，卡片直接要显示

# 首屏**不再放截断过的 body**，这是踩了两轮坑之后改的做法。
#
# 原来的做法是把 body 截成 160 字照样放在 body 这个字段里。问题在于
# 「一份看起来正常、其实是残缺的 body」会顺着各种路径被原样存回磁盘：
# 编辑器、拖便利贴、勾完成、拖甘特条、项目页的笔记框、想法升级成稿件……
# 每发现一处补一处，补了十几处，还是漏（项目页那个笔记框就是后来才发现的）。
# 根子在于：只要那个字段还叫 body，任何「读出来再存回去」的代码就都是地雷。
#
# 现在改成：非全文集合根本不带 body，只带 _preview（下划线开头，
# write_record 会把所有 _ 字段剥掉，所以它**不可能**被写进文件），
# 再配一个 _body_more 告诉界面「这条有正文，要用请去取全量」。
# 这样不是靠每个调用点小心，而是让「存回截断正文」这件事无从发生。
#
# 附带的好处：17594 条记录时首屏从 7.77MB 降到 2MB 出头 ——
# 那 5.7MB 预览里，界面真正显示的只有稿件卡和便利贴那两处。
BODY_PREVIEW = 90                          # 便利贴显示 90 字，稿件卡也够用
BODY_PREVIEW_COLLS = {"manuscripts", "ideas"}   # 只有这两处卡片会显示正文片段
LIFE_RECENT_DAYS = 180
LIFE_MAX = 400

# 只有「逐日累积、旧的翻不翻都行」的流水才能按时间裁。
#
# 这条界线是踩过坑才划出来的：本来六个本地集合一视同仁地只带近 180 天，
# 结果「重要日子」整张卡变空了 —— 生日存的是 1962-05-12，
# 靠 yearly 每年提醒，日期天然在很久以前，一裁就全没了；
# 「生活事务」里逾期没做的旧待办同样会凭空消失，
# 而那恰恰是最需要看见的几条。清单更直接：根本没有日期。
# 这三类都是「有限的、每条都还算数」的册子，不是流水。
LIFE_STREAMS = {"diet", "exercise", "finance"}


def slim_bootstrap(data, meta=None):
    """瘦身，并**如实告诉界面裁掉了多少**。

    只裁不说的话，界面会拿着一份残缺数据当全量用 ——
    「开支合计」这种统计会算出一个偏小的数字，还照样叫「合计」。
    数据不全是可以的，假装全才是不行的。
    """
    cut = (datetime.now() - timedelta(days=LIFE_RECENT_DAYS)).strftime("%Y-%m-%d")
    out = {}
    for coll, recs in data.items():
        if meta is not None:
            meta[coll] = {"total": len(recs)}
        since = cut
        if coll in LIFE_STREAMS:
            dated = [r for r in recs
                     if str(r.get("date") or r.get("start") or "")[:10] >= cut]
            # 没有日期的一条都不能少：它没有「新旧」可言，裁了就是凭空消失
            undated = [r for r in recs if not (r.get("date") or r.get("start"))]
            if len(dated) > LIFE_MAX:
                dated = sorted(dated, key=lambda r: str(r.get("date") or ""),
                               reverse=True)[:LIFE_MAX]
                # 条数上限一旦生效，实际覆盖的区间就比 180 天短了。
                # 这时候还报「近 180 天」，界面就会拿一段更短的数据
                # 挂上一个更长的时间标签 —— 又是一个对不上的数字。
                # 所以 since 报**真正带回来的最早那一天**。
                if dated:
                    since = min(str(r.get("date") or r.get("start") or "")[:10]
                                for r in dated) or cut
            recs = dated + undated
        if meta is not None and len(recs) != meta[coll]["total"]:
            meta[coll].update({"shown": len(recs), "partial": True,
                               "since": since,
                               # 没有日期的那些是**全带回来了**的，
                               # 界面算合计时要把它们算进去，才对得上标签。
                               "undated_complete": True})
        if coll not in BODY_KEEP:
            want_preview = coll in BODY_PREVIEW_COLLS
            trimmed = []
            for r in recs:
                b = r.get("body")
                if b:
                    r = dict(r)
                    r.pop("body", None)        # 关键：首屏根本不带 body 这个字段
                    # 只要正文非空就打标记 —— 哪怕它很短。
                    # 「短正文照原样带过来」听着无害，其实是另一个坑：
                    # 界面会以为手上这份是全的，于是不去取全量，
                    # 而这条记录在磁盘上可能刚被别处改长了。
                    r["_body_more"] = True
                    if want_preview:
                        r["_preview"] = b[:BODY_PREVIEW]
                trimmed.append(r)
            recs = trimmed
        out[coll] = recs
    return out


def load_quotes():
    """箴言库文件被改坏也不能让首屏 banner 崩掉。"""
    q = _load_json(QUOTES_PATH, {"quotes": []})
    if not isinstance(q, dict):
        q = {"quotes": []}
    if not isinstance(q.get("quotes"), list):
        q["quotes"] = []
    q["quotes"] = [x for x in q["quotes"] if isinstance(x, dict)]
    return q


def new_quote_id(existing):
    """给新箴言取一个**确实不重复**的 id。

    原来是 "u" + hex(毫秒 % 0xFFFFFF)：这个值每 16.7 秒就绕回来一次，
    同一毫秒里加两条更是必然撞上。id 一撞，删其中一条就会把另一条一起删掉 ——
    用户看到的是「我明明只删了一条，怎么少了两条」。
    这里直接看已有的 id 避让，撞不上为止。
    """
    used = {x.get("id") for x in (existing or []) if isinstance(x, dict)}
    base = int(time.time() * 1000)
    for i in range(100000):
        nid = "u" + format((base + i) % 0xFFFFFFFF, "x")
        if nid not in used:
            return nid
    return "u" + uuid.uuid4().hex[:12]

DEFAULT_CONFIG = {
    "owner": "",
    "sections": ["today", "hub", "papers", "conferences",
                 "reading", "ideas", "schedule", "life", "ai", "settings"],
    "theme": {"accent": "#3b5bdb", "mode": "light", "density": "comfortable"},
    "today_horizon_days": 45,
    "stale_manuscript_days": 7,
    "reading": {"weekly_goal": 5, "xp": {"skim": 1, "deep": 3, "critical": 5},
                "review_days": [1, 7, 30, 90],
                # 你平时用哪个文献管理器 —— 决定索引里「打开」按钮往哪跳。
                # zotero / mendeley / endnote / papers / none
                "manager": "zotero"},
    "autotasks": {
        "enabled": True,
        "kinds": ["brainstorm", "gap-scan", "method-scan", "data-scan", "audit",
                  "github-radar", "lit-radar"],
        "max_items_per_run": 3,
        "unread_pause_threshold": 3,
    },
    "tutorial_dismissed": {},
    "brand": {"title": "学术工作台", "sub": "Scholar Workspace"},
    "hide_samples": False,
    "card_opts": {},
    # ---- 首次使用向导会填写下面这些 ----
    "setup": {"done": False, "step": 0, "completed_at": ""},
    "profile": {"name": "", "city": "", "lat": None, "lon": None,
                "field": "", "keywords": []},
    "calendar": {"ics": [], "refresh_min": 15, "lunar": True, "weather": True},
    "ai": {"default_jump": "claude", "plan": "max5",
           "reset_hint": "", "work_start": "09:00", "work_end": "23:00"},
    "push": {"weekly_cron": "MON 08:00", "daily_brief": False,
             "channels": {"dingtalk": False, "email": False, "custom": False}},
    "security": {"remote_enabled": False, "remote_readonly": True, "encrypt_backup": False},
    "quicklinks": [
        {"name": "打开 Claude", "url": "https://claude.ai/new", "app": "claude://",
         "color": "#c96442", "letter": "C", "group": "AI"},
        {"name": "打开 ChatGPT", "url": "https://chatgpt.com/", "app": "chatgpt://",
         "color": "#10a37f", "letter": "G", "group": "AI"},
        {"name": "Google Scholar", "url": "https://scholar.google.com/", "color": "#4285f4", "letter": "S", "group": "学术"},
        {"name": "Overleaf", "url": "https://www.overleaf.com/project", "color": "#7048e8", "letter": "O", "group": "学术"},
        {"name": "SSRN", "url": "https://www.ssrn.com/index.cfm/en/", "color": "#0b5394", "letter": "R", "group": "学术"},
    ],
    "layout": {"rail_split": 0.55, "rail_collapsed": {"calendar": False, "memo": False},
               "card_order": {}, "hidden_cards": []},
    # 登记过的「文献文件夹」：点一下就能把里面的 .bib/.ris/.nbib 和 PDF 收进索引
    "lib_folders": [],
    # 学术雷达：每周按关键词和关键人去几个源捞新论文
    # people 的元素形如 {"name": "...", "orcid": "...", "note": "..."}；
    # 没填 ORCID 的只能按姓名模糊匹配，周报里会标明「可能不是同一个人」
    "radar": {"keywords": [], "people": [], "sources": ["crossref", "nber", "arxiv"],
              "per_keyword": 12, "mailto": ""},
}

# 点快捷入口时先试着唤起这些桌面软件，唤不起来再退回网页
APP_SCHEMES = {
    "claude.ai": "claude://",
    "chatgpt.com": "chatgpt://",
    "chat.openai.com": "chatgpt://",
}

DEFAULT_DEVICE = {
    "device_name": socket.gethostname(),
    "timezone": "auto",
    # Zotero 存储目录每台机器不一样，跨设备打开 PDF 靠它拼路径
    "zotero_root": "",
    "paper_root": "",          # 主根目录（兼容旧配置）
    "paper_roots": [],         # 可以有多个：论文、合作项目、旧存档…
    "onedrive_backup_dir": "",
    "watch_spreadsheets": [],
    "daily_backup_times": ["12:00", "21:00"],
    "rolling_minutes": 30,
    "rolling_keep_days": 7,
}

DEFAULT_QUOTA = {
    "rate_per_week": 14.0,        # 允许的成本点数/周（1轻=1，中=3，重=8）
    "week_start": None,
    "spent_this_week": 0.0,
    "history": [],                # 每周结算记录
    "runs": [],                   # 每次自动运行 {ts, kind, cost, ok}
    "blocked_events": [],         # 你点"我被挡住了"
    "activity": {},               # "%w-%H" -> 计数，学习活跃画像
    "overrides": {"tonight_boost": False, "silent_week": False},
    "unread_reports": 0,
}

# 老配置迁移：期刊/已刊并进论文库，稿件库并进「研究」
SECTION_MIGRATION = {"journals": "papers", "published": "papers", "manuscripts": "hub"}


def get_config():
    cfg = _load_json(CONFIG_PATH, DEFAULT_CONFIG)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    # 老配置迁移：改过名的模块换掉，新增的模块自动补进侧边栏
    secs = cfg.get("sections") or []
    if secs:
        out, seen = [], set()
        for x in secs:
            x = SECTION_MIGRATION.get(x, x)
            if x not in seen:
                seen.add(x); out.append(x)
        for x in DEFAULT_CONFIG["sections"]:
            if x not in seen:
                seen.add(x)
                out.insert(1 if x == "hub" else len(out), x)
        if out != secs:
            cfg["sections"] = out
            _save_json(CONFIG_PATH, cfg)
    # 老配置迁移：给已有的 Claude / ChatGPT 快捷入口补上桌面软件协议
    changed = False
    for l in (cfg.get("quicklinks") or []):
        if not isinstance(l, dict) or l.get("app"):
            continue
        u = str(l.get("url") or "")
        for host, scheme in APP_SCHEMES.items():
            if host in u:
                l["app"] = scheme
                changed = True
                break
    if changed:
        _save_json(CONFIG_PATH, cfg)
    return cfg

def get_device():
    dev = _load_json(DEVICE_PATH, DEFAULT_DEVICE)
    for k, v in DEFAULT_DEVICE.items():
        dev.setdefault(k, v)
    return dev

def _safe(fn, fallback):
    """任何子系统炸了都不该让首屏打不开。"""
    try:
        return fn()
    except Exception as e:
        sys.stderr.write(f"[warn] {getattr(fn, '__name__', fn)} 失败: {e}\n")
        return fallback


def get_secrets():
    return _load_json(SECRETS_PATH, {})


def secrets_status():
    """只报告"填没填"，绝不把密钥本身送到前端。"""
    s = get_secrets()
    p = s.get("push", {})
    em = p.get("email", {}) or {}
    return {
        "github_user": bool(s.get("github", {}).get("user")),
        "github_token": bool(s.get("github", {}).get("token")),
        "dingtalk": bool(p.get("dingtalk_webhook")),
        "dingtalk_signed": bool(p.get("dingtalk_secret")),
        "email": bool(em.get("host") and em.get("user") and em.get("to")),
        "email_to": em.get("to", ""),
        "email_host": em.get("host", ""),
        "email_port": em.get("port", ""),
        "email_user": em.get("user", ""),
        "remote_code": bool(s.get("remote", {}).get("access_code")),
        "backup_pass": bool(s.get("backup", {}).get("passphrase")),
    }


def deep_merge(base, patch):
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ---- 外部数据缓存（天气 / ICS），避免频繁请求 ----
_CACHE = {"weather": {"at": 0, "data": None}, "ics": {"at": 0, "data": None}}


def cached_weather(force=False):
    cfg = get_config()
    if not cfg.get("calendar", {}).get("weather", True) or sv is None:
        return {"ok": False, "detail": "未启用天气"}
    c = _CACHE["weather"]
    if not force and c["data"] and time.time() - c["at"] < 1800:
        return c["data"]
    p = cfg.get("profile", {})
    lat, lon = p.get("lat"), p.get("lon")
    if lat is None or lon is None:
        g = sv.geo_lookup()
        if g.get("ok"):
            cfg["profile"]["lat"], cfg["profile"]["lon"] = g["lat"], g["lon"]
            if not cfg["profile"].get("city"):
                cfg["profile"]["city"] = g.get("city", "")
            _save_json(CONFIG_PATH, cfg)
            lat, lon = g["lat"], g["lon"]
    d = sv.weather(lat, lon)
    d["city"] = cfg.get("profile", {}).get("city", "")
    _CACHE["weather"] = {"at": time.time(), "data": d}
    return d


_ICS_FETCHING = threading.Lock()


def _ics_pull(urls):
    events, errs = [], []
    for u in urls[:6]:
        r = sv.fetch_ics(u)
        if r.get("ok"):
            for e in r["events"]:
                e["source"] = "Outlook"
            events.extend(r["events"])
        else:
            errs.append({"url": u[:60], "detail": r.get("detail", "")})
    _CACHE["ics"] = {"at": time.time(),
                     "data": {"ok": True, "events": events, "sources": len(urls),
                              "errors": errs, "fetched": iso()}}


def cached_ics(force=False):
    """日历事件永远从缓存拿，抓取放到后台线程。

    原来是在请求线程里现抓：缓存一过期，下一个打开「今日」页的人
    就要等 Outlook 响应（每个源最多 15 秒超时，最多 6 个源）。
    页面会整个卡住，而且卡的原因用户完全看不出来。
    现在过期只是「触发一次后台刷新」，本次请求立刻返回旧数据。
    """
    cfg = get_config()
    urls = [u for u in (cfg.get("calendar", {}).get("ics") or []) if u]
    if not urls or sv is None:
        return {"ok": True, "events": [], "sources": 0}
    c = _CACHE["ics"]
    ttl = max(60, int(cfg.get("calendar", {}).get("refresh_min", 15)) * 60)
    fresh = c["data"] and time.time() - c["at"] < ttl

    if force or not c["data"]:
        # 用户明确点了「立即同步」，或者压根还没有过数据 —— 只能等
        if _ICS_FETCHING.acquire(blocking=False):
            try:
                _ics_pull(urls)
            finally:
                _ICS_FETCHING.release()
        return _CACHE["ics"]["data"] or {"ok": True, "events": [], "sources": len(urls)}

    if not fresh and _ICS_FETCHING.acquire(blocking=False):
        # 过期了：后台去拉，这次先把旧的给你。日历晚几秒更新没人在意，
        # 页面卡住十几秒有人在意。
        def _bg():
            try:
                _ics_pull(urls)
            except Exception:
                pass
            finally:
                _ICS_FETCHING.release()
        threading.Thread(target=_bg, daemon=True).start()
    return c["data"]


def get_quota():
    q = _load_json(QUOTA_PATH, DEFAULT_QUOTA)
    for k, v in DEFAULT_QUOTA.items():
        q.setdefault(k, v)
    return q

# ------------------------------------------------------------ quota engine
# 见 workspace-plan-v3.md 第二节：AIMD + 活跃画像 + 平方根衰减余量 + 背包挑选

COST = {"light": 1.0, "medium": 3.0, "heavy": 8.0}

def week_key(dt=None):
    dt = dt or now_local()
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")

def quota_settle(q):
    """跨周结算：加性增长 / 乘性回退。"""
    wk = week_key()
    if q.get("week_start") == wk:
        return q
    if q.get("week_start"):
        spent = q.get("spent_this_week", 0.0)
        rate = q.get("rate_per_week", 14.0)
        def _in_week(b):
            try:
                return week_key(datetime.fromisoformat(str(b))) == q["week_start"]
            except Exception:
                return False          # 坏数据一律忽略，绝不让整个工作台起不来
        blocked = any(_in_week(b) for b in (q.get("blocked_events") or []))
        leftover = max(0.0, rate - spent) / rate if rate else 0
        if blocked:
            new_rate = max(2.0, rate * 0.5)
            verdict = "blocked-halve"
        elif leftover > 0.20:
            new_rate = rate * 1.20
            verdict = "surplus-grow"
        else:
            new_rate = rate
            verdict = "well-tuned"
        q["history"].append({"week": q["week_start"], "rate": rate,
                             "spent": round(spent, 1), "verdict": verdict,
                             "new_rate": round(new_rate, 1)})
        q["history"] = q["history"][-26:]
        q["rate_per_week"] = round(new_rate, 2)
    q["week_start"] = wk
    q["spent_this_week"] = 0.0
    q["overrides"]["silent_week"] = False
    _save_json(QUOTA_PATH, q)
    return q

def activity_profile(q):
    """返回 {(weekday, hour): 0..1} 的活跃概率（拉普拉斯平滑）。"""
    act = q.get("activity", {})
    total = sum(act.values()) or 1
    prof = {}
    for wd in range(7):
        for h in range(24):
            prof[(wd, h)] = (act.get(f"{wd}-{h}", 0) + 0.5) / (total + 84)
    mx = max(prof.values()) or 1
    return {k: v / mx for k, v in prof.items()}

def quota_status(q=None):
    q = quota_settle(q or get_quota())
    now = now_local()
    reset = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7)
    tau_h = max(0.1, (reset - now).total_seconds() / 3600)
    try:
        rate = float(q.get("rate_per_week") or 0)
    except Exception:
        rate = 0.0
    if not (rate > 0) or rate != rate:      # 负数 / 0 / NaN 一律回落到默认
        rate = 14.0
    try:
        spent = max(0.0, float(q.get("spent_this_week") or 0))
    except Exception:
        spent = 0.0
    remaining = max(0.0, rate - spent)
    # 目标累计曲线：按剩余时间线性摊（周内平滑，避免堆到最后）
    elapsed_frac = 1 - tau_h / (7 * 24)
    target_spent = rate * elapsed_frac
    behind = spent < target_spent * 0.8      # 落后 → 该多跑
    ahead = spent > target_spent * 1.2       # 超前 → 收敛
    # 安全余量：随剩余时间平方根衰减
    buffer = rate * 0.25 * (tau_h / (7 * 24)) ** 0.5
    if q["overrides"].get("tonight_boost"):
        buffer *= 0.3
    if q["overrides"].get("silent_week"):
        buffer = rate
    available = max(0.0, remaining - buffer)
    prof = activity_profile(q)
    idle_now = 1 - prof[(now.weekday(), now.hour)]
    return {
        "week_start": q["week_start"], "rate_per_week": round(rate, 1),
        "spent": round(spent, 1), "remaining": round(remaining, 1),
        "buffer": round(buffer, 1), "available": round(available, 1),
        "target_spent": round(target_spent, 1),
        "pace": "behind" if behind else ("ahead" if ahead else "on-track"),
        "hours_to_reset": round(tau_h, 1), "idle_score": round(idle_now, 2),
        "overrides": q["overrides"], "history": q["history"][-8:],
        "runs_this_week": [r for r in q.get("runs", [])
                           if r.get("ts", "") >= q["week_start"]],
        "unread_reports": q.get("unread_reports", 0),
    }

def pick_tasks(q=None):
    """背包式挑任务：在可用余量内选 价值/成本 最高且未过期的。"""
    q = q or get_quota()
    st = quota_status(q)
    budget = st["available"]
    cfg = get_config()
    if not cfg["autotasks"]["enabled"] or st["overrides"].get("silent_week"):
        return {"budget": budget, "chosen": [], "reason": "disabled-or-silent"}
    if q.get("unread_reports", 0) >= cfg["autotasks"]["unread_pause_threshold"]:
        return {"budget": budget, "chosen": [], "reason": "too-many-unread"}
    queue = _load_json(QUEUE_PATH, {"tasks": []}).get("tasks", [])
    if not isinstance(queue, list):
        queue = []
    today = today_str()
    live = [t for t in queue if not t.get("done")
            and (not t.get("expires") or t["expires"] >= today)]
    for t in live:
        t["_cost"] = COST.get(t.get("weight", "medium"), 3.0)
        t["_ratio"] = float(t.get("value", 3)) / t["_cost"]
    live.sort(key=lambda t: -t["_ratio"])
    chosen, used = [], 0.0
    for t in live:
        if used + t["_cost"] <= budget:
            chosen.append(t)
            used += t["_cost"]
    if not chosen and budget >= 1 and "audit" in (cfg["autotasks"].get("kinds") or []):
        chosen = [{"id": "sweep-audit", "kind": "audit", "weight": "light",
                   "value": 3, "title": "全库准确性体检（扫尾任务）",
                   "_cost": 1.0, "auto": True}]
        used = 1.0
    return {"budget": round(budget, 1), "used": round(used, 1),
            "chosen": chosen, "pace": st["pace"], "reason": "ok"}

def record_run(kind, weight="medium", ok=True, note=""):
    with json_lock(QUOTA_PATH):
        q = quota_settle(get_quota())
        cost = COST.get(weight, 3.0)
        q["spent_this_week"] = round(q.get("spent_this_week", 0) + cost, 2)
        q["runs"].append({"ts": iso(), "kind": kind, "cost": cost,
                          "ok": ok, "note": note})
        q["runs"] = q["runs"][-200:]
        _save_json(QUOTA_PATH, q)
        return q

def log_activity():
    # 每次 bootstrap 都会调它，是所有配额写入里最频繁的一个 ——
    # 也就最容易把别人刚写的打卡/额度覆盖掉。整段包在锁里。
    with json_lock(QUOTA_PATH):
        q = get_quota()
        now = now_local()
        key = f"{now.weekday()}-{now.hour}"
        q.setdefault("activity", {})
        q["activity"][key] = q["activity"].get(key, 0) + 1
        _save_json(QUOTA_PATH, q)

# ---------------------------------------------------------------- git sync

def git(*args, timeout=60):
    try:
        r = subprocess.run(["git"] + list(args), cwd=str(ROOT),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "git not found"
    except Exception as e:
        return 1, "", str(e)

# ------------------------------------------------------- 跨库关联（想法↔稿件↔文献↔会议）

def _parse_ref(ref):
    """"manuscripts:abc-123" → ("manuscripts", "abc-123")。不合法一律 (None, None)。"""
    s = str(ref or "").strip()
    if ":" not in s:
        return None, None
    coll, _, rid = s.partition(":")
    coll = coll.strip()
    if coll not in COLLECTIONS and coll not in LOCAL_COLLECTIONS:
        return None, None
    rid = safe_rid(rid)
    if not rid:
        return None, None
    return coll, rid


def _links_of(rec):
    v = (rec or {}).get("links")
    if isinstance(v, str):
        v = [x for x in re.split(r"[,;\s]+", v) if x]
    return [str(x) for x in v] if isinstance(v, list) else []


def link_edit(a, b, op="add"):
    """双向增删一条关联。两头都写，所以从任何一边看都是连着的。

    关联不占独立文件——它就存在两条记录各自的 frontmatter 里。
    这样导出、备份、用别的编辑器打开都还看得见，不会有"关系数据库丢了"的问题。
    """
    ca, ia = _parse_ref(a)
    cb, ib = _parse_ref(b)
    if not ca or not cb:
        return {"ok": False, "detail": "关联的两头至少有一头不合法"}
    if (ca, ia) == (cb, ib):
        return {"ok": False, "detail": "不能把一条记录关联到它自己"}
    ra, rb = read_record(ca, ia), read_record(cb, ib)
    if not ra or not rb:
        missing = f"{ca}:{ia}" if not ra else f"{cb}:{ib}"
        return {"ok": False, "detail": f"找不到记录 {missing}"}
    ref_a, ref_b = f"{ca}:{ia}", f"{cb}:{ib}"
    changed = []
    for rec, coll, rid, other in ((ra, ca, ia, ref_b), (rb, cb, ib, ref_a)):
        cur = _links_of(rec)
        if op == "remove":
            new = [x for x in cur if x != other]
        else:
            new = cur + [other] if other not in cur else cur
        if new != cur:
            rec["links"] = new
            rec["id"] = rid
            write_record(coll, rec)
            changed.append(f"{coll}:{rid}")
    return {"ok": True, "op": op, "a": ref_a, "b": ref_b, "changed": changed}


def link_gc():
    """清掉指向已删记录的悬空关联。删记录时对面那条还留着半截箭头，得有人扫。"""
    alive, fixed = set(), 0
    for coll in COLLECTIONS + LOCAL_COLLECTIONS:
        for r in list_records(coll):
            if r.get("id"):
                alive.add(f"{coll}:{r['id']}")
    for coll in COLLECTIONS + LOCAL_COLLECTIONS:
        for r in list_records(coll):
            cur = _links_of(r)
            if not cur:
                continue
            new = [x for x in cur if x in alive]
            if new != cur:
                r["links"] = new
                write_record(coll, r)
                fixed += 1
    return {"ok": True, "fixed": fixed, "alive": len(alive)}


# ---------------------------------------------------------------- git sync（续）

def git_ready():
    code, out, _ = git("rev-parse", "--is-inside-work-tree")
    return code == 0 and out == "true"

SYNC_LOG = LOCAL / "sync.log"

def _mask(text):
    """日志里绝不能留 token：URL 里的 user:token@ 和裸的 ghp_/github_pat_ 都抹掉。"""
    s = str(text or "")
    s = re.sub(r"://([^:/@\s]+):[^@\s]+@", r"://\1:***@", s)
    s = re.sub(r"\b(gh[pousr]_|github_pat_)[A-Za-z0-9_]+", r"\1***", s)
    return s

def sync_log(line):
    """同步的成败必须落盘。以前只存在内存里，服务一重启就查不到为什么没推上去。"""
    try:
        LOCAL.mkdir(parents=True, exist_ok=True)
        old = ""
        if SYNC_LOG.exists():
            old = SYNC_LOG.read_text(encoding="utf-8", errors="replace")
            if len(old) > 200_000:
                old = old[-120_000:]
        with open(SYNC_LOG, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(old + f"[{iso()}] {_mask(line)}\n")
    except Exception:
        pass

def _rebase_in_progress():
    """rebase 停在半路了没有。停在半路时工作区里是带冲突标记的文件。"""
    try:
        d = ROOT / ".git"
        return (d / "rebase-merge").exists() or (d / "rebase-apply").exists()
    except Exception:
        return False


def git_sync(message=None):
    if not git_ready():
        return {"ok": False, "detail": "尚未初始化 git 仓库（设置页可一键初始化）"}
    steps = []
    code, out, err = git("pull", "--rebase", "--autostash")
    if code != 0 and ("no tracking information" in (err or "").lower()
                      or "couldn't find remote ref" in (err or "").lower()):
        code, out, err = 0, "（远程还是空仓库，跳过拉取）", ""
    steps.append({"step": "pull", "code": code, "out": out or err})
    # 拉取失败**绝不能**继续往下走。
    #
    # rebase 冲突（或 autostash 应用失败）之后，工作区里躺着的是带
    # <<<<<<< HEAD 标记的 .md 文件。原来这里不看返回码就 `git add -A` + commit + push，
    # 于是把一堆冲突标记当成正常内容提交、推给另一台机器 ——
    # 而两边的记录从此都是坏的，界面上照样渲染出来，没有任何地方报警。
    # 宁可这次不同步，也不能提交半个冲突。
    if code != 0:
        conflicted = git("diff", "--name-only", "--diff-filter=U")[1].strip()
        # rebase 停在半路时，工作区是「一半我的、一半对面的」状态，
        # 而且带着冲突标记。放着不管，用户接下来在界面里存的每一条
        # 都是在这个坏状态上改。abort 回到同步前 —— 对面的提交还在远程，
        # 一条都没丢，只是这次没合进来。
        aborted_rebase = False
        if _rebase_in_progress():
            aborted_rebase = git("rebase", "--abort")[0] == 0
        _STATE["push_error"] = "拉取失败，本次没有提交也没有推送"
        sync_log("拉取失败，已中止 · " + (err or out)[:300].replace("\n", " ／ "))
        detail = ("从远程拉取时出错，这次**没有**提交、也没有推送 —— "
                  "避免把冲突标记写进你的记录。")
        if aborted_rebase:
            detail += "已经把仓库恢复到同步前的状态，你的文件没有被动过。"
        if conflicted:
            detail += ("\n\n两边都改过的文件：\n" + conflicted[:800]
                       + "\n\n这几条需要你决定留哪一份 —— "
                         "两台机器同时改了同一条记录时会这样。")
        return {"ok": False, "steps": steps, "aborted": "pull",
                "rebase_aborted": aborted_rebase,
                "conflicted": conflicted.split("\n") if conflicted else [],
                "detail": detail}
    git("add", "-A")
    code, out, err = git("commit", "-m", message or f"workspace sync {iso()}")
    steps.append({"step": "commit", "code": code, "out": out or err})
    code, out, err = git("push")
    if code != 0 and ("no upstream" in (err or "").lower() or "set-upstream" in (err or "").lower()):
        code, out, err = git("push", "-u", "origin", "HEAD")   # 首次推送自动建 upstream
    steps.append({"step": "push", "code": code, "out": out or err})
    if code not in (0,):
        _STATE["push_error"] = f"推送失败：{_mask(err or out)[:220]}"
        sync_log("推送失败 · " + (err or out)[:400].replace("\n", " ／ "))
    else:
        _STATE["push_error"] = ""
        sync_log("推送成功 · " + (message or "sync"))
    ok = all(s["code"] in (0, 1) for s in steps)
    return {"ok": ok, "steps": steps, "at": iso(), "error": _STATE["push_error"]}

def test_git(body):
    """真正试一次 ls-remote（带凭据），成功才算配置通过。"""
    remote = (body.get("remote") or "").strip()
    user = (body.get("user") or "").strip()
    token = (body.get("token") or "").strip()
    if not remote:
        return {"ok": False, "detail": "请先填写仓库地址"}
    probe = remote
    if token and remote.startswith("https://"):
        host_path = remote[len("https://"):]
        probe = f"https://{urllib_quote(user or 'x')}:{urllib_quote(token)}@{host_path}"
    code, out, err = git("ls-remote", "--heads", probe, timeout=45)
    masked = (err or out).replace(token, "***") if token else (err or out)
    if code != 0:
        hint = ""
        low = masked.lower()
        if "could not read username" in low or "terminal prompts disabled" in low:
            hint = "（这个仓库需要凭据：请把 GitHub 用户名和 Personal Access Token 一起填上）"
        elif "authentication" in low or "403" in low or "invalid" in low:
            hint = "（凭据被拒：确认 token 有 repo 权限、且没有过期）"
        elif "not found" in low or "repository" in low and "not" in low:
            hint = "（仓库地址不对，或 token 无权访问这个私有仓库）"
        elif "could not resolve" in low or "timed out" in low:
            hint = "（网络连不上 GitHub）"
        return {"ok": False, "detail": (masked[:300] or "未知错误") + hint}
    branches = [l.split("\t")[-1] for l in out.splitlines() if l.strip()]
    return {"ok": True, "detail": "连接成功",
            "branches": branches[:10], "empty_repo": len(branches) == 0}


def urllib_quote(s):
    from urllib.parse import quote
    return quote(s, safe="")


_STATE = {"push_error": "", "last_pull": "", "remote_changed": False}


def git_history(collection, rid, limit=30):
    if not git_ready() or not collection or not rid:
        return {"ok": False, "entries": []}
    try:
        rel = str((coll_dir(collection) / f"{rid}.md").relative_to(ROOT))
    except Exception:
        return {"ok": False, "entries": []}
    code, out, err = git("log", f"-{limit}", "--date=format:%Y-%m-%d %H:%M",
                         "--pretty=%h\t%ad\t%an\t%s", "--", rel)
    if code != 0:
        return {"ok": False, "detail": err[:200], "entries": []}
    entries = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            entries.append({"hash": parts[0], "date": parts[1], "who": parts[2], "msg": parts[3]})
    return {"ok": True, "entries": entries, "file": rel}


def git_pull_bg():
    """后台拉取；有新提交就打标记，前端下次轮询会重新载入。"""
    if not git_ready():
        return
    code, out, err = git("rev-parse", "HEAD")
    before = out
    c2, o2, e2 = git("pull", "--rebase", "--autostash", timeout=90)
    _STATE["last_pull"] = iso()
    if c2 != 0:
        # 后台定时拉取同样不能把仓库丢在 rebase 半路：
        # 用户完全不知道刚才发生过什么，接下来的每一次保存都建立在坏状态上。
        if _rebase_in_progress():
            git("rebase", "--abort")
        _STATE["push_error"] = "拉取失败：" + _mask(e2 or o2)[:200]
        sync_log("拉取失败 · " + (e2 or o2)[:400].replace("\n", " ／ "))
        return
    code, after, _ = git("rev-parse", "HEAD")
    if after != before:
        _STATE["remote_changed"] = True


def git_status():
    if not git_ready():
        return {"repo": False}
    _, branch, _ = git("rev-parse", "--abbrev-ref", "HEAD")
    _, dirty, _ = git("status", "--porcelain")
    _, remote, _ = git("remote", "get-url", "origin")
    remote = re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", remote or "")
    _, last, _ = git("log", "-1", "--format=%h %ad %s", "--date=short")
    # 有没有真的推上去：只看提交数不够，得看本地领先上游多少。
    up_code, upstream, _ = git("rev-parse", "--abbrev-ref", "@{upstream}")
    ahead = 0
    if up_code == 0 and upstream:
        _, cnt, _ = git("rev-list", "--count", f"{upstream}..HEAD")
        try:
            ahead = int(cnt or 0)
        except ValueError:
            ahead = 0
    else:
        _, cnt, _ = git("rev-list", "--count", "HEAD")
        try:
            ahead = int(cnt or 0)
        except ValueError:
            ahead = 0
    return {"repo": True, "branch": branch, "dirty": len(dirty.splitlines()),
            "remote": remote, "last_commit": last,
            "upstream": upstream if up_code == 0 else "",
            "ahead": ahead,
            "never_pushed": up_code != 0,
            "log_tail": sync_tail(6)}


def sync_tail(n=20):
    try:
        return SYNC_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except Exception:
        return []

# ---------------------------------------------------------------- backups

def _backup_key(passphrase: str, salt: bytes, magic: bytes) -> bytes:
    """Derive a backup key with the strongest KDF available in this Python build.

    Some Apple-provided Python builds omit ``hashlib.scrypt`` even though the
    Python version itself is supported. SWCRYPT1 remains the scrypt format for
    backwards compatibility; SWCRYPT2 is the standard-library PBKDF2 fallback.
    """
    secret = passphrase.encode("utf-8")
    if magic == b"SWCRYPT1":
        if not hasattr(hashlib, "scrypt"):
            raise ValueError("这个 Python 缺少 scrypt，无法解开旧格式备份；请改用 python.org 或 Homebrew Python")
        return hashlib.scrypt(secret, salt=salt, n=2 ** 14, r=8, p=1, dklen=64)
    if magic == b"SWCRYPT2":
        return hashlib.pbkdf2_hmac("sha256", secret, salt, 240_000, dklen=64)
    raise ValueError("不是本工作台加密的备份")


def encrypt_blob(data: bytes, passphrase: str) -> bytes:
    """标准库实现的加密：口令派生密钥 → SHA256 计数器流异或 → HMAC 校验。
    格式：MAGIC(8) | salt(16) | nonce(16) | hmac(32) | ciphertext"""
    salt = os.urandom(16)
    nonce = os.urandom(16)
    magic = b"SWCRYPT1" if hasattr(hashlib, "scrypt") else b"SWCRYPT2"
    key = _backup_key(passphrase, salt, magic)
    ek, mk = key[:32], key[32:]
    out = bytearray()
    for i in range(0, len(data), 32):
        block = hashlib.sha256(ek + nonce + i.to_bytes(8, "big")).digest()
        chunk = data[i:i + 32]
        out += bytes(a ^ b for a, b in zip(chunk, block))
    ct = bytes(out)
    mac = hmac.new(mk, nonce + ct, hashlib.sha256).digest()
    return magic + salt + nonce + mac + ct


def decrypt_blob(blob: bytes, passphrase: str) -> bytes:
    if len(blob) < 72 or blob[:8] not in (b"SWCRYPT1", b"SWCRYPT2"):
        raise ValueError("不是本工作台加密的备份")
    magic = blob[:8]
    salt, nonce, mac, ct = blob[8:24], blob[24:40], blob[40:72], blob[72:]
    key = _backup_key(passphrase, salt, magic)
    ek, mk = key[:32], key[32:]
    if not hmac.compare_digest(hmac.new(mk, nonce + ct, hashlib.sha256).digest(), mac):
        raise ValueError("口令不对，或备份文件已损坏")
    out = bytearray()
    for i in range(0, len(ct), 32):
        block = hashlib.sha256(ek + nonce + i.to_bytes(8, "big")).digest()
        out += bytes(a ^ b for a, b in zip(ct[i:i + 32], block))
    return bytes(out)


def snapshot(kind="rolling"):
    dev = get_device()
    stamp = now_local().strftime("%Y-%m-%d_%H%M")
    name = f"workspace_{stamp}_{kind}.zip"
    if kind == "daily" and dev.get("onedrive_backup_dir"):
        outdir = Path(dev["onedrive_backup_dir"]).expanduser()
    else:
        outdir = LOCAL / "backups" / "rolling"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"ok": False, "detail": f"备份目录不可用: {e}"}
    target = outdir / name
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for base in (DATA, LOCAL / "life"):
                if not base.exists():
                    continue
                for p in base.rglob("*"):
                    if p.is_file():
                        z.write(p, str(p.relative_to(ROOT)))
    except Exception as e:
        return {"ok": False, "detail": str(e)}
    # 长期备份可选加密（口令只存本机 secrets，丢了就打不开）
    cfg = get_config()
    pw = (get_secrets().get("backup") or {}).get("passphrase", "")
    if kind == "daily" and cfg.get("security", {}).get("encrypt_backup") and pw:
        try:
            raw = target.read_bytes()
            enc = target.with_suffix(".zip.enc")
            enc.write_bytes(encrypt_blob(raw, pw))
            target.unlink()
            target = enc
        except Exception as e:
            return {"ok": False, "detail": f"加密失败：{e}"}
    if kind == "rolling":
        cutoff = time.time() - int(dev.get("rolling_keep_days", 7)) * 86400
        for old in outdir.glob("workspace_*_rolling.zip"):
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
            except Exception:
                pass
    return {"ok": True, "path": str(target), "kind": kind, "at": iso()}

def list_snapshots():
    out = []
    dev = get_device()
    dirs = [LOCAL / "backups" / "rolling"]
    if dev.get("onedrive_backup_dir"):
        dirs.append(Path(dev["onedrive_backup_dir"]).expanduser())
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(list(d.glob("workspace_*.zip")) + list(d.glob("workspace_*.zip.enc")), reverse=True):
            try:
                st = p.stat()
                out.append({"name": p.name, "path": str(p), "encrypted": p.suffix == ".enc",
                            "size_kb": round(st.st_size / 1024, 1),
                            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"),
                            "kind": "daily" if "_daily" in p.name else "rolling"})
            except Exception:
                pass
    return out[:200]

def backup_dirs():
    """备份只可能躺在这两个地方：本机的滚动备份目录，和用户自己指定的网盘目录。"""
    dev = get_device()
    dirs = [LOCAL / "backups" / "rolling", LOCAL / "backups"]
    if dev.get("onedrive_backup_dir"):
        try:
            dirs.append(Path(dev["onedrive_backup_dir"]).expanduser().resolve())
        except Exception:
            pass
    return dirs


def restore_snapshot(path):
    # 恢复 = 把一个 zip 解压覆盖到工作台目录里，**包括 server.py 和 app/ 下的脚本**。
    # 所以「解压哪个 zip」这件事本身就是最高权限的决定，绝不能由请求随便指定路径 ——
    # 否则任意一个能往磁盘上放文件的途径（下载、导入、同步）都能变成改代码。
    # 只认备份目录里、由我们自己写出去的那些 workspace_*.zip。
    p = Path(str(path or "")).expanduser()
    try:
        rp = p.resolve()
    except Exception:
        return {"ok": False, "detail": "路径无效"}
    if not (rp.name.startswith("workspace_")
            and (rp.name.endswith(".zip") or rp.name.endswith(".zip.enc"))
            and any(rp.parent == d.resolve() for d in backup_dirs() if d.exists())):
        return {"ok": False,
                "detail": "只能恢复备份目录里的工作台备份文件（workspace_*.zip）。"}
    p = rp
    if not p.is_file():
        return {"ok": False, "detail": "找不到该备份"}
    # 界面上明写了「当前状态会先自动另存一份，可以反悔」。
    # 那这份副本就必须真的存在 —— 存不下来（磁盘满、目录不可写）
    # 就该停在这里，而不是照样解压覆盖，然后让用户发现没得反悔。
    pre = snapshot("prerestore")
    if not pre.get("ok"):
        return {"ok": False, "detail": "没能先备份当前状态（" + str(pre.get("detail"))[:120]
                          + "），所以这次不恢复 —— 否则你就没有退路了。"}
    if p.suffix == ".enc":
        pw = (get_secrets().get("backup") or {}).get("passphrase", "")
        if not pw:
            return {"ok": False, "detail": "这是加密备份，但本机没有保存口令。请在设置里填入备份口令。"}
        try:
            tmp = LOCAL / "_restore_tmp.zip"
            tmp.write_bytes(decrypt_blob(p.read_bytes(), pw))
            p = tmp
        except Exception as e:
            return {"ok": False, "detail": str(e)}
    tmp_used = p.name == "_restore_tmp.zip"
    try:
        with zipfile.ZipFile(p) as z:
            # 备份里**只该有数据**（snapshot() 只打包 data/ 和 local/life/）。
            # 所以恢复也只往这两处写：既防 zip-slip，也防一个被动过手脚的 zip
            # 顺手把 server.py 或 app/js/*.js 换掉 —— 那等于下次启动就执行别人的代码。
            root = ROOT.resolve()
            allow = [(root / "data").resolve(), (root / "local" / "life").resolve()]
            members, bad = [], []
            for m in z.namelist():
                dest = (ROOT / m).resolve()
                if any(dest == a or a in dest.parents for a in allow):
                    members.append(m)
                else:
                    bad.append(m)
            if bad:
                return {"ok": False,
                        "detail": f"备份里有数据目录之外的文件，已整份拒绝：{bad[:3]}"}
            z.extractall(ROOT, members)
    except Exception as e:
        return {"ok": False, "detail": str(e)}
    finally:
        if tmp_used:
            try:
                p.unlink()
            except Exception:
                pass
    return {"ok": True, "restored": p.name, "safety_copy": pre.get("path")}

# ------------------------------------------------------------- spreadsheet

# 一次导入最多这么多行。不是嫌多，是因为每一行都会变成一个 .md 文件、
# 各带一次 fsync，而这一切都发生在**一个 HTTP 请求里**：
# 一个百万行的 csv 会让浏览器干等十几分钟，最后还超时。
# 到了上限就如实告诉用户截断了多少，别假装全导进去了。
MAX_TABLE_ROWS = 20000


def read_table(path):
    """读 csv/tsv/xlsx，返回 (headers, rows)。xlsx 用 zip+xml 解析，无需第三方库。"""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".csv", ".tsv", ".txt"):
        delim = "\t" if suffix == ".tsv" else ","
        rows = []
        with open(p, newline="", encoding="utf-8-sig", errors="replace") as f:
            for row in csv.reader(f, delimiter=delim):
                rows.append(row)
                if len(rows) > MAX_TABLE_ROWS:
                    break
        return (rows[0] if rows else []), rows[1:]
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(p)
    raise ValueError(f"不支持的表格类型: {suffix}")

def _col_index(ref):
    m = re.match(r"([A-Z]+)", ref or "")
    if not m:
        return 0
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _excel_date_styles(z):
    """Excel 把日期存成数字，靠单元格样式区分。这里把「日期格式」的样式号收集起来。"""
    out = set()
    try:
        xml = z.read("xl/styles.xml").decode("utf-8", "replace")
        custom = {int(i): f for i, f in
                  re.findall(r'<numFmt[^>]*numFmtId="(\d+)"[^>]*formatCode="([^"]*)"', xml)}
        builtin = set(range(14, 23)) | set(range(45, 48)) | {27, 30, 36, 50, 57}
        body = re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", xml, re.S)
        if not body:
            return out
        for i, xf in enumerate(re.findall(r"<xf[^>]*/?>", body.group(1))):
            m = re.search(r'numFmtId="(\d+)"', xf)
            if not m:
                continue
            fid = int(m.group(1))
            code = custom.get(fid, "")
            if fid in builtin or re.search(r"[yYdD]", code) and "[" not in code:
                out.add(i)
    except Exception:
        pass
    return out


def _looks_like_excel_date(attrs, val, date_styles):
    m = re.search(r's="(\d+)"', attrs)
    if not m or int(m.group(1)) not in date_styles:
        return False
    try:
        f = float(val)
    except Exception:
        return False
    return 20000 < f < 80000          # 大约 1954–2119 年，别把普通数字误判成日期


def _excel_serial_to_date(val):
    try:
        n = float(val)
    except Exception:
        return val
    # Excel 的 1900 闰年历史 bug：序列号 60 是不存在的 1900-02-29
    base = datetime(1899, 12, 30)
    try:
        d = base + timedelta(days=n)
        return d.strftime("%Y-%m-%d") if d.hour == 0 and d.minute == 0 else d.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return val


def _read_xlsx(p):
    with zipfile.ZipFile(p) as z:
        date_styles = _excel_date_styles(z)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            for si in re.findall(r"<si>(.*?)</si>", xml, re.S):
                shared.append("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
        # 取「工作簿里的第一张表」，不是文件名排序的第一个 ——
        # sheet1.xml 未必是用户看到的第一张，sorted() 还会把 sheet10 排到 sheet2 前面
        target = None
        try:
            wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
            rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
            rid = dict(re.findall(r'Id="([^"]+)"[^>]*?Target="([^"]+)"', rels))
            first = re.search(r'<sheet[^>]*r:id="([^"]+)"', wb)
            if first and first.group(1) in rid:
                cand = "xl/" + rid[first.group(1)].lstrip("/")
                if cand in z.namelist():
                    target = cand
        except Exception:
            pass
        if not target:
            sheets = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)]
            if not sheets:
                return [], []
            target = sorted(sheets, key=lambda n: int(re.search(r"(\d+)", n).group(1)))[0]
        xml = z.read(target).decode("utf-8", "replace")
    rows = []
    for row_xml in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
        cells = {}
        # 关键：空单元格写成自闭合的 <c r="A2" s="14"/>。
        # 以前的正则不认自闭合，会把下一个单元格整个吞进来，
        # 于是整行左移一格、共享字符串索引被当成数字原样吐出（表就全乱了）。
        for m in re.finditer(r"<c([^>]*?)(?:/>|>(.*?)</c>)", row_xml, re.S):
            attrs, inner = m.group(1), m.group(2) or ""
            ref = re.search(r'r="([A-Z]+\d+)"', attrs)
            typ = re.search(r't="(\w+)"', attrs)
            v = re.search(r"<v>(.*?)</v>", inner, re.S)
            t = re.search(r"<t[^>]*>(.*?)</t>", inner, re.S)
            val = ""
            kind = typ.group(1) if typ else ""
            if kind == "s" and v:
                idx = int(v.group(1))
                val = shared[idx] if idx < len(shared) else ""
            elif kind == "inlineStr" and t:
                val = t.group(1)
            elif t:
                val = t.group(1)
            elif v:
                val = v.group(1)
                if kind not in ("str", "e") and _looks_like_excel_date(attrs, val, date_styles):
                    val = _excel_serial_to_date(val)
            val = html.unescape(val)
            cells[_col_index(ref.group(1) if ref else "A1")] = val
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    if not rows:
        return [], []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    return rows[0], rows[1:]


# 表格导入：按列名猜字段。用户的表五花八门，全靠他自己一个个对太累了。
FIELD_GUESS = {
    "conferences": [
        (r"conference\s*name|会议名称|会议|name$|title", "title"),
        (r"cfp\s*close|deadline|截止|投稿截止|due", "deadline"),
        (r"conference\s*date|会议日期|dates?$|举办时间", "meeting_date"),
        (r"location|地点|城市|city|venue", "location"),
        (r"info\s*link|网址|链接|url|website", "link"),
        (r"submission\s*link|投稿链接|submission", "submit_link"),
        (r"notification|通知日期|结果", "notify_date"),
        (r"fee|费用", "fee"),
        (r"funding|资助|support|报销", "funding"),
        (r"status|状态", "status_note"),
        (r"note|备注|说明|comment", "body"),
        (r"cfp\s*open|开放", "cfp_open"),
    ],
    "manuscripts": [
        (r"title|题目|标题|论文", "title"),
        (r"journal|期刊|投向", "current_journal"),
        (r"stage|阶段|状态", "stage_note"),
        (r"coauthor|合作者|author", "coauthors"),
        (r"next|下一步|todo", "next_action"),
        (r"due|截止|deadline", "next_action_due"),
        (r"note|备注", "body"),
    ],
    "published": [
        (r"title|题目|标题", "title"),
        (r"journal|期刊", "journal"),
        (r"year|年份|发表年", "year"),
        (r"doi", "doi"),
        (r"author|作者", "authors"),
        (r"note|备注", "body"),
    ],
    "reading": [
        (r"title|题目|标题|paper", "title"),
        (r"author|作者", "authors"),
        (r"journal|期刊", "journal"),
        (r"year|年份", "year"),
        (r"doi", "doi"),
        (r"question|问题|背景", "question"),
        (r"method|方法", "method"),
        (r"finding|结论|结果", "findings"),
        (r"note|备注|摘要|abstract", "body"),
    ],
}


def guess_mapping(headers, collection):
    """返回 {列名: 猜出来的字段}。猜不出的留空，由用户自己选。"""
    out, used = {}, set()
    for h in headers:
        low = str(h or "").strip().lower()
        if not low:
            continue
        for pat, field in FIELD_GUESS.get(collection, []):
            if field in used:
                continue
            if re.search(pat, low, re.I):
                out[h] = field
                used.add(field)
                break
    return out


def import_table(path, collection, mapping=None, dedup_key=None):
    """mapping: {列名 -> 字段名}；不给则用列名本身（先搭框架，字段随后再对）。"""
    headers, rows = read_table(path)
    truncated = len(rows) >= MAX_TABLE_ROWS
    rows = rows[:MAX_TABLE_ROWS]
    existing = list_records(collection)
    by_key = {}
    if dedup_key:
        for r in existing:
            k = str(r.get(dedup_key, "")).strip().lower()
            if k:
                by_key[k] = r
    created = updated = skipped = 0
    for row in rows:
        rec = {}
        for i, h in enumerate(headers):
            field = str((mapping or {}).get(h, h) or "").strip()
            if not field or field == "-" or i >= len(row) or field in RESERVED_FIELDS:
                continue
            val = row[i]
            if str(val).strip() != "":
                rec[field] = val
        if not rec:
            continue
        title = str(rec.get("title") or rec.get("name") or rec.get("Title") or "").strip()
        if not title:
            skipped += 1          # 没标题的行多半是空行或分隔行，不要造一堆「（未命名）」
            continue
        rec["title"] = title
        rec["source_import"] = Path(path).name
        key = str(rec.get(dedup_key, "")).strip().lower() if dedup_key else ""
        if key and key in by_key:
            old = by_key[key]
            merged = dict(old)
            merged.update(rec)
            merged["id"] = old["id"]
            write_record(collection, merged)
            updated += 1
        else:
            write_record(collection, rec)
            created += 1
    out = {"ok": True, "headers": headers, "rows": len(rows), "skipped": skipped,
           "created": created, "updated": updated, "collection": collection}
    if truncated:
        out["truncated"] = MAX_TABLE_ROWS
        out["note"] = (f"这张表太大，这次只导了前 {MAX_TABLE_ROWS} 行。"
                       "剩下的请拆成几个文件再导 —— 一次请求跑不完那么多。")
    return out


# ------------------------------------------------------- Overleaf 写作进展
# 付费版 Overleaf 提供 Git 接入：每个项目有一个 git 地址，
# 用你的 Overleaf 邮箱当用户名、Git token 当密码就能 clone。
# 我们把项目 clone 到 local/overleaf/（只在本机，不进你的工作台仓库），
# 每次同步比对上次的提交，算出「今天改了什么」，写成一条进展记录。

OVERLEAF_DIR = LOCAL / "overleaf"


def overleaf_creds():
    o = (get_secrets().get("overleaf") or {})
    return (o.get("email") or "").strip(), (o.get("token") or "").strip()


def overleaf_repo_url(raw):
    """把用户填的东西统一成一个可 clone 的地址。
    支持三种写法：完整 git 地址、项目页地址、光一个项目 id。"""
    raw = str(raw or "").strip()
    if not raw:
        return ""
    m = re.search(r"([0-9a-f]{24})", raw)
    pid = m.group(1) if m else ""
    if raw.startswith("https://git.overleaf.com/"):
        return raw
    if pid:
        return "https://git.overleaf.com/" + pid
    return ""


def _ol_git(repo, *args, timeout=180):
    email, token = overleaf_creds()
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo")
    try:
        r = subprocess.run(["git"] + list(args), cwd=str(repo) if repo else str(ROOT),
                           capture_output=True, text=True, timeout=timeout, env=env)
        out, err = (r.stdout or "").strip(), (r.stderr or "").strip()
        if token:                       # 日志里绝不能留 token
            out, err = out.replace(token, "***"), err.replace(token, "***")
        return r.returncode, out, err
    except Exception as e:
        return 1, "", str(e)[:200]


def _ol_auth_url(url, user=None):
    email, token = overleaf_creds()
    if not token or not url.startswith("https://"):
        return url
    u = urllib_quote(user if user is not None else (email or "git"))
    return "https://" + u + ":" + urllib_quote(token) + "@" + url[len("https://"):]


def _ol_fetch(repo, repo_url, first_time):
    """clone 或 pull。Overleaf 对用户名的要求各账号不一：有的要邮箱，有的要 git。
    认证失败就换另一种再试一次，省得让人来回猜。"""
    email, _ = overleaf_creds()
    tries = [email, "git"] if email else ["git"]
    last = ""
    for user in tries:
        auth = _ol_auth_url(repo_url, user)
        if first_time:
            code, out, err = _ol_git(None, "clone", "--quiet", auth, str(repo))
        else:
            code, out, err = _ol_git(repo, "pull", "--quiet", auth)
        if code == 0:
            return True, ""
        last = err or out
        if "authentication" not in (last or "").lower() and "401" not in (last or ""):
            break                      # 不是认证问题，换用户名也没用
        shutil.rmtree(repo, ignore_errors=True) if first_time else None
    return False, last


def _tex_wordcount(text):
    """粗略但稳定的正文字数：去注释、去命令、去数学环境，再分别数英文词与中文字。"""
    t = re.sub(r"(?<!\\)%.*", "", text)
    t = re.sub(r"\\begin\{(equation|align|figure|table|tabular|lstlisting|verbatim)\*?\}.*?"
               r"\\end\{\1\*?\}", " ", t, flags=re.S)
    t = re.sub(r"\$\$.*?\$\$", " ", t, flags=re.S)
    t = re.sub(r"\$[^$]*\$", " ", t)
    t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
    t = re.sub(r"[{}\\]", " ", t)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    words = len(re.findall(r"[A-Za-z][A-Za-z'-]*", t))
    return words, cjk


def _tex_sections(text):
    return [m.group(2).strip() for m in
            re.finditer(r"\\(section|subsection)\*?\{([^}]{1,80})\}", text)]


def overleaf_sync(manuscript_id=None, url=None, quiet=True):
    """同步一个 Overleaf 项目，返回这次的进展。不写记录，只算数。"""
    email, token = overleaf_creds()
    if not token:
        return {"ok": False, "detail": "还没填 Overleaf 的 Git token（设置 → 研究 → Overleaf）"}
    rec = read_record("manuscripts", manuscript_id) if manuscript_id else None
    raw = url or (rec or {}).get("overleaf_url") or (rec or {}).get("overleaf") or ""
    repo_url = overleaf_repo_url(raw)
    if not repo_url:
        return {"ok": False, "detail": "Overleaf 地址填得不对，应该形如 "
                                       "https://www.overleaf.com/project/xxxxxxxx 或直接给项目 id"}
    pid = repo_url.rstrip("/").split("/")[-1]
    OVERLEAF_DIR.mkdir(parents=True, exist_ok=True)
    repo = OVERLEAF_DIR / pid
    if not (repo / ".git").exists():
        ok, err = _ol_fetch(repo, repo_url, True)
        if not ok:
            return {"ok": False, "detail": _overleaf_err(err)}
        before = None
    else:
        code, before, _ = _ol_git(repo, "rev-parse", "HEAD")
        before = before or None
        ok, err = _ol_fetch(repo, repo_url, False)
        if not ok:
            return {"ok": False, "detail": _overleaf_err(err)}
    code, after, _ = _ol_git(repo, "rev-parse", "HEAD")
    # 这次拉下来有哪些提交
    commits = []
    if before and after and before != after:
        _, log, _ = _ol_git(repo, "log", "--pretty=%h\t%an\t%ad\t%s",
                            "--date=format:%Y-%m-%d %H:%M", f"{before}..{after}")
        for line in (log or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 4:
                commits.append({"hash": parts[0], "author": parts[1],
                                "at": parts[2], "msg": parts[3]})
    # 改了哪些文件、净增删多少行
    files, added, removed = [], 0, 0
    if before and after and before != after:
        _, stat, _ = _ol_git(repo, "diff", "--numstat", before, after)
        for line in (stat or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                a = int(parts[0]) if parts[0].isdigit() else 0
                d = int(parts[1]) if parts[1].isdigit() else 0
                added += a; removed += d
                files.append({"path": parts[2], "add": a, "del": d})
    # 当前正文体量与结构
    words = cjk = 0
    sections = []
    for f in sorted(repo.rglob("*.tex")):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        w, c = _tex_wordcount(txt)
        words += w; cjk += c
        sections += _tex_sections(txt)
    touched = [f["path"] for f in sorted(files, key=lambda x: -(x["add"] + x["del"]))][:6]
    return {"ok": True, "project": pid, "url": repo_url, "repo": str(repo),
            "first_time": before is None, "changed": bool(commits or files),
            "commits": commits, "files": files, "touched": touched,
            "added": added, "removed": removed, "net": added - removed,
            "words": words, "cjk": cjk, "sections": sections[:40],
            "at": iso()}


def local_tex_sync(manuscript_id=None, folder=None):
    """本地 LaTeX 目录的写作进展 —— 给不用付费 Overleaf 的人。

    Overleaf 的 Git 接入是付费功能，但「今天改了哪几节、净增多少行」
    这件事跟 Overleaf 一点关系都没有：只要那个目录是个 git 仓库，
    同样的算法就能跑。没接付费版的人不该因此完全没有写作进展。

    跟 Overleaf 版的区别只有一个：不 clone、不 fetch，直接读本地仓库，
    比较「上次记录的 commit」和「现在的 HEAD」。
    """
    rec = read_record("manuscripts", manuscript_id) if manuscript_id else None
    raw = folder or (rec or {}).get("tex_folder") or (rec or {}).get("folder") or ""
    if not raw:
        return {"ok": False, "detail": "这篇稿件还没填「本地 LaTeX 目录」"}
    repo = Path(os.path.expanduser(str(raw)))
    if not repo.exists():
        return {"ok": False, "detail": f"目录不存在：{repo}"}
    if not (repo / ".git").exists():
        return {"ok": False, "detail":
                f"{repo} 不是一个 git 仓库。在那个目录里执行一次 "
                "`git init && git add -A && git commit -m 初始` 就能开始记录进展了。"}
    pid = "local-" + re.sub(r"\W+", "-", repo.name).strip("-").lower()[:40]
    code, after, _ = _ol_git(repo, "rev-parse", "HEAD")
    after = (after or "").strip()
    if not after:
        return {"ok": False, "detail": "这个仓库还没有任何提交"}
    # 上次记到哪了
    before, before_date = "", ""
    for r0 in list_records("progress"):
        if r0.get("project") == pid and r0.get("head"):
            if not before or str(r0.get("date", "")) > before_date:
                before, before_date = r0["head"], str(r0.get("date", ""))
    commits, files, added, removed = [], [], 0, 0
    if before and before != after:
        _, log, _ = _ol_git(repo, "log", "--pretty=%h\t%an\t%ad\t%s",
                            "--date=format:%Y-%m-%d %H:%M", f"{before}..{after}")
        for line in (log or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 4:
                commits.append({"hash": parts[0], "author": parts[1],
                                "at": parts[2], "msg": parts[3]})
        _, stat, _ = _ol_git(repo, "diff", "--numstat", before, after)
        for line in (stat or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                a = int(parts[0]) if parts[0].isdigit() else 0
                d = int(parts[1]) if parts[1].isdigit() else 0
                added += a; removed += d
                files.append({"path": parts[2], "add": a, "del": d})
    words = cjk = 0
    sections = []
    for f in sorted(repo.rglob("*.tex")):
        if ".git" in f.parts:
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        w, c = _tex_wordcount(txt)
        words += w; cjk += c
        sections += _tex_sections(txt)
    touched = [f["path"] for f in sorted(files, key=lambda x: -(x["add"] + x["del"]))][:6]
    return {"ok": True, "project": pid, "url": str(repo), "repo": str(repo),
            "kind": "local-tex", "head": after,
            "first_time": not before, "changed": bool(commits or files),
            "commits": commits, "files": files, "touched": touched,
            "added": added, "removed": removed, "net": added - removed,
            "words": words, "cjk": cjk, "sections": sections[:40], "at": iso()}


def _overleaf_err(msg):
    m = (msg or "").lower()
    if "authentication failed" in m or "401" in m:
        return "认证没过：检查 Overleaf 邮箱和 Git token（token 在 Overleaf 账号设置 → Git Integration 里生成）"
    if "403" in m:
        return "没权限：这个 token 可能不能访问该项目，或者项目 id 抄错了"
    if "not found" in m or "404" in m:
        return "项目找不到：确认地址里的项目 id 对不对"
    if "could not resolve host" in m or "timed out" in m:
        return "连不上 git.overleaf.com：检查网络或代理"
    return (msg or "同步失败")[:200]


def overleaf_record(manuscript_id, res):
    """把一次同步的结果写成当天的进展记录（同一天同一项目只留一条，累加）。"""
    if not res.get("ok"):
        return None
    day = today_str()
    rid = f"progress-{res['project']}-{day}"
    old = read_record("progress", rid) or {}
    rec = {
        "id": rid, "date": day, "kind": "overleaf",
        "manuscript": manuscript_id or old.get("manuscript") or "",
        "project": res["project"], "url": res["url"],
        "title": (read_record("manuscripts", manuscript_id) or {}).get("title", "")
                 if manuscript_id else old.get("title") or res["project"],
        "added": int(old.get("added") or 0) + res["added"],
        "removed": int(old.get("removed") or 0) + res["removed"],
        "commits": int(old.get("commits") or 0) + len(res["commits"]),
        "words": res["words"], "cjk": res["cjk"],
        "head": res.get("head") or old.get("head") or "",
        "kind2": res.get("kind") or "overleaf",
        "touched": sorted(set(list(old.get("touched") or []) + res["touched"]))[:8],
        "messages": (list(old.get("messages") or []) +
                     [c["msg"] for c in res["commits"] if c.get("msg")])[-12:],
        "synced_at": res["at"],
    }
    if not res["changed"] and not old:
        rec["note"] = "首次接入，记下当前体量作为基线"
    return write_record("progress", rec)


def overleaf_sync_all():
    """把所有填了 Overleaf 地址的稿件同步一遍。调度器每天叫它。"""
    out = []
    for m in list_records("manuscripts"):
        if not ((m.get("overleaf_url") or m.get("overleaf") or "").strip()):
            continue
        r = _safe(lambda: overleaf_sync(m["id"]), {"ok": False, "detail": "同步异常"})
        if r.get("ok"):
            overleaf_record(m["id"], r)
        out.append({"manuscript": m["id"], "title": m.get("title", ""),
                    "ok": r.get("ok"), "detail": r.get("detail", ""),
                    "net": r.get("net"), "commits": len(r.get("commits") or [])})
    return out


# --------------------------------------------------------------- scheduler

class Scheduler(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__()
        self.last_rolling = 0
        self.done_daily = set()

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:
                sys.stderr.write(f"[scheduler] {e}\n")
            time.sleep(60)

    def tick(self):
        dev = get_device()
        now = now_local()
        # 滚动快照
        gap = int(dev.get("rolling_minutes", 30)) * 60
        if time.time() - self.last_rolling > gap:
            snapshot("rolling")
            self.last_rolling = time.time()
        # 每日备份（错过则补做）
        for hhmm in dev.get("daily_backup_times", []):
            tag = f"{now:%Y-%m-%d}-{hhmm}"
            if tag in self.done_daily:
                continue
            try:
                h, m = [int(x) for x in hhmm.split(":")]
            except Exception:
                continue
            due = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if now >= due:
                snapshot("daily")
                if git_ready():
                    git_sync(f"daily backup {tag}")
                self.done_daily.add(tag)
        if len(self.done_daily) > 40:
            self.done_daily = set(list(self.done_daily)[-20:])
        # 周一早报：到点自动生成并推送（错过则当天补做一次）
        try:
            cfg = get_config()
            cron = (cfg.get("push") or {}).get("weekly_cron", "MON 08:00")
            parts = cron.split()
            wd_map = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
            wd = wd_map.get(parts[0].upper(), 0)
            hh, mm = (parts[1] if len(parts) > 1 else "08:00").split(":")
            due = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            tag = f"weekly-{now:%G-W%V}"
            if now.weekday() >= wd and (now.weekday() > wd or now >= due) \
                    and tag not in self.done_daily and not already_done(tag):
                self.done_daily.add(tag)
                mark_done(tag)
                def run_weekly():
                    # 先抓雷达再写周报。顺序不能反 ——
                    # 周报要用到这次抓回来的候选，反了就永远在用上周的。
                    try:
                        if (get_config().get("radar") or {}).get("keywords") or \
                                (get_config().get("radar") or {}).get("people"):
                            subprocess.run([sys.executable, "scripts/radar.py"],
                                           cwd=str(ROOT), capture_output=True, timeout=300)
                    except Exception:
                        pass          # 雷达抓不到不能拖累周报
                    try:
                        subprocess.run([sys.executable, "scripts/journal.py", "--render", "--push"],
                                       cwd=str(ROOT), capture_output=True, timeout=180)
                    except Exception:
                        pass
                threading.Thread(target=run_weekly, daemon=True).start()
        except Exception:
            pass
        # 每 5 分钟后台拉一次，避免两台机器互相覆盖
        if git_ready() and time.time() - getattr(self, "_last_pull", 0) > 300:
            self._last_pull = time.time()
            try:
                git_pull_bg()
            except Exception:
                pass
        # 每 10 分钟写一次在线心跳（文件名按设备区分，两台机器不会打架）
        if time.time() - getattr(self, "_last_presence", 0) > 600:
            self._last_presence = time.time()
            try:
                write_presence(SERVE_PORT)
            except Exception:
                pass
        # 每 30 分钟收一次邮件（手机随手记的通道）
        try:
            inb = (get_secrets().get("push") or {}).get("inbox") or {}
            if inb.get("enabled") and time.time() - getattr(self, "_last_mail", 0) > 1800:
                self._last_mail = time.time()
                threading.Thread(target=lambda: _safe(mail_intake, None), daemon=True).start()
        except Exception:
            pass
        # 每天同步一次 Overleaf，把写作进展记下来
        otag = f"overleaf-{now:%Y-%m-%d}"
        if now.hour >= 8 and otag not in self.done_daily and not already_done(otag):
            self.done_daily.add(otag)
            mark_done(otag)
            threading.Thread(target=lambda: _safe(overleaf_sync_all, []), daemon=True).start()
        # 每天生成一次只读简报（两台电脑都关机时手机还能看）
        tag = f"digest-{now:%Y-%m-%d}"
        if now.hour >= 7 and tag not in self.done_daily and not already_done(tag):
            self.done_daily.add(tag)
            mark_done(tag)
            try:
                build_digest()
                build_portal()
            except Exception:
                pass
        # 每周结算
        quota_settle(get_quota())
        # 刷新自动任务队列建议（供云端 Claude 读取）
        try:
            plan = pick_tasks()
            _save_json(CLAUDE / "next-run.json",
                       {"generated": iso(), "timezone": str(now.tzinfo), **plan})
        except Exception:
            pass

# ----------------------------------------------------- 远程访问与安全（阶段 11）
# 原则：本机怎么用都行；一旦是从别的设备连进来，必须先输访问码，
# 而且默认只读——想改东西要再解锁一次。所有失败尝试都记在案。

SESSIONS = {}                  # token -> {"ip":.., "until":.., "write_until":.., "ua":..}
LOGIN_FAILS = {}               # ip -> [失败时间, ...]
_SEC_LOCK = threading.Lock()
SESSION_HOURS = 12             # 一次登录管半天
WRITE_MINUTES = 30             # 解锁写入后 30 分钟自动回到只读
MAX_FAILS = 5                  # 15 分钟内错 5 次就锁 15 分钟
FAIL_WINDOW = 900
SERVE_PORT = 8765               # 实际监听端口，心跳与入口页要用


def security_log(event, ip, detail=""):
    """安全事件写在本机，不进 git、不进备份。"""
    try:
        p = LOCAL / "security.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(f"{iso()}\t{event}\t{ip}\t{detail}\n")
    except Exception:
        pass


def is_local_addr(ip):
    return ip in ("127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1")


def _fails(ip):
    """读一遍失败记录并顺手清掉过期的。**必须持锁调用。**

    这里是「读整个列表 → 过滤 → 整份写回」。不加锁的话，50 个并发的错误尝试
    会各自拿到同一份旧列表再各自写回，计数几乎不增长，
    15 分钟锁定于是永远不触发 —— 四位访问码就能被暴力枚举。
    """
    now = time.time()
    xs = [t for t in LOGIN_FAILS.get(ip, []) if now - t < FAIL_WINDOW]
    LOGIN_FAILS[ip] = xs
    return xs


def note_fail(ip):
    """记一次失败，返回窗口内的累计次数。"""
    with _SEC_LOCK:
        LOGIN_FAILS.setdefault(ip, []).append(time.time())
        return len(_fails(ip))


def locked_out(ip):
    with _SEC_LOCK:
        xs = _fails(ip)
        if len(xs) < MAX_FAILS:
            return 0
        return int(FAIL_WINDOW - (time.time() - xs[-MAX_FAILS]))


def check_access_code(code):
    want = ((get_secrets().get("remote") or {}).get("access_code") or "").strip()
    if not want:
        return False
    # 必须转成 bytes 再比：compare_digest 不支持含中文的字符串，
    # 而访问码很可能就是中文——直接比会抛异常，login 变成 500，锁定计数也不会累加
    return hmac.compare_digest(str(code or "").strip().encode("utf-8"), want.encode("utf-8"))


def new_session(ip, ua, writable=False):
    tok = base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip("=")
    with _SEC_LOCK:
        SESSIONS[tok] = {"ip": ip, "ua": (ua or "")[:120],
                         "until": time.time() + SESSION_HOURS * 3600,
                         "write_until": time.time() + WRITE_MINUTES * 60 if writable else 0,
                         "since": iso()}
        for t, s in list(SESSIONS.items()):        # 顺手清掉过期的
            if s["until"] < time.time():
                SESSIONS.pop(t, None)
    return tok


def get_session(tok):
    with _SEC_LOCK:
        s = SESSIONS.get(tok or "")
        if not s:
            return None
        if s["until"] < time.time():
            SESSIONS.pop(tok, None)
            return None
        return s


# 这些接口在没登录时也要能访问，否则登录页自己都打不开
OPEN_ROUTES = {"auth/status", "auth/login", "auth/unlock", "ping"}
# 远程即使解锁了也永远不许碰的：密钥、Git 凭据、任意路径读写、跑脚本
REMOTE_FORBIDDEN = ("secrets", "git", "run/", "file", "tree", "mkdir", "checkdir", "ai/", "overleaf/", "mail/",
                    "restore", "backup", "scan/pdfs", "table/", "security/log",
                    "portal/build", "digest/build", "library/zotero", "library/file",
                    "library/clear", "claude/outbox", "test/ics", "radar/submit",
                    "tex/sync")
# 手机速记（/jot.html）是**只追加**的：只会新建一条想法，改不了也删不了任何东西。
# 它正是给手机准备的功能，如果被「远程默认只读」挡住就等于没做。
# 所以放它过只读闸——但访问码那一关照样要过。
READONLY_EXEMPT = {"capture"}


# ------------------------------------------------------ 设备在线状态（阶段 10）

def lan_addresses(port):
    """本机在局域网里的地址，给手机/另一台电脑用。"""
    urls, seen = [], set()
    try:
        host = socket.gethostname()
        for cand in {host, host.split(".")[0] + ".local"}:
            if cand and cand not in seen:
                seen.add(cand)
                urls.append(f"http://{cand}:{port}/")
    except Exception:
        pass
    for fam, probe in ((socket.AF_INET, ("8.8.8.8", 80)),):
        s = socket.socket(fam, socket.SOCK_DGRAM)
        try:
            s.connect(probe)                       # 不真的发包，只为拿到出口网卡的地址
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127.") and ip not in seen:
                seen.add(ip)
                urls.insert(0, f"http://{ip}:{port}/")
        except Exception:
            pass
        finally:
            s.close()
    return urls


def presence_dir():
    d = DATA / "presence"
    d.mkdir(parents=True, exist_ok=True)
    return d


def device_id():
    did = (get_device() or {}).get("device_id")
    if did:
        return did
    with json_txn(DEVICE_PATH, DEFAULT_DEVICE) as dev:
        did = dev.get("device_id")
        if not did:
            did = "dev-" + hashlib.sha256(
                (socket.gethostname() + str(ROOT)).encode("utf-8")).hexdigest()[:10]
            dev["device_id"] = did
    return did


def write_presence(port):
    """每台机器只写自己那一份，文件名各不相同，所以两台机器不会打架。"""
    dev = get_device()
    p = presence_dir() / f"{device_id()}.json"
    _save_json(p, {
        "device_id": device_id(),
        "name": dev.get("device_name") or socket.gethostname(),
        "os": sys.platform,
        "port": port,
        "urls": lan_addresses(port),
        "version": VERSION,
        "seen": iso(),
    })


def list_peers():
    """所有见过的设备 + 在线判断。10 分钟内有心跳算在线；
    因为心跳是靠 git 同步过来的，另一台机器的时间戳天然会晚几分钟，这里放宽到 20 分钟。"""
    me, out = device_id(), []
    now = datetime.now(timezone.utc)
    for f in sorted(presence_dir().glob("*.json")):
        d = _load_json(f, {})
        if not isinstance(d, dict) or not d.get("device_id"):
            continue
        try:
            seen = datetime.fromisoformat(str(d.get("seen"))).astimezone(timezone.utc)
            mins = (now - seen).total_seconds() / 60
        except Exception:
            mins = 1e9
        d["is_me"] = d["device_id"] == me
        d["minutes_ago"] = round(mins, 1) if mins < 1e8 else None
        d["state"] = ("本机" if d["is_me"] else
                      "在线" if mins <= 20 else
                      "最近在线" if mins <= 60 * 24 else "离线")
        out.append(d)
    out.sort(key=lambda x: (not x["is_me"], x.get("minutes_ago") if x.get("minutes_ago") is not None else 1e9))
    return out


PORTAL_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>学术工作台 · 入口</title><style>
:root{color-scheme:light dark}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
background:#f6f7f9;color:#1b1d21;padding:24px;max-width:520px;margin:0 auto}
@media (prefers-color-scheme:dark){body{background:#14171d;color:#e6e8ec}.card{background:#1b1f27!important;border-color:#2a3039!important}}
h1{font-size:19px;margin:0 0 4px}.sub{color:#7a828e;font-size:13px;margin-bottom:18px}
.card{display:block;background:#fff;border:1px solid #e3e6ea;border-radius:12px;padding:14px 16px;
margin-bottom:10px;text-decoration:none;color:inherit}
.card b{display:block;font-size:15px}.card small{color:#7a828e}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:#c3c8cf}
.dot.ok{background:#2f9e44}.dot.no{background:#c3c8cf}
.busy{color:#7a828e;font-size:13px}
</style></head><body>
<h1>学术工作台</h1><div class="sub">正在找哪台机器开着…（__BUILT__ 生成）</div>
<div id="list"></div>
<div class="busy" id="tip">如果两台都显示离线：确认那台电脑开着、工作台在运行，而且手机和它在同一个网络（或都连着同一个 VPN）。</div>
<script>
const CANDIDATES = __CANDS__;
const list = document.getElementById('list');
function card(c, state, note){
  const a = document.createElement('a');
  a.className = 'card'; a.href = state === 'ok' ? c.url : 'javascript:void(0)';
  a.innerHTML = '<b><span class="dot ' + (state === 'ok' ? 'ok' : 'no') + '"></span>' +
    c.name + '</b><small>' + (note || c.url) + '</small>';
  return a;
}
async function probe(c){
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 2500);
  try{
    const r = await fetch(c.url + 'api/ping', {signal: ctl.signal, credentials: 'omit'});
    clearTimeout(t);
    if(!r.ok) return null;
    return await r.json();
  }catch(e){ clearTimeout(t); return null; }
}
(async () => {
  const results = await Promise.all(CANDIDATES.map(async c => [c, await probe(c)]));
  list.innerHTML = '';
  const live = results.filter(([, r]) => r);
  results.forEach(([c, r]) => list.appendChild(
    card(c, r ? 'ok' : 'no', r ? ('在线 · v' + r.version + ' · 点这里进入') : '连不上')));
  if(live.length === 1){ location.href = live[0][0].url; }
  else if(live.length > 1){ document.getElementById('tip').textContent = '两台都在线，挑一台点进去。'; }
})();
</script></body></html>"""


def portal_candidates():
    cands = []
    for p in list_peers():
        for u in (p.get("urls") or []):
            cands.append({"name": p.get("name") or p.get("device_id"), "url": u})
    seen, out = set(), []
    for c in cands:
        if c["url"] not in seen:
            seen.add(c["url"])
            out.append(c)
    return out


def build_portal(target_dir=""):
    """生成手机入口页：挨个探测哪台电脑开着，只有一台在线就直接跳过去。"""
    cands = portal_candidates()
    if not cands:
        return {"ok": False, "detail": "还没有任何设备的地址记录，先在每台电脑上跑一次工作台"}
    html = (PORTAL_HTML
            .replace("__CANDS__", json.dumps(cands, ensure_ascii=False))
            .replace("__BUILT__", datetime.now().strftime("%Y-%m-%d %H:%M")))
    written = []
    local = ROOT / "portal.html"
    atomic_write_text(local, html)
    written.append(str(local))
    d = (target_dir or get_device().get("onedrive_backup_dir") or "").strip()
    if d and not d.startswith(("http://", "https://")):
        try:
            p = Path(d).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            atomic_write_text(p / "工作台入口.html", html)
            written.append(str(p / "工作台入口.html"))
        except Exception as e:
            return {"ok": True, "written": written, "detail": f"OneDrive 目录写入失败：{e}"}
    return {"ok": True, "written": written, "candidates": cands,
            "detail": "入口页已生成" + ("，并已放进 OneDrive 目录" if len(written) > 1 else "")}


def build_digest(target_dir=""):
    """两台电脑都关机时的兜底：一份纯静态的只读简报，手机在 OneDrive 里就能看。"""
    cfg = get_config()
    today = today_str()
    ms = [m for m in list_records("manuscripts") if m.get("stage") not in ("published", "shelved")]
    confs = sorted([c for c in list_records("conferences") if c.get("deadline")],
                   key=lambda c: str(c.get("deadline")))[:6]
    sched = [s for s in list_records("schedule") if str(s.get("date", ""))[:10] >= today][:8]
    reading = [r for r in list_records("reading") if r.get("status") != "done"][:8]

    def esc(s):
        return html.escape(str(s if s is not None else ""))

    def block(title, items, fmt):
        if not items:
            return ""
        return (f"<h2>{esc(title)}</h2><ul>" +
                "".join(f"<li>{fmt(x)}</li>" for x in items) + "</ul>")

    body = (
        block("在进行的稿件", ms, lambda m: f"<b>{esc(m.get('title'))}</b>"
              f"<small> · {esc(m.get('stage') or '')}"
              f"{' · 下一步：' + esc(m.get('next_action')) if m.get('next_action') else ''}</small>") +
        block("近的会议截稿", confs, lambda c: f"<b>{esc(c.get('title'))}</b>"
              f"<small> · {esc(str(c.get('deadline'))[:10])}</small>") +
        block("接下来的日程", sched, lambda s: f"<b>{esc(s.get('title'))}</b>"
              f"<small> · {esc(str(s.get('date'))[:10])} {esc(s.get('time') or '')}</small>") +
        block("在读文献", reading, lambda r: f"<b>{esc(r.get('title'))}</b>"
              f"<small> · {esc(r.get('status') or '')}</small>"))
    quotes = load_quotes().get("quotes") or []
    q = quotes[(datetime.now().timetuple().tm_yday) % len(quotes)] if quotes else {}
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>工作台简报 {today}</title>
<style>:root{{color-scheme:light dark}}
body{{margin:0;padding:22px;max-width:560px;margin:0 auto;background:#f6f7f9;color:#1b1d21;
font:16px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
@media (prefers-color-scheme:dark){{body{{background:#14171d;color:#e6e8ec}}}}
h1{{font-size:20px;margin:0 0 2px}}h2{{font-size:15px;margin:22px 0 8px;color:#4c5360}}
.q{{border-left:3px solid #3b5bdb;padding:8px 12px;margin:14px 0;font-size:14px;color:#4c5360}}
ul{{padding-left:18px;margin:0}}li{{margin:6px 0}}small{{color:#7a828e}}
.foot{{margin-top:26px;font-size:12px;color:#9aa2ad}}</style></head><body>
<h1>{esc(cfg.get('profile', {}).get('name') or '我')}的工作台 · {today}</h1>
<div class="q">{esc(q.get('t', ''))}{('<br><small>—— ' + esc(q.get('s')) + '</small>') if q.get('s') else ''}</div>
{body or '<p>今天没有待办。</p>'}
<div class="foot">只读简报，两台电脑都关机时也能看。生成于 {datetime.now():%Y-%m-%d %H:%M}。</div>
</body></html>"""
    written = []
    p0 = LOCAL / "digest" / f"digest-{today}.html"
    atomic_write_text(p0, doc)
    written.append(str(p0))
    d = (target_dir or get_device().get("onedrive_backup_dir") or "").strip()
    if d and not d.startswith(("http://", "https://")):
        try:
            pd = Path(d).expanduser()
            pd.mkdir(parents=True, exist_ok=True)
            atomic_write_text(pd / "今日简报.html", doc)
            written.append(str(pd / "今日简报.html"))
        except Exception as e:
            return {"ok": True, "written": written, "detail": f"OneDrive 目录写入失败：{e}"}
    return {"ok": True, "written": written, "detail": "简报已生成"}


# ------------------------------------------------------------------ server

class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128        # 默认只有 5：一开页面几十个请求齐发就会被拒


class Handler(BaseHTTPRequestHandler):
    server_version = f"ScholarWorkspace/{VERSION}"

    def log_message(self, *a):
        pass

    # -- helpers
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _body(self):
        """读取并校验请求正文。坏正文一律抛 BadBody（→400），绝不悄悄当成空对象，
        否则一次网络抖动或程序 bug 就会往库里塞一条空白记录。"""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            raise BadBody("Content-Length 不是数字")
        if n < 0:
            raise BadBody("Content-Length 非法")
        if n > MAX_BODY:
            raise BadBody(f"正文过大（{n // 1048576} MB，上限 {MAX_BODY // 1048576} MB）")
        if not n:
            return {}
        raw = self.rfile.read(n)
        if len(raw) < n:
            raise BadBody("正文不完整（连接中断）")
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise BadBody("请求正文不是合法 JSON：" + str(e)[:60])
        if not isinstance(obj, dict):
            raise BadBody("请求正文必须是 JSON 对象")
        return obj

    # -- 安全闸门
    @property
    def client_ip(self):
        try:
            return self.client_address[0]
        except Exception:
            return "?"

    def _cookie_token(self):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sw_token":
                return v
        return self.headers.get("X-Access-Token") or ""

    def cross_site(self, method):
        """这个请求是不是从**别的网站**发过来的。

        工作台跑在 http://127.0.0.1:8765，浏览器里任何一个页面都能对它发请求，
        而「本机请求一律放行」意味着那个页面拿到的是完全的写权限：
        随手开一个恶意网页，它就能替你新建、删除、恢复备份。
        no-cors 的 POST 拿不到回应，但**副作用照样发生**，
        所以「反正它读不到返回值」不是安全的理由。

        同源的写请求浏览器一定会带 Origin，所以规则很简单：
        带了 Origin 且和自己的 Host 对不上 → 拒。
        curl / 脚本 / 手机 App 不带 Origin，照旧放行（它们不受浏览器的自动带 cookie 影响）。
        """
        if method not in ("POST", "DELETE", "PUT", "PATCH"):
            return False
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return False
        # Origin: null 来自沙箱 iframe、data: 页、file:// 页 ——
        # 工作台自己的页面永远不会是这些，但攻击者的页面可以主动变成这些。
        if origin == "null":
            return True
        host = (self.headers.get("Host") or "").strip()
        try:
            o = urlparse(origin)
            if not o.hostname:
                return True
            # Host 头可能带端口，也可能不带
            hh, _, hp = host.partition(":")
            op = str(o.port or (443 if o.scheme == "https" else 80))
            if hh != o.hostname:
                return True
            return bool(hp) and hp != op
        except Exception:
            return True

    def gate(self, route, method):
        """返回 None 表示放行，否则返回 (状态码, 响应体)。
        本机请求一律放行；远程请求要过访问码、只读、禁区三关。"""
        if self.cross_site(method):
            security_log("跨站写请求被拒", self.client_ip,
                         f"{route} <- {self.headers.get('Origin')}")
            return 403, {"error": "这个请求来自别的网站，已拒绝", "need": "cross-site"}
        if is_local_addr(self.client_ip):
            return None
        cfg = get_config()
        sec = cfg.get("security") or {}
        if not sec.get("remote_enabled"):
            security_log("远程被拒-未开启", self.client_ip, route)
            return 403, {"error": "这台机器没有开启远程访问", "need": "disabled"}
        left = locked_out(self.client_ip)
        if left > 0:
            return 429, {"error": f"访问码错误次数过多，请 {left // 60 + 1} 分钟后再试",
                         "need": "lockout"}
        if route in OPEN_ROUTES:
            return None
        sess = get_session(self._cookie_token())
        if not sess:
            return 401, {"error": "需要访问码", "need": "code"}
        if any(route == f or route.startswith(f) for f in REMOTE_FORBIDDEN):
            security_log("远程访问禁区", self.client_ip, route)
            return 403, {"error": "这项功能只能在本机操作（密钥、文件系统、脚本执行）",
                         "need": "local-only"}
        if method in ("POST", "DELETE") and route not in READONLY_EXEMPT:
            if sec.get("remote_readonly", True) and sess.get("write_until", 0) < time.time():
                return 423, {"error": "远程当前是只读模式，请先解锁写入", "need": "unlock"}
        return None

    # -- routing
    def do_GET(self):
        # 最外面这层兜底不能省：这里抛出去的异常不会变成 500，
        # 而是让这条连接**没有任何回应**地断掉 —— 排查起来比 500 难得多。
        try:
            u = urlparse(self.path)
            path, q = unquote(u.path), parse_qs(u.query)
        except Exception:
            return self._send(400, {"error": "请求地址无法解析"})
        if path.startswith("/api/"):
            blocked = self.gate(path[5:], "GET")
            if blocked:
                return self._send(blocked[0], blocked[1])
            return self.api_get(path[5:], q)
        try:
            if not is_local_addr(self.client_ip):
                cfg = get_config()
                if not (cfg.get("security") or {}).get("remote_enabled"):
                    return self._send(403, "这台机器没有开启远程访问。请在它本机的「设置 → 远程访问」里打开。",
                                      "text/plain; charset=utf-8")
                if not get_session(self._cookie_token()) and path not in ("/login.html",):
                    return self.static("/login.html")
            return self.static(path)
        except Exception:
            sys.stderr.write(f"[error] static {path[:120]}\n{traceback.format_exc()}\n")
            return self._send(404, "Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        blocked = self.gate(path[5:], "POST")
        if blocked:
            return self._send(blocked[0], blocked[1])
        try:
            body = self._body()
        except BadBody as e:
            return self._send(400, {"ok": False, "error": str(e)})
        return self.api_post(path[5:], body, parse_qs(u.query))

    def do_DELETE(self):
        u = urlparse(self.path)
        blocked = self.gate(unquote(u.path)[5:], "DELETE")
        if blocked:
            return self._send(blocked[0], blocked[1])
        parts = [unquote(p) for p in u.path.split("/") if p]
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "records":
            if parts[2] not in COLLECTIONS and parts[2] not in LOCAL_COLLECTIONS:
                return self._send(404, {"ok": False, "error": "unknown collection"})
            gone = read_record(parts[2], parts[3]) or {}
            ok = delete_record(parts[2], parts[3])
            if ok:
                # 对面那条记录里还留着指向这条的箭头，顺手摘掉，免得点了跳到空处
                me = f"{parts[2]}:{parts[3]}"
                for ref in _links_of(gone):
                    c2, i2 = _parse_ref(ref)
                    if not c2:
                        continue
                    other = read_record(c2, i2)
                    if not other:
                        continue
                    kept = [x for x in _links_of(other) if x != me]
                    if kept != _links_of(other):
                        other["links"] = kept
                        other["id"] = i2
                        try:
                            write_record(c2, other)
                        except Exception:
                            pass
            return self._send(200 if ok else 404, {"ok": ok,
                                                   "error": "" if ok else "记录不存在"})
        return self._send(404, {"error": "not found"})

    # -- static
    def static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        # 这一整段都要包在 try 里。do_GET 的静态分支外面**没有**兜底，
        # 任何一个异常都不是 500，而是线程直接死掉、连接被掐断 ——
        # 浏览器只显示「无法访问此网站」，连状态码都没有。
        # 实测能掐断的至少两种：路径里带 \x00（resolve 抛 ValueError）、
        # 路径太长（is_file/stat 抛 OSError: File name too long）。
        try:
            target = (APP / path.lstrip("/")).resolve()
            # 必须是 is_file 而不是 exists：目录也 exists，
            # 于是 GET /js 会一路走到 read_bytes 抛 IsADirectoryError。
            ok = (str(target).startswith(str(APP.resolve()))
                  and target.is_file())
            size = target.stat().st_size if ok else 0
        except (OSError, ValueError):
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        if not ok:
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        if size > MAX_STATIC:
            return self._send(413, "文件过大", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        # mimetypes 不认这两个，不给对类型的话 PWA 装不上、图标不显示
        if target.suffix == ".webmanifest":
            ctype = "application/manifest+json"
        elif target.suffix == ".svg":
            ctype = "image/svg+xml"
        if ctype.startswith("text/") or ctype in ("application/javascript",
                                                  "application/manifest+json",
                                                  "image/svg+xml"):
            ctype += "; charset=utf-8"
        try:
            data = target.read_bytes()
        except OSError:
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    # -- API GET
    def api_get(self, route, q):
        try:
            if route == "ping":
                dev = get_device()
                return self._send(200, {"ok": True, "app": "scholar-workspace",
                                        "version": VERSION,
                                        "device": dev.get("device_name") or socket.gethostname()})
            if route == "auth/status":
                sess = get_session(self._cookie_token())
                sec = get_config().get("security") or {}
                return self._send(200, {
                    "local": is_local_addr(self.client_ip),
                    "remote_enabled": bool(sec.get("remote_enabled")),
                    "has_code": bool((get_secrets().get("remote") or {}).get("access_code")),
                    "logged_in": bool(sess) or is_local_addr(self.client_ip),
                    "can_write": is_local_addr(self.client_ip) or bool(
                        sess and (not sec.get("remote_readonly", True)
                                  or sess.get("write_until", 0) > time.time())),
                    "readonly_policy": bool(sec.get("remote_readonly", True)),
                    "write_minutes_left": max(0, int(((sess or {}).get("write_until", 0) - time.time()) // 60)),
                })
            if route == "ai/status":
                if sv is None:
                    return self._send(200, {"any": False, "providers": []})
                out = sv.ai_status(get_secrets())
                out["usage"] = _safe(ai_usage_summary, {})
                return self._send(200, out)
            if route == "ai/models":
                if sv is None:
                    return self._send(200, {"ok": False, "detail": "services 未加载"})
                return self._send(200, sv.ai_models(get_secrets(), q.get("provider", [""])[0] or None))
            if route == "mail/status":
                c = (get_secrets().get("push") or {}).get("inbox") or {}
                return self._send(200, {k: v for k, v in c.items() if k != "imap_password"} |
                                  {"has_pw": bool(c.get("imap_password"))})
            if route == "overleaf/status":
                ms = [{"id": m["id"], "title": m.get("title", ""),
                       "url": m.get("overleaf_url") or m.get("overleaf") or "",
                       "last": (read_record("progress", "progress-" +
                                (overleaf_repo_url(m.get("overleaf_url") or m.get("overleaf") or "") or "/").rstrip("/").split("/")[-1] +
                                "-" + today_str()) or {}).get("synced_at", "")}
                      for m in list_records("manuscripts")
                      if (m.get("overleaf_url") or m.get("overleaf") or "").strip()]
                o = get_secrets().get("overleaf") or {}
                return self._send(200, {"configured": bool((o.get("token") or "").strip()),
                                        "email": o.get("email", ""), "projects": ms})
            if route == "peers":
                return self._send(200, {"me": device_id(), "peers": list_peers()})
            if route == "security/log":
                p = LOCAL / "security.log"
                lines = p.read_text(encoding="utf-8").splitlines()[-200:] if p.exists() else []
                return self._send(200, {"lines": lines})
            if route == "bootstrap":
                try:
                    log_activity()
                except Exception:
                    pass
                cfg, dev = get_config(), get_device()
                data = {c: list_records(c) for c in COLLECTIONS}
                data.update({c: list_records(c) for c in LOCAL_COLLECTIONS})
                data_meta = {}
                data = slim_bootstrap(data, data_meta)
                return self._send(200, {
                    "version": VERSION, "config": cfg, "device": dev,
                    "collections": COLLECTIONS, "local_collections": LOCAL_COLLECTIONS,
                    "data": data, "git": git_status(), "quota": quota_status(),
                    "server_time": iso(), "root": str(ROOT),
                    "secretsStatus": secrets_status() if is_local_addr(self.client_ip) else {},
                    "peers": _safe(list_peers, []),
                    "auth": {"local": is_local_addr(self.client_ip),
                             "can_write": is_local_addr(self.client_ip) or bool(
                                 (lambda sess, sec: sess and (not sec.get("remote_readonly", True)
                                  or sess.get("write_until", 0) > time.time()))(
                                     get_session(self._cookie_token()), cfg.get("security") or {}))},
                    "remoteChanged": _STATE.pop("remote_changed", False) if isinstance(_STATE, dict) else False,
                    "pushError": _STATE.get("push_error", ""),
                    "clock": (get_quota().get("clock") or {}).get(today_str(), {"in": "", "out": ""}),
                    # 只给数量，不给内容 —— 索引可能有几万条，进首屏必卡
                    "libraryCount": _safe(lambda: len(get_library().load()) if get_library() else 0, 0),
                    # 哪些集合被裁过、真实总数是多少。界面据此如实标注，
                    # 并提供「加载更早」，而不是拿残缺数据当全量去算合计。
                    "dataMeta": data_meta,
                    "weather": _CACHE["weather"]["data"],
                    "inbox": (CLAUDE / "inbox.md").read_text(encoding="utf-8")
                              if (CLAUDE / "inbox.md").exists() else "",
                    "outbox": sorted([p.name for p in (CLAUDE / "outbox").glob("*.md")], reverse=True),
                    "audits": sorted([p.name for p in (CLAUDE / "audits").glob("*.md")], reverse=True),
                })
            if route.startswith("records/"):
                parts = route.split("/", 2)
                coll = parts[1] if len(parts) > 1 else ""
                if coll not in COLLECTIONS and coll not in LOCAL_COLLECTIONS:
                    return self._send(404, {"error": "unknown collection", "collection": coll})
                if len(parts) == 2:
                    return self._send(200, list_records(coll))
                rec = read_record(coll, parts[2])
                return self._send(200 if rec else 404, rec or {"error": "not found"})
            if route == "quota":
                return self._send(200, quota_status())
            if route == "quota/plan":
                return self._send(200, pick_tasks())
            if route == "git/status":
                st = git_status()
                st["last_error"] = _STATE.get("push_error", "")
                st["last_pull"] = _STATE.get("last_pull", "")
                return self._send(200, st)
            if route == "git/history":
                coll = q.get("coll", [""])[0]
                rid = q.get("id", [""])[0]
                return self._send(200, git_history(coll, rid))
            if route == "backups":
                return self._send(200, list_snapshots())
            if route == "tree":
                base = q.get("path", [""])[0]
                raw = base or (get_device().get("paper_root") or str(ROOT))
                p = safe_path(raw)
                if p is None:
                    return self._send(200, {"ok": False, "entries": [],
                                            "detail": "这个路径不在允许访问的目录里（可在设置中把它设为论文根目录）"})
                if not p.exists():
                    return self._send(200, {"ok": False, "detail": "路径不存在", "entries": []})
                entries = []
                for c in sorted(p.iterdir())[:400]:
                    entries.append({"name": c.name, "dir": c.is_dir(),
                                    "size": c.stat().st_size if c.is_file() else 0})
                return self._send(200, {"ok": True, "path": str(p), "entries": entries})
            if route == "file":
                fp = safe_path(unquote(q.get("path", [""])[0]))
                if fp is None:
                    return self._send(403, {"error": "路径不在允许访问的目录内"})
                if not fp.exists() or not fp.is_file():
                    return self._send(404, {"error": "no file"})
                ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
                if fp.stat().st_size > MAX_SERVE_FILE:
                    return self._send(413, {"error": "文件太大（超过 512MB），请直接在文件管理器里打开"})
                data = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if route == "table/preview":
                # 和 /api/file 一样要过白名单。以前这里直接把 path 交给 read_table，
                # 于是「预览表格」变成了「读机器上任意 csv/txt」。
                fp = safe_path(unquote(q.get("path", [""])[0]))
                if fp is None:
                    return self._send(403, {"ok": False,
                                            "error": "这个路径不在允许的目录里（先在设置里把它加成表格来源）"})
                if not fp.is_file():
                    return self._send(400, {"ok": False,
                                            "error": "这不是一个文件（表格要指到 .csv / .xlsx 本身）"})
                try:
                    headers, rows = read_table(str(fp))
                except (ValueError, OSError) as e:
                    # 认不出的后缀、读不了的文件 —— 是用户指错了，不是服务器坏了
                    return self._send(400, {"ok": False, "error": str(e)[:200]})
                return self._send(200, {"ok": True, "headers": headers,
                                        "rows": rows[:20], "total": len(rows)})
            if route == "quotes":
                return self._send(200, load_quotes())
            # 全工作台搜索：记录 + 文献索引 + 箴言 + 功能设置
            if route == "search":
                if searchmod is None:
                    return self._send(200, {"ok": False, "detail": "search.py 未加载"})
                qq = (q.get("q") or [""])[0]
                try:
                    lim = max(1, min(int((q.get("limit") or ["30"])[0]), 100))
                except Exception:
                    lim = 30
                ix = get_library()
                mgr = ((get_config().get("reading") or {}).get("manager") or "zotero")
                return self._send(200, searchmod.search_all(
                    qq, list_records, COLLECTIONS + LOCAL_COLLECTIONS,
                    library=ix, quotes=(load_quotes() or {}).get("quotes") or [],
                    manager=mgr,
                    open_targets=(lib.open_targets if lib else None), limit=lim))

            # ---- 文献索引。搜索永远在服务端做、永远有上限，
            #      不把几万条题录丢给浏览器渲染。
            if route == "library/search":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                def _i(name, dflt=None):
                    v = (q.get(name) or [""])[0]
                    try:
                        return int(v) if str(v).strip() else dflt
                    except Exception:
                        return dflt
                hp = (q.get("has_pdf") or [""])[0]
                td = (q.get("todo") or [""])[0]
                r = ix.search(
                    q=(q.get("q") or [""])[0],
                    limit=_i("limit", 50) or 50,
                    offset=_i("offset", 0) or 0,
                    sort=(q.get("sort") or ["year"])[0],
                    year_from=_i("year_from"), year_to=_i("year_to"),
                    source=(q.get("source") or [""])[0],
                    has_pdf=True if hp == "1" else None,
                    todo=True if td == "1" else (False if td == "0" else None),
                )
                mgr = ((get_config().get("reading") or {}).get("manager") or "zotero")
                zroot = (get_device() or {}).get("zotero_root") or ""
                for it in r["items"]:
                    it["open"] = lib.open_targets(it, mgr, zroot)
                r["ok"] = True
                r["manager"] = mgr
                return self._send(200, r)
            if route == "radar/pool":
                if radar is None:
                    return self._send(200, {"ok": False, "detail": "radar.py 未加载"})
                pool = radar.Pool(CLAUDE / "radar-pool.jsonl")
                try:
                    lim = max(1, min(int((q.get("limit") or ["200"])[0]), 500))
                except Exception:
                    lim = 200
                raw = _load_json(CLAUDE / "radar-raw.json", {})
                return self._send(200, {
                    "ok": True,
                    "run": raw if isinstance(raw, dict) else {},
                    "candidates": pool.candidates((q.get("run") or [""])[0], lim),
                    "pool_total": len(pool.load()),
                })
            if route == "radar/selftest":
                if sv is None:
                    return self._send(200, {"ok": False, "detail": "services 未加载"})
                rad = (get_config().get("radar") or {})
                return self._send(200, sv.radar_selftest(
                    rad.get("sources"), mailto=(rad.get("mailto") or "")))
            if route == "library/stats":
                ix = get_library()
                return self._send(200, {"ok": bool(ix), **(ix.stats() if ix else {})})
            if route == "library/export":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False})
                body = lib.to_bibtex(ix.load()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/x-bibtex; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="library.bib"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if route == "library/zotero/status":
                return self._send(200, zotero_probe())
            if route == "diagnostics":
                if not is_local_addr(self.client_ip):
                    return self._send(403, {"ok": False, "detail": "只能在本机导出"})
                body = build_diagnostics().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="diagnostics.md"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if route == "library/file":
                # 浏览器不让 http 页面开 file://，只能由这里读了回传
                if not is_local_addr(self.client_ip):
                    return self._send(403, {"ok": False, "detail": "只能在本机打开本地文件"})
                rp, err = open_local_file((q.get("path") or [""])[0])
                if rp is None:
                    return self._send(404, {"ok": False, "detail": err})
                ctype = mimetypes.guess_type(str(rp))[0] or "application/octet-stream"
                # 整份读进内存再发，所以要有上限：一份 4GB 的扫描版 PDF
                # 会让这个进程直接被系统杀掉，工作台整个没了。
                try:
                    if rp.stat().st_size > MAX_SERVE_FILE:
                        return self._send(413, {"ok": False, "detail":
                                                "这个文件太大（超过 512MB），请直接在访达/资源管理器里打开。"})
                    data = rp.read_bytes()
                except Exception as e:
                    return self._send(500, {"ok": False, "detail": f"读不了：{e}"})
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition",
                                 "inline; filename*=UTF-8''" + urllib_quote(rp.name))
                self.end_headers()
                return self.wfile.write(data)
            if route == "secrets/status":
                return self._send(200, secrets_status())
            if route == "scan/pdfs":
                if pdfmeta is None:
                    return self._send(200, {"ok": False, "detail": "pdfmeta 未加载"})
                raw = unquote(q.get("path", [""])[0]).strip()
                if raw.startswith(("http://", "https://")):
                    return self._send(200, {"ok": False, "items": [],
                                            "detail": "这是网页链接，不是本机文件夹路径"})
                if path_too_long(raw):
                    return self._send(200, {"ok": False, "items": [], "detail": "路径太长了"})
                try:
                    pp = Path(raw).expanduser()
                    _ok = pp.exists() and pp.is_dir()
                except (OSError, ValueError) as e:
                    return self._send(200, {"ok": False, "items": [],
                                            "detail": f"这个路径用不了：{e}"})
                if not _ok:
                    return self._send(200, {"ok": False, "items": [],
                                            "detail": f"目录不存在：{pp}"})
                if not is_sane_scan_root(pp):
                    return self._send(200, {"ok": False, "items": [],
                                            "detail": "这个目录范围太大，请选择一个具体的论文文件夹"})
                result = pdfmeta.scan_folder(str(pp))
                # 扫描成功 → 自动记入允许范围，之后「打开 PDF」才放行。
                # 但「允许读这个目录下的一切」是件不该悄悄发生的事：
                # 扫一次家目录（甚至 /）就等于把 ~/.ssh 一起开放了，而界面上无从察觉、
                # 也没有地方能把它撤回来。所以太靠上的目录一律不入白名单 ——
                # 照样把扫描结果给你看，只是「打开 PDF」需要你明确挑一个真正的论文目录。
                if result.get("ok") and result.get("count"):
                    with json_txn(CONFIG_PATH, DEFAULT_CONFIG) as cfg:
                        folders = cfg.get("pdf_folders") or []
                        if str(pp) not in folders:
                            folders.append(str(pp))
                            cfg["pdf_folders"] = folders
                return self._send(200, result)
            if route == "geocode":
                return self._send(200, sv.geocode(q.get("city", [""])[0]) if sv else {"ok": False})
            if route == "checkdir":
                raw = (q.get("path", [""])[0] or "").strip()
                if not raw:
                    return self._send(200, {"ok": False, "detail": "路径为空"})
                if raw.startswith(("http://", "https://")):
                    return self._send(200, {"ok": False, "kind": "url",
                        "detail": "这是一个网页链接，不是本机文件夹。备份要写进 OneDrive 在你电脑上的<b>同步文件夹</b>，"
                                  "例如 /Users/你的用户名/OneDrive - University of Bristol/工作台备份。"
                                  "在访达里打开那个文件夹 → 右键文件夹名 → 按住 Option → 「拷贝为路径名」。"})
                if path_too_long(raw):
                    return self._send(200, {"ok": False, "detail": "路径太长了"})
                try:
                    pp = Path(raw).expanduser()
                    _isdir = pp.exists() and pp.is_dir()
                except (OSError, ValueError) as e:
                    return self._send(200, {"ok": False, "detail": f"这个路径用不了：{e}"})
                if _isdir:
                    try:
                        t = pp / ".workspace-write-test"
                        t.write_text("ok", encoding="utf-8"); t.unlink()
                        return self._send(200, {"ok": True, "detail": f"目录存在且可写：{pp}"})
                    except Exception as e:
                        return self._send(200, {"ok": False, "detail": f"目录存在但不可写：{e}"})
                parent = pp.parent
                if parent.exists():
                    return self._send(200, {"ok": False, "creatable": True,
                                            "detail": f"目录还不存在，但上级 {parent} 在 —— 可以帮你创建"})
                return self._send(200, {"ok": False, "detail": f"路径不存在：{pp}"})
            if route == "geo":
                return self._send(200, sv.geo_lookup() if sv else {"ok": False, "detail": "services 未加载"})
            if route == "weather":
                return self._send(200, cached_weather(q.get("force", ["0"])[0] == "1"))
            if route == "calendar/events":
                ics = cached_ics(q.get("force", ["0"])[0] == "1")
                return self._send(200, ics)
            if route == "claude/outbox":
                # name 是从 URL 里来的，必须只当**文件名**用。
                # 这里原来直接 CLAUDE/"outbox"/name 拼路径，
                # 于是 ?name=../../../local/secrets.json 就把访问码和
                # GitHub token 原样吐了出来 —— 而且是 GET，远程只读也拦不住。
                name = safe_name(q.get("name", [""])[0], "")
                text = ""
                if name:
                    for base in (CLAUDE / "outbox", CLAUDE / "audits"):
                        p = base / name
                        # 再兜一层：解析完必须还在这个目录里（挡符号链接）
                        try:
                            if p.is_file() and p.resolve().parent == base.resolve():
                                text = p.read_text(encoding="utf-8", errors="replace")
                                break
                        except OSError:
                            pass
                return self._send(200, {"name": name, "text": text})
            return self._send(404, {"error": "unknown route", "route": route})
        except BadBody as e:
            return self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:
            # 500 一定要留下现场，否则出问题只剩一句没头没尾的错误
            sys.stderr.write(f"[error] {route}\n{traceback.format_exc()}\n")
            return self._send(500, {"error": str(e), "route": route})

    # -- API POST
    def api_post(self, route, body, q):
        try:
            if route in ("auth/login", "auth/unlock"):
                ip = self.client_ip
                left = locked_out(ip)
                if left > 0:
                    return self._send(429, {"ok": False,
                                            "error": f"错太多次了，请 {left // 60 + 1} 分钟后再试"})
                if not check_access_code((body or {}).get("code")):
                    n = note_fail(ip)
                    security_log("访问码错误", ip, f"第 {n} 次")
                    return self._send(401, {"ok": False,
                                            "error": f"访问码不对（{n}/{MAX_FAILS}）"})
                with _SEC_LOCK:
                    LOGIN_FAILS.pop(ip, None)
                want_write = route == "auth/unlock"
                tok = self._cookie_token()
                sess = get_session(tok)
                if sess and want_write:
                    with _SEC_LOCK:
                        sess["write_until"] = time.time() + WRITE_MINUTES * 60
                else:
                    tok = new_session(ip, self.headers.get("User-Agent"), want_write)
                security_log("解锁写入" if want_write else "远程登录成功", ip, "")
                body_out = json.dumps({"ok": True, "token": tok,
                                       "write_minutes": WRITE_MINUTES if want_write else 0},
                                      ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body_out)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Set-Cookie",
                                 f"sw_token={tok}; Path=/; HttpOnly; SameSite=Lax; "
                                 f"Max-Age={SESSION_HOURS * 3600}")
                self.end_headers()
                try:
                    self.wfile.write(body_out)
                except BrokenPipeError:
                    pass
                return
            if route == "auth/logout":
                with _SEC_LOCK:
                    SESSIONS.pop(self._cookie_token(), None)
                return self._send(200, {"ok": True})
            if route == "ai/test":
                if sv is None:
                    return self._send(200, {"ok": False, "detail": "services 未加载"})
                return self._send(200, sv.ai_test(get_secrets(), (body or {}).get("provider")))
            if route == "ai/ask":
                if sv is None:
                    return self._send(200, {"ok": False, "detail": "services 未加载"})
                b = body or {}
                if not (b.get("prompt") or "").strip():
                    return self._send(400, {"ok": False, "error": "没有内容可问"})
                r = sv.ai_ask(get_secrets(), b["prompt"], b.get("system", ""),
                              b.get("provider"), int(b.get("max_tokens") or 1500))
                if r.get("ok"):
                    try:                       # 记一笔，方便你回头看 API 花在哪儿了
                        log_ai_call(b.get("provider") or "", r)
                    except Exception:
                        pass
                return self._send(200, r)
            if route == "mail/intake":
                return self._send(200, mail_intake(int((body or {}).get("limit") or 20)))
            if route == "overleaf/sync":
                b = body or {}
                if b.get("all"):
                    return self._send(200, {"ok": True, "results": overleaf_sync_all()})
                res = overleaf_sync(b.get("manuscript"), b.get("url"))
                if res.get("ok") and b.get("manuscript"):
                    overleaf_record(b["manuscript"], res)
                return self._send(200, res)
            if route == "portal/build":
                return self._send(200, build_portal((body or {}).get("dir") or ""))
            if route == "digest/build":
                return self._send(200, build_digest((body or {}).get("dir") or ""))
            if route.startswith("records/"):
                coll = route.split("/")[1]
                if coll not in COLLECTIONS and coll not in LOCAL_COLLECTIONS:
                    return self._send(404, {"error": "unknown collection", "collection": coll})
                if not any(k for k in body if not str(k).startswith("_")):
                    return self._send(400, {"error": "这条记录没有任何内容，没有保存"})
                try:
                    rec = write_record(coll, body, (body or {}).get("_mtime"))
                except Conflict as c:
                    return self._send(409, {"conflict": True, "mine": c.mine, "theirs": c.theirs})
                return self._send(200, rec)
            if route == "link":
                return self._send(200, link_edit((body or {}).get("a"), (body or {}).get("b"),
                                                 (body or {}).get("op") or "add"))
            if route == "link/gc":
                return self._send(200, link_gc())
            if route == "config":
                # 界面发来的是它手上那份**完整**配置。整份盖回去的话，
                # 另一个页签（或另一台设备、或 Claude）刚加进来的键会被抹掉：
                # 开着的旧页签点一下暗色模式，别处刚写的今日速记就没了。
                # 所以只覆盖它确实带来的顶层键，没提到的保持原样。
                if not isinstance(body, dict):
                    return self._send(400, {"ok": False, "error": "配置必须是一个对象"})
                with json_txn(CONFIG_PATH, DEFAULT_CONFIG) as cfg:
                    cfg.update(body)
                return self._send(200, {"ok": True})
            if route == "mkdir":
                raw = (body or {}).get("path", "").strip()
                try:
                    Path(raw).expanduser().mkdir(parents=True, exist_ok=True)
                    return self._send(200, {"ok": True, "detail": "已创建"})
                except Exception as e:
                    return self._send(200, {"ok": False, "detail": str(e)})
            if route == "config/merge":
                # 设置是逐项合并的，两个页面/两台设备同时改就会互相覆盖
                with json_lock(CONFIG_PATH):
                    cfg = deep_merge(get_config(), body)
                    # ICS 去重（同一条填两遍会导致日程重复显示）
                    cal = cfg.get("calendar") or {}
                    if isinstance(cal.get("ics"), list):
                        seen, uniq = set(), []
                        for u in cal["ics"]:
                            u = (u or "").strip()
                            if u and u not in seen:
                                seen.add(u); uniq.append(u)
                        cal["ics"] = uniq
                    _save_json(CONFIG_PATH, cfg)
                    return self._send(200, {"ok": True, "config": cfg})
            if route == "secrets/merge":
                with json_lock(SECRETS_PATH):
                    _save_json(SECRETS_PATH, deep_merge(get_secrets(), body))
                return self._send(200, {"ok": True, "status": secrets_status()})
            if route == "test/git":
                return self._send(200, test_git(body or {}))
            if route == "library/import":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                text = (body or {}).get("text") or ""
                if not isinstance(text, str):
                    return self._send(400, {"ok": False, "detail": "text 必须是文本"})
                fmt = ((body or {}).get("format") or "").strip().lower()
                fname = (body or {}).get("filename") or ""
                if not text.strip():
                    return self._send(200, {"ok": False, "detail": "没有内容"})
                if len(text) > 80 * 1024 * 1024:
                    return self._send(200, {"ok": False, "detail": "文件太大（超过 80MB）"})
                fmt = fmt or lib.sniff(text, fname)
                if fmt not in lib.PARSERS:
                    return self._send(200, {"ok": False,
                                            "detail": "认不出这是什么格式。支持 .bib / .ris / .json(CSL) / .nbib"})
                t0 = time.time()
                try:
                    items = lib.PARSERS[fmt](text)
                except Exception as e:
                    return self._send(200, {"ok": False, "detail": f"解析失败：{e}"})
                if not items:
                    return self._send(200, {"ok": False,
                                            "detail": f"按 {fmt} 解析出 0 条，检查一下文件对不对"})
                st = ix.add_many(items, source=fmt)
                st.update({"ok": True, "format": fmt, "parsed": len(items),
                           "ms": round((time.time() - t0) * 1000)})
                return self._send(200, st)
            if route == "library/zotero/sync":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                return self._send(200, zotero_sync(ix, (body or {})))
            if route == "library/promote":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                it = ix.get((body or {}).get("key") or "")
                if not it:
                    return self._send(200, {"ok": False, "detail": "索引里没有这一条"})
                return self._send(200, promote_to_reading(it))
            if route == "capture":
                # 手机速记页（/jot.html）的落点。故意不做智能解析：
                # 手机上写的东西最零碎，猜错分类比不猜更烦人。
                # 一律进「想法」并标成待分类，回到电脑上再归类。
                b = body or {}
                text = str(b.get("text") or "").strip()
                if not text:
                    return self._send(400, {"ok": False, "detail": "内容是空的"})
                truncated = 0
                if len(text) > 20000:
                    truncated = len(text) - 20000
                    text = text[:20000]
                kind = str(b.get("kind") or "idea")
                KIND = {"idea": "idea", "question": "question",
                        "todo": "idea", "done": "idea"}
                title = text.split("\n", 1)[0][:120] or "（无题）"
                rec = write_record("ideas", {
                    "title": title, "kind": KIND.get(kind, "idea"),
                    "status": "new", "source": "unsorted",
                    "from": "手机速记", "captured_kind": kind,
                    "captured_at": str(b.get("at") or iso())[:32],
                    "body": text if len(text) > len(title) else "",
                })
                out = {"ok": True, "id": rec.get("id")}
                if truncated:
                    out["truncated"] = truncated
                    out["detail"] = f"太长了，尾部 {truncated} 个字没能存下（上限 20000）。"
                return self._send(200, out)
            if route == "tex/sync":
                b = body or {}
                res = local_tex_sync(b.get("id"), b.get("folder"))
                if res.get("ok") and b.get("id"):
                    overleaf_record(b.get("id"), res)
                return self._send(200, res)
            if route == "library/merge":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                b = body or {}
                return self._send(200, ix.merge_pair(b.get("keep") or "", b.get("drop") or ""))
            if route == "library/remove":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                return self._send(200, {"ok": True, **ix.remove((body or {}).get("keys") or [])})
            # ---- 文献文件夹：指一个目录，把里面的 .bib/.ris/.nbib 和 PDF 一起收进来
            if route == "library/scan":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                raw = (body or {}).get("path") or ""
                folder = Path(str(raw)).expanduser()
                if not folder.is_dir():
                    return self._send(200, {"ok": False,
                                            "detail": f"这不是一个文件夹：{raw}"})
                if not is_sane_scan_root(folder):
                    return self._send(200, {"ok": False, "detail":
                                            "这个目录太靠上（家目录或磁盘根）。"
                                            "请指到具体存文献的那个文件夹 —— "
                                            "否则会把整块盘翻一遍，还会把无关的 json 当题录读。"})
                t0 = time.time()
                try:
                    r = lib.scan_folder_items(folder, pdfmeta=pdfmeta)
                except Exception as e:
                    return self._send(200, {"ok": False, "detail": f"扫描出错：{e}"})
                if not r.get("ok"):
                    return self._send(200, r)
                items = r.pop("items")
                r["found"] = len(items)
                # 先扫后导分两步：默认只告诉你扫到了什么，
                # 带 apply 才真的写进索引。误指一个目录不会当场改掉你的库。
                if (body or {}).get("apply"):
                    # 按来源可靠度分批并入：先 PDF 再题录文件，
                    # 这样同一篇论文最终留下的是更可信那一份的字段。
                    order = {"pdf": 0, "csl": 1, "nbib": 1, "ris": 1, "bib": 1}
                    items.sort(key=lambda x: order.get(x.get("s") or "", 1))
                    st = ix.add_many(items)
                    r.update({"applied": True, **st})
                    if str(folder) not in (get_config().get("lib_folders") or []):
                        with json_txn(CONFIG_PATH, DEFAULT_CONFIG) as cfg:
                            fs = cfg.get("lib_folders") or []
                            if str(folder) not in fs:
                                fs.append(str(folder))
                                cfg["lib_folders"] = fs[:20]
                else:
                    r["applied"] = False
                    r["preview"] = [{"t": x.get("t"), "y": x.get("y"),
                                     "s": x.get("s"), "todo": x.get("todo") or ""}
                                    for x in items[:20]]
                r["ms"] = round((time.time() - t0) * 1000)
                return self._send(200, r)
            if route == "library/folder/forget":
                with json_txn(CONFIG_PATH, DEFAULT_CONFIG) as cfg:
                    cfg["lib_folders"] = [x for x in (cfg.get("lib_folders") or [])
                                          if x != (body or {}).get("path")]
                    _left = list(cfg["lib_folders"])
                return self._send(200, {"ok": True, "folders": _left})
            # ---- 学术雷达：AI 挑完之后，**必须**经这条路进库。
            #      校验在服务端做，不在 AI 那边 —— 否则等于让被审的人自己签字。
            if route == "radar/submit":
                if radar is None:
                    return self._send(200, {"ok": False, "detail": "radar.py 未加载"})
                picks = (body or {}).get("picks")
                if not isinstance(picks, list):
                    return self._send(400, {"ok": False, "error": "picks 必须是一个列表"})
                pool = radar.Pool(CLAUDE / "radar-pool.jsonl")
                res = radar.verify(picks, pool)
                # 只有通过校验的才进文献索引，且来源标 radar（优先级最低，
                # 不会覆盖你从 Zotero 或 .bib 整理过的字段）
                added = {}
                ix = get_library()
                if ix is not None and res["ok"]:
                    items = [lib._mk_item(t=x.get("t"), a=x.get("a"), y=x.get("y"),
                                          j=x.get("j"), d=x.get("d"), u=x.get("u"),
                                          ty=x.get("ty"))
                             for x in res["ok"]]
                    added = ix.add_many(items, source="radar")
                pool.mark([x.get("fp") for x in res["ok"]], "shown")
                # rejected 里的 pick 可能根本不是字典（AI 交回来一个数字、一个字符串
                # 都见过），不能直接 .get —— 那样脏输入会变成 500。
                pool.mark([(r.get("pick") or {}).get("fp")
                           for r in res["rejected"]
                           if isinstance(r.get("pick"), dict)], "ignored")
                # 回给 AI 的必须是**完整的引用字段**（作者、年份、期刊都要）。
                # 之前这里只回了 fp/t/d/u/why，看着够用，其实是把周报逼上绝路：
                # 要写「He, Kelly and Manela (2017)」就只能凭印象补作者和年份 ——
                # 而「凭印象补」正是这整套校验想挡掉的那件事。
                # 校验过的原始记录已经在手里了，没有任何理由不给出去。
                keep = ("fp", "t", "a", "y", "j", "d", "u", "ty",
                        "hit_by", "hit_kind", "uncertain", "why", "rank")
                return self._send(200, {
                    "ok": True, **res["stats"],
                    "accepted": [{k: x[k] for k in keep if k in x} for x in res["ok"]],
                    # 丢掉的也要能看出丢的是哪一条，否则日志里只有一句
                    # 「候选池里没有这一条」，没法判断是模型编的还是抓取漏了
                    "rejected": [{"reason": r.get("reason"), "detail": r.get("detail"),
                                  "t": (str((r.get("pick") or {}).get("title")
                                            or (r.get("pick") or {}).get("t") or "")[:120]
                                        if isinstance(r.get("pick"), dict) else "")}
                                 for r in res["rejected"]],
                    "note": radar.verdict_line(res),
                    "library": added,
                })
            if route == "library/clear":
                ix = get_library()
                if ix is None:
                    return self._send(200, {"ok": False, "detail": "library.py 未加载"})
                return self._send(200, ix.clear((body or {}).get("source") or "",
                                                bool((body or {}).get("confirm"))))
            if route == "test/ics":
                if sv is None:
                    return self._send(200, {"ok": False, "detail": "services 未加载"})
                r = sv.fetch_ics((body or {}).get("url", ""))
                if r.get("ok"):
                    r["sample"] = [{"date": e.get("date"), "time": e.get("time"),
                                    "title": e.get("title")} for e in r["events"][:5]]
                    r.pop("events", None)
                return self._send(200, r)
            if route == "test/push":
                if sv is None:
                    return self._send(200, {"ok": False, "detail": "services 未加载"})
                kind = (body or {}).get("kind", "")
                return self._send(200, sv.test_channel(kind, get_secrets()))
            if route == "setup/complete":
                with json_txn(CONFIG_PATH, DEFAULT_CONFIG) as cfg:
                    cfg["setup"] = {"done": True, "step": 10, "completed_at": iso()}
                return self._send(200, {"ok": True})
            if route == "device":
                _save_json(DEVICE_PATH, body)
                return self._send(200, {"ok": True})
            if route == "secrets":
                cur = _load_json(SECRETS_PATH, {})
                cur.update(body)
                _save_json(SECRETS_PATH, cur)
                return self._send(200, {"ok": True, "keys": sorted(cur.keys())})
            if route == "activity":
                log_activity()
                return self._send(200, {"ok": True})
            if route == "clock":
                # 打卡整段必须是一次事务：读到写之间只要插进一次 log_activity()
                # （每回 bootstrap 都会调），刚打的卡就被整份盖回去了。
                with json_lock(QUOTA_PATH):
                    q = get_quota()
                    act = (body or {}).get("action", "")
                    today = today_str()
                    log = q.setdefault("clock", {})
                    rec = log.setdefault(today, {"in": "", "out": ""})
                    now = now_local().strftime("%H:%M")
                    if act == "in":
                        rec["in"] = rec["in"] or now
                    elif act == "out":
                        rec["out"] = now
                    elif act == "toggle":
                        if rec["in"] and not rec["out"]:
                            rec["out"] = now
                        else:
                            rec["in"] = now; rec["out"] = ""
                    for k in list(log.keys()):
                        if k < (now_local() - timedelta(days=90)).strftime("%Y-%m-%d"):
                            log.pop(k)
                    # 用打卡记录订正作息（比猜准）
                    ins = sorted(v["in"] for v in log.values() if v.get("in"))
                    outs = sorted(v["out"] for v in log.values() if v.get("out"))
                    if len(ins) >= 3 and len(outs) >= 3:
                        with json_txn(CONFIG_PATH, DEFAULT_CONFIG) as cfg:
                            cfg.setdefault("ai", {})["work_start"] = ins[len(ins) // 2]
                            cfg["ai"]["work_end"] = outs[len(outs) // 2]
                            cfg["ai"]["work_learned"] = True
                    _save_json(QUOTA_PATH, q)
                return self._send(200, {"ok": True, "today": rec,
                                        "learned": {"start": get_config().get("ai", {}).get("work_start"),
                                                    "end": get_config().get("ai", {}).get("work_end")},
                                        "days": len(log)})
            if route == "quota/override":
                with json_lock(QUOTA_PATH):
                    qd = get_quota()
                    qd["overrides"].update(body or {})
                    _save_json(QUOTA_PATH, qd)
                return self._send(200, quota_status(qd))
            if route == "quota/blocked":
                with json_lock(QUOTA_PATH):
                    qd = get_quota()
                    qd.setdefault("blocked_events", []).append(iso())
                    qd["rate_per_week"] = max(2.0, qd.get("rate_per_week", 14) * 0.5)
                    _save_json(QUOTA_PATH, qd)
                return self._send(200, quota_status(qd))
            if route == "quota/run":
                qd = record_run(body.get("kind", "manual"),
                                body.get("weight", "medium"),
                                body.get("ok", True), body.get("note", ""))
                return self._send(200, quota_status(qd))
            if route == "quota/read-report":
                with json_lock(QUOTA_PATH):
                    qd = get_quota()
                    qd["unread_reports"] = max(0, qd.get("unread_reports", 0) - 1)
                    _save_json(QUOTA_PATH, qd)
                return self._send(200, {"ok": True})
            if route == "queue":
                _save_json(QUEUE_PATH, body)
                return self._send(200, {"ok": True})
            if route == "git/init":
                first = not git_ready()
                if first:
                    git("init")
                    git("branch", "-M", "main")
                remote = (body or {}).get("remote", "").strip()
                gh = get_secrets().get("github", {})
                user, token = gh.get("user", ""), gh.get("token", "")
                # 身份：没配 commit 就会失败
                _, cur_name, _ = git("config", "user.name")
                if not cur_name:
                    git("config", "user.name", user or "workspace")
                    git("config", "user.email", gh.get("email") or f"{user or 'workspace'}@users.noreply.github.com")
                if remote:
                    url = remote
                    # 凭据嵌入 remote（只写进本机 .git/config，不进同步与备份）
                    if token and remote.startswith("https://") and "@" not in remote.split("//", 1)[1].split("/")[0]:
                        host_path = remote[len("https://"):]
                        url = f"https://{urllib_quote(user or 'x')}:{urllib_quote(token)}@{host_path}"
                    git("remote", "remove", "origin")
                    git("remote", "add", "origin", url)
                if first:
                    git("add", "-A")
                    git("commit", "-m", "init scholar workspace")
                return self._send(200, {"ok": True, **git_status()})
            if route == "git/sync":
                return self._send(200, git_sync((body or {}).get("message")))
            if route == "backup":
                return self._send(200, snapshot((body or {}).get("kind", "manual")))
            if route == "restore":
                return self._send(200, restore_snapshot((body or {}).get("path", "")))
            if route == "table/import":
                ip = safe_path(body.get("path", ""))
                if ip is None:
                    return self._send(403, {"ok": False,
                                            "error": "这个路径不在允许的目录里（先在设置里把它加成表格来源）"})
                try:
                    return self._send(200, import_table(
                        str(ip), body.get("collection", "journals"),
                        body.get("mapping"), body.get("dedup_key")))
                except (ValueError, OSError, KeyError) as e:
                    return self._send(400, {"ok": False, "error": str(e)[:200]})
            if route == "table/upload":
                name = safe_name(body.get("name", "upload.csv"), "upload.csv")
                # base64 不合法 / 不是字符串 —— 是上传出了问题，不是服务器坏了
                try:
                    raw = base64.b64decode(str(body.get("base64") or ""), validate=False)
                except Exception as e:
                    return self._send(400, {"ok": False,
                                            "error": f"文件内容不是合法的 base64：{str(e)[:80]}"})
                if len(raw) > 40 * 1024 * 1024:
                    return self._send(200, {"ok": False, "detail": "文件过大（上限 40MB）"})
                if Path(name).suffix.lower() not in (".csv", ".tsv", ".txt", ".xlsx", ".xlsm"):
                    return self._send(400, {"ok": False,
                                            "error": "只支持 .csv / .tsv / .txt / .xlsx 表格文件"})
                dest = LOCAL / "imports"
                dest.mkdir(parents=True, exist_ok=True)
                fp = dest / name
                fp.write_bytes(raw)
                try:
                    headers, rows = read_table(fp)
                except (ValueError, OSError) as e:
                    return self._send(400, {"ok": False, "error": str(e)[:200]})
                coll = (body or {}).get("collection") or ""
                return self._send(200, {"ok": True, "path": str(fp),
                                        "headers": headers, "rows": rows[:20],
                                        "total": len(rows),
                                        "guess": guess_mapping(headers, coll) if coll else {},
                                        "fields": [f for _, f in FIELD_GUESS.get(coll, [])]})
            # 箴言这三条全是「整份读进来 → 改一处 → 整份写回去」。
            # 不加锁的话，连着往里加词条会大批丢失（实测 100 条只落 28 条）——
            # 而且丢得毫无痕迹：接口返回 200，界面显示成功。
            if route == "quotes/fav":
                with json_txn(QUOTES_PATH, {"quotes": []}) as q:
                    for x in (q.get("quotes") or []):
                        if x.get("id") == (body or {}).get("id"):
                            x["fav"] = bool(body.get("fav"))
                return self._send(200, {"ok": True})
            if route == "quotes/add":
                with json_txn(QUOTES_PATH, {"quotes": []}) as q:
                    q.setdefault("quotes", [])
                    q["quotes"].append({"id": new_quote_id(q["quotes"]),
                                        "t": (body or {}).get("t", ""),
                                        "s": body.get("s", ""), "y": body.get("y", ""),
                                        "tag": body.get("tag", "mine"), "fav": False})
                return self._send(200, load_quotes())
            if route == "quotes/del":
                with json_txn(QUOTES_PATH, {"quotes": []}) as q:
                    q["quotes"] = [x for x in (q.get("quotes") or [])
                                   if x.get("id") != (body or {}).get("id")]
                return self._send(200, {"ok": True})
            if route.startswith("run/"):
                name = route.split("/")[1]
                allowed = {"radar": ["scripts/radar.py"],
                           "radar-selftest": ["scripts/radar.py", "--selftest"],
                           "primer-queue": ["scripts/primer.py", "--queue"],
                           "primer-plan": ["scripts/primer.py", "--plan"],
                           "audit": ["scripts/audit.py", "--write"],
                           "journal": ["scripts/journal.py", "--render"],
                           "journal-week": ["scripts/journal.py", "--week"],
                           "radar": ["scripts/radar.py", "--fetch"]}
                if name not in allowed:
                    return self._send(404, {"ok": False, "detail": "未知任务"})
                if name == "journal" and (body or {}).get("push"):
                    allowed[name] = allowed[name] + ["--push"]
                try:
                    r = subprocess.run([sys.executable] + allowed[name], cwd=str(ROOT),
                                       capture_output=True, text=True, timeout=180)
                    try:
                        data = json.loads(r.stdout or "{}")
                    except Exception:
                        data = {"raw": (r.stdout or "")[-4000:]}
                    return self._send(200, {"ok": r.returncode == 0, "data": data,
                                            "err": (r.stderr or "")[-800:]})
                except Exception as e:
                    return self._send(200, {"ok": False, "detail": str(e)})
            if route == "audit/ignore":
                _p = CLAUDE / "audit-ignored.json"
                with json_txn(_p, {"keys": []}) as cur:
                    k = (body or {}).get("key", "")
                    cur.setdefault("keys", [])
                    if k and k not in cur["keys"]:
                        cur["keys"].append(k)
                    _n = len(cur["keys"])
                return self._send(200, {"ok": True, "count": _n})
            if route == "push/send":
                if sv is None:
                    return self._send(200, {"ok": False, "detail": "services 未加载"})
                return self._send(200, sv.push_all(get_secrets(),
                                                   (body or {}).get("title", "学术工作台"),
                                                   (body or {}).get("markdown", "")))
            if route == "claude/inbox":
                text = body.get("text", "")
                if text is None:
                    text = ""
                if not isinstance(text, str):
                    return self._send(400, {"ok": False, "error": "text 必须是文本"})
                mode = body.get("mode", "append")
                p = CLAUDE / "inbox.md"
                # 追加也是读-改-写：两条请求撞上就丢一条；
                # 而且用的是普通 write_text —— 写到一半断电就把整个信箱截断了。
                # 加锁 + 原子写，两件事一起解决。
                with json_lock(p):
                    old = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                    atomic_write_text(p, text if mode == "replace" else
                                      (old + ("\n\n" if old else "") + text))
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "unknown route", "route": route})
        except BadBody as e:
            return self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:
            # 500 一定要留下现场，否则出问题只剩一句没头没尾的错误
            sys.stderr.write(f"[error] {route}\n{traceback.format_exc()}\n")
            return self._send(500, {"error": str(e), "route": route})


def first_run_seed():
    if not (DATA / "config.json").exists():
        _save_json(CONFIG_PATH, DEFAULT_CONFIG)
    if not DEVICE_PATH.exists():
        dev = dict(DEFAULT_DEVICE)
        dev["timezone"] = str(now_local().tzinfo)
        _save_json(DEVICE_PATH, dev)
    if not QUOTA_PATH.exists():
        _save_json(QUOTA_PATH, DEFAULT_QUOTA)
    if not QUEUE_PATH.exists():
        _save_json(QUEUE_PATH, {"tasks": []})
    if not (CLAUDE / "inbox.md").exists():
        (CLAUDE / "inbox.md").write_text(
            "# 给 Claude 的信箱\n\n（在工作台里点 @Claude 会把请求写到这里）\n",
            encoding="utf-8")
    if not (CLAUDE / "ledger.md").exists():
        (CLAUDE / "ledger.md").write_text(
            "# 想法台账 / Idea ledger\n\n"
            "自动任务每次产出前必须先读这里去重；产出后把新条目追加进来。\n"
            "格式：`- [状态] 指纹 · 一句话 · 首次出现日期`，"
            "状态 = new / adopted / rejected / duplicate。\n\n",
            encoding="utf-8")


def main():
    global SERVE_PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--lan", action="store_true",
                    help="同时监听局域网，手机/另一台电脑才连得上（需要先设访问码）")
    args = ap.parse_args()
    SERVE_PORT = args.port
    ensure_dirs()
    first_run_seed()
    host = args.host
    if args.lan:
        cfg, sec = get_config(), (get_config().get("security") or {})
        code = (get_secrets().get("remote") or {}).get("access_code") or ""
        if not code:
            sys.exit("要开局域网访问，请先在设置里填一个访问码（设置 → 远程访问）。\n"
                     "没有访问码就开放端口，等于把工作台放在网上裸奔。")
        if not sec.get("remote_enabled"):
            cfg["security"] = dict(sec, remote_enabled=True)
            _save_json(CONFIG_PATH, cfg)
            print("已自动打开「允许远程访问」开关。")
        host = "0.0.0.0"
    try:
        write_presence(args.port)
    except Exception:
        pass
    Scheduler().start()
    srv = WorkspaceServer((host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"学术工作台已启动 → {url}\n数据目录: {ROOT}\n按 Ctrl+C 停止。")
    if args.lan:
        print("局域网地址（手机可用）：")
        for u in lan_addresses(args.port):
            print("   " + u)
        print("远程默认只读，改东西要在页面上再输一次访问码解锁。")
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
