/* 启动、路由、主题、搜索、快捷键、同步状态 */

/* 工作台叫什么由用户自己定；左上角那个 J 是固定的，不提供修改入口 */
function applyBrand() {
  const b = S.config.brand || {};
  const t = $("#brandTitle"), sub = $("#brandSub");
  if (t) t.textContent = b.title || "学术工作台";
  if (sub) sub.textContent = b.sub || "Scholar Workspace";
  document.title = (b.title || "学术工作台") + " · " + (b.sub || "Scholar Workspace");
}

function applyTheme() {
  const t = S.config.theme || {};
  document.documentElement.dataset.mode = t.mode || "light";
  document.documentElement.dataset.density = t.density || "comfortable";
  if (t.accent) {
    document.documentElement.style.setProperty("--accent", t.accent);
    document.documentElement.style.setProperty("--accent-soft",
      (t.mode === "dark" ? "color-mix(in srgb," + t.accent + " 26%, #14171d)"
        : "color-mix(in srgb," + t.accent + " 11%, #ffffff)"));
  }
}

function updateSyncChip() {
  const g = S.git || {};
  const dot = $("#syncDot"), txt = $("#syncText");
  if (g.last_error || S.pushError) {
    dot.className = "dot err";
    txt.textContent = "同步出错，点此查看";
    $("#syncChip").title = g.last_error || S.pushError;
  } else if (!g.repo) { dot.className = "dot"; txt.textContent = "本地模式（未接 Git）"; }
  else if (g.dirty) { dot.className = "dot warn"; txt.textContent = `待同步 ${g.dirty} 处`; }
  else { dot.className = "dot ok"; txt.textContent = "已同步"; }
  const c = S.clock || { in: "", out: "" };
  const working = c.in && !c.out;
  $("#deviceMeta").innerHTML =
    `<button class="clock-btn ${working ? "on" : ""}" id="clockBtn">
       ${working ? `🔥 正在做伟大的事 · ${esc(c.in)} 起`
         : (c.out ? `🌙 今天就先忙到这儿吧！${esc(c.out)}` : "✨ 开始做伟大的事吧！")}
     </button>
     <div>${esc(S.device.device_name || "")} · ${esc(timeZone())} · v${esc(S.version || "")}</div>`;
  const cb = $("#clockBtn");
  if (cb) cb.onclick = async () => {
    const r = await API.post("clock", { action: "toggle" });
    S.clock = r.today;
    updateSyncChip();
    toast(r.today.in && !r.today.out
      ? "开工 " + r.today.in + "　自动任务会避开你的工作时段"
      : "收工 " + r.today.out + (r.days >= 3 ? `　（据 ${r.days} 天记录，你的作息约 ${r.learned.start}–${r.learned.end}）` : ""));
  };
}

async function doSync() {
  toast("同步中…");
  const r = await API.post("git/sync", {});
  S.git = await API.get("git/status");
  updateSyncChip();
  if (r.ok) {
    const boot = await API.bootstrap();
    S.data = boot.data; S.config = boot.config; S.inbox = boot.inbox;
    S.outbox = boot.outbox; S.audits = boot.audits;
    render(); renderNav(); toast("同步完成");
  } else {
    const detail = (r.steps || []).map(s => s.step + ": " + (s.out || "")).join(" | ");
    toast("同步未完成 · " + (r.detail || detail).slice(0, 90));
  }
}

/* ------------------------------------------------------------- 搜索
   全局搜索走服务端（palette.js → /api/search）：那边扫的是磁盘，
   搜得到几万条文献索引，也搜得到首屏没带回来的旧记录。
   这里原先还留着一个前端版 searchAll()，已经没有任何地方调它了——
   而且它按内存里那份搜、还读被截断的正文，留着迟早被人当成「全库搜索」用。
   删掉比留着安全。 */
const COLL_SEARCH = ["manuscripts", "journals", "published", "conferences", "reading",
  "ideas", "levels", "schedule", "reports", "diet", "exercise", "dates", "lists", "admin", "finance"];
const COLL_LABEL = {
  manuscripts: "稿件", journals: "期刊", published: "已刊", conferences: "会议",
  reading: "文献", ideas: "想法", levels: "关卡", schedule: "日程", reports: "报告",
  diet: "饮食", exercise: "运动", dates: "日子", lists: "清单", admin: "事务", finance: "开支",
};
const COLL_VIEW = {
  manuscripts: "hub", journals: "journals", published: "papers",
  conferences: "conferences", reading: "reading", ideas: "ideas", levels: "reading",
  schedule: "schedule", reports: "ai", diet: "life", exercise: "life",
  dates: "life", lists: "life", admin: "life", finance: "life",
};

