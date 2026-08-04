const FIELD_LABEL = {
  title: "标题 / 名称", deadline: "投稿截止", meeting_date: "会议日期", location: "地点",
  link: "官网链接", submit_link: "投稿链接", notify_date: "通知日期", fee: "费用",
  funding: "资助", status_note: "状态备注", cfp_open: "征稿开放", body: "备注 / 正文",
  current_journal: "当前期刊", stage_note: "阶段", coauthors: "合作者",
  next_action: "下一步", next_action_due: "下一步截止",
  journal: "期刊", year: "年份", doi: "DOI", authors: "作者",
  question: "问题背景", method: "方法", findings: "结论",
};

/* 设置与教程：装修模式 / 设备与路径 / Git / 备份时光机 / 表格导入 / 完整教程 */

VIEWS.settings = () => {
  const d = S.device || {}, c = S.config || {}, g = S.git || {};
  const tz = timeZone();

  const tutorial = UI.card("set-tutorial", "完整使用教程", "从零开始", `
    <div class="tut-body" style="padding:0">
    <p><b>1 · 它是什么</b><br>一个跑在你自己电脑上的学术工作台。数据是一堆 Markdown 文件（不是数据库），所以就算哪天不用这个界面了，你的记录用任何编辑器都能打开。</p>
    <p><b>2 · 三种存放位置，各有分工</b><br>
      · <code>data/</code>：学术数据，进 Git 仓库，两台电脑（Win/Mac）靠它同步，云端的 Claude 也靠它读写；<br>
      · <code>local/</code>：生活数据、密钥、备份、本机路径——<b>永不进 Git</b>；<br>
      · 大附件（审稿 PDF、数据集）放在 OneDrive 或本地文件夹，工作台只存路径引用。</p>
    <p><b>3 · 每天怎么用</b><br>早上打开「今日」→ 看逾期与近期截止、稿件下一步、AI 夜里的产出、该复习的文献 → 处理完顺手记一篇文献（闯关加经验）→ 有重活就点 🤖 写进 Claude 信箱。</p>
    <p><b>4 · 投稿流程怎么记</b><br>在稿件卡上点「＋ 记录事件」：投稿、拒稿、R&R、转投各记一条。阶段会自动跟着变，期刊库里「你的真实审稿周期」也会自动算出来，复盘时的耗时统计同理。<b>这是整个系统最值得坚持的一个习惯。</b></p>
    <p><b>5 · AI 两条通道</b><br>重活 → Claude 信箱（能直接改文件）；小问题 → 预填跳转 Claude 或 ChatGPT 网页。两条都走订阅，不花 API 钱。</p>
    <p><b>6 · 额度调度器</b><br>它替你把「用不完会蒸发」的订阅额度花在有用的地方，同时避免你自己要用时被挡。三个开关：今晚放开跑 / 本周静默 / 我被挡住了。</p>
    <p><b>7 · 备份与恢复</b><br>每 30 分钟一次滚动快照（保留 7 天，自动清理）；每天中午和晚上各一次长期备份写进 OneDrive 文件夹（永久保留）。错过的会在下次启动时补做。下面「时光机」里可以一键恢复到任意快照，恢复前会自动先存一份当前状态。</p>
    <p><b>8 · 快捷键</b><br><kbd>c</kbd> 快速捕捉 · <kbd>Cmd/Ctrl+K</kbd> 全局搜索 · <kbd>Esc</kbd> 关闭弹窗</p>
    <p><b>9 · 想改界面</b><br>下面「装修模式」可以开关模块、改阈值、换主题。想要新功能就在 Cowork 里直接说，我改代码后 Git 一同步，两台电脑都更新了。</p>
    </div>`, { icon: "📖", defaultOpen: false });

  const deco = UI.card("set-deco", "装修模式", "自定义", `
    <div class="form-grid">
      <div class="field"><label>工作台名称</label>
        <input id="cfg_btitle" value="${esc((c.brand || {}).title || "")}" placeholder="学术工作台"></div>
      <div class="field"><label>副标题</label>
        <input id="cfg_bsub" value="${esc((c.brand || {}).sub || "")}" placeholder="Scholar Workspace"></div>
      <div class="field"><label>今日页显示未来几天的截止</label>
        <input type="number" id="cfg_horizon" value="${c.today_horizon_days || 45}"></div>
      <div class="field"><label>稿件停滞判定（天）</label>
        <input type="number" id="cfg_stale" value="${c.stale_manuscript_days || 7}"></div>
      <div class="field"><label>每周读文献目标（篇）</label>
        <input type="number" id="cfg_goal" value="${(c.reading || {}).weekly_goal || 5}"></div>
      <div class="field"><label>AI 跳转默认</label>
        <div class="pill-select" data-pill="cfg_jump">
          <button type="button" data-v="claude" class="${((c.ai || {}).default_jump || "claude") === "claude" ? "on" : ""}">Claude</button>
          <button type="button" data-v="chatgpt" class="${(c.ai || {}).default_jump === "chatgpt" ? "on" : ""}">ChatGPT</button>
        </div><input type="hidden" id="f_cfg_jump" value="${(c.ai || {}).default_jump || "claude"}"></div>
      <div class="field"><label>主题色</label><input type="color" id="cfg_accent" value="${(c.theme || {}).accent || "#3b5bdb"}"></div>
      <div class="field"><label>深浅色</label>
        <div class="pill-select" data-pill="cfg_mode">
          <button type="button" data-v="light" class="${(c.theme || {}).mode !== "dark" ? "on" : ""}">浅色</button>
          <button type="button" data-v="dark" class="${(c.theme || {}).mode === "dark" ? "on" : ""}">深色</button>
        </div><input type="hidden" id="f_cfg_mode" value="${(c.theme || {}).mode || "light"}"></div>
    </div>
    <div class="hr"></div>
    <div class="tiny muted" style="margin-bottom:6px">显示哪些模块（取消勾选即从侧边栏隐藏，数据不会丢）</div>
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      ${SECTIONS.filter(s => !["today", "settings"].includes(s.id)).map(s => `
        <label class="small"><input type="checkbox" data-sec="${s.id}"
          ${(c.sections || []).includes(s.id) ? "checked" : ""}> ${s.icon} ${s.name}</label>`).join("")}
    </div>
    <div style="margin-top:11px"><button class="btn primary" id="cfgSave">保存设置</button></div>`, { icon: "🎨" });

  const device = UI.card("set-device", "本机设置", "只存这台电脑", `
    <div class="small muted" style="margin-bottom:8px">时区自动检测：<b>${esc(tz)}</b>（你换地方它会自己变，不用手动改）。
      这些路径每台机器不同，所以存在 <code>local/device.json</code>，不会同步。</div>
    <div class="form-grid">
      <div class="field"><label>本机名称</label><input id="dev_name" value="${esc(d.device_name || "")}"></div>
      <div class="field"><label>论文根目录</label><input id="dev_paper" value="${esc(d.paper_root || "")}"
        placeholder="Mac: /Users/你/Papers ；Win: D:\\Papers"></div>
      <div class="field wide"><label>OneDrive 长期备份目录</label><input id="dev_od" value="${esc(d.onedrive_backup_dir || "")}"
        placeholder="Mac: /Users/你/OneDrive/工作台备份 ；Win: C:\\Users\\你\\OneDrive\\工作台备份"></div>
      <div class="field wide"><label>Zotero 存储目录</label>
        <input id="dev_zroot" value="${esc(d.zotero_root || "")}"
          placeholder="Mac: /Users/你/Zotero ；Win: C:\\Users\\你\\Zotero">
        <div class="hint">填了之后，文献索引里的本地 PDF 在<b>每台机器上都能打开</b> ——
          索引存的是相对 <code>storage/</code> 的路径，靠这个根目录拼回来。
          不填的话只在导入那台机器上打得开。</div></div>
      <div class="field"><label>每日备份时间（逗号分隔）</label><input id="dev_times" value="${esc((d.daily_backup_times || []).join(","))}"></div>
      <div class="field"><label>滚动快照间隔（分钟）</label><input type="number" id="dev_roll" value="${d.rolling_minutes || 30}"></div>
      <div class="field"><label>滚动快照保留（天）</label><input type="number" id="dev_keep" value="${d.rolling_keep_days || 7}"></div>
    </div>
    <div style="margin-top:11px"><button class="btn primary" id="devSave">保存本机设置</button></div>`, { icon: "💻" });

  const gitCard = UI.card("set-git", "Git 同步（Win ↔ Mac ↔ 云端 Claude）", "", `
    ${g.repo ? `<div class="small">分支 <b>${esc(g.branch || "")}</b> · 未提交改动 <b>${g.dirty || 0}</b> 处<br>
        远程：<code>${esc(g.remote || "（未设置）")}</code><br>
        最近提交：${esc(g.last_commit || "—")}</div>
      ${g.never_pushed
        ? `<div class="warn-box" style="margin-top:8px">⚠️ <b>从来没成功推送过</b>——本地 ${g.ahead || 0} 个提交还全在这台电脑上，
             GitHub 那边是空的。云端 Claude、双机同步、自动任务在推上去之前都不会真的运行。
             点下面的「立即同步」；要是还失败，错误会记在 <code>local/sync.log</code> 里。</div>`
        : (g.ahead ? `<div class="warn-box" style="margin-top:8px">⚠️ 本地有 <b>${g.ahead}</b> 个提交还没推上去（上游 <code>${esc(g.upstream || "")}</code>）。</div>` : "")}
      ${(g.log_tail || []).length
        ? `<details style="margin-top:8px"><summary class="small muted" style="cursor:pointer">最近几次同步记录</summary>
             <pre class="small" style="white-space:pre-wrap;margin:6px 0 0">${esc((g.log_tail || []).join("\n"))}</pre></details>`
        : ""}`
      : `<div class="small muted">还不是 Git 仓库。填一个私有仓库地址后点「初始化」，这台电脑就接上了。</div>`}
    <div class="form-grid" style="margin-top:9px">
      <div class="field wide"><label>私有仓库地址（GitHub）</label>
        <input id="git_remote" value="${esc(g.remote || (c.git || {}).remote || "")}" placeholder="https://github.com/你的用户名/scholar-workspace.git">
        <div class="hint">建议用 HTTPS 地址；首次推送时用 GitHub 的 Personal Access Token 当密码。</div></div>
      <div class="field"><label>GitHub 用户名</label><input id="gh_user" placeholder="仅存本机"></div>
      <div class="field"><label>Personal Access Token</label><input id="gh_token" type="password" placeholder="仅存本机 local/secrets.json">
        <div class="hint"><a href="https://github.com/settings/tokens/new?scopes=repo&description=%E5%AD%A6%E6%9C%AF%E5%B7%A5%E4%BD%9C%E5%8F%B0" target="_blank" rel="noopener">去 GitHub 生成一个 ↗</a>
          （已经替你勾好 <code>repo</code> 权限，有效期建议选 No expiration）</div></div>
    </div>
    <div class="small muted" style="margin-top:7px">
      ${g.remote ? `<a href="${esc(String(g.remote).replace(/\.git$/, ""))}" target="_blank" rel="noopener">打开这个仓库 ↗</a> · ` : ""}
      <a href="https://github.com/new?name=workspace&visibility=private" target="_blank" rel="noopener">新建一个私有仓库 ↗</a>
      <span style="opacity:.8"> —— 建仓库时<b>务必勾 Private</b>，你的稿件和审稿记录都会推上去。</span>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:11px">
      <button class="btn primary" id="gitInit">${g.repo ? "更新远程地址" : "初始化仓库"}</button>
      <button class="btn" id="gitSync">立即同步（pull → commit → push）</button>
      <button class="btn ghost" id="ghSave">保存凭据到本机</button>
    </div>
    <div class="small muted" style="margin-top:9px">
      学术数据（<code>data/</code>）会同步；生活数据、密钥、备份（<code>local/</code>）不会。
      云端的 Claude 也是通过这个仓库读写你的工作台——这就是自动任务能在你笔记本合着时干活的原因。</div>`, { icon: "🔗" });

  const cal = c.calendar || {};
  const icsArr = (cal.ics || []).filter(Boolean);
  const icsErrs = S.icsErrors || [];
  const icsN = (S.icsEvents || []).length;
  const calCard = UI.card("set-cal", "日历订阅（Outlook / Google / 苹果日历）",
    icsArr.length ? `${icsArr.length} 个源 · ${icsN} 条日程` : "未订阅", `
    <div class="small muted" style="margin-bottom:10px">
      订阅之后，你在 Outlook 或 Google 日历里的会议会直接出现在右上角日历和「今日」页，
      和工作台自己的日程、投稿截止、会议倒计时排在一起。<b>只读</b>——工作台永远不会往你的日历里写东西。</div>

    <details style="margin-bottom:11px"><summary class="small" style="cursor:pointer">📎 订阅地址去哪拿（三家的步骤，点开看）</summary>
      <div class="small muted" style="margin-top:9px;line-height:1.8">
        <b>Outlook（学校 / 公司邮箱）</b> ——
        <a href="https://outlook.office.com/calendar/options/calendar/SharedCalendars" target="_blank" rel="noopener">直接打开发布设置 ↗</a><br>
        或者手动点：日历页右上角 ⚙️ → 日历 → 共享日历 → 「发布日历」→ 选中日历、权限选
        <b>可以查看所有详细信息</b> → 发布 → 复制 <b>ICS 结尾</b>那条（不是 HTML 那条）。<br>
        <span style="opacity:.85">要是根本看不到「发布日历」这一项，那是学校 IT 在 Exchange 里关掉了对外发布，
        大学邮箱挺常见的，不是你操作错了。绕法：把这个日历共享到你自己的私人 Outlook/Google 账号，再从那边拿订阅地址。</span>
        <br><br>
        <b>Google 日历</b> ——
        <a href="https://calendar.google.com/calendar/u/0/r/settings" target="_blank" rel="noopener">直接打开日历设置 ↗</a><br>
        左栏「我的日历的设置」下点日历名字 → 整合日历 → 复制 <b>iCal 格式的私密地址</b>。
        <br><br>
        <b>苹果 / iCloud 日历</b> —— Mac 上「日历」App 里右键那个日历 → 共享设置 → 勾上<b>公开日历</b> → 复制地址，
        然后把开头的 <code>webcal://</code> 改成 <code>https://</code>（粘进来我会自动帮你改）。
        <br><br>
        <b>三家都一样的一件事</b>：这条地址等于一把没有密码的钥匙，谁拿到都能看你全部日程。
        别贴到任何公开地方。它只写进这台电脑的 <code>data/config.json</code>。
      </div>
    </details>

    <div class="form-grid">
      <div class="field wide"><label>订阅地址 1</label>
        <input id="cal_ics1" value="${esc(icsArr[0] || "")}"
          placeholder="https://outlook.office365.com/owa/calendar/…/reachcalendar.ics"></div>
      <div class="field wide"><label>订阅地址 2（可留空）</label>
        <input id="cal_ics2" value="${esc(icsArr[1] || "")}"
          placeholder="https://calendar.google.com/calendar/ical/…/basic.ics"></div>
      <div class="field"><label>多久拉一次（分钟）</label>
        <input type="number" id="cal_refresh" min="5" value="${Number(cal.refresh_min) || 15}"></div>
      <div class="field"><label>农历 / 节气</label>
        <div class="pill-select" data-pill="calLunar">
          <button type="button" data-v="1" class="${cal.lunar === false ? "" : "on"}">显示</button>
          <button type="button" data-v="0" class="${cal.lunar === false ? "on" : ""}">不显示</button>
        </div><input type="hidden" id="f_calLunar" value="${cal.lunar === false ? 0 : 1}"></div>
      <div class="field"><label>天气</label>
        <div class="pill-select" data-pill="calWx">
          <button type="button" data-v="1" class="${cal.weather === false ? "" : "on"}">显示</button>
          <button type="button" data-v="0" class="${cal.weather === false ? "on" : ""}">不显示</button>
        </div><input type="hidden" id="f_calWx" value="${cal.weather === false ? 0 : 1}"></div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:11px">
      <button class="btn primary" id="calSave">保存并立即同步</button>
      <button class="btn" id="calTest">只测一下地址通不通</button>
      <button class="btn" id="calSyncNow" ${icsArr.length ? "" : "disabled"}>立即同步一次</button>
      <span class="spacer"></span>
      <span class="small muted">${icsArr.length
        ? `当前已拉到 ${icsN} 条日程${icsErrs.length ? ` · <b style="color:var(--red)">${icsErrs.length} 个源失败</b>` : ""}`
        : "还没订阅任何日历"}</span>
    </div>
    ${icsErrs.length ? `<div class="warn-box" style="margin-top:10px"><b>拉取失败</b><br>
      ${icsErrs.map(e => `<code>${esc(String(e.url || "").slice(0, 70))}…</code> —— ${esc(e.detail || "连不上")}`).join("<br>")}
      <div style="margin-top:6px">常见原因：地址复制少了一截、发布后又被撤销了、或者这台电脑挂了代理连不出去。</div></div>` : ""}
    <div id="calOut" class="small" style="margin-top:9px"></div>`, { icon: "📅" });

  const ai = S.aiStatus || { providers: [], usage: {} };
  const aiCard = UI.card("set-ai", "AI 直连 API（可选）", ai.any ? "已启用" : "未启用", `
    <div class="small muted" style="margin-bottom:10px">
      跟顶栏那两个「打开 Claude / ChatGPT」不是一回事：那两个是跳到网页或桌面软件；
      这里是让工作台自己调接口。<b>API 按量付费，跟网页订阅是两个钱包。</b>
      自动任务默认走订阅，不填这里也照跑；填了只是多一条「在工作台里直接问」的路。</div>
    <div class="form-grid">
      <div class="field"><label>默认用哪家</label>
        <div class="pill-select" data-pill="aiProv">
          <button type="button" data-v="anthropic" class="${ai.provider !== "openai" ? "on" : ""}">Claude</button>
          <button type="button" data-v="openai" class="${ai.provider === "openai" ? "on" : ""}">ChatGPT</button>
          <button type="button" data-v="deepseek" class="${ai.provider === "deepseek" ? "on" : ""}">DeepSeek</button>
        </div><input type="hidden" id="f_aiProv" value="${esc(ai.provider || "anthropic")}"></div>
      <div class="field"></div>
      ${(ai.providers || []).map(pv => `
        <div class="field wide"><label>${esc(pv.name)} API Key ${pv.configured ? "（已配，留空表示不改）" : ""}</label>
          <input id="ai_key_${pv.id}" type="password" placeholder="${esc(pv.key_hint)}"></div>
        <div class="field"><label>模型</label>
          <input id="ai_model_${pv.id}" value="${esc(pv.model || "")}" placeholder="留空用默认"></div>
        <div class="field"><label>中转地址（可留空）</label>
          <input id="ai_base_${pv.id}" value="${esc(pv.base || "")}" placeholder="https://…"></div>`).join("")}
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:11px">
      <button class="btn primary" id="aiSave">保存</button>
      <button class="btn" id="aiModels">列出可用模型</button>
      <button class="btn" id="aiTest">测一下通不通</button>
      <span class="spacer"></span>
      <span class="small muted">近 30 天：${(ai.usage || {}).calls || 0} 次调用 ·
        进 ${((ai.usage || {}).in || 0).toLocaleString()} / 出 ${((ai.usage || {}).out || 0).toLocaleString()} tokens</span>
    </div>
    <div id="aiOut" class="small" style="margin-top:9px"></div>`, { icon: "🔌" });

  const ch = ((c.push || {}).channels) || {};
  const sst = S.secretsStatus || {};
  const pushCard = UI.card("set-push", "推送渠道", ch.dingtalk ? "钉钉已开" : "未开启", `
    <div class="small muted" style="margin-bottom:9px">周一早报、每日简报、以及需要你拍板的提醒会推到这里。
      推送凭据只存在这台电脑上，不进 Git 也不进备份。<br>
      钉钉的 webhook 在手机或电脑客户端里拿：建一个只有自己的群 → 群设置 → 智能群助手 → 添加机器人 → 自定义 →
      安全设置勾<b>加签</b> → 复制 Webhook 地址和密钥。<a href="https://open.dingtalk.com/document/orgapp/custom-robot-access" target="_blank" rel="noopener">官方说明 ↗</a></div>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px">
      <label class="small"><input type="checkbox" id="ch_ding" ${ch.dingtalk ? "checked" : ""}>
        钉钉 ${sst.dingtalk ? (sst.dingtalk_signed ? "（已配 · 加签）" : "（已配 · 未加签）") : "（未配 webhook）"}</label>
      <label class="small"><input type="checkbox" id="ch_mail" ${ch.email ? "checked" : ""}>
        邮件 ${sst.email ? "（已配）" : "（未配）"}</label>
      <label class="small"><input type="checkbox" id="ch_custom" ${ch.custom ? "checked" : ""}>
        自定义 webhook</label>
    </div>
    <div class="form-grid">
      <div class="field"><label>周报推送时间</label>
        <input id="push_cron" value="${esc((c.push || {}).weekly_cron || "MON 08:00")}" placeholder="MON 08:00"></div>
      <div class="field"><label>每天早上推一份简报</label>
        <div class="pill-select" data-pill="pushDaily">
          <button type="button" data-v="1" class="${(c.push || {}).daily_brief ? "on" : ""}">要</button>
          <button type="button" data-v="0" class="${(c.push || {}).daily_brief ? "" : "on"}">不要</button>
        </div><input type="hidden" id="f_pushDaily" value="${(c.push || {}).daily_brief ? 1 : 0}"></div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:11px">
      <button class="btn primary" id="pushSave">保存</button>
      <button class="btn" id="pushTest">发送测试消息（钉钉）</button>
    </div>
    <div id="pushOut" class="small" style="margin-top:9px"></div>`, { icon: "🔔" });

  const inb = (S.inboxCfg || {});
  const mailCard = UI.card("set-mailin", "邮箱收件（手机随手记）", inb.enabled ? "已开启" : "未开启", `
    <div class="small muted" style="margin-bottom:10px">
      钉钉的自定义机器人只能发不能收，所以手机上随手往工作台丢东西，走邮箱最稳：
      你发一封邮件过去，工作台<b>每 30 分钟</b>收一次，自动变成「待分类」的条目。
      建议专门用一个邮箱，或者用「只收来自某个地址」把范围限死。</div>
    <div class="form-grid">
      <div class="field"><label>开启</label>
        <div class="pill-select" data-pill="mbOn">
          <button type="button" data-v="0" class="${inb.enabled ? "" : "on"}">关</button>
          <button type="button" data-v="1" class="${inb.enabled ? "on" : ""}">开</button>
        </div><input type="hidden" id="f_mbOn" value="${inb.enabled ? 1 : 0}"></div>
      <div class="field"><label>IMAP 服务器</label>
        <input id="mb_host" value="${esc(inb.imap_host || "")}" placeholder="imap.qq.com / outlook.office365.com"></div>
      <div class="field"><label>端口</label><input id="mb_port" value="${esc(inb.imap_port || 993)}"></div>
      <div class="field"><label>账号</label><input id="mb_user" value="${esc(inb.imap_user || "")}" placeholder="you@example.com"></div>
      <div class="field"><label>密码 / 授权码${inb.has_pw ? "（已配，留空表示不改）" : ""}</label>
        <input id="mb_pw" type="password" placeholder="多数邮箱要用授权码，不是登录密码">
        <div class="hint">只存本机，不进 Git、不进备份。</div></div>
      <div class="field"><label>只收来自（逗号分隔，留空=不限）</label>
        <input id="mb_from" value="${esc(inb.imap_only_from || "")}" placeholder="你自己的邮箱地址"></div>
      <div class="field"><label>标题必须含（留空=不限）</label>
        <input id="mb_tag" value="${esc(inb.imap_subject_tag || "")}" placeholder="比如 #台"></div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:11px">
      <button class="btn primary" id="mbSave">保存</button>
      <button class="btn" id="mbNow">立即收一次</button>
    </div>
    <div id="mbOut" class="small" style="margin-top:9px"></div>`, { icon: "📮", defaultOpen: false });

  const ol = S.overleafStatus || { projects: [] };
  const olCard = UI.card("set-overleaf", "Overleaf 写作进展", ol.configured ? `${ol.projects.length} 个项目` : "未启用", `
    <div class="small muted" style="margin-bottom:10px">
      付费版 Overleaf 提供 Git 接入。填好之后，工作台每天早上会把你的项目拉一次，
      算出<b>改了哪几节、净增多少行、正文字数变化</b>，写成一条进展记录 ——
      今日页、周报和手帐都会自动用上，你不用手动记「今天写了什么」。
      项目只 clone 到本机 <code>local/overleaf/</code>，不进你的工作台仓库。</div>
    <div class="form-grid">
      <div class="field"><label>Overleaf 邮箱</label>
        <input id="ol_email" value="${esc(ol.email || "")}" placeholder="登录 Overleaf 用的邮箱"></div>
      <div class="field"><label>Git token ${ol.configured ? "（已配，留空表示不改）" : ""}</label>
        <input id="ol_token" type="password" placeholder="Overleaf → Account Settings → Git Integration → Generate token">
        <div class="hint"><a href="https://www.overleaf.com/user/settings" target="_blank" rel="noopener">去 Overleaf 生成 ↗</a>
          —— 页面往下拉到 Git Integration。不是登录密码，是那个单独生成的 token。只存本机，不进 Git、不进备份。</div></div>
    </div>
    <div class="small muted" style="margin:9px 0;padding:9px;background:var(--bg-2);border-radius:8px">
      <b>不是付费版 Overleaf？</b>写作进展照样能有。<br>
      在稿件的「本地 LaTeX 目录」里填上本机存 .tex 的文件夹——只要它是个 git 仓库，
      同样能算出「改了哪几节、净增多少行、正文字数变化」。
      算法跟这里完全一样，区别只是读本地而不是 clone 下来。
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:11px">
      <button class="btn primary" id="olSave">保存</button>
      <button class="btn" id="olSyncAll">立即同步全部项目</button>
      <button class="btn" id="texSyncAll">同步本地 LaTeX 目录</button>
      <span class="spacer"></span>
      <span class="small muted">项目地址填在每篇稿件的「Overleaf 项目地址」里</span>
    </div>
    ${ol.projects.length ? `<div style="margin-top:10px">${ol.projects.map(pr => `
      <div class="row-line"><div class="rl-main">
        <div class="rl-title small">${esc(pr.title || "（未命名稿件）")}</div>
        <div class="rl-meta">${esc(pr.url)}${pr.last ? " · 今天同步过" : " · 今天还没同步"}</div>
      </div><div class="rl-acts"><button class="btn sm" data-olsync="${esc(pr.id)}">同步</button></div></div>`).join("")}</div>`
      : `<div class="empty" style="margin-top:9px">还没有稿件填 Overleaf 地址。去稿件卡片点「编辑」，把项目地址粘进去。</div>`}
    <div id="olOut" class="small" style="margin-top:9px"></div>`, { icon: "📝" });

  /* 数字必须诚实：生活流水在首屏是裁过的，示例种子放久了就会掉出那个窗口。
     照着内存数就会说「彻底删掉这 9 条」，而磁盘上其实还有 14 条 ——
     点完之后剩下的那几条既删不掉、也没有任何地方告诉你它们还在。
     所以裁过的时候不写死数字，改成「至少 N 条」，真删的时候先补全再删。 */
  const SAMPLE_COLLS = ["manuscripts", "published", "conferences", "reading",
    "ideas", "schedule", "journals", "diet", "exercise", "dates", "lists", "admin", "finance"];
  const sampleTotal = sampleCount(SAMPLE_COLLS);
  const samplePartial = SAMPLE_COLLS.some(isPartial);
  const sampleN = samplePartial ? `至少 ${sampleTotal}` : `${sampleTotal}`;
  /* ---------------------------------------------------------- 学术雷达 */
  const rad = c.radar || {};
  const radKw = rad.keywords || (c.profile || {}).keywords || [];
  const radPeople = rad.people || [];
  const radSrc = rad.sources || ["crossref", "nber", "arxiv"];
  const radarCard = UI.card("set-radar", "学术雷达",
    (radKw.length || radPeople.length) ? `${radKw.length} 个词 · ${radPeople.length} 个人` : "还没设",
    `
    <div class="small muted" style="margin-bottom:10px">
      每周去 Crossref / NBER / arXiv 捞一遍新发表和新 working paper，
      挑出值得看的写成一段速览，选中的自动进文献索引。
      <b>抓取是代码做的，不经过 AI</b>；AI 只负责在抓回来的东西里挑、并写成人话，
      而且它说的每一条都要能对回抓来的原始记录 —— 对不上的会被丢掉并如实告诉你。</div>
    <div class="form-grid">
      <div class="field wide"><label>关键词（逗号分隔）</label>
        <input id="rad_kw" value="${esc(radKw.join(", "))}"
          placeholder="intermediary asset pricing, funding liquidity, dealer balance sheet">
        <div class="hint">用英文写。留空就沿用「你是谁」里填的研究方向。</div></div>
      <div class="field wide"><label>要盯的人（一行一个：<code>姓名 | ORCID</code>，ORCID 可省）</label>
        <textarea id="rad_people" style="min-height:78px"
          placeholder="Zhiguo He | 0000-0002-1234-5678&#10;Tobias Adrian">${
      esc(radPeople.map(p => [p.name, p.orcid].filter(Boolean).join(" | ")).join("\n"))}</textarea>
        <div class="hint"><b>填 ORCID 才追得准。</b>只写名字的话是按姓名去猜的 ——
          重名很常见（搜 "Zhiguo He" 会把所有姓 He 的都翻出来），
          这种条目会被标成「可能不是同一个人」，别当准的用。
          ORCID 在对方主页或论文首页一般能找到。</div></div>
      <div class="field wide"><label>抓哪些源</label>
        <div style="display:flex;gap:8px 18px;flex-wrap:wrap;align-items:flex-start">
          ${[["crossref", "Crossref（最全，连 NBER 也收）"],
             ["nber", "NBER（新 working paper 首发，快几天）"],
             ["arxiv", "arXiv（q-fin/econ，最快但窄）"]].map(([v, t]) =>
      /* flex:0 1 auto + 文字不换行，否则三个选项会被挤成三条窄柱，
         勾选框和它的文字看着像是分开的两样东西 */
      `<label class="tiny" style="display:inline-flex;align-items:center;gap:5px;white-space:nowrap;flex:0 1 auto">
             <input type="checkbox" class="rad-src" value="${v}"${radSrc.includes(v) ? " checked" : ""}> ${t}</label>`).join("")}
        </div></div>
      <div class="field"><label>联系邮箱（可选）</label>
        <input id="rad_mail" value="${esc(rad.mailto || "")}" placeholder="you@university.edu">
        <div class="hint">填了会进 Crossref 的 polite pool，响应更稳定。它只用于这个。</div></div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:10px">
      <button class="btn primary" id="radSave">保存</button>
      <button class="btn" id="radTest">测一下各个源通不通</button>
    </div>
    <div id="radOut" class="small" style="margin-top:9px"></div>
    <div class="tiny muted" style="margin-top:8px">
      抓取要连外网。学校或公司的网络代理经常会挡掉这些 API ——
      先点「测一下」确认能连上，别等到某个周一发现周报是空的。</div>`,
    { icon: "📡", defaultOpen: false });

  const sampleCard = UI.card("set-sample", "示例数据", c.hide_samples ? "已隐藏" : `${sampleN} 条`, `
    <div class="small muted" style="margin-bottom:9px">种子里的示例记录是给你看结构用的。
      每张卡片右上角都有「🙈 隐藏示例」，点一次全站生效；这里可以再显示回来，或者彻底删掉。</div>
    <div style="display:flex;gap:7px;flex-wrap:wrap">
      <button class="btn" id="smpToggle">${c.hide_samples ? "重新显示示例" : "隐藏全部示例"}</button>
      <button class="btn danger" id="smpPurge">彻底删掉这 ${sampleN} 条</button>
    </div>
    ${samplePartial ? `<div class="tiny muted" style="margin-top:6px">
      生活流水首屏只带了近期的，更早的示例这里数不到；点「彻底删掉」时会先把它们全部读回来再删。</div>` : ""}
    <div class="small muted" style="margin-top:8px">彻底删掉也是移到 <code>local/trash/</code>，捞得回来。</div>`,
    { icon: "🌱", defaultOpen: false });

  const CLEAN_COLLS = [
    ["conferences", "学术会议"], ["manuscripts", "稿件库"], ["published", "论文库"],
    ["reading", "读文献"], ["ideas", "想法"], ["schedule", "日程"], ["journals", "期刊库"],
  ];
  const cleanColl = S.cleanColl || "conferences";
  const cleanRows = rows(cleanColl);
  const cleanCard = UI.card("set-clean", "批量清理", `${cleanRows.length} 条`, `
    <div class="small muted" style="margin-bottom:9px">导入错了、试用时造的垃圾数据，在这里挑出来一次删掉。
      删除同样是移到 <code>local/trash/</code>，不是真删，误删了还能捞回来。</div>
    <div class="form-grid">
      <div class="field wide"><label>清理哪个库</label>
        <div class="pill-select" data-pill="cleanColl">
          ${CLEAN_COLLS.map(([id, nm]) => `<button type="button" data-v="${id}" class="${cleanColl === id ? "on" : ""}">${nm} ${rows(id).length}</button>`).join("")}
        </div><input type="hidden" id="f_cleanColl" value="${esc(cleanColl)}"></div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin:9px 0">
      <button class="btn sm" id="clSelAll">全选</button>
      <button class="btn sm" id="clSelNone">全不选</button>
      <button class="btn sm" id="clSelEmpty">只选「未命名 / 空标题」</button>
      <button class="btn sm" id="clSelImported">只选导入进来的</button>
      <span class="spacer"></span>
      <button class="btn danger" id="clDelete">删除选中</button>
    </div>
    <div class="scroll-x" style="max-height:340px;overflow-y:auto">
      ${cleanRows.length ? cleanRows.map(r => `<label class="row-line" style="cursor:pointer">
          <input type="checkbox" class="clchk" data-id="${esc(r.id)}" style="margin-right:9px">
          <div class="rl-main"><div class="rl-title small">${esc(r.title || "（未命名）")}</div>
            <div class="rl-meta">${esc(r.deadline || r.date || r.start || r.year || "")}
              ${r.source_import ? ` · 来自 ${esc(r.source_import)}` : ""}</div></div>
        </label>`).join("") : `<div class="empty">这个库是空的</div>`}
    </div>`, { icon: "🧹", defaultOpen: false });

  const backup = UI.card("set-backup", "备份时光机", "Time machine", `
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:9px">
      <button class="btn primary" id="bkNow">立即备份</button>
      <button class="btn" id="bkRefresh">刷新列表</button>
      <span class="spacer"></span>
      <span class="small muted">滚动快照保留 ${d.rolling_keep_days || 7} 天；OneDrive 里的每日备份永久保留</span>
    </div>
    <div id="bkList"><div class="empty">点「刷新列表」查看快照</div></div>`, { icon: "🕰" });

  const importCard = UI.card("set-import", "表格导入（Excel / CSV）", "", `
    <div class="small muted" style="margin-bottom:9px">支持 .xlsx / .csv。先选文件预览，确认列名后导入。
      重复导入同一张表不会产生重复记录（按去重键更新）。</div>
    <div class="form-grid">
      <div class="field"><label>选择文件</label><input type="file" id="impFile" accept=".xlsx,.xlsm,.csv,.tsv"></div>
      <div class="field"><label>导入到</label>
        <div class="pill-select" data-pill="impColl">
          <button type="button" data-v="manuscripts" class="on">稿件库</button>
          <button type="button" data-v="published">论文库</button>
          <button type="button" data-v="conferences">会议</button>
          <button type="button" data-v="reading">文献</button>
        </div><input type="hidden" id="f_impColl" value="manuscripts"></div>
      <div class="field"><label>去重键（列名）</label><input id="impKey" value="title" placeholder="留空则每次都新增"></div>
    </div>
    <div id="impPreview" style="margin-top:11px"></div>`, { icon: "📥" });

  const st = S.secretsStatus || {};
  const todo = [];
  if (!st.github_token) todo.push("GitHub 同步没配 —— 两台电脑和手机都还连不上");
  if (!d.onedrive_backup_dir) todo.push("没设 OneDrive 备份目录 —— 长期备份不会生成");
  else if (/^https?:\/\//.test(d.onedrive_backup_dir)) todo.push(
    "OneDrive 那一栏填的是网页链接，工作台要的是本机路径（形如 /Users/你/Library/CloudStorage/OneDrive-xxx/workspace）");
  else if (S.odMissing) todo.push("OneDrive 目录找不到了 —— 路径写错了，或者 OneDrive 客户端没在跑");
  if (!((c.calendar || {}).ics || []).length) todo.push("没订阅 Outlook 日历 —— 右上角日历只显示工作台自己的日程");
  if (!(st.dingtalk || st.wecom || st.email)) todo.push("没配推送渠道 —— 周一早报只能在工作台里看");
  if (!d.paper_root) todo.push("没设论文根目录 —— 稿件卡上的结果图无法自动扫描");
  const setupCard = UI.card("set-wizard", "配置向导", (c.setup || {}).done ? "已完成" : "尚未完成", `
    <div class="small">${(c.setup || {}).done
      ? `你在 ${esc(String((c.setup || {}).completed_at || "").slice(0, 16).replace("T", " "))} 完成了首次配置。想改哪一步都可以重新走一遍，已填的内容会保留。`
      : `还没走完首次配置。建议现在花三分钟走一遍，之后就不用再管了。`}</div>
    ${todo.length ? `<div style="margin-top:9px">${todo.map(t => `<div class="row-line"><div class="rl-main">
        <div class="rl-title small">⚠️ ${esc(t)}</div></div></div>`).join("")}</div>` : `
      <div class="row-line"><div class="rl-main"><div class="rl-title small">✅ 该配的都配好了</div></div></div>`}
    <div style="margin-top:10px"><button class="btn primary" id="wzOpen">${(c.setup || {}).done ? "重新走一遍向导" : "开始配置向导"}</button></div>`,
    { icon: "🧭" });

  const sec = c.security || {};
  const peers = S.peers || [];
  const remoteCard = UI.card("set-remote", "远程访问与手机", sec.remote_enabled ? "已开启" : "已关闭", `
    <div class="small muted" style="margin-bottom:10px">
      默认只有这台电脑自己能打开工作台。开启远程后，同一网络（或同一 VPN）下的手机、另一台电脑
      才能连进来——<b>连进来必须输访问码，而且默认只读</b>，要改东西得在页面上再解锁一次，30 分钟后自动回到只读。
      密钥、Git 凭据、文件浏览、脚本执行这几项，远程永远碰不到。</div>
    <div class="form-grid">
      <div class="field"><label>允许远程访问</label>
        <div class="pill-select" data-pill="secOn">
          <button type="button" data-v="0" class="${sec.remote_enabled ? "" : "on"}">关闭（最安全）</button>
          <button type="button" data-v="1" class="${sec.remote_enabled ? "on" : ""}">开启</button>
        </div><input type="hidden" id="f_secOn" value="${sec.remote_enabled ? 1 : 0}"></div>
      <div class="field"><label>远程默认只读</label>
        <div class="pill-select" data-pill="secRO">
          <button type="button" data-v="1" class="${sec.remote_readonly === false ? "" : "on"}">只读（推荐）</button>
          <button type="button" data-v="0" class="${sec.remote_readonly === false ? "on" : ""}">可直接编辑</button>
        </div><input type="hidden" id="f_secRO" value="${sec.remote_readonly === false ? 0 : 1}"></div>
      <div class="field"><label>访问码${st.remote_code ? "（已设置，留空表示不改）" : "（必填）"}</label>
        <input id="sec_code" type="password" placeholder="${st.remote_code ? "••••••" : "至少 6 位，中文也行"}"></div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:10px">
      <button class="btn primary" id="secSave">保存</button>
      <button class="btn" id="portalBuild">生成手机入口页</button>
      <button class="btn" id="digestBuild">生成今日只读简报</button>
      <button class="btn ghost" id="secLog">查看访问记录</button>
    </div>
    <div class="small muted" style="margin-top:9px">开启后，用这条命令启动才会监听局域网：
      <code>python3 server.py --lan</code>（普通双击启动仍然只有本机能用）。</div>
    <div id="remoteOut" class="small" style="margin-top:9px"></div>`, { icon: "📱" });

  const diagCard = UI.card("set-diag", "导出诊断包", "报 bug 用", `
    <div class="small muted" style="margin-bottom:10px">
      工作台<b>不会</b>把任何崩溃信息发回给我们——这是刻意的，你的数据只在你自己机器上。
      代价是你报 bug 时只能说「坏了」，我们没法查。<br>
      这个按钮导出一份纯文本：版本、系统环境、各类记录的<b>条数</b>、
      配置项的开关状态、最近的同步日志（token 已自动抹掉）。
      <b>不含任何记录内容</b>——没有标题、没有正文、没有文献题录、没有生活数据。
      导出后你可以自己先看一遍再决定发不发。</div>
    <div style="display:flex;gap:7px;flex-wrap:wrap">
      <a class="btn primary" href="/api/diagnostics" download="diagnostics.md">下载诊断包</a>
      <button class="btn" id="diagView">先看看里面是什么</button>
    </div>
    <pre id="diagOut" class="small" style="white-space:pre-wrap;margin-top:10px;max-height:320px;
      overflow:auto;display:none;background:var(--bg-2);padding:10px;border-radius:8px"></pre>`,
    { icon: "🩺", defaultOpen: false });

  const peersCard = UI.card("set-peers", "我的设备", peers.length ? `${peers.length} 台` : "", `
    <div class="small muted" style="margin-bottom:9px">每台电脑每 10 分钟写一次心跳，通过 Git 同步过来。
      "在线"是指 20 分钟内有过心跳。</div>
    ${peers.length ? peers.map(p => `<div class="row-line"><div class="rl-main">
        <div class="rl-title">${p.state === "在线" || p.state === "本机" ? "🟢" : p.state === "最近在线" ? "🟡" : "⚪️"}
          ${esc(p.name || p.device_id)} ${p.is_me ? '<span class="chip">本机</span>' : ""}</div>
        <div class="rl-sub small">${esc(p.state)}${p.minutes_ago != null && !p.is_me
          ? ` · ${p.minutes_ago < 60 ? Math.round(p.minutes_ago) + " 分钟前" : Math.round(p.minutes_ago / 60) + " 小时前"}` : ""}
          ${(p.urls || []).length ? " · " + esc((p.urls || [])[0]) : ""}</div>
      </div></div>`).join("")
      : `<div class="empty">还只有这一台。在另一台电脑上装好并接同一个 Git 仓库后，它会自动出现在这里。</div>`}
    <div style="margin-top:10px"><button class="btn" id="peerRefresh">刷新</button></div>`, { icon: "💻" });

  return `<div class="page-head"><h1>⚙️ 设置与教程</h1><div class="sub">v${esc(S.version || "")} · ${esc(S.root || "")}</div></div>
    ${setupCard}${tutorial}${deco}${device}${remoteCard}${peersCard}${gitCard}${calCard}${pushCard}${aiCard}${olCard}${mailCard}${radarCard}${sampleCard}${cleanCard}${backup}${importCard}${diagCard}`;
};

