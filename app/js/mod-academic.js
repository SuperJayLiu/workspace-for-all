/* 学术生产：稿件库 / 期刊库 / 已刊论文 / 学术会议 */

const STAGES = [
  { v: "idea", t: "选题" }, { v: "writing", t: "写作" }, { v: "analysis", t: "分析" },
  { v: "submitted", t: "在投" }, { v: "rnr", t: "R&R" }, { v: "accepted", t: "接收" },
  { v: "published", t: "已发表" }, { v: "shelved", t: "搁置" },
];
const STAGE_T = Object.fromEntries(STAGES.map(s => [s.v, s.t]));
const EVENTS = [
  { v: "started", t: "启动" }, { v: "draft", t: "初稿完成" }, { v: "submitted", t: "投稿" },
  { v: "desk-reject", t: "编辑部退稿" }, { v: "rejected", t: "拒稿" }, { v: "rnr", t: "R&R" },
  { v: "resubmitted", t: "返修再投" }, { v: "accepted", t: "接收" },
  { v: "published", t: "发表" }, { v: "withdrawn", t: "撤稿" }, { v: "note", t: "备注" },
];
const EVENT_T = Object.fromEntries(EVENTS.map(e => [e.v, e.t]));
const NEG = ["desk-reject", "rejected", "withdrawn"], POS = ["accepted", "published", "rnr"];

/* ---------------------------------------------------------- 字段 schema */
window.schema_manuscripts = () => [
  { k: "title", label: "题目", type: "text", wide: true },
  { k: "stage", label: "阶段", type: "select", opts: STAGES },
  { k: "progress", label: "进度 %", type: "number" },
  { k: "coauthors", label: "合作者", type: "tags" },
  { k: "target_journal", label: "目标期刊", type: "text" },
  { k: "current_journal", label: "当前在投期刊", type: "text" },
  { k: "next_action", label: "下一步", type: "text", wide: true },
  { k: "next_action_due", label: "下一步截止", type: "date" },
  { k: "folder", label: "论文文件夹", type: "text", wide: true, hint: "绝对路径，或相对于设置里的「论文根目录」" },
  { k: "overleaf", label: "Overleaf 项目地址", type: "url", wide: true, hint: "填了就能一键跳转；如果你是付费版并在设置里配了 Git token，工作台每天还会自动读出「今天改了什么」记进手帐" },
  { k: "tex_folder", label: "本地 LaTeX 目录（不用付费 Overleaf 的填这个）", type: "text", wide: true, hint: "指向本机存 .tex 的文件夹，只要它是个 git 仓库，就能算出「今天改了哪几节、净增多少行」——跟 Overleaf 付费版一样的进展记录，不花钱。还不是仓库的话，在那个目录里跑一次 git init && git add -A && git commit -m 初始" },
  { k: "repo", label: "代码仓库", type: "url", wide: true },
  { k: "tags", label: "标签", type: "tags" },
];
window.schema_journals = () => [
  { k: "title", label: "期刊名", type: "text", wide: true },
  { k: "tier", label: "档次/分区", type: "text" },
  { k: "field", label: "领域", type: "text" },
  { k: "issn", label: "ISSN", type: "text" },
  { k: "stated_review_days", label: "官方审稿周期(天)", type: "number" },
  { k: "fee", label: "版面费", type: "text" },
  { k: "url", label: "主页", type: "url" },
  { k: "portal", label: "投稿入口", type: "url" },
];
window.schema_published = () => [
  { k: "title", label: "题目", type: "text", wide: true },
  { k: "journal", label: "期刊", type: "text" },
  { k: "year", label: "年份", type: "number" },
  { k: "volume", label: "卷期页", type: "text" },
  { k: "doi", label: "DOI", type: "text" },
  { k: "url", label: "链接", type: "url" },
  { k: "coauthors", label: "合作者", type: "tags" },
  { k: "cites", label: "被引", type: "number" },
  { k: "folder", label: "复现文件位置", type: "text", wide: true },
];
window.schema_conferences = () => [
  { k: "title", label: "会议名", type: "text", wide: true },
  { k: "deadline", label: "投稿截止", type: "date" },
  { k: "notify_date", label: "通知日期", type: "date" },
  { k: "start", label: "开始日期", type: "date" },
  { k: "end", label: "结束日期", type: "date" },
  { k: "location", label: "地点", type: "text" },
  { k: "fee", label: "注册费", type: "text" },
  { k: "submitted", label: "投了哪篇", type: "text" },
  { k: "status", label: "状态", type: "select", opts: [{ v: "watching", t: "关注" }, { v: "submitted", t: "已投" }, { v: "accepted", t: "已接收" }, { v: "attending", t: "将参加" }, { v: "done", t: "已结束" }] },
  { k: "url", label: "链接", type: "url" },
];

