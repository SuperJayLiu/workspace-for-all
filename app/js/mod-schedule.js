/* 日程：月历 + 可拖动甘特 */

window.schema_schedule = () => [
  { k: "title", label: "事项", type: "text", wide: true },
  { k: "start", label: "开始", type: "date" },
  { k: "end", label: "结束", type: "date" },
  { k: "kind", label: "类型", type: "select", opts: [{ v: "task", t: "任务" }, { v: "meeting", t: "会议" }, { v: "travel", t: "出行" }, { v: "teaching", t: "教学" }, { v: "milestone", t: "里程碑" }] },
  { k: "done", label: "已完成", type: "check" },
];

function allDated() {
  const out = [];
  /* 订阅日历（Outlook / Google / 学校课表）也要出现在这张月历上。
     以前只有右边栏和「今天」页读 S.icsEvents，日程页压根没接 ——
     于是同一个会议，右边栏看得见、点进日程页却没有，
     而这张卡上还写着「学术和生活的日期都会自动出现」。
     这些是**别人日历里的**条目，工作台改不了，所以标成只读：
     不给编辑按钮，也不进甘特图（拖了根本存不回去）。 */
  (S.icsEvents || []).forEach(e => {
    if (!e.date) return;
    out.push({
      date: String(e.date).slice(0, 10),
      end: String(e.end_date || e.date).slice(0, 10),
      title: (e.time ? e.time + " " : "") + (e.title || "（无标题）"),
      kind: "external", icon: "📨", coll: "", id: "", readonly: true,
      source: e.source || "订阅日历",
      tzNote: e.src_tz ? `原 ${e.src_time} · ${e.src_tz}（已换算成本地时间）` : "",
    });
  });
  rows("schedule").forEach(s => out.push({
    date: s.start, end: s.end || s.start, title: s.title, kind: s.kind || "task",
    icon: "📅", coll: "schedule", id: s.id, done: s.done,
  }));
  rows("conferences").forEach(c => {
    if (c.deadline) out.push({ date: c.deadline, end: c.deadline, title: c.title + " 截止", kind: "deadline", icon: "🎤", coll: "conferences", id: c.id });
    if (c.start) out.push({ date: c.start, end: c.end || c.start, title: c.title, kind: "travel", icon: "🎤", coll: "conferences", id: c.id });
  });
  rows("manuscripts").forEach(m => {
    if (m.next_action_due) out.push({ date: m.next_action_due, end: m.next_action_due, title: (m.title || "") + " · " + (m.next_action || "下一步"), kind: "deadline", icon: "📄", coll: "manuscripts", id: m.id });
  });
  rows("admin").forEach(a => { if (a.date && !a.done) out.push({ date: a.date, end: a.date, title: a.title, kind: "life", icon: "🏡", coll: "admin", id: a.id }); });
  rows("dates").forEach(d => {
    if (!d.date) return;
    const n = daysUntil(d.date, d.yearly);
    const dd = new Date(); dd.setDate(dd.getDate() + (n || 0));
    out.push({ date: todayStr(dd), end: todayStr(dd), title: d.title, kind: "anniversary", icon: "🎂", coll: "dates", id: d.id });
  });
  return out.filter(x => x.date);
}

