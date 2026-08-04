/* 读文献（闯关式） + 想法画布 */

const READ_STATUS = [{ v: "to-read", t: "待读" }, { v: "reading", t: "在读" }, { v: "done", t: "读完" }];
const READ_LEVEL = [{ v: "skim", t: "略读 1分" }, { v: "deep", t: "精读 3分" }, { v: "critical", t: "批判 5分" }];

window.schema_reading = () => [
  { k: "title", label: "文献题目", type: "text", wide: true },
  { k: "authors", label: "作者", type: "tags" },
  { k: "year", label: "年份", type: "number" },
  { k: "journal", label: "期刊", type: "text" },
  { k: "link", label: "链接", type: "url" },
  { k: "doi", label: "DOI", type: "text" },
  { k: "status", label: "状态", type: "select", opts: READ_STATUS },
  { k: "level", label: "阅读深度", type: "select", opts: READ_LEVEL },
  { k: "topic", label: "所属关卡/主题", type: "text" },
  { k: "read_date", label: "读完日期", type: "date" },
  { k: "question", label: "研究问题", type: "textarea", wide: true },
  { k: "background", label: "背景与文献位置", type: "textarea", wide: true },
  { k: "method", label: "识别策略 / 方法", type: "textarea", wide: true },
  { k: "data", label: "数据", type: "textarea", wide: true },
  { k: "findings", label: "主要结论", type: "textarea", wide: true },
  { k: "contribution", label: "贡献与局限", type: "textarea", wide: true },
  { k: "relates_to", label: "与我哪篇稿件相关", type: "text", wide: true },
];
window.schema_ideas = () => [
  { k: "title", label: "一句话想法", type: "text", wide: true },
  { k: "kind", label: "类型", type: "select", opts: [{ v: "idea", t: "想法" }, { v: "question", t: "疑问" }, { v: "ref", t: "线索" }, { v: "link", t: "链接" }] },
  { k: "status", label: "状态", type: "select", opts: [{ v: "new", t: "新" }, { v: "adopted", t: "采纳" }, { v: "rejected", t: "放弃" }] },
  { k: "source", label: "来源", type: "text" },
  { k: "tags", label: "标签", type: "tags" },
];
window.schema_levels = () => [
  { k: "title", label: "关卡主题", type: "text", wide: true },
  { k: "target", label: "目标篇数", type: "number" },
  { k: "note", label: "说明", type: "textarea", wide: true },
];

/* -------------------------------------------------------------- 计算 */
function xpOf(r) {
  const map = (S.config.reading && S.config.reading.xp) || { skim: 1, deep: 3, critical: 5 };
  return r.status === "done" ? (map[r.level] || 1) : 0;
}
function totalXp() { return rows("reading").reduce((s, r) => s + xpOf(r), 0); }
function levelOfXp(xp) {
  let lv = 1, need = 10, acc = 0;
  while (xp >= acc + need) { acc += need; lv++; need = Math.round(need * 1.35); }
  return { level: lv, into: xp - acc, need, pct: Math.round(((xp - acc) / need) * 100) };
}
function readStreak() {
  const days = new Set(rows("reading").filter(r => r.read_date).map(r => String(r.read_date).slice(0, 10)));
  let n = 0; const d = new Date();
  for (; ;) {
    if (days.has(todayStr(d))) n++;
    else if (n > 0 || todayStr(d) !== todayStr()) break;
    d.setDate(d.getDate() - 1);
    if (n > 400) break;
  }
  return { streak: n, days };
}
function weekCount() {
  const now = new Date(); const monday = new Date(now); monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  const m = todayStr(monday);
  return rows("reading").filter(r => r.read_date && String(r.read_date).slice(0, 10) >= m).length;
}
/* 遗忘曲线复习队列 */
function reviewQueue() {
  const gaps = (S.config.reading && S.config.reading.review_days) || [1, 7, 30, 90];
  const out = [];
  rows("reading").filter(r => r.status === "done" && r.read_date).forEach(r => {
    const done = (r.reviews || []).map(x => x.gap);
    const age = daysBetween(r.read_date, todayStr());
    if (age == null) return;
    /* 每篇只排「当前该做的那一档」——以前一篇很久以前读的会同时占掉
       第 1/7/30/90 天四行，三篇就把队列塞满，真正今天该复习的反而被挤出去 */
    const due = gaps.filter(g => !done.includes(g) && age >= g);
    if (!due.length) return;
    const g = Math.min.apply(null, due);
    out.push({ rec: r, gap: g, age, overdue: age - g, backlog: due.length });
  });
  /* 该做而没做得越久的排前面 */
  return out.sort((a, b) => b.overdue - a.overdue).slice(0, 12);
}

