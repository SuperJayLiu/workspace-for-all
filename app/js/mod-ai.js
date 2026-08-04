/* AI 双通道（Claude 信箱 / Claude·ChatGPT 预填跳转） + 额度调度器面板 + 报告库 */

const AI_TARGETS = [
  { v: "claude", t: "Claude", url: q => "https://claude.ai/new?q=" + encodeURIComponent(q) },
  { v: "chatgpt", t: "ChatGPT", url: q => "https://chatgpt.com/?q=" + encodeURIComponent(q) },
];
const URL_LIMIT = 6000;

/* 自动任务/常用提问的预设（对应你要的五类） */
const TASK_KINDS = [
  { v: "brainstorm", t: "头脑风暴", weight: "medium", tip: "基于这篇稿件/这批笔记，提出新的角度与做法" },
  { v: "gap-scan", t: "文献缺口扫描", weight: "heavy", tip: "对照近年文献，找出尚未被回答的问题" },
  { v: "method-scan", t: "新方法扫描", weight: "medium", tip: "最近论文里出现的新方法，哪些能用在我这里" },
  { v: "data-scan", t: "新数据整理", weight: "medium", tip: "可用数据源的描述与获取链接（不下载数据）" },
  { v: "critique", t: "挑漏洞 / 审稿人攻击", weight: "heavy", tip: "以审稿人视角攻击这篇稿子" },
  { v: "audit", t: "全库体检", weight: "light", tip: "检查工作台所有信息的准确性与一致性" },
];
const KIND_T = Object.fromEntries(TASK_KINDS.map(k => [k.v, k.t]));

function contextOf(ref) {
  const [coll, id] = String(ref || "").split(":");
  const r = id ? byId(coll, id) : null;
  if (!r) return { coll, id, text: "", title: "" };
  const pick = (k, label) => r[k] ? `${label}：${Array.isArray(r[k]) ? r[k].join("、") : r[k]}\n` : "";
  let t = `【${{ manuscripts: "稿件", reading: "文献", ideas: "想法", levels: "关卡", journals: "期刊" }[coll] || coll}】${r.title || ""}\n`;
  if (coll === "manuscripts") {
    t += pick("stage", "阶段") + pick("target_journal", "目标期刊") + pick("current_journal", "在投") +
      pick("next_action", "下一步") + pick("coauthors", "合作者");
    const tl = (r.timeline || []).map(e => `  ${e.date} ${KIND_T[e.event] || EVENT_T[e.event] || e.event} ${e.journal || ""} ${e.note || ""}`).join("\n");
    if (tl) t += "投稿历史：\n" + tl + "\n";
  } else if (coll === "reading") {
    t += pick("authors", "作者") + pick("year", "年份") + pick("journal", "期刊") +
      pick("question", "研究问题") + pick("background", "背景") + pick("method", "方法") +
      pick("data", "数据") + pick("findings", "结论") + pick("contribution", "贡献与局限");
  }
  if (r.body) t += "笔记：\n" + r.body + "\n";
  return { coll, id, text: t, title: r.title || "" };
}

