/* 今日：把学术与生活的一切自动汇聚到一页 */

/* 存完一条之后说句人话，并把「拿去问 AI」这一步铺好 —— 不用你自己再组织语言 */
const CAP_REPLY = {
  ideas: r => r.kind === "question" ? "疑问记下了，别急着解决 —— 先让它躺一躺 🤔"
                                    : "灵感记下啦，周末一起讨论吧 💡",
  reading: () => "文献进队列了，读完记三段就能加经验 📚",
  manuscripts: () => "挂到稿件的下一步了，今日页会替你盯着 📄",
  conferences: () => "会议记下了，截稿前会提前提醒你 🎤",
  schedule: () => "日程排好了，右上角日历里也能看到 📅",
  diet: () => "记下了。要不要让 AI 估个热量、给两个更均衡的替代？🍚",
  exercise: () => "动过了就是赢了 🏃",
  finance: () => "记账完成 💰",
  admin: () => "杂务记下了，别让它占着脑子 🧹",
  lists: () => "加进清单了 ✅",
};

function afterCapture(parsed) {
  const coll = parsed.collection;
  const rec = parsed.record || {};
  const line = (CAP_REPLY[coll] || (() => "记下了"))(rec);
  const fields = parsed.notes.length ? " · " + parsed.notes.join("、") : "";
  const prompt = CAP.aiPrompt(coll, rec);
  if (!prompt) { toast(line + fields); return; }
  /* 有可问的东西就给一条带按钮的提示，5 秒后自己消失 */
  const t = $("#toast");
  t.innerHTML = `${esc(line)}${esc(fields)}
    <button class="btn sm" id="capAsk" style="margin-left:9px">🤖 拿去问 AI</button>`;
  t.classList.add("show", "wide");
  clearTimeout(t._h);
  t._h = setTimeout(() => { t.classList.remove("show", "wide"); t.textContent = ""; }, 6500);
  const btn = $("#capAsk");
  if (btn) btn.onclick = () => {
    clearTimeout(t._h); t.classList.remove("show", "wide"); t.textContent = "";
    openAiDialog("", { preset: prompt });
  };
}

/* 本周一览：Outlook 日程 + 工作台的截止与待办，按天铺开 */
function weekPlan() {
  const mon = new Date(); mon.setDate(mon.getDate() - ((mon.getDay() + 6) % 7));
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(mon); d.setDate(mon.getDate() + i);
    const ds = todayStr(d);
    const ics = (S.icsEvents || []).filter(e => String(e.date).slice(0, 10) === ds)
      .map(e => ({ t: e.time || "", title: e.title || "", src: "Outlook", cls: "v" }));
    const sched = rows("schedule").filter(r => !r.done && String(r.start || "").slice(0, 10) === ds)
      .map(r => ({ t: r.time || "", title: r.title || "", src: "日程", cls: "b", go: "schedule" }));
    const conf = rows("conferences").filter(c => String(c.deadline || "").slice(0, 10) === ds)
      .map(c => ({ t: "", title: (c.title || "") + " 截稿", src: "会议", cls: "a", go: "conferences" }));
    const ms = rows("manuscripts").filter(m => String(m.next_action_due || "").slice(0, 10) === ds)
      .map(m => ({ t: "", title: (m.title || "") + " · " + (m.next_action || "下一步"), src: "稿件", cls: "b", go: "hub" }));
    const adm = rows("admin").filter(a => !a.done && String(a.date || "").slice(0, 10) === ds)
      .map(a => ({ t: "", title: a.title || "", src: "事务", cls: "g", go: "life" }));
    const items = ics.concat(sched, conf, ms, adm)
      .sort((a, b) => String(a.t || "zz").localeCompare(String(b.t || "zz")));
    days.push({ ds, d, items, isToday: ds === todayStr(), isPast: ds < todayStr() });
  }
  return days;
}

/* Overleaf 同步出来的写作进展：今天的 + 本周合计 */
function writingProgress() {
  const all = rows("progress");
  const today = todayStr();
  const monday = (() => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return todayStr(d); })();
  const t = all.filter(r => String(r.date || "").slice(0, 10) === today);
  const w = all.filter(r => String(r.date || "").slice(0, 10) >= monday);
  const sum = arr => arr.reduce((a, r) => ({
    added: a.added + (Number(r.added) || 0),
    removed: a.removed + (Number(r.removed) || 0),
    commits: a.commits + (Number(r.commits) || 0),
  }), { added: 0, removed: 0, commits: 0 });
  return { today: t, week: w, tSum: sum(t), wSum: sum(w) };
}