/* ------------------------------------------------------------ 计算函数 */
function journalExperience(name) {
  if (!name) return null;
  const key = String(name).trim().toLowerCase();
  let n = 0, total = 0, outcomes = { rejected: 0, rnr: 0, accepted: 0 };
  rows("manuscripts").forEach(m => {
    const tl = (m.timeline || []).slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
    let subDate = null;
    tl.forEach(ev => {
      const j = String(ev.journal || "").trim().toLowerCase();
      if (ev.event === "submitted" || ev.event === "resubmitted") { if (j === key) subDate = ev.date; }
      else if (subDate && j === key && ["rejected", "desk-reject", "rnr", "accepted"].includes(ev.event)) {
        const d = daysBetween(subDate, ev.date);
        if (d != null && d >= 0) { n++; total += d; }
        if (ev.event === "rnr") outcomes.rnr++;
        else if (ev.event === "accepted") outcomes.accepted++;
        else outcomes.rejected++;
        subDate = null;
      }
    });
  });
  return n ? { n, avg: Math.round(total / n), outcomes } : null;
}

function msLastEvent(m) {
  const tl = (m.timeline || []).slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
  return tl[0] || null;
}
function msDaysSinceUpdate(m) {
  const last = msLastEvent(m);
  const d = last ? last.date : (m.updated || "").slice(0, 10);
  const n = daysBetween(d, todayStr());
  return n == null ? null : n;
}
function msInReviewDays(m) {
  const tl = (m.timeline || []).slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
  let subDate = null;
  tl.forEach(ev => {
    if (ev.event === "submitted" || ev.event === "resubmitted") subDate = ev.date;
    else if (["rejected", "desk-reject", "rnr", "accepted", "withdrawn"].includes(ev.event)) subDate = null;
  });
  return subDate ? { since: subDate, days: daysBetween(subDate, todayStr()) } : null;
}

/* --------------------------------------------------------- 图表加载 */
S._figs = {};
function resolveFolder(folder) {
  if (!folder) return "";
  const root = (S.device.paper_root || "").replace(/[\/\\]+$/, "");
  if (/^([a-zA-Z]:[\\\/]|[\\\/]|~)/.test(folder)) return folder;
  return root ? root + "/" + folder : folder;
}
async function loadFigures(id, folder) {
  const base = resolveFolder(folder);
  if (!base) return;
  const seen = [];
  const scan = async p => {
    try {
      const r = await API.get("tree?path=" + encodeURIComponent(p));
      if (!r.ok) return [];
      return r.entries.map(e => Object.assign({}, e, { path: p.replace(/[\/\\]+$/, "") + "/" + e.name }));
    } catch (e) { return []; }
  };
  const top = await scan(base);
  const dirs = top.filter(e => e.dir && /^(figures?|tables?|output|results|figs|exhibits)$/i.test(e.name));
  let files = top.filter(e => !e.dir);
  for (const d of dirs) files = files.concat((await scan(d.path)).filter(e => !e.dir));
  const figs = files.filter(f => /\.(pdf|png|jpe?g|svg|webp)$/i.test(f.name)).slice(0, 24);
  S._figs[id] = figs;
  const slot = document.querySelector(`[data-figs="${id}"]`);
  if (slot) {
    const m = byId("manuscripts", id) || {};
    slot.innerHTML = UI.gallery(figs, { pinTo: id, pinned: m.pinned_figure });
    UI.afterRender();
  }
}