VIEWS.schedule = () => {
  const tut = UI.tut("schedule", "日程怎么用", `
    <p>月历把<b>学术和生活的日期合在一起</b>：会议截止、稿件下一步、生活事务、重要日子，都会自动出现，不用重复录入。</p>
    <p>下面的甘特图可以<b>直接拖动</b>：拖条移动整段，拖两端改开始/结束。改完立即存盘。</p>`);
  const items = allDated();
  const now = new Date();
  const y = S._calY != null ? S._calY : now.getFullYear();
  const m = S._calM != null ? S._calM : now.getMonth();
  const first = new Date(y, m, 1), last = new Date(y, m + 1, 0);
  const lead = (first.getDay() + 6) % 7;
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(null);
  for (let d = 1; d <= last.getDate(); d++) cells.push(new Date(y, m, d));
  while (cells.length % 7) cells.push(null);

  const cal = `<div style="display:flex;align-items:center;gap:9px;margin-bottom:9px">
      <button class="btn sm" data-cal="-1">‹</button>
      <b>${y} 年 ${m + 1} 月</b>
      <button class="btn sm" data-cal="1">›</button>
      <button class="btn sm ghost" data-cal="0">今天</button></div>
    <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px">
      ${["一", "二", "三", "四", "五", "六", "日"].map(d => `<div class="tiny muted" style="text-align:center">${d}</div>`).join("")}
      ${cells.map(d => {
    if (!d) return `<div></div>`;
    const ds = todayStr(d);
    const evs = items.filter(x => ds >= String(x.date).slice(0, 10) && ds <= String(x.end || x.date).slice(0, 10));
    const isToday = ds === todayStr();
    return `<div style="min-height:74px;border:1px solid var(--line);border-radius:8px;padding:4px 5px;
        ${isToday ? "border-color:var(--accent);background:var(--accent-soft)" : ""}">
      <div class="tiny ${isToday ? "" : "muted"}" style="font-weight:${isToday ? 700 : 400}">${d.getDate()}</div>
      ${evs.slice(0, 3).map(e => `<div class="tiny" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
          color:${e.kind === "deadline" ? "var(--red)" : e.kind === "anniversary" ? "var(--violet)"
      : e.kind === "external" ? "var(--accent)" : "var(--ink-2)"}"
          title="${esc(e.title)}${e.readonly ? ` · 来自${esc(e.source || "订阅日历")}（只读）` : ""}${
      e.tzNote ? "\n" + esc(e.tzNote) : ""}">${e.icon} ${esc(e.title)}</div>`).join("")}
      ${evs.length > 3 ? `<div class="tiny muted">+${evs.length - 3}</div>` : ""}
    </div>`;
  }).join("")}
    </div>`;

  const schedAll = rows("schedule");
  const gitems = rows("manuscripts").filter(x => !["published", "shelved"].includes(x.stage)).map(x => {
    const tl = (x.timeline || []).map(e => e.date).filter(Boolean).sort();
    const start = x.start || tl[0] || (x.created || "").slice(0, 10) || todayStr();
    const end = x.end || x.next_action_due || todayStr(new Date(Date.now() + 60 * 86400000));
    return {
      id: x.id, coll: "manuscripts", label: x.title || "", short: STAGE_T[x.stage] || "",
      start, end, cls: x.stage === "rnr" ? "a" : x.stage === "submitted" ? "v" : "",
    };
  }).concat(schedAll.filter(s => s.start).map(s => ({
    id: s.id, coll: "schedule", label: s.title || "", short: "",
    start: s.start, end: s.end || s.start, cls: s.done ? "g" : "",
  })));

  /* 日程是**逐日累积**的：记两年就上千条，是全站最容易撑爆的一页。
     压测 2001 条时这一页要 5.9 秒、84724 个 DOM 节点。
     两处都得封顶——而且封顶对甘特图来说本来就是对的，
     两千根条子叠在一起没人看得懂。 */
  const GANTT_MAX = 60;
  const gShown = gitems.slice(0, GANTT_MAX);
  const gCut = gitems.length - gShown.length;

  const step = 150;
  const max = S._schMax || step;
  const today = todayStr();
  /* 排序按「离今天多远」：未来的先来（近的在前），再接最近的过去。
     两千条里你要找的几乎总是这两头，不是中间某个月。 */
  const sorted = schedAll.slice().sort((a, b) => {
    const A = String(a.start || ""), B = String(b.start || "");
    const fa = A >= today, fb = B >= today;
    if (fa !== fb) return fa ? -1 : 1;
    return fa ? A.localeCompare(B) : B.localeCompare(A);
  });
  const shown = sorted.slice(0, max);
  const rest = sorted.length - shown.length;

  /* 订阅日历单独一张卡：它们改不了，混在「日程清单」里会让人以为能勾能编辑。
     只列今天往后的，过去的会议没人回头翻。 */
  const EXT_MAX = 60;
  const extAll = items.filter(x => x.readonly
    && String(x.end || x.date) >= today).sort((a, b) =>
      String(a.date).localeCompare(String(b.date)));
  const extShown = extAll.slice(0, EXT_MAX);
  const icsErr = (S.icsErrors || []).length;
  const extCard = (extAll.length || icsErr || (S.config.calendar || {}).ics)
    ? UI.card("sch-ics", "订阅日历", extAll.length
      ? `${extShown.length}${extAll.length > EXT_MAX ? ` / ${extAll.length}` : ""} 条`
      : (icsErr ? "拉取失败" : "没有即将开始的"),
      (icsErr
        ? `<div class="small" style="color:var(--red);margin-bottom:8px">
             有 ${icsErr} 个订阅链接拉不动，去「设置 → 日历」看看。</div>` : "")
      + (extShown.length
        ? extShown.map(e => `<div class="row-line">
            <div class="rl-main"><div class="rl-title">${esc(e.title)}</div>
              <div class="rl-meta">${esc(e.date)}${e.end && e.end !== e.date
          ? " → " + esc(e.end) : ""} · ${esc(e.source)}${
          e.tzNote ? " · " + esc(e.tzNote) : ""}</div></div></div>`).join("")
        + (extAll.length > EXT_MAX
          ? `<div class="small muted" style="margin-top:8px">还有 ${extAll.length - EXT_MAX} 条没列出来。</div>` : "")
        : `<div class="empty">最近没有来自订阅日历的安排。</div>`)
      + `<div class="tiny muted" style="margin-top:8px">这些来自你订阅的日历（Outlook / Google / 课表），
           工作台只读不改 —— 要改请去原来那个日历里改，这边下次同步会跟上。</div>`,
      { icon: "📨", defaultOpen: false })
    : "";

  return `<div class="page-head"><h1>📅 日程</h1><div class="sub">学术与生活合流 · 甘特可拖动</div>
    <span class="spacer"></span><button class="btn primary" data-new="schedule">＋ 新日程</button></div>
    ${tut}
    ${UI.card("sch-cal", "月历", "Calendar", cal, { icon: "🗓" })}
    ${UI.card("sch-gantt", "甘特图（拖动条改日期，拖两端改工期）",
      gCut > 0 ? `只画前 ${GANTT_MAX} 条` : "Gantt",
      UI.gantt(gShown) + (gCut > 0
        ? `<div class="small muted" style="margin-top:8px">还有 ${gCut} 条没画在图上 ——
             甘特图超过几十根条子就没法看了，这里只保留稿件和最近的日程。
             完整清单在下面那张卡。</div>` : ""), { icon: "📊" })}
    ${extCard}
    ${UI.card("sch-list", "日程清单", sorted.length ? `${shown.length} / ${sorted.length} 条` : "",
      sorted.length ? shown.map(s => `
      <div class="row-line ${s.done ? "done" : ""}">
        <input type="checkbox" ${s.done ? "checked" : ""} data-toggle="schedule:${s.id}:done">
        <div class="rl-main"><div class="rl-title">${esc(s.title || "")}</div>
          <div class="rl-meta">${esc(s.start || "")}${s.end && s.end !== s.start ? " → " + esc(s.end) : ""} · ${esc(s.kind || "")}</div></div>
        <div class="rl-acts"><button class="btn sm" data-edit="schedule:${s.id}">编辑</button></div></div>`).join("")
        + (rest > 0 ? `<div style="margin-top:10px;display:flex;gap:8px;align-items:center">
            <button class="btn" id="schMore">再显示 ${Math.min(step, rest)} 条</button>
            <span class="small muted">还有 ${rest} 条没显示（按离今天的远近排，未来的在前）</span></div>` : "")
      : `<div class="empty">还没有日程</div>`, { icon: "📋" })}`;
};

window.bindScheduleExtras = function () {
  const more = $("#schMore");
  if (more) more.onclick = () => { S._schMax = (S._schMax || 150) + 150; render(); };
  $$("[data-cal]").forEach(b => b.onclick = () => {
    const d = Number(b.dataset.cal), now = new Date();
    if (d === 0) { S._calY = now.getFullYear(); S._calM = now.getMonth(); }
    else {
      const y = S._calY != null ? S._calY : now.getFullYear();
      const m = (S._calM != null ? S._calM : now.getMonth()) + d;
      S._calY = y + Math.floor(m / 12); S._calM = ((m % 12) + 12) % 12;
    }
    render();
  });
};
