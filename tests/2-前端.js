const BASE = process.env.TEST_URL || 'http://127.0.0.1:8799/';
const { chromium } = require('playwright');

const FAIL = [];
const check = (name, cond, extra = '') => {
  if (cond) console.log('  ✓ ' + name);
  else { FAIL.push(name); console.log('  ✗ ' + name + '  ' + extra); }
};

(async () => {
  // 有 PW_CHROMIUM 就用它，否则用 Playwright 自己下载的浏览器
  const exe = process.env.PW_CHROMIUM || undefined;
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const p = await b.newPage({ viewport: { width: 1480, height: 1000 } });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  let alerted = false;
  p.on('dialog', async d => { alerted = true; await d.dismiss(); });

  await p.goto(BASE); await p.waitForTimeout(1700);
  if (await p.isVisible('#wz')) { await p.evaluate(() => WZ.close()); await p.waitForTimeout(300); }

  console.log('\n=== 1. XSS 注入（记录内容渲染到 HTML） ===');
  const XSS = [
    `<img src=x onerror="window.__pwned=1">`,
    `<script>window.__pwned2=1<\/script>`,
    `"><svg onload="window.__pwned3=1">`,
    `javascript:alert(1)`,
    `<iframe src="javascript:window.__pwned4=1">`,
    `</textarea><img src=x onerror=window.__pwned5=1>`,
  ];
  const madeIds = await p.evaluate(async (payloads) => {
    const ids = [];
    for (const x of payloads) {
      const r = await saveRec('manuscripts', {
        title: x, stage: 'writing', next_action: x, body: x,
        current_journal: x, coauthors: [x],
        timeline: [{ date: '2026-01-01', event: 'note', journal: x, note: x }],
      });
      ids.push(r.id);
      await saveRec('reading', { title: x, status: 'to-read', link: x, question: x });
      await saveRec('ideas', { title: x, kind: 'idea' });
      await saveRec('conferences', { title: x, deadline: '2026-08-15', status: 'watching' });
    }
    return ids;
  }, XSS);
  const pages = ['today', 'hub', 'manuscripts', 'papers', 'conferences', 'reading', 'ideas', 'schedule', 'life', 'ai', 'settings'];
  for (const pg of pages) { await p.evaluate(id => go(id), pg); await p.waitForTimeout(220); }
  await p.evaluate(id => { S.projectId = id; go('project'); }, madeIds[0]);
  await p.waitForTimeout(500);
  const pwned = await p.evaluate(() => Object.keys(window).filter(k => k.startsWith('__pwned')));
  check('11 页 + 子页渲染恶意内容后无脚本执行', pwned.length === 0, JSON.stringify(pwned));
  check('未弹出 alert', !alerted);
  const injected = await p.evaluate(() => document.querySelectorAll('#view img[src="x"], #view iframe, #view svg[onload]').length);
  check('未注入活动元素', injected === 0, String(injected));
  // 搜索与速记里也过一遍
  await p.fill('#globalSearch', '<img src=x onerror=window.__pwned9=1>');
  await p.waitForTimeout(500);
  await p.evaluate(() => DOCK.renderBox());
  await p.waitForTimeout(300);
  const pwned2 = await p.evaluate(() => Object.keys(window).filter(k => k.startsWith('__pwned')));
  check('搜索框与速记同样安全', pwned2.length === 0, JSON.stringify(pwned2));
  await p.fill('#globalSearch', ''); await p.keyboard.press('Escape');

  console.log('\n=== 2. 极端长度与畸形值不破坏布局 ===');
  await p.evaluate(async () => {
    await saveRec('manuscripts', {
      title: '超长'.repeat(400), stage: 'submitted', progress: 999,
      next_action: 'x'.repeat(2000), next_action_due: '不是日期',
      current_journal: 'J'.repeat(300),
      timeline: [{ date: '9999-99-99', event: 'submitted', journal: 'x' }],
    });
    await saveRec('manuscripts', { title: 'NaN 进度', progress: NaN, stage: 'writing' });
    await saveRec('manuscripts', { title: '负进度', progress: -50, stage: 'writing' });
    await saveRec('reading', { title: '无字段' });
    await saveRec('exercise', { date: '2026-07-29', title: '负时长', minutes: -30 });
    await saveRec('finance', { date: '2026-07-29', title: '天文数字', amount: 1e20 });
  });
  for (const pg of pages) { await p.evaluate(id => go(id), pg); await p.waitForTimeout(200); }
  const overflow = await p.evaluate(() => {
    const de = document.documentElement;
    return { hScroll: de.scrollWidth - de.clientWidth, bodyW: de.scrollWidth };
  });
  check('无横向溢出', overflow.hScroll <= 2, JSON.stringify(overflow));
  const progOK = await p.evaluate(() => {
    go('hub');
    return [...document.querySelectorAll('.prog .fill')].every(el => {
      const w = parseFloat(el.style.width);
      return !isNaN(w) && w >= 0 && w <= 100;
    });
  });
  await p.waitForTimeout(300);
  check('进度条被夹在 0–100', progOK);

  console.log('\n=== 3. 大数据量渲染性能 ===');
  await p.evaluate(async () => {
    for (let i = 0; i < 300; i++) {
      S.data.reading.push({ id: 'perf' + i, title: '性能文献 ' + i, status: i % 3 ? 'to-read' : 'done',
        level: 'deep', read_date: '2026-07-2' + (i % 9), topic: '主题' + (i % 12), authors: ['A', 'B'] });
      S.data.manuscripts.push({ id: 'pm' + i, title: '性能稿件 ' + i, stage: 'writing', progress: i % 100,
        timeline: [{ date: '2026-05-01', event: 'started' }] });
    }
  });
  for (const pg of ['today', 'hub', 'reading', 'manuscripts']) {
    const t0 = Date.now();
    await p.evaluate(id => go(id), pg);
    await p.waitForTimeout(60);
    const dt = Date.now() - t0;
    check(`${pg} 在 600+ 条下渲染 ${dt}ms`, dt < 4000, String(dt));
  }
  const t0 = Date.now();
  await p.fill('#globalSearch', '性能'); await p.waitForTimeout(500);
  check(`搜索 600+ 条耗时 ${Date.now() - t0}ms`, Date.now() - t0 < 3000);
  await p.fill('#globalSearch', ''); await p.keyboard.press('Escape');

  console.log('\n=== 4. 快速连点 / 竞态 ===');
  await p.evaluate(() => { for (let i = 0; i < 40; i++) go(['today','hub','reading','ai','life'][i % 5]); });
  await p.waitForTimeout(800);
  check('40 次极速切页后仍可用', await p.isVisible('#view'), '');
  await p.evaluate(() => { RAIL.render(); RAIL.render(); RAIL.render(); DOCK.relocate(); DOCK.relocate(); });
  await p.waitForTimeout(400);
  check('右栏重复重绘后速记仍在', await p.evaluate(() => !!document.querySelector('#dockInput')));
  // 布局编辑开关快速切换
  await p.evaluate(() => { EDIT.toggle(true); EDIT.toggle(false); EDIT.toggle(true); EDIT.toggle(false); });
  await p.waitForTimeout(400);
  check('布局编辑快速开关无残留', await p.evaluate(() => !document.body.classList.contains('editing') && document.querySelectorAll('.drag').length === 0));

  console.log('\n=== 5. 服务器不可用时的表现 ===');
  await p.route('**/api/**', route => route.abort());
  const saveErr = await p.evaluate(async () => {
    try { await saveRec('ideas', { title: '断网测试' }); return 'no-throw'; }
    catch (e) { return 'threw:' + (e.message || '').slice(0, 30); }
  });
  check('断网时保存抛出可捕获的错误（不静默丢数据）', saveErr.startsWith('threw'), saveErr);
  await p.evaluate(() => go('today')); await p.waitForTimeout(400);
  check('断网后页面未白屏', (await p.textContent('#view')).length > 50);
  await p.unroute('**/api/**');

  console.log('\n=== 6. 智能捕捉解析器：模糊输入 ===');
  const capCases = await p.evaluate(() => {
    const inputs = ['', '   ', '。。。', '2月30日开会', '13月45日', '25:99 开会',
      '一二三四五六七八九十天后', '花了 999999999999 元', '跑步 -30 分钟',
      '🎉🎊', 'a'.repeat(5000), '明天明天明天', 'DOI 10.1093/rfs/hhad012 和 arxiv:2401.01234'];
    return inputs.map(t => {
      try { const r = CAP.toRecord(t, 'auto', new Date()); return { t: t.slice(0, 18), ok: true, c: r.collection }; }
      catch (e) { return { t: t.slice(0, 18), ok: false, e: e.message.slice(0, 40) }; }
    });
  });
  const capBad = capCases.filter(c => !c.ok);
  check(`13 种模糊输入全部不崩溃`, capBad.length === 0, JSON.stringify(capBad));
  const dateSanity = await p.evaluate(() => ({
    feb30: CAP.parseDate('2月30日', new Date(2026, 6, 29)),
    m13: CAP.parseDate('13月45日', new Date(2026, 6, 29)),
    t2599: CAP.parseTime('25:99 开会'),
  }));
  check('非法日期不产生垃圾值', (() => {
    const ok = v => v === null || /^\d{4}-\d{2}-\d{2}$/.test(v);
    return ok(dateSanity.feb30) && ok(dateSanity.m13);
  })(), JSON.stringify(dateSanity));

  console.log('\n=== 7. 农历边界 ===');
  const lunar = await p.evaluate(() => {
    const out = {};
    out.y1900 = LUNAR.fromSolar(new Date(1900, 0, 31));
    out.y2100 = LUNAR.fromSolar(new Date(2100, 11, 31));
    out.tooEarly = LUNAR.fromSolar(new Date(1899, 5, 1));
    out.tooLate = LUNAR.fromSolar(new Date(2101, 0, 1));
    out.leapDay = LUNAR.describe(new Date(2024, 1, 29));
    let crash = null;
    try { for (let y = 1900; y <= 2100; y += 7) for (let mo = 0; mo < 12; mo += 5) LUNAR.describe(new Date(y, mo, 15)); }
    catch (e) { crash = e.message; }
    out.sweepCrash = crash;
    return out;
  });
  check('1900/2100 边界可解析', !!lunar.y1900 && !!lunar.y2100);
  check('范围外返回 null 而非乱码', lunar.tooEarly === null && lunar.tooLate === null, JSON.stringify([lunar.tooEarly, lunar.tooLate]));
  check('闰日可解析', !!lunar.leapDay, lunar.leapDay);
  check('200 年扫描无异常', lunar.sweepCrash === null, String(lunar.sweepCrash));

  console.log('\n=== 8. 清理与最终状态 ===');
  await p.evaluate(async () => {
    S.data.reading = S.data.reading.filter(r => !String(r.id).startsWith('perf'));
    S.data.manuscripts = S.data.manuscripts.filter(r => !String(r.id).startsWith('pm'));
    const junk = r => /超长|NaN 进度|负进度|无字段|负时长|天文数字|pwned|javascript:|<|>/i.test(r.title || '');
    for (const coll of ['manuscripts', 'reading', 'ideas', 'conferences', 'exercise', 'finance']) {
      for (const r of (S.data[coll] || []).slice()) if (junk(r)) { try { await deleteRec(coll, r.id); } catch (e) { } }
    }
  });
  await p.waitForTimeout(1200);
  await p.evaluate(() => go('today')); await p.waitForTimeout(500);
  check('清理后今日页正常', (await p.textContent('#view')).includes('今日'));

  console.log('\n控制台错误:', errs.length ? errs.slice(0, 6) : '无');
  console.log('\n' + '='.repeat(56));
  console.log(FAIL.length ? `前端极端测试：${FAIL.length} 项失败` : '前端极端测试：全部通过 ✓');
  FAIL.forEach(f => console.log('   ✗', f));
  await b.close();
})();