/* ------------------------------------------------------------- 稿件库 */
VIEWS.manuscripts = () => {
  const ms = rows("manuscripts");
  const active = ms.filter(m => !["published", "shelved"].includes(m.stage));
  const inReview = ms.filter(m => m.stage === "submitted" || m.stage === "rnr");
  const stale = active.filter(m => (msDaysSinceUpdate(m) || 0) >= (S.config.stale_manuscript_days || 7));

  const tut = UI.tut("manuscripts", "稿件库怎么用", `
    <p>每篇论文一张卡。上面那排<b>阶段按钮</b>点一下就切换（不用打字），下面的<b>进度条可以直接拖</b>。</p>
    <p><b>生命周期时间线</b>是这个库的核心：每次投稿、被拒、R&R、转投都点「＋ 记录事件」加一条。有了这些记录，系统会自动算出你在每家期刊的<b>真实审稿周期</b>（显示在期刊库里），也会自动生成复盘。</p>
    <p>把论文文件夹填进去（绝对路径，或相对于设置里的「论文根目录」），卡片会自动扫描 <code>figures/</code> <code>tables/</code> 里的图表并渲染出来；点图上的 ☆ 可以<b>钉住主结果</b>，让它常驻卡片顶部。</p>
    <p>看板区可以把卡片<b>拖到另一个阶段</b>。超过 ${S.config.stale_manuscript_days || 7} 天没有任何事件的稿件会被标为「停滞」提醒你。</p>`);

  const stats = `<div class="grid g4" style="margin-bottom:14px">
    <div class="stat"><div class="k">进行中</div><div class="v">${active.length}</div><div class="d">共 ${ms.length} 篇</div></div>
    <div class="stat ${inReview.length ? "warn" : ""}"><div class="k">在投 / R&R</div><div class="v">${inReview.length}</div>
      <div class="d">${inReview.map(m => esc(m.current_journal || m.target_journal || "?")).join("、") || "—"}</div></div>
    <div class="stat ${stale.length ? "alert" : "good"}"><div class="k">停滞 ≥${S.config.stale_manuscript_days || 7}天</div><div class="v">${stale.length}</div><div class="d">需要推动</div></div>
    <div class="stat"><div class="k">已发表</div><div class="v">${rows("published").length}</div><div class="d">见「已刊论文」</div></div>
  </div>`;

  const kanban = `<div class="kanban">` + STAGES.filter(s => s.v !== "shelved").map(s => {
    const list = ms.filter(m => m.stage === s.v);
    return `<div class="kcol" data-stage="${s.v}" data-stage-name="${s.t}" data-field="stage">
      <h4>${s.t}<span class="n">${list.length}</span></h4>
      ${list.map(m => `<div class="kcard" draggable="true" data-coll="manuscripts" data-id="${m.id}">
        <div class="t">${esc(m.title || "（未命名）")}</div>
        <div class="m">${esc(m.current_journal || m.target_journal || "")}${m.progress ? " · " + m.progress + "%" : ""}</div>
      </div>`).join("")}
    </div>`;
  }).join("") + `</div>`;

  /* 每张稿件卡都会把整条生命周期、结果图占位、正文一起画出来，
     一张卡上百个 DOM 节点。压测 200 篇时研究页 22611 个节点。
     跟日程页一个道理：封顶 + 「再显示」。
     排序已经把最该看的放前面（在投/R&R 在前），所以截断是安全的。 */
  const MS_STEP = 40;
  const msMax = S._msMax || MS_STEP;
  const msShown = ms.slice(0, msMax);
  const msRest = ms.length - msShown.length;
  const cards = msShown.map(m => {
    const exp = journalExperience(m.current_journal);
    const rev = msInReviewDays(m);
    const stale2 = (msDaysSinceUpdate(m) || 0) >= (S.config.stale_manuscript_days || 7) && !["published", "shelved"].includes(m.stage);
    const tl = (m.timeline || []).slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
    const due = daysUntil(m.next_action_due);
    const pinned = m.pinned_figure;
    return UI.card("ms:" + m.id, m.title || "（未命名）", "", `
      <div style="display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-bottom:9px">
        ${UI.seg(STAGES, m.stage, "manuscripts", m.id, "stage")}
        <div style="flex:1;min-width:170px">${UI.prog(m.progress, `data-prog-coll="manuscripts" data-prog-id="${m.id}"`)}</div>
      </div>
      ${pinned ? `<div class="pinned-figure" style="margin-bottom:10px">
          <div class="tiny muted" style="margin-bottom:4px">📌 当前主结果</div>
          <div class="fig-slot" data-src="${esc(pinned)}">载入中…</div></div>` : ""}
      <div class="grid g2">
        <div>
          <div class="small"><b>下一步</b>：${esc(m.next_action || "—")}
            ${m.next_action_due ? `<span class="badge">${esc(m.next_action_due)}</span>${daysChip(due)}` : ""}</div>
          <div class="small muted" style="margin-top:3px">
            ${m.coauthors && m.coauthors.length ? "合作者：" + esc([].concat(m.coauthors).join("、")) + " · " : ""}
            ${m.current_journal ? "在投：" + esc(m.current_journal) : (m.target_journal ? "目标：" + esc(m.target_journal) : "")}
          </div>
          ${rev ? `<div class="small" style="margin-top:4px">⏱ 已在 ${esc(m.current_journal || "该刊")} 审稿 <b>${rev.days}</b> 天（自 ${esc(rev.since)}）
            ${exp ? `<span class="muted">· 你在这家的历史均值 ${exp.avg} 天</span>` : ""}</div>` : ""}
          ${stale2 ? `<div class="small" style="color:var(--amber);margin-top:4px">⚠️ 已 ${msDaysSinceUpdate(m)} 天没有任何事件</div>` : ""}
        </div>
        <div>
          <div class="tiny muted">生命周期 · ${tl.length} 条事件</div>
          <div class="tl">${tl.length ? tl.map(ev => `<div class="tl-item ${NEG.includes(ev.event) ? "neg" : POS.includes(ev.event) ? "pos" : ""}">
            <div class="d">${esc(ev.date || "")}</div>
            <div class="e">${esc(EVENT_T[ev.event] || ev.event || "")} ${ev.journal ? `<span class="badge">${esc(ev.journal)}</span>` : ""}</div>
            ${ev.note ? `<div class="n">${esc(ev.note)}</div>` : ""}</div>`).join("")
        : `<div class="empty">还没有事件</div>`}</div>
        </div>
      </div>
      ${m.folder ? `<div class="hr"></div><div class="tiny muted" style="margin-bottom:6px">📊 结果图表 · ${esc(resolveFolder(m.folder))}</div>
        <div data-figs="${m.id}" data-folder="${esc(m.folder)}"><div class="empty">扫描中…</div></div>` : ""}
      ${(m.body || m._preview) ? `<div class="hr"></div><div class="small" style="white-space:pre-wrap">${
        esc(m.body || m._preview)}${
        m._body_more ? `… <a href="#" data-fullbody="manuscripts:${m.id}">展开全文</a>` : ""}</div>` : ""}
    `, {
      icon: stale2 ? "⚠️" : "📄",
      actions: `<span class="badge ${m.stage === "rnr" ? "a" : m.stage === "accepted" ? "g" : "b"}">${STAGE_T[m.stage] || m.stage || "—"}</span>${UI.linkBadge(m)}
        <button class="btn sm" data-event="${m.id}">＋ 记录事件</button>
        <button class="btn sm" data-ai="manuscripts:${m.id}">🤖 问 AI</button>
        <button class="btn sm" data-edit="manuscripts:${m.id}">编辑</button>`,
    });
  }).join("");

  const msMore = msRest > 0
    ? `<div style="margin:10px 0;display:flex;gap:8px;align-items:center">
         <button class="btn" id="msMore">再显示 ${Math.min(MS_STEP, msRest)} 篇</button>
         <span class="small muted">还有 ${msRest} 篇没展开（在投和 R&R 的排在前面）</span></div>`
    : "";
  MS_PARTS = { kanban: UI.card("ms-kanban", "阶段看板（可拖动）", "Kanban", kanban, { icon: "🗂" }),
               cards: cards + msMore };
  return `<div class="page-head"><h1>📄 稿件库</h1><div class="sub">选题 → 写作 → 投稿 → 审稿 → 转投 → 发表</div>
    <span class="spacer"></span>
    <button class="btn primary" data-new="manuscripts">＋ 新稿件</button></div>
    ${tut}${stats}
    ${MS_PARTS.kanban}
    ${cards ? cards + msMore : `<div class="empty">还没有稿件，点右上角新建。</div>`}`;
};

