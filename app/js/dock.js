/* 右下角速记 dock：想法/灵感 · 完成记录 · 待分类
   完成记录会同步进日程（补记那些"做了才想起来"的事）。 */

const DOCK = {
  tab: "note",
  open: false,

  TABS: [
    { v: "note", t: "💭 想法·灵感", ph: "现在想记点什么？想法、灵感、疑问都往这儿丢…" },
    { v: "done", t: "✅ 完成记录", ph: "刚做完什么？「改完了 Table 5」「跟合作者开了一小时会」…" },
    { v: "todo", t: "📥 待分类", ph: "拿不准归到哪儿的，先扔这里，攒够了一起处理" },
  ],

  mount() {
    if (!$("#dock")) {
      document.body.insertAdjacentHTML("beforeend", `
        <div class="dock" id="dock">
          <div class="dock-box hide" id="dockBox"></div>
          <div class="dock-pill" id="dockPill">💭 现在想记点什么？<span class="dock-badge" id="dockBadge" hidden></span></div>
        </div>`);
      $("#dockPill").onclick = () => DOCK.toggle();
    }
    DOCK.relocate();
    DOCK.updateBadge();
  },

  /* 宽屏时把速记搬进右栏；窄屏搬回右下角浮动 */
  relocate() {
    const host = $("#memoHost");
    const dock = $("#dock"), box = $("#dockBox"), pill = $("#dockPill");
    if (!dock || !box) return;
    if (host) {
      if (box.parentElement !== host) host.appendChild(box);
      box.classList.remove("hide");
      box.classList.add("in-rail");
      dock.style.display = "none";
      DOCK.open = true;
    } else {
      if (box.parentElement !== dock) dock.insertBefore(box, pill);
      box.classList.remove("in-rail");
      box.classList.toggle("hide", !DOCK.open);
      const dd = $("#dock"); if (dd) dd.classList.toggle("open", DOCK.open);
      dock.style.display = "";
    }
    DOCK.renderBox();
  },

  toggle(force) {
    if ($("#memoHost")) {          // 已在右栏里常驻，无需开关
      const t = $("#dockInput"); if (t) t.focus();
      return;
    }
    DOCK.open = force == null ? !DOCK.open : force;
    $("#dockBox").classList.toggle("hide", !DOCK.open);
    const d = $("#dock"); if (d) d.classList.toggle("open", DOCK.open);   // 手机上靠它变抽屉
    if (DOCK.open) { DOCK.renderBox(); setTimeout(() => { const t = $("#dockInput"); if (t) t.focus(); }, 60); }
  },

  /* 三个 tab 的数据来源 */
  items(tab) {
    if (tab === "note") {
      return rows("ideas").filter(r => r.source !== "unsorted")
        .slice().sort((a, b) => String(b.created || "").localeCompare(String(a.created || ""))).slice(0, 40);
    }
    if (tab === "done") {
      return rows("schedule").filter(r => r.done && r.logged)
        .slice().sort((a, b) => String(b.created || "").localeCompare(String(a.created || ""))).slice(0, 40);
    }
    return rows("ideas").filter(r => r.source === "unsorted")
      .slice().sort((a, b) => String(b.created || "").localeCompare(String(a.created || "")));
  },

  /* 需要人工/AI 处理的总量：待分类 + 等你粘回答的报告 + 未读 AI 产出 + 体检待处理 */
  pendingCount() {
    const unsorted = rows("ideas").filter(r => r.source === "unsorted").length;
    const reports = rows("reports").filter(r => r.status === "waiting" || r.status === "unread").length;
    const audits = (S.auditOpen || 0);
    return { unsorted, reports, audits, total: unsorted + reports + audits };
  },

  updateBadge() {
    const p = DOCK.pendingCount();
    [$("#dockBadge"), $("#dockBadgeRail")].forEach(el => {
      if (!el) return;
      el.hidden = p.total === 0;
      el.textContent = p.total;
      el.className = "dock-badge" + (p.total >= (S.config.pending_threshold || 10) ? " hot" : "");
    });
    // 超阈值 → 推送一次（每天最多一次，避免骚扰）
    if (p.total >= (S.config.pending_threshold || 10)) DOCK.maybeNotify(p);
  },

  async maybeNotify(p) {
    const key = "pending-notified-" + todayStr();
    if (S.config[key]) return;
    await saveConfig({ [key]: true });
    const md = `### 待处理事项已达 ${p.total} 条\n\n` +
      `- 待分类速记：${p.unsorted}\n- 等你处理的 AI 产出：${p.reports}\n- 体检待办：${p.audits}\n\n` +
      `> 打开工作台右下角「📥 待分类」批量处理一下吧。`;
    try {
      await API.post("push/send", { title: "工作台 · 待处理已达 " + p.total + " 条", markdown: md });
      toast("待处理已达 " + p.total + " 条，已推送提醒你");
    } catch (e) {
      toast("待处理已达 " + p.total + " 条，记得处理");
    }
  },

  renderBox() {
    const box = $("#dockBox"); if (!box) return;
    /* renderBox 会把整个面板的 innerHTML 换掉，**包括你正在打字的那个 textarea**。
       而它不只在切页签时被调用：改窗口大小、插拔外接屏、手机弹出键盘，
       都会经 RAIL.onResize → DOCK.relocate 走到这里。
       原来只有切页签那条路径记得存草稿，于是「窗口拖一下，写了一半的想法没了」——
       不报错、不进任何存储，就是没了。所以在这一层统一存、统一恢复。 */
    const _live = $("#dockInput");
    if (_live && _live.value) {
      DOCK.draft = DOCK.draft || {};
      DOCK.draft[DOCK.tab] = _live.value;
    }
    const tab = DOCK.TABS.find(t => t.v === DOCK.tab) || DOCK.TABS[0];
    const list = DOCK.items(DOCK.tab);
    const p = DOCK.pendingCount();
    box.innerHTML = `
      <div class="dock-h">
        <div class="dock-tabs">
          ${DOCK.TABS.map(t => {
            const n = DOCK.items(t.v).length;
            return `<button class="${t.v === DOCK.tab ? "on" : ""}" data-dtab="${t.v}">${t.t}${n ? `<i>${n}</i>` : ""}</button>`;
          }).join("")}
        </div>
        <span class="spacer"></span>
        ${$("#memoHost") ? "" : `<button class="icon-btn" id="dockMin" title="收起">—</button>`}
      </div>
      ${DOCK.tab === "todo" && p.total >= (S.config.pending_threshold || 10)
        ? `<div class="dock-warn">⚠️ 全站待处理已 ${p.total} 条（待分类 ${p.unsorted} · AI 产出 ${p.reports} · 体检 ${p.audits}），建议现在清一批</div>` : ""}
      <div class="dock-body" id="dockBody">
        ${list.length ? list.map(r => DOCK.bubble(r)).join("") : `<div class="empty" style="padding:24px 8px">${DOCK.tab === "done" ? "今天还没有完成记录 —— 做完一件事就来记一句" : "还没有内容"}</div>`}
      </div>
      <div class="dock-in">
        <textarea id="dockInput" placeholder="${esc(tab.ph)}"></textarea>
        <div id="dockPrev"></div>
        <div class="dock-row">
          ${DOCK.tab === "note" ? `<div class="tagsel" id="dockTags">
              <button class="on" data-k="idea">想法</button>
              <button data-k="question">疑问</button>
              <button data-k="ref">线索</button>
              <button data-k="link">链接</button></div>`
            : DOCK.tab === "done" ? `<span class="tiny muted">会同时补一条已完成的日程</span>`
            : `<span class="tiny muted">先存着，之后一起分拣</span>`}
          <span class="spacer"></span>
          <button class="btn primary sm" id="dockSave">确定</button>
        </div>
      </div>`;
    // 重画之后把草稿放回去（切页签、改窗口大小、删一条气泡，都会走到这）
    const _back = $("#dockInput");
    if (_back && (DOCK.draft || {})[DOCK.tab]) {
      _back.value = DOCK.draft[DOCK.tab];
      if (DOCK.tab !== "note" && typeof DOCK.preview === "function") {
        try { DOCK.preview(); } catch (e) { }
      }
    }
    $$("[data-dtab]").forEach(b => b.onclick = () => {
      DOCK.tab = b.dataset.dtab;
      DOCK.renderBox();                              // 草稿在 renderBox 里存、也在里面恢复
      const nta = $("#dockInput");
      if (nta) nta.focus();
    });
    if ($("#dockMin")) $("#dockMin").onclick = () => DOCK.toggle(false);
    $("#dockSave").onclick = DOCK.save;
    const ta = $("#dockInput");
    ta.onkeydown = e => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") DOCK.save(); };
    if (DOCK.tab !== "note") ta.oninput = debounce(DOCK.preview, 180);
    $$("#dockTags button").forEach(b => b.onclick = () => {
      $$("#dockTags button").forEach(x => x.classList.remove("on")); b.classList.add("on");
    });
    // 走同一个 sortIdea：它会先把完整正文取回来，
    // 否则手机上记的多行笔记分拣完只剩第一行（原记录还会被删掉）
    $$("[data-dsort]").forEach(b => b.onclick = () => sortIdea(b.dataset.dsort));
    $$("[data-ddel]").forEach(b => b.onclick = async () => {
      await deleteRec("ideas", b.dataset.ddel); DOCK.renderBox(); DOCK.updateBadge(); render();
    });
    $$("[data-dundo]").forEach(b => b.onclick = async () => {
      await patchRec("schedule", b.dataset.dundo, { done: false });
      DOCK.renderBox(); render(); toast("已标回未完成");
    });
  },

  bubble(r) {
    if (DOCK.tab === "done") {
      return `<div class="bub me">${esc(r.title || "")}
        <div class="mt"><span class="badge g" style="margin:0">已完成</span>
          ${esc(String(r.start || "").slice(5))}${r.time ? " " + esc(r.time) : ""}
          ${r.minutes ? ` · ${r.minutes} 分钟` : ""}
          <span class="spacer"></span><button class="lnk" data-dundo="${r.id}">撤销</button></div></div>`;
    }
    if (DOCK.tab === "todo") {
      return `<div class="bub">${esc(r.title || "")}
        <div class="mt">${esc(String(r.created || "").slice(5, 16).replace("T", " "))}
          <span class="spacer"></span>
          <button class="lnk" data-dsort="${r.id}">分拣</button>
          <button class="lnk" data-ddel="${r.id}">删除</button></div></div>`;
    }
    const kindT = { idea: "想法", question: "疑问", ref: "线索", link: "链接" }[r.kind] || "想法";
    return `<div class="bub me">${r.source === "auto" ? "🤖 " : ""}${esc(r.title || "")}
      <div class="mt"><span class="badge v" style="margin:0">${kindT}</span>
        ${esc(String(r.created || "").slice(5, 16).replace("T", " "))}
        ${r.status === "adopted" ? ` · <span style="color:var(--green)">已采纳</span>` : ""}</div></div>`;
  },

  preview() {
    const t = $("#dockInput").value.trim();
    const box = $("#dockPrev"); if (!box) return;
    if (!t) { box.innerHTML = ""; return; }
    if (DOCK.tab === "done") {
      const parsed = CAP.toRecord(t, "auto", new Date());
      const mins = CAP.parseMinutes(t), d = CAP.parseDate(t) || todayStr();
      box.innerHTML = `<div class="dock-prev">记为 <b>${esc(d)}</b> 完成${mins ? ` · ${mins} 分钟` : ""}
        ${parsed.collection !== "schedule" && parsed.collection !== "ideas"
          ? ` · 同时进「${esc(COLL_NAME[parsed.collection] || parsed.collection)}」` : ""}</div>`;
    } else {
      const kind = CAP.classify(t);
      box.innerHTML = kind === "unknown"
        ? `<div class="dock-prev warn">算法判不准 → 会进待分类，之后一起处理</div>`
        : `<div class="dock-prev">算法认为这是「${esc(COLL_NAME[CAP.toRecord(t, "auto", new Date()).collection] || kind)}」，
             点确定会直接落位（不想自动落位就切到「📥 待分类」）</div>`;
    }
  },

  async save() {
    const ta = $("#dockInput"); const text = (ta.value || "").trim();
    if (!text) return;

    if (DOCK.tab === "note") {
      const kind = ($("#dockTags .on") || {}).dataset ? $("#dockTags .on").dataset.k : "idea";
      const refs = CAP.parseRefs(text);
      const dups = CAP.findDuplicates(text, "ideas");
      await saveRec("ideas", {
        title: text, kind, status: "new", source: "manual",
        body: refs.urls.length ? refs.urls.join("\n") : "",
      });
      toast(dups.length ? "已记下 · 和已有 " + dups.length + " 条相似，周报时会一并回顾" : "已记下");

    } else if (DOCK.tab === "done") {
      // 完成记录：既进日程（已完成），又按内容落到对应模块
      const parsed = CAP.toRecord(text, "auto", new Date());
      const date = CAP.parseDate(text) || todayStr();
      const mins = CAP.parseMinutes(text);
      let extra = "";
      if (["exercise", "diet", "finance"].includes(parsed.collection)) {
        await saveRec(parsed.collection, parsed.record);
        extra = " · 同时进「" + (COLL_NAME[parsed.collection] || "") + "」";
      } else if (parsed.collection === "manuscripts" && parsed.patchId) {
        // 追加到时间线：基于服务端刚给的那份接，别拿内存里可能过时的数组整段覆盖
        await patchRec("manuscripts", parsed.patchId, fresh => ({
          timeline: (fresh.timeline || []).concat(
            [{ date, event: "note", journal: "", note: text }]),
        }));
        extra = " · 已记入稿件时间线";
      }
      await saveRec("schedule", {
        title: text, start: date, end: date, kind: "task",
        done: true, logged: true, minutes: mins || null,
      });
      toast("已记为完成" + extra);

    } else {
      await saveRec("ideas", { title: text, kind: "idea", status: "new", source: "unsorted" });
      toast("已放入待分类");
    }

    // 存成功了才清草稿。清在 renderBox 之前 ——
    // 否则 renderBox 会把刚存过的那段字又恢复回输入框，看起来像没存进去。
    ta.value = ""; $("#dockPrev").innerHTML = "";
    if (DOCK.draft) delete DOCK.draft[DOCK.tab];
    DOCK.renderBox(); DOCK.updateBadge(); renderNav();
    if (S.route === "today" || S.route === "ideas" || S.route === "schedule" || S.route === "life") render();
  },
};
