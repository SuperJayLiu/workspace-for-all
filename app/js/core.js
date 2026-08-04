/* 学术工作台 · 核心：状态、API、工具、路由 */
const S = {            // 全局状态
  data: {}, dataMeta: {}, config: {}, device: {}, git: {}, quota: {},
  inbox: "", outbox: [], audits: [], version: "", root: "",
  route: "today", ready: false,
};

/* 把服务器返回的错误正文变成人能看懂的一句话 */
async function apiError(r) {
  let msg = "";
  try {
    const t = await r.text();
    try { msg = (JSON.parse(t) || {}).error || ""; } catch (e) { msg = t; }
  } catch (e) { }
  return new Error(String(msg || "").slice(0, 200) || `请求失败 (HTTP ${r.status})`);
}

const API = {
  async get(path) {
    const r = await fetch("/api/" + path);
    if (!r.ok) throw await apiError(r);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch("/api/" + path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (r.status === 409) { const e = new Error("conflict"); e.conflict = await r.json(); throw e; }
    if (!r.ok) throw await apiError(r);
    return r.json();
  },
  async del(path) {
    const r = await fetch("/api/" + path, { method: "DELETE" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `删除失败 (HTTP ${r.status})`);
    return j;
  },
  /* 首屏数据是**裁过**的（近半年的生活流水、截断的长正文）。
     服务端会连带告诉我们裁了多少（dataMeta）。这里统一记进 S ——
     否则界面会拿残缺数据当全量去算「合计」，算出个偏小的数字还照样叫合计。
     以前有 7 处各写各的 `S.data = b.data`，只要漏一处就退回到「假装全量」，
     所以在这一层收口，而不是指望每个调用点记得。 */
  async bootstrap() {
    const b = await this.get("bootstrap");
    S.dataMeta = b.dataMeta || {};
    return b;
  },
  save(coll, rec) { return this.post("records/" + coll, rec); },
  remove(coll, id) { return this.del("records/" + coll + "/" + id); },
};

/* ------------------------------------------------------------ utilities */
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const uid = () => "x" + Math.random().toString(36).slice(2, 9);

function todayStr(d) {
  d = d || new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
    "-" + String(d.getDate()).padStart(2, "0");
}
function parseDate(s) {
  if (!s) return null;
  const d = new Date(String(s).slice(0, 10) + "T00:00:00");
  return isNaN(d) ? null : d;
}
function daysUntil(s, yearly) {
  const d = parseDate(s); if (!d) return null;
  const now = new Date(); now.setHours(0, 0, 0, 0);
  if (yearly) { d.setFullYear(now.getFullYear()); if (d < now) d.setFullYear(now.getFullYear() + 1); }
  return Math.round((d - now) / 86400000);
}
function daysBetween(a, b) {
  const x = parseDate(a), y = parseDate(b);
  if (!x || !y) return null;
  return Math.round((y - x) / 86400000);
}
function daysChip(n) {
  if (n == null) return "";
  const txt = n < 0 ? `逾期 ${-n} 天` : n === 0 ? "今天" : n === 1 ? "明天" : `${n} 天后`;
  const col = n < 0 ? "var(--red)" : n <= 3 ? "var(--red)" : n <= 14 ? "var(--amber)" : "var(--green)";
  return `<span class="chip-days" style="color:${col}">${txt}</span>`;
}
function fmtDate(s) { return s ? String(s).slice(0, 10) : ""; }
function timeZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return "?"; }
}
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 1900);
}
function debounce(fn, ms) { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; }

/* ------------------------------------------------------------ 示例数据
   种子里的示例记录是给你看结构用的，用熟了就该消失。
   过滤放在 rows() 这一层，一开关全站生效，不用每个页面各改一遍。 */
function isSample(r) {
  return !!r && (r.sample === true ||
    /^[（(]示例[）)]/.test(String(r.title || "")) ||
    /^[（(]示例[）)]/.test(String(r.name || "")));
}
function rowsAll(coll) { return S.data[coll] || []; }
function sampleCount(colls) {
  return [].concat(colls).reduce((n, c) => n + rowsAll(c).filter(isSample).length, 0);
}
/* 内存里这个集合是不是被首屏裁过（生活流水只带近期那一段）。
   凡是要给出「一共有多少条」「全部处理一遍」这类承诺的地方都得先问一句，
   否则会拿一段残缺数据当全量：说「彻底删掉这 9 条」，磁盘上其实有 14 条。 */