/* 兜底：任何没被接住的异步错误都要让用户看见，绝不静默丢数据 */
function bindErrorGuard() {
  const show = (msg) => {
    const m = String(msg || "");
    if (/conflict/i.test(m)) return;                       // 冲突有专门的界面
    const net = /Failed to fetch|NetworkError|load failed|ERR_/i.test(m);
    toast(net ? "保存失败：连不上本地服务，请确认 server.py 还在运行（你的输入还在页面上）"
              : "出错了：" + m.slice(0, 80));
  };
  window.addEventListener("unhandledrejection", e => {
    show(e.reason && (e.reason.message || e.reason));
    e.preventDefault();
  });
  window.addEventListener("error", e => {
    if (e.message) show(e.message);
  });
}

/* 远程只读时，顶栏放一把锁；点一下输访问码就能解锁 30 分钟 */
function updateLockChip() {
  const b = $("#unlockBtn");
  if (!b) return;
  const a = S.auth || { local: true, can_write: true };
  if (a.local !== false) { b.hidden = true; document.body.classList.remove("readonly"); return; }
  b.hidden = false;
  b.textContent = a.can_write ? "🔓 可编辑" : "🔒 只读";
  b.classList.toggle("on", !!a.can_write);
  document.body.classList.toggle("readonly", !a.can_write);
  b.onclick = () => {
    if (a.can_write) { toast("当前已可编辑，到时间会自动回到只读"); return; }
    UI.modal("解锁写入", `
      <div class="small muted" style="margin-bottom:9px">
        你正从别的设备访问这台电脑上的工作台。为了防止误改，远程默认只读。
        输一次访问码可以解锁 30 分钟。</div>
      <input id="unlockCode" type="password" placeholder="访问码" autofocus>
      <div class="small" id="unlockMsg" style="margin-top:8px;color:var(--red)"></div>`,
      `<button class="btn primary" id="unlockGo">解锁</button>
       <span class="spacer"></span><button class="btn ghost" data-close>取消</button>`);
    const go = async () => {
      const code = $("#unlockCode").value.trim();
      if (!code) return;
      try {
        await API.post("auth/unlock", { code });
        S.auth = Object.assign({}, S.auth, { can_write: true });
        UI.closeModal(); updateLockChip(); render();
        toast("已解锁写入，30 分钟后自动回到只读");
      } catch (e) {
        $("#unlockMsg").textContent = e.message || "访问码不对";
      }
    };
    $("#unlockGo").onclick = go;
    $("#unlockCode").addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  };
}

function bindGlobal() {
  bindErrorGuard();
  updateLockChip();
  $("#menuBtn").onclick = () => $("#sidebar").classList.toggle("open");
  $("#themeBtn").onclick = async () => {
    const mode = (S.config.theme || {}).mode === "dark" ? "light" : "dark";
    await saveConfig({ theme: Object.assign({}, S.config.theme, { mode }) });
    applyTheme();
  };
  $("#captureBtn").onclick = () => quickCapture();
  $("#claudeBtn").onclick = () => openAiDialog("");
  $("#editBtn").onclick = () => EDIT.toggle();
  $("#ebDone").onclick = () => EDIT.toggle(false);
  $("#ebReset").onclick = async () => {
    if (!confirm("恢复默认布局？（卡片顺序、隐藏状态、右栏宽度与比例都会重置）")) return;
    await saveConfig({ layout: { rail_split: 0.55, rail_collapsed: {}, card_order: {}, hidden_cards: [], rail_width: 326 } });
    document.documentElement.style.setProperty("--rail-w", "326px");
    EDIT.toggle(false); RAIL.render(); render(); toast("已恢复默认布局");
  };
  $("#calBtnTop").onclick = () => { RAIL.popover(); };
  RAIL.mount();
  DOCK.mount();
  QL.render();
  $("#syncChip").onclick = doSync;

  /* 搜索交给 palette.js：服务端搜全工作台（记录 + 文献索引 + 箴言 + 功能设置） */
  const si = $("#globalSearch");
  if (typeof PAL !== "undefined") PAL.mount();

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { UI.closeModal(); if (typeof PAL !== "undefined") PAL.close(); }
    const typing = /input|textarea|select/i.test((e.target.tagName || "")) || e.target.isContentEditable;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); si.focus(); return; }
    if (typing) return;
    if (e.key === "c") { e.preventDefault(); quickCapture(); }
    if (e.key === "n") { e.preventDefault(); DOCK.toggle(true); }
    if (e.key === "d") { e.preventDefault(); DOCK.tab = "done"; DOCK.toggle(true); DOCK.renderBox(); }
  });

  window.addEventListener("hashchange", () => {
    const raw = location.hash.replace("#", "");
    const [id, pid] = raw.split("/");
    /* 换项目也必须重画。
       原来只在 id 变了才 render()，于是「项目 A → 研究 → 项目 B → 后退」
       会出现：S.projectId 已经变回 A，页面还停在 B 上，
       而项目页那个自动保存的笔记框读的是 S.projectId ——
       你在看起来是 B 的框里打字，内容被写进了 A，A 原来的笔记被覆盖。 */
    const projChanged = id === "project" && pid
      && S.projectId !== decodeURIComponent(pid);
    if (id === "project" && pid) { S.projectId = decodeURIComponent(pid); }
    if (id && VIEWS[id] && (id !== S.route || projChanged)) {
      S.route = id; renderNav(); render();
    }
  });

  /* 每 5 分钟报一次活跃（喂给额度调度器的活跃画像） */
  setInterval(() => API.post("activity", {}).catch(() => { }), 5 * 60 * 1000);
  /* 每 3 分钟刷新一次 Git / 额度状态 */
  setInterval(async () => {
    try {
      S.git = await API.get("git/status");
      S.quota = await API.get("quota");
      updateSyncChip();
      if (S.git.last_error) toast("同步出错：" + String(S.git.last_error).slice(0, 60));
    } catch (e) { }
  }, 3 * 60 * 1000);
}

