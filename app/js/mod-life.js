/* 生活（仅存本机，永不进 git）：饮食 / 运动 / 重要日子 / 清单 / 生活事务 / 开支 */

window.schema_diet = () => [
  { k: "date", label: "日期", type: "date" },
  { k: "meal", label: "餐次", type: "select", opts: [{ v: "breakfast", t: "早" }, { v: "lunch", t: "午" }, { v: "dinner", t: "晚" }, { v: "snack", t: "加餐" }] },
  { k: "title", label: "吃了什么", type: "text", wide: true },
  { k: "kcal", label: "热量(可选)", type: "number" },
  { k: "mood", label: "感觉", type: "select", opts: [{ v: "good", t: "很好" }, { v: "ok", t: "一般" }, { v: "heavy", t: "过量" }] },
];
window.schema_exercise = () => [
  { k: "date", label: "日期", type: "date" },
  { k: "title", label: "项目", type: "text" },
  { k: "minutes", label: "时长(分钟)", type: "number" },
  { k: "intensity", label: "强度", type: "select", opts: [{ v: "light", t: "轻" }, { v: "moderate", t: "中" }, { v: "hard", t: "大" }] },
  { k: "note", label: "备注", type: "text", wide: true },
];
window.schema_dates = () => [
  { k: "title", label: "事项", type: "text", wide: true },
  { k: "date", label: "日期", type: "date" },
  { k: "yearly", label: "每年重复", type: "check", checkLabel: "每年" },
];
window.schema_lists = () => [
  { k: "title", label: "条目", type: "text", wide: true },
  { k: "list", label: "归入清单", type: "select", opts: [{ v: "groceries", t: "买菜" }, { v: "restaurants", t: "餐厅" }, { v: "travel", t: "旅行" }, { v: "wishlist", t: "心愿" }, { v: "other", t: "其他" }] },
  { k: "done", label: "已完成", type: "check" },
];
window.schema_admin = () => [
  { k: "title", label: "事项", type: "text", wide: true },
  { k: "date", label: "截止", type: "date" },
  { k: "repeat", label: "重复", type: "select", opts: [{ v: "", t: "不重复" }, { v: "monthly", t: "每月" }, { v: "quarterly", t: "每季" }, { v: "yearly", t: "每年" }] },
  { k: "done", label: "已完成", type: "check" },
];
window.schema_finance = () => [
  { k: "date", label: "日期", type: "date" },
  { k: "title", label: "项目", type: "text", wide: true },
  { k: "amount", label: "金额", type: "number" },
  { k: "cat", label: "类别", type: "select", opts: [{ v: "food", t: "吃" }, { v: "home", t: "居家" }, { v: "travel", t: "出行" }, { v: "research", t: "科研" }, { v: "fun", t: "娱乐" }, { v: "other", t: "其他" }] },
];

function last7(coll, valFn) {
  const out = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    const ds = todayStr(d);
    out.push(rows(coll).filter(r => String(r.date || "").slice(0, 10) === ds).reduce((s, r) => s + (valFn(r) || 0), 0));
  }
  return out;
}