async function openAiDialog(ref, opts) {
  opts = opts || {};
  /* 首屏会截断长正文。喂给 AI 的上下文必须是完整的 ——
     半截笔记生成的东西看起来正常，实际是基于残缺信息，
     这种错比直接报错难发现得多。 */
  const [rc, rid] = String(ref || "").split(":");
  if (rid) {
    const cur = byId(rc, rid);
    if (cur && cur._body_more) {
      try {
        const fresh = await API.get(`records/${encodeURIComponent(rc)}/${encodeURIComponent(rid)}`);
        if (fresh && fresh.id) {
          const arr = S.data[rc] || [];
          const i = arr.findIndex(x => x.id === rid);
          if (i >= 0) arr[i] = fresh;
        }
      } catch (e) { toast("取完整笔记失败，这次的上下文可能不全"); }
    }
  }
  const ctx = contextOf(ref);
  const def = (S.config.ai && S.config.ai.default_jump) || "claude";
  const preset = opts.preset || "";
  const initial = (preset ? preset + "\n\n" : "") + "---\n" + ctx.text + (opts.body ? "\n" + opts.body : "");

  UI.modal("🤖 问 AI · " + (ctx.title || "工作台"), `
    <div class="small muted" style="margin-bottom:8px">
      <b>重活</b>（读写文件、跑文献综述、批量整理）→ 写进 <b>Claude 信箱</b>，Claude 会直接改你的文件。
      <b>即时小问题</b> → 预填跳转到 Claude 或 ChatGPT 网页（走你的订阅，不花 API 钱）。</div>
    <div class="pill-select" style="margin-bottom:9px" id="kindPills">
      ${TASK_KINDS.map(k => `<button type="button" data-kind="${k.v}" title="${esc(k.tip)}">${k.t}</button>`).join("")}
    </div>
    <div class="field wide"><label>要问什么</label>
      <textarea id="aiText" style="min-height:210px">${esc(initial)}</textarea>
      <div class="hint" id="aiLen"></div></div>`,
    `<button class="btn primary" id="aiInbox">📥 写进 Claude 信箱</button>
     <button class="btn" id="aiClaude">↗ Claude 网页</button>
     <button class="btn" id="aiGpt">↗ ChatGPT</button>
     <button class="btn ghost" id="aiCopy">复制</button>
     <span class="spacer"></span>
     <button class="btn ghost" id="aiSaveQ">存为报告</button>
     <button class="btn" data-close>关闭</button>`);

  const ta = $("#aiText");
  const upd = () => {
    const n = ta.value.length;
    $("#aiLen").innerHTML = `${n} 字符${n > URL_LIMIT ? ` · <span style="color:var(--amber)">超过 ${URL_LIMIT}，网页跳转可能被截断，建议用「复制」或写进信箱</span>` : ""}`;
  };
  ta.oninput = upd; upd();
  $$("#kindPills button").forEach(b => b.onclick = () => {
    $$("#kindPills button").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    const k = TASK_KINDS.find(x => x.v === b.dataset.kind);
    const head = {
      brainstorm: "请基于下面的材料做头脑风暴：给出 3 个（最多 3 个）此前没被提过的新角度或新做法。每条都要说明：为什么现在可行、需要什么数据、最可能的反驳是什么。避免泛泛而谈的套话。",
      "gap-scan": "请对照近三年的相关文献，找出下面这项工作周边**尚未被回答**的问题。要求：每条缺口都要给出支撑它的具体文献（作者-年份-期刊，必须真实存在，不确定就标注「待核实」），并说明为什么这个缺口值得做。",
      "method-scan": "请扫描近期论文中出现的、可以用在下面这项工作上的**新方法/新估计量/新识别策略**。每条说明：出处、核心思想、用在我这里需要满足什么条件、相比我现在的做法好在哪。",
      "data-scan": "请整理可用于下面这项工作的**数据源**。只要描述和获取链接，不要下载数据。每条给出：数据名称、覆盖范围与频率、可获取方式（链接）、已知的使用限制、以及用它能回答什么问题。",
      critique: "请以该领域顶刊（JF/JFE/RFS）审稿人的视角，写一份**攻击性**的审稿意见：找出识别策略、样本、稳健性、机制证据上的漏洞，按严重程度排序，并对每条指出作者可以怎么补救。不要客套。",
      audit: "请检查工作台数据的准确性与一致性：内部矛盾（状态与时间线冲突）、过期未动、事实错误（DOI/期刊名/会议日期/失效链接）、引用真伪、缺失字段、重复记录。只提议不擅自修改，按严重程度分级列出。",
    }[b.dataset.kind] || "";
    ta.value = head + "\n\n---\n" + ctx.text + (opts.body ? "\n" + opts.body : "");
    ta.dataset.kind = b.dataset.kind;
    ta.dataset.weight = k ? k.weight : "medium";
    upd();
  });
  if (opts.kind) { const b = $(`#kindPills button[data-kind="${opts.kind}"]`); if (b) b.classList.add("on"); }

  $("#aiInbox").onclick = async () => {
    const text = `\n## ${todayStr()} · ${ctx.title || "工作台"}${ta.dataset.kind ? " · " + KIND_T[ta.dataset.kind] : ""}\n` +
      `> 来源：${ref || "-"}\n\n${ta.value}\n`;
    await API.post("claude/inbox", { text, mode: "append" });
    S.inbox += text;
    UI.closeModal(); toast("已写进信箱 · 去 Cowork 说「处理工作台信箱」");
  };
  const jump = which => {
    const t = AI_TARGETS.find(x => x.v === which);
    window.open(t.url(ta.value), "_blank");
    saveConfig({ ai: Object.assign({}, S.config.ai, { default_jump: which }) });
  };
  $("#aiClaude").onclick = () => jump("claude");
  $("#aiGpt").onclick = () => jump("chatgpt");
  $("#aiCopy").onclick = async () => {
    try { await navigator.clipboard.writeText(ta.value); } catch (e) {
      const x = document.createElement("textarea"); x.value = ta.value;
      document.body.appendChild(x); x.select(); document.execCommand("copy"); x.remove();
    }
    toast("已复制");
  };
  $("#aiSaveQ").onclick = async () => {
    await saveRec("reports", {
      title: (KIND_T[ta.dataset.kind] || "提问") + " · " + (ctx.title || todayStr()),
      kind: ta.dataset.kind || "ask", source: def, ref: ref || "", date: todayStr(),
      status: "waiting", body: "## 问题\n\n" + ta.value + "\n\n## 回答\n\n（把 AI 的回答粘贴到这里）\n",
    });
    UI.closeModal(); toast("已存入报告库，回答粘回去即可归档"); go("ai");
  };
  if (def === "chatgpt") $("#aiGpt").classList.add("primary");
}

