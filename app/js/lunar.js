/* 农历 / 节气 / 干支 · 离线算法（1900–2100）
   数据来源：通行的农历压缩表（源自紫金山天文台历表），与二十四节气的分钟偏移表。
   纯查表 + 算术，不联网、确定性、毫秒级。不需要也不应该让 AI 来"核对"它。 */

const LUNAR = {
  // 每年一个 20 位二进制：闰月大小 + 12/13 个月的大小月 + 闰月月份
  INFO: [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x055c0, 0x0ab60, 0x096d5, 0x092e0,
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,
    0x0a2e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,
    0x0d520,
  ],
  // 二十四节气：以 1900-01-06 02:05:00 为基准的分钟偏移
  TERM_INFO: [
    0, 21208, 42467, 63836, 85337, 107014, 128867, 150921, 173149, 195551, 218072, 240693,
    263343, 285989, 308563, 331033, 353350, 375494, 397447, 419210, 440795, 462224, 483532, 504758,
  ],
  TERMS: ["小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
          "小暑", "大暑", "立秋", "处暑", "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至"],
  GAN: ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"],
  ZHI: ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"],
  ANIMAL: ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"],
  NM: ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"],
  ND1: ["初", "十", "廿", "卅"],
  ND2: ["日", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"],
  FESTIVAL: {
    "1-1": "春节", "1-15": "元宵", "2-2": "龙抬头", "5-5": "端午", "7-7": "七夕",
    "7-15": "中元", "8-15": "中秋", "9-9": "重阳", "12-8": "腊八", "12-23": "小年",
  },

  info(y) { return LUNAR.INFO[y - 1900]; },
  leapMonth(y) { return LUNAR.info(y) & 0xf; },              // 闰哪个月，0 = 不闰
  leapDays(y) { return LUNAR.leapMonth(y) ? ((LUNAR.info(y) & 0x10000) ? 30 : 29) : 0 },
  monthDays(y, m) { return (LUNAR.info(y) & (0x10000 >> m)) ? 30 : 29; },
  yearDays(y) {
    let sum = 348;                                            // 12 × 29
    for (let i = 0x8000; i > 0x8; i >>= 1) sum += (LUNAR.info(y) & i) ? 1 : 0;
    return sum + LUNAR.leapDays(y);
  },

  /* 公历 → 农历 */
  fromSolar(date) {
    const base = Date.UTC(1900, 0, 31);                       // 1900 正月初一
    const d = Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
    if (date.getFullYear() < 1900 || date.getFullYear() > 2100) return null;
    let offset = Math.floor((d - base) / 86400000);
    let year = 1900, temp = 0;
    for (; year < 2101 && offset > 0; year++) {
      temp = LUNAR.yearDays(year);
      offset -= temp;
    }
    if (offset < 0) { offset += temp; year--; }

    const leap = LUNAR.leapMonth(year);
    let isLeap = false, month = 1;
    for (; month < 13 && offset > 0; month++) {
      if (leap > 0 && month === leap + 1 && !isLeap) {
        month--; isLeap = true; temp = LUNAR.leapDays(year);
      } else {
        temp = LUNAR.monthDays(year, month);
      }
      if (isLeap && month === leap + 1) isLeap = false;
      offset -= temp;
    }
    if (offset === 0 && leap > 0 && month === leap + 1) {
      if (isLeap) isLeap = false; else { isLeap = true; month--; }
    }
    if (offset < 0) { offset += temp; month--; }
    return { year, month, day: offset + 1, isLeap };
  },

  monthName(m, isLeap) { return (isLeap ? "闰" : "") + LUNAR.NM[m - 1] + "月"; },
  dayName(d) {
    if (d === 10) return "初十";
    if (d === 20) return "二十";
    if (d === 30) return "三十";
    return LUNAR.ND1[Math.floor(d / 10)] + LUNAR.ND2[d % 10];
  },
  ganzhi(n) { return LUNAR.GAN[n % 10] + LUNAR.ZHI[n % 12]; },
  yearGanzhi(y) { return LUNAR.ganzhi(y - 1900 + 36); },
  animal(y) { return LUNAR.ANIMAL[(y - 4) % 12]; },

  /* 某年第 n 个节气所在的公历日（n: 0..23） */
  termDay(y, n) {
    const ms = 31556925974.7 * (y - 1900) + LUNAR.TERM_INFO[n] * 60000 + Date.UTC(1900, 0, 6, 2, 5);
    const d = new Date(ms);
    return d.getUTCDate();
  },
  termOf(date) {
    const y = date.getFullYear(), m = date.getMonth(), day = date.getDate();
    const a = LUNAR.termDay(y, m * 2), b = LUNAR.termDay(y, m * 2 + 1);
    if (day === a) return LUNAR.TERMS[m * 2];
    if (day === b) return LUNAR.TERMS[m * 2 + 1];
    return "";
  },
  /* 当前所处的节气（离今天最近的、已过的那个） */
  currentTerm(date) {
    let d = new Date(date);
    for (let i = 0; i < 20; i++) {
      const t = LUNAR.termOf(d);
      if (t) return { name: t, daysAgo: Math.round((date - d) / 86400000) };
      d.setDate(d.getDate() - 1);
    }
    return null;
  },

  festival(l) {
    if (!l || l.isLeap) return "";
    return LUNAR.FESTIVAL[`${l.month}-${l.day}`] || "";
  },

  /* 一行式描述，给日历面板与今日页用 */
  describe(date) {
    const l = LUNAR.fromSolar(date);
    if (!l) return "";
    const parts = [`农历${LUNAR.monthName(l.month, l.isLeap)}${LUNAR.dayName(l.day)}`];
    const f = LUNAR.festival(l);
    if (f) parts.push(f);
    const t = LUNAR.termOf(date);
    if (t) parts.push(t);
    return parts.join(" · ");
  },
  full(date) {
    const l = LUNAR.fromSolar(date);
    if (!l) return null;
    const cur = LUNAR.currentTerm(date);
    return {
      text: `${LUNAR.monthName(l.month, l.isLeap)}${LUNAR.dayName(l.day)}`,
      ganzhi: `${LUNAR.yearGanzhi(l.year)}${LUNAR.animal(l.year)}年`,
      festival: LUNAR.festival(l),
      term: LUNAR.termOf(date),
      currentTerm: cur ? cur.name : "",
      lunar: l,
    };
  },
};

if (typeof module !== "undefined") module.exports = LUNAR;
