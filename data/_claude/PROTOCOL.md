# Claude 工作协议 · 读我

这份文件是给 **Claude**（以及任何接手这个工作台的 AI）看的操作规范。
用户只需在 Cowork 会话里说一句「**处理工作台信箱**」，或让定时任务自动触发。

---

## 0. 这个仓库是什么

一个单人学术工作台的数据层。界面是本机跑的 `server.py` + 浏览器，
但**你不需要界面**——所有内容都是 Markdown（YAML frontmatter），直接读写文件即可。

```
data/manuscripts/*.md    稿件（含 timeline 投稿生命周期）
data/journals/*.md       期刊档案
data/published/*.md      已发表
data/conferences/*.md    会议
data/reading/*.md        文献结构化笔记（含 reviews 复习记录）
data/levels/*.md         闯关主题
data/ideas/*.md          想法便利贴
data/schedule/*.md       日程
data/reports/*.md        AI 报告库  ← 你的产出写这里
data/retros/*.md         复盘
data/config.json         用户设置
data/_claude/
  inbox.md               用户写给你的请求（处理完要清理）
  outbox/*.md            你的回信
  audits/*.md            体检报告
  ledger.md              想法台账（去重用，**必读必写**）
  quota.json             额度调度器状态
  queue.json             自动任务队列
  next-run.json          调度器给出的本次建议（含预算与选中的任务）
```

`local/` 目录**不在仓库里**（生活数据与密钥留在用户本机），看不到是正常的。

## 1. 处理信箱的标准流程

1. 读 `data/_claude/inbox.md`。逐条处理（每条以 `## 日期 · 标题` 开头）。
2. **先读 `ledger.md`**，确认你要提的东西不是以前提过或被否决过的。
3. 干活。需要文献时**必须**使用 `academic-literature-review` 技能，禁止编造引用。
4. 产出写成 `data/reports/<slug>.md`（frontmatter 见下），并在 `data/_claude/outbox/` 放一份同名副本方便界面直接查看。
5. 把新想法追加进 `ledger.md`。
6. 从 `inbox.md` 移除已处理条目（保留标题行加 `✅ 已处理 <日期>` 一行即可）。
7. 如果改了任何数据文件，`git add -A && git commit && git push`。

报告文件的 frontmatter：

```yaml
---
title: 简短标题
kind: brainstorm | gap-scan | method-scan | data-scan | critique | audit | review-draft | quiz
source: auto            # 自动任务用 auto；用户主动要的用 claude
date: 2026-07-29
status: unread
ref: manuscripts:<id>   # 关联记录，可空
---
```

## 2. 自动任务（无人值守时）

读 `next-run.json`，里面是调度器基于额度算出的 `budget` 和选中的 `chosen` 任务列表。
**只做 `chosen` 里的任务，不要自作主张加量。** 做完把每次运行追加进 `quota.json` 的 `runs`
（`{ts, kind, cost, ok, note}`，cost：light=1 / medium=3 / heavy=8），并把 `spent_this_week` 相应增加。

五类任务的硬性要求：

- **brainstorm 头脑风暴**：必须锚定一份真实稿件或一批文献笔记。**每次最多 3 条**，每条给出：新角度、为什么现在可行、需要什么数据、最可能的反驳。与 ledger 重复的一律丢弃。
- **gap-scan 文献缺口扫描**：每条缺口必须附真实可核对的文献（作者-年份-期刊）。不确定的标 `【待核实】`，不得混入正文当作已确认。
- **method-scan 新方法扫描**：给出方法出处、核心思想、适用条件、相对现有做法的改进。
- **data-scan 新数据整理**：**只给描述和链接，不要下载数据**。每条含：数据名、覆盖范围与频率、获取链接、使用限制、能回答什么问题。
- **audit 全库体检**：见下节。这是余量扫尾的默认任务，永远有得做。

## 3. 全库体检（audit）

检查六类问题，产出 `data/_claude/audits/YYYY-MM-DD.md`：

1. **内部矛盾** — 如 stage 写着 `submitted` 但 timeline 最后一条是 `rejected`；current_journal 与 timeline 不符。
2. **过期未动** — 投出去超过 90 天没有新事件；next_action_due 已过期。
3. **事实错误** — DOI 格式/可解析性、期刊名拼写、会议日期、失效链接。
4. **引用真伪** — reading 与 reports 中的文献是否真实存在（必须核验，宁可标"无法确认"）。
5. **缺失** — 引用了但磁盘上不存在的附件、必填字段为空。
6. **重复** — 同一篇文献/期刊录了两次。

**只提议，不擅自修改。** 每条给出：严重程度（高/中/低）、位置（文件名）、问题、建议的修正值。
唯一允许自动执行的是给失效链接加标记。

## 4. 三条不可违反的规则

1. **不编造引用。** 任何文献必须真实可核对；不确定就明说。
2. **不擅自改用户的记录。** 除非用户在 inbox 里明确要求，你只写 `reports/`、`outbox/`、`audits/`、`ledger.md`。
3. **不超预算。** `next-run.json` 里的 budget 是硬上限；宁可少做。

## 5. 去重台账 `ledger.md` 的格式

```
- [new] intermediary-china-nonlinear · 中国市场中介约束的非线性检验 · 2026-07-29
- [rejected] wechat-diffusion · 微信小程序做技术扩散 · 2026-06-02 · 用户否决：数据不可得
```

提新想法前先扫一遍指纹（短横线 slug）和描述，**语义相近也算重复**。
用户在界面上标「采纳/否决」时，状态会同步到这里——被否决过的方向不要再提。