/* -------------------------------------------------------------- 视图 */
VIEWS.reading = () => {
  const rs = rows("reading");
  const xp = totalXp(), lv = levelOfXp(xp), st = readStreak();
  const goal = (S.config.reading && S.config.reading.weekly_goal) || 5;
  const wk = weekCount();
  const queue = reviewQueue();

  const tut = UI.tut("reading", "每日辅学 · 闯关怎么玩", `
    <p>每读一篇就填一张卡：<b>研究问题、背景、识别策略、数据、结论、贡献与局限、与我哪篇稿子相关</b>。字段固定是有意的——半年后你想找「所有用 DID 做中国市场的论文」，一秒就能筛出来。</p>
    <p><b>经验值</b>：略读 1 分、精读 3 分、批判 5 分，累积升级。<b>关卡</b>是主题包（例如「intermediary asset pricing · 15 篇」），打通时可以让 AI 直接生成该主题的综述初稿——这才是真正的奖励。</p>
    <p><b>复习队列</b>按遗忘曲线（1/7/30/90 天）自动排。点「出题」让 AI 针对这篇提问，答不上来就说明当时没读透。</p>
    <p>连续天数只看「读完日期」，所以填卡时别忘了写日期。</p>`);

  const head = `<div class="grid g4" style="margin-bottom:14px">
    <div class="stat"><div class="k">等级</div><div class="v">Lv.${lv.level}</div><div class="d">${lv.into}/${lv.need} 经验</div></div>
    <div class="stat ${st.streak >= 3 ? "good" : ""}"><div class="k">连续天数</div><div class="v">${st.streak}</div><div class="d">🔥 保持住</div></div>
    <div class="stat ${wk >= goal ? "good" : "warn"}"><div class="k">本周</div><div class="v">${wk}/${goal}</div><div class="d">周目标</div></div>
    <div class="stat"><div class="k">总计</div><div class="v">${rs.filter(r => r.status === "done").length}</div><div class="d">共 ${rs.length} 条</div></div>
  </div>`;

  const levels = rows("levels").map(l => {
    const list = rs.filter(r => (r.topic || "").trim() === (l.title || "").trim() && r.status === "done");
    const pct = Math.min(100, Math.round(list.length / Math.max(1, l.target || 10) * 100));
    return `<div class="level-card">
      <div class="lt"><div class="xp-ring" style="--p:${pct}"><span>${pct}%</span></div>
        <div><div>${esc(l.title || "")}</div>
        <div class="tiny muted">${list.length} / ${l.target || 10} 篇</div></div></div>
      ${pct >= 100 ? `<button class="btn sm primary" style="margin-top:8px" data-levelup="${l.id}">🎉 通关 · 生成综述初稿</button>`
        : `<div class="tiny muted" style="margin-top:7px">还差 ${Math.max(0, (l.target || 10) - list.length)} 篇</div>`}
      <button class="btn sm ghost" style="margin-top:5px" data-edit="levels:${l.id}">编辑</button>
    </div>`;
  }).join("");

  const queueHtml = queue.length ? queue.map(q => `<div class="row-line"><div class="rl-main">
      <div class="rl-title">${esc(q.rec.title || "")}</div>
      <div class="rl-meta">读于 ${esc(q.rec.read_date)} · 已 ${q.age} 天 · 该做第 <b>${q.gap}</b> 天复习</div>
    </div><div class="rl-acts">
      <button class="btn sm" data-quiz="${q.rec.id}:${q.gap}">出题</button>
      <button class="btn sm ghost" data-reviewed="${q.rec.id}:${q.gap}">✓ 已复习</button>
    </div></div>`).join("") : `<div class="empty">暂无到期复习 · 读完的文献会按 1/7/30/90 天自动排进来</div>`;

  const groups = {};
  rs.forEach(r => { (groups[r.topic || "未归类"] = groups[r.topic || "未归类"] || []).push(r); });
  /* 领域助读：自己设领域，工作台每周排一次任务给 Claude，产出一条循序渐进的中文路线 */
  const flds = ((S.config.reading || {}).fields) || [];
  const primerRows = rows("reading").filter(r => r.source === "primer");
  const byWeek = {};
  primerRows.forEach(r => { (byWeek[r.primer_week || "—"] = byWeek[r.primer_week || "—"] || []).push(r); });
  const fieldCard = UI.card("rd-primer", "领域助读", flds.length ? `${flds.length} 个领域` : "还没设", `
    <div class="small muted" style="margin-bottom:10px">
      设一个你想快速入门的领域，工作台每周会排一个任务给 Claude：挑出这个领域最经典的四到六篇，
      按由浅入深排好顺序，每篇写一段中文重述（问题是什么、怎么做的、结论边界在哪、
      读完该带什么问题看下一篇），再给一份五天的安排。<b>走你的订阅，不花 API 钱。</b></div>
    <div class="form-grid">
      <div class="field wide"><label>关注领域（逗号分隔，第一个是本周要做的）</label>
        <input id="rd_fields" value="${esc(flds.map(f => f.name || f).join(", "))}"
          placeholder="intermediary asset pricing, household finance">
        <div class="hint">用英文写更准 —— 经典文献的检索词基本都是英文。</div></div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:10px">
      <button class="btn primary" id="rdFieldSave">保存领域</button>
      <button class="btn" id="rdPrimerNow">生成本周助读</button>
      <span class="spacer"></span>
      <span class="small muted">${primerRows.length ? `已产出 ${primerRows.length} 篇助读文献` : ""}</span>
    </div>
    ${Object.keys(byWeek).sort().reverse().slice(0, 2).map(w => `
      <div class="hr"></div><div class="tiny muted" style="margin-bottom:5px">${esc(w)}</div>
      ${byWeek[w].sort((a, b) => (a.primer_order || 0) - (b.primer_order || 0)).map(r => `
        <div class="row-line" data-pick="reading:${r.id}"><div class="rl-main">
          <div class="rl-title small">${r.primer_order || ""}. ${esc(r.title || "")}
            <span class="badge">${esc(r.year || "")}</span>
            ${r.status === "done" ? `<span class="badge g">读完</span>` : ""}</div>
          <div class="rl-meta">${esc((r.question || "").slice(0, 70))}</div>
        </div><div class="rl-acts"><button class="btn sm" data-edit="reading:${r.id}">打开</button></div></div>`).join("")}
    `).join("")}
    <div id="rdPrimerOut" class="small" style="margin-top:9px"></div>`,
    { icon: "🧭", defaultOpen: !!flds.length });

  const list = Object.keys(groups).sort().map(t => UI.card("rd:" + t, t, `${groups[t].length} 篇`,
    groups[t].slice().sort((a, b) => String(b.read_date || "").localeCompare(String(a.read_date || ""))).map(r => `
      <div class="row-line" data-pick="reading:${r.id}"><div class="rl-main">
        <div class="rl-title">
          <span class="badge ${r.status === "done" ? "g" : r.status === "reading" ? "a" : ""}">${esc((READ_STATUS.find(x => x.v === r.status) || {}).t || "待读")}</span>
          ${esc(r.title || "")} ${r.link ? `<a href="${esc(r.link)}" target="_blank">↗</a>` : ""}${UI.linkBadge(r)}
          ${r.status === "done" ? `<span class="badge v">+${xpOf(r)} XP</span>` : ""}</div>
        <div class="rl-meta">${esc([].concat(r.authors || []).join(", "))}${r.year ? " (" + r.year + ")" : ""}
          ${r.journal ? " · " + esc(r.journal) : ""}${r.read_date ? " · 读于 " + esc(r.read_date) : ""}
          ${r.relates_to ? " · 关联：" + esc(r.relates_to) : ""}</div>
        ${r.question ? `<div class="rl-meta" style="margin-top:3px">❓ ${esc(String(r.question).slice(0, 140))}</div>` : ""}
        ${r.method ? `<div class="rl-meta">🔬 ${esc(String(r.method).slice(0, 140))}</div>` : ""}
      </div><div class="rl-acts">
        <button class="btn sm" data-ai="reading:${r.id}">🤖</button>
        <button class="btn sm" data-edit="reading:${r.id}">编辑</button>
      </div></div>`).join(""), { icon: "📚" })).join("");

  return `<div class="page-head"><h1>📚 读文献</h1><div class="sub">结构化记录 · 闯关 · 遗忘曲线复习</div>
    <span class="spacer"></span>
    <button class="btn" data-new="levels">＋ 新关卡</button>
    <button class="btn primary" data-new="reading">＋ 新文献</button></div>
    ${tut}${head}
    ${typeof LIB !== "undefined" ? LIB.card() : ""}
    ${fieldCard}
    ${UI.card("rd-levels", "关卡 · 主题进度", "Levels", levels ? `<div class="grid g3">${levels}</div>`
      : `<div class="empty">还没有关卡。关卡 = 一个主题 + 目标篇数，例如「intermediary asset pricing · 15 篇」。</div>`, { icon: "🎮" })}
    ${UI.card("rd-review", "复习队列", "Spaced repetition", queueHtml, { icon: "🔁", actions: sampleBtn(["reading"]) })}
    ${list || `<div class="empty">还没有文献记录。</div>`}`;
};