/* 「研究」页要复用看板与卡片，这里把它们单独产出一份 */
let MS_PARTS = { kanban: "", cards: "" };
window.manuscriptSections = function () {
  VIEWS.manuscripts();          // 走一遍生成，副作用是填好 MS_PARTS
  return MS_PARTS;
};

/* ------------------------------------------------------------- 期刊库 */
VIEWS.journals = () => {
  const js = rows("journals");
  const tut = UI.tut("journals", "期刊库怎么用", `
    <p>这里是你的目标期刊档案。最有价值的一列是<b>「你的实际经历」</b>——它不是抄来的官方说法，而是<b>从你自己的稿件时间线自动算出来的</b>：这家期刊平均让你等了多少天、拒了几次、给过几次 R&R。</p>
    <p>所以你只要坚持在稿件库里记录投稿事件，这张表会自己长出来，越用越准。</p>
    <p>已有的 Excel 期刊清单可以在「设置」页一键导入，不用重录。</p>`);
  const groups = {};
  js.forEach(j => { (groups[j.tier || "未分组"] = groups[j.tier || "未分组"] || []).push(j); });
  const body = Object.keys(groups).sort().map(tier => {
    const list = groups[tier].slice().sort((a, b) => String(a.title).localeCompare(String(b.title)));
    return UI.card("jr:" + tier, tier, `${list.length} 家`, `<div class="scroll-x"><table class="tbl">
      <tr><th>期刊</th><th>领域</th><th>你的实际经历</th><th>官方周期</th><th>版面费</th><th></th></tr>
      ${list.map(j => {
      const e = journalExperience(j.title);
      return `<tr>
          <td><b>${esc(j.title || "")}</b>${j.url ? ` <a href="${esc(j.url)}" target="_blank">↗</a>` : ""}
            ${j.portal ? `<div class="tiny"><a href="${esc(j.portal)}" target="_blank">投稿入口</a></div>` : ""}</td>
          <td class="small">${esc(j.field || "")}</td>
          <td class="small">${e ? `<b>${e.avg} 天</b> · ${e.n} 次
              <div class="tiny muted">拒 ${e.outcomes.rejected} · R&R ${e.outcomes.rnr} · 接收 ${e.outcomes.accepted}</div>`
          : `<span class="muted">暂无记录</span>`}</td>
          <td class="small">${j.stated_review_days ? j.stated_review_days + " 天" : "—"}</td>
          <td class="small">${esc(j.fee || "—")}</td>
          <td><button class="btn sm" data-edit="journals:${j.id}">编辑</button></td>
        </tr>`;
    }).join("")}
    </table></div>`, { icon: "📕" });
  }).join("");
  return `<div class="page-head"><h1>📕 期刊库</h1><div class="sub">目标期刊档案 · 你的真实审稿周期会自动沉淀</div>
    <span class="spacer"></span><button class="btn primary" data-new="journals">＋ 新期刊</button></div>
    ${tut}${body || `<div class="empty">还没有期刊。可以在「设置 → 表格导入」里导入你的 Excel 清单。</div>`}`;
};

