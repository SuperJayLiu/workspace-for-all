const PICK = new Set();   // 当前选中的记录（跨页面保留，直到你清空）

/* 学术工作台 · 通用组件：卡片收纳、教程、表单、拖拽、图表、画廊 */
const UI = {

  /* ---------------- 可收缩卡片（同一类可打开/收起，状态记忆） --------------- */
  card(key, title, en, bodyHtml, opts) {
    opts = opts || {};
    /* 用户在布局编辑里给这张卡设的个性化项（标题、条数、默认收起、备注） */
    const co = ((S.config || {}).card_opts || {})[key] || {};
    const shownTitle = co.title || title;
    const defOpen = co.collapsed ? false : (opts.defaultOpen !== false);
    const collapsed = UI.isCollapsed(key, defOpen);
    let body = bodyHtml;
    if (co.limit > 0) body = UI.limitRows(body, co.limit);
    if (co.note) body = `<div class="card-note">${esc(co.note)}</div>` + body;
    return `<section class="card ${collapsed ? "collapsed" : ""}" data-cardkey="${esc(key)}">
      <div class="card-head" data-collapse>
        <span class="caret">▾</span>
        <h2>${opts.icon ? opts.icon + " " : ""}${esc(shownTitle)}${en ? ` <span class="zh">${esc(en)}</span>` : ""}</h2>
        <span class="spacer"></span>
        ${opts.actions || ""}
      </div>
      <div class="card-body">${body}</div>
    </section>`;
  },

  /* 只显示前 n 条，其余折起来。纯字符串处理，不依赖各页面配合。 */
  limitRows(html, n) {
    const box = document.createElement("div");
    box.innerHTML = html;
    const rowsEl = Array.from(box.children).filter(el => el.classList.contains("row-line"));
    if (rowsEl.length <= n) return html;
    rowsEl.slice(n).forEach(el => el.classList.add("row-extra"));
    box.insertAdjacentHTML("beforeend",
      `<button class="btn sm ghost show-extra" data-showextra="1">还有 ${rowsEl.length - n} 条，点开看</button>`);
    return box.innerHTML;
  },
  isCollapsed(key, defOpen) {
    const st = UI._collapse();
    if (key in st) return st[key];
    return defOpen === false;
  },
  _collapse() {
    try { return JSON.parse(localStorage.getItem("collapse") || "{}"); } catch (e) { return {}; }
  },
  setCollapsed(key, v) {
    const st = UI._collapse(); st[key] = v;
    try { localStorage.setItem("collapse", JSON.stringify(st)); } catch (e) { }
  },

  /* ------------------------------- 可收缩教程 ---------------------------- */
  tut(key, title, html) {
    const dis = (S.config.tutorial_dismissed || {})[key];
    return `<div class="tut ${dis ? "collapsed" : ""}" data-tutkey="${esc(key)}">
      <div class="tut-head" data-tut><span class="caret">▾</span><span>📖 ${esc(title)}</span>
        <span class="spacer"></span><span class="tiny muted">点此收起/展开</span></div>
      <div class="tut-body">${html}</div></div>`;
  },

  /* --------------------------------- 表单 ------------------------------- */
  /* schema: [{k,label,type,opts,hint,wide}] type: text|textarea|date|number|select|url|check|tags */
  field(f, val) {
    const id = "f_" + f.k;
    let inner;
    if (f.type === "select") {
      inner = `<div class="pill-select" data-pill="${f.k}">` +
        (f.opts || []).map(o => {
          const v = typeof o === "string" ? o : o.v;
          const t = typeof o === "string" ? o : o.t;
          return `<button type="button" data-v="${esc(v)}" class="${String(val || "") === String(v) ? "on" : ""}">${esc(t)}</button>`;
        }).join("") + `</div><input type="hidden" id="${id}" value="${esc(val || "")}">`;
    } else if (f.type === "textarea") {
      inner = `<textarea id="${id}">${esc(val || "")}</textarea>`;
    } else if (f.type === "check") {
      inner = `<label class="small"><input type="checkbox" id="${id}" ${val ? "checked" : ""}> ${esc(f.checkLabel || "是")}</label>`;
    } else if (f.type === "tags") {
      inner = `<input id="${id}" value="${esc(Array.isArray(val) ? val.join(", ") : (val || ""))}" placeholder="用逗号分隔">`;
    } else {
      const t = f.type === "number" ? "number" : f.type === "date" ? "date" : f.type === "url" ? "url" : "text";
      inner = `<input type="${t}" step="any" id="${id}" value="${esc(val == null ? "" : val)}" placeholder="${esc(f.ph || "")}">`;
    }
    return `<div class="field ${f.wide ? "wide" : ""}"><label>${esc(f.label)}</label>${inner}
      ${f.hint ? `<div class="hint">${f.hint}</div>` : ""}</div>`;
  },
  readForm(schema) {
    const out = {};
    schema.forEach(f => {
      const el = document.getElementById("f_" + f.k);
      if (!el) return;
      if (f.type === "check") out[f.k] = el.checked;
      else if (f.type === "number") out[f.k] = el.value === "" ? null : Number(el.value);
      else if (f.type === "tags") out[f.k] = el.value.split(/[,，]/).map(s => s.trim()).filter(Boolean);
      else out[f.k] = el.value.trim();
    });
    return out;
  },

  /* --------------------------------- 弹窗 ------------------------------- */
  modal(title, bodyHtml, footHtml) {
    $("#modal").innerHTML = `
      <div class="modal-head"><h3>${esc(title)}</h3><span class="spacer"></span>
        <button class="icon-btn" data-close>✕</button></div>
      <div class="modal-body">${bodyHtml}</div>
      ${footHtml ? `<div class="modal-foot">${footHtml}</div>` : ""}`;
    $("#modalBack").hidden = false;
    UI.bindPills($("#modal"));
    $$("[data-close]", $("#modal")).forEach(b => b.onclick = UI.closeModal);
  },
  closeModal() { $("#modalBack").hidden = true; $("#modal").innerHTML = ""; },

  /* 通用记录编辑器 */
  /* 打开编辑器前，先把这条记录的**完整**内容从服务端取回来。
   *
   * 两个原因，第二个是硬伤：
   *   1. 别的设备（或 Claude）可能刚改过，用内存里那份会拿旧数据去覆盖。
   *   2. 首屏为了体积会把长正文截断（带 _body_more 标记）。
   *      如果编辑器直接拿内存里那份，文本框里就是截断后的内容，
   *      用户随手一保存，剩下的正文就**永久没了**。
   * 所以取全量这件事必须发生在唯一的写回路径上。
   */
  async editRecord(coll, id, schema, opts) {
    opts = opts || {};
    if (id) {
      const cur = byId(coll, id);
      if (!cur || cur._body_more) {
        try {
          const fresh = await API.get(`records/${encodeURIComponent(coll)}/${encodeURIComponent(id)}`);
          if (fresh && fresh.id) {
            const arr = S.data[coll] || (S.data[coll] = []);
            const i = arr.findIndex(x => x.id === id);
            if (i >= 0) arr[i] = fresh; else arr.push(fresh);
          }
        } catch (e) {
          if (!cur) { toast("这条记录读不出来：" + (e.message || e)); return; }
          /* 取不到但内存里有截断版：宁可不让编辑，也不能让用户把正文截断保存 */
          if (cur._body_more) {
            toast("连不上服务端，为避免把正文截断保存，这次先不打开编辑器。");
            return;
          }
        }
      }
    }
    const rec = id ? (byId(coll, id) || {}) : (opts.preset || {});
    const body = `<div class="form-grid">${schema.map(f => UI.field(f, rec[f.k])).join("")}</div>
      ${opts.extra ? opts.extra(rec) : ""}
      <div class="field wide" style="margin-top:11px"><label>笔记 / 正文（Markdown）</label>
      <textarea id="f_body" style="min-height:110px">${esc(rec.body || "")}</textarea></div>
      ${UI.linkBlock(coll, id, rec)}`;
    UI.modal(id ? "编辑" : "新建", body,
      `<button class="btn primary" id="mSave">保存</button>
       ${id ? `<button class="btn danger" id="mDel">删除</button>` : ""}
       <span class="spacer"></span><button class="btn" data-close>取消</button>`);
    UI.bindLinks(coll, id, schema, opts);
    $("#mSave").onclick = async (e) => {
      const btn = e.currentTarget;
      if (btn.disabled) return;                 // 手抖点两下不该存出两条
      btn.disabled = true; btn.textContent = "保存中…";
      try {
        const patch = UI.readForm(schema);
        patch.body = $("#f_body").value;
        if (id) patch.id = id;
        if (opts.beforeSave) opts.beforeSave(patch, rec);
        await saveRec(coll, Object.assign({}, rec, patch));
        UI.closeModal(); render(); renderNav();
        if (typeof RAIL !== "undefined") RAIL.renderCalendar();   // 右栏日历同步刷新
        toast("已保存");
      } catch (err) {
        btn.disabled = false; btn.textContent = "保存";
        throw err;
      }
    };
    if (id && $("#mDel")) $("#mDel").onclick = async () => {
      if (!confirm("确定删除？（会移到 local/trash，可找回）")) return;
      await deleteRec(coll, id); UI.closeModal(); render(); renderNav(); toast("已删除");
    };
  },


  /* ---------------------------- 跨库关联 ------------------------------ */
  /* 想法 ↔ 稿件 ↔ 文献 ↔ 会议 ↔ 日程：一条记录记在自己身上，两头都写，
     所以从哪一边打开都看得见对面。点一下直接跳过去编辑那一条。 */

  linkRefs(rec) {
    const v = (rec || {}).links;
    if (typeof v === "string") return v.split(/[,;\s]+/).filter(Boolean);
    return Array.isArray(v) ? v.map(String) : [];
  },

  linkResolve(ref) {
    const i = String(ref).indexOf(":");
    if (i < 0) return null;
    const coll = ref.slice(0, i), rid = ref.slice(i + 1);
    const r = (S.data[coll] || []).find(x => x.id === rid);
    return r ? { coll, id: rid, rec: r } : { coll, id: rid, rec: null };
  },

  /* 列表里的小标记：这条连着几条别的记录 */
  linkBadge(rec) {
    const n = UI.linkRefs(rec).length;
    if (!n) return "";
    const names = UI.linkRefs(rec).slice(0, 5).map(ref => {
      const x = UI.linkResolve(ref);
      return x ? `${COLL_LABEL[x.coll] || x.coll}：${(x.rec && (x.rec.title || x.rec.name)) || "已删除"}` : ref;
    }).join("\n");
    return `<span class="badge lk" title="${esc(names)}">🔗 ${n}</span>`;
  },

  linkBlock(coll, id, rec) {
    if (!id) {
      return `<div class="linkwrap"><label class="linklabel">🔗 关联</label>
        <div class="small muted">先保存这一条，就能把它和稿件、文献、会议连起来。</div></div>`;
    }
    return `<div class="linkwrap"><label class="linklabel">🔗 关联</label>
      <div id="linkList">${UI.linkChips(rec)}</div>
      <button class="btn sm ghost" id="linkAdd" style="margin-top:7px">＋ 关联到别的记录</button>
      <div class="hint">关联是双向的：在对面那条记录里也会出现这一条。</div></div>`;
  },

  linkChips(rec) {
    const refs = UI.linkRefs(rec);
    if (!refs.length) return `<div class="small muted">还没有关联。</div>`;
    return `<div class="chips">` + refs.map(ref => {
      const x = UI.linkResolve(ref);
      if (!x) return "";
      const label = x.rec ? (x.rec.title || x.rec.name || x.id) : "（记录已删除）";
      return `<span class="chip link ${x.rec ? "" : "dead"}" data-ref="${esc(ref)}">
        <span class="chip-tag">${esc(COLL_LABEL[x.coll] || x.coll)}</span>
        <span class="chip-go" title="打开这一条">${esc(String(label).slice(0, 42))}</span>
        <button class="chip-x" title="解除关联">✕</button></span>`;
    }).join("") + `</div>`;
  },

  bindLinks(coll, id, schema, opts) {
    if (!id) return;
    const me = coll + ":" + id;
    const refresh = () => {
      const fresh = (S.data[coll] || []).find(r => r.id === id) || {};
      const box = $("#linkList");
      if (box) box.innerHTML = UI.linkChips(fresh);
      bind();
    };
    const bind = () => {
      $$("#linkList .chip-go").forEach(el => el.onclick = () => {
        const ref = el.closest(".chip").dataset.ref;
        const x = UI.linkResolve(ref);
        if (!x || !x.rec) return toast("那条记录已经不在了");
        UI.closeModal();
        go(COLL_VIEW[x.coll] || x.coll);
        setTimeout(() => UI.openRecord(x.coll, x.id), 60);
      });
      $$("#linkList .chip-x").forEach(el => el.onclick = async () => {
        const ref = el.closest(".chip").dataset.ref;
        el.disabled = true;
        const r = await API.post("link", { a: me, b: ref, op: "remove" });
        if (!r.ok) { el.disabled = false; return toast(r.detail || "解除失败"); }
        await reload(); refresh(); toast("已解除关联");
      });
    };
    bind();
    const add = $("#linkAdd");
    if (add) add.onclick = () => UI.linkPicker(me, refresh);
  },

  /* 关联选择器：一个搜索框，跨所有库找，点一下就连上 */
  linkPicker(me, after) {
    const myColl = me.slice(0, me.indexOf(":"));
    const pool = [];
    COLL_SEARCH.forEach(c => (S.data[c] || []).forEach(r => {
      if (!r.id || (c + ":" + r.id) === me) return;
      pool.push({ coll: c, id: r.id, title: String(r.title || r.name || r.id),
                  sub: [r.date, r.deadline, r.status].filter(Boolean).join(" · ") });
    }));
    // 同类排后面：你多半想把想法连到稿件，而不是连到另一个想法
    pool.sort((a, b) => (a.coll === myColl) - (b.coll === myColl)
      || a.coll.localeCompare(b.coll) || a.title.localeCompare(b.title, "zh"));
    const rowHtml = list => list.length
      ? list.slice(0, 60).map(x => `<div class="pickrow" data-ref="${esc(x.coll + ":" + x.id)}">
          <span class="chip-tag">${esc(COLL_LABEL[x.coll] || x.coll)}</span>
          <b>${esc(x.title.slice(0, 52))}</b>
          ${x.sub ? `<small> · ${esc(x.sub.slice(0, 40))}</small>` : ""}</div>`).join("")
      : `<div class="small muted" style="padding:10px">没有匹配的记录。</div>`;
    /* 选择器**盖在**当前弹窗上面，而不是把弹窗的 innerHTML 换掉再换回来。
       原来那种做法有两个后果，都很致命：
         · innerHTML 序列化**不包含** input/textarea 的当前值 ——
           你在编辑器里敲了半天的正文，用一次关联选择器就回到了打开时的样子；
         · 换回来的是一份新 DOM，「保存」按钮上的事件处理器没了 ——
           点它毫无反应，不报错、不提示，只能关掉弹窗（内容随之丢弃）。
       盖一层就都没有这些问题：原来那份 DOM 从头到尾没被动过。 */
    const host = $("#modal");
    const layer = document.createElement("div");
    layer.className = "modal-layer";
    layer.style.cssText = "position:absolute;inset:0;background:var(--bg);"
      + "border-radius:inherit;display:flex;flex-direction:column;z-index:5";
    layer.innerHTML = `
      <div class="modal-head"><h3>关联到…</h3><span class="spacer"></span>
        <button class="icon-btn" id="lkX">✕</button></div>
      <div class="modal-body">
        <input id="lkq" class="lkq" placeholder="搜标题…（回车选第一条）" autocomplete="off">
        <div id="lkList" class="picklist">${rowHtml(pool)}</div>
      </div>
      <div class="modal-foot"><span class="spacer"></span>
        <button class="btn" id="lkBack">返回</button></div>`;
    const hostPos = getComputedStyle(host).position;
    if (hostPos === "static") host.style.position = "relative";
    host.appendChild(layer);
    const restore = () => { layer.remove(); };
    layer.querySelector("#lkBack").onclick = restore;
    layer.querySelector("#lkX").onclick = restore;
    const q = $("#lkq");
    /* 内存里那份是**裁过**的（生活流水只带近期），所以「内存里搜不到」
       不等于「这条不存在」。以前直接显示「没有匹配的记录。」——
       想把稿件关联到八个月前的一笔会议差旅，就会被告知那条不存在，
       而全局搜索明明找得到。所以内存里没有时补一次服务端搜索。 */
    let seq = 0;
    const filter = async () => {
      const s = q.value.trim().toLowerCase();
      const list = s ? pool.filter(x => x.title.toLowerCase().includes(s)
        || (COLL_LABEL[x.coll] || "").includes(s)) : pool;
      $("#lkList").innerHTML = rowHtml(list);
      bindRows();
      if (!s || list.length) return;
      const mine = ++seq;
      let extra = [];
      try {
        const r = await API.get(`search?q=${encodeURIComponent(s)}&limit=40`);
        const seen = new Set(pool.map(x => x.coll + ":" + x.id));
        extra = (r.groups || []).flatMap(g => g.items || [])
          .filter(x => x.kind === "record" && x.coll && x.id
            && COLL_SEARCH.includes(x.coll)
            && (x.coll + ":" + x.id) !== me && !seen.has(x.coll + ":" + x.id))
          .map(x => ({ coll: x.coll, id: x.id, title: String(x.title || x.id),
                       sub: String(x.meta || "") }));
      } catch (e) { /* 搜不动就维持「没有匹配」 */ }
      if (mine !== seq || !$("#lkList")) return;         // 用户已经又敲了字
      if (!extra.length) return;
      $("#lkList").innerHTML =
        `<div class="tiny muted" style="padding:6px 10px">这些不在当前页面的数据里，是从全库搜到的：</div>`
        + rowHtml(extra);
      bindRows();
    };
    const choose = async ref => {
      const r = await API.post("link", { a: me, b: ref, op: "add" });
      if (!r.ok) return toast(r.detail || "关联失败");
      await reload();
      restore();
      if (after) after();
      toast("已关联");
    };
    const bindRows = () => $$("#lkList .pickrow").forEach(el =>
      el.onclick = () => choose(el.dataset.ref));
    bindRows();
    q.oninput = filter;
    q.onkeydown = e => {
      if (e.key === "Enter") {
        e.preventDefault();
        const first = $("#lkList .pickrow");
        if (first) choose(first.dataset.ref);
      }
    };
    setTimeout(() => q.focus(), 30);
  },

  /* 从任何地方打开某一条记录的编辑器 */
  openRecord(coll, id) {
    const fn = window["schema_" + coll];
    if (!fn) return toast("这个库还没有编辑器");
    UI.editRecord(coll, id, fn());
  },

  /* 底部批量操作条 */
  pickBar() {
    let bar = $("#pickbar");
    if (!PICK.size) { if (bar) bar.remove(); return; }
    if (!bar) {
      document.body.insertAdjacentHTML("beforeend", `<div class="pickbar" id="pickbar"></div>`);
      bar = $("#pickbar");
    }
    bar.innerHTML = `<b>已选 ${PICK.size} 条</b>
      <button class="btn sm" id="pkAll">全选本页</button>
      <button class="btn sm" id="pkNone">取消选择</button>
      <span class="spacer"></span>
      <button class="btn sm" id="pkArchive">📦 存档</button>
      <button class="btn sm danger" id="pkDel">🗑 删除</button>`;
    $("#pkAll").onclick = () => {
      $$("[data-pick]").forEach(r => PICK.add(r.dataset.pick));
      render(); renderNav();
    };
    $("#pkNone").onclick = () => { PICK.clear(); render(); renderNav(); };
    $("#pkArchive").onclick = () => UI.pickRun("archive");
    $("#pkDel").onclick = () => UI.pickRun("delete");
  },

  async pickRun(mode) {
    const list = [...PICK];
    const word = mode === "delete" ? "删除" : "存档";
    if (!confirm(`确定${word}选中的 ${list.length} 条？` +
      (mode === "delete" ? "\n（移到 local/trash，还能捞回来）" : "\n（存档只是标记，记录还在）"))) return;
    const bar = $("#pickbar");
    if (bar) bar.innerHTML = `<b>${word}中… 0/${list.length}</b>`;
    let ok = 0, bad = 0;
    for (const key of list) {
      const i = key.indexOf(":");
      const coll = key.slice(0, i), id = key.slice(i + 1);
      try {
        if (mode === "delete") await deleteRec(coll, id);
        else await patchRec(coll, id, { archived: true, status: "shelved" });
        ok++;
      } catch (e) { bad++; }
      if (bar) bar.innerHTML = `<b>${word}中… ${ok + bad}/${list.length}</b>`;
    }
    PICK.clear();
    render(); renderNav();
    toast(`${word}了 ${ok} 条` + (bad ? `，${bad} 条失败` : ""));
  },

  bindPills(root) {
    $$(".pill-select", root || document).forEach(ps => {
      ps.onclick = e => {
        const b = e.target.closest("button[data-v]"); if (!b) return;
        $$("button", ps).forEach(x => x.classList.remove("on"));
        b.classList.add("on");
        const hidden = document.getElementById("f_" + ps.dataset.pill);
        if (hidden) hidden.value = b.dataset.v;
        if (ps.dataset.onchange && window[ps.dataset.onchange]) window[ps.dataset.onchange](b.dataset.v);
      };
    });
  },

  /* ------------------------------ 可拖动进度条 ---------------------------- */
  prog(pct, attrs) {
    pct = Math.max(0, Math.min(100, Math.round(pct || 0)));
    return `<div class="prog-wrap"><div class="prog" ${attrs || ""}><div class="fill" style="width:${pct}%"></div></div>
      <span class="pct">${pct}%</span></div>`;
  },
  bindProg() {
    $$(".prog[data-prog-coll]").forEach(el => {
      if (el._bound) return; el._bound = true;
      const apply = (clientX, commit) => {
        const r = el.getBoundingClientRect();
        let p = Math.round(((clientX - r.left) / r.width) * 100);
        p = Math.max(0, Math.min(100, p));
        $(".fill", el).style.width = p + "%";
        const lbl = el.parentElement.querySelector(".pct"); if (lbl) lbl.textContent = p + "%";
        if (commit) patchRec(el.dataset.progColl, el.dataset.progId, { progress: p }).then(() => toast("进度 " + p + "%"));
      };
      const move = e => apply((e.touches ? e.touches[0] : e).clientX, false);
      const up = e => {
        document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up);
        document.removeEventListener("touchmove", move); document.removeEventListener("touchend", up);
        apply((e.changedTouches ? e.changedTouches[0] : e).clientX, true);
      };
      const down = e => {
        e.preventDefault();
        document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
        document.addEventListener("touchmove", move, { passive: false }); document.addEventListener("touchend", up);
        apply((e.touches ? e.touches[0] : e).clientX, false);
      };
      el.addEventListener("mousedown", down);
      el.addEventListener("touchstart", down, { passive: false });
    });
  },

  /* -------------------------------- 分段状态 ----------------------------- */
  seg(stages, cur, coll, id, field) {
    const i = stages.findIndex(s => (s.v || s) === cur);
    return `<div class="seg" data-seg-coll="${coll}" data-seg-id="${id}" data-seg-field="${field || "stage"}">` +
      stages.map((s, j) => {
        const v = s.v || s, t = s.t || s;
        const cls = v === cur ? "on" : (j < i ? "done-stage" : "");
        return `<button data-v="${esc(v)}" class="${cls}">${esc(t)}</button>`;
      }).join("") + `</div>`;
  },
  bindSeg() {
    $$(".seg[data-seg-coll]").forEach(el => {
      if (el._bound) return; el._bound = true;
      el.onclick = async e => {
        const b = e.target.closest("button[data-v]"); if (!b) return;
        const patch = {}; patch[el.dataset.segField] = b.dataset.v;
        await patchRec(el.dataset.segColl, el.dataset.segId, patch);
        render(); renderNav(); toast("已更新为「" + b.textContent + "」");
      };
    });
  },

  /* --------------------------------- 看板 ------------------------------- */
  bindKanban() {
    let dragged = null;
    $$(".kcard[draggable]").forEach(c => {
      c.ondragstart = e => { dragged = c; c.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; };
      c.ondragend = () => { c.classList.remove("dragging"); dragged = null; };
    });
    $$(".kcol[data-stage]").forEach(col => {
      col.ondragover = e => { e.preventDefault(); col.classList.add("over"); };
      col.ondragleave = () => col.classList.remove("over");
      col.ondrop = async e => {
        e.preventDefault(); col.classList.remove("over");
        if (!dragged) return;
        const patch = {}; patch[col.dataset.field || "stage"] = col.dataset.stage;
        await patchRec(dragged.dataset.coll, dragged.dataset.id, patch);
        render(); renderNav(); toast("已移到「" + col.dataset.stageName + "」");
      };
    });
  },

  /* --------------------------------- 甘特 ------------------------------- */
  gantt(items, opts) {
    opts = opts || {};
    const today = new Date(); today.setHours(0, 0, 0, 0);
    let min = null, max = null;
    items.forEach(it => {
      const a = parseDate(it.start), b = parseDate(it.end);
      if (a && (!min || a < min)) min = a;
      if (b && (!max || b > max)) max = b;
    });
    if (!min) min = new Date(today);
    if (!max) max = new Date(today.getTime() + 60 * 86400000);
    min = new Date(min.getTime() - 5 * 86400000);
    max = new Date(max.getTime() + 5 * 86400000);
    const span = Math.max(1, (max - min) / 86400000);
    const pos = d => ((parseDate(d) - min) / 86400000) / span * 100;
    const ticks = [];
    let cur = new Date(min.getFullYear(), min.getMonth(), 1);
    while (cur < max) {
      const p = ((cur - min) / 86400000) / span * 100;
      if (p >= 0) ticks.push(`<div class="gantt-tick" style="left:${p}%">${cur.getMonth() + 1}月</div>`);
      cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
    }
    const todayP = ((today - min) / 86400000) / span * 100;
    const rowsHtml = items.map(it => {
      const l = pos(it.start), r = pos(it.end);
      const w = Math.max(1.2, r - l);
      return `<div class="gantt-row">
        <div class="gantt-label" title="${esc(it.label)}">${esc(it.label)}</div>
        <div class="gantt-track">
          ${ticks.join("")}
          <div class="gantt-today" style="left:${todayP}%"></div>
          <div class="gantt-bar ${it.cls || ""}" style="left:${l}%;width:${w}%"
               data-gid="${esc(it.id)}" data-gcoll="${esc(it.coll || "")}"
               data-gstart="${esc(it.start)}" data-gend="${esc(it.end)}"
               data-gspan="${span}" title="${esc(it.label)} ${esc(it.start)} → ${esc(it.end)}">
            <span class="h l"></span>${esc(it.short || "")}<span class="h r"></span>
          </div>
        </div></div>`;
    }).join("");
    return `<div class="gantt"><div class="gantt-grid">
      <div class="gantt-head"><div class="gantt-label">项目 / 任务</div>
        <div class="gantt-track" style="position:relative">${ticks.join("")}
        <div class="gantt-today" style="left:${todayP}%"></div></div></div>
      ${rowsHtml || '<div class="empty">暂无带日期的条目</div>'}
    </div></div>`;
  },
  bindGantt() {
    $$(".gantt-bar[data-gid]").forEach(bar => {
      if (bar._bound) return; bar._bound = true;
      const track = bar.parentElement;
      let mode = null, startX = 0, l0 = 0, w0 = 0;
      const dayPx = () => track.getBoundingClientRect().width / Number(bar.dataset.gspan);
      const down = e => {
        const t = e.target;
        mode = t.classList.contains("l") ? "l" : t.classList.contains("r") ? "r" : "move";
        startX = (e.touches ? e.touches[0] : e).clientX;
        l0 = bar.offsetLeft; w0 = bar.offsetWidth;
        e.preventDefault();
        document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
        document.addEventListener("touchmove", move, { passive: false }); document.addEventListener("touchend", up);
      };
      const move = e => {
        const dx = (e.touches ? e.touches[0] : e).clientX - startX;
        if (mode === "move") bar.style.left = (l0 + dx) + "px";
        else if (mode === "r") bar.style.width = Math.max(6, w0 + dx) + "px";
        else { bar.style.left = (l0 + dx) + "px"; bar.style.width = Math.max(6, w0 - dx) + "px"; }
      };
      const up = async e => {
        document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up);
        document.removeEventListener("touchmove", move); document.removeEventListener("touchend", up);
        const dx = (e.changedTouches ? e.changedTouches[0] : e).clientX - startX;
        const dd = Math.round(dx / dayPx());
        if (!dd) { render(); return; }
        const shift = (s, n) => { const d = parseDate(s); if (!d) return s; d.setDate(d.getDate() + n); return todayStr(d); };
        const patch = {};
        if (mode === "move") { patch.start = shift(bar.dataset.gstart, dd); patch.end = shift(bar.dataset.gend, dd); }
        else if (mode === "r") patch.end = shift(bar.dataset.gend, dd);
        else patch.start = shift(bar.dataset.gstart, dd);
        await patchRec(bar.dataset.gcoll, bar.dataset.gid, patch);
        render(); toast("日期已调整");
      };
      bar.addEventListener("mousedown", down);
      bar.addEventListener("touchstart", down, { passive: false });
    });
  },

  /* ------------------------------ 图表 / 画廊 ---------------------------- */
  gallery(files, opts) {
    opts = opts || {};
    if (!files.length) return `<div class="empty">这个文件夹里没找到图表。把图放进 <code>figures/</code> 或 <code>tables/</code> 即可自动显示。</div>`;
    return `<div class="gallery">` + files.map(f => `
      <div class="gitem ${opts.pinned === f.path ? "pinned" : ""}" data-fig="${esc(f.path)}">
        <div class="fig-slot" data-src="${esc(f.path)}" style="min-height:74px;display:grid;place-items:center;color:var(--muted);font-size:11px">载入中…</div>
        ${opts.pinTo ? `<span class="pin" data-pin="${esc(f.path)}" data-pinid="${esc(opts.pinTo)}">${opts.pinned === f.path ? "★" : "☆"}</span>` : ""}
        <div class="cap" title="${esc(f.name)}">${esc(f.name)}</div>
      </div>`).join("") + `</div>`;
  },
  async renderFigures(root) {
    const slots = $$(".fig-slot[data-src]", root || document).filter(s => !s._done);
    for (const slot of slots) {
      slot._done = true;
      const path = slot.dataset.src;
      const url = "/api/file?path=" + encodeURIComponent(path);
      if (/\.(png|jpe?g|gif|svg|webp)$/i.test(path)) {
        slot.innerHTML = `<img src="${url}" loading="lazy" alt="">`;
      } else if (/\.pdf$/i.test(path)) {
        try {
          await UI.ensurePdfJs();
          const pdf = await pdfjsLib.getDocument(url).promise;
          const page = await pdf.getPage(1);
          const vp0 = page.getViewport({ scale: 1 });
          const scale = Math.min(2, 260 / vp0.width);
          const vp = page.getViewport({ scale });
          const cv = document.createElement("canvas");
          cv.width = vp.width; cv.height = vp.height;
          await page.render({ canvasContext: cv.getContext("2d"), viewport: vp }).promise;
          slot.innerHTML = ""; slot.appendChild(cv);
        } catch (e) {
          slot.innerHTML = `<a href="${url}" target="_blank" class="small">打开 PDF ↗</a>`;
        }
      } else {
        slot.innerHTML = `<a href="${url}" target="_blank" class="small">打开文件 ↗</a>`;
      }
    }
  },
  ensurePdfJs() {
    if (window._pdfjsReady) return window._pdfjsReady;
    window._pdfjsReady = new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
      s.onload = () => {
        pdfjsLib.GlobalWorkerOptions.workerSrc =
          "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        res();
      };
      s.onerror = rej;
      document.head.appendChild(s);
    });
    return window._pdfjsReady;
  },

  /* ------------------------------- 迷你折线 ------------------------------ */
  spark(values, opts) {
    opts = opts || {};
    if (!values.length) return "";
    const w = 300, h = 46, max = Math.max(1, ...values.map(v => Math.abs(v)));
    const pts = values.map((v, i) => [i / Math.max(1, values.length - 1) * w, h - 3 - (v / max) * (h - 8)]);
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <path d="${d}" fill="none" stroke="${opts.color || "var(--accent)"}" stroke-width="2"/>
      ${opts.area ? `<path d="${d} L ${w} ${h} L 0 ${h} Z" fill="${opts.color || "var(--accent)"}" opacity=".12"/>` : ""}
    </svg>`;
  },

  /* --------------------------- 渲染后统一绑定事件 -------------------------- */
  afterRender() {
    $$("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
    /* 多选批量操作：行首出现勾选框，选中后页面底部弹出操作条 */
    $$("[data-pick]").forEach(row => {
      if (row.querySelector(".pickbox")) return;
      const [coll, id] = row.dataset.pick.split(":");
      row.insertAdjacentHTML("afterbegin",
        `<input type="checkbox" class="pickbox" data-pcoll="${coll}" data-pid="${id}"
          ${(PICK.has(row.dataset.pick) ? "checked" : "")}>`);
    });
    $$(".pickbox").forEach(cb => cb.onclick = e => {
      e.stopPropagation();
      const key = cb.dataset.pcoll + ":" + cb.dataset.pid;
      cb.checked ? PICK.add(key) : PICK.delete(key);
      UI.pickBar();
    });
    UI.pickBar();
    $$("[data-showextra]").forEach(b => b.onclick = e => {
      e.stopPropagation();
      const body = b.closest(".card-body");
      $$(".row-extra", body).forEach(r => r.classList.remove("row-extra"));
      b.remove();
    });
    $$("[data-hidesample]").forEach(b => b.onclick = async (e) => {
      e.stopPropagation();
      await saveConfig({ hide_samples: true });
      render(); renderNav();
      toast("示例已隐藏 —— 设置里可以随时恢复或彻底删掉");
    });
    /* 整行可点：以前只有行尾那个「前往」小按钮能点，太难瞄了 */
    $$(".row-line[data-rowgo]").forEach(row => {
      row.classList.add("clickable");
      row.onclick = e => {
        if (e.target.closest("button, a, input, select, textarea, label")) return;
        go(row.dataset.rowgo);
      };
    });
    $$("[data-collapse]").forEach(h => h.onclick = e => {
      if (e.target.closest("button:not([data-collapse])")) return;
      const card = h.closest(".card");
      card.classList.toggle("collapsed");
      UI.setCollapsed(card.dataset.cardkey, card.classList.contains("collapsed"));
    });
    $$("[data-tut]").forEach(h => h.onclick = async () => {
      const box = h.closest(".tut");
      box.classList.toggle("collapsed");
      const d = Object.assign({}, S.config.tutorial_dismissed || {});
      d[box.dataset.tutkey] = box.classList.contains("collapsed");
      await saveConfig({ tutorial_dismissed: d });
    });
    $$("[data-edit]").forEach(b => b.onclick = () => {
      const [coll, id] = b.dataset.edit.split(":");
      (window["schema_" + coll] ? UI.editRecord(coll, id || null, window["schema_" + coll]()) : null);
    });
    $$("[data-del]").forEach(b => b.onclick = async () => {
      const [coll, id] = b.dataset.del.split(":");
      if (!confirm("确定删除？")) return;
      await deleteRec(coll, id); render(); renderNav(); toast("已删除");
    });
    $$("[data-toggle]").forEach(b => b.onchange = async () => {
      const [coll, id, field] = b.dataset.toggle.split(":");
      const cur = byId(coll, id); const patch = {}; patch[field] = !cur[field];
      await patchRec(coll, id, patch); render(); renderNav();
    });
    $$("[data-pin]").forEach(b => b.onclick = async e => {
      e.stopPropagation();
      const cur = byId("manuscripts", b.dataset.pinid);
      const val = cur.pinned_figure === b.dataset.pin ? "" : b.dataset.pin;
      await patchRec("manuscripts", b.dataset.pinid, { pinned_figure: val });
      render(); toast(val ? "已钉为主结果" : "已取消");
    });
    UI.bindPills();
    UI.bindProg();
    UI.bindSeg();
    UI.bindKanban();
    UI.bindGantt();
    UI.renderFigures();
    if (window.bindModuleExtras) window.bindModuleExtras();
  },
};