/* ------------------------------------------------------------ 想法画布 */
VIEWS.ideas = () => {
  const is = rows("ideas");
  const tut = UI.tut("ideas", "想法区怎么用", `
    <p>便利贴可以<b>直接拖动</b>摆位置，位置会保存。颜色按类型区分：想法（黄）、疑问（蓝）、线索（绿）、链接（紫）。</p>
    <p>任何一张便利贴都能<b>一键升级为稿件</b>或<b>扔进阅读清单</b>——想法不该停留在便利贴上。</p>
    <p>按 <kbd>c</kbd> 可以在任何页面快速捕捉一条想法，先记下来再说。</p>
    <p>自动任务产出的新想法也会落到这里（标记为 🤖），你可以标「采纳」或「放弃」——这个反馈会写进台账，让它以后不再重复提类似的东西。</p>`);
  /* 先记下已经占了哪些格子，新贴才不会正好盖在旧贴上 */
  const taken = new Set(is.filter(r => r.x != null && r.y != null)
    .map(r => `${Math.round(r.x / 186)},${Math.round(r.y / 96)}`));
  let slot = 0;
  const nextFree = () => {
    while (taken.has(`${slot % 5},${Math.floor(slot / 5)}`)) slot++;
    const cell = `${slot % 5},${Math.floor(slot / 5)}`;
    taken.add(cell);
    const col = slot % 5, row = Math.floor(slot / 5);
    slot++;
    return { x: 18 + col * 186, y: 18 + row * 96 };
  };
  const notes = is.map((r) => {
    const auto = (r.x == null || r.y == null) ? nextFree() : null;
    const x = r.x != null ? r.x : auto.x;
    const y = r.y != null ? r.y : auto.y;
    return `<div class="note k-${esc(r.kind || "idea")}" data-note="${r.id}" style="left:${x}px;top:${y}px">
      <span class="nx" data-del="ideas:${r.id}">✕</span>
      <div class="nt">${r.source === "auto" ? "🤖 " : ""}${esc(r.title || "")}${UI.linkBadge(r)}</div>
      <div class="tiny">${esc(String(r.body || r._preview || "").slice(0, 90))}</div>
      <div style="margin-top:5px;display:flex;gap:3px;flex-wrap:wrap">
        <button class="btn sm ghost" data-promote="${r.id}" title="升级为稿件">⤴ 稿件</button>
        <button class="btn sm ghost" data-edit="ideas:${r.id}">✎</button>
      </div></div>`;
  }).join("");
  const adopted = is.filter(r => r.status === "adopted").length;
  return `<div class="page-head"><h1>💡 想法</h1><div class="sub">头脑风暴画布 · 可拖动</div>
    <span class="spacer"></span>
    <span class="badge">已采纳 ${adopted}</span>
    <button class="btn primary" data-new="ideas">＋ 便利贴</button></div>
    ${tut}
    ${UI.card("ideas-canvas", "画布", "Canvas", `<div class="bcanvas" id="bcanvas">${notes || `<div class="empty" style="padding:40px">空空如也。点右上角加一张便利贴，或按 c 快速捕捉。</div>`}</div>`, { icon: "🧠" })}`;
};

