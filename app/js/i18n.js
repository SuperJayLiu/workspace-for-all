/* Scholar Workspace · build-free interface internationalisation.
 *
 * This file deliberately owns translation at the DOM boundary.  The app is a
 * collection of small, independently rendered modules; modals, the setup wizard,
 * search results and toasts can all appear after the main route has rendered.
 * A MutationObserver makes those late surfaces behave exactly like route pages.
 *
 * User-authored records are excluded by stable content selectors.  Never add a
 * broad container (for example `.proj`) to USER_CONTENT: doing so also shields
 * buttons and status chrome inside that container from translation.
 */
const I18N = {
  DICT: {
    "学术工作台": "Scholar Workspace",
    "本地模式": "Local mode",
    "本地模式（未接 Git）": "Local mode (Git not connected)",
    "已同步": "Synced",
    "同步出错，点此查看": "Sync error — click for details",
    "今日": "Today",
    "研究": "Research",
    "论文库": "Papers",
    "学术会议": "Conferences",
    "读文献": "Reading",
    "想法": "Ideas",
    "日程": "Schedule",
    "生活": "Life",
    "AI 与额度": "AI & Quota",
    "设置与教程": "Settings",
    "🏠 今日": "🏠 Today",
    "📊 研究": "📊 Research",
    "🏆 论文库": "🏆 Papers",
    "🎤 学术会议": "🎤 Conferences",
    "📚 读文献": "📚 Reading",
    "💡 想法": "💡 Ideas",
    "📅 日程": "📅 Schedule",
    "🌱 生活": "🌱 Life",
    "🤖 AI 与额度": "🤖 AI & Quota",
    "⚙️ 设置与教程": "⚙️ Settings",
    "完整使用教程": "Complete guide",
    "装修模式": "Layout editor",
    "本机设置": "Device settings",
    "Git 同步（Win ↔ Mac ↔ 云端 Claude）": "Git sync (Windows ↔ Mac ↔ cloud AI)",
    "日历订阅（Outlook / Google / 苹果日历）": "Calendar subscriptions (Outlook / Google / Apple)",
    "AI 直连 API（可选）": "Direct AI APIs (optional)",
    "推送渠道": "Notification channels",
    "邮箱收件（手机随手记）": "Email capture",
    "Overleaf 写作进展": "Overleaf writing progress",
    "学术雷达": "Research radar",
    "示例数据": "Sample data",
    "批量清理": "Bulk cleanup",
    "备份时光机": "Backup time machine",
    "表格导入（Excel / CSV）": "Table import (Excel / CSV)",
    "配置向导": "Setup wizard",
    "远程访问与手机": "Remote & mobile access",
    "导出诊断包": "Export diagnostic bundle",
    "我的设备": "My devices",
    "进行中的项目": "Active projects",
    "全部稿件": "All manuscripts",
    "阶段看板（可拖动）": "Stage board (drag to move)",
    "期刊档案": "Journal directory",
    "论文 PDF 库": "Local PDF library",
    "状态": "Status",
    "生命周期": "Lifecycle",
    "结果图表": "Figures & results",
    "笔记": "Notes",
    "文献索引": "Reference index",
    "领域助读": "Field primer",
    "关卡 · 主题进度": "Topic progress",
    "复习队列": "Review queue",
    "画布": "Canvas",
    "订阅日历": "Subscribed calendars",
    "月历": "Calendar",
    "甘特图（拖动条改日期，拖两端改工期）": "Gantt chart",
    "日程清单": "Schedule list",
    "饮食记录": "Diet",
    "运动记录": "Exercise",
    "清单": "Lists",
    "重要日子": "Important dates",
    "生活事务": "Life admin",
    "开支": "Finance",
    "Claude 信箱": "AI inbox",
    "Claude 回信 / 体检报告": "AI replies & audits",
    "AI 报告库": "AI report library",
    "手动跑一次": "Run a task",
    "额度调度器": "Quota controller",
    "逾期": "Overdue",
    "今天": "Today",
    "待分拣的速记": "Unsorted captures",
    "近期截止": "Upcoming deadlines",
    "稿件下一步": "Next manuscript actions",
    "本周一览": "This week",
    "今天完成了什么": "Completed today",
    "写作进展": "Writing progress",
    "AI 新产出": "New AI output",
    "今天该复习的文献": "Reading reviews due",
    "额度状态": "Quota status",
    "随手记": "Quick notes",
    "保存": "Save",
    "取消": "Cancel",
    "删除": "Delete",
    "编辑": "Edit",
    "新建": "New",
    "完成": "Done",
    "恢复默认": "Reset",
    "扫描": "Scan",
    "打开": "Open",
    "查看": "View",
    "分拣": "Sort",
    "留作想法": "Keep as idea",
    "隐藏示例": "Hide samples",
    "已开启": "Enabled",
    "未开启": "Disabled",
    "已启用": "Enabled",
    "未启用": "Disabled",
    "已完成": "Completed",
    "尚未完成": "Not completed",
    "已隐藏": "Hidden",
    "还没扫描": "Not scanned yet",
    "自动保存": "Autosaved",
    "＋ 已发表": "+ Published paper",
    "＋ 新项目": "+ New project",
    "🤖 问 AI": "🤖 Ask AI",
    "⚡ 快速捕捉": "⚡ Quick capture",
    "⚡ 捕捉": "⚡ Capture",
    "🤖 信箱": "🤖 Inbox",
    "🎛 布局": "🎛 Layout",
    "◐ 主题": "◐ Theme",
    "🔒 只读": "🔒 Read only",
    "🔓 可编辑": "🔓 Editable",
    "连不上本地服务": "Cannot reach the local service",
    "这一页出错了": "This page encountered an error",
    "还没有关联。": "No links yet.",
    "关联": "Links",
    "问 AI": "Ask AI",
    "菜单": "Menu",
    "点击同步": "Sync now",
    "搜索全部 · Cmd/Ctrl+K": "Search everything · Cmd/Ctrl+K",
    "搜记录 / 文献 / 功能设置 · Cmd/Ctrl+K": "Search records, papers, and settings · Cmd/Ctrl+K",
    "快速捕捉（按 c）": "Quick capture (press C)",
    "写给 Claude": "Write to AI",
    "日历": "Calendar",
    "调整布局：拖动排序、隐藏卡片、改标题": "Edit layout: reorder, hide, and rename cards",
    "切换深色 / 浅色": "Toggle dark / light theme",
    "正在载入…": "Loading…",
    "解锁": "Unlock",
    "解锁写入": "Unlock editing",
    "访问码": "Access code",
    "上一页": "Previous",
    "下一页": "Next",
    "上一步": "Previous",
    "下一步": "Next",
    "以后再说": "Not now",
    "跳过这步": "Skip this step",
    "完成设置 ✓": "Finish setup ✓",
    "开始": "Start",
    "欢迎使用学术工作台": "Welcome to Scholar Workspace",
    "你是谁": "About you",
    "这台电脑的路径": "Folders on this computer",
    "GitHub 同步": "GitHub sync",
    "日历与天气": "Calendar & weather",
    "推送渠道": "Notification channels",
    "推送通知": "Notifications",
    "AI 与额度调度": "AI & quota scheduling",
    "学术偏好": "Research preferences",
    "隐私与安全": "Privacy & security",
    "导入你现有的表格": "Import an existing table",
    "Overleaf 写作进展（可跳过）": "Overleaf writing progress (optional)",
    "AI 直连 API（可跳过）": "Direct AI APIs (optional)",
    "核对一下，就可以开始了": "Review and start",
    "花三分钟把该配的一次配完，之后就不用再管了。每一步都可以跳过，跳过的会在设置页留个提醒。": "Take three minutes to configure the essentials. Optional steps can be skipped and completed later in Settings.",
    "用于称呼、天气定位，以及给雷达功能一组默认关键词。": "Used for your display name, weather location, and default research-radar keywords.",
    "每台设备各填一次，这些不会同步到另一台机器。": "Configure these folders once per device; they are never synced to another computer.",
    "这是 Mac ↔ Windows ↔ 手机 ↔ 云端 Claude 之间唯一的桥。建议私有仓库。": "This private repository connects macOS, Windows, mobile access, and cloud AI tasks.",
    "右上角那个日历面板的数据源。ICS 是只读订阅，不需要授权，安全。": "Data sources for the calendar panel. ICS subscriptions are read-only and require no account authorization.",
    "周一早上的「本周开局」，以及逾期和体检告警，从这里发给你。钉钉是主通道；邮件和自定义 webhook 可选。": "Send weekly plans, overdue reminders, and audit alerts through DingTalk, email, or a custom webhook.",
    "订阅额度用不完也不滚存。告诉我你的作息，我就知道什么时候替你把它花掉、什么时候该让路。": "Set your working hours so optional AI tasks run outside your active sessions and stay within quota.",
    "几个阈值，之后在设置里随时能改。": "A few defaults that can be changed later in Settings.",
    "决定什么留在本机、什么能被远程访问。": "Choose what stays local and what remote devices may access.",
    "期刊清单、投稿记录……有就拖进来，没有就跳过，以后随时能导。": "Import journal lists or submission records now, or skip this step and import them later.",
    "如果你用 Overleaf 写论文，工作台可以每天自动读出「今天改了哪几节、增删多少行、字数变化」，替你把进展记下来。没有付费版就跳过，不影响任何功能。": "With a paid Overleaf plan, the workspace can record daily section, line, and word-count changes. Skip this optional step otherwise.",
    "这一步跟前面的「打开 Claude / ChatGPT」不是一回事——那两个是跳到网页或桌面软件，这里是让工作台自己去调接口。不填也完全不影响使用。": "Optional API access lets the workspace call an AI provider directly. It is separate from opening Claude or ChatGPT and can be left blank.",
    "下面是刚才填的内容。有不对的可以退回去改，也可以完成后在设置页随时改。": "Review what you entered. Go back to make changes, or update these values later in Settings.",
    "给你的工作台起个名字": "Workspace name",
    "副标题": "Subtitle",
    "称呼": "Name",
    "所在城市": "City",
    "学科领域": "Research field",
    "关注的研究主题关键词": "Research keywords",
    "时区": "Time zone",
    "定位": "Locate",
    "本机名称": "Device name",
    "论文根目录": "Paper root folder",
    "其它论文目录（可选，一行一个）": "Other paper folders (optional, one per line)",
    "OneDrive 长期备份目录": "OneDrive long-term backup folder",
    "浏览器": "Browser",
    "检查这个目录": "Check folder",
    "GitHub 用户名": "GitHub username",
    "Personal Access Token": "Personal Access Token",
    "私有仓库地址": "Private repository URL",
    "测试连接": "Test connection",
    "我确认这是私有仓库，且不是 workspace-for-all 公共源码仓库": "I confirm this repository is private and is not the public workspace-for-all source repository",
    "选择文件（.xlsx / .csv）": "Choose file (.xlsx / .csv)",
    "导入到": "Import into",
    "稿件库": "Manuscripts",
    "会议": "Conferences",
    "文献": "Reading",
    "保存中…": "Saving…",
    "同步中…": "Syncing…",
    "同步完成": "Sync complete",
    "确定删除？": "Delete this item?",
    "确定删除？（会移到 local/trash，可找回）": "Delete this item? It will move to local/trash and can be recovered.",
    "没有匹配的记录。": "No matching records.",
    "关联到…": "Link to…",
    "搜标题…（回车选第一条）": "Search titles… (Enter selects the first)",
    "返回": "Back",
    "全选本页": "Select page",
    "取消选择": "Clear selection",
    "存档": "Archive",
    "载入中…": "Loading…",
    "打开 PDF ↗": "Open PDF ↗",
    "打开文件 ↗": "Open file ↗",
    "已保存": "Saved",
    "已删除": "Deleted",
    "已刷新": "Refreshed",
    "已关联": "Linked",
    "已解除关联": "Link removed",
    "已复制": "Copied",
    "已备份": "Backed up",
    "备份失败": "Backup failed",
    "已恢复": "Restored",
    "已恢复默认": "Defaults restored",
    "已恢复默认布局": "Default layout restored",
    "已清空": "Cleared",
    "已标记": "Marked",
    "已记录复习": "Review recorded",
    "事件已记录": "Event recorded",
    "设置已保存": "Settings saved",
    "本机设置已保存": "Device settings saved",
    "远程设置已保存": "Remote settings saved",
    "推送设置已保存": "Notification settings saved",
    "刷新中…": "Refreshing…",
    "读取失败": "Load failed",
    "执行失败": "Task failed",
    "一条都没选": "Nothing selected",
    "两个都空着，没什么可存的": "There is nothing to save",
    "当前已可编辑，到时间会自动回到只读": "Editing is already unlocked; it will return to read-only automatically",
    "已解锁写入，30 分钟后自动回到只读": "Editing unlocked for 30 minutes",
    "示例已隐藏 —— 设置里可以随时恢复或彻底删掉": "Samples hidden — restore or remove them in Settings",
    "设置完成！正在跑第一次全库体检…": "Setup complete — running the first workspace audit…",
    "项目 / 任务": "Project / task",
    "暂无带日期的条目": "No dated items",
    "点此收起/展开": "Collapse / expand",
    "用逗号分隔": "Separate with commas",
    "笔记 / 正文（Markdown）": "Notes / body (Markdown)",
    "＋ 关联到别的记录": "+ Link another record",
    "打开这一条": "Open record",
    "解除关联": "Remove link",
    "需要访问码": "Access code required",
    "进入": "Continue",
    "只读": "Read only",
    "记一笔": "Quick capture",
    "只做一件事：把念头存下来。之后在电脑上分类。": "Capture a thought now and organize it later on your computer.",
    "💡 想法": "💡 Idea",
    "❓ 疑问": "❓ Question",
    "📅 待办": "📅 Task",
    "✅ 完成": "✅ Done",
    "存进工作台": "Save to workspace",
    "← 打开完整工作台": "← Open full workspace"
  },

  /* Longer reusable fragments are applied only after exact lookup.  They cover
     counters and status sentences without translating record titles. */
  PARTS: [
    ["第 ", "Step "], [" 步", ""], ["未提交改动", "uncommitted changes"],
    ["最近提交", "latest commit"], ["私有仓库", "private repository"],
    ["远程默认只读", "remote access is read-only by default"],
    ["保存失败", "Save failed"], ["初始化失败", "Initialization failed"],
    ["查询中…", "Searching…"], ["检查中…", "Checking…"],
    ["没有新变化", "No new changes"], ["已创建，可以用了", "Created and ready"],
    ["还没有", "No "], ["未设置", "Not configured"], ["当前时间", "Current time"],
    ["来自 Overleaf", "From Overleaf"], ["含 Outlook", "Includes Outlook"],
    ["进行中", "active"], ["待处理", "pending"], ["条事件", "events"],
    ["个项目", "projects"], ["个领域", "fields"], ["个文件夹", "folders"]
  ],
  PREFIXES: [
    ["保存失败：", "Save failed: "], ["加载失败：", "Load failed: "],
    ["读取失败：", "Load failed: "], ["恢复失败：", "Restore failed: "],
    ["执行失败：", "Task failed: "], ["初始化失败：", "Initialization failed: "],
    ["同步出错：", "Sync error: "], ["同步未完成 · ", "Sync incomplete · "],
    ["已更新为「", "Updated to “"], ["已移到「", "Moved to “"],
    ["进度 ", "Progress "], ["待处理已达 ", "Pending items: "]
  ],

  USER_CONTENT: [
    "textarea", "[contenteditable='true']", "[data-user-content]", ".record-title",
    ".rl-title", ".card-note", ".markdown", ".note .nt", ".note .body",
    ".proj-h b", ".proj-m", ".sr-title", ".sr-snip", ".chip-go", ".cap"
  ].join(","),

  isEnglish() {
    return ((S.config || {}).language || "zh-CN") === "en";
  },

  t(zh, en) {
    if (!this.isEnglish()) return zh;
    return en || this.DICT[String(zh)] || zh;
  },

  translateText(raw) {
    const lead = raw.match(/^\s*/)[0], tail = raw.match(/\s*$/)[0];
    const s = raw.trim();
    if (!s) return raw;
    let out = this.DICT[s];
    if (!out) {
      let m;
      if ((m = s.match(/^(\d+) 个$/))) out = `${m[1]} items`;
      else if ((m = s.match(/^(\d+) 篇$/))) out = `${m[1]} papers`;
      else if ((m = s.match(/^(\d+) 条$/))) out = `${m[1]} items`;
      else if ((m = s.match(/^(\d+) 项$/))) out = `${m[1]} items`;
      else if ((m = s.match(/^(\d+) 件$/))) out = `${m[1]} items`;
      else if ((m = s.match(/^(\d+) 天内$/))) out = `Within ${m[1]} days`;
      else if ((m = s.match(/^待同步 (\d+) 处$/))) out = `${m[1]} changes to sync`;
      else if ((m = s.match(/^逾期 (\d+) 天$/))) out = `${m[1]} days overdue`;
      else if ((m = s.match(/^(\d+) 天后$/))) out = `In ${m[1]} days`;
      else if (s === "明天") out = "Tomorrow";
      else if ((m = s.match(/^(\d+) 分$/))) out = `${m[1]} min`;
      else if ((m = s.match(/^已选 (\d+) 条$/))) out = `${m[1]} selected`;
      else if ((m = s.match(/^还有 (\d+) 条，点开看$/))) out = `${m[1]} more — show all`;
      else if ((m = s.match(/^第 (\d+) \/ (\d+) 步$/))) out = `Step ${m[1]} of ${m[2]}`;
      else if ((m = s.match(/^没找到「(.+)」$/))) out = `No results for “${m[1]}”`;
      else if ((m = s.match(/^共 (\d+) 条$/))) out = `${m[1]} total`;
      else {
        const prefix = this.PREFIXES.find(([from]) => s.startsWith(from));
        if (prefix) out = prefix[1] + s.slice(prefix[0].length).replace(/」$/, "”");
      }
      if (!out && /^[^\u4e00-\u9fff]*[\u4e00-\u9fff]/.test(s)) {
        let candidate = s;
        this.PARTS.forEach(([from, to]) => { candidate = candidate.split(from).join(to); });
        if (candidate !== s && !/[\u4e00-\u9fff]/.test(candidate)) out = candidate;
      }
    }
    return out ? lead + out + tail : raw;
  },

  apply(root) {
    document.documentElement.lang = this.isEnglish() ? "en" : "zh-CN";
    const scope = root || document.body;
    if (!scope) return;
    this.enhance(scope);
    if (!this.isEnglish()) return;
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const p = node.parentElement;
      if (!p || p.closest("script,style,code,pre," + this.USER_CONTENT)) return;
      const translated = this.translateText(node.nodeValue || "");
      if (translated !== node.nodeValue) node.nodeValue = translated;
    });
    const attrEls = [];
    if (scope.nodeType === 1 && scope.matches("[placeholder],[title],[aria-label]")) attrEls.push(scope);
    attrEls.push(...scope.querySelectorAll("[placeholder],[title],[aria-label]"));
    attrEls.forEach(el => {
      ["placeholder", "title", "aria-label"].forEach(attr => {
        const value = el.getAttribute(attr);
        if (value) {
          const translated = this.translateText(value);
          if (translated !== value) el.setAttribute(attr, translated);
        }
      });
    });
  },

  enhance(scope) {
    const labels = [];
    if (scope.nodeType === 1 && scope.matches("label")) labels.push(scope);
    labels.push(...scope.querySelectorAll("label"));
    labels.forEach((label, index) => {
      if (label.htmlFor) return;
      const control = label.querySelector("input,select,textarea")
        || (label.parentElement && label.parentElement.querySelector("input:not([type='hidden']),select,textarea"));
      if (!control) return;
      if (!control.id) control.id = `field_${Date.now()}_${index}`;
      if (!label.contains(control)) label.htmlFor = control.id;
    });
    const icons = [];
    if (scope.nodeType === 1 && scope.matches("button")) icons.push(scope);
    icons.push(...scope.querySelectorAll("button"));
    icons.forEach(button => {
      if (button.hasAttribute("aria-label")) return;
      const text = (button.textContent || "").trim();
      if (button.title) button.setAttribute("aria-label", button.title);
      else if (text && text.length <= 3) button.setAttribute("aria-label", text === "✕" ? "Close" : text);
    });
  },

  observe() {
    if (this._observer || !document.body) return;
    this._observer = new MutationObserver(records => {
      if (this._applying) return;
      this._applying = true;
      try {
        records.forEach(record => {
          if (record.type === "characterData") this.apply(record.target.parentElement);
          else record.addedNodes.forEach(node => {
            if (node.nodeType === 1) this.apply(node);
            else if (node.nodeType === 3 && node.parentElement) this.apply(node.parentElement);
          });
        });
      } finally { this._applying = false; }
    });
    this._observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  },

  async toggle() {
    const previous = (S.config || {}).language || "zh-CN";
    const language = this.isEnglish() ? "zh-CN" : "en";
    const button = document.getElementById("langBtn");
    if (button) button.disabled = true;
    try {
      await saveConfig({ language }, { throwOnError: true });
      try { localStorage.setItem("sw_language", language); } catch (e) { }
      location.reload();
      return true;
    } catch (error) {
      S.config.language = previous;
      if (button) button.disabled = false;
      toast(this.t("语言没有保存成功，请检查本地服务后重试。", "Language was not saved. Check the local service and try again."));
      return false;
    }
  }
};

function tr(zh, en) { return I18N.t(zh, en); }
