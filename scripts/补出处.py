#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给箴言库补出处（一次性脚本，留档用）
============================================================================

    python3 scripts/补出处.py --dry     只看会改什么
    python3 scripts/补出处.py           真的写进 data/quotes.json

背景：库里有一百多条只写了「摘抄」的条目 —— 当年随手存下来，没记从哪看到的。
这个脚本把**查证过**的那些补上真实出处。

查证的标准（这一条比脚本本身重要）：

只有在能找到**可靠来源**明确指认出处时才补 —— 古籍原文、正规出版物、
新闻媒体、官方讲话全文、歌曲词作者页面。**语录站一律不算数**
（"励志名言100句" 那类网站会非常自信地把话安到爱因斯坦、鲁迅、
莫言头上，其中大部分是假的）。查不到就老老实实空着，
宁可写「Jay摘抄」，也不能安一个看起来很像的作者上去 ——
署错名比不署名坏得多。

按这个标准，156 条里只有 16 条查得实。其余 140 条是网络流传的无名句子、
剧集台词、歌词片段，本来就没有可考的作者。**这不是失败，这就是实情。**

下面每条后面的注释是当时的证据。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUOTES = ROOT / "data" / "quotes.json"

# id -> (出处, 证据说明)
VERIFIED = {
    "q003": ("习近平（2013 年欧美同学会讲话）",
             "讲话全文含「创新是……中华民族最深沉的民族禀赋」"),
    "q029": ("《圣经·哥林多前书》13 章",
             "和合本 13:4-5「爱是不嫉妒……不张狂……不求自己的益处」的缩写"),
    "q034": ("《辛普森一家》",
             "S5E20 校长 Skinner 台词 Am I out of touch?"),
    "q044": ("电视剧《人世间》主题曲（唐恬 词）",
             "红网报道引词作者唐恬原句"),
    "q064": ("半山《半山文集》",
             "书中原句，末句「大家一般称之为世面」是网络添补"),
    "q084": ("《淮南子·说林训》（前半句）",
             "「行一棋不足以见智，弹一弦不足以见悲」为原文；后半句是现代添加"),
    "q122": ("蔡襄",
             "《公绰示及生日以九龙泉为寿依韵奉答》末句，古诗文网全文可查"),
    "q142": ("《冰与火之歌》",
             "第一部 Ned Stark 对 Bran：唯有恐惧时人才能勇敢"),
    "q144": ("sapientdream《Past Lives》",
             "歌曲副歌反复句"),
    "q166": ("美剧《纸牌屋》",
             "Frank Underwood: Proximity to power deludes some into thinking they wield it"),
    "q176": ("歌曲《小尖尖》（薛之谦 词）",
             "《天外来物》专辑，薛之谦、韩红"),
    "q187": ("电影《流浪地球 2》",
             "周喆直联合国讲话台词"),
    "q192": ("歌曲《妈妈的话》（Zyboy 忠宇）",
             "歌词原句"),
    "q196": ("黄令仪",
             "光明日报报道「龙芯之母」黄令仪原话"),
    "q208": ("王阳明《中秋》",
             "⚠ 通行本作「吾心自有光明月，千古团圆永无缺」——"
             "库里这条「自由」「无残缺」两处与原文有出入，需要你确认要不要改"),
    "q252": ("《宋史·范纯仁传》",
             "范纯仁「以责人之心责己，恕己之心恕人」，后收入《格言联璧》"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    data = json.loads(QUOTES.read_text(encoding="utf-8"))
    by_id = {x.get("id"): x for x in data["quotes"]}
    changed, missing = [], []

    for qid, (src, why) in VERIFIED.items():
        q = by_id.get(qid)
        if not q:
            missing.append(qid)
            continue
        old = (q.get("s") or "").strip()
        if old == src:
            continue
        changed.append((qid, old or "(空)", src, q["t"][:34], why))
        if not args.dry:
            q["s"] = src

    for qid, old, new, txt, why in changed:
        print(f"  {qid}  {old} → {new}")
        print(f"        「{txt}…」")
        print(f"        依据：{why}")
    if missing:
        print("  ! 库里找不到这些 id：", ", ".join(missing))

    still = [x for x in data["quotes"] if (x.get("s") or "").strip() in {"摘抄", ""}]
    print(f"\n  补上 {len(changed)} 条；仍然没有出处的还有 {len(still)} 条 —— "
          f"这些在公开版里会署「Jay摘抄」。")

    if not args.dry:
        QUOTES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  已写回 {QUOTES}")
    else:
        print("  （--dry，没有写入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
