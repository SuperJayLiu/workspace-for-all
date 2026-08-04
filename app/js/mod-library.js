/* 文献索引 · Library index
 *
 * 定位：几千上万条题录只做「找得到、跳得回去」，不做「在这里读」。
 * 精读笔记还是 data/reading/*.md 那套，从索引一键提升过来。
 *
 * 性能是这个模块的第一约束，写法上有三条硬规矩：
 *   1. 索引不进 bootstrap。首屏永远只拿到一个数字。
 *   2. 搜索在服务端做，一次最多画 50 行。三千条渲染要两秒，五十行是毫秒级。
 *   3. 搜索时只重画 #libList 这一块，绝不调全局 render()——
 *      全局 render 会把整页几十张卡重建一遍，敲一个字卡一次。
 */

const LIB = {
  q: "", page: 0, per: 50, sort: "year", total: 0, todo: false,
  loading: false, _timer: null, _painted: false,

  managers: [
    { v: "zotero", t: "Zotero" }, { v: "mendeley", t: "Mendeley" },
    { v: "endnote", t: "EndNote" }, { v: "papers", t: "Papers / 其它" },
    { v: "none", t: "不用文献管理器" },
  ],

  manager() { return ((S.config.reading || {}).manager) || "zotero"; },

  card() {
    const n = S.libraryCount || 0;
    const mgr = LIB.manager();
    return UI.card("rd-library", "文献索引", n ? `${n} 条` : "还没导入", `
      <div class="small muted" style="margin-bottom:10px">
        把 Zotero / EndNote / Mendeley 里的题录导进来做一张<b>可搜索的总表</b>，
        一行一篇，点开直接跳回你原来的软件、DOI 或本地 PDF。
        <b>这里不替代你的文献管理器</b>，只做索引和跳转 ——
        你真正精读的那些，用「提升为精读」挪进下面的笔记里，才有研究问题、识别策略、复习队列。
        <br>索引不进首屏、搜索在服务端做、一次只画 ${LIB.per} 行，所以几万条也不会卡。</div>

      <div class="form-grid">
        <div class="field"><label>你平时用哪个文献管理器</label>
          <div class="pill-select" data-pill="libMgr">
            ${LIB.managers.map(m => `<button type="button" data-v="${m.v}" class="${mgr === m.v ? "on" : ""}">${m.t}</button>`).join("")}
          </div><input type="hidden" id="f_libMgr" value="${esc(mgr)}">
          <div class="hint">决定每行「打开」按钮往哪跳。选 Zotero 才会出现 <code>zotero://</code> 链接，
            不用的人不会看到一堆必然打不开的死链。</div></div>
        <div class="field"><label>导入题录文件</label>
          <input type="file" id="libFile" accept=".bib,.bibtex,.ris,.json,.nbib,.txt">
          <div class="hint">支持 .bib（BibTeX）· .ris（EndNote / Web of Science / 知网）·
            .json（CSL-JSON）· .nbib（PubMed）。格式认不出来会自己猜。</div></div>
        <div class="field wide"><label>或者直接指一个文件夹</label>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <input id="libFolder" style="flex:1;min-width:240px"
              placeholder="例如 ${esc((S.device.paper_root || "/Users/你/Documents/0PhD"))}/文献">
            <button class="btn" id="libScan">先看看有什么</button>
            <button class="btn primary" id="libScanApply">扫描并导入</button>
          </div>
          <div class="hint">把文件夹里的 <b>.bib / .ris / .nbib / CSL-JSON</b> 和 <b>PDF</b> 一起收进来
            —— Overleaf 项目旁边那个 ref.bib、下载的一堆 PDF，不用再一个个挑。
            子目录也会一起扫。同一篇在多处出现会自动合并，<b>以 Zotero 的信息为准</b>。</div>
          ${(S.config.lib_folders || []).length ? `<div style="margin-top:7px;display:flex;gap:6px;flex-wrap:wrap">
            ${(S.config.lib_folders || []).map(f => `<span class="badge" title="${esc(f)}">📁 ${esc(f.split("/").filter(Boolean).pop() || f)}
              <button class="lnk" data-rescan="${esc(f)}" title="重新扫这个文件夹">↻</button>
              <button class="lnk" data-libfrm="${esc(f)}" title="不再记住这个文件夹">✕</button></span>`).join("")}
          </div>` : ""}</div>
      </div>
      <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:10px">
        <button class="btn primary" id="libImport">导入这个文件</button>
        <button class="btn" id="libZotero">从 Zotero 直接拉</button>
        <button class="btn" id="libMirror" title="以 Zotero 为准全量对齐：你在 Zotero 里删掉的，这边也删掉">镜像同步</button>
        <a class="btn" href="/api/library/export" download="library.bib">导出成 .bib</a>
        <span class="spacer"></span>
        <button class="btn ghost danger" id="libClear">清空索引</button>
      </div>
      <div id="libOut" class="small" style="margin-top:9px"></div>

      <div style="display:flex;gap:7px;align-items:center;margin:13px 0 8px;flex-wrap:wrap">
        <input id="libQ" placeholder="搜标题、作者、期刊、年份、citekey、DOI…" value="${esc(LIB.q)}"
          style="flex:1;min-width:220px">
        <label class="tiny" style="display:flex;align-items:center;gap:4px;white-space:nowrap"
          title="从 PDF 抠出来的条目元数据常常不全。勾上只看这些，集中补一次。">
          <input type="checkbox" id="libTodo"${LIB.todo ? " checked" : ""}> 只看待补全</label>
        <select id="libSort" style="width:auto">
          <option value="year"${LIB.sort === "year" ? " selected" : ""}>按年份</option>
          <option value="added"${LIB.sort === "added" ? " selected" : ""}>按导入时间</option>
          <option value="title"${LIB.sort === "title" ? " selected" : ""}>按标题</option>
        </select>
        <button class="btn sm" id="libPrev">上一页</button>
        <span class="small muted" id="libPage"></span>
        <button class="btn sm" id="libNext">下一页</button>
      </div>
      <div id="libList"><div class="empty">加载中…</div></div>`,
      { icon: "🗂", defaultOpen: !!n });
  },

  bind() {
    const q = $("#libQ");
    if (!q) return;                     // 不在这一页

    q.oninput = () => {
      /* 防抖：不防的话打「liquidity」会发九次请求、重画九次 */
      clearTimeout(LIB._timer);
      LIB._timer = setTimeout(() => { LIB.q = q.value; LIB.page = 0; LIB.load(); }, 250);
    };
    const st = $("#libSort");
    if (st) st.onchange = () => { LIB.sort = st.value; LIB.page = 0; LIB.load(); };
    const pv = $("#libPrev");
    if (pv) pv.onclick = () => { if (LIB.page > 0) { LIB.page--; LIB.load(); } };
    const nx = $("#libNext");
    if (nx) nx.onclick = () => {
      if ((LIB.page + 1) * LIB.per < LIB.total) { LIB.page++; LIB.load(); }
    };

    const mg = $("[data-pill=\"libMgr\"]");
    if (mg) $$("button", mg).forEach(b => b.addEventListener("click", async () => {
      await saveConfig({ reading: Object.assign({}, S.config.reading, { manager: b.dataset.v }) });
      LIB.load();
      toast("已记住，跳转方式跟着变");
    }));

    const imp = $("#libImport");
    if (imp) imp.onclick = () => LIB.doImport();
    const zt = $("#libZotero");
    if (zt) zt.onclick = () => LIB.doZotero(false);
    const mi = $("#libMirror");
    if (mi) mi.onclick = () => {
      if (!confirm("镜像同步会以 Zotero 为准：\n\n"
        + "· 你在 Zotero 里删掉的条目，这边也会删掉\n"
        + "· 手工导入的 .bib / .ris 条目不受影响\n\n"
        + "普通「直接拉」只加不减，删掉的会留成僵尸条目。继续？")) return;
      LIB.doZotero(true);
    };
    const cl = $("#libClear");
    if (cl) cl.onclick = () => LIB.doClear();

    const td = $("#libTodo");
    if (td) td.onchange = () => { LIB.todo = td.checked; LIB.page = 0; LIB.load(); };
    const sc = $("#libScan");
    if (sc) sc.onclick = () => LIB.doScan($("#libFolder").value.trim(), false);
    const sa = $("#libScanApply");
    if (sa) sa.onclick = () => LIB.doScan($("#libFolder").value.trim(), true);
    $$("[data-rescan]").forEach(b => b.onclick = () => LIB.doScan(b.dataset.rescan, true));
    $$("[data-libfrm]").forEach(b => b.onclick = async () => {
      const r = await API.post("library/folder/forget", { path: b.dataset.libfrm });
      S.config.lib_folders = r.folders || [];
      render();
      toast("不再记住这个文件夹（已导入的条目不受影响）");
    });

    LIB.load();
  },

  /* 扫一个文件夹。默认只看不导 —— 指错目录的代价应该是「白等几秒」，
     而不是「索引里凭空多出两千条不相干的东西」。 */
  async doScan(path, apply) {
    if (!path) { LIB.out("先填一个文件夹路径。"); return; }
    LIB.out(apply ? "正在扫描并导入…（PDF 多的话要几十秒）" : "正在扫描…（只看不导）");
    try {
      const r = await API.post("library/scan", { path, apply: !!apply });
      if (!r.ok) { LIB.out(`<span style="color:var(--red)">${esc(r.detail || "扫描失败")}</span>`); return; }
      const c = r.counts || {};
      const head = `扫到 <b>${r.found}</b> 条：题录文件 ${c.bib || 0} 条、PDF ${c.pdf || 0} 篇`
        + (r.todo ? ` · 其中 <b>${r.todo}</b> 条元数据不全，已标「待补全」` : "")
        + `（用时 ${r.ms} ms）`;
      const warn = (r.capped ? `<div class="tiny" style="color:var(--amber)">这个目录太大，只扫了一部分 —— 建议指到更具体的文件夹。</div>` : "")
        + (r.error_count ? `<div class="tiny muted">有 ${r.error_count} 个文件读不了或解析失败，已跳过。</div>` : "");
      if (!apply) {
        LIB.out(head + `<div class="tiny muted" style="margin-top:5px">还没有写进索引。确认没问题就点「扫描并导入」。</div>`
          + warn
          + (r.preview || []).map(x => `<div class="tiny">· ${esc(String(x.t || "").slice(0, 70))}
              <span class="muted">${x.y || ""} · ${esc(x.s || "")}${x.todo ? " · 待补全：" + esc(x.todo) : ""}</span></div>`).join("")
          + ((r.found || 0) > 20 ? `<div class="tiny muted">…只列了前 20 条。</div>` : ""));
        return;
      }
      LIB.out(head + `<br>新增 <b>${r.added}</b>、补全已有 ${r.updated}、跳过 ${r.skipped}，现在共 ${r.total} 条。`
        + `<span class="muted">同一篇在多处出现的已经合并，以 Zotero 的信息为准。</span>` + warn);
      S.libraryCount = r.total;
      if (!(S.config.lib_folders || []).includes(r.folder)) {
        S.config.lib_folders = (S.config.lib_folders || []).concat([r.folder]);
      }
      LIB.page = 0; LIB.load();
    } catch (e) {
      LIB.out(`<span style="color:var(--red)">扫描失败：${esc(String(e.message || e))}</span>`);
    }
  },

  out(html) { const o = $("#libOut"); if (o) o.innerHTML = html; },

  async load() {
    const host = $("#libList");
    if (!host || LIB.loading) return;
    LIB.loading = true;
    try {
      const p = new URLSearchParams({
        q: LIB.q, limit: LIB.per, offset: LIB.page * LIB.per, sort: LIB.sort,
      });
      if (LIB.todo) p.set("todo", "1");
      const d = await API.get("library/search?" + p.toString());
      LIB.total = d.total || 0;
      LIB.paint(d);
    } catch (e) {
      host.innerHTML = `<div class="empty">读不出索引：${esc(String(e.message || e))}</div>`;
    } finally { LIB.loading = false; }
  },

  paint(d) {
    const host = $("#libList");
    if (!host) return;
    const items = d.items || [];
    const pg = $("#libPage");
    if (pg) {
      pg.textContent = LIB.total
        ? `第 ${LIB.page * LIB.per + 1}–${Math.min((LIB.page + 1) * LIB.per, LIB.total)} 条 / 共 ${LIB.total}`
        : "";
    }
    if (!items.length) {
      host.innerHTML = `<div class="empty">${LIB.todo ? "没有待补全的条目 —— 元数据都齐了。"
        : (LIB.q ? "没搜到。换个词试试。"
          : "索引是空的。上面选个 .bib / .ris 文件导进来，指一个文件夹扫，或者从 Zotero 直接拉。")}</div>`;
      return;
    }
    /* 一次最多 50 行；每行 DOM 尽量薄，别塞摘要之类的大段文字 */
    host.innerHTML = items.map(it => {
      const meta = [
        [].concat(it.a || []).slice(0, 4).join("; ") + ((it.a || []).length > 4 ? " 等" : ""),
        it.y || "", it.j || "",
      ].filter(Boolean).map(esc).join(" · ");
      const jumps = (it.open || []).map(o =>
        `<a class="btn sm" href="${esc(o.url)}" ${o.url.startsWith("http") ? 'target="_blank" rel="noopener"' : ""}
           title="${esc(o.label)}">${o.icon}</a>`).join("");
      return `<div class="row-line">
        <div class="rl-main">
          <div class="rl-title">${esc(it.t || "（无题）")}${
        it.todo ? `<span class="badge a" title="从 PDF 里抠出来的元数据不全：${esc(it.todo)}。点「编辑」补上，或者到 Zotero 里补好再同步一次。">待补全</span>` : ""}${
        (it.srcs || []).length > 1 ? `<span class="badge" title="这一篇在这些地方都出现过：${esc((it.srcs || []).join("、"))}">${(it.srcs || []).length} 处</span>` : ""}</div>
          <div class="rl-meta">${meta}${it.c ? ` · <code>${esc(it.c)}</code>` : ""}${
        it.todo ? ` · <span style="color:var(--amber)">缺 ${esc(it.todo)}</span>` : ""}</div>
        </div>
        <div class="rl-acts">${jumps}
          ${it.c ? `<button class="btn sm ghost" data-cite="${esc(it.c)}" title="复制 \\cite{${esc(it.c)}}">cite</button>` : ""}
          <button class="btn sm ghost" data-merge="${esc(it.k)}" title="这条和另一条是同一篇（工作论文 / 正式发表版）">合并</button>
          <button class="btn sm" data-promote="${esc(it.k)}" title="挪进精读笔记，开始记研究问题、方法、结论">提升</button>
        </div></div>`;
    }).join("");

    $$("[data-promote]", host).forEach(b => b.onclick = async () => {
      b.disabled = true;
      try {
        const r = await API.post("library/promote", { key: b.dataset.promote });
        if (!r.ok) { toast(r.detail || "提升失败"); b.disabled = false; return; }
        toast(r.already ? "这篇已经在精读笔记里了" : "已加进精读笔记，去下面填研究问题");
        await reload();
        render();
      } catch (e) { toast("提升失败：" + (e.message || e)); b.disabled = false; }
    });
    $$("[data-merge]", host).forEach(b => b.onclick = () => {
      if (!LIB._mergeFrom) {
        LIB._mergeFrom = b.dataset.merge;
        b.textContent = "选另一条…";
        toast("再点另一条的「合并」。保留先点的这条，把后点那条的字段补过来。");
        return;
      }
      if (LIB._mergeFrom === b.dataset.merge) { LIB._mergeFrom = null; LIB.load(); return; }
      const keep = LIB._mergeFrom, drop = b.dataset.merge;
      LIB._mergeFrom = null;
      if (!confirm("把这两条合并成一条？\n\n工作论文和它正式发表的版本常被认成两篇——\n"
        + "无 DOI 时是按「标题+年份」去重的，年份一变就分家了。\n\n"
        + "保留先选的那条，后选的字段补过去然后删掉。")) { LIB.load(); return; }
      API.post("library/merge", { keep, drop }).then(r => {
        toast(r.ok ? "已合并" : (r.detail || "合并失败"));
        S.libraryCount = r.total || S.libraryCount;
        LIB.load();
      }).catch(e => toast("合并失败：" + (e.message || e)));
    });
    $$("[data-cite]", host).forEach(b => b.onclick = async () => {
      const s = "\\cite{" + b.dataset.cite + "}";
      try { await navigator.clipboard.writeText(s); toast("已复制 " + s); }
      catch (e) { toast("复制不了，手动抄：" + s); }
    });
  },

  async doImport() {
    const f = $("#libFile");
    if (!f || !f.files || !f.files[0]) { LIB.out("先选一个文件。"); return; }
    const file = f.files[0];
    if (file.size > 80 * 1024 * 1024) { LIB.out("文件超过 80MB，太大了。"); return; }
    LIB.out(`正在读 ${esc(file.name)}（${Math.round(file.size / 1024)} KB）…`);
    let text;
    try { text = await file.text(); }
    catch (e) { LIB.out("读不了这个文件：" + esc(String(e.message || e))); return; }
    LIB.out("正在解析并合并…");
    try {
      const r = await API.post("library/import", { text, filename: file.name });
      if (!r.ok) { LIB.out(`<span style="color:var(--red)">${esc(r.detail || "导入失败")}</span>`); return; }
      LIB.out(`按 <b>${esc(r.format)}</b> 解析出 ${r.parsed} 条：新增 <b>${r.added}</b>、
        补全已有 ${r.updated}、跳过 ${r.skipped}，现在共 ${r.total} 条（用时 ${r.ms} ms）。
        <span class="muted">重复的按 DOI、标题+年份认出来，不会堆两份。</span>`);
      S.libraryCount = r.total;
      LIB.page = 0; LIB.load();
    } catch (e) {
      LIB.out(`<span style="color:var(--red)">导入失败：${esc(String(e.message || e))}</span>`);
    }
  },

  async doZotero(mirror) {
    LIB.out("正在连本机 Zotero…");
    try {
      const s = await API.get("library/zotero/status");
      if (!s.ok) {
        LIB.out(`<span style="color:var(--red)">${esc(s.detail || "连不上")}</span>
          <div class="muted" style="margin-top:5px">连不上也没关系：在 Zotero 里选中文献 →
            右键「导出条目」→ 格式选 BibTeX 或 CSL JSON，存成文件，用上面的「导入这个文件」一样能进来。</div>`);
        return;
      }
      LIB.out(`Zotero 在跑${s.total ? `，看到约 ${s.total} 条` : ""}，正在分批拉取…`);
      let r = await API.post("library/zotero/sync", { mirror: !!mirror });
      /* 镜像会大批删数据，服务端设了两道闸：拉回来是空的、或者要删掉一多半，
         都会先拒绝并把情况说清楚，由你决定要不要坚持。 */
      if (!r.ok && r.refused) {
        const go = confirm(`${r.detail}\n\n确定这就是你要的结果吗？\n`
          + `点确定会真的删掉${r.would_remove ? ` ${r.would_remove} 条` : ""}。`);
        if (!go) { LIB.out(`已取消，索引没有变化。<span class="muted">${esc(r.detail)}</span>`); return; }
        r = await API.post("library/zotero/sync", { mirror: true, force: true });
      }
      if (!r.ok) { LIB.out(`<span style="color:var(--red)">${esc(r.detail || "拉取失败")}</span>`); return; }
      LIB.out(r.mirrored
        ? `镜像完成：拉回 ${r.fetched} 条，删掉 Zotero 里已不存在的 <b>${r.removed || 0}</b> 条，
           现在共 ${r.total} 条（用时 ${Math.round(r.ms / 100) / 10}s）。
           <span class="muted">手工导入的条目没受影响。</span>`
        : `拉回 ${r.fetched} 条（${r.pages} 批）：新增 <b>${r.added}</b>、补全 ${r.updated}，
           现在共 ${r.total} 条（用时 ${Math.round(r.ms / 100) / 10}s）。
           <span class="muted">再点一次只补新增的。Zotero 里删掉的要用「镜像同步」才会跟着删。</span>`);
      S.libraryCount = r.total;
      LIB.page = 0; LIB.load();
    } catch (e) {
      LIB.out(`<span style="color:var(--red)">出错：${esc(String(e.message || e))}</span>`);
    }
  },

  /* 清空整库分两步：先问服务端「这会删多少条」，把真实条数摆到用户面前，
     用户点了确认才带 confirm 再发一次。服务端不带 confirm 一律不动数据，
     所以就算别处（脚本、误触、手机）打到这条路由，也删不掉东西。 */
  async doClear() {
    try {
      const probe = await API.post("library/clear", {});
      if (probe.refused === "confirm") {
        if (!confirm(`清空整个文献索引？这会删掉 ${probe.would_remove} 条题录。\n\n`
          + "只删索引这张表，你的精读笔记和 Zotero 库都不受影响；\n"
          + "索引随时能从 Zotero 或 .bib 重新导进来。")) { LIB.out("已取消，没有动任何数据。"); return; }
        const r = await API.post("library/clear", { confirm: true });
        LIB.out(`已清空 ${r.removed} 条。`);
      } else {
        LIB.out(`已清空 ${probe.removed || 0} 条。`);
      }
      S.libraryCount = 0; LIB.page = 0; LIB.load();
    } catch (e) { LIB.out("清空失败：" + esc(String(e.message || e))); }
  },
};

window.LIB = LIB;
