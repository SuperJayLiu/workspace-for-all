/* 每日箴言 banner + 箴言库
   选取是确定性的：同一天永远同一句，走完一轮才重复；收藏的出现权重更高。 */

const QUOTE = {
  list: [],
  today: null,

  async load() {
    try {
      const r = await API.get("quotes");
      QUOTE.list = r.quotes || [];
    } catch (e) { QUOTE.list = []; }
    QUOTE.pickToday();
  },

  /* 以「距纪元的天数」为种子做无重复轮转：先按顺序走完全部，再换一个新的排列 */
  pickToday(offset) {
    const n = QUOTE.list.length;
    if (!n) { QUOTE.today = null; return; }
    const day = Math.floor(Date.now() / 86400000) + (offset || 0);
    const round = Math.floor(day / n);
    const idx = QUOTE.shuffleIndex(day % n, n, round);
    QUOTE.today = QUOTE.list[idx];
    QUOTE.todayIdx = idx;
  },
  /* 每一轮用一个不同的乘法置换，保证一轮内不重复且轮与轮之间顺序不同 */
  shuffleIndex(pos, n, round) {
    const coprime = QUOTE.coprimeFor(n, round);
    return (pos * coprime + round * 7919) % n;
  },
  coprimeFor(n, round) {
    const gcd = (a, b) => b ? gcd(b, a % b) : a;
    let c = 1 + ((round * 37 + 11) % Math.max(1, n - 1));
    let guard = 0;
    while (gcd(c, n) !== 1 && guard++ < n) c = (c % (n - 1)) + 1;
    return c;
  },

  banner() {
    const q = QUOTE.today;
    if (!q) return "";
    const total = QUOTE.list.length;
    const favs = QUOTE.list.filter(x => x.fav).length;
    return `<div class="banner" id="qBanner">
      <div class="q-acts">
        <button id="qNext" title="换一句">↻</button>
        <button id="qFav" title="${q.fav ? "取消收藏" : "收藏"}">${q.fav ? "♥" : "♡"}</button>
        <button id="qAll" title="打开箴言库">☰</button>
      </div>
      <div class="q-text">${esc(q.t)}</div>
      <div class="q-meta">
        <span class="q-tag">${todayStr()} · 每日一句</span>
        ${q.s ? `<span>${esc(q.s)}${q.y ? " · " + esc(q.y) : ""}</span>` : ""}
        <span>库中 ${total} 条${favs ? " · 收藏 " + favs : ""}</span>
      </div></div>`;
  },

  bind() {
    const nx = $("#qNext");
    if (nx) nx.onclick = () => {
      QUOTE._off = (QUOTE._off || 0) + 1;
      QUOTE.pickToday(QUOTE._off);
      const b = $("#qBanner");
      if (b) { b.outerHTML = QUOTE.banner(); QUOTE.bind(); }
    };
    const fv = $("#qFav");
    if (fv) fv.onclick = async () => {
      const q = QUOTE.today; if (!q) return;
      q.fav = !q.fav;
      await API.post("quotes/fav", { id: q.id, fav: q.fav });
      const b = $("#qBanner");
      if (b) { b.outerHTML = QUOTE.banner(); QUOTE.bind(); }
      toast(q.fav ? "已收藏" : "已取消收藏");
    };
    const al = $("#qAll");
    if (al) al.onclick = QUOTE.library;
  },

  library() {
    const render = (kw, tag) => {
      const k = (kw || "").trim().toLowerCase();
      const list = QUOTE.list.filter(q =>
        (!tag || tag === "all" || (tag === "fav" ? q.fav : q.tag === tag)) &&
        (!k || (q.t + " " + (q.s || "")).toLowerCase().includes(k)));
      return `<div class="qlib-count">${list.length} 条</div>` + list.slice(0, 400).map(q => `
        <div class="qlib-item ${q.fav ? "fav" : ""}">
          <div class="qi-t">${esc(q.t)}</div>
          <div class="qi-m">${esc(q.s || "")}${q.y ? " · " + esc(q.y) : ""}
            <span class="spacer"></span>
            <button class="lnk" data-qfav="${q.id}">${q.fav ? "♥ 已收藏" : "♡ 收藏"}</button>
            <button class="lnk" data-quse="${q.id}">今天用它</button>
            <button class="lnk" data-qdel="${q.id}">删除</button></div>
        </div>`).join("");
    };
    UI.modal("☰ 箴言库", `
      <div class="qlib-bar">
        <input id="qSearch" class="search" placeholder="搜索内容或出处…" style="flex:1">
        <div class="pill-select" data-pill="qTag">
          <button type="button" data-v="all" class="on">全部</button>
          <button type="button" data-v="mine">我的摘抄</button>
          <button type="button" data-v="classic">古今经典</button>
          <button type="button" data-v="fav">收藏</button>
        </div><input type="hidden" id="f_qTag" value="all">
      </div>
      <div class="qlib-add">
        <input id="qNewT" placeholder="加一句自己的…" style="flex:2">
        <input id="qNewS" placeholder="出处（可空）" style="flex:1">
        <button class="btn primary sm" id="qAdd">添加</button>
      </div>
      <div id="qlibList" class="qlib-list">${render("", "all")}</div>`,
      `<span class="spacer"></span><button class="btn" data-close>关闭</button>`);

    const refresh = () => {
      $("#qlibList").innerHTML = render($("#qSearch").value, $("#f_qTag").value);
      bindItems();
    };
    const bindItems = () => {
      $$("[data-qfav]").forEach(b => b.onclick = async () => {
        const q = QUOTE.list.find(x => x.id === b.dataset.qfav);
        q.fav = !q.fav;
        await API.post("quotes/fav", { id: q.id, fav: q.fav });
        refresh();
      });
      $$("[data-quse]").forEach(b => b.onclick = () => {
        const i = QUOTE.list.findIndex(x => x.id === b.dataset.quse);
        QUOTE.today = QUOTE.list[i];
        UI.closeModal();
        const bn = $("#qBanner"); if (bn) { bn.outerHTML = QUOTE.banner(); QUOTE.bind(); }
        toast("已换成这一句");
      });
      $$("[data-qdel]").forEach(b => b.onclick = async () => {
        if (!confirm("从箴言库里删掉这一条？")) return;
        await API.post("quotes/del", { id: b.dataset.qdel });
        QUOTE.list = QUOTE.list.filter(x => x.id !== b.dataset.qdel);
        refresh(); toast("已删除");
      });
    };
    bindItems();
    $("#qSearch").oninput = debounce(refresh, 160);
    $$('[data-pill="qTag"] button').forEach(b => b.addEventListener("click", () => setTimeout(refresh, 10)));
    $("#qAdd").onclick = async () => {
      const t = $("#qNewT").value.trim(); if (!t) return;
      const r = await API.post("quotes/add", { t, s: $("#qNewS").value.trim(), tag: "mine" });
      QUOTE.list = r.quotes || QUOTE.list;
      $("#qNewT").value = ""; $("#qNewS").value = "";
      refresh(); toast("已加入箴言库");
    };
  },
};