function upcomingItems(horizon) {
  horizon = horizon || S.config.today_horizon_days || 45;
  const out = [];
  const push = (d, icon, title, meta, go_, yearly, tag) => {
    const n = daysUntil(d, yearly);
    if (n == null || n > horizon) return;
    out.push({ n, icon, title, meta, date: d, go: go_, tag: tag || "" });
  };
  rows("conferences").forEach(c => { if (c.status !== "done") push(c.deadline, "🎤", (c.title || "") + " 投稿截止", c.location || "", "conferences", false, "学术"); });
  rows("manuscripts").forEach(m => { if (m.next_action_due) push(m.next_action_due, "📄", (m.title || "") + " · " + (m.next_action || "下一步"), STAGE_T[m.stage] || "", "manuscripts", false, "学术"); });
  rows("schedule").forEach(s => { if (!s.done) push(s.start, "📅", s.title, [s.time, s.kind].filter(Boolean).join(" · "), "schedule", false, "日程"); });
  rows("admin").forEach(a => { if (!a.done) push(a.date, "🏡", a.title, a.repeat || "", "life", false, "生活"); });
  rows("dates").forEach(d => push(d.date, "🎂", d.title, d.yearly ? "每年" : "", "life", d.yearly, "生活"));
  return out.sort((a, b) => a.n - b.n);
}

/* 今天的 ICS 日程（Outlook 等） */
function icsToday() {
  const evs = (S.icsEvents || []).filter(e => String(e.date).slice(0, 10) === todayStr());
  return evs.sort((a, b) => String(a.time || "99").localeCompare(String(b.time || "99")));
}