window.schema_reports = () => [
  { k: "title", label: "标题", type: "text", wide: true },
  { k: "kind", label: "类型", type: "select", opts: TASK_KINDS.map(k => ({ v: k.v, t: k.t })) },
  { k: "source", label: "来源", type: "select", opts: [{ v: "claude", t: "Claude" }, { v: "chatgpt", t: "ChatGPT" }, { v: "auto", t: "自动任务" }] },
  { k: "date", label: "日期", type: "date" },
  { k: "status", label: "状态", type: "select", opts: [{ v: "waiting", t: "待回答" }, { v: "unread", t: "未读" }, { v: "read", t: "已读" }, { v: "adopted", t: "已采纳" }, { v: "rejected", t: "已否决" }] },
  { k: "ref", label: "关联记录", type: "text" },
];

/* ------------------------------------------------------------ 额度面板 */
function quotaPanel() {
  const q = S.quota || {};
  const rate = q.rate_per_week || 1;
  const you = 0; // 交互用量无法直接读取，见教程说明
  const autoPct = Math.min(100, (q.spent || 0) / rate * 100);
  const bufPct = Math.min(100 - autoPct, (q.buffer || 0) / rate * 100);
  const targetPct = Math.min(100, (q.target_spent || 0) / rate * 100);
  const runs = q.runs_this_week || [];
  const pace = { behind: ["落后（在浪费额度）", "var(--amber)"], ahead: ["超前（该收敛）", "var(--violet)"], "on-track": ["节奏正常", "var(--green)"] }[q.pace] || ["—", "var(--muted)"];

  return `
  <div class="grid g4" style="margin-bottom:12px">
    <div class="stat"><div class="k">本周自动配额</div><div class="v">${q.rate_per_week ?? "—"}</div><div class="d">成本点数（自适应）</div></div>
    <div class="stat"><div class="k">已用</div><div class="v">${q.spent ?? 0}</div><div class="d">目标进度 ${q.target_spent ?? 0}</div></div>
    <div class="stat"><div class="k">现在可用</div><div class="v">${q.available ?? 0}</div><div class="d">已扣安全余量 ${q.buffer ?? 0}</div></div>
    <div class="stat"><div class="k">距重置</div><div class="v">${Math.round((q.hours_to_reset || 0) / 24 * 10) / 10}<span style="font-size:13px"> 天</span></div>
      <div class="d" style="color:${pace[1]}">${pace[0]}</div></div>
  </div>
  <div class="qbar">
    <div class="seg-auto" style="width:${autoPct}%"></div>
    <div class="seg-buf" style="width:${bufPct}%"></div>
    <div class="marker" style="left:${targetPct}%" title="本周目标进度"></div>
  </div>
  <div class="qlegend">
    <span><i style="background:var(--violet)"></i>自动任务已用</span>
    <span><i class="seg-buf" style="background:var(--line)"></i>安全余量（留给你）</span>
    <span><i style="background:var(--line-2)"></i>可用</span>
    <span>▎标记 = 目标进度线</span>
  </div>
  <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:12px">
    <button class="btn ${q.overrides && q.overrides.tonight_boost ? "primary" : ""}" data-qover="tonight_boost">🌙 今晚放开跑</button>
    <button class="btn ${q.overrides && q.overrides.silent_week ? "primary" : ""}" data-qover="silent_week">🤫 本周静默</button>
    <button class="btn danger" id="qBlocked">🚧 我被挡住了</button>
    <span class="spacer"></span>
    <button class="btn ghost" id="qRefresh">刷新</button>
  </div>
  <div class="hr"></div>
  <div class="grid g2">
    <div>
      <div class="tiny muted">本周自动运行 ${runs.length} 次</div>
      ${runs.length ? runs.slice(-8).reverse().map(r => `<div class="row-line"><div class="rl-main">
          <div class="rl-title small">${esc(KIND_T[r.kind] || r.kind)} <span class="badge">${r.cost}</span></div>
          <div class="rl-meta">${esc(String(r.ts).slice(0, 16).replace("T", " "))}${r.note ? " · " + esc(r.note) : ""}</div>
        </div></div>`).join("") : `<div class="empty">本周还没有自动任务运行</div>`}
    </div>
    <div>
      <div class="tiny muted">每周结算（加性增长 / 乘性回退）</div>
      ${(q.history || []).length ? `<table class="tbl"><tr><th>周</th><th>配额</th><th>用掉</th><th>结论</th><th>下周</th></tr>
        ${q.history.slice().reverse().map(h => `<tr><td>${esc(h.week)}</td><td>${h.rate}</td><td>${h.spent}</td>
          <td>${{ "blocked-halve": "挡住过 → 减半", "surplus-grow": "有盈余 → +20%", "well-tuned": "刚好" }[h.verdict] || h.verdict}</td>
          <td><b>${h.new_rate}</b></td></tr>`).join("")}</table>`
      : `<div class="empty">还没有跨周记录 · 运行几周后它会自己收敛到你的真实余量</div>`}
    </div>
  </div>`;
}

