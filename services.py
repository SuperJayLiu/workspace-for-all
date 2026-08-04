# -*- coding: utf-8 -*-
"""
外部服务：推送（钉钉 / 邮件 / 自定义 webhook）、ICS 日历订阅、天气与定位、GitHub 雷达。
只用标准库。所有函数返回 {"ok": bool, ...}，绝不抛异常打断主流程。
"""
import base64, hashlib, hmac, json, re, smtplib, ssl, socket
import urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone, date
from email.message import EmailMessage

UA = "ScholarWorkspace/3.0 (local)"
TIMEOUT = 15


def _req(url, data=None, headers=None, method=None, timeout=TIMEOUT):
    """返回 (ok, status, text)。"""
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json; charset=utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return False, e.code, e.read().decode("utf-8", "replace")[:500]
    except Exception as e:
        return False, 0, str(e)


def _fetch_text(url, timeout=30):
    """带 gzip、重定向、浏览器式 UA 的文本抓取。返回 (text, status, content_type, err)。"""
    import gzip, io as _io
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ScholarWorkspace/3.1)",
        "Accept": "text/calendar, text/plain, */*",
        "Accept-Encoding": "gzip, deflate",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding", "") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            ctype = r.headers.get("Content-Type", "")
            return raw.decode("utf-8", "replace"), r.status, ctype, None
    except urllib.error.HTTPError as e:
        return None, e.code, e.headers.get("Content-Type", "") if e.headers else "", f"{e.code} {e.reason}"
    except Exception as e:
        return None, 0, "", str(e)


def _json(url, **kw):
    ok, status, text = _req(url, **kw)
    if not ok:
        return {"ok": False, "detail": f"{status} {text[:200]}"}
    try:
        return {"ok": True, "data": json.loads(text)}
    except Exception:
        return {"ok": False, "detail": "返回不是合法 JSON: " + text[:200]}


# ------------------------------------------------------------------ 推送

DING_ERR = {
    310000: "安全校验没过：看 errmsg —— keywords not in content=正文缺关键词；"
            "invalid timestamp=本机时钟偏差过大；sign not match=加签密钥填错；"
            "ip not in whitelist=IP 不在白名单",
    300001: "这个 webhook 属于「机器人市场」里的成品机器人（比如 GitHub 机器人），"
            "它只认自己那套消息格式，收不了自定义内容。"
            "解法：在群里另外添加一个「自定义」机器人，用它的 webhook。",
    400013: "群已被解散",
    400101: "access_token 不存在，webhook 地址抄错了",
    400102: "机器人已停用，去群设置里启用",
    400105: "不支持的消息类型",
    400106: "机器人不存在（可能已被移出群）",
    410100: "发送太快被限流（每分钟上限 20 条，触发后限流 10 分钟）",
    430101: "含有不安全的外链",
    430102: "含有不合适的文本",
    430103: "含有不合适的图片",
    430104: "含有不合适的内容",
}

# 每个机器人每分钟最多 20 条，超了限流 10 分钟 —— 本地先挡一道
_DING_SENT = []


def _ding_rate_ok():
    now = datetime.now().timestamp()
    while _DING_SENT and now - _DING_SENT[0] > 60:
        _DING_SENT.pop(0)
    if len(_DING_SENT) >= 18:          # 留 2 条余量
        return False
    _DING_SENT.append(now)
    return True


def dingtalk_send(webhook, secret, title, markdown, keyword="", at_mobiles=None, at_all=False):
    """
    钉钉群机器人（自定义机器人 webhook）。
    三种安全设置任选其一：加签(secret) / 自定义关键词(keyword) / IP 段。
    加签算法：timestamp(ms) + "\\n" + secret，以 secret 为密钥做 HMAC-SHA256，
    base64 后 URL 编码，追加 &timestamp=&sign=。
    注意：每个机器人每分钟最多 20 条，超了会被限流 10 分钟。
    """
    if not webhook:
        return {"ok": False, "detail": "未配置钉钉 webhook"}
    if not _ding_rate_ok():
        return {"ok": False, "channel": "dingtalk",
                "detail": "本地限流：这一分钟已发 18 条，为避免被钉钉限流 10 分钟，本条未发送"}
    url = webhook
    if secret:
        ts = str(round(datetime.now().timestamp() * 1000))
        sign = base64.b64encode(hmac.new(secret.encode("utf-8"),
                                         f"{ts}\n{secret}".encode("utf-8"),
                                         hashlib.sha256).digest()).decode("utf-8")
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"
    # 若用「自定义关键词」模式，标题与正文里必须出现该关键词，否则钉钉会拒收
    if keyword:
        if keyword not in title:
            title = f"{keyword} · {title}"
        if keyword not in markdown:
            markdown = f"{markdown}\n\n> {keyword}"
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": markdown}}
    if at_mobiles or at_all:
        payload["at"] = {"atMobiles": at_mobiles or [], "isAtAll": bool(at_all)}
    r = _json(url, data=payload)
    if not r["ok"]:
        return {"ok": False, "channel": "dingtalk", "detail": r["detail"]}
    d = r["data"]
    code = d.get("errcode")
    if code not in (0, None):
        hint = DING_ERR.get(code, "")
        return {"ok": False, "channel": "dingtalk", "code": code,
                "detail": f'{code} {d.get("errmsg", "")}' + (f" —— {hint}" if hint else "")}
    return {"ok": True, "channel": "dingtalk"}


def wecom_send(webhook, title, markdown):
    """（已停用）企业微信群机器人。保留函数以防将来需要，不在推送路由中。"""
    if not webhook:
        return {"ok": False, "detail": "未配置企业微信 webhook"}
    payload = {"msgtype": "markdown", "markdown": {"content": f"**{title}**\n{markdown}"}}
    r = _json(webhook, data=payload)
    if not r["ok"]:
        return {"ok": False, "channel": "wecom", "detail": r["detail"]}
    d = r["data"]
    if d.get("errcode") not in (0, None):
        return {"ok": False, "channel": "wecom", "detail": f'{d.get("errcode")} {d.get("errmsg")}'}
    return {"ok": True, "channel": "wecom"}


def email_send(cfg, title, text_body, html_body=None):
    """
    cfg: {host, port, user, password, to, from_addr, ssl}
    端口 465 用 SMTP_SSL；587/25 用 STARTTLS。
    """
    need = ["host", "port", "user", "password", "to"]
    miss = [k for k in need if not cfg.get(k)]
    if miss:
        return {"ok": False, "channel": "email", "detail": "缺少配置：" + "、".join(miss)}
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = cfg.get("from_addr") or cfg["user"]
    msg["To"] = cfg["to"]
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    port = int(cfg["port"])
    try:
        ctx = ssl.create_default_context()
        if port == 465 or cfg.get("ssl"):
            with smtplib.SMTP_SSL(cfg["host"], port, context=ctx, timeout=25) as s:
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], port, timeout=25) as s:
                s.ehlo()
                try:
                    s.starttls(context=ctx)
                    s.ehlo()
                except Exception:
                    pass
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        return {"ok": True, "channel": "email"}
    except Exception as e:
        return {"ok": False, "channel": "email", "detail": str(e)}