VIEWS.life = () => {
  const tut = UI.tut("life", "生活区怎么用（数据只在本机）", `
    <p>这一区的所有数据<b>只保存在这台电脑上</b>，不会进 git 仓库、不会上传到任何地方——这是刻意的隐私边界：学术数据可以同步，饮食体重不必。</p>
    <p>饮食和运动都以「一天一条或多条」的方式记，下面有最近 7 天的趋势小图。热量可以留空；想估算时点 🤖 让 AI 按你写的食物估。</p>
    <p>清单、重要日子、生活事务和学术那边共用同一套提醒逻辑——填了日期就会出现在今日页。</p>`);

  const kcal = last7("diet", r => Number(r.kcal) || 0);
  const mins = last7("exercise", r => Number(r.minutes) || 0);
  const exWeek = mins.reduce((a, b) => a + b, 0);

  const dietCard = UI.card("life-diet", "饮食记录", "Diet", `
    <div class="grid g2">
      <div><div class="tiny muted">最近 7 天热量（未填则为 0）</div>${UI.spark(kcal, { area: true, color: "var(--amber)" })}</div>
      <div><div class="tiny muted">今天</div>
        ${rows("diet").filter(r => String(r.date || "").slice(0, 10) === todayStr()).map(r => `
          <div class="row-line"><div class="rl-main"><div class="rl-title small">${esc(r.title || "")}
            <span class="badge">${esc({ breakfast: "早", lunch: "午", dinner: "晚", snack: "加餐" }[r.meal] || "")}</span>
            ${r.kcal ? `<span class="badge a">${r.kcal} kcal</span>` : ""}</div></div>
            <div class="rl-acts"><button class="btn sm" data-edit="diet:${r.id}">✎</button></div></div>`).join("") || `<div class="empty">今天还没记</div>`}
      </div></div>
    <div style="margin-top:9px"><button class="btn primary sm" data-new="diet">＋ 记一餐</button>
      <button class="btn sm" data-ai="diet:">🤖 让 AI 估热量/给建议</button></div>`, { icon: "🍚" });

  const exCard = UI.card("life-ex", "运动记录", "Exercise", `
    <div class="grid g2">
      <div><div class="tiny muted">最近 7 天时长 · 本周合计 ${exWeek} 分钟</div>${UI.spark(mins, { area: true, color: "var(--green)" })}</div>
      <div>${rows("exercise").slice().sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))).slice(0, 5).map(r => `
        <div class="row-line"><div class="rl-main"><div class="rl-title small">${esc(r.title || "")}
          <span class="badge g">${r.minutes || 0} 分</span>
          <span class="badge">${esc({ light: "轻", moderate: "中", hard: "大" }[r.intensity] || "")}</span></div>
          <div class="rl-meta">${esc(r.date || "")}</div></div>
          <div class="rl-acts"><button class="btn sm" data-edit="exercise:${r.id}">✎</button></div></div>`).join("") || `<div class="empty">还没有记录</div>`}
      </div></div>
    <div style="margin-top:9px"><button class="btn primary sm" data-new="exercise">＋ 记一次运动</button></div>`, { icon: "🏃" });

  const listGroups = { groceries: "🛒 买菜", restaurants: "🍜 餐厅", travel: "✈️ 旅行", wishlist: "🎁 心愿", other: "📋 其他" };
  const listsCard = UI.card("life-lists", "清单", "Lists", Object.keys(listGroups).map(g => {
    const items = rows("lists").filter(r => (r.list || "other") === g);
    if (!items.length) return "";
    return `<div style="margin-bottom:9px"><div class="tiny muted">${listGroups[g]}</div>
      ${items.map(r => `<div class="row-line ${r.done ? "done" : ""}">
        <input type="checkbox" ${r.done ? "checked" : ""} data-toggle="lists:${r.id}:done">
        <div class="rl-main"><div class="rl-title">${esc(r.title || "")}</div></div>
        <div class="rl-acts"><button class="btn sm" data-del="lists:${r.id}">🗑</button></div></div>`).join("")}</div>`;
  }).join("") + `<button class="btn primary sm" data-new="lists">＋ 加一条</button>`, { icon: "📝" });

  const datesCard = UI.card("life-dates", "重要日子", "Dates", rows("dates").slice()
    .sort((a, b) => (daysUntil(a.date, a.yearly) ?? 999) - (daysUntil(b.date, b.yearly) ?? 999)).map(r => {
      const n = daysUntil(r.date, r.yearly);
      return `<div class="row-line"><div class="rl-main"><div class="rl-title">${esc(r.title || "")}
        <span class="badge">${esc(r.date || "")}</span>${r.yearly ? `<span class="badge v">每年</span>` : ""}${daysChip(n)}</div></div>
        <div class="rl-acts"><button class="btn sm" data-edit="dates:${r.id}">✎</button></div></div>`;
    }).join("") + `<button class="btn primary sm" style="margin-top:7px" data-new="dates">＋ 加一个</button>`, { icon: "🎂" });

  const adminCard = UI.card("life-admin", "生活事务", "Admin", rows("admin").slice()
    .sort((a, b) => String(a.date || "").localeCompare(String(b.date || ""))).map(r => {
      const n = daysUntil(r.date);
      return `<div class="row-line ${r.done ? "done" : ""}">
        <input type="checkbox" ${r.done ? "checked" : ""} data-toggle="admin:${r.id}:done">
        <div class="rl-main"><div class="rl-title">${esc(r.title || "")}
          ${r.date ? `<span class="badge">${esc(r.date)}</span>` : ""}${r.done ? "" : daysChip(n)}
          ${r.repeat ? `<span class="badge v">${esc({ monthly: "每月", quarterly: "每季", yearly: "每年" }[r.repeat] || r.repeat)}</span>` : ""}</div></div>
        <div class="rl-acts"><button class="btn sm" data-edit="admin:${r.id}">✎</button></div></div>`;
    }).join("") + `<button class="btn primary sm" style="margin-top:7px" data-new="admin">＋ 加一条</button>`, { icon: "🏡" });

  const fin = rows("finance");
  /* 首屏为了体积只带近期的生活流水。这里必须**如实说**是哪段时间的合计 ——
     拿半年数据算出来的数字挂上「合计」两个字，比不显示更糟。

     三处细节都得对上，否则标签和数字还是两回事：
     · 区间用服务端给的 since，不是写死的 180 天 ——
       条数上限一生效，实际覆盖的可能只有 130 天；
     · 从搜索里点开一笔去年的开支，那条会被顺手读进内存，
       照单全收就会把区间外的也算进来，所以求和时按 since 过滤；
     · 没有日期的（比如忘了填日期的房租）服务端是**全带回来**的，
       所以要算进去 —— 否则列表里明明列着它，合计里却没有它。 */
  const finMeta = (S.dataMeta || {}).finance || {};
  const inWindow = r => {
    if (!finMeta.partial || !finMeta.since) return true;
    const d = String(r.date || "").slice(0, 10);
    return d ? d >= finMeta.since : !!finMeta.undated_complete;
  };
  const finTotal = fin.reduce((s, r) => s + (inWindow(r) ? (Number(r.amount) || 0) : 0), 0);
  const finCard = UI.card("life-fin", "开支", "Finance", `
    <div class="small muted">${finMeta.partial
      ? `${esc(finMeta.since || "")} 以来合计 <b>${finTotal.toFixed(2)}</b>
         <span class="muted">· 共 ${finMeta.total} 条，这里只带了 ${finMeta.shown} 条</span>
         <button class="btn sm ghost" data-loadall="finance" style="margin-left:6px">加载全部</button>`
      : `合计 <b>${finTotal.toFixed(2)}</b>`}</div>
    ${fin.slice().sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))).slice(0, 12).map(r => `
      <div class="row-line"><div class="rl-main"><div class="rl-title small">${esc(r.title || "")}
        <span class="badge">${Number(r.amount || 0).toFixed(2)}</span>
        <span class="badge">${esc({ food: "吃", home: "居家", travel: "出行", research: "科研", fun: "娱乐", other: "其他" }[r.cat] || "")}</span></div>
        <div class="rl-meta">${esc(r.date || "")}</div></div>
      <div class="rl-acts"><button class="btn sm" data-edit="finance:${r.id}">✎</button></div></div>`).join("")
    || `<div class="empty">还没有记录</div>`}
    <button class="btn primary sm" style="margin-top:7px" data-new="finance">＋ 记一笔</button>`, { icon: "💰", defaultOpen: false });

  return `<div class="page-head"><h1>🌱 生活</h1><div class="sub">仅存本机 · 不进 git、不上传</div></div>
    ${tut}${dietCard}${exCard}${listsCard}${datesCard}${adminCard}${finCard}`;
};

const LIFE_DAYS = 180;

window.bindLifeExtras = function () {
  if (window.bindScheduleExtras) window.bindScheduleExtras();
  /* 「加载全部」：把这个集合的完整数据补进内存，统计随之变成真的合计 */
  $$("[data-loadall]").forEach(b => b.onclick = async () => {
    const coll = b.dataset.loadall;
    b.disabled = true; b.textContent = "加载中…";
    try {
      const all = await API.get(`records/${encodeURIComponent(coll)}`);
      S.data[coll] = all;
      (S.dataMeta || (S.dataMeta = {}))[coll] = { total: all.length };
      render();
      toast(`已加载全部 ${all.length} 条`);
    } catch (e) {
      b.disabled = false; b.textContent = "加载全部";
      toast("加载失败：" + (e.message || e));
    }
  });
};