VIEWS.today = () => {
  const up = upcomingItems();
  const overdue = up.filter(x => x.n < 0);
  const todayDue = up.filter(x => x.n === 0);
  const soon = up.filter(x => x.n > 0);
  const ms = rows("manuscripts");
  const active = ms.filter(m => !["published", "shelved"].includes(m.stage));
  const stale = active.filter(m => (msDaysSinceUpdate(m) || 0) >= (S.config.stale_manuscript_days || 7));
  const inReview = ms.filter(m => m.stage === "submitted" || m.stage === "rnr");
  const chase = inReview.filter(m => {
    const r = msInReviewDays(m); return r && r.days >= (S.config.chase_days || 120);
  });
  const reps = rows("reports").filter(r => r.status === "unread" || r.status === "waiting");
  const queue = (typeof reviewQueue === "function") ? reviewQueue() : [];
  const st = (typeof readStreak === "function") ? readStreak() : { streak: 0 };
  const q = S.quota || {};
  const w = S.weather || {};

  // 生活打卡
  const dietToday = rows("diet").filter(r => String(r.date || "").slice(0, 10) === todayStr());
  const exToday = rows("exercise").filter(r => String(r.date || "").slice(0, 10) === todayStr());
  const exWeekMin = (() => {
    const monday = new Date(); monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
    const m = todayStr(monday);
    return rows("exercise").filter(r => String(r.date || "").slice(0, 10) >= m)
      .reduce((s, r) => s + (Number(r.minutes) || 0), 0);
  })();
  const listPending = rows("lists").filter(r => !r.done);
  const inboxRaw = rows("ideas").filter(r => r.source === "capture" && r.status === "new");

  const tut = UI.tut("today", "今日页是自动生成的", `
    <p>这一页<b>不需要你维护</b>，也不只管研究：稿件的下一步、会议截止、Outlook 日程、生活事务、重要日子、
    停滞与该催稿的稿件、饮食运动打卡、待分拣的速记、AI 的新产出、到期的文献复习，全都自动汇聚到这里。</p>
    <p>规则：${S.config.today_horizon_days || 45} 天内的截止会显示；超过 ${S.config.stale_manuscript_days || 7} 天没有事件的稿件标为「停滞」；
    投出去超过 ${S.config.chase_days || 120} 天会提醒你催稿。这些数字在设置里可改。</p>
    <p>按 <kbd>c</kbd> 随手记一句，系统会<b>自动判断</b>它是想法、待办、文献、运动还是开支，并把日期、时间、金额、时长、DOI 都抽出来填好——你只要确认。</p>`);

  const stats = `<div class="grid g4" style="margin-bottom:14px">
    <button class="stat ${overdue.length ? "alert" : "good"}" data-stat="overdue"><div class="k">逾期</div><div class="v">${overdue.length}</div><div class="d">${overdue.length ? "点开看是哪几项" : "干干净净"}</div></button>
    <button class="stat ${todayDue.length ? "warn" : ""}" data-stat="today"><div class="k">今天到期</div><div class="v">${todayDue.length}</div><div class="d">另有 ${soon.length} 项在 ${S.config.today_horizon_days || 45} 天内</div></button>
    <button class="stat ${stale.length ? "warn" : ""}" data-stat="stale"><div class="k">停滞稿件</div><div class="v">${stale.length}</div><div class="d">在投 ${inReview.length}${chase.length ? " · " + chase.length + " 篇该催了" : ""}</div></button>
    <button class="stat ${st.streak >= 3 ? "good" : ""}" data-stat="reading"><div class="k">读文献连续</div><div class="v">${st.streak}</div><div class="d">天 · ${queue.length} 条待复习</div></button>
  </div>`;

  const listHtml = arr => arr.map(x => `<div class="row-line" data-rowgo="${x.go}"><div class="rl-main">
      <div class="rl-title">${x.icon} ${esc(x.title)} <span class="badge">${esc(x.date)}</span>${daysChip(x.n)}
        ${x.tag ? `<span class="badge ${x.tag === "学术" ? "b" : x.tag === "生活" ? "g" : "v"}">${x.tag}</span>` : ""}</div>
      ${x.meta ? `<div class="rl-meta">${esc(x.meta)}</div>` : ""}
    </div><div class="rl-acts"><button class="btn sm ghost" data-go="${x.go}">前往</button></div></div>`).join("");

  const ics = icsToday();
  const todayLine = todayDue.concat([]).map(x => x);
  const agenda = ics.length || todayLine.length ? `
    ${ics.map(e => `<div class="row-line"><div class="rl-main">
      <div class="rl-title">${e.time ? `<span class="badge">${esc(e.time)}</span>` : `<span class="badge">全天</span>`}
        ${esc(e.title || "")} <span class="badge v">Outlook</span></div>
      ${e.location ? `<div class="rl-meta">${esc(e.location)}</div>` : ""}
      ${e.src_tz ? `<div class="rl-meta">🌐 原 ${esc(e.src_time)} · ${esc(e.src_tz)}，已换算成本地时间</div>` : ""}</div></div>`).join("")}
    ${listHtml(todayLine)}` : `<div class="empty">今天没有排定的事 —— 可以专心写点东西 ✍️</div>`;

  const nextActions = active.filter(m => m.next_action).map(m => {
    const rev = msInReviewDays(m);
    const needChase = rev && rev.days >= (S.config.chase_days || 120);
    return `<div class="row-line"><div class="rl-main">
      <div class="rl-title"><span class="badge ${m.stage === "rnr" ? "a" : "b"}">${STAGE_T[m.stage] || ""}</span>${esc(m.title || "")}</div>
      <div class="rl-meta">下一步：${esc(m.next_action)}${m.next_action_due ? " · " + esc(m.next_action_due) : ""}
        ${(msDaysSinceUpdate(m) || 0) >= (S.config.stale_manuscript_days || 7) ? ` · <span style="color:var(--amber)">已 ${msDaysSinceUpdate(m)} 天没动</span>` : ""}
        ${needChase ? ` · <span style="color:var(--red)">在 ${esc(m.current_journal || "")} 已 ${rev.days} 天，该催稿了</span>` : ""}</div>
    </div><div class="rl-acts">
      ${needChase ? `<button class="btn sm" data-chase="${m.id}">催稿信</button>` : ""}
      <button class="btn sm" data-ai="manuscripts:${m.id}">🤖</button>
      <button class="btn sm ghost" data-go="manuscripts">打开</button></div></div>`;
  }).join("");

  const wk = weekPlan();
  const wkTotal = wk.reduce((n, d) => n + d.items.length, 0);
  const weekCard = `
    <div class="small muted" style="margin-bottom:9px">本周共 ${wkTotal} 项，Outlook 日程与工作台的截止已经合在一起。
      每天早上会自动刷新一次。</div>
    <div class="weekgrid">
      ${wk.map(d => `<div class="wkday ${d.isToday ? "on" : ""} ${d.isPast ? "past" : ""}">
        <div class="wkh">${["一", "二", "三", "四", "五", "六", "日"][(d.d.getDay() + 6) % 7]}
          <span>${d.d.getMonth() + 1}/${d.d.getDate()}</span></div>
        ${d.items.length ? d.items.map(x => `<div class="wkitem" ${x.go ? `data-rowgo="${x.go}"` : ""}>
            ${x.t ? `<b>${esc(x.t)}</b> ` : ""}${esc(String(x.title).slice(0, 42))}
            <span class="badge ${x.cls}">${esc(x.src)}</span></div>`).join("")
          : `<div class="wkempty">—</div>`}
      </div>`).join("")}
    </div>`;

  const doneToday = rows("schedule").filter(r => r.done && r.logged &&
    String(r.date || r.start || "").slice(0, 10) === todayStr());
  const doneMonday = (() => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return todayStr(d); })();
  const doneWeek = rows("schedule").filter(r => r.done && r.logged &&
    String(r.date || r.start || "").slice(0, 10) >= doneMonday);
  const doneMin = doneWeek.reduce((a, r) => a + (Number(r.minutes) || 0), 0);
  const doneCard = `
    <div class="small" style="margin-bottom:9px">今天完成 <b>${doneToday.length}</b> 件 · 本周 <b>${doneWeek.length}</b> 件${doneMin ? ` · 记了 ${doneMin} 分钟` : ""}</div>
    ${doneToday.length ? doneToday.map(r => `<div class="row-line" data-rowgo="schedule"><div class="rl-main">
        <div class="rl-title small">✅ ${esc(r.title || "")}${r.minutes ? ` <span class="badge g">${r.minutes} 分</span>` : ""}</div>
        <div class="rl-meta">${esc(String(r.updated || r.created || "").slice(11, 16))}</div>
      </div></div>`).join("")
      : `<div class="empty" style="padding:10px">今天还没记完成 —— 做完一件事，按 <kbd>d</kbd> 说一句就行</div>`}`;

  const wp = writingProgress();
  const writeCard = wp.week.length ? `
    <div class="small" style="margin-bottom:9px">
      今天 <b>${wp.tSum.commits}</b> 次提交 · 净 <b>${wp.tSum.added - wp.tSum.removed > 0 ? "+" : ""}${wp.tSum.added - wp.tSum.removed}</b> 行
      　本周 <b>${wp.wSum.commits}</b> 次 · 净 <b>${wp.wSum.added - wp.wSum.removed > 0 ? "+" : ""}${wp.wSum.added - wp.wSum.removed}</b> 行</div>
    ${(wp.today.length ? wp.today : wp.week.slice(-3)).map(r => `<div class="row-line"><div class="rl-main">
      <div class="rl-title">${esc(r.title || r.project || "")}
        <span class="badge b">${esc(String(r.date).slice(5))}</span>
        ${r.words ? `<span class="badge">${r.words} 词${r.cjk ? " + " + r.cjk + " 字" : ""}</span>` : ""}</div>
      <div class="rl-meta">+${r.added || 0} / −${r.removed || 0} 行
        ${(r.touched || []).length ? " · 动了 " + esc([].concat(r.touched).slice(0, 3).join("、")) : ""}
        ${(r.messages || []).length ? " · " + esc([].concat(r.messages).slice(-2).join("；")) : ""}</div>
    </div><div class="rl-acts">${r.url ? `<a class="btn sm ghost" href="${esc(r.url)}" target="_blank" rel="noopener">Overleaf</a>` : ""}</div></div>`).join("")}` : "";

  const lifeCard = `
    <div class="grid g2">
      <div>
        <div class="tiny muted">🍚 今天的饮食</div>
        ${dietToday.length ? dietToday.map(r => `<div class="row-line"><div class="rl-main">
            <div class="rl-title small">${esc(r.title || "")}
              <span class="badge">${esc({ breakfast: "早", lunch: "午", dinner: "晚", snack: "加餐" }[r.meal] || "")}</span>
              ${r.kcal ? `<span class="badge a">${r.kcal} kcal</span>` : ""}</div></div></div>`).join("")
      : `<div class="empty" style="padding:8px">还没记 —— 按 c 说一句「午饭吃了牛肉面」就行</div>`}
      </div>
      <div>
        <div class="tiny muted">🏃 运动 · 本周合计 ${exWeekMin} 分钟</div>
        ${exToday.length ? exToday.map(r => `<div class="row-line"><div class="rl-main">
            <div class="rl-title small">${esc(r.title || "")} <span class="badge g">${r.minutes || 0} 分</span>
              ${r.km ? `<span class="badge">${r.km} km</span>` : ""}</div></div></div>`).join("")
      : `<div class="empty" style="padding:8px">今天还没动 —— 说一句「跑步 30 分钟」即可记录</div>`}
      </div>
    </div>
    ${listPending.length ? `<div class="hr"></div><div class="tiny muted">📝 待办清单还有 ${listPending.length} 项</div>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:5px">
      ${listPending.slice(0, 8).map(r => `<span class="badge">${esc(r.title || "")}</span>`).join("")}
      ${listPending.length > 8 ? `<span class="badge">+${listPending.length - 8}</span>` : ""}</div>` : ""}`;

  const weatherLine = w.ok ? `<span class="badge">${esc(w.text || "")} ${w.temp != null ? Math.round(w.temp) + "°C" : ""}</span>
      ${(w.tips || []).map(t => `<span class="badge a">${esc(t)}</span>`).join("")}` : "";

  return `${typeof QUOTE !== "undefined" ? QUOTE.banner() : ""}
    <div class="page-head"><h1>🏠 今日</h1>
    <div class="sub">${new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })}
      ${S.lunar ? " · " + esc(S.lunar) : ""} · ${esc(timeZone())} ${weatherLine}</div>
    <span class="spacer"></span>
    <button class="btn" data-ai="">🤖 问 AI</button>
    <button class="btn primary" id="quickCapture2">⚡ 快速捕捉</button></div>
    ${tut}${stats}
    ${overdue.length ? UI.card("today-overdue", "逾期", `${overdue.length} 项`, listHtml(overdue), { icon: "🚨", actions: sampleBtn(["schedule", "conferences", "manuscripts", "admin", "dates"]) }) : ""}
    ${UI.card("today-agenda", "今天", "含 Outlook 日程", agenda, { icon: "📌", actions: sampleBtn(["schedule"]) })}
    ${inboxRaw.length ? UI.card("today-inbox", "待分拣的速记", `${inboxRaw.length} 条`,
      inboxRaw.map(r => `<div class="row-line"><div class="rl-main"><div class="rl-title small">${esc(r.title || "")}</div>
        <div class="rl-meta">${esc(String(r.created || "").slice(0, 16).replace("T", " "))}</div></div>
        <div class="rl-acts"><button class="btn sm" data-sort="${r.id}">分拣</button>
        <button class="btn sm ghost" data-keep="${r.id}">留作想法</button></div></div>`).join(""), { icon: "📥" }) : ""}
    ${UI.card("today-soon", "近期截止", `${S.config.today_horizon_days || 45} 天内`,
        soon.length ? listHtml(soon) : `<div class="empty">这段时间没有截止事项 🎉</div>`, { icon: "⏳", actions: sampleBtn(["schedule", "conferences", "manuscripts", "admin", "dates"]) })}
    ${UI.card("today-next", "稿件下一步", `${active.length} 篇进行中`,
          nextActions || `<div class="empty">进行中的稿件都没写「下一步」——去稿件库补上，这一页就会替你盯着。</div>`, { icon: "📄", actions: sampleBtn(["manuscripts"]) })}
    ${UI.card("today-week", "本周一览", "含 Outlook", weekCard, { icon: "🗓" })}
    ${UI.card("today-done", "今天完成了什么", `${doneToday.length} 件`, doneCard, { icon: "✅" })}
    ${writeCard ? UI.card("today-writing", "写作进展", "来自 Overleaf", writeCard, { icon: "✍️" }) : ""}
    ${UI.card("today-life", "生活", "饮食 · 运动 · 清单", lifeCard, { icon: "🌱", actions: sampleBtn(["diet", "exercise", "lists", "admin", "dates", "finance"]) })}
    ${reps.length ? UI.card("today-ai", "AI 新产出", `${reps.length} 份待处理`,
            reps.map(r => `<div class="row-line"><div class="rl-main">
          <div class="rl-title">${r.source === "auto" ? "🤖" : r.source === "chatgpt" ? "🟢" : "🟣"} ${esc(r.title || "")}</div>
          <div class="rl-meta">${esc(r.date || "")} · ${esc(r.status === "waiting" ? "等你把回答粘回来" : "未读")}</div>
        </div><div class="rl-acts"><button class="btn sm" data-go="ai">查看</button></div></div>`).join(""), { icon: "🤖" }) : ""}
    ${queue.length ? UI.card("today-review", "今天该复习的文献", `${queue.length} 篇`,
              queue.slice(0, 5).map(x => `<div class="row-line"><div class="rl-main">
        <div class="rl-title">${esc(x.rec.title || "")}</div>
        <div class="rl-meta">读于 ${esc(x.rec.read_date)} · 第 ${x.gap} 天复习</div></div>
        <div class="rl-acts"><button class="btn sm" data-quiz="${x.rec.id}:${x.gap}">出题</button></div></div>`).join(""), { icon: "🔁", actions: sampleBtn(["reading"]) }) : ""}
    ${UI.card("today-quota", "额度状态", "", `
      <div class="small">本周自动配额 <b>${q.rate_per_week ?? "—"}</b>，已用 <b>${q.spent ?? 0}</b>，现在可用 <b>${q.available ?? 0}</b>，
      距重置 ${Math.round((q.hours_to_reset || 0) / 24 * 10) / 10} 天。
      <span class="muted">${{ behind: "· 进度落后，额度正在浪费", ahead: "· 超前，会自动收敛", "on-track": "· 节奏正常" }[q.pace] || ""}</span></div>
      <div class="qbar" style="margin-top:8px;height:16px">
        <div class="seg-auto" style="width:${Math.min(100, (q.spent || 0) / (q.rate_per_week || 1) * 100)}%"></div>
        <div class="seg-buf" style="width:${Math.min(100, (q.buffer || 0) / (q.rate_per_week || 1) * 100)}%"></div>
        <div class="marker" style="left:${Math.min(100, (q.target_spent || 0) / (q.rate_per_week || 1) * 100)}%"></div>
      </div>
      <div style="margin-top:9px"><button class="btn sm ghost" data-go="ai">调度器详情 →</button></div>`, { icon: "⚡", defaultOpen: false })}
    ${UI.card("today-notes", "随手记", "Quick notes", `
      <textarea id="quickNotes" style="width:100%;min-height:100px;border:1px solid var(--line);border-radius:9px;padding:10px;background:var(--bg)"
        placeholder="想到什么先扔进来…">${esc((S.config.quick_notes || ""))}</textarea>
      <div class="tiny muted" style="margin-top:4px">自动保存</div>`, { icon: "🗒", defaultOpen: false })}`;
};