def custom_send(cfg, title, markdown, plain=None):
    """
    通用 webhook：你自己填 URL 和 JSON 模板，占位符 {title} {markdown} {text} 会被替换。
    可用来接 wxbot、Server酱、Bark、ntfy、Telegram、Slack 等任何能收 HTTP 的东西。
    cfg: {url, method, headers{}, template(str), name}
    """
    url = (cfg or {}).get("url", "").strip()
    if not url:
        return {"ok": False, "channel": "custom", "detail": "未配置通用 webhook"}
    text = plain or re.sub(r"[*#>`\[\]]", "", markdown)

    def fill(s):
        return (s.replace("{title}", json.dumps(title, ensure_ascii=False)[1:-1])
                 .replace("{markdown}", json.dumps(markdown, ensure_ascii=False)[1:-1])
                 .replace("{text}", json.dumps(text, ensure_ascii=False)[1:-1]))

    tpl = cfg.get("template") or '{"title":"{title}","content":"{markdown}"}'
    body_str = fill(tpl)
    try:
        body = json.loads(body_str)
    except Exception as e:
        return {"ok": False, "channel": "custom",
                "detail": f"模板填充后不是合法 JSON：{e}（检查花括号与引号）"}
    ok, status, resp = _req(url, data=body, headers=cfg.get("headers") or {},
                            method=(cfg.get("method") or "POST").upper())
    if not ok or status >= 300:
        return {"ok": False, "channel": "custom", "detail": f"{status} {resp[:200]}"}
    return {"ok": True, "channel": "custom", "name": cfg.get("name") or "自定义", "resp": resp[:200]}


def push_all(secrets, title, markdown, plain=None):
    """按已配置的渠道全部推送，返回每一路的结果。"""
    out = []
    p = secrets.get("push", {})
    if p.get("dingtalk_webhook"):
        out.append(dingtalk_send(p["dingtalk_webhook"], p.get("dingtalk_secret", ""),
                                 title, markdown, p.get("dingtalk_keyword", "")))
    if p.get("email", {}).get("host"):
        out.append(email_send(p["email"], title, plain or re.sub(r"[*#>`\[\]]", "", markdown)))
    if p.get("custom", {}).get("url"):
        out.append(custom_send(p["custom"], title, markdown, plain))
    if not out:
        return {"ok": False, "detail": "还没有配置任何推送渠道", "results": []}
    return {"ok": any(r.get("ok") for r in out), "results": out}


# ----------------------------------------------------------------- ICS 日历

def _ics_unfold(text):
    lines, out = text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), []
    for ln in lines:
        if ln[:1] in (" ", "\t") and out:
            out[-1] += ln[1:]
        else:
            out.append(ln)
    return out