function isPartial(coll) { return !!((S.dataMeta || {})[coll] || {}).partial; }
/* 把裁过的集合补全到内存里。要「全量遍历」之前先调它。 */
async function loadAll(colls) {
  for (const c of [].concat(colls)) {
    if (!isPartial(c)) continue;
    const all = await API.get(`records/${encodeURIComponent(c)}`);
    S.data[c] = all;
    (S.dataMeta || (S.dataMeta = {}))[c] = { total: all.length };
  }
}
/* 卡片右上角那个「隐藏示例」小按钮：只有这张卡确实含示例时才出现 */
function sampleBtn(colls) {
  if (S.config.hide_samples) return "";
  const n = sampleCount(colls);
  return n ? `<button class="btn sm ghost hide-sample" data-hidesample="1"
    title="把种子里的示例记录藏起来（不会删除，设置里随时能恢复）">🙈 隐藏示例 ${n}</button>` : "";
}

/* 集合读写的便捷封装（本地状态 + 服务器） */
function rows(coll) {
  const a = S.data[coll] || [];
  return S.config.hide_samples ? a.filter(r => !isSample(r)) : a;
}
/* byId 走 rowsAll：关联、跳转这些要的是「这条在不在」，不该被「隐藏示例」影响 */
function byId(coll, id) { return (S.data[coll] || []).find(r => r.id === id); }

/* 从服务器重新拉一遍数据（关联、批量操作这类会改到别的库的动作之后要用） */
async function reload() {
  const b = await API.bootstrap();
  S.data = b.data;
  if (b.config) S.config = b.config;
  return b;
}
/* 把某条记录的**完整**内容取回内存。
 *
 * 首屏为了体积会截断长正文（带 _body_more 标记）。任何「基于内存那份再存回去」
 * 的动作，如果不先取全量，就会把正文写成截断后的样子——**而且不报错**。
 * 这类动作远不止编辑器：拖便利贴、勾完成、拖甘特条、记一次复习……
 * 全都会顺手把那条记录整份写回去。
 */
async function ensureFull(coll, id) {
  const cur = byId(coll, id);
  if (cur && !cur._body_more) return cur;
  const fresh = await API.get(`records/${encodeURIComponent(coll)}/${encodeURIComponent(id)}`);
  const arr = S.data[coll] = S.data[coll] || [];
  const i = arr.findIndex(r => r.id === id);
  if (i >= 0) arr[i] = fresh; else arr.push(fresh);
  return fresh;
}

async function saveRec(coll, rec) {
  let saved;
  /* 最后一道网：真要存了还带着 _body_more，说明上游漏了取全量。
     这时候宁可不写 body（服务端保留磁盘上那份），也不能把截断的存进去。 */
  if (rec && rec._body_more) {
    try {
      const fresh = await API.get(`records/${encodeURIComponent(coll)}/${encodeURIComponent(rec.id)}`);
      rec = Object.assign({}, rec, { body: fresh.body, _body_more: undefined });
    } catch (e) {
      rec = Object.assign({}, rec);
      delete rec.body;                 // 取不到就干脆不动 body
      delete rec._body_more;
      console.warn("取不到完整正文，本次保存不修改正文", coll, rec.id);
    }
  }
  try {
    saved = await API.save(coll, rec);
  } catch (e) {
    if (e.conflict) { return resolveConflict(coll, e.conflict); }
    throw e;
  }
  const arr = S.data[coll] = S.data[coll] || [];
  const i = arr.findIndex(r => r.id === saved.id);
  if (i >= 0) arr[i] = saved; else arr.push(saved);
  return saved;
}
async function deleteRec(coll, id) {
  await API.remove(coll, id);            // 失败会抛，由全局兜底提示，不会假装删掉
  /* 这里必须用 S.data 而不是 rows()：rows() 已经按「隐藏示例」过滤过，
     把它的结果写回去，等于顺手把所有示例记录从内存里一起抹掉 ——
     磁盘上还在，界面上却消失了：设置页会显示「彻底删掉这 0 条」，
     点了没反应；「重新显示示例」也变不回来，非得刷新页面。 */
  const arr = S.data[coll] || [];
  S.data[coll] = arr.filter(r => r.id !== id);
}
/* 局部修改一条记录。
 *
 * patch 可以是一个对象，也可以是 `fresh => ({...})` 这样的函数。
 * **往数组里追加东西时一定要用函数形式**（时间线、复习记录这些）：
 * 对象形式的 patch 是在调用方那边、用内存里可能已经过时的数组算出来的，
 * 而函数形式拿到的是刚从服务端取回来的那份。
 */
