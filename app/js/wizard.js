/* 首次使用向导 · 十步 */
const WZ = {
  step: 0,
  draft: { config: {}, device: {}, secrets: {} },
  get last() { return WZ.steps.length - 1; },      // 最后一步（核对页）的索引

  open(startAt) {
    WZ.step = startAt || 0;
    WZ.draft = { config: {}, device: {}, secrets: {} };
    document.body.insertAdjacentHTML("beforeend", `<div class="wz-back" id="wzBack"><div class="wz" id="wz"></div></div>`);
    WZ.render();
  },
  close() { const b = $("#wzBack"); if (b) b.remove(); },

  /* 必填校验：缺哪项就红框标出并阻止下一步；点「跳过这步」则不校验 */
  requireOk() {
    const req = WZ.steps[WZ.step].required || [];
    const miss = [];
    req.forEach(r => {
      const el = document.getElementById(r.id);
      if (!el) return;
      const v = (el.type === "checkbox" ? el.checked : (el.value || "").trim());
      const ok = r.test ? r.test(v) : !!v;
      el.classList.toggle("need", !ok);
      if (!ok) miss.push(r.label);
    });
    if (miss.length) {
      let box = document.getElementById("wzReq");
      if (!box) {
        box = document.createElement("div");
        box.id = "wzReq"; box.className = "wz-result bad";
        $(".wz-body").appendChild(box);
      }
      box.className = "wz-result bad";
      box.innerHTML = "✕ 还差：" + miss.join("、") +
        "　—— 填好才能继续；如果暂时没有，点右下角「跳过这步」。";
      box.scrollIntoView({ block: "nearest" });
      return false;
    }
    return true;
  },

  async saveAndNext(delta) {
    if (!WZ.requireOk()) return;
    const fn = WZ.steps[WZ.step].collect;
    if (fn) {
      const res = await fn();
      if (res === false) return;               // 校验没过
    }
    await WZ.flush();
    WZ.step = Math.max(0, Math.min(WZ.last, WZ.step + (delta == null ? 1 : delta)));
    await API.post("config/merge", { setup: { step: WZ.step } });
    WZ.render();
  },

  async flush() {
    if (Object.keys(WZ.draft.config).length) {
      const r = await API.post("config/merge", WZ.draft.config);
      S.config = r.config; WZ.draft.config = {};
    }
    if (Object.keys(WZ.draft.device).length) {
      await saveDevice(WZ.draft.device); WZ.draft.device = {};
    }
    if (Object.keys(WZ.draft.secrets).length) {
      const r = await API.post("secrets/merge", WZ.draft.secrets); WZ.draft.secrets = {};
      /* 核对页读的是 S.secretsStatus，不刷新的话刚填好的会显示成「未配」 */
      S.secretsStatus = (r && r.status) || await API.get("secrets/status").catch(() => S.secretsStatus);
    }
  },

  v(id) { const el = document.getElementById(id); return el ? (el.type === "checkbox" ? el.checked : el.value.trim()) : ""; },

  render() {
    const s = WZ.steps[WZ.step];
    const pct = Math.round((WZ.step / WZ.last) * 100);
    $("#wz").innerHTML = `
      <div class="wz-head">
        <div class="wz-bar"><i style="width:${pct}%"></i></div>
        <div class="wz-step">${WZ.step === 0 ? "开始" : `第 ${WZ.step} / ${WZ.last} 步`}</div>
        <div class="wz-title">${s.icon} ${s.title}</div>
        ${s.sub ? `<div class="wz-sub">${s.sub}</div>` : ""}
      </div>
      <div class="wz-body">${s.body()}</div>
      <div class="wz-foot">
        ${WZ.step > 0 ? `<button class="btn" id="wzBack2">← 上一步</button>` : ""}
        <button class="btn ghost" id="wzQuit">以后再说</button>
        <span class="spacer"></span>
        ${s.skippable !== false && WZ.step < WZ.last ? `<button class="btn g" id="wzSkip">跳过这步</button>` : ""}
        <button class="btn primary" id="wzNext">${WZ.step >= WZ.last ? "完成设置 ✓" : "下一步 →"}</button>
      </div>`;
    if ($("#wzBack2")) $("#wzBack2").onclick = async () => {
      const fn = WZ.steps[WZ.step].collect;        // 往回走也要先把这一步填的收起来
      try { if (fn) await fn(); } catch (e) { }
      WZ.step--; WZ.render();
    };
    if ($("#wzQuit")) $("#wzQuit").onclick = WZ.close;
    const back = $("#wzBack");
    if (back) back.onclick = e => { if (e.target === back) WZ.close(); };   // 点遮罩也能关
    if ($("#wzSkip")) $("#wzSkip").onclick = () => { WZ.step = Math.min(WZ.last, WZ.step + 1); WZ.render(); };
    $("#wzNext").onclick = () => WZ.step >= WZ.last ? (WZ.requireOk() && WZ.finish()) : WZ.saveAndNext(1);
    if (s.after) s.after();
  },

  async finish() {
    const fn = WZ.steps[WZ.step].collect;
    if (fn) await fn();
    await WZ.flush();
    await API.post("setup/complete", {});
    const b = await API.bootstrap(); Object.assign(S, b);
    WZ.close(); applyTheme(); renderNav(); render();
    toast("设置完成！正在跑第一次全库体检…");
  },

  note(t) { return `<div class="wz-note">${t}</div>`; },
  row(label, id, ph, type, hint) {
    return `<div class="field"><label>${label}</label>
      <input id="${id}" type="${type || "text"}" placeholder="${ph || ""}">
      ${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  },
  /* 只把「这次真的填了」的字段交上去。
     以前空框一律当成 ""，一次 secrets/merge 就把已配好的 token / 密钥全抹了。 */
  prune(obj) {
    const out = {};
    Object.entries(obj).forEach(([k, v]) => {
      if (v && typeof v === "object" && !Array.isArray(v)) {
        const inner = WZ.prune(v);
        if (Object.keys(inner).length) out[k] = inner;
      } else if (v !== "" && v != null) {
        out[k] = v;
      }
    });
    return out;
  },
  pushPayload() {
    return WZ.prune({
      dingtalk_webhook: WZ.v("wz_dd"), dingtalk_secret: WZ.v("wz_dds"),
      dingtalk_keyword: WZ.v("wz_ddk"),
      email: {
        host: WZ.v("wz_eh"), port: WZ.v("wz_ep"), user: WZ.v("wz_eu"),
        password: WZ.v("wz_epw"), to: WZ.v("wz_et"),
      },
      custom: { url: WZ.v("wz_cu"), name: WZ.v("wz_cn"), template: WZ.v("wz_ct") },
    });
  },
  aiPayload() {
    return WZ.prune({
      provider: WZ.v("wz_aip") || "anthropic",
      anthropic_key: (WZ.v("wz_ak") || "").trim(),
      anthropic_model: (WZ.v("wz_am") || "").trim(),
      anthropic_base: (WZ.v("wz_ab") || "").trim(),
      openai_key: (WZ.v("wz_ok") || "").trim(),
      openai_model: (WZ.v("wz_om") || "").trim(),
      openai_base: (WZ.v("wz_ob") || "").trim(),
      deepseek_key: (WZ.v("wz_dk") || "").trim(),
      deepseek_model: (WZ.v("wz_dm") || "").trim(),
      deepseek_base: (WZ.v("wz_db") || "").trim(),
    });
  },
  result(id) { return `<div class="wz-result" id="${id}"></div>`; },
  say(id, ok, msg) {
    const el = document.getElementById(id); if (!el) return;
    el.className = "wz-result " + (ok ? "ok" : "bad");
    el.innerHTML = (ok ? "✓ " : "✕ ") + esc(String(msg == null ? "" : msg));
  },
};

WZ.steps = [
  /* ---------------------------------------------------------- 0 欢迎 */
  {
    icon: "👋", title: "欢迎使用学术工作台", skippable: false,
    sub: "花三分钟把该配的一次配完，之后就不用再管了。每一步都可以跳过，跳过的会在设置页留个提醒。",
    body: () => `
      <div class="wz-hero">
        <div class="wz-hero-q">“不驰于空想，不骛于虚声，循正道而行，故无所不至。”</div>
        <div class="wz-hero-m">— 每天打开工作台，这里会是一句新的</div>
      </div>
      <div class="wz-grid3">
        <div class="wz-card"><b>📄 学术生产</b><div>选题 → 写作 → 投稿 → 审稿 → 转投 → 发表 → 复盘，全程留痕，期刊的真实审稿周期自动沉淀。</div></div>
        <div class="wz-card"><b>🤖 AI 不闲着</b><div>把你订阅里用不完、会蒸发的额度，用在挑漏洞、扫文献缺口、全库体检上。</div></div>
        <div class="wz-card"><b>🔗 多设备</b><div>Mac 与 Windows 共用一个私有 Git 仓库，手机也能连；生活数据只留本机。</div></div>
      </div>
      <div class="form-grid" style="margin-top:14px">
        <div class="field"><label>给你的工作台起个名字</label>
          <input id="wz_bt" placeholder="学术工作台">
          <div class="hint">显示在左上角。左边那个 J 是这套工作台的标志，固定不变。</div></div>
        <div class="field"><label>副标题</label>
          <input id="wz_bs" placeholder="Scholar Workspace"></div>
      </div>
      ${WZ.note("下面这些信息只存在你自己的电脑和你自己的私有仓库里，不会发给任何第三方。")}`,
    after: () => {
      const b = S.config.brand || {};
      if (b.title && $("#wz_bt")) $("#wz_bt").value = b.title;
      if (b.sub && $("#wz_bs")) $("#wz_bs").value = b.sub;
    },
    collect: () => {
      const b = WZ.prune({ title: WZ.v("wz_bt"), sub: WZ.v("wz_bs") });
      if (Object.keys(b).length) WZ.draft.config.brand = b;
    },
  },

  /* ---------------------------------------------------------- 1 你是谁 */
  {
    icon: "🧑‍🎓", title: "你是谁", sub: "用于称呼、天气定位，以及给雷达功能一组默认关键词。",
    body: () => `
      <div class="form-grid">
        ${WZ.row("称呼", "wz_name", "你怎么称呼")}
        <div class="field"><label>所在城市</label>
          <div style="display:flex;gap:6px"><input id="wz_city" placeholder="杭州 / Bristol" style="flex:1">
            <button class="btn sm" type="button" id="wz_geoBtn">定位</button></div>
          <div class="hint">按城市名查坐标，比 IP 定位准（挂 VPN 时 IP 会把你定到别的国家）。</div></div>
        ${WZ.row("学科领域", "wz_field", "金融 / 资产定价")}
        <div class="field wide"><label>关注的研究主题关键词</label>
          <input id="wz_kw" placeholder="intermediary asset pricing, market microstructure, DID estimator">
          <div class="hint">逗号分隔。GitHub 雷达和文献扫描会按这些词找东西给你。</div></div>
      </div>
      <div class="field"><label>时区</label>
        <div class="wz-static" id="wz_tz">检测中…</div>
        <div class="hint">自动检测，你换地方它会自己跟着变，不用手动改。</div></div>
      ${WZ.result("wz_geo")}`,
    after: () => {
      $("#wz_tz").textContent = timeZone() + " · 当前时间 " + new Date().toLocaleString("zh-CN");
      const p = S.config.profile || {};
      if (p.name) $("#wz_name").value = p.name;
      if (p.field) $("#wz_field").value = p.field;
      if ((p.keywords || []).length) $("#wz_kw").value = p.keywords.join(", ");
      const doGeo = async () => {
        const city = $("#wz_city").value.trim();
        if (!city) return WZ.say("wz_geo", false, "先填城市名");
        WZ.say("wz_geo", true, "查询中…");
        const g = await API.get("geocode?city=" + encodeURIComponent(city));
        if (g.ok) {
          WZ._geo = g;
          WZ.say("wz_geo", true, `${esc(g.city)}${g.admin ? "・" + esc(g.admin) : ""}${g.country ? "・" + esc(g.country) : ""}
            （${g.lat.toFixed(2)}, ${g.lon.toFixed(2)}）` +
            (g.alts.length > 1 ? `<div class="tiny" style="margin-top:4px">同名的还有：` +
              g.alts.slice(1).map((a, i) => `<button class="lnk" data-alt="${i + 1}">${esc(a.name)}·${esc(a.country)}</button>`).join(" ") + `</div>` : ""));
          $$("[data-alt]").forEach(b => b.onclick = () => {
            const a = g.alts[Number(b.dataset.alt)];
            WZ._geo = Object.assign({}, g, a);
            WZ.say("wz_geo", true, `已改为 ${esc(a.name)}・${esc(a.country)}（${a.lat.toFixed(2)}, ${a.lon.toFixed(2)}）`);
          });
        } else WZ.say("wz_geo", false, g.detail || "查询失败");
      };
      $("#wz_geoBtn").onclick = doGeo;
      if (p.city) { $("#wz_city").value = p.city; if (p.lat == null) doGeo(); }
      else API.get("geo").then(g => {
        if (g.ok && g.city) { $("#wz_city").value = g.city; doGeo(); }
        else WZ.say("wz_geo", false, "自动定位不可用，请手填城市后点「定位」。");
      }).catch(() => { });
    },
    required: [{ id: "wz_name", label: "称呼" }, { id: "wz_city", label: "所在城市" },
               { id: "wz_kw", label: "研究关键词（雷达和文献扫描要用）" }],
    collect: () => {
      WZ.draft.config.profile = {
        name: WZ.v("wz_name") || "",
        city: WZ.v("wz_city"),
        field: WZ.v("wz_field"),
        keywords: WZ.v("wz_kw").split(/[,，]/).map(s => s.trim()).filter(Boolean),
      };
      if (WZ._geo) { WZ.draft.config.profile.lat = WZ._geo.lat; WZ.draft.config.profile.lon = WZ._geo.lon; }
      WZ.draft.device.timezone = timeZone();
    },
  },

  /* ---------------------------------------------------------- 2 本机路径 */
  {
    icon: "💻", title: "这台电脑的路径", sub: "每台设备各填一次，这些不会同步到另一台机器。",
    body: () => `
      <div class="form-grid">
        ${WZ.row("本机名称", "wz_dev", "MacBook / 办公室 Windows")}
        <div class="field wide"><label>论文根目录<span class="req">·必填</span></label>
          <input id="wz_paper" placeholder="Mac: /Users/你/Documents/0PhD　Win: D:\\Papers">
          <div class="hint"><b>它是干什么的：</b>稿件卡里只需填相对路径（如 <code>intermediary/</code>），
            系统会到这里往下找，并自动扫描 <code>figures/</code> <code>tables/</code> 把结果图渲染出来。
            它也是「允许访问」的白名单——不在这些目录下的文件工作台一律不读。</div></div>
        <div class="field wide"><label>其它论文目录（可选，一行一个）</label>
          <textarea id="wz_paper2" style="min-height:54px" placeholder="/Users/你/Dropbox/合作项目&#10;/Volumes/移动硬盘/旧论文"></textarea>
          <div class="hint">论文散在多处很正常，都填进来即可。</div></div>
        <div class="field wide">${""}
          <label>OneDrive 长期备份目录</label>
          <input id="wz_od" placeholder="Mac: /Users/你/OneDrive/工作台备份　Win: C:\\Users\\你\\OneDrive\\工作台备份">
          <div class="hint">要填<b>本机路径</b>，不是网页链接。在访达里打开 OneDrive 的同步文件夹 →
            右键文件夹名 → 按住 Option → 「拷贝为路径名」。每天中午和晚上各存一份到这里，永久保留。</div>
          <div style="display:flex;gap:6px;margin-top:6px">
            <button class="btn sm" type="button" id="wz_odCheck">检查这个目录</button></div>
          ${WZ.result("wz_odRes")}</div>
      </div>
      <div class="field"><label>浏览器</label>
        <label class="wz-check"><input type="checkbox" id="wz_chrome" checked> 固定用 Chrome 打开工作台</label>
        <div class="hint">勾上后，服务启动会直接调 Chrome。好处是：顶部那些「打开 Claude / ChatGPT / Scholar」的按钮会用 Chrome 里<b>已经登录好的</b>会话，你只需登录一次。</div></div>`,
    after: () => {
      const d = S.device || {};
      $("#wz_dev").value = d.device_name || "";
      $("#wz_paper").value = d.paper_root || "";
      $("#wz_paper2").value = (d.paper_roots || []).join("\n");
      $("#wz_od").value = d.onedrive_backup_dir || "";
      $("#wz_odCheck").onclick = async () => {
        const path = $("#wz_od").value.trim();
        WZ.say("wz_odRes", true, "检查中…");
        const r = await API.get("checkdir?path=" + encodeURIComponent(path));
        if (r.ok) return WZ.say("wz_odRes", true, r.detail);
        WZ.say("wz_odRes", false, r.detail +
          (r.creatable ? ` <button class="lnk" id="wz_mk">帮我创建</button>` : ""));
        const mk = $("#wz_mk");
        if (mk) mk.onclick = async () => {
          const rr = await API.post("mkdir", { path });
          WZ.say("wz_odRes", rr.ok, rr.ok ? "已创建，可以用了" : rr.detail);
        };
      };
      if ((d.onedrive_backup_dir || "").startsWith("http")) {
        setTimeout(() => WZ.say("wz_odRes", false,
          "当前填的是一个网页链接，备份会失败——请改成本机文件夹路径。"), 200);
      }
    },
    required: [{ id: "wz_paper", label: "论文根目录" }],
    collect: () => {
      WZ.draft.device = Object.assign(WZ.draft.device || {}, {
        device_name: WZ.v("wz_dev"), paper_root: WZ.v("wz_paper"),
        paper_roots: WZ.v("wz_paper2").split(/\n/).map(x => x.trim()).filter(Boolean),
        onedrive_backup_dir: WZ.v("wz_od"), prefer_chrome: WZ.v("wz_chrome"),
      });
    },
  },

  /* ---------------------------------------------------------- 3 GitHub */
  {
    icon: "🔗", title: "GitHub 同步", sub: "这是 Mac ↔ Windows ↔ 手机 ↔ 云端 Claude 之间唯一的桥。建议私有仓库。",
    body: () => `
      <div class="form-grid">
        ${WZ.row("GitHub 用户名", "wz_ghu", "your-username")}
        ${WZ.row("Personal Access Token", "wz_ght", "ghp_…", "password", "GitHub → Settings → Developer settings → PAT，勾 repo 权限。只存本机 local/secrets.json")}
        <div class="field wide">
          <label>私有仓库地址</label>
          <input id="wz_ghr" placeholder="https://github.com/你的用户名/scholar-workspace.git">
          <div class="hint">先去 GitHub 建一个<b>空的私有仓库</b>（不要勾任何初始化文件），把 HTTPS 地址贴过来。</div></div>
        ${WZ.row("Git 提交邮箱", "wz_ghe", "you@example.com")}
      </div>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button class="btn" id="wz_gtest">测试连接</button>
        <span class="hint" style="align-self:center">强烈建议测一下再往下走</span></div>
      ${WZ.result("wz_gres")}`,
    after: () => {
      $("#wz_gtest").onclick = async () => {
        WZ.say("wz_gres", true, "连接中…");
        const r = await API.post("test/git", {
          remote: WZ.v("wz_ghr"), user: WZ.v("wz_ghu"), token: WZ.v("wz_ght"),
        });
        if (r.ok) WZ.say("wz_gres", true, r.empty_repo
          ? "连上了，是个空仓库——正合适，完成向导后会把工作台推上去。"
          : "连上了，远程分支：" + (r.branches || []).join("、"));
        else WZ.say("wz_gres", false, r.detail);
      };
    },
    required: [{ id: "wz_ghr", label: "私有仓库地址", test: v => /^https?:\/\/.+\.git$|^git@/.test(v) },
               { id: "wz_ght", label: "Personal Access Token" }],
    collect: () => {
      WZ.draft.secrets.github = { user: WZ.v("wz_ghu"), token: WZ.v("wz_ght"), email: WZ.v("wz_ghe") };
      WZ.draft.config.git = { remote: WZ.v("wz_ghr") };
    },
  },

  /* ---------------------------------------------------------- 4 日历天气 */
  {
    icon: "📅", title: "日历与天气", sub: "右上角那个日历面板的数据源。ICS 是只读订阅，不需要授权，安全。",
    body: () => `
      <div class="field wide"><label>Outlook 日历订阅链接（ICS）</label>
        <input id="wz_ics1" placeholder="https://outlook.office365.com/owa/calendar/.../reachcalendar.ics">
        <div class="hint">Outlook 网页版 → 设置 → 日历 → 共享日历 → 发布日历 → 选「可以查看所有详细信息」→ 复制 <b>ICS</b> 链接（不是 HTML 那个）。</div></div>
      <div class="field wide"><label>另一个日历（可选：学校 / 会议 / Google）</label>
        <input id="wz_ics2" placeholder="https://…/basic.ics"></div>
      <div class="form-grid">
        <div class="field"><label>刷新间隔（分钟）</label><input type="number" id="wz_ref" value="15"></div>
        <div class="field"><label>显示</label>
          <label class="wz-check"><input type="checkbox" id="wz_lunar" checked> 农历与二十四节气</label>
          <label class="wz-check"><input type="checkbox" id="wz_wx" checked> 天气与提醒</label></div>
      </div>
      <div style="display:flex;gap:8px;margin-top:6px"><button class="btn" id="wz_itest">立即拉取试试</button></div>
      ${WZ.result("wz_ires")}
      ${WZ.note("农历和节气用的是离线算法（1900–2100），不联网、不会错、也不需要 AI 去核对。天气用 Open-Meteo，不需要 API key。")}`,
    after: () => {
      const ics = (S.config.calendar || {}).ics || [];
      if (ics[0]) $("#wz_ics1").value = ics[0];
      if (ics[1]) $("#wz_ics2").value = ics[1];
      $("#wz_itest").onclick = async () => {
        const url = WZ.v("wz_ics1") || WZ.v("wz_ics2");
        if (!url) return WZ.say("wz_ires", false, "先填一个链接");
        WZ.say("wz_ires", true, "拉取中…");
        const r = await API.post("test/ics", { url });
        if (r.ok) WZ.say("wz_ires", true, `读到 ${r.count} 条日程。例如：` +
          (r.sample || []).map(e => `${e.date}${e.time ? " " + e.time : ""} ${e.title}`).join("；"));
        else WZ.say("wz_ires", false, r.detail);
      };
    },
    collect: () => {
      WZ.draft.config.calendar = {
        ics: [WZ.v("wz_ics1"), WZ.v("wz_ics2")].filter(Boolean),
        refresh_min: Number(WZ.v("wz_ref")) || 15,
        lunar: WZ.v("wz_lunar"), weather: WZ.v("wz_wx"),
      };
    },
  },

  /* ---------------------------------------------------------- 5 推送 */
  {
    icon: "📲", title: "推送渠道", sub: "周一早上的「本周开局」，以及逾期和体检告警，从这里发给你。钉钉是主通道；邮件和自定义 webhook 可选。",
    body: () => `
      <div class="wz-sec">🔔 钉钉群机器人</div>
      <div class="form-grid">
        <div class="field wide">${""}<label>Webhook</label>
          <input id="wz_dd" placeholder="https://oapi.dingtalk.com/robot/send?access_token=…">
          <div class="hint">钉钉里建一个只有你自己的群 → 群设置 → 机器人 → 添加「自定义」→ 安全设置勾<b>加签</b> → 复制 Webhook 和密钥。</div></div>
        ${WZ.row("加签密钥（SEC 开头）", "wz_dds", "SEC…", "password", "推荐用加签；每个机器人每分钟限 20 条")}
        ${WZ.row("或：自定义关键词", "wz_ddk", "工作台", "text", "如果安全设置选的是关键词而不是加签，填这里，消息会自动带上它")}
      </div>
      <div style="display:flex;gap:8px"><button class="btn sm" data-tp="dingtalk">发送测试消息</button></div>
      ${WZ.result("wz_r_dingtalk")}

      <div class="wz-sec">📧 邮件</div>
      <div class="form-grid">
        ${WZ.row("SMTP 服务器", "wz_eh", "smtp.gmail.com / smtp.qq.com")}
        ${WZ.row("端口", "wz_ep", "465", "number", "465=SSL，587=STARTTLS")}
        ${WZ.row("账号", "wz_eu", "you@gmail.com")}
        ${WZ.row("密码 / 授权码", "wz_epw", "应用专用密码", "password", "Gmail 用「应用专用密码」，QQ/163 用「授权码」，不是登录密码")}
        ${WZ.row("收件人", "wz_et", "you@gmail.com")}
      </div>
      <div style="display:flex;gap:8px"><button class="btn sm" data-tp="email">发送测试邮件</button></div>
      ${WZ.result("wz_r_email")}

      <div class="wz-sec">🔌 通用 webhook（可选）</div>
      <div class="form-grid">
        <div class="field wide"><label>URL</label>
          <input id="wz_cu" placeholder="https://你的服务/send">
          <div class="hint">任何能收 HTTP 的东西都能接：wxbot、Server酱、Bark、ntfy、Telegram、Slack…
            <b>关于个人微信</b>：wxbot 这类走的是 Wechaty iPad 协议，需要自己跑 Node+MongoDB 服务并申请 token，
            官方 README 也承认有<b>封号风险</b>。我不建议把它当主通道，但你要用，填这里就能接。</div></div>
        ${WZ.row("名称", "wz_cn", "wxbot")}
        <div class="field wide"><label>JSON 模板</label>
          <input id="wz_ct" placeholder='{"to":"filehelper","msg":"{title}\n{text}"}'>
          <div class="hint">占位符 <code>{title}</code> <code>{markdown}</code> <code>{text}</code> 会被自动替换并做好转义。</div></div>
      </div>
      <div style="display:flex;gap:8px"><button class="btn sm" data-tp="custom">发送测试消息</button></div>
      ${WZ.result("wz_r_custom")}

      <div class="wz-sec">⏰ 时间</div>
      <div class="form-grid">
        ${WZ.row("周报推送时间", "wz_wt", "MON 08:00", "text", "按你的本地时区")}
        <div class="field"><label>另外</label>
          <label class="wz-check"><input type="checkbox" id="wz_daily"> 每天早上也来一条今日简报</label></div>
      </div>`,
    after: () => {
      $$("[data-tp]").forEach(b => b.onclick = async () => {
        const kind = b.dataset.tp;
        // 先把当前输入存进去再测，否则测的是空配置
        await API.post("secrets/merge", { push: WZ.pushPayload() });
        WZ.say("wz_r_" + kind, true, "发送中…");
        const r = await API.post("test/push", { kind });
        WZ.say("wz_r_" + kind, r.ok, r.ok ? "发出去了，去看看收到没有。" : (r.detail || "失败"));
      });
      const st = S.secretsStatus || {};
      if (st.email_host) { $("#wz_eh").value = st.email_host; $("#wz_ep").value = st.email_port || ""; $("#wz_eu").value = st.email_user || ""; $("#wz_et").value = st.email_to || ""; }
    },
    required: [{ id: "wz_dd", label: "钉钉 Webhook", test: v => v.startsWith("https://oapi.dingtalk.com/robot/send") }],
    collect: () => {
      WZ.draft.secrets.push = WZ.pushPayload();
      WZ.draft.config.push = {
        weekly_cron: WZ.v("wz_wt") || "MON 08:00", daily_brief: WZ.v("wz_daily"),
        channels: {
          dingtalk: !!WZ.v("wz_dd"), email: !!WZ.v("wz_eh"), custom: !!WZ.v("wz_cu"),
        },
      };
    },
  },

  /* ---------------------------------------------------------- 6 AI 与额度 */
  {
    icon: "⚡", title: "AI 与额度调度", sub: "订阅额度用不完也不滚存。告诉我你的作息，我就知道什么时候替你把它花掉、什么时候该让路。",
    body: () => `
      <div class="form-grid">
        <div class="field"><label>点「打开 AI」默认去哪家</label>
          <div class="pill-select" data-pill="wz_jump">
            <button type="button" data-v="claude" class="on">Claude</button>
            <button type="button" data-v="chatgpt">ChatGPT</button>
          </div><input type="hidden" id="f_wz_jump" value="claude"></div>
        <div class="field"><label>Claude 订阅档位</label>
          <div class="pill-select" data-pill="wz_plan">
            <button type="button" data-v="pro">Pro</button>
            <button type="button" data-v="max5" class="on">Max 5×</button>
            <button type="button" data-v="max20">Max 20×</button>
          </div><input type="hidden" id="f_wz_plan" value="max5">
          <div class="hint">只用来给调度器一个起始配额，之后它会按实际情况自己校准。</div></div>
        ${WZ.row("通常几点开始工作", "wz_ws", "09:00")}
        ${WZ.row("通常几点收工", "wz_we", "23:00", "text", "自动任务会安排在你收工之后，避开你的 5 小时窗口")}
      </div>
      <div class="field wide"><label>让它自动做哪些事</label>
        <div class="wz-checks">
          <label class="wz-check"><input type="checkbox" id="wz_k_audit" checked> 🩺 全库体检（推荐必开）</label>
          <label class="wz-check"><input type="checkbox" id="wz_k_brainstorm" checked> 💡 头脑风暴</label>
          <label class="wz-check"><input type="checkbox" id="wz_k_gap" checked> 🔍 文献缺口扫描</label>
          <label class="wz-check"><input type="checkbox" id="wz_k_method" checked> 🔬 新方法扫描</label>
          <label class="wz-check"><input type="checkbox" id="wz_k_data" checked> 🗃 新数据整理（只给描述与链接）</label>
          <label class="wz-check"><input type="checkbox" id="wz_k_gh" checked> 🛰 GitHub / 文献雷达</label>
        </div></div>
      ${WZ.note("这些任务由云端的 Claude 在你睡觉时跑，走你的订阅，<b>不花 API 的钱</b>。调度器会按周预算控制用量，并在你被限流时立刻减半。")}`,
    after: () => { UI.bindPills($("#wz")); },
    collect: () => {
      const kinds = [];
      if (WZ.v("wz_k_brainstorm")) kinds.push("brainstorm");
      if (WZ.v("wz_k_gap")) kinds.push("gap-scan");
      if (WZ.v("wz_k_method")) kinds.push("method-scan");
      if (WZ.v("wz_k_data")) kinds.push("data-scan");
      if (WZ.v("wz_k_audit")) kinds.push("audit");
      if (WZ.v("wz_k_gh")) kinds.push("github-radar");
      WZ.draft.config.ai = {
        default_jump: WZ.v("f_wz_jump") || "claude",
        plan: WZ.v("f_wz_plan") || "max5",
        work_start: WZ.v("wz_ws") || "09:00", work_end: WZ.v("wz_we") || "23:00",
      };
      WZ.draft.config.autotasks = Object.assign({}, S.config.autotasks, { kinds, enabled: kinds.length > 0 });
    },
  },

  /* ---------------------------------------------------------- 7 学术偏好 */
  {
    icon: "📚", title: "学术偏好", sub: "几个阈值，之后在设置里随时能改。",
    body: () => `
      <div class="form-grid">
        ${WZ.row("每周读文献目标（篇）", "wz_goal", "5", "number")}
        ${WZ.row("今日页显示未来多少天的截止", "wz_hor", "45", "number")}
        ${WZ.row("稿件多少天没动算「停滞」", "wz_stale", "7", "number")}
        ${WZ.row("投出去多少天没消息该催稿", "wz_chase", "120", "number", "到了这个天数，今日页会提醒并备好催稿信草稿")}
      </div>
      ${WZ.note("提示：稿件库里每次投稿、被拒、R&R、转投都记一条事件——这是整个系统最值得坚持的习惯。有了它，期刊库里「你在这家刊的真实审稿周期」和复盘里的耗时统计都会自动长出来。")}`,
    after: () => {
      $("#wz_goal").value = (S.config.reading || {}).weekly_goal || 5;
      $("#wz_hor").value = S.config.today_horizon_days || 45;
      $("#wz_stale").value = S.config.stale_manuscript_days || 7;
      $("#wz_chase").value = S.config.chase_days || 120;
    },
    collect: () => {
      WZ.draft.config.reading = Object.assign({}, S.config.reading, { weekly_goal: Number(WZ.v("wz_goal")) || 5 });
      WZ.draft.config.today_horizon_days = Number(WZ.v("wz_hor")) || 45;
      WZ.draft.config.stale_manuscript_days = Number(WZ.v("wz_stale")) || 7;
      WZ.draft.config.chase_days = Number(WZ.v("wz_chase")) || 120;
    },
  },

  /* ---------------------------------------------------------- 8 隐私安全 */
  {
    icon: "🔒", title: "隐私与安全", sub: "决定什么留在本机、什么能被远程访问。",
    body: () => `
      <div class="opt">
        <label class="opt-h"><input type="checkbox" id="wz_remote"> <b>允许手机 / 其它设备访问</b></label>
        <div class="opt-d">不开的话工作台只在这台电脑上可用，最安全。开了才能用手机看（配合 Tailscale）。</div>
        <div class="opt-sub">
          <div class="field"><label>远程访问码<span class="req">·必填</span></label>
            <input type="password" id="wz_code" placeholder="自己设一串，别人猜不到的">
            <div class="hint">远程访问必须输入它；在本机打开不需要。</div></div>
          <label class="opt-h sm"><input type="checkbox" id="wz_ro" checked> 远程默认<b>只读</b>，要改东西得手动解锁</label>
        </div>
      </div>
      <div class="opt">
        <label class="opt-h"><input type="checkbox" id="wz_enc"> <b>加密存进 OneDrive 的长期备份</b></label>
        <div class="opt-d">那份备份包含你全部研究进展。加密后需要口令才能恢复——<b style="color:var(--red)">口令丢了就真的打不开</b>，请自己保管好（存进密码管理器）。</div>
        <div class="opt-sub">
          <div class="field"><label>备份口令</label><input type="password" id="wz_encpw" placeholder="至少 8 位"></div>
        </div>
      </div>
      <div class="opt">
        <label class="opt-h"><input type="checkbox" id="wz_life" checked> <b>生活数据只留本机</b></label>
        <div class="opt-d">饮食 / 运动 / 开支不进 Git、不上传任何地方。建议保持勾选。</div>
      </div>`,
    after: () => {
        const sync = () => {
          $("#wz_remote").closest(".opt").classList.toggle("on", $("#wz_remote").checked);
          $("#wz_enc").closest(".opt").classList.toggle("on", $("#wz_enc").checked);
          WZ.steps[WZ.step].required = [];
          if ($("#wz_remote").checked) WZ.steps[WZ.step].required.push({ id: "wz_code", label: "远程访问码" });
          if ($("#wz_enc").checked) WZ.steps[WZ.step].required.push(
            { id: "wz_encpw", label: "备份口令（至少 8 位）", test: v => v.length >= 8 });
        };
        $("#wz_remote").onchange = sync; $("#wz_enc").onchange = sync; sync();
      },
    collect: () => {
      WZ.draft.config.security = {
        remote_enabled: WZ.v("wz_remote"), remote_readonly: WZ.v("wz_ro"),
        encrypt_backup: WZ.v("wz_enc"), life_local_only: WZ.v("wz_life"),
      };
      const s = {};
      if (WZ.v("wz_code")) s.remote = { access_code: WZ.v("wz_code") };
      if (WZ.v("wz_encpw")) s.backup = { passphrase: WZ.v("wz_encpw") };
      if (Object.keys(s).length) Object.assign(WZ.draft.secrets, s);

    },
  },

  /* ---------------------------------------------------------- 9 导入 */
  {
    icon: "📥", title: "导入你现有的表格", sub: "期刊清单、投稿记录……有就拖进来，没有就跳过，以后随时能导。",
    body: () => `
      <div class="form-grid">
        <div class="field"><label>选择文件（.xlsx / .csv）</label><input type="file" id="wz_file" accept=".xlsx,.xlsm,.csv,.tsv"></div>
        <div class="field"><label>导入到</label>
          <div class="pill-select" data-pill="wz_coll">
            <button type="button" data-v="manuscripts" class="on">稿件库</button>
            <button type="button" data-v="published">论文库</button>
            <button type="button" data-v="conferences">会议</button>
            <button type="button" data-v="reading">文献</button>
          </div><input type="hidden" id="f_wz_coll" value="manuscripts"></div>
      </div>
      <div id="wz_prev"></div>
      ${WZ.note("第一版会把表里的列名原样存成字段名。你之后把表发给我、说清楚哪列对应什么，我统一改一次就行——先把数据弄进来最重要。")}`,
    after: () => {
      UI.bindPills($("#wz"));
      $("#wz_file").onchange = async () => {
        const f = $("#wz_file").files[0]; if (!f) return;
        const buf = await f.arrayBuffer(); const by = new Uint8Array(buf);
        let bin = ""; for (let i = 0; i < by.length; i += 8192) bin += String.fromCharCode.apply(null, by.subarray(i, i + 8192));
        const r = await API.post("table/upload", { name: f.name, base64: btoa(bin) });
        if (!r.ok) return WZ.say("wz_prev", false, "读取失败");
        $("#wz_prev").innerHTML = `<div class="small" style="margin-top:8px">共 <b>${r.total}</b> 行；列名：
          ${r.headers.map(h => `<span class="badge">${esc(h)}</span>`).join("")}</div>
          <div class="scroll-x" style="margin-top:6px"><table class="tbl">
          <tr>${r.headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr>
          ${r.rows.slice(0, 5).map(row => `<tr>${row.map(c => `<td>${esc(String(c).slice(0, 30))}</td>`).join("")}</tr>`).join("")}
          </table></div>
          <button class="btn primary sm" style="margin-top:8px" id="wz_imp">导入这 ${r.total} 行</button>
          <span class="wz-result" id="wz_impres"></span>`;
        $("#wz_imp").onclick = async () => {
          const res = await API.post("table/import", {
            path: r.path, collection: $("#f_wz_coll").value, dedup_key: "title",
          });
          WZ.say("wz_impres", true, `新增 ${res.created} 条，更新 ${res.updated} 条`);
          const b = await API.bootstrap(); S.data = b.data;
        };
      };
    },
  },

  /* ------------------------------------------- 9.4 Overleaf（可跳过） */
  {
    icon: "📝", title: "Overleaf 写作进展（可跳过）", skippable: true,
    sub: "如果你用 Overleaf 写论文，工作台可以每天自动读出「今天改了哪几节、增删多少行、字数变化」，替你把进展记下来。没有付费版就跳过，不影响任何功能。",
    body: () => `
      ${WZ.note("这一步需要 <b>Overleaf 付费版</b>——只有付费版才开放 Git 接入。免费版请直接跳过：" +
        "你仍然可以在每篇稿件上填 Overleaf 链接做一键跳转，只是没有自动进展记录。<br><br>" +
        "拿 token 的路径：Overleaf 网页 → 右上角头像 → <b>Account Settings</b> → 左侧 <b>Git Integration</b> → " +
        "<b>Generate token</b>，会得到一串 <code>olp_</code> 开头的字符（不是你的登录密码）。")}
      <div class="form-grid" style="margin-top:12px">
        <div class="field"><label>Overleaf 登录邮箱</label>
          <input id="wz_ole" placeholder="you@example.com"></div>
        <div class="field"><label>Git token</label>
          <input id="wz_olt" type="password" placeholder="olp_…">
          <div class="hint">只存本机 <code>local/secrets.json</code>，不进 Git、不进备份。</div></div>
      </div>
      <div class="small muted" style="margin-top:10px">
        填好之后，去每篇稿件的「Overleaf 项目地址」里粘上项目链接（形如
        <code>https://www.overleaf.com/project/xxxxx</code>），工作台每天早上会自动同步一次。</div>
      <span class="wz-result" id="wz_olres"></span>`,
    after: () => {
      const st = S.overleafStatus || {};
      if (st.email && $("#wz_ole")) $("#wz_ole").value = st.email;
    },
    collect: () => {
      const o = WZ.prune({ email: WZ.v("wz_ole"), token: WZ.v("wz_olt") });
      if (Object.keys(o).length) WZ.draft.secrets.overleaf = o;
    },
  },

  /* --------------------------------------------- 9.5 AI 直连（可跳过） */
  {
    icon: "🔌", title: "AI 直连 API（可跳过）", skippable: true,
    sub: "这一步跟前面的「打开 Claude / ChatGPT」不是一回事——那两个是跳到网页或桌面软件，这里是让工作台自己去调接口。不填也完全不影响使用。",
    body: () => `
      ${WZ.note("先说清楚花钱的事：API 是<b>按量付费</b>的，跟你的网页订阅是两个钱包，订阅再贵也不会覆盖 API 的账单。" +
        "工作台的自动任务（夜里的头脑风暴、漏洞扫描、周报）默认走<b>订阅</b>那条路，不花 API 钱，这一步留空它们照样跑。" +
        "填了 API 只多一件事：你可以在工作台里直接问、让它直接改，不用来回复制粘贴。")}
      <div class="form-grid" style="margin-top:12px">
        <div class="field"><label>默认用哪家</label>
          <div class="pill-select" data-pill="wz_aip">
            <button type="button" data-v="anthropic" class="on">Claude</button>
            <button type="button" data-v="openai">ChatGPT</button>
            <button type="button" data-v="deepseek">DeepSeek</button>
          </div><input type="hidden" id="f_wz_aip" value="anthropic"></div>
        <div class="field"></div>
        <div class="field wide"><label>Anthropic API Key</label>
          <input id="wz_ak" type="password" placeholder="sk-ant-…（console.anthropic.com → API keys）">
          <div class="hint">留空即不启用。只存本机 <code>local/secrets.json</code>，不进 Git、不进备份。</div></div>
        <div class="field"><label>Claude 模型</label><input id="wz_am" placeholder="留空用默认"></div>
        <div class="field"><label>Anthropic 中转地址（可留空）</label><input id="wz_ab" placeholder="https://…"></div>
        <div class="field wide"><label>OpenAI API Key</label>
          <input id="wz_ok" type="password" placeholder="sk-…（platform.openai.com → API keys）"></div>
        <div class="field"><label>ChatGPT 模型</label><input id="wz_om" placeholder="留空用默认"></div>
        <div class="field"><label>OpenAI 中转地址（可留空）</label><input id="wz_ob" placeholder="https://…"></div>
        <div class="field wide"><label>DeepSeek API Key</label>
          <input id="wz_dk" type="password" placeholder="sk-…（platform.deepseek.com → API keys）"></div>
        <div class="field"><label>DeepSeek 模型</label><input id="wz_dm" placeholder="留空用 deepseek-chat"></div>
        <div class="field"><label>DeepSeek 中转地址（可留空）</label><input id="wz_db" placeholder="https://…"></div>
      </div>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn sm" id="wz_ailist">列出可用模型</button>
        <button class="btn sm" id="wz_aitest">测一下通不通</button>
      </div>
      <span class="wz-result" id="wz_aires"></span>`,
    after: () => {
      UI.bindPills($("#wz"));
      const save = () => API.post("secrets/merge", { ai: WZ.aiPayload() });
      $("#wz_ailist").onclick = async () => {
        await save();
        WZ.say("wz_aires", true, "查询中…");
        const r = await API.get("ai/models?provider=" + $("#f_wz_aip").value);
        if (!r.ok) return WZ.say("wz_aires", false, r.detail || "查不到");
        WZ.say("wz_aires", true, "可用模型：" + (r.models || []).slice(0, 8).join("、") +
          ((r.models || []).length > 8 ? " …" : "") + "（挑一个填进上面的模型栏）");
      };
      $("#wz_aitest").onclick = async () => {
        await save();
        WZ.say("wz_aires", true, "测试中…");
        const r = await API.post("ai/test", { provider: $("#f_wz_aip").value });
        WZ.say("wz_aires", !!r.ok, r.detail || (r.ok ? "通了" : "失败"));
      };
    },
    collect: () => { WZ.draft.secrets.ai = WZ.aiPayload(); },
  },

  /* ---------------------------------------------------------- 10 完成 */
  {
    icon: "✅", title: "核对一下，就可以开始了", skippable: false,
    sub: "下面是刚才填的内容。有不对的可以退回去改，也可以完成后在设置页随时改。",
    body: () => {
      const c = S.config, d = S.device, st = S.secretsStatus || {};
      const yes = v => v ? `<span class="ok-dot">✓</span>` : `<span class="no-dot">—</span>`;
      return `<table class="tbl wz-sum">
        <tr><td>称呼 / 领域</td><td>${esc((c.profile || {}).name || "—")} · ${esc((c.profile || {}).field || "—")}</td></tr>
        <tr><td>城市 / 时区</td><td>${esc((c.profile || {}).city || "—")} · ${esc(timeZone())}</td></tr>
        <tr><td>关键词</td><td>${((c.profile || {}).keywords || []).map(k => `<span class="badge">${esc(k)}</span>`).join("") || "—"}</td></tr>
        <tr><td>本机 / 论文目录</td><td>${esc(d.device_name || "—")} · ${esc(d.paper_root || "未设置")}</td></tr>
        <tr><td>OneDrive 备份</td><td>${esc(d.onedrive_backup_dir || "未设置（长期备份不会生成）")}</td></tr>
        <tr><td>GitHub</td><td>${yes(st.github_token)} ${esc((c.git || {}).remote || "未设置")}</td></tr>
        <tr><td>日历订阅</td><td>${((c.calendar || {}).ics || []).length} 个 · 农历 ${((c.calendar || {}).lunar ? "开" : "关")} · 天气 ${((c.calendar || {}).weather ? "开" : "关")}</td></tr>
        <tr><td>推送</td><td>钉钉 ${yes(st.dingtalk)} 邮件 ${yes(st.email)} · ${esc((c.push || {}).weekly_cron || "MON 08:00")}</td></tr>
        <tr><td>自动任务</td><td>${((c.autotasks || {}).kinds || []).length} 类 · 作息 ${esc((c.ai || {}).work_start || "")}–${esc((c.ai || {}).work_end || "")}</td></tr>
        <tr><td>远程访问</td><td>${(c.security || {}).remote_enabled ? "已开启 " + yes(st.remote_code) + ((c.security || {}).remote_readonly ? " · 默认只读" : " · 可写") : "未开启（只在本机可用）"}</td></tr>
        <tr><td>数据量</td><td>${["manuscripts", "journals", "reading", "conferences"].map(k => `${esc(k)} ${rows(k).length}`).join(" · ")}</td></tr>
      </table>
      ${WZ.note("点「完成设置」后：工作台会做第一次备份、把内容推到你的私有仓库（如果配了），并跑一次全库体检让你看到系统是活的。")}`;
    },
  },
];