/* 四个统计卡点开之后看到的明细 */
function statDetail(kind) {
  const up = upcomingItems();
  const ms = rows("manuscripts");
  const active = ms.filter(m => !["published", "shelved"].includes(m.stage));
  const line = (title, meta, goId) => `<div class="row-line" data-rowgo="${goId}"><div class="rl-main">
      <div class="rl-title">${title}</div>${meta ? `<div class="rl-meta">${meta}</div>` : ""}</div>
      <div class="rl-acts"><button class="btn sm ghost" data-go="${goId}">前往</button></div></div>`;
  const conf = {
    overdue: {
      t: "🚨 逾期的事项",
      hint: "已经过了日子还没处理的。点任意一行直接跳过去。",
      html: () => up.filter(x => x.n < 0).map(x =>
        line(`${x.icon} ${esc(x.title)} ${daysChip(x.n)}`, esc(x.date + (x.meta ? " · " + x.meta : "")), x.go)).join("")
        || `<div class="empty">一件都没有，干干净净 🎉</div>`,
    },
    today: {
      t: "📌 今天到期",
      hint: "今天该结束的事；下面还列了 45 天内的其余截止。",
      html: () => {
        const t = up.filter(x => x.n === 0), soon = up.filter(x => x.n > 0);
        return (t.length ? t.map(x => line(`${x.icon} ${esc(x.title)}`, esc(x.meta || ""), x.go)).join("")
          : `<div class="empty">今天没有到期的事</div>`) +
          (soon.length ? `<div class="hr"></div><div class="tiny muted" style="margin-bottom:6px">接下来 ${soon.length} 项</div>` +
            soon.slice(0, 12).map(x => line(`${x.icon} ${esc(x.title)} ${daysChip(x.n)}`, esc(x.date), x.go)).join("") : "");
      },
    },
    stale: {
      t: "🐢 停滞的稿件",
      hint: `超过 ${S.config.stale_manuscript_days || 7} 天没有任何事件的稿件。数字在设置里可改。`,
      html: () => active.filter(m => (msDaysSinceUpdate(m) || 0) >= (S.config.stale_manuscript_days || 7))
        .map(m => line(`${esc(m.title || "")} <span class="badge a">${msDaysSinceUpdate(m)} 天没动</span>`,
          `${esc(STAGE_T[m.stage] || "")}${m.next_action ? " · 下一步：" + esc(m.next_action) : " · 还没写下一步"}`,
          "manuscripts")).join("") || `<div class="empty">每篇都在动，很好 👍</div>`,
    },
    reading: {
      t: "📚 读文献",
      hint: "连续天数是按「有没有记录」算的；下面是到期该复习的。",
      html: () => {
        const q = (typeof reviewQueue === "function") ? reviewQueue() : [];
        const recent = rows("reading").filter(r => r.read_date)
          .sort((a, b) => String(b.read_date).localeCompare(String(a.read_date))).slice(0, 6);
        return (q.length ? `<div class="tiny muted" style="margin-bottom:6px">该复习的 ${q.length} 篇</div>` +
          q.slice(0, 8).map(x => line(esc(x.rec.title || ""), `读于 ${esc(x.rec.read_date)} · 第 ${x.gap} 天`, "reading")).join("")
          : `<div class="empty">今天没有要复习的</div>`) +
          (recent.length ? `<div class="hr"></div><div class="tiny muted" style="margin-bottom:6px">最近读过</div>` +
            recent.map(r => line(esc(r.title || ""), esc(r.read_date || ""), "reading")).join("") : "");
      },
    },
  }[kind];
  if (!conf) return;
  UI.modal(conf.t, `<div class="small muted" style="margin-bottom:9px">${conf.hint}</div>${conf.html()}`,
    `<span class="spacer"></span><button class="btn" data-close>关闭</button>`);
  UI.afterRender();
}

