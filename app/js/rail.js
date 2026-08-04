/* 右栏：日历 + 速记，占满纵向、中缝可拖、各自可收
   宽屏常驻；窄屏自动退回「右上角弹出 + 右下角药丸」形态。 */

const RAIL = {
  BREAK: 1180,          // 低于这个宽度就退回浮动形态
  wide: true,
  calMonth: null,       // 月历当前显示的月份（null = 本月）

  state() {
    const L = S.config.layout || {};
    return {
      split: L.rail_split == null ? 0.55 : L.rail_split,
      cal: !!(L.rail_collapsed || {}).calendar,
      memo: !!(L.rail_collapsed || {}).memo,
      width: L.rail_width || 326,
    };
  },
  async setState(patch) {
    const L = Object.assign({}, S.config.layout || {});
    Object.assign(L, patch);
    await saveConfig({ layout: L });
  },

  mount() {
    if (!$("#rail")) {
      $(".body").insertAdjacentHTML("beforeend", `<aside class="rail" id="rail"></aside>`);
    }
    RAIL.onResize();
    window.addEventListener("resize", debounce(RAIL.onResize, 160));
  },

  onResize() {
    const wide = window.innerWidth >= RAIL.BREAK;
    if (wide === RAIL.wide && $("#rail") && $("#rail").innerHTML) { RAIL.render(); return; }
    RAIL.wide = wide;
    document.body.classList.toggle("narrow", !wide);
    RAIL.render();
    DOCK.relocate();
  },

  /* 重绘右栏前，先把速记框搬回它的老家，否则会被 innerHTML 连根拔掉 */
  detachDock() {
    const box = document.getElementById("dockBox");
    const home = document.getElementById("dock");
    if (box && home && box.parentElement !== home) {
      const pill = document.getElementById("dockPill");
      home.insertBefore(box, pill || null);
      box.classList.add("hide");
      box.classList.remove("in-rail");
    }
  },

  render() {
    const rail = $("#rail"); if (!rail) return;
    RAIL.detachDock();
    if (!RAIL.wide) { rail.innerHTML = ""; if (typeof DOCK !== "undefined") DOCK.relocate(); return; }
    const st = RAIL.state();
    const bothClosed = st.cal && st.memo;
    document.documentElement.style.setProperty("--rail-w", bothClosed ? "44px" : st.width + "px");
    rail.classList.toggle("mini", bothClosed);

    if (bothClosed) {
      rail.innerHTML = `
        <div class="rail-mini">
          <button class="rail-mini-btn" data-rexpand="calendar" title="展开日历">📅</button>
          <button class="rail-mini-btn" data-rexpand="memo" title="展开速记">💭</button>
        </div>`;
    } else {
      const calFlex = st.cal ? 0 : (st.memo ? 1 : st.split);
      const memoFlex = st.memo ? 0 : (st.cal ? 1 : 1 - st.split);
      rail.innerHTML = `
        <section class="rpanel ${st.cal ? "closed" : ""}" id="rpCal" style="flex:${calFlex} 1 0">
          <div class="rp-head" data-rtoggle="calendar">
            <span class="caret">▾</span><b>📅 日历</b><span class="spacer"></span>
            <span class="tiny muted" id="calSub"></span>
          </div>
          <div class="rp-body" id="calBody"></div>
        </section>
        ${(!st.cal && !st.memo) ? `<div class="rail-split" id="railSplit" title="拖动调整上下比例；双击复位"></div>` : ""}
        <section class="rpanel ${st.memo ? "closed" : ""}" id="rpMemo" style="flex:${memoFlex} 1 0">
          <div class="rp-head" data-rtoggle="memo">
            <span class="caret">▾</span><b>💭 现在想记点什么？</b><span class="spacer"></span>
            <span class="dock-badge" id="dockBadgeRail" hidden></span>
          </div>
          <div class="rp-body" id="memoHost"></div>
        </section>`;
      if (!st.cal) RAIL.renderCalendar();
      RAIL.bindSplit();
    }
    $$("[data-rtoggle]").forEach(h => h.onclick = async e => {
      if (e.target.closest("button")) return;
      const k = h.dataset.rtoggle;
      const cur = Object.assign({}, (S.config.layout || {}).rail_collapsed || {});
      cur[k] = !cur[k];
      await RAIL.setState({ rail_collapsed: cur });
      RAIL.render(); DOCK.relocate();
    });
    $$("[data-rexpand]").forEach(b => b.onclick = async () => {
      const cur = Object.assign({}, (S.config.layout || {}).rail_collapsed || {});
      cur[b.dataset.rexpand] = false;
      await RAIL.setState({ rail_collapsed: cur });
      RAIL.render(); DOCK.relocate();
    });
    DOCK.relocate();
  },

  bindSplit() {
    const sp = $("#railSplit"); if (!sp) return;
    let startY = 0, h0 = 0, total = 0;
    const down = e => {
      const p = e.touches ? e.touches[0] : e;
      startY = p.clientY;
      h0 = $("#rpCal").getBoundingClientRect().height;
      total = $("#rail").getBoundingClientRect().height;
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
      document.addEventListener("touchmove", mv, { passive: false }); document.addEventListener("touchend", up);
      e.preventDefault();
    };
    const mv = e => {
      const p = e.touches ? e.touches[0] : e;
      const ratio = Math.max(0.18, Math.min(0.85, (h0 + p.clientY - startY) / total));
      $("#rpCal").style.flex = `${ratio} 1 0`;
      $("#rpMemo").style.flex = `${1 - ratio} 1 0`;
      sp.dataset.ratio = ratio;
    };
    const up = async () => {
      document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up);
      document.removeEventListener("touchmove", mv); document.removeEventListener("touchend", up);
      document.body.style.userSelect = "";
      if (sp.dataset.ratio) await RAIL.setState({ rail_split: Number(sp.dataset.ratio) });
    };
    sp.addEventListener("mousedown", down);
    sp.addEventListener("touchstart", down, { passive: false });
    sp.ondblclick = async () => { await RAIL.setState({ rail_split: 0.55 }); RAIL.render(); };
  },

  /* ------------------------------------------------------- 日历面板 */
  events(dateStr) {
    const out = [];
    (S.icsEvents || []).forEach(e => {
      if (String(e.date).slice(0, 10) === dateStr) {
        out.push({
          time: e.time, title: e.title, src: "Outlook", cls: "o", loc: e.location,
          /* 时间已按订阅日历里的时区换算成本机时间。跨时区的会在这里留个痕，
             免得你对着「邀请上明明写的是 9 点」发懵 */
          tzNote: e.src_tz ? `原 ${e.src_time} · ${e.src_tz}（已换算成本地时间）` : "",
        });
      }
    });
    rows("schedule").forEach(s => {
      if (String(s.start || "").slice(0, 10) === dateStr && !s.logged) {
        out.push({ time: s.time, title: s.title, src: "工作台", cls: s.done ? "g" : "", done: s.done });
      }
    });
    rows("conferences").forEach(c => {
      if (String(c.deadline || "").slice(0, 10) === dateStr) out.push({ title: c.title + " 截止", src: "会议", cls: "v" });
    });
    rows("manuscripts").forEach(m => {
      if (String(m.next_action_due || "").slice(0, 10) === dateStr) out.push({ title: (m.title || "").slice(0, 20) + " · " + (m.next_action || ""), src: "稿件", cls: "v" });
    });
    rows("admin").forEach(a => {
      if (String(a.date || "").slice(0, 10) === dateStr && !a.done) out.push({ title: a.title, src: "生活", cls: "g" });
    });
    return out.sort((a, b) => String(a.time || "99").localeCompare(String(b.time || "99")));
  },
  hasEvents(dateStr) { return RAIL.events(dateStr).length > 0; },

  renderCalendar(hostSel) {
    /* 弹出层和常驻右栏都要画日历，容器不能重名，否则弹层永远是空的 */
    const host = $(hostSel || "#calPop #calBodyPop") || $("#calBody");
    if (!host) return;
    const now = new Date();
    const cur = RAIL.calMonth ? new Date(RAIL.calMonth) : now;
    const y = cur.getFullYear(), mo = cur.getMonth();
    const lun = typeof LUNAR !== "undefined" ? LUNAR.full(now) : null;
    const w = S.weather || {};
    const first = new Date(y, mo, 1), last = new Date(y, mo + 1, 0);
    const lead = (first.getDay() + 6) % 7;
    const cells = [];
    for (let i = 0; i < lead; i++) cells.push(new Date(y, mo, -(lead - i - 1)));
    for (let d = 1; d <= last.getDate(); d++) cells.push(new Date(y, mo, d));
    while (cells.length % 7) cells.push(new Date(y, mo + 1, cells.length - lead - last.getDate() + 1));
    const todayS = todayStr();
    const sel = RAIL.selDate || todayS;

    host.innerHTML = `
      <div class="cal-top compact">
        <div class="cal-line1">
          <span class="cal-d1">${now.getMonth() + 1}月${now.getDate()}日</span>
          <span class="cal-d2">${now.toLocaleDateString("zh-CN", { weekday: "short" })}</span>
          ${w.ok ? `<span class="cal-temp">${esc(w.text || "")} <b>${w.temp != null ? Math.round(w.temp) + "°" : "—"}</b></span>` : ""}
        </div>
        <div class="cal-line2">
          ${lun ? `<span>${esc(lun.text)}</span>${lun.festival ? `<span class="hl">${esc(lun.festival)}</span>`
            : (lun.term ? `<span class="hl">${esc(lun.term)}</span>` : "")}` : ""}
          ${w.ok && w.tmax != null ? `<span class="spacer"></span><span>${Math.round(w.tmin)}~${Math.round(w.tmax)}°</span>` : ""}
        </div>
        ${(w.tips || []).length ? `<div class="cal-tips">${w.tips.slice(0, 1).map(t => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="cal-nav">
        <button class="btn sm ghost" data-cmove="-1">‹</button>
        <b>${y} 年 ${mo + 1} 月</b>
        <button class="btn sm ghost" data-cmove="1">›</button>
        <span class="spacer"></span>
        <button class="btn sm ghost" data-cmove="0">今天</button>
      </div>
      <div class="cg">
        ${["一", "二", "三", "四", "五", "六", "日"].map(d => `<div class="hd">${d}</div>`).join("")}
        ${cells.map(d => {
          const ds = todayStr(d);
          const out = d.getMonth() !== mo;
          const li = typeof LUNAR !== "undefined" ? LUNAR.fromSolar(d) : null;
          const lbl = li ? (li.day === 1 ? LUNAR.monthName(li.month, li.isLeap) : LUNAR.dayName(li.day)) : "";
          const fest = li && typeof LUNAR !== "undefined" ? LUNAR.festival(li) : "";
          const term = typeof LUNAR !== "undefined" ? LUNAR.termOf(d) : "";
          return `<div class="dd ${out ? "out" : ""} ${ds === todayS ? "today" : ""} ${ds === sel ? "sel" : ""}" data-cday="${ds}">
            <span class="dnum">${d.getDate()}</span>
            <span class="dlun ${fest || term ? "hl" : ""}">${esc(fest || term || lbl)}</span>
            ${RAIL.hasEvents(ds) ? `<span class="ev"></span>` : ""}</div>`;
        }).join("")}
      </div>
      <div class="cal-list">
        <div class="cal-list-h">${sel === todayS ? "今天" : esc(sel)}</div>
        ${(() => {
          const evs = RAIL.events(sel);
          return evs.length ? evs.map(e => `<div class="cal-ev ${e.done ? "done" : ""}"${e.tzNote ? ` title="${esc(e.tzNote)}"` : ""}>
            <div class="tm">${esc(e.time || "全天")}${e.tzNote ? `<span class="tzdot" title="${esc(e.tzNote)}">🌐</span>` : ""}</div>
            <div class="bar ${e.cls || ""}"></div>
            <div class="ct">${esc(e.title || "")}<span class="src">${esc(e.src)}</span>
              ${e.loc ? `<div class="tiny muted">${esc(e.loc)}</div>` : ""}
              ${e.tzNote ? `<div class="tiny muted">${esc(e.tzNote)}</div>` : ""}</div></div>`).join("")
            : `<div class="empty" style="padding:14px 4px">这天没有安排</div>`;
        })()}
      </div>
      <div class="rfoot">
        <button class="btn sm primary" id="calAdd">＋ 加日程</button>
        <button class="btn sm" data-go="schedule">完整日历</button>
        <span class="spacer"></span>
        <button class="btn sm ghost" id="calRefresh" title="重新拉取订阅日历与天气">⟳</button>
      </div>`;
    const sub = $("#calSub");
    if (sub) {
      const n = ((S.config.calendar || {}).ics || []).length;
      const bad = (S.icsErrors || []).length;
      sub.textContent = bad ? `订阅拉取失败 ${bad} 个` : (n ? `已订阅 ${n} 个` : "");
      sub.style.color = bad ? "var(--red)" : "";
      sub.title = bad ? (S.icsErrors || []).map(e => e.detail || e.url).join("\n") : "";
    }
    $$("[data-cmove]", host).forEach(b => b.onclick = () => {
      const d = Number(b.dataset.cmove);
      if (d === 0) { RAIL.calMonth = null; RAIL.selDate = todayStr(); }
      else {
        /* 必须从当月 1 号算，否则 31 号时 setMonth(+1) 会溢出到下下个月，2 月直接被跳过 */
        const c = RAIL.calMonth ? new Date(RAIL.calMonth) : new Date();
        RAIL.calMonth = new Date(c.getFullYear(), c.getMonth() + d, 1);
      }
      RAIL.renderCalendar(hostSel);
    });
    $$("[data-cday]", host).forEach(c => c.onclick = () => { RAIL.selDate = c.dataset.cday; RAIL.renderCalendar(hostSel); });
    const addBtn = $("#calAdd", host); if (addBtn) addBtn.onclick = () => quickCapture(RAIL.selDate === todayStr() ? "" : RAIL.selDate + " ");
    const refBtn = $("#calRefresh", host);
    if (refBtn) refBtn.onclick = async () => {
      toast("刷新中…"); await refreshAmbient(true); RAIL.renderCalendar(hostSel); toast("已刷新");
    };
    $$("[data-go]", host).forEach(b => b.onclick = () => go(b.dataset.go));
  },
};

/* 窄屏时的日历弹出层 */
RAIL.popover = function () {
  if ($("#calPop")) { $("#calPop").remove(); return; }
  document.body.insertAdjacentHTML("beforeend",
    `<div class="calpop-back" id="calPop"><div class="calpop"><div class="rp-body" id="calBodyPop"></div></div></div>`);
  RAIL.renderCalendar("#calBodyPop");
  $("#calPop").onclick = e => { if (e.target.id === "calPop") $("#calPop").remove(); };
};
