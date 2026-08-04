/* 学术生产总起：一屏看清所有项目 + 论文 PDF 库 */

VIEWS.hub = () => {
  const ms = rows("manuscripts");
  const active = ms.filter(m => !["published", "shelved"].includes(m.stage));
  const pub = rows("published");
  const byStage = {};
  STAGES.forEach(s => byStage[s.v] = ms.filter(m => m.stage === s.v));
  const noSubmission = !ms.some(m => (m.timeline || []).some(e => e.event === "submitted"));

  const tut = UI.tut("hub", "学术生产总起怎么用", `
    <p>这一页是<b>入口</b>：所有在做的项目一屏看清，点任意一张卡进入它的<b>专属页面</b>（时间线、图表、附件、Overleaf 链接都在里面）。</p>
    <p>下半部分是<b>论文 PDF 库</b>：把你存论文的文件夹加进来，系统会自动读出每个 PDF 的标题、作者、年份
    （优先读元数据，读不到就按首页最大字号识别，再不行才用文件名），你可以一键把它加进阅读清单。<b>这一步不花 AI 额度</b>。</p>
    ${noSubmission ? `<p><b>你还没有投过稿</b>——这很正常。在投稿之前，这里显示的是「离投出去还差什么」；
      等你记下第一条投稿事件，期刊周期、催稿提醒、复盘统计会自动开始工作。</p>` : ""}`);

  const stats = `<div class="grid g4" style="margin-bottom:14px">
    <div class="stat"><div class="k">进行中项目</div><div class="v">${active.length}</div>
      <div class="d">${STAGES.filter(s => byStage[s.v].length && !["published","shelved"].includes(s.v))
        .map(s => s.t + " " + byStage[s.v].length).join(" · ") || "—"}</div></div>
    <div class="stat"><div class="k">论文库</div><div class="v">${pub.length}</div><div class="d">已发表 / 已归档</div></div>
    <div class="stat"><div class="k">阅读清单</div><div class="v">${rows("reading").length}</div>
      <div class="d">读完 ${rows("reading").filter(r => r.status === "done").length}</div></div>
    <div class="stat"><div class="k">本地 PDF</div>
      <div class="v">${S.pdfLib ? S.pdfLib.length : "—"}</div>
      <div class="d">${S.pdfLib
        ? `本次扫描 · 已登记 ${(S.config.pdf_folders || []).length} 个文件夹`
        : `已登记 ${(S.config.pdf_folders || []).length} 个文件夹 · 扫一下才知道多少篇`}</div></div>
  </div>`;

  const projCards = active.length ? `<div class="grid g2">` + active.map(m => {
    const rev = msInReviewDays(m);
    const stale = (msDaysSinceUpdate(m) || 0) >= (S.config.stale_manuscript_days || 7);
    const tl = (m.timeline || []).length;
    return `<div class="proj" data-open="${m.id}">
      <div class="proj-h">
        <span class="badge ${m.stage === "rnr" ? "a" : m.stage === "accepted" ? "g" : "b"}">${STAGE_T[m.stage] || ""}</span>
        <b>${esc(m.title || "（未命名）")}</b>
        ${stale ? `<span class="badge a">停滞 ${msDaysSinceUpdate(m)} 天</span>` : ""}
      </div>
      ${UI.prog(m.progress, `data-prog-coll="manuscripts" data-prog-id="${m.id}"`)}
      <div class="proj-m">
        ${m.next_action ? `下一步：${esc(m.next_action)}` : `<span style="color:var(--amber)">还没写下一步</span>`}
        ${m.next_action_due ? daysChip(daysUntil(m.next_action_due)) : ""}
      </div>
      <div class="proj-f">
        <span>${tl} 条事件</span>
        ${rev ? `<span>· 在 ${esc(m.current_journal || "")} 审了 ${rev.days} 天</span>`
              : (m.target_journal ? `<span>· 目标 ${esc(m.target_journal)}</span>` : "")}
        <span class="spacer"></span>
        ${m.overleaf ? `<a href="${esc(m.overleaf)}" target="_blank" class="mini-link" onclick="event.stopPropagation()">Overleaf ↗</a>` : ""}
        <button class="btn sm" onclick="event.stopPropagation()" data-open2="${m.id}">打开 →</button>
      </div>
    </div>`;
  }).join("") + `</div>` : `<div class="empty">还没有进行中的项目。点右上角「＋ 新项目」开始，或从「想法」里把一条升级成项目。</div>`;

  /* S.pdfLib 只存**这次**扫描的结果，刷新页面就没了，
     而 pdf_folders 是存在配置里、会一直累积的。
     两个数字并排放着，很容易被读成「3 个文件夹里一共 0 篇」——
     其实只是还没扫。没扫过就说「还没扫」，别报一个 0。 */
  const pdfCard = UI.card("hub-pdf", "论文 PDF 库",
    S.pdfLib ? `本次扫到 ${S.pdfLib.length} 篇` : "还没扫描", `
    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:9px">
      <input id="pdfPath" class="search" style="flex:1;min-width:220px"
        placeholder="粘贴一个存论文的文件夹路径，例如 ${esc((S.device.paper_root || "/Users/你/Documents/0PhD"))}/文献">
      <button class="btn primary sm" id="pdfScan">扫描</button>
      ${(S.config.pdf_folders || []).map((f, i) => `<span class="badge">${esc(f.split("/").pop())}
        <button class="lnk" data-pdfrm="${i}">✕</button></span>`).join("")}
    </div>
    <div id="pdfOut">${pdfTable()}</div>`, { icon: "📚" });

  /* 稿件库并进来：同一件事不该分两页 */
  const msPart = (typeof manuscriptSections === "function") ? manuscriptSections() : { kanban: "", cards: "" };
  const jrPart = (typeof journalStatsCard === "function") ? journalStatsCard() : "";

  return `<div class="page-head"><h1>📊 研究</h1>
    <div class="sub">选题 → 写作 → 投稿 → 审稿 → 转投 → 发表 · 点项目卡进专属页面</div>
    <span class="spacer"></span>
    <button class="btn" data-new="published">＋ 已发表</button>
    <button class="btn primary" data-new="manuscripts">＋ 新项目</button></div>
    ${tut}${stats}
    ${UI.card("hub-proj", "进行中的项目", `${active.length} 个`, projCards,
      { icon: "📄", actions: sampleBtn(["manuscripts"]) })}
    ${msPart.kanban}
    ${UI.card("hub-mslist", "全部稿件", `${ms.length} 篇`, msPart.cards ||
      `<div class="empty">还没有稿件，点右上角新建。</div>`, { icon: "🗃", defaultOpen: false })}
    ${jrPart}
    ${pdfCard}`;
};

