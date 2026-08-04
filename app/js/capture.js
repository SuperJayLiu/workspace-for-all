/* 智能速记解析：能用算法就不用 AI
   输入一句自然语言，尽量把结构化字段抽干净，减少你二次录入。
   纯函数、可单元测试、零网络、零 AI 成本。 */

const CAP = {

  /* ---------------------------------------------------------- 日期解析 */
  // 支持：今天/明天/后天/大后天、下周三、周五、本周日、8月10日、8/10、2026-08-10、
  //      3天后、两周后、月底、下个月、每周一（重复）
  CN_NUM: { 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 },
  WD: { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 7, 天: 7 },

  num(s) {
    if (!s) return null;
    if (/^\d+$/.test(s)) return Number(s);
    if (s.length === 1) return CAP.CN_NUM[s] ?? null;
    if (s === "十") return 10;
    const m = s.match(/^十(.)$/); if (m) return 10 + (CAP.CN_NUM[m[1]] || 0);
    const m2 = s.match(/^(.)十(.)?$/);
    if (m2) return (CAP.CN_NUM[m2[1]] || 0) * 10 + (m2[2] ? CAP.CN_NUM[m2[2]] || 0 : 0);
    return null;
  },

  _d(base, days) { const d = new Date(base); d.setDate(d.getDate() + days); return d; },
  _iso(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
      "-" + String(d.getDate()).padStart(2, "0");
  },

  parseDate(text, now) {
    now = now || new Date();
    const t = text;
    const hit = (re, fn) => { const m = t.match(re); return m ? fn(m) : null; };
    let r =
      hit(/(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})/, m => new Date(+m[1], +m[2] - 1, +m[3])) ||
      hit(/(\d{1,2})[-/月](\d{1,2})日?/, m => {
        const d = new Date(now.getFullYear(), +m[1] - 1, +m[2]);
        if (d < CAP._d(now, -1)) d.setFullYear(d.getFullYear() + 1);   // 过去的日期视为明年
        return d;
      }) ||
      hit(/大后天/, () => CAP._d(now, 3)) ||
      hit(/后天/, () => CAP._d(now, 2)) ||
      hit(/明天|明日/, () => CAP._d(now, 1)) ||
      hit(/今天|今日/, () => new Date(now)) ||
      hit(/昨天/, () => CAP._d(now, -1)) ||
      hit(/([一二两三四五六七八九十\d]+)\s*天[后内]/, m => CAP._d(now, CAP.num(m[1]) || 0)) ||
      hit(/([一二两三四五六七八九十\d]+)\s*周[后内]/, m => CAP._d(now, (CAP.num(m[1]) || 0) * 7)) ||
      hit(/([一二两三四五六七八九十\d]+)\s*个?月[后内]/, m => {
        const d = new Date(now); d.setMonth(d.getMonth() + (CAP.num(m[1]) || 0)); return d;
      }) ||
      hit(/(下+)\s*(?:个)?周\s*([一二三四五六日天])/, m => {
        const weeks = m[1].length;
        const target = CAP.WD[m[2]];
        const cur = now.getDay() === 0 ? 7 : now.getDay();
        return CAP._d(now, (target - cur) + 7 * weeks);
      }) ||
      hit(/(?:这|本)?\s*(?:个)?(?:周|星期|礼拜)\s*([一二三四五六日天])/, m => {
        const target = CAP.WD[m[1]];
        const cur = now.getDay() === 0 ? 7 : now.getDay();
        let delta = target - cur;
        if (delta < 0) delta += 7;                 // 已过则顺延到下一个
        return CAP._d(now, delta);
      }) ||
      hit(/下(?:个)?月/, () => { const d = new Date(now); d.setMonth(d.getMonth() + 1); return d; }) ||
      hit(/月底/, () => new Date(now.getFullYear(), now.getMonth() + 1, 0)) ||
      hit(/月初/, () => new Date(now.getFullYear(), now.getMonth() + 1, 1));
    if (!r || isNaN(r)) return null;
    return CAP._iso(r);
  },

  parseTime(text) {
    let m = text.match(/(\d{1,2})[:：](\d{2})/);
    if (m) return String(+m[1]).padStart(2, "0") + ":" + m[2];
    m = text.match(/(上午|下午|晚上|中午|早上)?\s*([一二三四五六七八九十\d]+)\s*点(半|[一二三四五六七八九十\d]+分?)?/);
    if (m) {
      let h = CAP.num(m[2]);
      if (h == null) return null;
      const period = m[1] || "";
      if (/下午|晚上/.test(period) && h < 12) h += 12;
      if (period === "中午" && h < 12) h = 12;
      let mm = 0;
      if (m[3] === "半") mm = 30;
      else if (m[3]) mm = CAP.num(String(m[3]).replace("分", "")) || 0;
      return String(h).padStart(2, "0") + ":" + String(mm).padStart(2, "0");
    }
    return null;
  },

  parseRepeat(text) {
    if (/每天|每日/.test(text)) return "daily";
    if (/每周|每星期/.test(text)) return "weekly";
    if (/每月|每个月/.test(text)) return "monthly";
    if (/每年|每一年/.test(text)) return "yearly";
    return "";
  },

  /* ---------------------------------------------------- 链接 / 标识符 */
  parseRefs(text) {
    const urls = text.match(/https?:\/\/[^\s，。；）)]+/g) || [];
    const doi = (text.match(/\b10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+/) || [])[0] || "";
    const arxiv = (text.match(/arxiv\.org\/abs\/(\d{4}\.\d{4,5})/i) ||
      text.match(/\barXiv:\s*(\d{4}\.\d{4,5})/i) || [])[1] || "";
    const ssrn = /ssrn\.com/i.test(text);
    return { urls, doi, arxiv, ssrn };
  },

  /* -------------------------------------------------------- 数量抽取 */
  parseAmount(text) {
    const m = text.match(/(?:¥|￥|\$|花了|花费|付了?)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:元|块|镑|刀|欧)/);
    if (!m) return null;
    return Number(m[1] || m[2]);
  },
  parseMinutes(text) {
    let m = text.match(/(\d+(?:\.\d+)?)\s*(?:分钟|min|分)/i);
    if (m) return Math.round(Number(m[1]));
    m = text.match(/(\d+(?:\.\d+)?)\s*(?:小时|h|hr|hours?)/i);
    if (m) return Math.round(Number(m[1]) * 60);
    m = text.match(/([一二两三四五六七八九十]+)\s*(?:个)?小时/);
    if (m) return (CAP.num(m[1]) || 0) * 60;
    return null;
  },
  parseKm(text) {
    const m = text.match(/(\d+(?:\.\d+)?)\s*(?:公里|km|千米)/i);
    return m ? Number(m[1]) : null;
  },
  parsePages(text) {
    const m = text.match(/(\d{4})\s*年?/);
    return m && +m[1] >= 1900 && +m[1] <= 2100 ? +m[1] : null;
  },

  /* -------------------------------------------------------- 类型判定 */
  // 纯规则。判不准时返回 unknown，交给用户选（而不是花 AI 的钱去猜）。
  KW: {
    exercise: /跑步|健身|游泳|骑车|骑行|羽毛球|篮球|足球|网球|瑜伽|力量|撸铁|快走|徒步|爬山|做操|拉伸|运动|锻炼|gym|run|swim|yoga/i,
    diet: /早饭|早餐|午饭|午餐|晚饭|晚餐|夜宵|加餐|吃了|喝了|外卖|食堂|咖啡|奶茶|面|饭|菜|肉|沙拉|水果/,
    finance: /花了|花费|付了|买了|报销|房租|水电|机票|车票|订阅费|会员费|¥|￥|\$|元|块钱/,
    reading: /论文|文献|paper|读了|在读|待读|(?<!合)作者|期刊|journal|arxiv|ssrn|doi|working paper|\bjf\b|\bjfe\b|\brfs\b|\baer\b|\bqje\b/i,
    manuscript: /稿子|稿件|我的论文|section|投稿|返修|审稿意见|response|初稿|终稿|表\s*\d|figure\s*\d|table\s*\d/i,
    conference: /会议|年会|研讨会|workshop|conference|seminar|报名|注册费|摘要提交/i,
    schedule: /开会|见面|约了|讨论|答辩|上课|讲座|面试|视频|通话|meeting|call/,
    admin: /交房租|缴费|续签|签证|保险|体检|报税|快递|取件|预约|挂号|换证|年检|续订|物业费|水费|电费|燃气|宽带|话费|会员费|订阅费|还款|信用卡/,
    todo: /要|得|需要|记得|别忘|todo|待办|提醒我/,
    idea: /想法|点子|idea|或许|是不是可以|能不能|如果.*会不会|假设/,
  },

  classify(text) {
    const t = text || "";
    const refs = CAP.parseRefs(t);
    if (refs.doi || refs.arxiv || refs.ssrn) return "reading";
    const scores = {};
    for (const [k, re] of Object.entries(CAP.KW)) {
      const m = t.match(new RegExp(re.source, re.flags.includes("i") ? "gi" : "g"));
      if (m) scores[k] = m.length;
    }
    // 强信号优先；日程带明确时间点时压过"论文相关"的弱线索
    if (scores.exercise && CAP.parseMinutes(t)) return "exercise";
    if (scores.finance && CAP.parseAmount(t) != null && !CAP.parseRepeat(t)) return "finance";
    if (scores.diet && !scores.exercise) return "diet";
    if (scores.schedule && (CAP.parseDate(t) || CAP.parseTime(t))) return "schedule";
    if (scores.reading) return "reading";
    if (scores.manuscript) return "manuscript";
    if (scores.conference) return "conference";
    if (scores.admin) return "admin";
    // 有重复周期的多半是周期性事务（交费、续订之类）
    if (CAP.parseRepeat(t)) return "admin";
    if (scores.idea) return "idea";
    if (scores.todo) return "todo";
    return "unknown";
  },

  /* --------------------------------------------------- 一句话 → 记录 */
  // 返回 {collection, record, notes[]}：notes 说明"我替你填了什么"，便于你核对。
  toRecord(text, hintKind, now) {
    return CAP.honestNotes(CAP._toRecord(text, hintKind, now));
  },

  _toRecord(text, hintKind, now) {
    const t = (text || "").trim();
    const kind = hintKind && hintKind !== "auto" ? hintKind : CAP.classify(t);
    const date = CAP.parseDate(t, now);
    const time = CAP.parseTime(t);
    const repeat = CAP.parseRepeat(t);
    const refs = CAP.parseRefs(t);
    const notes = [];
    const today = CAP._iso(now || new Date());
    // 标题：去掉已被结构化吸收的时间词，避免重复
    let title = t
      .replace(/https?:\/\/\S+/g, "")
      // 「月底前」要整个去掉，只去「月底」会留下一个孤零零的「前」；
      // 「每周一交周报」里的「周一」不能动，否则剩下「每交周报」
      .replace(/(今天|明天|后天|大后天|昨天)/g, "")
      .replace(/(月底|月初|下个?月|本月)[前内以]?/g, "")
      .replace(/下+个?周[一二三四五六日天][前内]?/g, "")
      .replace(/(?<!每)(?:这|本)?个?(?:周|星期|礼拜)[一二三四五六日天](?![^\s，,。.]*报)/g, "")
      .replace(/\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?/g, "")
      .replace(/\d{1,2}[-/月]\d{1,2}日?/g, "")
      .replace(/[一二两三四五六七八九十\d]+\s*(?:天|周|个?月)[后内]/g, "")
      .replace(/^\s*(?:之前|以前|前|之内|以内|内|之后|以后)\s*/g, "")
      .replace(/^[，,。.、\s]+|[，,。.、\s]+$/g, "")
      .trim() || t;
    if (date) notes.push("日期 " + date);
    if (time) notes.push("时间 " + time);
    if (repeat) notes.push("重复 " + { daily: "每天", weekly: "每周", monthly: "每月", yearly: "每年" }[repeat]);

    switch (kind) {
      case "exercise": {
        const mins = CAP.parseMinutes(t), km = CAP.parseKm(t);
        if (mins) notes.push(mins + " 分钟");
        if (km) notes.push(km + " 公里");
        return {
          collection: "exercise", notes,
          record: {
            date: date || today, title: title || "运动", minutes: mins || null,
            km: km || null, intensity: /大强度|高强度|冲刺|极限/.test(t) ? "hard"
              : /轻松|慢跑|散步|拉伸/.test(t) ? "light" : "moderate",
          },
        };
      }
      case "diet": {
        const kcal = (t.match(/(\d{2,4})\s*(?:kcal|大卡|卡)/i) || [])[1];
        const meal = /早饭|早餐|早上吃/.test(t) ? "breakfast"
          : /午饭|午餐|中午吃/.test(t) ? "lunch"
            : /晚饭|晚餐|晚上吃/.test(t) ? "dinner"
              : /夜宵|加餐|下午茶/.test(t) ? "snack" : CAP.mealByHour(now);
        if (kcal) notes.push(kcal + " kcal");
        notes.push("餐次 " + { breakfast: "早", lunch: "午", dinner: "晚", snack: "加餐" }[meal]);
        return {
          collection: "diet", notes,
          record: { date: date || today, meal, title: title || "一餐", kcal: kcal ? +kcal : null },
        };
      }
      case "finance": {
        const amt = CAP.parseAmount(t);
        if (amt != null) notes.push("金额 " + amt);
        const cat = /房租|水电|物业|家|家具/.test(t) ? "home"
          : /机票|车票|打车|地铁|酒店|住宿/.test(t) ? "travel"
            : /书|论文|版面费|会议|注册费|数据/.test(t) ? "research"
              : /电影|游戏|演出|旅游/.test(t) ? "fun"
                : /吃|饭|咖啡|外卖|超市|菜/.test(t) ? "food" : "other";
        return {
          collection: "finance", notes,
          record: { date: date || today, title: title || "支出", amount: amt, cat },
        };
      }
      case "reading": {
        const year = CAP.parsePages(t);
        const rec = {
          title: title || "（待补题目）", status: "to-read", level: "skim",
          link: refs.urls[0] || (refs.arxiv ? "https://arxiv.org/abs/" + refs.arxiv : ""),
          doi: refs.doi || "",
        };
        if (date) rec.due = date;              // 「月底前读完」这个日期要真的存下来
        if (time) rec.due_time = time;
        if (year) { rec.year = year; notes.push("年份 " + year); }
        if (refs.doi) notes.push("DOI " + refs.doi);
        if (refs.arxiv) notes.push("arXiv " + refs.arxiv);
        // 常见期刊缩写自动识别
        const j = (t.match(/\b(JF|JFE|RFS|AER|QJE|JPE|ReStud|Econometrica|RFS|JFQA|MS|JAR|TAR)\b/i) || [])[1];
        if (j) { rec.journal = j.toUpperCase(); notes.push("期刊 " + rec.journal); }
        const topic = (S.config.profile || {}).keywords || [];
        const hitTopic = topic.find(k => t.toLowerCase().includes(String(k).toLowerCase()));
        if (hitTopic) { rec.topic = hitTopic; notes.push("归入关卡「" + hitTopic + "」"); }
        return { collection: "reading", notes, record: rec };
      }
      case "manuscript": {
        // 不新建稿件（太重），而是挂到最匹配的稿件的「下一步」上
        const ms = CAP.matchManuscript(t);
        if (ms) {
          notes.push("挂到稿件「" + (ms.title || "").slice(0, 18) + "…」");
          return {
            collection: "manuscripts", patchId: ms.id, notes,
            record: { next_action: title, next_action_due: date || ms.next_action_due || "" },
          };
        }
        return { collection: "ideas", notes,
                 record: Object.assign({ title, kind: "idea", status: "new", source: "capture" },
                                       date ? { due: date } : {}, time ? { due_time: time } : {}) };
      }
      case "conference":
        return {
          collection: "conferences", notes,
          record: Object.assign({ title: title || "会议", deadline: date || "", status: "watching",
                                  url: refs.urls[0] || "" }, time ? { time } : {}),
        };
      case "schedule":
        return {
          collection: "schedule", notes,
          record: {
            title: title || "日程", start: date || today, end: date || today,
            time: time || "", kind: /开会|讨论|见面|meeting|call|视频/.test(t) ? "meeting" : "task", done: false,
          },
        };
      case "admin":
        return {
          collection: "admin", notes,
          record: { title: title || "事务", date: date || "", repeat, done: false },
        };
      case "todo":
        return {
          collection: "schedule", notes,
          record: { title: title || t, start: date || today, end: date || today, kind: "task", done: false },
        };
      case "idea":
      default: {
        const rec = { title: title || t, kind: /[?？]|是不是|能不能|会不会/.test(t) ? "question" : "idea",
                      status: "new", source: "capture",
                      body: refs.urls.length ? refs.urls.join("\n") : "" };
        if (date) rec.due = date;              // 以前只在提示里说「已填好日期」，实际没存
        if (time) rec.due_time = time;
        return { collection: "ideas", notes, record: rec };
      }
    }
  },

  /* 提示只说真话：字段没进记录就不要写在「已替你填好」里 */
  honestNotes(res) {
    const rec = res.record || {};
    const has = k => rec[k] !== undefined && rec[k] !== "" && rec[k] !== null;
    const dateIn = has("due") || has("date") || has("start") || has("deadline") ||
      has("read_date") || has("next_action_due");
    const timeIn = has("due_time") || has("time");
    res.notes = (res.notes || []).filter(n => {
      if (/^日期 /.test(n)) return dateIn;
      if (/^时间 /.test(n)) return timeIn;
      return true;
    });
    return res;
  },


  /* 记完一条之后，顺手给一句可以直接拿去问 AI 的话。
     模板按类型写死，不花任何 AI 成本；点一下就带着上下文跳过去。 */
  AI_TEMPLATES: {
    diet: r => `我今天这一餐是「${r.title || ""}」${r.kcal ? `（约 ${r.kcal} kcal）` : ""}。` +
      `请估一下热量与三大营养素的大致构成，指出一个最值得改的地方，并给两个同样方便、更均衡的替代吃法。别说教，直接给结论。`,
    exercise: r => `我今天运动是「${r.title || ""}」${r.minutes ? `${r.minutes} 分钟` : ""}${r.km ? `，${r.km} 公里` : ""}。` +
      `按我这个量，评估一下强度是否合适，下一次可以怎么小幅进阶；如果这周量偏少，给一个能在 20 分钟内完成的补充方案。`,
    reading: r => `我要读这篇文献：《${r.title || ""}》${r.journal ? `（${r.journal}）` : ""}${r.doi ? ` DOI ${r.doi}` : ""}。` +
      `请先用三句话说清它想回答什么问题、用了什么识别策略、结论是什么；然后指出两处最可能被审稿人攻击的地方；` +
      `最后说它和我的研究（${(S.config.profile || {}).field || "金融"}）可能有什么接口。`,
    idea: r => `我刚记下一个想法：「${r.title || ""}」。` +
      `请帮我把它逼成一个可检验的经济学问题：它在跟哪个既有解释竞争？最干净的识别来自哪种变异？` +
      `需要什么数据？如果这个想法已经被做过，告诉我最接近的三篇，并说清我还剩什么空间。`,
    question: r => `我有个疑问：「${r.title || ""}」。` +
      `请先判断这是概念问题还是实证问题，然后给一个不绕弯的回答，最后指出我这个问题里可能藏着的错误前提。`,
    manuscript: r => `我的稿子下一步是「${r.next_action || r.title || ""}」。` +
      `请把它拆成今天就能动手的三步，每步给一个完成标准；如果这一步本身有更省事的做法，直接说。`,
    conference: r => `我在考虑投这个会议：「${r.title || ""}」${r.deadline ? `，截稿 ${r.deadline}` : ""}。` +
      `请判断它对我这个阶段（博士生，${(S.config.profile || {}).field || "金融"}）值不值得投，` +
      `以及在截稿前应该优先把稿子的哪一部分打磨到什么程度。`,
    finance: r => `我记了一笔开支：「${r.title || ""}」${r.amount ? ` ${r.amount} 元` : ""}。` +
      `帮我判断这类支出在我的整体结构里算不算异常，以及有没有更划算的替代。`,
    schedule: r => `我安排了「${r.title || ""}」${r.time ? ` ${r.time}` : ""}。` +
      `帮我列一个 5 分钟就能过一遍的准备清单，只列真的会影响结果的事。`,
  },

  aiPrompt(collection, rec) {
    const kindMap = {
      diet: "diet", exercise: "exercise", reading: "reading", ideas: rec.kind === "question" ? "question" : "idea",
      manuscripts: "manuscript", conferences: "conference", finance: "finance", schedule: "schedule",
      admin: "schedule", lists: "schedule",
    };
    const fn = CAP.AI_TEMPLATES[kindMap[collection]];
    return fn ? fn(rec || {}) : "";
  },

  mealByHour(now) {
    const h = (now || new Date()).getHours();
    return h < 10 ? "breakfast" : h < 15 ? "lunch" : h < 21 ? "dinner" : "snack";
  },

  /* 把一句话和已有稿件做模糊匹配（纯算法：词重叠 + 连续子串） */
  matchManuscript(text) {
    const list = (typeof rows === "function" ? rows("manuscripts") : []) || [];
    const t = text.toLowerCase();
    let best = null, bestScore = 0;
    list.forEach(m => {
      const title = String(m.title || "").toLowerCase();
      if (!title) return;
      let score = 0;
      title.split(/[\s:：,，·]+/).filter(w => w.length > 3).forEach(w => {
        if (t.includes(w)) score += w.length;
      });
      if (m.current_journal && t.includes(String(m.current_journal).toLowerCase())) score += 6;
      if (score > bestScore) { bestScore = score; best = m; }
    });
    return bestScore >= 5 ? best : null;
  },

  /* 想法去重：纯算法初筛（字符级 Jaccard），只有拿不准时才建议用 AI 复核 */
  similar(a, b) {
    const norm = s => String(s || "").toLowerCase().replace(/[\s，。,.、；;：:!！?？"'"'（）()]/g, "");
    const A = new Set(norm(a)), B = new Set(norm(b));
    if (!A.size || !B.size) return 0;
    let inter = 0; A.forEach(c => { if (B.has(c)) inter++; });
    return inter / (A.size + B.size - inter);
  },
  /* 只在**内存里那份**上找相似。生活流水首屏只带近期的，
     所以「没弹出重复提示」不等于「以前没记过」——
     一笔一年交一次的房租，去年那条根本不在内存里。
     这里不去补拉全量（速记要在敲字时立刻出结果，不能等网络），
     而是把这个边界如实交出去，由界面决定怎么说。 */
  findDuplicates(text, collection, threshold) {
    threshold = threshold || 0.62;
    const list = (typeof rows === "function" ? rows(collection) : []) || [];
    const out = list.map(r => ({ rec: r, sim: CAP.similar(text, r.title) }))
      .filter(x => x.sim >= threshold)
      .sort((a, b) => b.sim - a.sim).slice(0, 3);
    out.partial = typeof isPartial === "function" && isPartial(collection);
    return out;
  },
};

if (typeof module !== "undefined") module.exports = CAP;