VIEWS.ai = () => {
  const reps = rows("reports").slice().sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  const unread = reps.filter(r => r.status === "unread" || r.status === "waiting");

  const tut = UI.tut("ai", "AI 双通道 + 额度调度器怎么用", `
    <p><b>两条通道，都走你的订阅，不花 API 钱：</b></p>
    <p>① <b>Claude 信箱</b>——重活。任何地方点 🤖 写进信箱，然后在 Cowork 里说一句「处理工作台信箱」，Claude 会读你的数据文件、干活、把结果写回来（能直接改文件，这是网页聊天做不到的）。</p>
    <p>② <b>预填跳转</b>——即时小问题。同一个面板里点「↗ Claude 网页」或「↗ ChatGPT」，问题已经拼好，回车即问。默认跳哪家可以在设置里改，你点哪个它就记住哪个。唯一代价：答案不会自动回到工作台，想留档就点「存为报告」再把回答粘回去。</p>
    <p><b>额度调度器</b>解决的是：订阅额度用不完也不滚存，睡觉时就白白蒸发了；但如果无脑跑满，你周四要用时会被锁。<br>
    所以它用<b>加性增长/乘性回退</b>自我校准（上周没挡住你且有盈余 → 配额 +20%；挡住过 → 立刻减半），用<b>你的活跃画像</b>决定在哪些时段跑（你越不可能用，它越多跑），用<b>随剩余时间平方根衰减的安全余量</b>决定敢花多少（周一保守、周日大胆），并且按<b>价值/成本 + 有效期</b>挑任务。重置前还有盈余就跑「全库体检」这类扫尾任务，所以余量不会浪费。</p>
    <p>你手上有三个开关：明天不用 Claude 就点<b>今晚放开跑</b>；要冲刺赶稿就点<b>本周静默</b>；真被限流了点<b>我被挡住了</b>（它会立刻减半并停掉当天任务）。</p>
    <p class="muted">注：交互用量目前无法被程序直接读取，所以调度器按「运行次数 × 成本档位」自己记账，再用你的反馈校准——这就是上面那两个开关和结算表存在的意义。</p>`);

  const inboxCard = UI.card("ai-inbox", "Claude 信箱", "inbox.md", `
    <div class="small muted" style="margin-bottom:6px">在 Cowork 会话里说「处理工作台信箱」，Claude 会读这里并把结果写回 outbox。</div>
    <textarea id="inboxText" style="width:100%;min-height:140px;border:1px solid var(--line);border-radius:8px;padding:9px;font-family:ui-monospace,monospace;font-size:12.5px">${esc(S.inbox || "")}</textarea>
    <div style="display:flex;gap:7px;margin-top:8px">
      <button class="btn primary" id="inboxSave">保存信箱</button>
      <button class="btn" id="inboxClear">清空</button>
      <span class="spacer"></span>
      <button class="btn" data-ai="">🤖 新建请求</button>
    </div>`, { icon: "📥" });

  const outboxCard = UI.card("ai-outbox", "Claude 回信 / 体检报告", "outbox", `
    ${(S.outbox || []).length || (S.audits || []).length ? `
      ${(S.outbox || []).map(n => `<div class="row-line"><div class="rl-main"><div class="rl-title small">📄 ${esc(n)}</div></div>
        <div class="rl-acts"><button class="btn sm" data-outbox="${esc(n)}">查看</button></div></div>`).join("")}
      ${(S.audits || []).map(n => `<div class="row-line"><div class="rl-main"><div class="rl-title small">🩺 ${esc(n)}</div></div>
        <div class="rl-acts"><button class="btn sm" data-outbox="${esc(n)}">查看</button></div></div>`).join("")}`
      : `<div class="empty">还没有回信。自动任务或「处理工作台信箱」跑完后，结果会出现在这里。</div>`}`, { icon: "📤" });

  const repCard = UI.card("ai-reports", "AI 报告库", `${reps.length} 份`, reps.length ? reps.map(r => `
    <div class="row-line"><div class="rl-main">
      <div class="rl-title">${r.source === "chatgpt" ? "🟢" : r.source === "auto" ? "🤖" : "🟣"} ${esc(r.title || "")}
        <span class="badge ${r.status === "adopted" ? "g" : r.status === "rejected" ? "r" : r.status === "waiting" ? "a" : ""}">${esc(r.status || "")}</span></div>
      <div class="rl-meta">${esc(r.date || "")} · ${esc(KIND_T[r.kind] || r.kind || "")}${r.ref ? " · " + esc(r.ref) : ""}</div>
    </div><div class="rl-acts">
      <button class="btn sm" data-report="${r.id}">打开</button>
      <button class="btn sm" data-edit="reports:${r.id}">编辑</button>
    </div></div>`).join("") : `<div class="empty">还没有报告。在任何记录上点 🤖 → 「存为报告」即可归档。</div>`, { icon: "📊" });

  const tasksCard = UI.card("ai-tasks", "手动跑一次", "算法 + Claude 协作", `
    <div class="small muted" style="margin-bottom:9px">这些平时由额度调度器在你睡觉时自动跑。想现在就要结果，点这里。
      带「算法」标记的完全不花额度。</div>
    <div style="display:flex;gap:7px;flex-wrap:wrap">
      <button class="btn" data-run="audit">🩺 全库体检 <span class="badge g">算法</span></button>
      <button class="btn" data-run="journal">🗓 生成本周开局 <span class="badge g">算法</span></button>
      <button class="btn" data-run="radar">🛰 GitHub / 文献雷达 <span class="badge g">算法</span></button>
      <button class="btn" data-run="journal-push">📲 生成并推送到钉钉</button>
    </div>
    <div id="runOut" class="run-out"></div>
    <div class="hr"></div>
    <div class="small muted">体检查出的「引用真伪」「语义重复」需要理解力，算法做不了——
      跑完后点 🤖 把结果写进 Claude 信箱，说一句「按 workspace-audit 技能补完体检」即可。</div>`,
    { icon: "▶️" });

  return `<div class="page-head"><h1>🤖 AI 与额度</h1><div class="sub">Claude 信箱 · ChatGPT/Claude 跳转 · 额度调度器</div>
    <span class="spacer"></span>${unread.length ? `<span class="badge a">${unread.length} 份待处理</span>` : ""}
    <button class="btn primary" data-ai="">🤖 问 AI</button></div>
    ${tut}
    ${UI.card("ai-quota", "额度调度器", "Quota controller", quotaPanel(), { icon: "⚡" })}
    ${tasksCard}${inboxCard}${outboxCard}${repCard}`;
};