def _ics_unescape(s):
    return (s.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


# ------------------------------------------------------------ ICS 时区换算
#
# 为什么要这一整段：Outlook 发布的日历里，事件时间是「某个时区的墙上时间」，
# 形如 DTSTART;TZID="Eastern Standard Time":20260804T090000。
# 如果直接把 090000 当成本地时间显示，纽约同事约的 9 点会在伦敦显示成 9 点
# ——实际是伦敦下午 2 点。跨时区开会的人会因此错过会议。
#
# 换算优先级：
#   1) ICS 自带的 VTIMEZONE 块（Outlook 一定会带，含 DST 切换规则）—— 最可靠，且完全自足
#   2) Windows 时区名 → IANA 名，交给标准库 zoneinfo（Google/Apple 直接给 IANA 名）
#   3) 都拿不到 → 按 RFC 5545 的「浮动时间」处理，即当作本机时间，不换算
#
# 刻意不引第三方库：Windows 上没有 IANA 时区库时 zoneinfo 会失败，
# 所以第 1 条（用日历自己带的规则）才是主力，第 2 条只是兜底。

try:
    from zoneinfo import ZoneInfo           # 标准库，Python 3.9+
except Exception:                            # pragma: no cover
    ZoneInfo = None

# Outlook 用的是 Windows 时区名，不是 IANA 名。只列常见的，查不到就走 VTIMEZONE。
_WIN_TZ = {
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Romance Standard Time": "Europe/Paris",
    "E. Europe Standard Time": "Europe/Chisinau",
    "FLE Standard Time": "Europe/Kiev",
    "GTB Standard Time": "Europe/Bucharest",
    "Russian Standard Time": "Europe/Moscow",
    "China Standard Time": "Asia/Shanghai",
    "Taipei Standard Time": "Asia/Taipei",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "Singapore Standard Time": "Asia/Singapore",
    "India Standard Time": "Asia/Kolkata",
    "Arabian Standard Time": "Asia/Dubai",
    "Israel Standard Time": "Asia/Jerusalem",
    "Eastern Standard Time": "America/New_York",
    "US Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles",
    "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Atlantic Standard Time": "America/Halifax",
    "SA Eastern Standard Time": "America/Sao_Paulo",
    "E. South America Standard Time": "America/Sao_Paulo",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "AUS Central Standard Time": "Australia/Darwin",
    "W. Australia Standard Time": "Australia/Perth",
    "New Zealand Standard Time": "Pacific/Auckland",
    "South Africa Standard Time": "Africa/Johannesburg",
    "UTC": "UTC",
}

_WD = {"SU": 6, "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5}


def _tz_offset(s):
    """+0100 / -0430 → timedelta。"""
    m = re.fullmatch(r"([+-])(\d{2})(\d{2})(\d{2})?", (s or "").strip())
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    return timedelta(seconds=sign * (int(m.group(2)) * 3600 + int(m.group(3)) * 60
                                     + int(m.group(4) or 0)))


def _nth_weekday(year, month, weekday, nth):
    """该月第 nth 个 weekday（nth 为负=倒数第 |nth| 个）。返回 date。"""
    if nth > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        d += timedelta(weeks=nth - 1)
        return d if d.month == month else None
    last = date(year, month, 28)
    while True:
        nxt = last + timedelta(days=1)
        if nxt.month != month:
            break
        last = nxt
    last -= timedelta(days=(last.weekday() - weekday) % 7)
    last -= timedelta(weeks=-nth - 1)
    return last if last.month == month else None


class _VTimeZone:
    """用 VTIMEZONE 里的 STANDARD / DAYLIGHT 子块推算某个墙上时间该用哪个偏移。"""

    def __init__(self, tzid):
        self.tzid = tzid
        self.subs = []          # {"dt": naive datetime, "off_from", "off_to", "month", "wd", "nth"}

    def add(self, sub):
        if sub.get("off_to") is not None:
            self.subs.append(sub)

    def _transition(self, sub, year):
        """该规则在 year 年的切换时刻（naive，按切换前的墙上时间算）。"""
        if sub.get("month") and sub.get("wd") is not None:
            d = _nth_weekday(year, sub["month"], sub["wd"], sub["nth"] or 1)
            if not d:
                return None
            base = sub["dt"]
            return datetime(d.year, d.month, d.day, base.hour, base.minute, base.second)
        # 没有 RRULE：固定日期，只在它自己那一年之后有效
        return sub["dt"].replace(year=year) if sub["dt"] else None

    def offset_for(self, naive):
        if not self.subs:
            return None
        if len(self.subs) == 1:
            return self.subs[0]["off_to"]
        cands = []
        for y in (naive.year - 1, naive.year, naive.year + 1):
            for sub in self.subs:
                t = self._transition(sub, y)
                if t:
                    cands.append((t, sub))
        if not cands:
            return self.subs[0]["off_to"]
        cands.sort(key=lambda x: x[0])
        prev = None
        for t, sub in cands:
            if t <= naive:
                prev = sub
            else:
                break
        if prev is None:                       # 早于所有切换点 → 用最早那次切换之前的偏移
            first = cands[0][1]
            return first.get("off_from") or first["off_to"]
        return prev["off_to"]


def _parse_vtimezones(lines):
    """从 ICS 文本行里抽出所有 VTIMEZONE 定义。"""
    out, cur, sub, in_sub = {}, None, None, None
    for ln in lines:
        u = ln.strip().upper()
        if u == "BEGIN:VTIMEZONE":
            cur = _VTimeZone("")
            continue
        if u == "END:VTIMEZONE":
            if cur and cur.tzid:
                out[cur.tzid] = cur
            cur = None
            continue
        if cur is None:
            continue
        if u in ("BEGIN:STANDARD", "BEGIN:DAYLIGHT"):
            in_sub, sub = u.split(":")[1], {"dt": None, "off_from": None, "off_to": None,
                                            "month": None, "wd": None, "nth": None}
            continue
        if u in ("END:STANDARD", "END:DAYLIGHT"):
            if sub:
                cur.add(sub)
            in_sub, sub = None, None
            continue
        if ":" not in ln:
            continue
        key, val = ln.split(":", 1)
        key = key.split(";")[0].strip().upper()
        val = val.strip()
        if key == "TZID" and in_sub is None:
            cur.tzid = val
        elif sub is not None:
            if key == "DTSTART":
                m = re.fullmatch(r"(\d{8})T(\d{6})", val)
                if m:
                    d, t = m.group(1), m.group(2)
                    sub["dt"] = datetime(int(d[:4]), int(d[4:6]), int(d[6:8]),
                                         int(t[:2]), int(t[2:4]), int(t[4:6]))
            elif key == "TZOFFSETFROM":
                sub["off_from"] = _tz_offset(val)
            elif key == "TZOFFSETTO":
                sub["off_to"] = _tz_offset(val)
            elif key == "RRULE":
                for part in val.split(";"):
                    if part.upper().startswith("BYMONTH="):
                        try:
                            sub["month"] = int(part.split("=", 1)[1])
                        except Exception:
                            pass
                    elif part.upper().startswith("BYDAY="):
                        bd = part.split("=", 1)[1].strip().upper()
                        m = re.fullmatch(r"(-?\d+)?([A-Z]{2})", bd)
                        if m:
                            sub["nth"] = int(m.group(1) or 1)
                            sub["wd"] = _WD.get(m.group(2))
    return out


def _zone_from_tzid(tzid):
    """TZID → tzinfo。先按 IANA 直接试，再查 Windows 名对照表。"""
    if not tzid or ZoneInfo is None:
        return None
    for name in (tzid, _WIN_TZ.get(tzid)):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except Exception:
            continue
    return None


def _ics_dt(val, params, vtz=None, local_tz=None, default_tzid=None):
    """返回 (date_str, time_str|None, all_day, src_tzid)，时间已换算到 local_tz。

    整天事件（VALUE=DATE）不做换算——「8 月 10 日」在哪个时区都是 8 月 10 日，
    换算反而会把它挪到前一天。
    """
    v = (val or "").strip()
    if re.fullmatch(r"\d{8}", v) or (params or {}).get("VALUE", "").upper() == "DATE":
        m = re.match(r"(\d{4})(\d{2})(\d{2})", v)
        return (f"{m.group(1)}-{m.group(2)}-{m.group(3)}", None, True, None) if m else (None, None, False, None)
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", v)
    if not m:
        return None, None, False, None
    d, t, z = m.group(1), m.group(2), m.group(3)
    naive = datetime(int(d[:4]), int(d[4:6]), int(d[6:8]),
                     int(t[:2]), int(t[2:4]), int(t[4:6]))

    if z == "Z":
        return _fmt_local(naive.replace(tzinfo=timezone.utc), local_tz, "UTC")

    tzid = ((params or {}).get("TZID") or default_tzid or "").strip().strip('"')
    if tzid:
        # 1) 日历自带的 VTIMEZONE 规则（最可靠，Windows 上也不依赖系统时区库）
        rule = (vtz or {}).get(tzid) or (vtz or {}).get(tzid.strip('"'))
        if rule is not None:
            off = rule.offset_for(naive)
            if off is not None:
                return _fmt_local(naive.replace(tzinfo=timezone(off)), local_tz, tzid)
        # 2) 交给标准库
        zone = _zone_from_tzid(tzid)
        if zone is not None:
            return _fmt_local(naive.replace(tzinfo=zone), local_tz, tzid)

    # 3) 浮动时间：按 RFC 5545 当作本机时间，不换算
    return naive.strftime("%Y-%m-%d"), naive.strftime("%H:%M"), False, None


def _ics_raw(val, params):
    """只取原始的墙上时间，不做换算。返回 (naive datetime|date, tzid, 是否整天)。

    重复事件必须留着这个：每一次发生要**单独**换算。
    纽约每周 9 点的例会，在英国跨过夏令时那天应该从 14:00 变 13:00 ——
    只换算第一次然后按天数平移，整个序列都会错一小时。
    """
    v = (val or "").strip()
    # 日期本身可能是垃圾（月份 13、日 32、闰日不存在…）。
    # 真实订阅里这种数据不算罕见，一条坏事件不能把整个日历搞崩。
    if re.fullmatch(r"\d{8}", v) or (params or {}).get("VALUE", "").upper() == "DATE":
        m = re.match(r"(\d{4})(\d{2})(\d{2})", v)
        if not m:
            return None, "", True
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), "", True
        except ValueError:
            return None, "", True
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", v)
    if not m:
        return None, "", False
    d, tm, z = m.group(1), m.group(2), m.group(3)
    try:
        naive = datetime(int(d[:4]), int(d[4:6]), int(d[6:8]),
                         int(tm[:2]), int(tm[2:4]), int(tm[4:6]))
    except ValueError:
        return None, "", False
    tzid = "UTC" if z == "Z" else ((params or {}).get("TZID") or "").strip().strip('"')
    return naive, tzid, False


def _conv(naive, tzid, vtz, local_tz):
    """把某个时区的墙上时间换算成本机时间，返回 (日期, 时间, 原时区名或 None)。"""
    def _three(r):
        return r[0], r[1], (r[3] or {}).get("tz") if isinstance(r[3], dict) else r[3]
    if tzid == "UTC":
        return _three(_fmt_local(naive.replace(tzinfo=timezone.utc), local_tz, "UTC"))
    if tzid:
        rule = (vtz or {}).get(tzid) or (vtz or {}).get(tzid.strip('"'))
        if rule is not None:
            off = rule.offset_for(naive)
            if off is not None:
                return _three(_fmt_local(naive.replace(tzinfo=timezone(off)), local_tz, tzid))
        zone = _zone_from_tzid(tzid)
        if zone is not None:
            return _three(_fmt_local(naive.replace(tzinfo=zone), local_tz, tzid))
    return naive.strftime("%Y-%m-%d"), naive.strftime("%H:%M"), None


def _fmt_local(aware, local_tz, src):
    """换算到本地。

    local_tz=None 表示「本机时区」，此时**必须**走 fromtimestamp：
    datetime.now().astimezone().tzinfo 拿到的是「此刻」的固定偏移
    （七月在伦敦就是 +01:00），拿它去换算十二月的会议会整整差一小时。
    fromtimestamp 会按那个时刻真正的夏令时状态算，Windows 上也一样。
    """
    if local_tz is None:
        loc = datetime.fromtimestamp(aware.timestamp())
    else:
        loc = aware.astimezone(local_tz)
    return (loc.strftime("%Y-%m-%d"), loc.strftime("%H:%M"), False,
            {"tz": src, "time": aware.strftime("%H:%M")})


def parse_ics(text, horizon_days=120, local_tz=None):
    """解析 VEVENT。

    真实的 Outlook 订阅里，一个重复会议往往由三部分组成：
      · 主事件（带 RRULE）
      · EXDATE —— 被取消的那几次
      · 带 RECURRENCE-ID 的覆盖事件 —— 被改了时间/地点的那一次
    只认主事件的话：老板取消了这周组会，你的日历上它还在；
    会议从 9 点挪到 11 点，你这边要么还是 9 点、要么冒出两条。
    """
    events, cur, in_ev = [], None, False
    today = date.today()
    limit = today + timedelta(days=horizon_days)
    back = today - timedelta(days=30)
    lines = _ics_unfold(text)
    vtz = _parse_vtimezones(lines)
    default_tzid = ""
    for ln in lines:
        if ln.upper().startswith("X-WR-TIMEZONE"):
            default_tzid = ln.split(":", 1)[-1].strip()
            break

    raw_events = []
    for ln in lines:
        if ln.startswith("BEGIN:VEVENT"):
            in_ev, cur = True, {"exdates": set()}
            continue
        if ln.startswith("END:VEVENT"):
            in_ev = False
            if cur and cur.get("_naive") is not None:
                raw_events.append(cur)
            cur = None
            continue
        if not in_ev or ":" not in ln:
            continue
        key, val = ln.split(":", 1)
        params = {}
        if ";" in key:
            parts = key.split(";")
            key = parts[0]
            for pp in parts[1:]:
                if "=" in pp:
                    k, v = pp.split("=", 1)
                    params[k.upper()] = v
        key = key.upper()
        if key == "SUMMARY":
            cur["title"] = _ics_unescape(val)
        elif key == "LOCATION":
            cur["location"] = _ics_unescape(val)
        elif key == "DTSTART":
            naive, tzid, allday = _ics_raw(val, params)
            cur["_naive"], cur["_tzid"], cur["all_day"] = naive, (tzid or default_tzid), allday
        elif key == "DTEND":
            naive, tzid, allday = _ics_raw(val, params)
            cur["_end_naive"], cur["_end_tzid"] = naive, (tzid or default_tzid)
        elif key == "RRULE":
            cur["rrule"] = val
        elif key == "UID":
            cur["uid"] = val
        elif key == "STATUS":
            cur["status"] = val.strip().upper()
        elif key == "RECURRENCE-ID":
            naive, tzid, allday = _ics_raw(val, params)
            cur["_recid"] = naive
        elif key == "EXDATE":
            # 一行可以写多个，逗号分隔
            for piece in val.split(","):
                naive, tzid, allday = _ics_raw(piece.strip(), params)
                if naive is not None:
                    cur["exdates"].add(_occ_key(naive))

    # 被改期/取消的那一次：按 (uid, 原始发生时刻) 去覆盖主事件
    overrides = {}
    for e in raw_events:
        if e.get("_recid") is not None:
            overrides[(e.get("uid", ""), _occ_key(e["_recid"]))] = e

    def emit(e, naive, end_naive=None):
        """把一次具体发生换算成本机时间后产出。"""
        if e.get("all_day"):
            d = naive if isinstance(naive, date) and not isinstance(naive, datetime) else naive.date()
            out = {"uid": e.get("uid", ""), "title": e.get("title", ""),
                   "date": d.isoformat(), "time": None, "all_day": True,
                   "end_date": d.isoformat(), "end_time": None,
                   "location": e.get("location"), "source": "Outlook"}
            return out
        ds, ts, src = _conv(naive, e.get("_tzid") or "", vtz, local_tz)
        out = {"uid": e.get("uid", ""), "title": e.get("title", ""),
               "date": ds, "time": ts, "all_day": False,
               "location": e.get("location"), "source": "Outlook"}
        if src and ts != naive.strftime("%H:%M"):
            out["src_tz"], out["src_time"] = src, naive.strftime("%H:%M")
        if end_naive is not None and not isinstance(end_naive, date) or isinstance(end_naive, datetime):
            eds, ets, _ = _conv(end_naive, e.get("_end_tzid") or e.get("_tzid") or "", vtz, local_tz)
            out["end_date"], out["end_time"] = eds, ets
        return out

    for e in raw_events:
        if e.get("_recid") is not None:
            continue                       # 覆盖事件单独处理
        naive = e["_naive"]
        dur = None
        if e.get("_end_naive") is not None and isinstance(naive, datetime) \
                and isinstance(e["_end_naive"], datetime):
            dur = e["_end_naive"] - naive
        for occ in _expand_occurrences(e, naive, back, limit):
            key = (e.get("uid", ""), _occ_key(occ))
            if _occ_key(occ) in e["exdates"]:
                continue                   # 这一次被取消了
            ov = overrides.get(key)
            if ov is not None:
                if (ov.get("status") or "") == "CANCELLED":
                    continue               # 改期事件本身写着取消
                events.append(emit(ov, ov["_naive"], ov.get("_end_naive")))
                continue
            events.append(emit(e, occ, (occ + dur) if dur else None))

    # 不属于任何已展开序列的覆盖事件（主事件不在窗口里，但这一次在），也要露出来
    seen = {(x.get("uid"), x.get("date"), x.get("time")) for x in events}
    for (uid, _k), ov in overrides.items():
        if (ov.get("status") or "") == "CANCELLED":
            continue
        one = emit(ov, ov["_naive"], ov.get("_end_naive"))
        try:
            d0 = date.fromisoformat(one["date"])
        except Exception:
            continue
        if back <= d0 <= limit and (one.get("uid"), one.get("date"), one.get("time")) not in seen:
            events.append(one)
            seen.add((one.get("uid"), one.get("date"), one.get("time")))
    return events


def _occ_key(naive):
    """一次发生的身份：只用日期。

    Outlook 的 EXDATE / RECURRENCE-ID 时间部分偶尔跟主事件差几秒或时区写法不同，
    按整秒比对会漏掉；同一天出现两场同 UID 的会议实际上不存在。
    """
    if isinstance(naive, datetime):
        return naive.date().isoformat()
    if isinstance(naive, date):
        return naive.isoformat()
    return str(naive)


def _expand_occurrences(ev, start_naive, back, limit):
    """按 RRULE 产出每一次发生的**原始墙上时间**（不换算，换算在 emit 里逐次做）。"""
    is_dt = isinstance(start_naive, datetime)
    d0 = start_naive.date() if is_dt else start_naive
    rule = ev.get("rrule")
    if not rule:
        return [start_naive] if back <= d0 <= limit else []
    parts = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    freq = parts.get("FREQ", "")
    interval = int(parts.get("INTERVAL", "1") or 1)
    count = int(parts.get("COUNT", "0") or 0)
    until = None
    if parts.get("UNTIL"):
        u = re.sub(r"T.*", "", parts["UNTIL"])
        try:
            until = date(int(u[:4]), int(u[4:6]), int(u[6:8]))
        except Exception:
            until = None
    out, cur, n = [], d0, 0
    while cur <= limit and n < 400:
        if until and cur > until:
            break
        if cur >= back:
            out.append(datetime.combine(cur, start_naive.time()) if is_dt else cur)
        n += 1
        if count and n >= count:
            break
        if freq == "DAILY":
            cur += timedelta(days=interval)
        elif freq == "WEEKLY":
            cur += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            y, m = cur.year, cur.month + interval
            y += (m - 1) // 12
            m = (m - 1) % 12 + 1
            day = min(cur.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
            cur = date(y, m, day)
        elif freq == "YEARLY":
            try:
                cur = cur.replace(year=cur.year + interval)
            except ValueError:
                cur = cur.replace(year=cur.year + interval, day=28)
        else:
            break
    return out


def _expand(ev, back, limit):
    base = ev.get("date")
    if not base:
        return []
    try:
        d0 = date.fromisoformat(base)
    except Exception:
        return []
    rule = ev.get("rrule")
    if not rule:
        return [ev] if back <= d0 <= limit else []
    parts = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    freq = parts.get("FREQ", "")
    interval = int(parts.get("INTERVAL", "1") or 1)
    count = int(parts.get("COUNT", "0") or 0)
    until = None
    if parts.get("UNTIL"):
        u = re.sub(r"T.*", "", parts["UNTIL"])
        try:
            until = date(int(u[:4]), int(u[4:6]), int(u[6:8]))
        except Exception:
            until = None
    out, cur, n = [], d0, 0
    while cur <= limit and n < 400:
        if until and cur > until:
            break
        if cur >= back:
            e = dict(ev)
            e["date"] = cur.isoformat()
            e.pop("rrule", None)
            out.append(e)
        n += 1
        if count and n >= count:
            break
        if freq == "DAILY":
            cur += timedelta(days=interval)
        elif freq == "WEEKLY":
            cur += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            y, m = cur.year, cur.month + interval
            y += (m - 1) // 12
            m = (m - 1) % 12 + 1
            day = min(cur.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
            cur = date(y, m, day)
        elif freq == "YEARLY":
            try:
                cur = cur.replace(year=cur.year + interval)
            except ValueError:
                cur = cur.replace(year=cur.year + interval, day=28)
        else:
            break
    return out


def _private_host(url):
    """这个 URL 指向的是不是本机/内网/云平台元数据地址。是的话返回一句人话。"""
    import ipaddress
    import socket as _sk
    from urllib.parse import urlparse as _up
    try:
        host = (_up(url).hostname or "").strip("[]")
    except Exception:
        return "无法解析的地址"
    if not host:
        return "无法解析的地址"
    if host.lower() in ("localhost", "localhost.localdomain") or host.lower().endswith(".local"):
        return "本机"
    try:
        infos = _sk.getaddrinfo(host, None)
    except Exception:
        return ""          # 解析不了就让后面的请求自己去失败，别在这里瞎猜
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except Exception:
            continue
        if ip.is_loopback:
            return "本机"
        if ip.is_link_local:
            return "链路本地地址（云平台的元数据接口就在这里）"
        if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return "保留地址"
    return ""
    # 注：局域网地址（192.168./10./172.16.）是**放行**的 ——
    # 学校自建的日历服务经常就在内网，一刀切会挡掉正常用法。
    # 真正没有任何正当理由的是本机和链路本地：
    # 前者是 Zotero、数据库这些只监听 127.0.0.1 的东西，
    # 后者是云平台取临时凭证的元数据接口。


def fetch_ics(url, horizon_days=120):
    if not url:
        return {"ok": False, "detail": "未填写 ICS 链接"}
    u = url.strip()
    if u.startswith("webcal://"):
        u = "https://" + u[len("webcal://"):]
    if not u.startswith(("http://", "https://")):
        return {"ok": False, "detail": "不是合法链接，应以 https:// 开头"}
    # 日历链接是**公网**上的订阅地址。允许它指向内网，就等于把工作台
    # 变成一个替人探测局域网、探测云平台元数据接口的工具 ——
    # 而且下面出错时还会把对方返回的前 80 字原样回显。
    bad = _private_host(u)
    if bad:
        return {"ok": False, "detail": f"日历链接不能指向{bad}。请填公开发布的订阅地址。"}
    text, status, ctype, err = _fetch_text(u)
    if text is None:
        hint = ""
        low = str(err).lower()
        if "certificate" in low or "ssl" in low:
            hint = "（证书问题：可能被公司/学校网络代理拦截）"
        elif "timed out" in low:
            hint = "（超时：网络不通，或该链接需要校园网/VPN）"
        elif "403" in low or "401" in low:
            hint = "（被拒绝：这个日历可能没有真正「发布」，或权限只给了组织内部）"
        elif "404" in low:
            hint = "（链接不存在：确认复制的是 ICS 那一行，不是 HTML 那一行）"
        return {"ok": False, "detail": f"拉取失败 {status or ''} {str(err)[:160]} {hint}"}
    if "BEGIN:VCALENDAR" not in text:
        if "<html" in text[:600].lower():
            return {"ok": False, "detail":
                    "这个链接返回的是网页而不是日历文件。Outlook 发布日历后会给两个链接，"
                    "要复制 <b>ICS</b> 那一行（结尾是 .ics），不是 HTML 那一行。"
                    f"（返回类型 {ctype}）"}
        # 只回显可打印的 ASCII，且不超过 80 字：这段是给人看「拿到的不是日历」的，
        # 不该变成一条把任意 URL 的响应内容读回来的通道。
        peek = "".join(c if 32 <= ord(c) < 127 else "." for c in text[:80])
        return {"ok": False, "detail": f"返回内容不是日历（没找到 BEGIN:VCALENDAR，类型 {ctype}，前 80 字：{peek!r}）"}
    try:
        evs = parse_ics(text, horizon_days)
    except Exception as e:
        return {"ok": False, "detail": "解析失败：" + str(e)}
    return {"ok": True, "count": len(evs), "events": evs}


# -------------------------------------------------------------- 定位与天气

def geo_lookup():
    """按出口 IP 粗定位。失败不影响其它功能。"""
    for url, pick in (
        ("https://ipapi.co/json/", lambda d: (d.get("city"), d.get("latitude"), d.get("longitude"), d.get("timezone"))),
        ("http://ip-api.com/json/", lambda d: (d.get("city"), d.get("lat"), d.get("lon"), d.get("timezone"))),
    ):
        r = _json(url, timeout=8)
        if r["ok"]:
            try:
                city, lat, lon, tz = pick(r["data"])
                if lat and lon:
                    return {"ok": True, "city": city or "", "lat": float(lat), "lon": float(lon), "timezone": tz or ""}
            except Exception:
                pass
    return {"ok": False, "detail": "自动定位失败，请在设置里手填城市"}


def geocode(city):
    """按城市名查经纬度。比 IP 定位可靠——挂 VPN 时 IP 会把你定位到别的国家。"""
    if not city:
        return {"ok": False, "detail": "未填城市"}
    url = ("https://geocoding-api.open-meteo.com/v1/search?name="
           + urllib.parse.quote(city) + "&count=5&language=zh")
    r = _json(url, timeout=12)
    if not r["ok"]:
        return {"ok": False, "detail": r["detail"]}
    res = (r["data"].get("results") or [])
    if not res:
        return {"ok": False, "detail": f"没找到「{city}」，换个写法试试（如 Hangzhou / 杭州市）"}
    top = res[0]
    return {"ok": True, "city": top.get("name"), "country": top.get("country", ""),
            "admin": top.get("admin1", ""), "lat": top.get("latitude"), "lon": top.get("longitude"),
            "timezone": top.get("timezone", ""),
            "alts": [{"name": x.get("name"), "admin": x.get("admin1", ""), "country": x.get("country", ""),
                      "lat": x.get("latitude"), "lon": x.get("longitude")} for x in res[:5]]}


WX = {0: "晴", 1: "晴间多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇", 51: "毛毛雨", 53: "小雨",
      55: "中雨", 56: "冻雨", 57: "冻雨", 61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
      71: "小雪", 73: "中雪", 75: "大雪", 77: "米雪", 80: "阵雨", 81: "阵雨", 82: "强阵雨",
      85: "阵雪", 86: "强阵雪", 95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷阵雨伴冰雹"}


def weather(lat, lon):
    if lat is None or lon is None:
        return {"ok": False, "detail": "未设置位置"}
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,precipitation"
           "&hourly=precipitation_probability,temperature_2m,weather_code"
           "&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"
           "&forecast_days=2&timezone=auto")
    r = _json(url, timeout=12)
    if not r["ok"]:
        return {"ok": False, "detail": r["detail"]}
    d = r["data"]
    cur = d.get("current", {})
    code = cur.get("weather_code")
    hourly = d.get("hourly", {})
    times = hourly.get("time", []) or []
    probs = hourly.get("precipitation_probability", []) or []
    temps = hourly.get("temperature_2m", []) or []
    daily = d.get("daily", {})
    tips = []
    # 未来 12 小时内首次降水概率 >= 55% 的时刻
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:00")
    try:
        i0 = times.index(now_iso)
    except ValueError:
        i0 = 0
    window = list(zip(times[i0:i0 + 12], probs[i0:i0 + 12]))
    for t, p in window:
        if p is not None and p >= 55:
            tips.append(f"☔️ {t[11:16]} 前后可能下雨（{p}%）")
            break
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    if tmax is not None and tmax >= 33:
        tips.append(f"🥵 今日最高 {round(tmax)}°C，注意防暑")
    if tmin is not None and tmin <= 2:
        tips.append(f"🧊 今日最低 {round(tmin)}°C，注意保暖")
    fut = [x for x in temps[i0:i0 + 10] if x is not None]
    if fut and cur.get("temperature_2m") is not None:
        drop = cur["temperature_2m"] - min(fut)
        if drop >= 7:
            tips.append(f"🌡 未来几小时降温约 {round(drop)}°C")
    return {
        "ok": True,
        "temp": cur.get("temperature_2m"),
        "feels": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "code": code,
        "text": WX.get(code, "—"),
        "tmax": tmax, "tmin": tmin,
        "tips": tips,
        "updated": datetime.now().strftime("%H:%M"),
    }


# ------------------------------------------------------------ GitHub 雷达

def github_search(keywords, token="", per_page=8, min_stars=20, days=365):
    """按关键词搜仓库。未登录也能用（限速较严），填 token 可提高限额。"""
    out, errors = [], []
    since = (date.today() - timedelta(days=days)).isoformat()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    for kw in (keywords or [])[:8]:
        q = f'{kw} stars:>={min_stars} pushed:>={since}'
        url = ("https://api.github.com/search/repositories?q=" +
               urllib.parse.quote(q) + f"&sort=stars&order=desc&per_page={per_page}")
        r = _json(url, headers=headers, timeout=20)
        if not r["ok"]:
            errors.append(f"{kw}: {r['detail'][:80]}")
            continue
        for it in (r["data"].get("items") or []):
            out.append({
                "keyword": kw,
                "name": it.get("full_name"),
                "url": it.get("html_url"),
                "desc": (it.get("description") or "")[:300],
                "stars": it.get("stargazers_count"),
                "language": it.get("language"),
                "updated": (it.get("pushed_at") or "")[:10],
                "topics": it.get("topics") or [],
            })
    seen, uniq = set(), []
    for r in out:
        if r["name"] in seen:
            continue
        seen.add(r["name"])
        uniq.append(r)
    uniq.sort(key=lambda x: -(x.get("stars") or 0))
    return {"ok": True, "count": len(uniq), "items": uniq[:60], "errors": errors}


def arxiv_search(keywords, max_results=8):
    """arXiv 新论文（q-fin / econ 优先）。返回标题、作者、摘要、链接。"""
    out = []
    for kw in (keywords or [])[:6]:
        q = urllib.parse.quote(f'all:"{kw}"')
        url = (f"http://export.arxiv.org/api/query?search_query={q}"
               f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}")
        ok, status, text = _req(url, timeout=20)
        if not ok:
            continue
        for entry in re.findall(r"<entry>(.*?)</entry>", text, re.S):
            def g(tag):
                m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", entry, re.S)
                return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            link = re.search(r'<id>(.*?)</id>', entry, re.S)
            out.append({
                "keyword": kw,
                "title": g("title"),
                "summary": g("summary")[:600],
                "published": g("published")[:10],
                "authors": re.findall(r"<name>(.*?)</name>", entry, re.S)[:6],
                "url": link.group(1).strip() if link else "",
            })
    seen, uniq = set(), []
    for r in out:
        k = r["title"][:80]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    uniq.sort(key=lambda x: x.get("published", ""), reverse=True)
    return {"ok": True, "count": len(uniq), "items": uniq[:40]}


# ------------------------------------------------------------------ 自检

def test_channel(kind, secrets):
    p = secrets.get("push", {})
    title = "学术工作台 · 测试消息"
    md = ("### 学术工作台 · 测试消息\n\n"
          f"如果你看到这条消息，说明**{ {'dingtalk':'钉钉','email':'邮件','custom':'自定义'}.get(kind, kind) }**通道配置成功。\n\n"
          f"> 发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if kind == "dingtalk":
        return dingtalk_send(p.get("dingtalk_webhook", ""), p.get("dingtalk_secret", ""),
                             title, md, p.get("dingtalk_keyword", ""))
    if kind == "email":
        return email_send(p.get("email", {}), title, "如果你看到这封邮件，说明邮件通道配置成功。\n"
                          f"发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if kind == "custom":
        return custom_send(p.get("custom", {}), title, md)
    return {"ok": False, "detail": "未知渠道"}


# ------------------------------------------------------------ AI 直连（可选）
# 说明：工作台的自动任务默认走订阅（Claude 信箱 + Git），不花 API 钱。
# 这一节是「另一条路」：你自己填 API key 之后，可以在工作台里直接问、直接改，
# 不用来回复制粘贴。留空则整段不生效，什么都不会发生。

AI_PROVIDERS = {
    "anthropic": {
        "name": "Claude（Anthropic）",
        "base": "https://api.anthropic.com",
        "key_hint": "sk-ant- 开头，在 console.anthropic.com 的 API keys 里建",
        "default_model": "claude-sonnet-4-5",
    },
    "openai": {
        "name": "ChatGPT（OpenAI）",
        "base": "https://api.openai.com",
        "key_hint": "sk- 开头，在 platform.openai.com 的 API keys 里建",
        "default_model": "gpt-4.1-mini",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base": "https://api.deepseek.com",
        "key_hint": "sk- 开头，在 platform.deepseek.com 的 API keys 里建；国内直连快、便宜",
        "default_model": "deepseek-chat",
    },
}

AI_ERR = {
    401: "API key 不对，或者已经被吊销",
    403: "这个 key 没有调用权限（可能是组织限制，或 key 只授权了别的用途）",
    404: "模型名写错了，换一个（下面的「列出可用模型」能查）",
    429: "触发限流或余额不足 —— 注意 API 是按量付费的，跟你的网页订阅是两个钱包",
    500: "对方服务出错，过一会儿再试",
    529: "对方过载，过一会儿再试",
}


def _ai_conf(secrets, provider=None):
    a = (secrets or {}).get("ai") or {}
    provider = provider or a.get("provider") or "anthropic"
    if provider not in AI_PROVIDERS:
        return None, {"ok": False, "detail": f"不认识的服务商：{provider}"}
    spec = AI_PROVIDERS[provider]
    key = (a.get(provider + "_key") or "").strip()
    if not key:
        return None, {"ok": False, "detail": f"还没填 {spec['name']} 的 API key"}
    base = (a.get(provider + "_base") or "").strip().rstrip("/") or spec["base"]
    model = (a.get(provider + "_model") or "").strip() or spec["default_model"]
    return {"provider": provider, "key": key, "base": base, "model": model,
            "spec": spec, "timeout": int(a.get("timeout") or 90)}, None


def _ai_request(conf, path, payload=None, method="POST"):
    url = conf["base"] + path
    headers = {"Content-Type": "application/json"}
    if conf["provider"] == "anthropic":
        headers["x-api-key"] = conf["key"]
        headers["anthropic-version"] = "2023-06-01"
    else:                                   # OpenAI 与 DeepSeek 都是同一套 Bearer + chat/completions
        headers["Authorization"] = "Bearer " + conf["key"]
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=conf["timeout"]) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            msg = (json.loads(raw).get("error") or {}).get("message") or raw[:200]
        except Exception:
            msg = raw[:200]
        hint = AI_ERR.get(e.code, "")
        return None, {"ok": False, "code": e.code,
                      "detail": f"HTTP {e.code}：{msg}" + (f" —— {hint}" if hint else "")}
    except Exception as e:
        return None, {"ok": False, "detail": f"连不上（{type(e).__name__}）：{str(e)[:120]}。"
                                             "如果你在国内直连，可能需要在设置里填一个中转地址。"}


def ai_models(secrets, provider=None):
    """列出这个 key 能用的模型，省得手敲模型名敲错。"""
    conf, err = _ai_conf(secrets, provider)
    if err:
        return err
    if conf["provider"] == "anthropic":
        d, err = _ai_request(conf, "/v1/models?limit=40", method="GET")
        if err:
            return err
        return {"ok": True, "models": [m.get("id") for m in (d.get("data") or []) if m.get("id")]}
    d, err = _ai_request(conf, "/v1/models", method="GET")
    if err:
        return err
    ids = sorted(m.get("id") for m in (d.get("data") or []) if m.get("id"))
    if conf["provider"] == "openai":
        ids = [i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))] or ids
    return {"ok": True, "models": ids}


def ai_ask(secrets, prompt, system="", provider=None, max_tokens=1500):
    """问一句，拿回一段文字。两家的接口形状不同，这里统一成一种返回。"""
    conf, err = _ai_conf(secrets, provider)
    if err:
        return err
    if conf["provider"] == "anthropic":
        payload = {"model": conf["model"], "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}
        if system:
            payload["system"] = system
        d, err = _ai_request(conf, "/v1/messages", payload)
        if err:
            return err
        text = "".join(b.get("text", "") for b in (d.get("content") or [])
                       if b.get("type") == "text")
        u = d.get("usage") or {}
        return {"ok": True, "text": text, "model": d.get("model") or conf["model"],
                "usage": {"in": u.get("input_tokens"), "out": u.get("output_tokens")}}
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload = {"model": conf["model"], "messages": msgs, "max_tokens": max_tokens}
    d, err = _ai_request(conf, "/v1/chat/completions", payload)
    if err:
        return err
    ch = (d.get("choices") or [{}])[0]
    u = d.get("usage") or {}
    return {"ok": True, "text": (ch.get("message") or {}).get("content", ""),
            "model": d.get("model") or conf["model"],
            "usage": {"in": u.get("prompt_tokens"), "out": u.get("completion_tokens")}}


def ai_test(secrets, provider=None):
    r = ai_ask(secrets, "请只回复两个字：正常", max_tokens=32, provider=provider)
    if r.get("ok"):
        return {"ok": True, "detail": f"通了 · 模型 {r.get('model')} · 回了「{(r.get('text') or '').strip()[:20]}」"}
    return r


def ai_status(secrets):
    a = (secrets or {}).get("ai") or {}
    return {
        "providers": [{"id": k, "name": v["name"], "key_hint": v["key_hint"],
                       "default_model": v["default_model"],
                       "configured": bool((a.get(k + "_key") or "").strip()),
                       "model": (a.get(k + "_model") or "").strip() or v["default_model"],
                       "base": (a.get(k + "_base") or "").strip() or v["base"]}
                      for k, v in AI_PROVIDERS.items()],
        "provider": a.get("provider") or "anthropic",
        "any": any((a.get(k + "_key") or "").strip() for k in AI_PROVIDERS),
    }


# -------------------------------------------------- 邮箱收件（手机随手记）
# 钉钉自定义机器人是单向的，读不了群消息。想在手机上随手往工作台丢东西，
# 最稳的通道是邮箱：你发一封邮件，工作台定时拉一次，自动进「待分类」。
# 用标准库 imaplib，不需要装任何东西。

def imap_fetch(cfg, limit=20):
    """把未读邮件取下来并标记已读。返回 [{subject, body, from, date}]。"""
    import imaplib
    import email as emaillib
    from email.header import decode_header, make_header

    host = (cfg.get("imap_host") or "").strip()
    user = (cfg.get("imap_user") or "").strip()
    pw = (cfg.get("imap_password") or "").strip()
    if not (host and user and pw):
        return {"ok": False, "detail": "邮箱收件没配全（服务器 / 账号 / 密码）"}
    port = int(cfg.get("imap_port") or 993)
    folder = (cfg.get("imap_folder") or "INBOX").strip() or "INBOX"
    only_from = [x.strip().lower() for x in (cfg.get("imap_only_from") or "").split(",") if x.strip()]
    subj_tag = (cfg.get("imap_subject_tag") or "").strip()

    def dec(v):
        try:
            return str(make_header(decode_header(v or "")))
        except Exception:
            return v or ""

    out = []
    try:
        M = imaplib.IMAP4_SSL(host, port, timeout=30)
    except Exception as e:
        return {"ok": False, "detail": f"连不上 {host}:{port} —— {str(e)[:90]}"}
    try:
        M.login(user, pw)
    except Exception as e:
        try:
            M.logout()
        except Exception:
            pass
        msg = str(e)[:120]
        hint = ""
        if "AUTH" in msg.upper() or "LOGIN" in msg.upper():
            hint = "（多数邮箱要用「授权码」而不是登录密码，去邮箱设置里开 IMAP 并生成一个）"
        return {"ok": False, "detail": f"登录失败：{msg}{hint}"}
    try:
        M.select(folder)
        typ, data = M.search(None, "UNSEEN")
        ids = (data[0].split() if data and data[0] else [])[-limit:]
        for i in ids:
            typ, raw = M.fetch(i, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            m = emaillib.message_from_bytes(raw[0][1])
            subject = dec(m.get("Subject"))
            sender = dec(m.get("From"))
            if only_from and not any(a in sender.lower() for a in only_from):
                continue                     # 不是自己发的就不动它，也不标已读
            if subj_tag and subj_tag.lower() not in subject.lower():
                continue
            body = ""
            if m.is_multipart():
                for part in m.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", "replace")
                        except Exception:
                            body = ""
                        break
            else:
                try:
                    body = m.get_payload(decode=True).decode(
                        m.get_content_charset() or "utf-8", "replace")
                except Exception:
                    body = ""
            out.append({"subject": subject, "from": sender,
                        "date": dec(m.get("Date")), "body": (body or "").strip()[:4000]})
            M.store(i, "+FLAGS", "\\Seen")
    except Exception as e:
        return {"ok": False, "detail": f"读取失败：{str(e)[:120]}"}
    finally:
        try:
            M.close()
            M.logout()
        except Exception:
            pass
    return {"ok": True, "items": out}


# ================================================== 学术雷达：新论文抓取
#
# 这一整段**没有一行用 AI**，这是有意的。
#
# 「每周让 AI 上网找新论文」听起来对，实际上是这套东西最容易出事的地方：
# 模型会把记不清的论文按印象写出来 —— 标题像模像样、作者是那个领域的人、
# 年份也合理，但那篇论文根本不存在。你拿着去搜，搜不到，才发现被骗了一周。
#
# 所以抓取必须是死代码：固定的 API、固定的字段、抓不到就报抓不到。
# AI 只在**后面**出场，从这里抓回来的东西里挑、并写成人话。
#
# 源的选择是实测出来的：
#   · Crossref  —— 免 key，收录范围最广，**连 NBER working paper 都有**
#                  （10.3386/* 就是 NBER）。是主力。
#   · NBER      —— 自有 API 带 newthisweek 标记，比 Crossref 快几天，
#                  经济金融的新 working paper 首发地，值得单独抓。
#   · arXiv     —— q-fin / econ 板块，覆盖面窄但更新最快。
#
# 关于「盯人」有个坑要写下来：Crossref 的 query.author 是**模糊匹配**，
# 搜 "Zhiguo He" 会把所有姓 He 的人都返回来，完全没法用来追踪特定学者。
# 可靠的只有 ORCID。所以盯人分两档：填了 ORCID 的精确追，
# 没填的退化成「姓名 + 关键词」并**明确标注为可能不准**。

CROSSREF_API = "https://api.crossref.org/works"
NBER_API = ("https://www.nber.org/api/v1/working_page_listing/contentType/"
            "working_paper/_/_/search")


def _cr_date(parts):
    """Crossref 的 date-parts → YYYY-MM-DD。缺月缺日就补 01。"""
    try:
        p = (parts or {}).get("date-parts") or [[]]
        p = p[0] or []
        y = int(p[0]) if len(p) > 0 else 0
        if not y:
            return ""
        m = int(p[1]) if len(p) > 1 else 1
        d = int(p[2]) if len(p) > 2 else 1
        return f"{y:04d}-{min(max(m,1),12):02d}-{min(max(d,1),31):02d}"
    except Exception:
        return ""


def _cr_item(it, hit_by="", hit_kind=""):
    """Crossref 的一条 → 我们的统一格式。字段名和 library 的短名对齐。"""
    au = []
    for a in (it.get("author") or [])[:12]:
        nm = " ".join(x for x in [a.get("given"), a.get("family")] if x).strip()
        if nm:
            au.append(nm)
    ct = [x for x in (it.get("container-title") or []) if x]
    pub = it.get("publisher") or ""
    doi = str(it.get("DOI") or "").strip().lower()
    ty = str(it.get("type") or "").strip()
    # NBER / CEPR 这些的 DOI 前缀能认出来是 working paper
    wp = ty in ("report", "posted-content") or doi.startswith("10.3386/")
    # 标题、年份都要按「可能缺、可能是 None、可能是空数组」来取。
    # Crossref 的响应里这几处确实会出现 [None] 和 [[]]，直接索引就崩。
    titles = [x for x in (it.get("title") or []) if x]
    try:
        dp = ((it.get("issued") or {}).get("date-parts") or [[]])[0] or []
        year = int(dp[0]) if dp and dp[0] else None
    except (TypeError, ValueError, IndexError):
        year = None
    return {
        "t": str(titles[0] if titles else "")[:400],
        "a": au,
        "y": year,
        "j": (ct[0] if ct else pub)[:200],
        "d": doi,
        "u": ("https://doi.org/" + doi) if doi else "",
        "ty": "working_paper" if wp else "article",
        "date": _cr_date(it.get("issued")) or _cr_date(it.get("created")),
        "src": "crossref",
        "hit_by": hit_by,          # 命中的是哪个关键词/哪个人
        "hit_kind": hit_kind,      # "keyword" 还是 "author"
    }


def crossref_recent(query="", since="", rows=20, orcid="", mailto=""):
    """按关键词或 ORCID 拉最近的条目。

    since 是 YYYY-MM-DD；用 from-created-date 而不是 from-pub-date ——
    正式发表日期常常滞后好几个月，而我们要的是「这周刚出现的」。
    """
    filters = []
    if since:
        filters.append(f"from-created-date:{since}")
    if orcid:
        filters.append(f"orcid:{orcid}")
    params = {
        "rows": str(max(1, min(int(rows or 20), 100))),
        "sort": "created", "order": "desc",
        "select": "DOI,title,author,issued,created,container-title,type,publisher",
    }
    if query:
        params["query.bibliographic"] = query
    if filters:
        params["filter"] = ",".join(filters)
    if mailto:
        params["mailto"] = mailto          # 进 polite pool，响应更稳
    url = CROSSREF_API + "?" + urllib.parse.urlencode(params)
    ok, status, text = _req(url, timeout=25)
    if not ok:
        return {"ok": False, "detail": f"Crossref 拉取失败（{status}）", "items": []}
    try:
        msg = (json.loads(text) or {}).get("message") or {}
    except Exception as e:
        return {"ok": False, "detail": f"Crossref 返回的不是 JSON：{e}", "items": []}
    return {"ok": True, "total": msg.get("total-results"),
            "items": msg.get("items") or []}


def nber_new(limit=40):
    """NBER 最新 working paper。比 Crossref 早几天，经济金融的首发地。"""
    url = f"{NBER_API}?page=1&perPage={max(1, min(int(limit or 40), 100))}&sortBy=public_date"
    ok, status, text = _req(url, timeout=25)
    if not ok:
        return {"ok": False, "detail": f"NBER 拉取失败（{status}）", "items": []}
    try:
        data = json.loads(text)
    except Exception as e:
        return {"ok": False, "detail": f"NBER 返回的不是 JSON：{e}", "items": []}
    rows = data.get("results") if isinstance(data, dict) else data
    out = []
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        # authors 是一串 <a> 标签，把文字抠出来
        raw_au = r.get("authors")
        if isinstance(raw_au, list):
            au = [re.sub(r"<[^>]+>", "", str(x)).strip() for x in raw_au]
        else:
            au = [x.strip() for x in re.sub(r"<[^>]+>", "|", str(raw_au or "")).split("|")]
        au = [x for x in au if x][:12]
        u = str(r.get("url") or "")
        if u.startswith("/"):
            u = "https://www.nber.org" + u
        title = re.sub(r"<[^>]+>", "", str(r.get("title") or "")).strip()
        out.append({
            "t": title[:400], "a": au,
            "y": _year_from(str(r.get("displaydate") or "")),
            "j": "NBER Working Paper", "d": "", "u": u,
            "ty": "working_paper",
            "date": str(r.get("displaydate") or ""),
            "abstract": re.sub(r"<[^>]+>", "", str(r.get("abstract") or "")).strip()[:800],
            "new_this_week": bool(r.get("newthisweek")),
            "src": "nber", "hit_by": "", "hit_kind": "",
        })
    return {"ok": True, "items": out}


def _year_from(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def radar_selftest(sources=None, mailto=""):
    """自检：四个源分别能不能连、抓回来几条。

    存在的理由：抓取依赖外网，而外网什么都可能发生 ——
    公司/学校代理挡了、对方限流、DNS 挂了。这些不该等到某个周一
    「周报怎么是空的」才发现。在设置页点一下就知道每个源是死是活。
    """
    out = []
    want = set(sources or ["crossref", "nber", "arxiv"])
    if "crossref" in want:
        r = crossref_recent(query="asset pricing", rows=3, mailto=mailto)
        out.append({"source": "Crossref", "ok": bool(r.get("ok")),
                    "n": len(r.get("items") or []), "detail": r.get("detail", ""),
                    "note": "主力源，覆盖最广，连 NBER working paper 也收"})
    if "nber" in want:
        r = nber_new(3)
        out.append({"source": "NBER", "ok": bool(r.get("ok")),
                    "n": len(r.get("items") or []), "detail": r.get("detail", ""),
                    "note": "经济金融新 working paper 的首发地，比 Crossref 早几天"})
    if "arxiv" in want:
        # arxiv_search 返回的是 {"ok":..., "count":..., "items":[...]}，不是列表。
        # 早先这里写成 len(返回值)，那是在数字典有几个键 —— 永远是 3，
        # 于是一个连不上的源被报成「✓ 3 条」。
        # 自检报告假的成功，比没有自检更糟：你会以为一切正常。
        try:
            ax = arxiv_search(["asset pricing"], max_results=3) or {}
            n = len(ax.get("items") or [])
            out.append({"source": "arXiv", "ok": bool(ax.get("ok")) and n > 0, "n": n,
                        "detail": "" if n else "连上了但没返回条目（可能被网络代理挡了）",
                        "note": "q-fin / econ，更新最快但覆盖窄"})
        except Exception as e:
            out.append({"source": "arXiv", "ok": False, "n": 0,
                        "detail": str(e)[:120], "note": ""})
    alive = [x for x in out if x["ok"]]
    return {"ok": bool(alive), "sources": out,
            "summary": (f"{len(alive)}/{len(out)} 个源可用"
                        if alive else
                        "一个源都连不上 —— 多半是网络或代理挡住了，雷达这周不会有产出")}