/* ---------------------------------------------------------- 已刊论文 */
VIEWS.papers = () => {
  const ps = rows("published").slice().sort((a, b) => String(b.year || "").localeCompare(String(a.year || "")));
  const tut = UI.tut("published", "已刊论文库怎么用", `
    <p>发表后的归档：引用信息、DOI、终稿与复现文件的位置、被引情况。</p>
    <p>建议每篇都填「复现文件位置」——三年后有人问你要数据和代码时，你会感谢现在的自己。</p>`);
  const byYear = {};
  ps.forEach(p => { (byYear[p.year || "未标年份"] = byYear[p.year || "未标年份"] || []).push(p); });
  const body = Object.keys(byYear).sort().reverse().map(y =>
    UI.card("pub:" + y, String(y), `${byYear[y].length} 篇`, byYear[y].map(p => `
      <div class="row-line" data-pick="published:${p.id}"><div class="rl-main">
        <div class="rl-title">${esc(p.title || "")} ${p.url ? `<a href="${esc(p.url)}" target="_blank">↗</a>` : ""}${UI.linkBadge(p)}</div>
        <div class="rl-meta">${esc(p.journal || "")} ${esc(p.volume || "")}
          ${p.doi ? " · DOI " + esc(p.doi) : ""} ${p.cites ? " · 被引 " + p.cites : ""}
          ${p.folder ? " · 复现文件：" + esc(p.folder) : ""}</div>
      </div><div class="rl-acts"><button class="btn sm" data-edit="published:${p.id}">编辑</button></div></div>`).join(""),
      { icon: "🏆" })).join("");
  return `<div class="page-head"><h1>🏆 论文库</h1><div class="sub">已发表 · 归档 · 复现材料</div>
    <span class="spacer"></span><button class="btn primary" data-new="published">＋ 新增</button></div>
    ${tut}${body || `<div class="empty">还没有记录。</div>`}`;
};