window.bindTodayExtras = function () {
  $$("[data-stat]").forEach(b => b.onclick = () => statDetail(b.dataset.stat));
  if (typeof QUOTE !== "undefined") QUOTE.bind();
  const qn = $("#quickNotes");
  if (qn) qn.oninput = debounce(() => saveConfig({ quick_notes: qn.value }), 700);
  const qc = $("#quickCapture2");
  if (qc) qc.onclick = quickCapture;
  $$("[data-sort]").forEach(b => b.onclick = () => sortIdea(b.dataset.sort));
  $$("[data-keep]").forEach(b => b.onclick = async () => {
    await patchRec("ideas", b.dataset.keep, { source: "manual" });
    render(); toast("已留作想法");
  });
  $$("[data-chase]").forEach(b => b.onclick = () => {
    const m = byId("manuscripts", b.dataset.chase);
    const rev = msInReviewDays(m);
    openAiDialog("manuscripts:" + m.id, {
      kind: "critique",
      preset: `我这篇稿子在 ${m.current_journal || "该期刊"} 已经审了 ${rev ? rev.days : "很多"} 天（我在这家刊的历史均值见下），` +
        `请帮我写一封给编辑的催稿信（status inquiry）：语气礼貌、简短、不施压，说明投稿日期与稿件编号占位，` +
        `并礼貌询问大致时间线。给中英文两版。`,
    });
  });
};