function pdfTable() {
  const lib = S.pdfLib || [];
  if (!lib.length) return `<div class="empty">还没扫描。把存论文的文件夹路径贴上去，点「扫描」。</div>`;
  // 用 rowsAll 而不是 rows：判断「这篇是不是已经在清单里」跟「要不要显示示例」
  // 没有关系。用过滤后的那份，会把跟隐藏示例同名的 PDF 当成新的，一点就多出一条重复。
  const known = new Set(rowsAll("reading").map(r => (r.title || "").toLowerCase().slice(0, 50)));
  return `<div class="scroll-x"><table class="tbl">
    <tr><th>标题</th><th>年份</th><th>识别方式</th><th></th></tr>
    ${lib.slice(0, 200).map((p, i) => {
      const dup = known.has((p.title || "").toLowerCase().slice(0, 50));
      return `<tr>
        <td><b>${esc(p.title || p.file)}</b>
          ${p.authors ? `<div class="tiny muted">${esc(p.authors)}</div>` : ""}
          <div class="tiny muted">${esc(p.file)}</div></td>
        <td class="small">${esc(p.year || "")}</td>
        <td><span class="badge ${p.source === "元数据" ? "g" : p.source === "首页排版" ? "b" : ""}">${esc(p.source || "")}</span></td>
        <td style="white-space:nowrap">
          <button class="btn sm" data-pdfopen="${i}">打开</button>
          ${dup ? `<span class="badge g">已在清单</span>`
                : `<button class="btn sm primary" data-pdfadd="${i}">加入阅读</button>`}</td>
      </tr>`;
    }).join("")}
  </table></div>${lib.length > 200 ? `<div class="tiny muted">仅显示前 200 篇</div>` : ""}`;
}

