/* 全工作台搜索 · 顶栏那个搜索框
 *
 * 原来它只扫 bootstrap 里那份内存记录，搜不到 5 万条文献索引，
 * 也搜不到「备份在哪」「钉钉怎么配」这种功能类问题。
 * 现在全部交给服务端 /api/search，一次拿回四类结果：
 *   功能与设置 · 我的记录 · 文献索引 · 箴言
 *
 * 三条设计约束：
 *   1. 服务端搜、结果封顶。跟文献索引一个道理，前端不碰全量。
 *   2. 键盘要能一路走完：↑↓ 选、Enter 进、Esc 关。搜索框是给赶时间的人用的。
 *   3. 「功能」永远排在最前。找不到某个开关在哪，是比找记录更常见的困境。
 */

const PAL = {
  q: "", items: [], sel: 0, open: false, _timer: null, _seq: 0,

  el() { return { i: $("#globalSearch"), r: $("#searchResults") }; },

  mount() {
    const { i, r } = PAL.el();
    if (!i || !r) return;
    i.setAttribute("placeholder", "搜记录 / 文献 / 功能设置 · Cmd/Ctrl+K");
    i.oninput = () => {
      clearTimeout(PAL._timer);
      PAL._timer = setTimeout(() => PAL.run(i.value), 180);
    };
    i.onkeydown = e => {
      if (e.key === "ArrowDown") { e.preventDefault(); PAL.move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); PAL.move(-1); }
      else if (e.key === "Enter") { e.preventDefault(); PAL.activate(PAL.sel); }
      else if (e.key === "Escape") { PAL.close(); i.blur(); }
    };
    i.onfocus = () => { if (i.value.trim()) PAL.run(i.value); };
    /* 用 mousedown 而不是 click：blur 会先触发，click 时结果面板已经关了 */
    r.addEventListener("mousedown", e => {
      const row = e.target.closest("[data-pi]");
      if (!row) return;
      e.preventDefault();
      PAL.activate(Number(row.dataset.pi));
    });
    i.onblur = () => setTimeout(() => PAL.close(), 160);
  },

  async run(q) {
    q = (q || "").trim();
    PAL.q = q;
    if (!q) { PAL.close(); return; }
    const seq = ++PAL._seq;
    try {
      const d = await API.get("search?q=" + encodeURIComponent(q) + "&limit=30");
      if (seq !== PAL._seq) return;        // 打字快时旧请求后到，丢掉
      PAL.paint(d);
    } catch (e) {
      const { r } = PAL.el();
      if (r) { r.hidden = false; r.innerHTML = `<div class="sr-empty">搜索出错：${esc(String(e.message || e))}</div>`; }
    }
  },

  paint(d) {
    const { r } = PAL.el();
    if (!r) return;
    PAL.items = [];
    const groups = d.groups || [];
    if (!groups.length) {
      r.hidden = false;
      r.innerHTML = `<div class="sr-empty">没找到「${esc(PAL.q)}」<br>
        <span class="tiny muted">试试搜功能名（备份 / 钉钉 / 时区 / token）、稿件题目、作者、citekey</span></div>`;
      return;
    }
    let html = "";
    groups.forEach(g => {
      const more = g.total > g.items.length ? `<span class="sr-more">共 ${g.total} 条</span>` : "";
      html += `<div class="sr-h">${esc(g.label)}${more}</div>`;
      g.items.forEach(it => {
        const idx = PAL.items.length;
        PAL.items.push(Object.assign({ _group: g.key }, it));
        html += PAL.row(idx, g.key, it);
      });
    });
    r.hidden = false;
    r.innerHTML = html;
    PAL.sel = 0;
    PAL.highlight();
    PAL.open = true;
  },

  row(idx, kind, it) {
    const ICON = { feature: "⚙️", action: "⚡", record: "📄", library: "🗂", quote: "❝" };
    const sub = kind === "record"
      ? `<span class="sr-tag">${esc(it.label || "")}</span>${it.meta ? " " + esc(it.meta) : ""}`
      : kind === "library"
        ? esc(it.meta || "") + (it.citekey ? ` · <code>${esc(it.citekey)}</code>` : "")
        : kind === "quote" ? esc(it.meta || "")
          : (it.route ? `跳到「${esc(it.route === "settings" ? "设置" : it.route)}」` : "");
    return `<div class="sr" data-pi="${idx}">
      <span class="sr-ico">${ICON[kind] || "•"}</span>
      <span class="sr-main">
        <span class="sr-title">${esc(String(it.title || "").slice(0, 110))}</span>
        ${sub ? `<span class="sr-sub">${sub}</span>` : ""}
        ${it.snippet ? `<span class="sr-snip">${esc(it.snippet)}</span>` : ""}
      </span></div>`;
  },

  move(d) {
    if (!PAL.items.length) return;
    PAL.sel = (PAL.sel + d + PAL.items.length) % PAL.items.length;
    PAL.highlight();
  },

  highlight() {
    const { r } = PAL.el();
    if (!r) return;
    $$(".sr", r).forEach((el, i) => el.classList.toggle("on", i === PAL.sel));
    const on = $(".sr.on", r);
    if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest" });
  },

  close() {
    const { r } = PAL.el();
    if (r) r.hidden = true;
    PAL.open = false;
  },

  activate(i) {
    const it = PAL.items[i];
    if (!it) return;
    const { i: input } = PAL.el();
    PAL.close();
    if (input) { input.value = ""; input.blur(); }

    if (it.kind === "feature") return PAL.goFeature(it);
    if (it.kind === "action") return PAL.doAction(it);
    if (it.kind === "record") return PAL.openRecord(it);
    if (it.kind === "library") {
      go("reading");
      setTimeout(() => {
        PAL.revealCard("rd-library");
        const q = $("#libQ");
        if (q) { q.value = it.title.slice(0, 40); LIB.q = q.value; LIB.page = 0; LIB.load(); }
      }, 220);
      return;
    }
    if (it.kind === "quote") { toast(it.title); return; }
  },

  goFeature(it) {
    if (it.route && it.route !== S.route) go(it.route);
    if (!it.card) return;
    /* 等这一页画完再去找卡片。render() 是同步的，但 go() 里还有 renderNav，
       用 setTimeout 让出一帧最稳。 */
    setTimeout(() => PAL.revealCard(it.card), 220);
  },

  /* 展开并滚动到某张卡片，顺便闪一下，否则用户不知道跳到哪了 */
  revealCard(key) {
    const c = document.querySelector(`[data-cardkey="${key}"]`);
    if (!c) return;
    c.classList.remove("collapsed");
    if (typeof UI !== "undefined" && UI.setCollapsed) UI.setCollapsed(key, false);
    c.scrollIntoView({ behavior: "smooth", block: "center" });
    c.classList.add("flash");
    setTimeout(() => c.classList.remove("flash"), 1600);
    if (typeof bindModuleExtras === "function") { try { bindModuleExtras(); } catch (e) { } }
  },

  /* 搜索是扫磁盘的，能搜到的东西不一定在内存里 ——
     去年的一笔开支、半年前的一条饮食，首屏为了体积根本没带过来。
     以前这里要求「内存里有」才肯打开编辑器，于是搜到了、点了，
     只弹一个 toast，等于搜索白搜。editRecord 本来就会自己去取全量，
     所以只要有 schema 就直接开。 */
  openRecord(it) {
    go(it.view || "today");
    setTimeout(async () => {
      const sc = window["schema_" + it.coll];
      if (sc) { await UI.editRecord(it.coll, it.id, sc()); return; }
      toast(`${it.label}：${it.title}`);
    }, 220);
  },

  doAction(it) {
    const m = {
      "a-capture": () => quickCapture(),
      "a-new-ms": () => UI.editRecord("manuscripts", null, schema_manuscripts()),
      "a-new-reading": () => UI.editRecord("reading", null, schema_reading()),
      "a-new-sched": () => UI.editRecord("schedule", null, schema_schedule()),
      "a-new-idea": () => UI.editRecord("ideas", null, schema_ideas()),
      "a-sync": () => (typeof doSync === "function" ? doSync() : null),
      "a-backup": () => API.post("backup", {}).then(() => toast("已备份")).catch(e => toast("备份失败")),
    };
    const fn = m[it.id];
    if (fn) { try { fn(); } catch (e) { toast("执行失败：" + (e.message || e)); } }
  },
};

window.PAL = PAL;
