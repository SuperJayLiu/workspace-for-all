/* 快捷入口条 + 🎛 布局编辑模式（拖动排序 / 隐藏 / 调宽度） */

const QL = {
  render() {
    const box = $("#qlinks"); if (!box) return;
    const links = S.config.quicklinks || [];
    box.innerHTML = links.map((l, i) => `
      <button class="qlink" data-ql="${i}" draggable="true" title="${esc(l.url)}">
        <span class="ic" style="background:${esc(l.color || "#5a6478")}">${esc(l.letter || (l.name || "?")[0])}</span>${esc(l.name)}
      </button>`).join("") + `<button class="qlink add" id="qlAdd">＋</button>`;
    $$("[data-ql]").forEach(b => {
      const l = links[Number(b.dataset.ql)];
      b.onclick = e => {
        if (document.body.classList.contains("editing")) { QL.edit(Number(b.dataset.ql)); return; }
        QL.open(l);
      };
      b.ondragstart = e => { QL._drag = Number(b.dataset.ql); b.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; };
      b.ondragend = () => b.classList.remove("dragging");
      b.ondragover = e => e.preventDefault();
      b.ondrop = async e => {
        e.preventDefault();
        const from = QL._drag, to = Number(b.dataset.ql);
        if (from == null || from === to) return;
        const arr = (S.config.quicklinks || []).slice();
        arr.splice(to, 0, arr.splice(from, 1)[0]);
        await saveConfig({ quicklinks: arr }); QL.render();
      };
    });
    $("#qlAdd").onclick = () => QL.edit(null);
  },


  /* 先试着唤起桌面软件，唤不起来再退回网页。
     浏览器没有"这个协议装没装"的 API，所以只能用这个土办法：
     跳一下自定义协议，如果页面被系统切走（软件起来了）就什么都不做；
     若干毫秒后页面还在前台，说明没唤起来，再开网页。 */
  open(l) {
    const web = l.url, scheme = (l.app || "").trim();
    if (!scheme) { window.open(web, "_blank", "noopener"); return; }
    let left = false;
    const mark = () => { if (document.hidden) left = true; };
    document.addEventListener("visibilitychange", mark);
    window.addEventListener("blur", mark);
    const f = document.createElement("iframe");   // 用隐藏 iframe 跳协议，避免当前页被导航走
    f.style.display = "none";
    f.src = scheme;
    document.body.appendChild(f);
    setTimeout(() => {
      document.removeEventListener("visibilitychange", mark);
      window.removeEventListener("blur", mark);
      f.remove();
      if (!left && !document.hidden && web) window.open(web, "_blank", "noopener");
    }, 1200);
  },

  edit(idx) {
    const links = (S.config.quicklinks || []).slice();
    const l = idx == null ? { name: "", url: "", color: "#3b5bdb", letter: "", group: "" } : links[idx];
    UI.modal(idx == null ? "新增快捷入口" : "编辑快捷入口", `
      <div class="form-grid">
        <div class="field"><label>名称</label><input id="ql_n" value="${esc(l.name)}" placeholder="Google Scholar"></div>
        <div class="field"><label>网址</label><input id="ql_u" value="${esc(l.url)}" placeholder="https://…"></div>
        <div class="field wide"><label>桌面软件协议（可留空）</label>
          <input id="ql_a" value="${esc(l.app || "")}" placeholder="claude:// 或 chatgpt://">
          <div class="hint">填了就先尝试唤起本机软件，1.2 秒内没反应再退回网页。不确定填什么就留空。</div></div>
        <div class="field"><label>图标字母</label><input id="ql_l" value="${esc(l.letter || "")}" maxlength="2" placeholder="S"></div>
        <div class="field"><label>颜色</label><input type="color" id="ql_c" value="${esc(l.color || "#3b5bdb")}"></div>
        <div class="field"><label>分组</label><input id="ql_g" value="${esc(l.group || "")}" placeholder="AI / 学术 / 生活"></div>
      </div>
      <div class="wz-note">没填软件协议时，链接在<b>当前这个浏览器</b>的新标签页打开——只要你在 Chrome 里登录过一次，
        点这些按钮就是已登录状态。填了协议则优先唤起本机装的桌面软件（Claude、ChatGPT 都有 Mac 版），
        唤不起来会自动退回网页，不会卡住。</div>`,
      `<button class="btn primary" id="ql_save">保存</button>
       ${idx == null ? "" : `<button class="btn danger" id="ql_del">删除</button>`}
       <span class="spacer"></span><button class="btn" data-close>取消</button>`);
    $("#ql_save").onclick = async () => {
      const item = {
        name: $("#ql_n").value.trim() || "未命名",
        url: $("#ql_u").value.trim(),
        letter: $("#ql_l").value.trim() || ($("#ql_n").value.trim()[0] || "?").toUpperCase(),
        color: $("#ql_c").value, group: $("#ql_g").value.trim(),
        app: $("#ql_a").value.trim(),
      };
      if (!/^https?:\/\//.test(item.url)) { alert("网址要以 http:// 或 https:// 开头"); return; }
      if (idx == null) links.push(item); else links[idx] = item;
      await saveConfig({ quicklinks: links });
      UI.closeModal(); QL.render(); toast("已保存");
    };
    if (idx != null && $("#ql_del")) $("#ql_del").onclick = async () => {
      links.splice(idx, 1); await saveConfig({ quicklinks: links });
      UI.closeModal(); QL.render(); toast("已删除");
    };
  },
};

/* ---------------------------------------------------- 布局编辑模式 */
const EDIT = {
  on: false,

  toggle(force) {
    EDIT.on = force == null ? !EDIT.on : force;
    document.body.classList.toggle("editing", EDIT.on);
    $("#editbar").hidden = !EDIT.on;
    if (EDIT.on) { EDIT.decorate(); EDIT.bindRailResize(); }
    else render();
  },

  decorate() {
    const hidden = new Set((S.config.layout || {}).hidden_cards || []);
    $$("#view .card, #view .stat").forEach(el => {
      const key = el.dataset.cardkey || el.querySelector(".k")?.textContent || "";
      if (!key) return;
      el.dataset.ekey = key;
      if (!el.querySelector(".drag")) {
        el.insertAdjacentHTML("afterbegin",
          `<span class="drag" draggable="true" title="拖动排序">⠿</span>
           <span class="eyeb" title="隐藏/显示">${hidden.has(key) ? "🚫" : "👁"}</span>
           ${el.classList.contains("card") ? `<span class="gearb" title="改标题、限制条数">⚙</span>` : ""}`);
      }
      el.classList.toggle("card-hidden", hidden.has(key));
    });
    EDIT.bindDrag();
    $$(".gearb").forEach(b => b.onclick = e => {
      e.stopPropagation();
      EDIT.cardOptions(b.closest("[data-ekey]").dataset.ekey);
    });
    $$(".eyeb").forEach(b => b.onclick = async e => {
      e.stopPropagation();
      const el = b.closest("[data-ekey]"); const key = el.dataset.ekey;
      const cur = new Set(((S.config.layout || {}).hidden_cards || []));
      cur.has(key) ? cur.delete(key) : cur.add(key);
      const L = Object.assign({}, S.config.layout || {}, { hidden_cards: [...cur] });
      await saveConfig({ layout: L });
      b.textContent = cur.has(key) ? "🚫" : "👁";
      el.classList.toggle("card-hidden", cur.has(key));
    });
  },


  /* 每张卡自己的小设置：换标题、限制显示条数、折叠。
     目的很简单——想改点小东西不用每次去找人改代码。 */
  cardOptions(key) {
    const all = Object.assign({}, (S.config.card_opts || {}));
    const cur = Object.assign({ title: "", limit: 0, note: "" }, all[key] || {});
    const el = $(`[data-cardkey="${CSS.escape(key)}"]`);
    const orig = el ? (el.querySelector(".card-head h2")?.textContent || key).trim() : key;
    UI.modal("这张卡的设置", `
      <div class="small muted" style="margin-bottom:10px">改的只是这张卡的显示方式，数据一点不动。
        留空就是用默认的。</div>
      <div class="form-grid">
        <div class="field wide"><label>标题</label>
          <input id="co_title" value="${esc(cur.title)}" placeholder="${esc(orig)}"></div>
        <div class="field"><label>最多显示几条</label>
          <input id="co_limit" type="number" min="0" value="${cur.limit || ""}" placeholder="不限">
          <div class="hint">超出的会折起来，点「还有 N 条」再展开</div></div>
        <div class="field"><label>默认状态</label>
          <div class="pill-select" data-pill="co_open">
            <button type="button" data-v="open" class="${cur.collapsed ? "" : "on"}">展开</button>
            <button type="button" data-v="fold" class="${cur.collapsed ? "on" : ""}">收起</button>
          </div><input type="hidden" id="f_co_open" value="${cur.collapsed ? "fold" : "open"}"></div>
        <div class="field wide"><label>自己加一句备注（显示在卡片顶部）</label>
          <input id="co_note" value="${esc(cur.note || "")}" placeholder="比如：这周先别管这里"></div>
      </div>`,
      `<button class="btn primary" id="coSave">保存</button>
       <button class="btn" id="coReset">恢复默认</button>
       <span class="spacer"></span><button class="btn ghost" data-close>取消</button>`);
    UI.bindPills($("#modal"));
    $("#coSave").onclick = async () => {
      const v = {
        title: $("#co_title").value.trim(),
        limit: Number($("#co_limit").value) || 0,
        collapsed: $("#f_co_open").value === "fold",
        note: $("#co_note").value.trim(),
      };
      if (!v.title && !v.limit && !v.collapsed && !v.note) delete all[key]; else all[key] = v;
      await saveConfig({ card_opts: all });
      UI.closeModal(); render(); if (EDIT.on) EDIT.decorate();
      toast("这张卡的设置已保存");
    };
    $("#coReset").onclick = async () => {
      delete all[key];
      await saveConfig({ card_opts: all });
      UI.closeModal(); render(); if (EDIT.on) EDIT.decorate();
      toast("已恢复默认");
    };
  },

  bindDrag() {
    let src = null;
    $$("#view .drag").forEach(h => {
      const card = h.closest("[data-ekey]");
      h.ondragstart = e => { src = card; card.style.opacity = ".4"; e.dataTransfer.effectAllowed = "move"; };
      h.ondragend = () => { if (src) src.style.opacity = ""; src = null; EDIT.persistOrder(); };
    });
    $$("#view .card, #view .stat").forEach(el => {
      el.ondragover = e => { if (src && src !== el) e.preventDefault(); };
      el.ondrop = e => {
        e.preventDefault();
        if (!src || src === el) return;
        const parent = el.parentElement;
        if (src.parentElement !== parent) return;
        const after = [...parent.children].indexOf(src) < [...parent.children].indexOf(el);
        parent.insertBefore(src, after ? el.nextSibling : el);
      };
    });
  },

  async persistOrder() {
    const order = {};
    ["#view"].forEach(sel => {
      $$(sel + " [data-ekey]").forEach((el, i) => { order[el.dataset.ekey] = i; });
    });
    const L = Object.assign({}, S.config.layout || {});
    L.card_order = Object.assign({}, L.card_order || {}, { [S.route]: order });
    await saveConfig({ layout: L });
  },

  bindRailResize() {
    const rail = $("#rail"); if (!rail || rail.classList.contains("mini")) return;
    if (rail._rs) return; rail._rs = true;
    const grip = document.createElement("div");
    grip.className = "rail-grip";
    grip.title = "拖动改变右栏宽度";
    rail.appendChild(grip);
    let x0 = 0, w0 = 0;
    const down = e => {
      x0 = (e.touches ? e.touches[0] : e).clientX;
      w0 = rail.getBoundingClientRect().width;
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
      e.preventDefault();
    };
    const mv = e => {
      const w = Math.max(250, Math.min(520, w0 - ((e.touches ? e.touches[0] : e).clientX - x0)));
      document.documentElement.style.setProperty("--rail-w", w + "px");
      grip.dataset.w = w;
    };
    const up = async () => {
      document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up);
      document.body.style.userSelect = "";
      if (grip.dataset.w) await RAIL.setState({ rail_width: Number(grip.dataset.w) });
    };
    grip.addEventListener("mousedown", down);
  },

  /* 渲染后按保存的顺序与隐藏状态重排 */
  apply() {
    const L = S.config.layout || {};
    const hidden = new Set(L.hidden_cards || []);
    const order = (L.card_order || {})[S.route];
    $$("#view .card").forEach(el => {
      if (el.dataset.cardkey && hidden.has(el.dataset.cardkey)) el.style.display = "none";
    });
    $$("#view .stat").forEach(el => {
      const k = el.querySelector(".k") ? el.querySelector(".k").textContent : "";
      if (k && hidden.has(k)) el.style.display = "none";
    });
    if (!order) return;
    const view = $("#view");
    const items = $$("#view .card").filter(el => order[el.dataset.cardkey] != null);
    items.sort((a, b) => order[a.dataset.cardkey] - order[b.dataset.cardkey])
      .forEach(el => view.appendChild(el));
  },
};