/* ------------------------------------------------- 稿件专属子页面 */
VIEWS.project = () => {
  if (!S.projectId && /^project\//.test(location.hash.replace("#", ""))) {
    S.projectId = decodeURIComponent(location.hash.replace("#", "").slice(8));
  }
  const m = byId("manuscripts", S.projectId);
  if (!m) return `<div class="empty">找不到这个项目 · <button class="btn sm" data-go="hub">返回</button></div>`;
  const rev = msInReviewDays(m);
  const exp = journalExperience(m.current_journal);
  const tl = (m.timeline || []).slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const elapsed = tl.length ? daysBetween(tl[tl.length - 1].date, todayStr()) : null;

  return `<div class="page-head">
    <button class="btn ghost" data-go="hub">← 学术生产</button>
    <h1 style="font-size:18px">${esc(m.title || "（未命名）")}</h1>
    <span class="spacer"></span>
    <button class="btn" data-event="${m.id}">＋ 记录事件</button>
    <button class="btn" data-ai="manuscripts:${m.id}">🤖 问 AI</button>
    <button class="btn" data-edit="manuscripts:${m.id}">编辑</button></div>

  ${UI.card("pj-status", "状态", "", `
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
      ${UI.seg(STAGES, m.stage, "manuscripts", m.id, "stage")}
      <div style="flex:1;min-width:180px">${UI.prog(m.progress, `data-prog-coll="manuscripts" data-prog-id="${m.id}"`)}</div>
    </div>
    <div class="grid g3">
      <div class="mini-stat"><div class="k">下一步</div><div class="v2">${esc(m.next_action || "—")}</div>
        <div class="d">${m.next_action_due ? esc(m.next_action_due) + " " + daysChip(daysUntil(m.next_action_due)).replace(/<[^>]+>/g, "") : "没设截止"}</div></div>
      <div class="mini-stat"><div class="k">当前状态</div>
        <div class="v2">${rev ? `在 ${esc(m.current_journal || "")} 审稿` : (m.target_journal ? `准备投 ${esc(m.target_journal)}` : "尚未定目标")}</div>
        <div class="d">${rev ? `已 ${rev.days} 天${exp ? "，你在这家的历史均值 " + exp.avg + " 天" : ""}` : "还没投出去"}</div></div>
      <div class="mini-stat"><div class="k">总耗时</div><div class="v2">${elapsed != null ? elapsed + " 天" : "—"}</div>
        <div class="d">${tl.length} 条事件</div></div>
    </div>
    ${m.overleaf || m.folder || m.repo ? `<div class="hr"></div><div style="display:flex;gap:7px;flex-wrap:wrap">
      ${m.overleaf ? `<a class="btn sm" href="${esc(m.overleaf)}" target="_blank">📝 Overleaf ↗</a>` : ""}
      ${m.repo ? `<a class="btn sm" href="${esc(m.repo)}" target="_blank">💻 代码仓库 ↗</a>` : ""}
      ${m.folder ? `<button class="btn sm" data-openfolder="${esc(resolveFolder(m.folder))}">📁 本地文件夹</button>` : ""}
    </div>` : `<div class="hr"></div><div class="tiny muted">还没关联 Overleaf 或本地文件夹 —— 点「编辑」补上，之后就能一键跳转。</div>`}
  `, { icon: "📌" })}

  ${UI.card("pj-timeline", "生命周期", `${tl.length} 条`, tl.length ? `<div class="tl">${tl.map(ev => `
    <div class="tl-item ${NEG.includes(ev.event) ? "neg" : POS.includes(ev.event) ? "pos" : ""}">
      <div class="d">${esc(ev.date || "")}</div>
      <div class="e">${esc(EVENT_T[ev.event] || ev.event || "")}${ev.journal ? ` <span class="badge">${esc(ev.journal)}</span>` : ""}</div>
      ${ev.note ? `<div class="n">${esc(ev.note)}</div>` : ""}</div>`).join("")}</div>`
    : `<div class="empty">还没有事件。点右上角「＋ 记录事件」记下第一条（比如「启动」）。<br>
       <span class="tiny">从记下投稿事件那一刻起，期刊周期、催稿提醒、复盘统计会自动开始工作。</span></div>`, { icon: "🕰" })}

  ${m.folder ? UI.card("pj-figs", "结果图表", esc(resolveFolder(m.folder)),
    `<div data-figs="${m.id}" data-folder="${esc(m.folder)}"><div class="empty">扫描中…</div></div>`, { icon: "📊" }) : ""}

  ${UI.card("pj-notes", "笔记", "", `
    <textarea id="pjBody" data-full="${m._body_more ? "0" : "1"}"
      ${m._body_more ? "disabled" : ""}
      style="width:100%;min-height:160px;border:1px solid var(--line);border-radius:9px;padding:10px;background:var(--bg)">${esc(m.body || "")}</textarea>
    <div class="tiny muted" style="margin-top:4px" id="pjBodyHint">${m._body_more
      ? "正在取完整笔记…" : "自动保存"}</div>`, { icon: "🗒" })}`;
};