/* ------------------------------------------------------ 智能快速捕捉 */
const CAP_KINDS = [
  { v: "auto", t: "🪄 自动判断" }, { v: "idea", t: "💡 想法" }, { v: "todo", t: "✅ 待办" },
  { v: "schedule", t: "📅 日程" }, { v: "reading", t: "📚 文献" }, { v: "manuscript", t: "📄 稿件" },
  { v: "conference", t: "🎤 会议" }, { v: "exercise", t: "🏃 运动" }, { v: "diet", t: "🍚 饮食" },
  { v: "finance", t: "💰 开支" }, { v: "admin", t: "🏡 事务" },
];
const COLL_NAME = {
  ideas: "想法", schedule: "日程", reading: "文献", manuscripts: "稿件",
  conferences: "会议", exercise: "运动", diet: "饮食", finance: "开支", admin: "生活事务", lists: "清单",
};

/* 分拣一条待分类的想法：把它变成日程/开支/文献等等，然后删掉原来那条。
 *
 * 关键在于**必须带上完整正文**。手机上速记的note，第一行进 title、
 * 全文进 body；以前这里只把 title 塞进捕捉框，存完又把原记录删掉，
 * 于是除了第一行以外的内容全部消失 —— 不报错、不提示，
 * 而这正是手机速记最主要的使用路径。
 * 首屏现在根本不带 body，所以一定要先取全量。 */