/* 订阅地址常见的两种手滑：webcal:// 开头（苹果给的就是这个），
   以及从邮件里复制时把整条 URL 用尖括号裹住。都在保存前悄悄修掉。 */
function normIcsUrl(u) {
  u = String(u || "").trim().replace(/^[<(]|[>)]$/g, "").trim();
  if (!u) return "";
  return u.replace(/^webcal:\/\//i, "https://");
}

window.bindSettingsExtras = function () {
  const tsa = $("#texSyncAll");
  if (tsa) tsa.onclick = async () => {
    const out = $("#olOut");
    const ms = (S.data.manuscripts || []).filter(m => m.tex_folder);
    if (!ms.length) { out.innerHTML = "没有稿件填了「本地 LaTeX 目录」。去稿件卡片点编辑填上。"; return; }
    out.textContent = `正在读 ${ms.length} 个本地目录…`;
    const lines = [];
    for (const m of ms) {
      try {
        const r = await API.post("tex/sync", { id: m.id });
        lines.push(r.ok
          ? `✅ ${esc(m.title || m.id)} —— ${r.first_time ? "首次接入，记下基线" :
              (r.changed ? `净增 ${r.net} 行 · ${r.commits.length} 次提交` : "没有新变化")}，当前 ${r.words} 词`
          : `❌ ${esc(m.title || m.id)} —— ${esc(r.detail || "失败")}`);
      } catch (e) { lines.push(`❌ ${esc(m.title || m.id)} —— ${esc(String(e.message || e))}`); }
    }
    out.innerHTML = lines.join("<br>");
    await reload(); render();
  };
  const dv = $("#diagView");
  if (dv) dv.onclick = async () => {
    const box = $("#diagOut");
    box.style.display = "block";
    box.textContent = "生成中…";
    try {
      const r = await fetch("/api/diagnostics");
      box.textContent = await r.text();
    } catch (e) { box.textContent = "生成失败：" + (e.message || e); }
  };
  const wo = $("#wzOpen");
  if (wo) wo.onclick = () => WZ.open(0);

  const calOut = () => $("#calOut");
  const calSave = $("#calSave");
  if (calSave) calSave.onclick = async () => {
    const list = [normIcsUrl($("#cal_ics1").value), normIcsUrl($("#cal_ics2").value)].filter(Boolean);
    const bad = list.find(u => !/^https?:\/\//i.test(u));
    if (bad) { calOut().innerHTML = `<span style="color:var(--red)">这条不像订阅地址：<code>${esc(bad)}</code><br>
      应该是 https:// 开头、通常以 .ics 结尾的一长串。</span>`; return; }
    calSave.disabled = true; calOut().textContent = "保存中…";
    try {
      await saveConfig({
        calendar: Object.assign({}, S.config.calendar, {
          ics: list,
          refresh_min: Math.max(5, Number($("#cal_refresh").value) || 15),
          lunar: $("#f_calLunar").value === "1",
          weather: $("#f_calWx").value === "1",
        }),
      });
      calOut().textContent = list.length ? "已保存，正在拉取…" : "已保存（没有订阅源）";
      if (list.length) await refreshAmbient(true);
      render();
      toast(list.length ? `日历已同步，${(S.icsEvents || []).length} 条日程` : "日历设置已保存");
    } catch (e) {
      calOut().innerHTML = `<span style="color:var(--red)">保存失败：${esc(String(e.message || e))}</span>`;
    } finally { calSave.disabled = false; }
  };

  const calTest = $("#calTest");
  if (calTest) calTest.onclick = async () => {
    const list = [normIcsUrl($("#cal_ics1").value), normIcsUrl($("#cal_ics2").value)].filter(Boolean);
    if (!list.length) { calOut().textContent = "先填一条订阅地址。"; return; }
    calTest.disabled = true; calOut().textContent = "正在连…";
    const lines = [];
    for (const url of list) {
      try {
        const r = await API.post("test/ics", { url });
        const eg = ((r.sample || [])[0] || {}).title;
        lines.push(r.ok
          ? `✅ <code>${esc(url.slice(0, 60))}…</code> 通了，未来 120 天内看到 <b>${r.count || 0}</b> 条日程${eg ? `（比如「${esc(eg)}」）` : ""}`
          : `❌ <code>${esc(url.slice(0, 60))}…</code> ${r.detail || "拉不到"}`);
      } catch (e) {
        lines.push(`❌ <code>${esc(url.slice(0, 60))}…</code> ${esc(String(e.message || e))}`);
      }
    }
    calOut().innerHTML = lines.join("<br>") + `<div class="muted" style="margin-top:6px">测通了记得点「保存并立即同步」才会真的用上。</div>`;
    calTest.disabled = false;
  };

  const calNow = $("#calSyncNow");
  if (calNow) calNow.onclick = async () => {
    calNow.disabled = true; calOut().textContent = "正在拉取…";
    let msg;
    try {
      await refreshAmbient(true);
      const bad = (S.icsErrors || []).length;
      msg = bad
        ? `<span style="color:var(--red)">拉完了，但有 ${bad} 个源没成功</span>（原因在下面）`
        : `已同步，共 <b>${(S.icsEvents || []).length}</b> 条日程`;
    } catch (e) {
      msg = `<span style="color:var(--red)">同步失败：${esc(String(e.message || e))}</span>`;
    }
    /* render() 会把整页重画，#calOut 是新的空元素 —— 必须重画完再写字，
       否则消息一闪就没了（第一次就栽在这儿） */
    render();
    const o = calOut(); if (o) o.innerHTML = msg;
  };
  const cs = $("#cfgSave");
  if (cs) cs.onclick = async () => {
    const secs = $$("[data-sec]").filter(x => x.checked).map(x => x.dataset.sec);
    await saveConfig({
      today_horizon_days: Number($("#cfg_horizon").value) || 45,
      stale_manuscript_days: Number($("#cfg_stale").value) || 7,
      reading: Object.assign({}, S.config.reading, { weekly_goal: Number($("#cfg_goal").value) || 5 }),
      ai: Object.assign({}, S.config.ai, { default_jump: $("#f_cfg_jump").value }),
      theme: Object.assign({}, S.config.theme, { accent: $("#cfg_accent").value, mode: $("#f_cfg_mode").value }),
      sections: ["today"].concat(secs).concat(["settings"]),
      brand: { title: $("#cfg_btitle").value.trim(), sub: $("#cfg_bsub").value.trim() },
    });
    applyTheme(); applyBrand(); renderNav(); render(); toast("设置已保存");
  };
  const ds = $("#devSave");
  if (ds) ds.onclick = async () => {
    await saveDevice({
      device_name: $("#dev_name").value.trim(),
      paper_root: $("#dev_paper").value.trim(),
      onedrive_backup_dir: $("#dev_od").value.trim(),
      zotero_root: ($("#dev_zroot") ? $("#dev_zroot").value.trim() : (S.device || {}).zotero_root || ""),
      daily_backup_times: $("#dev_times").value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
      rolling_minutes: Number($("#dev_roll").value) || 30,
      rolling_keep_days: Number($("#dev_keep").value) || 7,
      timezone: timeZone(),
    });
    S._figs = {}; render(); toast("本机设置已保存");
  };
  const smpT = $("#smpToggle");
  if (smpT) smpT.onclick = async () => {
    await saveConfig({ hide_samples: !S.config.hide_samples });
    render(); renderNav();
    toast(S.config.hide_samples ? "示例已隐藏" : "示例已重新显示");
  };
  /* ---- 学术雷达 ---- */
  const radSave = $("#radSave");
  if (radSave) radSave.onclick = async () => {
    /* 「一行一个：姓名 | ORCID」解析。
       ORCID 长得是 0000-0000-0000-000X（最后一位可能是 X）——
       格式不对就当没填，并且**说出来**，否则用户以为自己在精确追人，
       实际系统在按姓名瞎猜，而两者的可信度差很远。 */
    const bad = [];
    const people = ($("#rad_people").value || "").split("\n")
      .map(l => l.trim()).filter(Boolean).map(line => {
        const [nm, oc] = line.split("|").map(x => (x || "").trim());
        const orcid = (oc || "").replace(/^https?:\/\/orcid\.org\//, "");
        if (oc && !/^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/i.test(orcid)) {
          bad.push(`${nm || line}：ORCID「${oc}」格式不对，这次按姓名匹配`);
          return { name: nm || line };
        }
        return orcid ? { name: nm, orcid } : { name: nm || line };
      }).filter(p => p.name || p.orcid);
    const kws = ($("#rad_kw").value || "").split(/[,，]/).map(x => x.trim()).filter(Boolean);
    const sources = $$(".rad-src").filter(x => x.checked).map(x => x.value);
    await saveConfig({ radar: {
      keywords: kws, people, sources,
      mailto: ($("#rad_mail").value || "").trim(),
      per_keyword: (S.config.radar || {}).per_keyword || 12,
    } });
    const noOrcid = people.filter(p => !p.orcid).length;
    $("#radOut").innerHTML =
      `已保存：${kws.length} 个关键词、${people.length} 个人、${sources.length} 个源。`
      + (noOrcid ? `<div class="tiny" style="color:var(--amber)">其中 ${noOrcid} 个人没填 ORCID
           —— 这些是按姓名猜的，重名会混进来，周报里会标出来。</div>` : "")
      + bad.map(b => `<div class="tiny" style="color:var(--red)">${esc(b)}</div>`).join("");
    if (!sources.length) {
      $("#radOut").innerHTML += `<div class="tiny" style="color:var(--red)">
        一个源都没勾 —— 雷达不会抓到任何东西。</div>`;
    }
    toast("学术雷达已保存");
  };
  const radTest = $("#radTest");
  if (radTest) radTest.onclick = async () => {
    radTest.disabled = true; radTest.textContent = "测试中…";
    $("#radOut").innerHTML = "正在逐个连…（最多十几秒）";
    try {
      const r = await API.get("radar/selftest");
      $("#radOut").innerHTML = (r.sources || []).map(x =>
        `<div class="tiny">${x.ok ? "✓" : "<span style=\"color:var(--red)\">✗</span>"}
          <b>${esc(x.source)}</b> ${x.n} 条 ${esc(x.detail || x.note || "")}</div>`).join("")
        + `<div class="small" style="margin-top:5px">${esc(r.summary || "")}</div>`
        + (r.ok ? "" : `<div class="tiny muted" style="margin-top:4px">
            一个都连不上，最常见的原因是学校/公司的网络代理挡了外网 API。
            换个网络再试。</div>`);
    } catch (e) {
      $("#radOut").innerHTML = `<span style="color:var(--red)">测不了：${esc(String(e.message || e))}</span>`;
    } finally { radTest.disabled = false; radTest.textContent = "测一下各个源通不通"; }
  };

  const smpP = $("#smpPurge");
  if (smpP) smpP.onclick = async () => {
    const colls = ["manuscripts", "published", "conferences", "reading", "ideas",
                   "schedule", "journals", "diet", "exercise", "dates", "lists", "admin", "finance"];
    // 先把裁过的集合补全，否则「彻底删掉」只删得掉首屏带回来的那部分
    smpP.disabled = true; smpP.textContent = "统计中…";
    try { await loadAll(colls); } catch (e) {
      smpP.disabled = false; smpP.textContent = "彻底删掉示例";
      return toast("读不全数据，先不删：" + (e.message || e));
    }
    smpP.disabled = false;
    const hit = [];
    colls.forEach(cl => rowsAll(cl).filter(isSample).forEach(r => hit.push([cl, r.id])));
    if (!hit.length) { toast("没有示例数据了"); return; }
    if (!confirm(`确定彻底删掉 ${hit.length} 条示例？\n（会移到 local/trash，还能捞回来）`)) return;
    smpP.disabled = true; smpP.textContent = "删除中…";
    let ok = 0;
    for (const [cl, id] of hit) { try { await deleteRec(cl, id); ok++; } catch (e) { } }
    await saveConfig({ hide_samples: false });
    render(); renderNav(); toast(`删了 ${ok} 条示例`);
  };
  const mbSave = $("#mbSave");
  if (mbSave) mbSave.onclick = async () => {
    const box = {
      enabled: $("#f_mbOn").value === "1",
      imap_host: $("#mb_host").value.trim(), imap_port: $("#mb_port").value.trim(),
      imap_user: $("#mb_user").value.trim(),
      imap_only_from: $("#mb_from").value.trim(), imap_subject_tag: $("#mb_tag").value.trim(),
    };
    const pw = $("#mb_pw").value.trim();
    if (pw) box.imap_password = pw;               // 空的不覆盖
    await API.post("secrets/merge", { push: { inbox: box } });
    S.inboxCfg = await API.get("mail/status").catch(() => S.inboxCfg);
    $("#mb_pw").value = "";
    render(); toast("邮箱收件设置已保存");
  };
  const mbNow = $("#mbNow");
  if (mbNow) mbNow.onclick = async () => {
    const el = $("#mbOut"); el.textContent = "收信中…";
    const r = await API.post("mail/intake", { limit: 20 });
    el.innerHTML = r.ok
      ? `<span style="color:var(--green)">收到 ${r.fetched} 封，新建 ${r.created} 条待分类</span>`
      : `<span style="color:var(--red)">${esc(r.detail || "收信失败")}</span>`;
    const b = await API.bootstrap(); S.data = b.data; renderNav();
  };
  const olOut = m => { const el = $("#olOut"); if (el) el.innerHTML = m; };
  const olSave = $("#olSave");
  if (olSave) olSave.onclick = async () => {
    const o = { email: $("#ol_email").value.trim() };
    const t = $("#ol_token").value.trim();
    if (t) o.token = t;                       // 空的不覆盖
    await API.post("secrets/merge", { overleaf: o });
    S.overleafStatus = await API.get("overleaf/status");
    $("#ol_token").value = "";
    render(); toast("Overleaf 设置已保存（只存本机）");
  };
  const runOl = async (payload, label) => {
    olOut(label + "…（第一次要 clone，可能要等十几秒）");
    const r = await API.post("overleaf/sync", payload);
    if (r.results) {
      olOut(r.results.length
        ? r.results.map(x => x.ok
            ? `<span style="color:var(--green)">✓ ${esc(x.title)}：${x.commits} 次提交，净 ${x.net > 0 ? "+" : ""}${x.net} 行</span>`
            : `<span style="color:var(--red)">✕ ${esc(x.title)}：${esc(x.detail)}</span>`).join("<br>")
        : "没有稿件填了 Overleaf 地址");
    } else if (r.ok) {
      olOut(`<span style="color:var(--green)">✓ ${r.first_time ? "首次接入，已记下基线" :
        (r.changed ? `${r.commits.length} 次提交 · 净 ${r.net > 0 ? "+" : ""}${r.net} 行 · 动了 ${esc((r.touched || []).join("、"))}` : "这次没有新改动")}
        · 全文约 ${r.words} 词${r.cjk ? " + " + r.cjk + " 字" : ""}</span>`);
    } else {
      olOut(`<span style="color:var(--red)">✕ ${esc(r.detail || "同步失败")}</span>`);
    }
    const b = await API.bootstrap(); S.data = b.data;
    S.overleafStatus = await API.get("overleaf/status").catch(() => S.overleafStatus);
  };
  const olAll = $("#olSyncAll");
  if (olAll) olAll.onclick = () => runOl({ all: true }, "同步全部项目中");
  $$("[data-olsync]").forEach(b => b.onclick = () => runOl({ manuscript: b.dataset.olsync }, "同步中"));
  const cp = $("[data-pill=\"cleanColl\"]");
  if (cp) cp.addEventListener("click", () => setTimeout(() => {
    S.cleanColl = $("#f_cleanColl").value; render();
  }, 30));
  const chks = () => $$(".clchk");
  const cs1 = $("#clSelAll"); if (cs1) cs1.onclick = () => chks().forEach(c => c.checked = true);
  const cs2 = $("#clSelNone"); if (cs2) cs2.onclick = () => chks().forEach(c => c.checked = false);
  const cs3 = $("#clSelEmpty");
  if (cs3) cs3.onclick = () => chks().forEach(c => {
    const r = byId(S.cleanColl || "conferences", c.dataset.id) || {};
    c.checked = !String(r.title || "").trim() || String(r.title).includes("未命名");
  });
  const cs4 = $("#clSelImported");
  if (cs4) cs4.onclick = () => chks().forEach(c => {
    const r = byId(S.cleanColl || "conferences", c.dataset.id) || {};
    c.checked = !!r.source_import;
  });
  const cdel = $("#clDelete");
  if (cdel) cdel.onclick = async () => {
    const ids = chks().filter(c => c.checked).map(c => c.dataset.id);
    if (!ids.length) { toast("一条都没选"); return; }
    if (!confirm(`确定删除选中的 ${ids.length} 条？\n（移到 local/trash，可以捞回来）`)) return;
    cdel.disabled = true; cdel.textContent = "删除中…";
    let ok = 0, bad = 0;
    for (const id of ids) {
      try { await deleteRec(S.cleanColl || "conferences", id); ok++; } catch (e) { bad++; }
    }
    render(); renderNav();
    toast(`删了 ${ok} 条` + (bad ? `，${bad} 条失败` : ""));
  };
  const out = m => { const el = $("#remoteOut"); if (el) el.innerHTML = m; };
  const ss = $("#secSave");
  if (ss) ss.onclick = async () => {
    const on = $("#f_secOn").value === "1";
    const code = $("#sec_code").value.trim();
    if (on && !code && !(S.secretsStatus || {}).remote_code) {
      out(`<span style="color:var(--red)">要开远程访问，必须先设一个访问码。</span>`); return;
    }
    if (code && code.length < 6) {
      out(`<span style="color:var(--red)">访问码太短了，至少 6 位。</span>`); return;
    }
    if (code) await API.post("secrets/merge", { remote: { access_code: code } });
    await saveConfig({
      security: Object.assign({}, S.config.security, {
        remote_enabled: on, remote_readonly: $("#f_secRO").value === "1",
      }),
    });
    S.secretsStatus = await API.get("secrets/status").catch(() => S.secretsStatus);
    $("#sec_code").value = "";
    out(on ? `已开启。用 <code>python3 server.py --lan</code> 启动后，手机在同一网络下就能连。`
           : `已关闭，现在只有这台电脑自己能用。`);
    toast("远程设置已保存");
  };
  const pb = $("#portalBuild");
  if (pb) pb.onclick = async () => {
    const r = await API.post("portal/build", {});
    out(r.ok ? `入口页已生成：<br>${(r.written || []).map(w => `<code>${esc(w)}</code>`).join("<br>")}
        <br><span class="muted">把它放进 OneDrive，手机上收藏这个文件即可——它会自动找哪台电脑开着。</span>`
      : `<span style="color:var(--red)">${esc(r.detail || "生成失败")}</span>`);
  };
  const db = $("#digestBuild");
  if (db) db.onclick = async () => {
    const r = await API.post("digest/build", {});
    out(r.ok ? `简报已生成：<br>${(r.written || []).map(w => `<code>${esc(w)}</code>`).join("<br>")}
        <br><span class="muted">这是纯静态页面，两台电脑都关机时手机也能看。每天早上会自动更新一次。</span>`
      : `<span style="color:var(--red)">${esc(r.detail || "生成失败")}</span>`);
  };
  const sl = $("#secLog");
  if (sl) sl.onclick = async () => {
    const r = await API.get("security/log");
    const lines = (r.lines || []).slice(-40).reverse();
    UI.modal("远程访问记录", lines.length
      ? `<div class="small" style="font-family:ui-monospace,monospace;line-height:1.7">
           ${lines.map(l => esc(l)).join("<br>")}</div>`
      : `<div class="empty">还没有任何远程访问记录。</div>`,
      `<span class="spacer"></span><button class="btn" data-close>关闭</button>`);
  };
  const pr = $("#peerRefresh");
  if (pr) pr.onclick = async () => {
    const r = await API.get("peers"); S.peers = r.peers || []; render(); toast("已刷新");
  };
  const gi = $("#gitInit");
  if (gi) gi.onclick = async () => {
    const r = await API.post("git/init", { remote: $("#git_remote").value.trim() });
    S.git = await API.get("git/status"); render(); updateSyncChip();
    toast(r.ok ? "仓库就绪" : "初始化失败");
  };
  const gs = $("#gitSync");
  if (gs) gs.onclick = () => doSync();
  const ghs = $("#ghSave");
  if (ghs) ghs.onclick = async () => {
    const u = $("#gh_user").value.trim(), t = $("#gh_token").value.trim();
    if (!u && !t) { toast("两个都空着，没什么可存的"); return; }
    const g = {};                              // 空的不覆盖，免得把已存的 token 抹掉
    if (u) g.user = u;
    if (t) g.token = t;
    await API.post("secrets/merge", { github: g });
    S.secretsStatus = await API.get("secrets/status").catch(() => S.secretsStatus);
    $("#gh_token").value = "";
    render();
    toast("已存到本机 local/secrets.json（不会同步）");
  };
  const aiOut = m => { const el = $("#aiOut"); if (el) el.innerHTML = m; };
  const aiPayload = () => {
    const out = { provider: $("#f_aiProv").value };
    ["anthropic", "openai", "deepseek"].forEach(id => {
      const k = $("#ai_key_" + id), m = $("#ai_model_" + id), b = $("#ai_base_" + id);
      if (k && k.value.trim()) out[id + "_key"] = k.value.trim();
      if (m) out[id + "_model"] = m.value.trim();
      if (b) out[id + "_base"] = b.value.trim();
    });
    return out;
  };
  const asv = $("#aiSave");
  if (asv) asv.onclick = async () => {
    await API.post("secrets/merge", { ai: aiPayload() });
    S.aiStatus = await API.get("ai/status");
    render(); toast("AI 设置已保存（只存本机）");
  };
  const amd = $("#aiModels");
  if (amd) amd.onclick = async () => {
    await API.post("secrets/merge", { ai: aiPayload() });
    aiOut("查询中…");
    const r = await API.get("ai/models?provider=" + $("#f_aiProv").value);
    aiOut(r.ok
      ? `可用模型：${(r.models || []).map(m => `<code>${esc(m)}</code>`).join("、")}`
      : `<span style="color:var(--red)">${esc(r.detail || "查不到")}</span>`);
  };
  const at = $("#aiTest");
  if (at) at.onclick = async () => {
    await API.post("secrets/merge", { ai: aiPayload() });
    aiOut("测试中…");
    const r = await API.post("ai/test", { provider: $("#f_aiProv").value });
    aiOut(r.ok ? `<span style="color:var(--green)">${esc(r.detail)}</span>`
               : `<span style="color:var(--red)">${esc(r.detail || "失败")}</span>`);
    S.aiStatus = await API.get("ai/status").catch(() => S.aiStatus);
  };
  const pt = $("#pushTest");
  if (pt) pt.onclick = async () => {
    const el = $("#pushOut");
    el.textContent = "正在发…";
    const r = await API.post("test/push", { kind: "dingtalk" });
    el.innerHTML = r.ok
      ? `<span style="color:var(--green)">发送成功，去钉钉群里看一眼。</span>`
      : `<span style="color:var(--red)">没发出去：${esc(r.detail || JSON.stringify(r))}</span>`;
  };
  const ps = $("#pushSave");
  if (ps) ps.onclick = async () => {
    await saveConfig({
      push: Object.assign({}, S.config.push, {
        weekly_cron: $("#push_cron").value.trim() || "MON 08:00",
        daily_brief: $("#f_pushDaily").value === "1",
        channels: Object.assign({}, (S.config.push || {}).channels, {
          dingtalk: $("#ch_ding").checked, email: $("#ch_mail").checked,
          custom: $("#ch_custom").checked,
        }),
      }),
    });
    render(); toast("推送设置已保存");
  };
  const bn = $("#bkNow");
  if (bn) bn.onclick = async () => { const r = await API.post("backup", { kind: "manual" }); toast(r.ok ? "已备份" : "备份失败：" + (r.detail || "")); loadBackups(); };
  const br = $("#bkRefresh");
  if (br) br.onclick = loadBackups;
  const inp = $("#impFile");
  if (inp) inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    const buf = await f.arrayBuffer();
    let bin = ""; const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i += 8192) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
    const r = await API.post("table/upload", { name: f.name, base64: btoa(bin), collection: $("#f_impColl").value });
    if (!r.ok) { toast("读取失败"); return; }
    $("#impPreview").innerHTML = `
      <div class="small">共 <b>${r.total}</b> 行，列名：${r.headers.map(h => `<span class="badge">${esc(h)}</span>`).join("")}</div>
      <div class="scroll-x" style="margin-top:7px"><table class="tbl">
        <tr>${r.headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr>
        ${r.rows.slice(0, 8).map(row => `<tr>${row.map(c => `<td>${esc(String(c).slice(0, 40))}</td>`).join("")}</tr>`).join("")}
      </table></div>
      <div class="small" style="margin-top:11px;font-weight:600">这些列分别是什么？</div>
      <div class="small muted" style="margin:3px 0 7px">已经替你猜了一遍，不对的改一下；选「不导入」的列会被忽略。
        <b>标题那一列必须选对</b>，否则整行会被跳过。</div>
      <div class="form-grid">
        ${r.headers.map((h, i) => `<div class="field"><label>${esc(h || "（第 " + (i + 1) + " 列）")}</label>
          <select id="map_${i}" data-mapcol="${esc(h)}">
            <option value="-">不导入</option>
            ${(r.fields || []).concat(["title"]).filter((v, j, a) => a.indexOf(v) === j)
              .map(f => `<option value="${esc(f)}" ${(r.guess || {})[h] === f ? "selected" : ""}>${esc(FIELD_LABEL[f] || f)}</option>`).join("")}
          </select></div>`).join("")}
      </div>
      <div style="margin-top:11px"><button class="btn primary" id="impGo">导入 ${r.total} 行</button>
        <span class="small muted" style="margin-left:8px">重复导入同一张表不会产生重复记录</span></div>`;
    $("#impGo").onclick = async (e) => {
      const btn = e.currentTarget; btn.disabled = true; btn.textContent = "导入中…";
      const mapping = {};
      $$("[data-mapcol]").forEach(sel => { if (sel.value !== "-") mapping[sel.dataset.mapcol] = sel.value; });
      const res = await API.post("table/import", {
        path: r.path, collection: $("#f_impColl").value, mapping,
        dedup_key: $("#impKey").value.trim() || null,
      });
      const boot = await API.bootstrap(); S.data = boot.data;
      render(); renderNav();
      toast(`新增 ${res.created} 条，更新 ${res.updated} 条` +
        (res.skipped ? `，跳过 ${res.skipped} 行（没有标题）` : ""));
    };
  };
};

async function loadBackups() {
  const list = await API.get("backups");
  const el = $("#bkList"); if (!el) return;
  el.innerHTML = list.length ? list.slice(0, 30).map(b => `
    <div class="row-line"><div class="rl-main">
      <div class="rl-title small">${b.kind === "daily" ? "📦" : "🕐"} ${esc(b.name)}</div>
      <div class="rl-meta">${esc(b.mtime)} · ${b.size_kb} KB · ${b.kind === "daily" ? "长期（OneDrive）" : "滚动"}</div>
    </div><div class="rl-acts"><button class="btn sm danger" data-restore="${esc(b.path)}">恢复</button></div></div>`).join("")
    : `<div class="empty">还没有快照（服务运行 30 分钟后会自动生成第一个）</div>`;
  $$("[data-restore]", el).forEach(b => b.onclick = async () => {
    if (!confirm("恢复到这个快照？当前状态会先自动另存一份，可以反悔。")) return;
    const r = await API.post("restore", { path: b.dataset.restore });
    if (r.ok) { const boot = await API.bootstrap(); Object.assign(S, boot); render(); renderNav(); toast("已恢复"); }
    else toast("恢复失败：" + (r.detail || ""));
  });
}