/* 天气 / 订阅日历 / 农历：后台刷新，失败静默（不影响主功能） */
async function refreshAmbient(force) {
  const jobs = [];
  if ((S.config.calendar || {}).weather !== false) {
    jobs.push(API.get("weather" + (force ? "?force=1" : "")).then(w => { S.weather = w; }).catch(() => { }));
  }
  if (((S.config.calendar || {}).ics || []).length) {
    jobs.push(API.get("calendar/events" + (force ? "?force=1" : ""))
      .then(r => { S.icsEvents = r.events || []; S.icsErrors = r.errors || []; }).catch(() => { }));
  }
  await Promise.all(jobs);
  if (typeof LUNAR !== "undefined") S.lunar = LUNAR.describe(new Date());
  if (S.route === "today" || S.route === "schedule") render();
  /* 右栏日历是启动时画的，那会儿 ICS 还没到 —— 数据到了必须重画一次，
     否则「今天」卡片有 Outlook 日程、右边日历却说「这天没有安排」 */
  if (typeof RAIL !== "undefined") RAIL.renderCalendar();
}

async function boot() {
  try {
    const b = await API.bootstrap();
    Object.assign(S, b);
    const raw = (location.hash.replace("#", "") || "today");
    const [rid, rpid] = raw.split("/");
    if (rid === "project" && rpid) S.projectId = decodeURIComponent(rpid);
    S.route = rid;
    if (!VIEWS[S.route]) S.route = "today";
    S.ready = true;
    applyTheme(); applyBrand();
    await QUOTE.load();
    renderNav(); render(); updateSyncChip(); bindGlobal();
    /* 日历与天气：后台取，取到再局部刷新，不阻塞首屏 */
    refreshAmbient();
    API.get("ai/status").then(r => { S.aiStatus = r; if (S.route === "settings") render(); }).catch(() => { });
    API.get("mail/status").then(r => { S.inboxCfg = r; }).catch(() => { });
    API.get("overleaf/status").then(r => { S.overleafStatus = r; if (S.route === "settings") render(); }).catch(() => { });
    /* OneDrive 目录到底存不存在，只有服务端知道 —— 顺手查一次，写错了要在设置页提醒 */
    if ((S.device || {}).onedrive_backup_dir && !/^https?:\/\//.test(S.device.onedrive_backup_dir)) {
      API.get("checkdir?path=" + encodeURIComponent(S.device.onedrive_backup_dir))
        .then(r => { S.odMissing = !r.ok; if (S.route === "settings") render(); }).catch(() => { });
    }
    /* 第一次使用 → 走向导 */
    if (!(S.config.setup || {}).done) {
      setTimeout(() => WZ.open((S.config.setup || {}).step || 0), 300);
    }
  } catch (e) {
    $("#view").innerHTML = `<div class="card"><div class="card-body">
      <h2>连不上本地服务</h2>
      <p class="small">请确认已经在工作台目录里运行 <code>python3 server.py</code>，然后刷新本页。</p>
      <pre class="small" style="color:var(--red);white-space:pre-wrap">${esc(e.message || e)}</pre>
    </div></div>`;
  }
}
boot();