window.bindAiExtras = function () {
  $$("[data-run]").forEach(b => b.onclick = async () => {
    const key = b.dataset.run;
    const name = key === "journal-push" ? "journal" : key;
    const out = $("#runOut");
    out.innerHTML = `<div class="run-line">运行中…（首次可能要十几秒）</div>`;
    b.disabled = true;
    try {
      const r = await API.post("run/" + name, key === "journal-push" ? { push: true } : {});
      b.disabled = false;
      if (!r.ok) { out.innerHTML = `<div class="run-line bad">失败：${esc(r.detail || r.err || "")}</div>`; return; }
      const d = r.data || {};
      if (name === "audit") {
        const by = d.by_level || {};
        out.innerHTML = `<div class="run-line ok">体检完成：共 <b>${d.count || 0}</b> 条
            （高 ${by["高"] || 0} · 中 ${by["中"] || 0} · 低 ${by["低"] || 0}）</div>` +
          (d.items || []).slice(0, 12).map(i => `<div class="au-item lv-${esc(i.level)}">
            <span class="badge ${i.level === "高" ? "r" : i.level === "中" ? "a" : ""}">${esc(i.level)}</span>
            <b>${esc(i.kind)}</b> ${esc(i.what)}
            ${i.fix ? `<div class="tiny muted">建议：${esc(i.fix)}</div>` : ""}
            <button class="lnk" data-ignore="${esc(i.key || "")}">忽略</button></div>`).join("") +
          ((d.count || 0) > 12 ? `<div class="tiny muted">还有 ${d.count - 12} 条，完整报告在 outbox</div>` : "");
        $$("[data-ignore]").forEach(x => x.onclick = async () => {
          await API.post("audit/ignore", { key: x.dataset.ignore });
          x.closest(".au-item").style.opacity = ".35"; x.remove(); toast("以后不再报这条");
        });
      } else if (name === "journal") {
        out.innerHTML = `<div class="run-line ok">已生成 <b>${esc(d.week || "")}</b> 的周报与手帐
            ${d.push ? (d.push.ok ? "· 已推送 ✓" : "· 推送失败：" + esc((d.push.results || [{}])[0].detail || "")) : ""}</div>
          <div class="tiny muted">周报进了「AI 报告库」；手帐在 local/journal/ 下，可直接打开或打印。</div>
          <div style="margin-top:7px"><button class="btn sm" id="openJournal">打开手帐</button></div>`;
        const oj = $("#openJournal");
        if (oj) oj.onclick = () => window.open("/api/file?path=" + encodeURIComponent(d.journal), "_blank");
        const boot = await API.bootstrap(); S.data = boot.data; renderNav();
      } else if (name === "radar") {
        out.innerHTML = `<div class="run-line ${d.ok ? "ok" : "bad"}">
          抓到 <b>${d.repos || 0}</b> 个仓库、<b>${d.papers || 0}</b> 篇论文
          ${(d.errors || []).length ? `<div class="tiny">${esc(JSON.stringify(d.errors).slice(0, 160))}</div>` : ""}</div>
          <div class="tiny muted">候选已存入 radar-raw.json。让 Claude 按 github-radar 技能筛选排序即可。</div>`;
      } else {
        out.innerHTML = `<div class="run-line ok">${esc(JSON.stringify(d).slice(0, 400))}</div>`;
      }
    } catch (e) { b.disabled = false; out.innerHTML = `<div class="run-line bad">${esc(e.message)}</div>`; }
  });
  $$("[data-ai]").forEach(b => b.onclick = e => { e.stopPropagation(); openAiDialog(b.dataset.ai); });
  $$("[data-qover]").forEach(b => b.onclick = async () => {
    const key = b.dataset.qover;
    const cur = (S.quota.overrides || {})[key];
    const patch = {}; patch[key] = !cur;
    S.quota = await API.post("quota/override", patch);
    render(); toast(patch[key] ? "已开启" : "已关闭");
  });
  const qb = $("#qBlocked");
  if (qb) qb.onclick = async () => {
    if (!confirm("确认你刚刚被 Claude 限流挡住了？配额会立刻减半，并暂停今天的自动任务。")) return;
    S.quota = await API.post("quota/blocked", {});
    render(); toast("已记录，配额已减半");
  };
  const qr = $("#qRefresh");
  if (qr) qr.onclick = async () => { S.quota = await API.get("quota"); render(); toast("已刷新"); };
  const ibs = $("#inboxSave");
  if (ibs) ibs.onclick = async () => {
    await API.post("claude/inbox", { text: $("#inboxText").value, mode: "replace" });
    S.inbox = $("#inboxText").value; toast("已保存");
  };
  const ibc = $("#inboxClear");
  if (ibc) ibc.onclick = async () => {
    if (!confirm("清空信箱？")) return;
    await API.post("claude/inbox", { text: "", mode: "replace" });
    S.inbox = ""; render(); toast("已清空");
  };
  $$("[data-outbox]").forEach(b => b.onclick = async () => {
    const r = await API.get("claude/outbox?name=" + encodeURIComponent(b.dataset.outbox));
    UI.modal(b.dataset.outbox, `<pre style="white-space:pre-wrap;font-size:13px;line-height:1.65">${esc(r.text || "（空）")}</pre>`,
      `<button class="btn" id="markRead">标记已读</button><span class="spacer"></span><button class="btn" data-close>关闭</button>`);
    $("#markRead").onclick = async () => { await API.post("quota/read-report", {}); UI.closeModal(); toast("已标记"); };
  });
  $$("[data-report]").forEach(b => b.onclick = () => {
    const r = byId("reports", b.dataset.report);
    UI.modal(r.title || "报告", `
      <textarea id="repBody" style="width:100%;min-height:340px;border:1px solid var(--line);border-radius:8px;padding:10px;font-size:13px;line-height:1.6">${esc(r.body || "")}</textarea>`,
      `<button class="btn primary" id="repSave">保存</button>
       <button class="btn" id="repAdopt">✓ 采纳</button>
       <button class="btn" id="repReject">✕ 否决</button>
       <span class="spacer"></span><button class="btn" data-close>关闭</button>`);
    const upd = async status => {
      await patchRec("reports", r.id, { body: $("#repBody").value, status });
      UI.closeModal(); render(); toast("已保存");
    };
    $("#repSave").onclick = () => upd(r.status === "waiting" ? "read" : r.status);
    $("#repAdopt").onclick = () => upd("adopted");
    $("#repReject").onclick = () => upd("rejected");
  });
};