/* ---------------------------------------------------------- 学术会议 */
VIEWS.conferences = () => {
  const cs = rows("conferences");
  const tut = UI.tut("conferences", "学术会议怎么用", `
    <p>会议按年份收纳。填了「投稿截止」之后，它会自动出现在<b>今日页</b>的近期提醒里，不用你再单独记。</p>
    <p>「投了哪篇」填稿件题目，将来复盘时能看到这篇论文走过哪些会议。</p>`);
  const byYear = {};
  cs.forEach(c => {
    const y = (c.start || c.deadline || "").slice(0, 4) || "未定";
    (byYear[y] = byYear[y] || []).push(c);
  });
  const body = Object.keys(byYear).sort().reverse().map(y =>
    UI.card("conf:" + y, String(y), `${byYear[y].length} 个`,
      byYear[y].slice().sort((a, b) => String(a.deadline || "").localeCompare(String(b.deadline || ""))).map(c => {
        const d = daysUntil(c.deadline);
        return `<div class="row-line" data-pick="conferences:${c.id}"><div class="rl-main">
        <div class="rl-title">${esc(c.title || "")} ${c.url ? `<a href="${esc(c.url)}" target="_blank">↗</a>` : ""}
          <span class="badge ${c.status === "accepted" ? "g" : c.status === "submitted" ? "b" : ""}">${esc(c.status || "关注")}</span>${UI.linkBadge(c)}</div>
        <div class="rl-meta">${c.deadline ? "截止 " + esc(c.deadline) : ""}${d != null && d > -60 ? " " + daysChip(d).replace(/<[^>]+>/g, "") : ""}
          ${c.start ? " · 会期 " + esc(c.start) + (c.end ? "→" + esc(c.end) : "") : ""}
          ${c.location ? " · " + esc(c.location) : ""}${c.submitted ? " · 投了：" + esc(c.submitted) : ""}</div>
      </div><div class="rl-acts"><button class="btn sm" data-edit="conferences:${c.id}">编辑</button></div></div>`;
      }).join(""), { icon: "🎤", actions: sampleBtn(["conferences"]) })).join("");
  return `<div class="page-head"><h1>🎤 学术会议</h1><div class="sub">截止日期会自动进今日提醒</div>
    <span class="spacer"></span><button class="btn primary" data-new="conferences">＋ 新会议</button></div>
    ${tut}${body || `<div class="empty">还没有会议。</div>`}`;
};