async function patchRec(coll, id, patch) {
  let cur = byId(coll, id); if (!cur) return;
  /* 冲突检测靠的是「我这份是基于哪个时间点的」。ensureFull 会把 _mtime 刷新成
     此刻的值，于是服务端永远看不出「这中间别人改过」—— 检测形同虚设。
     所以先把原始的 _mtime 记下来，合并完再放回去：
     内容用新取回来的（不会写回截断正文），基准时间仍是我看到的那一版。 */
  /* 但也不能一律拿旧时间戳去卡：那样连「明明是基于新数据算出来的」也会弹冲突框。
     分界线就是 patch 的形式 ——
       · 函数形式 patch(fresh)：值是用**刚取回来的那份**算的，
         调用方已经把别人的改动接进去了，放行；
       · 对象形式 {a: 1}：值是调用方在别处、拿内存里那份算好的，
         内存可能已经过时，必须让服务端比一比。 */
  const computedFromFresh = typeof patch === "function";
  const baseMtime = cur._mtime;
  if (cur._body_more && !(!computedFromFresh && "body" in (patch || {}))) {
    try { cur = await ensureFull(coll, id); } catch (e) { /* 交给 saveRec 那道网 */ }
  }
  const p = computedFromFresh ? (patch(cur) || {}) : patch;
  const merged = Object.assign({}, cur, p);
  if (!computedFromFresh && baseMtime !== undefined) merged._mtime = baseMtime;
  return saveRec(coll, merged);
}
/* 配置写入必须排队。以前每次点击都发一整份 config，
   多个请求到达顺序不定，后到的旧快照会把新改动盖掉（静默回滚）。 */
let _cfgChain = Promise.resolve();
async function saveConfig(patch) {
  S.config = Object.assign({}, S.config, patch || {});
  const snapshot = S.config;
  _cfgChain = _cfgChain.then(() => API.post("config", snapshot)).catch(e => {
    toast("设置没保存上：" + String(e.message || e).slice(0, 60));
  });
  return _cfgChain;
}
async function saveDevice(patch) {
  S.device = Object.assign({}, S.device, patch || {});
  await API.post("device", S.device);
}

/* ------------------------------------------------------------- sections */
const SECTIONS = [
  { id: "today", icon: "🏠", name: "今日", en: "Today" },
  { id: "hub", icon: "📊", name: "研究", en: "Research" },
  { id: "papers", icon: "🏆", name: "论文库", en: "Papers", coll: "published" },
  { id: "conferences", icon: "🎤", name: "学术会议", en: "Conferences", coll: "conferences" },
  { id: "reading", icon: "📚", name: "读文献", en: "Reading", coll: "reading" },
  { id: "ideas", icon: "💡", name: "想法", en: "Ideas", coll: "ideas" },
  { id: "schedule", icon: "📅", name: "日程", en: "Schedule", coll: "schedule" },
  { id: "life", icon: "🌱", name: "生活", en: "Life" },
  { id: "ai", icon: "🤖", name: "AI 与额度", en: "AI", coll: "reports" },
  { id: "settings", icon: "⚙️", name: "设置与教程", en: "Settings" },
];

const VIEWS = {};   // 由各模块注册：VIEWS.today = () => html

function visibleSections() {
  const allowed = new Set((S.config.sections || SECTIONS.map(s => s.id)).concat(["today", "settings"]));
  return SECTIONS.filter(s => allowed.has(s.id));
}