async function sortIdea(id) {
  let r = byId("ideas", id);
  if (!r) return toast("这条想法已经不在了");
  if (r._body_more) {
    try { r = await ensureFull("ideas", id); }
    catch (e) {
      return toast("取不到这条的完整内容，先别分拣 —— 免得只搬走第一行。");
    }
  }
  /* 手机速记存的时候，第一行进 title、**全文**（含第一行）进 body。
     所以不能无脑 title + body 拼，会把第一行重复一遍。 */
  const title = (r.title || "").trim();
  const body = (r.body || "").trim();
  let full;
  if (!body) full = title;
  else if (body === title || body.startsWith(title)) full = body;
  else full = (title ? title + "\n" : "") + body;
  quickCapture(full, id);
}
window.sortIdea = sortIdea;

function quickCapture(preset, fromIdeaId) {
  UI.modal("⚡ 快速捕捉", `
    <div class="field wide"><label>一句话就好（⌘/Ctrl+Enter 直接存）</label>
      <textarea id="capText" style="min-height:64px" placeholder="明天下午三点和合作者讨论 Table 5　/　跑步 35 分钟　/　读 He & Krishnamurthy 2013　/　交房租 3800">${esc(preset || "")}</textarea></div>
    <div class="field wide"><label>落到哪里</label>
      <div class="pill-select" data-pill="capTo">
        ${CAP_KINDS.map((k, i) => `<button type="button" data-v="${k.v}" class="${i === 0 ? "on" : ""}">${k.t}</button>`).join("")}
      </div><input type="hidden" id="f_capTo" value="auto"></div>
    <div id="capPreview"></div>`,
    `<button class="btn primary" id="capSave">存下</button>
     <span class="spacer"></span><button class="btn" data-close>取消</button>`);

  const ta = $("#capText");
  const refresh = () => {
    const box = $("#capPreview"), to = $("#f_capTo");
    if (!box || !to || !document.body.contains(ta)) return;   // 弹窗已关掉，debounce 别再跑
    const text = ta.value.trim();
    if (!text) { box.innerHTML = ""; return; }
    const hint = to.value;
    let parsed;
    try { parsed = CAP.toRecord(text, hint, new Date()); }
    catch (e) { box.innerHTML = `<div class="wz-result bad" style="display:block">解析出错：${esc(e.message)}</div>`; return; }
    const dups = CAP.findDuplicates(text, parsed.collection === "manuscripts" ? "ideas" : parsed.collection);
    box.innerHTML = `
      <div class="cap-prev">
        <div class="cap-line"><b>→ ${esc(COLL_NAME[parsed.collection] || parsed.collection)}</b>
          ${parsed.patchId ? `<span class="badge b">挂到已有稿件</span>` : `<span class="badge">新建一条</span>`}
          ${hint === "auto" ? `<span class="badge v">自动判断</span>` : ""}</div>
        <div class="cap-title">${esc(parsed.record.title || parsed.record.next_action || "（无题）")}</div>
        ${parsed.notes.length ? `<div class="cap-notes">已替你填好：${parsed.notes.map(n => `<span class="badge g">${esc(n)}</span>`).join("")}</div>` : ""}
        ${dups.length ? `<div class="cap-dup">⚠️ 和已有的 ${dups.length} 条很像：
          ${dups.map(d => `<div class="tiny">· ${esc(d.rec.title || "")}（相似度 ${Math.round(d.sim * 100)}%）</div>`).join("")}
          <div class="tiny muted" style="margin-top:3px">仍然可以存；语义上是不是真重复，交给每周的 AI 体检去判断，这里不花那个钱。</div></div>`
          : (dups.partial ? `<div class="tiny muted">查重只比对了近期这一段记录，更早的没比 —— 没提示不代表以前没记过。</div>` : "")}
      </div>`;
  };
  ta.oninput = debounce(refresh, 160);
  $$('[data-pill="capTo"] button').forEach(b => b.addEventListener("click", () => setTimeout(refresh, 10)));
  refresh();

  let saving = false;
  const save = async () => {
    if (saving) return;                       // 连点两下不该存出两条
    const text = ta.value.trim(); if (!text) return;
    saving = true;
    const btn = $("#capSave");
    if (btn) { btn.disabled = true; btn.textContent = "存入中…"; }
    try {
    const parsed = CAP.toRecord(text, $("#f_capTo").value, new Date());
    if (parsed.patchId) {
      await patchRec(parsed.collection, parsed.patchId, parsed.record);
    } else {
      await saveRec(parsed.collection, parsed.record);
    }
    if (fromIdeaId) await deleteRec("ideas", fromIdeaId);
    UI.closeModal(); render(); renderNav();
    if (typeof RAIL !== "undefined") RAIL.renderCalendar();    // 加完日程右栏要当场看得见
    afterCapture(parsed);
    } catch (e) {
      saving = false;
      if (btn) { btn.disabled = false; btn.textContent = "存下"; }
      throw e;
    }
  };
  $("#capSave").onclick = save;
  ta.onkeydown = e => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") save(); };
  setTimeout(() => ta.focus(), 60);
}