/* -------------------------------------------------- 记录事件 / 新建按钮 */
function openEventDialog(msId) {
  const m = byId("manuscripts", msId); if (!m) return;
  const journals = rows("journals").map(j => j.title).filter(Boolean);
  UI.modal("记录事件 · " + (m.title || ""), `
    <div class="form-grid">
      <div class="field"><label>日期</label><input type="date" id="ev_date" value="${todayStr()}"></div>
      <div class="field"><label>事件</label><div class="pill-select" data-pill="ev_event">
        ${EVENTS.map(e => `<button type="button" data-v="${e.v}" class="${e.v === "submitted" ? "on" : ""}">${e.t}</button>`).join("")}
      </div><input type="hidden" id="f_ev_event" value="submitted"></div>
      <div class="field"><label>期刊</label><input id="ev_journal" list="jlist" value="${esc(m.current_journal || m.target_journal || "")}">
        <datalist id="jlist">${journals.map(j => `<option value="${esc(j)}">`).join("")}</datalist></div>
      <div class="field wide"><label>备注（审稿意见要点、编辑回复等）</label><textarea id="ev_note"></textarea></div>
    </div>
    <div class="small muted" style="margin-top:8px">保存后会自动更新稿件阶段与「当前在投期刊」。</div>`,
    `<button class="btn primary" id="evSave">保存事件</button><span class="spacer"></span><button class="btn" data-close>取消</button>`);
  $("#evSave").onclick = async () => {
    const ev = {
      date: $("#ev_date").value || todayStr(),
      event: $("#f_ev_event").value,
      journal: $("#ev_journal").value.trim(),
      note: $("#ev_note").value.trim(),
    };
    /* 时间线是往数组里**追加**，所以必须基于「刚取回来的那份」去接，
       不能用内存里那份 —— 另一台设备/另一个页签刚记的一条事件会被整段覆盖掉，
       而界面上什么都不会说。patchRec 的函数形式给的就是新鲜那份。 */
    const map = { submitted: "submitted", resubmitted: "submitted", rnr: "rnr", accepted: "accepted", published: "published" };
    await patchRec("manuscripts", msId, fresh => {
      const patch = { timeline: (fresh.timeline || []).concat([ev]) };
      if (map[ev.event]) patch.stage = map[ev.event];
      if (["rejected", "desk-reject", "withdrawn"].includes(ev.event)) patch.stage = "writing";
      if (["submitted", "resubmitted", "rnr"].includes(ev.event)) patch.current_journal = ev.journal;
      if (["rejected", "desk-reject", "withdrawn", "published"].includes(ev.event)) patch.current_journal = "";
      return patch;
    });
    UI.closeModal(); render(); renderNav(); toast("事件已记录");
  };
}