function renderNav() {
  const counts = {
    hub: rows("manuscripts").filter(m => !["published", "shelved"].includes(m.stage)).length,
    papers: rows("published").length,
    conferences: rows("conferences").length,
    reading: rows("reading").filter(r => r.status !== "done").length,
    ideas: rows("ideas").length,
    schedule: rows("schedule").length,
    ai: (S.quota.unread_reports || 0) + (S.outbox || []).length,
  };
  $("#nav").innerHTML = visibleSections().map(s => {
    const n = counts[s.id];
    return `<button class="${s.id === S.route ? "active" : ""}" data-go="${s.id}">
      <span class="nav-ico">${s.icon}</span><span>${s.name}</span>
      ${n ? `<span class="nav-count">${n}</span>` : ""}</button>`;
  }).join("");
  /* 自己绑一次。以前只靠 render() 里的 UI.afterRender()，
     于是「先 render 后 renderNav」的调用顺序会让整个侧边栏失去点击响应 —— 全站有十几处这样调。 */
  $$("#nav [data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
}

function go(id) {
  S.route = id;
  /* 专属页要把 id 带进地址栏，否则一刷新就变成「找不到这个项目」 */
  location.hash = (id === "project" && S.projectId)
    ? "project/" + encodeURIComponent(S.projectId) : id;
  renderNav();
  render();
  $("#sidebar").classList.remove("open");
  window.scrollTo(0, 0);
}

function render() {
  const fn = VIEWS[S.route] || VIEWS.today;
  try {
    $("#view").innerHTML = fn();
  } catch (e) {
    $("#view").innerHTML = `<div class="card"><div class="card-body"><b>这一页出错了</b>
      <pre class="small" style="white-space:pre-wrap;color:var(--red)">${esc(e.stack || e.message)}</pre></div></div>`;
    console.error(e);
  }
  UI.afterRender();
  if (typeof EDIT !== "undefined") { EDIT.apply(); if (EDIT.on) EDIT.decorate(); }
}


/* 两台设备同时改了同一条记录时，让你选，绝不静默覆盖 */
async function resolveConflict(coll, c) {   // c 可能在解决过程中被更新的冲突替换
  const fmt = r => Object.entries(r)
    .filter(([k]) => !["id", "_collection", "_mtime", "created", "updated"].includes(k))
    .map(([k, v]) => `<div class="cf-row"><b>${esc(k)}</b><span>${esc(
      Array.isArray(v) ? JSON.stringify(v) : String(v == null ? "" : v)).slice(0, 300)}</span></div>`).join("");
  return new Promise(resolve => {
    UI.modal("⚠️ 这条记录在别处被改过", `
      <div class="small muted" style="margin-bottom:9px">
        另一台设备（或 Claude 的自动任务）在你编辑期间改动了这条记录。
        为了不弄丢任何一方的内容，请你选一份保留——另一份会作为备注附在正文末尾，不会消失。</div>
      <div class="grid g2">
        <div class="cf-col"><div class="cf-h">你现在这份</div>${fmt(c.mine)}</div>
        <div class="cf-col theirs"><div class="cf-h">对方那份（较新）</div>${fmt(c.theirs)}</div>
      </div>`,
      `<button class="btn primary" id="cfMine">保留我的</button>
       <button class="btn" id="cfTheirs">保留对方的</button>
       <button class="btn" id="cfMerge">两份都留（对方的附到正文）</button>
       <span class="spacer"></span><button class="btn ghost" data-close>取消</button>`);
    let busy = false;
    const finish = async rec => {
      if (busy) return;
      busy = true;
      try {
        rec._mtime = c.theirs._mtime;
        const saved = await API.save(coll, rec);
        const arr = S.data[coll] = S.data[coll] || [];
        const i = arr.findIndex(r => r.id === saved.id);
        if (i >= 0) arr[i] = saved; else arr.push(saved);
        UI.closeModal(); render(); renderNav(); toast("冲突已解决");
        resolve(saved);
      } catch (err) {
        /* 看冲突对比要花一分钟，这一分钟里对方**可能又改了一次**。
           原来这里的 promise 被丢掉，第二次冲突变成 unhandledrejection，
           而全局兜底又专门忽略 conflict —— 于是点「保留我的」毫无反应，
           不报错、不关窗，用户再点几下就放弃了，改动就此丢掉。 */
        busy = false;
        const el = $("#modal");
        if (err && err.conflict) {
          c = err.conflict;
          if (el) {
            const w = document.createElement("div");
            w.className = "small";
            w.style.cssText = "color:var(--amber);margin:8px 0";
            w.textContent = "刚才那一分钟里对方又改了一次。上面是最新的对比，请重新选一次。";
            const body = el.querySelector(".modal-body");
            if (body) { body.prepend(w); }
          }
          // 用最新的对比重画
          UI.closeModal();
          resolve(await resolveConflict(coll, c));
          return;
        }
        toast("保存失败：" + ((err && err.message) || err));
      }
    };
    $("#cfMine").onclick = () => finish(Object.assign({}, c.mine));
    $("#cfTheirs").onclick = () => finish(Object.assign({}, c.theirs));
    // 取消也要把 promise 结掉，否则上游的 await 永远悬着，这次编辑无声无息地没了
    $$("[data-close]", $("#modal")).forEach(b => b.onclick = () => {
      UI.closeModal();
      toast("已取消 —— 这条没有保存，你的改动还在编辑器里没提交");
      resolve(null);
    });
    $("#cfMerge").onclick = () => {
      const merged = Object.assign({}, c.mine);
      /* mine 有可能根本没带 body（saveRec 取全量失败时会主动去掉它，
         好让服务端保留磁盘上那份）。这时候直接 (merged.body || "") 拼注解，
         结果就是 body 只剩一句注解 —— 把两边的正文一起冲掉了。
         以对方那份为底就不会。 */
      if (!("body" in merged)) merged.body = c.theirs.body || "";
      merged.body = (merged.body || "") +
        "\n\n---\n> 冲突合并 " + todayStr() + " · 另一台设备的版本：\n" +
        Object.entries(c.theirs).filter(([k]) => !["id", "_collection", "_mtime"].includes(k))
          .map(([k, v]) => `> ${k}: ${Array.isArray(v) ? JSON.stringify(v) : v}`).join("\n");
      finish(merged);
    };
  });
}