window.bindHubExtras = function () {
  $$("[data-open],[data-open2]").forEach(el => el.onclick = e => {
    e.stopPropagation();
    S.projectId = el.dataset.open || el.dataset.open2;
    go("project");
  });
  /* 笔记框里必须是**完整**正文。
     首屏只带 160 字预览（带 _body_more 标记），要是直接把预览渲进 textarea：
     用户敲第一个字 → saveRec 那道网发现标记，悄悄用磁盘上的全文替换掉这次输入
     （这一击键就没了）；敲第二个字时标记已经没了，于是 160 字连同新输入
     被当作全文写回去 —— 剩下的两千多字永久消失，不报错、不提示。
     所以：没拿到全文之前，框子先禁用，取回来再放开。 */
  const pb = $("#pjBody");
  if (pb) {
    const arm = () => {
      pb.disabled = false;
      const h = $("#pjBodyHint"); if (h) h.textContent = "自动保存";
      /* 把 id 在**绑定时**就固定下来，不要到触发时才去读 S.projectId。
         debounce 有 800ms 延迟，这中间用户完全可能已经切到别的项目了 ——
         那样这次保存就会把 A 的笔记写进 B。 */
      const pid = S.projectId;
      pb.oninput = debounce(() => {
        if (!document.body.contains(pb)) return;      // 已经换页，别再写
        patchRec("manuscripts", pid, { body: pb.value });
      }, 800);
    };
    if (pb.dataset.full === "1") { arm(); }
    else {
      ensureFull("manuscripts", S.projectId).then(fresh => {
        if ($("#pjBody") !== pb) return;                 // 期间换页了
        pb.value = (fresh && fresh.body) || "";
        arm();
      }).catch(() => {
        const h = $("#pjBodyHint");
        if (h) h.textContent = "连不上服务端，取不到完整笔记 —— 先不让编辑，免得把正文截断存回去。";
      });
    }
  }
  const ps = $("#pdfScan");
  if (ps) ps.onclick = async () => {
    const path = $("#pdfPath").value.trim();
    if (!path) return toast("先填一个文件夹路径");
    $("#pdfOut").innerHTML = `<div class="empty">扫描中…（PDF 多的话要几秒）</div>`;
    const r = await API.get("scan/pdfs?path=" + encodeURIComponent(path));
    if (!r.ok) { $("#pdfOut").innerHTML = `<div class="wz-result bad" style="display:block">${esc(r.detail)}</div>`; return; }
    S.pdfLib = (r.items || []).filter(x => x.ok);
    const folders = (S.config.pdf_folders || []).slice();
    if (!folders.includes(path)) { folders.push(path); await saveConfig({ pdf_folders: folders }); }
    render();
    toast(`扫描到 ${S.pdfLib.length} 篇`);
  };
  $$("[data-pdfrm]").forEach(b => b.onclick = async () => {
    const f = (S.config.pdf_folders || []).slice(); f.splice(Number(b.dataset.pdfrm), 1);
    await saveConfig({ pdf_folders: f }); render();
  });
  $$("[data-pdfopen]").forEach(b => b.onclick = () => {
    const p = (S.pdfLib || [])[Number(b.dataset.pdfopen)];
    if (p) window.open("/api/file?path=" + encodeURIComponent(p.path), "_blank");
  });
  $$("[data-pdfadd]").forEach(b => b.onclick = async () => {
    const p = (S.pdfLib || [])[Number(b.dataset.pdfadd)];
    if (!p) return;
    await saveRec("reading", {
      title: p.title, authors: p.authors ? [p.authors] : [], year: p.year ? Number(p.year) : null,
      status: "to-read", level: "skim", link: "", pdf: p.path,
      body: p.snippet ? "首页片段：" + p.snippet : "",
    });
    render(); renderNav(); toast("已加入阅读清单");
  });
  $$("[data-openfolder]").forEach(b => b.onclick = () =>
    window.open("/api/file?path=" + encodeURIComponent(b.dataset.openfolder), "_blank"));
};