window._bindPrimer = function () {
  const sv = $("#rdFieldSave");
  if (sv) sv.onclick = async () => {
    const names = $("#rd_fields").value.split(/[,，]/).map(x => x.trim()).filter(Boolean);
    await saveConfig({
      reading: Object.assign({}, S.config.reading, {
        fields: names.map((n, i) => ({ name: n, active: i === 0 })),
      }),
    });
    render(); toast(names.length ? `已设 ${names.length} 个领域，第一个是本周要做的` : "已清空领域");
  };
  const go = $("#rdPrimerNow");
  if (go) go.onclick = async () => {
    const out = $("#rdPrimerOut");
    out.textContent = "排任务中…";
    const r = await API.post("run/primer-queue", {});
    const d = (r && r.data) || r || {};
    out.innerHTML = (d.ok === false)
      ? `<span style="color:var(--red)">${esc(d.detail || "排队失败")}</span>`
      : `<span style="color:var(--green)">已排进自动任务队列。Claude 会在你不用电脑、额度富余的时候做，
         做完出现在「AI 新产出」里，文献也会自动进这一页。</span>`;
  };
};

window.bindKnowledgeExtras = function () {
  window._bindPrimer();
  /* 便利贴拖动 */
  $$(".note[data-note]").forEach(n => {
    if (n._bound) return; n._bound = true;
    let sx, sy, ox, oy, moved = false;
    const down = e => {
      if (e.target.closest("button,.nx")) return;
      const p = e.touches ? e.touches[0] : e;
      sx = p.clientX; sy = p.clientY; ox = n.offsetLeft; oy = n.offsetTop; moved = false;
      n.classList.add("dragging");
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
      document.addEventListener("touchmove", mv, { passive: false }); document.addEventListener("touchend", up);
      e.preventDefault();
    };
    const mv = e => {
      const p = e.touches ? e.touches[0] : e;
      const nx = Math.max(0, ox + p.clientX - sx), ny = Math.max(0, oy + p.clientY - sy);
      n.style.left = nx + "px"; n.style.top = ny + "px";
      if (Math.abs(p.clientX - sx) + Math.abs(p.clientY - sy) > 4) moved = true;
    };
    const up = async () => {
      document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up);
      document.removeEventListener("touchmove", mv); document.removeEventListener("touchend", up);
      n.classList.remove("dragging");
      if (moved) await patchRec("ideas", n.dataset.note, { x: n.offsetLeft, y: n.offsetTop });
    };
    n.addEventListener("mousedown", down);
    n.addEventListener("touchstart", down, { passive: false });
  });
  $$("[data-promote]").forEach(b => b.onclick = async e => {
    e.stopPropagation();
    /* 便利贴的正文在首屏是截断的。这里是**新建**一条稿件，
       新对象上没有 _body_more 标记，saveRec 那道网也就不会响 ——
       于是一条上千字的想法，升级成稿件后只剩开头 160 字，
       而原来那条被标成「已采纳」，看上去一切正常。先取全量再复制。 */
    let idea = byId("ideas", b.dataset.promote);
    try {
      idea = await ensureFull("ideas", b.dataset.promote);
    } catch (err) {
      toast("取不到这条想法的完整内容，先别升级 —— 免得只搬过去一个开头。");
      return;
    }
    if (!idea) return toast("找不到这条想法");
    await saveRec("manuscripts", { title: idea.title, stage: "idea", progress: 0, body: idea.body || "" });
    await patchRec("ideas", idea.id, { status: "adopted" });
    toast("已升级为稿件"); go("manuscripts");
  });
  $$("[data-reviewed]").forEach(b => b.onclick = async () => {
    const [id, gap] = b.dataset.reviewed.split(":");
    // 同理：复习记录也是追加，要接在新鲜那份后面
    await patchRec("reading", id, fresh => ({
      reviews: (fresh.reviews || []).concat([{ gap: Number(gap), date: todayStr() }]),
    }));
    render(); toast("已记录复习");
  });
  $$("[data-quiz]").forEach(b => b.onclick = () => {
    const [id, gap] = b.dataset.quiz.split(":");
    const r = byId("reading", id);
    openAiDialog("reading:" + id, {
      preset: `我在 ${r.read_date} 读过这篇文献，现在是第 ${gap} 天复习。请**不要**直接给我答案：先根据下面我的笔记出 3 道针对性的问题（重点考识别策略和关键假设），我答完后你再逐条判分并指出我理解偏差的地方。`,
      kind: "quiz",
    });
  });
  $$("[data-levelup]").forEach(b => b.onclick = () => {
    const l = byId("levels", b.dataset.levelup);
    const list = rows("reading").filter(r => (r.topic || "").trim() === (l.title || "").trim() && r.status === "done");
    openAiDialog("levels:" + l.id, {
      preset: `我已读完「${l.title}」主题下的 ${list.length} 篇文献（笔记见下）。请写一份该主题的综述初稿：先梳理这些文献的共识与分歧，再指出尚未解决的空白，最后给出 2–3 个可做的研究方向。要求：只使用我笔记中确实存在的文献，不要引入我没读过的引用；如需补充文献请单列一节并标注"待我核实"。`,
      kind: "review-draft",
      body: list.map(r => `### ${r.title} (${r.year || ""})\n问题：${r.question || ""}\n方法：${r.method || ""}\n结论：${r.findings || ""}\n局限：${r.contribution || ""}`).join("\n\n"),
    });
  });
};