window.bindModuleExtras = function () {
  /* 首屏截断的正文，点一下按需把全文取回来（不刷新整页，只换那一段） */
  $$("[data-fullbody]").forEach(a => a.onclick = async e => {
    e.preventDefault();
    const [c, i] = a.dataset.fullbody.split(":");
    try {
      const fresh = await API.get(`records/${encodeURIComponent(c)}/${encodeURIComponent(i)}`);
      const arr = S.data[c] || [];
      const k = arr.findIndex(x => x.id === i);
      if (k >= 0) arr[k] = fresh;
      const box = a.parentElement;
      if (box) box.textContent = fresh.body || "";
    } catch (err) { toast("取全文失败：" + (err.message || err)); }
  });
  const msM = $("#msMore");
  if (msM) msM.onclick = () => { S._msMax = (S._msMax || 40) + 40; render(); };
  /* 文献索引自己管自己的取数与重绘：它一次只画 50 行，
     绝不参与全局 render()，否则几万条题录会把每一次交互都拖慢 */
  if (typeof LIB !== "undefined") { try { LIB.bind(); } catch (e) { console.error(e); } }
  $$("[data-new]").forEach(b => b.onclick = () => {
    const coll = b.dataset.new;
    const sc = window["schema_" + coll];
    if (sc) UI.editRecord(coll, null, sc());
  });
  $$("[data-event]").forEach(b => b.onclick = e => { e.stopPropagation(); openEventDialog(b.dataset.event); });
  $$("[data-ai]").forEach(b => b.onclick = e => { e.stopPropagation(); openAiDialog(b.dataset.ai); });
  $$("[data-figs]").forEach(el => {
    const id = el.dataset.figs;
    if (S._figs[id]) {
      const m = byId("manuscripts", id) || {};
      el.innerHTML = UI.gallery(S._figs[id], { pinTo: id, pinned: m.pinned_figure });
      UI.renderFigures(el);
      $$("[data-pin]", el).forEach(p => p.onclick = async ev => {
        ev.stopPropagation();
        const cur = byId("manuscripts", p.dataset.pinid);
        const val = cur.pinned_figure === p.dataset.pin ? "" : p.dataset.pin;
        await patchRec("manuscripts", p.dataset.pinid, { pinned_figure: val });
        render(); toast(val ? "已钉为主结果" : "已取消");
      });
    } else if (!el._loading) {
      el._loading = true;
      loadFigures(id, el.dataset.folder);
    }
  });
  if (window.bindHubExtras) window.bindHubExtras();
  if (window.bindTodayExtras) window.bindTodayExtras();
  if (window.bindKnowledgeExtras) window.bindKnowledgeExtras();
  if (window.bindScheduleExtras) window.bindScheduleExtras();
  if (window.bindAiExtras) window.bindAiExtras();
  if (window.bindSettingsExtras) window.bindSettingsExtras();
  if (window.bindLifeExtras) window.bindLifeExtras();
};

/* 期刊统计并进「研究」页：只显示你真的投过的那几家，
   完整期刊库仍然可以从这里点进去（不再单独占一个侧边栏位置）。 */
window.journalStatsCard = function () {
  const js = rows("journals");
  const withExp = js.map(j => ({ j, e: journalExperience(j.title) })).filter(x => x.e);
  if (!withExp.length && !js.length) return "";
  const body = withExp.length ? `<div class="scroll-x"><table class="tbl">
      <tr><th>期刊</th><th>你的真实审稿周期</th><th>官方</th><th></th></tr>
      ${withExp.sort((a, b) => b.e.n - a.e.n).map(({ j, e }) => `<tr>
        <td><b>${esc(j.title || "")}</b>${j.portal ? ` <a href="${esc(j.portal)}" target="_blank" rel="noopener">投稿入口</a>` : ""}</td>
        <td class="small"><b>${e.avg} 天</b> · ${e.n} 次
          <div class="tiny muted">拒 ${e.outcomes.rejected} · R&R ${e.outcomes.rnr} · 接收 ${e.outcomes.accepted}</div></td>
        <td class="small">${j.stated_review_days ? j.stated_review_days + " 天" : "—"}</td>
        <td><button class="btn sm" data-edit="journals:${j.id}">编辑</button></td></tr>`).join("")}
    </table></div>`
    : `<div class="empty">还没有投稿记录。每次投稿在稿件卡上点「＋ 记录事件」记一条，
        这里就会自动算出你在每家刊的真实审稿周期。</div>`;
  return UI.card("hub-journals", "期刊档案", `${js.length} 家`, body + `
    <div style="margin-top:10px;display:flex;gap:7px;flex-wrap:wrap">
      <button class="btn sm" data-go="journals">打开完整期刊库</button>
      <button class="btn sm ghost" data-new="journals">＋ 新期刊</button></div>`,
    { icon: "📕", defaultOpen: false });
};
