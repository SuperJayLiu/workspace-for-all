#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日历订阅的时区换算体检

背景：Outlook 发布的 ICS 里，时间是「某个时区的墙上时间」，
形如 DTSTART;TZID="Eastern Standard Time":20260804T090000。
早期版本直接把 090000 当本机时间显示，纽约同事约的 9 点在伦敦也显示 9 点，
实际该是下午 2 点 —— 跨时区开会的人会因此错过会议。

这套测试锁住换算行为，覆盖：
  · Outlook 的 Windows 时区名 + 自带 VTIMEZONE 规则
  · 夏令时 / 冬令时两侧（同一个时区，不同月份，偏移不同）
  · 无 DST 的时区（北京）
  · UTC 的 Z 后缀
  · IANA 时区名（Google / Apple）
  · 整天事件不换算
  · 浮动时间按本机处理
  · 换算导致跨日
  · 南半球（新西兰，DST 与北半球相反）
"""
import os
import sys
import time
from pathlib import Path

os.environ["TZ"] = "Europe/London"          # 固定观察点，否则结果依赖跑测试的机器
try:
    time.tzset()
except AttributeError:                       # Windows 没有 tzset
    print("跳过：Windows 上无法固定测试时区（功能本身不受影响）")
    sys.exit(0)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import services as sv                        # noqa: E402

FAIL = []


def check(name, cond, got=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"   实际={got}"))
    if not cond:
        FAIL.append(name)


VTIMEZONES = """BEGIN:VTIMEZONE
TZID:GMT Standard Time
BEGIN:STANDARD
DTSTART:16011028T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010325T010000
TZOFFSETFROM:+0000
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VTIMEZONE
TZID:Eastern Standard Time
BEGIN:STANDARD
DTSTART:16011101T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010308T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VTIMEZONE
TZID:China Standard Time
BEGIN:STANDARD
DTSTART:16010101T000000
TZOFFSETFROM:+0800
TZOFFSETTO:+0800
END:STANDARD
END:VTIMEZONE
BEGIN:VTIMEZONE
TZID:New Zealand Standard Time
BEGIN:STANDARD
DTSTART:16010405T030000
TZOFFSETFROM:+1300
TZOFFSETTO:+1200
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010927T020000
TZOFFSETFROM:+1200
TZOFFSETTO:+1300
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=9
END:DAYLIGHT
END:VTIMEZONE
"""


def ev(uid, summary, dtstart):
    return f"BEGIN:VEVENT\nUID:{uid}\nSUMMARY:{summary}\nDTSTART{dtstart}\nEND:VEVENT\n"


CASES = [
    # (标题, DTSTART 片段, 期望日期, 期望时间)
    ("同区：伦敦 14:00 夏令时", ';TZID="GMT Standard Time":20260803T140000', "2026-08-03", "14:00"),
    ("同区：伦敦 14:00 冬令时", ';TZID="GMT Standard Time":20261214T140000', "2026-12-14", "14:00"),
    ("美东夏令时 09:00 → 伦敦 14:00", ';TZID="Eastern Standard Time":20260804T090000', "2026-08-04", "14:00"),
    ("美东冬令时 09:00 → 伦敦 14:00", ';TZID="Eastern Standard Time":20261204T090000', "2026-12-04", "14:00"),
    ("北京 20:00 → 伦敦 13:00", ';TZID="China Standard Time":20260805T200000', "2026-08-05", "13:00"),
    ("UTC 09:00Z → 伦敦 10:00", ":20260806T090000Z", "2026-08-06", "10:00"),
    ("IANA 名 东京 10:00 → 伦敦 02:00", ";TZID=Asia/Tokyo:20260807T100000", "2026-08-07", "02:00"),
    ("浮动时间 15:00 按本机处理", ":20260811T150000", "2026-08-11", "15:00"),
    ("换算跨日：美东 22:00 → 伦敦次日 03:00", ';TZID="Eastern Standard Time":20260812T220000', "2026-08-13", "03:00"),
    ("南半球：新西兰 1 月 09:00 → 伦敦前一天 20:00",
     ';TZID="New Zealand Standard Time":20270115T090000', "2027-01-14", "20:00"),
    ("南半球：新西兰 7 月 09:00 → 伦敦 22:00",
     ';TZID="New Zealand Standard Time":20260715T090000', "2026-07-14", "22:00"),
]

ics = ("BEGIN:VCALENDAR\nVERSION:2.0\n" + VTIMEZONES
       + "".join(ev(f"u{i}", c[0], c[1]) for i, c in enumerate(CASES))
       + ev("allday", "整天：投稿截止", ";VALUE=DATE:20260810")
       + "END:VCALENDAR\n")

events = {e["title"]: e for e in sv.parse_ics(ics, horizon_days=600)}

print("=" * 60)
print("日历时区换算")
for title, _src, want_d, want_t in CASES:
    e = events.get(title) or {}
    check(title, (e.get("date"), e.get("time")) == (want_d, want_t),
          (e.get("date"), e.get("time")))

print("\n整天事件不做换算")
ad = events.get("整天：投稿截止") or {}
check("日期保持 2026-08-10", ad.get("date") == "2026-08-10", ad.get("date"))
check("没有时间、标为整天", ad.get("time") is None and ad.get("all_day") is True,
      (ad.get("time"), ad.get("all_day")))

print("\n换算留痕（界面用来显示「原 09:00 · 某时区」）")
e = events.get("美东夏令时 09:00 → 伦敦 14:00") or {}
check("留下原时区名", e.get("src_tz") == "Eastern Standard Time", e.get("src_tz"))
check("留下原墙上时间", e.get("src_time") == "09:00", e.get("src_time"))
same = events.get("同区：伦敦 14:00 夏令时") or {}
check("同区不留痕（钟点没变就不啰嗦）", not same.get("src_tz"), same.get("src_tz"))

print("\n坏数据不能把整个订阅搞崩")
broken = """BEGIN:VCALENDAR
BEGIN:VTIMEZONE
TZID:Broken Zone
BEGIN:STANDARD
TZOFFSETTO:不是偏移
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:x
SUMMARY:时区坏了的事件
DTSTART;TZID="Broken Zone":20260901T100000
END:VEVENT
BEGIN:VEVENT
UID:y
SUMMARY:引用了不存在的时区
DTSTART;TZID="No Such Zone At All":20260902T100000
END:VEVENT
BEGIN:VEVENT
UID:z
SUMMARY:日期本身是垃圾
DTSTART;TZID="Broken Zone":这不是日期
END:VEVENT
END:VCALENDAR
"""
try:
    out = sv.parse_ics(broken, horizon_days=600)
    titles = [x["title"] for x in out]
    check("没抛异常", True)
    check("坏时区退回按本机时间显示", "时区坏了的事件" in titles, titles)
    check("未知时区退回按本机时间显示", "引用了不存在的时区" in titles, titles)
    check("垃圾日期被丢弃而不是崩掉", "日期本身是垃圾" not in titles, titles)
except Exception as exc:
    check("没抛异常", False, repr(exc))

print("\n重复事件：取消、改期、以及逐次换算夏令时")
NY_TZ = """BEGIN:VTIMEZONE
TZID:Eastern Standard Time
BEGIN:STANDARD
DTSTART:16011101T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010308T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
"""
REC = ("BEGIN:VCALENDAR\n" + NY_TZ +
       "BEGIN:VEVENT\nUID:weekly@x\nSUMMARY:纽约周会\n"
       'DTSTART;TZID="Eastern Standard Time":20261019T090000\n'
       "RRULE:FREQ=WEEKLY;COUNT=6\n"
       'EXDATE;TZID="Eastern Standard Time":20261102T090000\n'
       "END:VEVENT\n"
       "BEGIN:VEVENT\nUID:weekly@x\n"
       'RECURRENCE-ID;TZID="Eastern Standard Time":20261109T090000\n'
       "SUMMARY:纽约周会（改到下午）\n"
       'DTSTART;TZID="Eastern Standard Time":20261109T150000\n'
       "END:VEVENT\nEND:VCALENDAR\n")
evs = sv.parse_ics(REC, horizon_days=800)
by = {e["date"]: e for e in evs}
check("EXDATE 取消的那次不再出现", "2026-11-02" not in by, sorted(by))
check("改期那次只出现一次", sum(1 for e in evs if e["date"] == "2026-11-09") == 1,
      [e["date"] for e in evs])
check("改期那次用的是新时间（NY 15:00 → 伦敦 20:00）",
      by.get("2026-11-09", {}).get("time") == "20:00", by.get("2026-11-09"))
# 逐次换算才是重点：英国 10/25 回冬令时，纽约 11/1 才回，中间这一周差一小时
check("两地都在夏令时：14:00", by.get("2026-10-19", {}).get("time") == "14:00",
      by.get("2026-10-19"))
check("英国已回冬令时、纽约还没：13:00（只换算一次的话会错成 14:00）",
      by.get("2026-10-26", {}).get("time") == "13:00", by.get("2026-10-26"))
check("两地都回冬令时：14:00", by.get("2026-11-16", {}).get("time") == "14:00",
      by.get("2026-11-16"))

CANCEL = ("BEGIN:VCALENDAR\n" + NY_TZ +
          "BEGIN:VEVENT\nUID:c@x\nSUMMARY:会被整场取消的\n"
          'DTSTART;TZID="Eastern Standard Time":20261019T090000\n'
          "RRULE:FREQ=WEEKLY;COUNT=3\nEND:VEVENT\n"
          "BEGIN:VEVENT\nUID:c@x\n"
          'RECURRENCE-ID;TZID="Eastern Standard Time":20261026T090000\n'
          "STATUS:CANCELLED\nSUMMARY:会被整场取消的\n"
          'DTSTART;TZID="Eastern Standard Time":20261026T090000\n'
          "END:VEVENT\nEND:VCALENDAR\n")
cd2 = [e["date"] for e in sv.parse_ics(CANCEL, horizon_days=800)]
check("STATUS:CANCELLED 的那次被剔除", "2026-10-26" not in cd2, cd2)

MULTI = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:m@x\nSUMMARY:每天\n"
         "DTSTART:20261201T090000Z\nRRULE:FREQ=DAILY;COUNT=5\n"
         "EXDATE:20261202T090000Z,20261204T090000Z\n"
         "END:VEVENT\nEND:VCALENDAR\n")
md = sorted(e["date"] for e in sv.parse_ics(MULTI, horizon_days=800))
check("一行写多个 EXDATE 都生效", md == ["2026-12-01", "2026-12-03", "2026-12-05"], md)

print("=" * 60)
if FAIL:
    print(f"日历时区测试：{len(FAIL)} 条不通过 ✗")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("日历时区测试：全部通过 ✓")
