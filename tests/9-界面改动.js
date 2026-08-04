/* 极端测试 9 · 这一轮的界面改动
   跑之前：python3 server.py --port 8799 --no-open &                        */
const BASE = process.env.TEST_URL || 'http://127.0.0.1:8799/';
const { chromium } = require('playwright');
const FAIL = [];
const ck = (n, c, e = '') => { if (c) console.log('  ✓ ' + n); else { FAIL.push(n); console.log('  ✗ ' + n + '  ' + e); } };

(async () => {
  const b = await chromium.launch({ executablePath: process.env.PW_CHROMIUM || undefined });
  const p = await b.newPage({ viewport: { width: 1500, height: 1000 } });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(BASE);
  await p.waitForTimeout(1800);
  if (await p.isVisible('#wz')) { await p.evaluate(() => WZ.close()); await p.waitForTimeout(300); }
  await p.evaluate(async () => { await saveConfig({ hide_samples: false, card_opts: {} }); render(); });
  await p.waitForTimeout(400);

  console.log('\n=== 1. 每张卡上的「隐藏示例」按钮 ===');
  await p.evaluate(() => go('today'));
  await p.waitForTimeout(500);
  const btns = await p.evaluate(() => document.querySelectorAll('[data-hidesample]').length);
  ck('今日页多张卡上都有这个按钮', btns >= 3, String(btns));
  const before = await p.evaluate(() => rowsAll('manuscripts').length);
  await p.evaluate(() => document.querySelector('[data-hidesample]').click());
  await p.waitForTimeout(800);
  const hid = await p.evaluate(() => ({
    cfg: S.config.hide_samples, shown: rows('manuscripts').length, all: rowsAll('manuscripts').length,
  }));
  ck('点一下全站生效', hid.cfg === true && hid.shown < hid.all, JSON.stringify(hid));
  ck('只是藏起来，没有删数据', hid.all === before, `${before} → ${hid.all}`);
  ck('藏好之后按钮自己消失', await p.evaluate(() => document.querySelectorAll('[data-hidesample]').length) === 0);
  await p.evaluate(async () => { await saveConfig({ hide_samples: false }); render(); });
  await p.waitForTimeout(400);
  ck('可以再显示回来', await p.evaluate(() => document.querySelectorAll('[data-hidesample]').length) > 0);

  console.log('\n=== 2. 四个统计卡都能点开明细 ===');
  for (const k of ['overdue', 'today', 'stale', 'reading']) {
    await p.click(`[data-stat="${k}"]`);
    await p.waitForTimeout(400);
    const t = await p.textContent('#modal');
    ck(`点「${k}」弹出明细`, t.length > 20, t.slice(0, 30));
    await p.evaluate(() => UI.closeModal());
    await p.waitForTimeout(200);
  }

  console.log('\n=== 3. 整行可点，不用瞄那个小按钮 ===');
  const rowOK = await p.evaluate(() => {
    const r = document.querySelector('#view .row-line[data-rowgo]');
    if (!r) return 'no-row';
    const want = r.dataset.rowgo;
    r.click();
    return { ok: S.route === want, to: S.route, want };
  });
  ck('点整行会跳转', rowOK !== 'no-row' && rowOK.ok, JSON.stringify(rowOK));

  console.log('\n=== 4. 卡片自定义：改标题、限条数、加备注 ===');
  await p.evaluate(() => go('today'));
  await p.waitForTimeout(400);
  await p.evaluate(() => EDIT.toggle(true));
  await p.waitForTimeout(600);
  const gears = await p.evaluate(() => document.querySelectorAll('.gearb').length);
  ck('编辑模式下每张卡都有 ⚙', gears >= 4, String(gears));
  // 挑一张确实有好几行的卡（近期截止），否则「限制条数」无从验证
  const target = await p.evaluate(() => {
    const cards = [...document.querySelectorAll('#view .card')];
    const c = cards.find(x => x.querySelectorAll('.card-body > .row-line').length >= 3) || cards[0];
    c.querySelector('.gearb').click();
    return c.dataset.cardkey;
  });
  await p.waitForTimeout(400);
  ck(`⚙ 打开卡片设置（${target}）`, (await p.textContent('#modal')).includes('这张卡的设置'));
  await p.fill('#co_title', '我自己改的标题');
  await p.fill('#co_limit', '2');
  await p.fill('#co_note', '这周先别管这里');
  await p.click('#coSave');
  await p.waitForTimeout(800);
  const applied = await p.evaluate(() => ({
    titles: [...document.querySelectorAll('#view .card-head h2')].filter(x => x.textContent.includes('我自己改的标题')).length,
    extra: document.querySelectorAll('.row-extra').length,
    more: document.querySelectorAll('[data-showextra]').length,
    note: document.querySelectorAll('.card-note').length,
  }));
  ck('标题改成了自定义的', applied.titles === 1, JSON.stringify(applied));
  ck('条数限制生效', applied.extra > 0 && applied.more > 0, JSON.stringify(applied));
  ck('备注显示出来了', applied.note === 1, JSON.stringify(applied));
  await p.evaluate(() => document.querySelector('[data-showextra]').click());
  await p.waitForTimeout(300);
  ck('点「还有 N 条」能展开', await p.evaluate(() => document.querySelectorAll('.row-extra').length) === 0);
  await p.evaluate(k => {
    document.querySelector(`[data-cardkey="${k}"] .gearb`).click();
  }, target);
  await p.waitForTimeout(400);
  await p.click('#coReset');
  await p.waitForTimeout(700);
  ck('恢复默认能清干净', await p.evaluate(() => Object.keys(S.config.card_opts || {}).length) === 0);
  await p.evaluate(() => EDIT.toggle(false));
  await p.waitForTimeout(400);

  console.log('\n=== 5. 顶栏文字与左下角文案 ===');
  ck('布局按钮有文字', (await p.textContent('#editBtn')).includes('布局'));
  ck('主题按钮有文字', (await p.textContent('#themeBtn')).includes('主题'));
  const meta = await p.textContent('#deviceMeta');
  ck('左下角写的是「开始做伟大的事吧！」', meta.includes('伟大的事'), meta.slice(0, 40));

  console.log('\n=== 6. 完成记录进了今日页 ===');
  ck('今日页有「今天完成了什么」', (await p.textContent('#view')).includes('今天完成了什么'));

  console.log('\n=== 7. 日历更紧凑、滚动只在日程区 ===');
  const cal = await p.evaluate(() => {
    const top = document.querySelector('.cal-top');
    const list = document.querySelector('.cal-list');
    const grid = document.querySelector('.cg');
    return {
      topH: top ? Math.round(top.getBoundingClientRect().height) : 0,
      listScroll: list ? getComputedStyle(list).overflowY : '',
      gridScroll: grid ? getComputedStyle(grid).overflowY : '',
    };
  });
  ck('顶部信息块压到 130px 以内', cal.topH > 0 && cal.topH < 130, JSON.stringify(cal));
  ck('日程列表才是滚动的那一块', cal.listScroll === 'auto', JSON.stringify(cal));
  ck('日历格子本身不滚', cal.gridScroll !== 'auto' && cal.gridScroll !== 'scroll', JSON.stringify(cal));


  console.log('\n=== 8. 本周一览（含 Outlook） ===');
  await p.evaluate(() => go('today'));
  await p.waitForTimeout(600);
  const wk = await p.evaluate(() => {
    const days = [...document.querySelectorAll('.weekgrid .wkday')];
    return {
      n: days.length,
      today: days.filter(d => d.classList.contains('on')).length,
      past: days.filter(d => d.classList.contains('past')).length,
      heads: days.map(d => (d.querySelector('.wkh') || {}).textContent || ''),
    };
  });
  ck('铺开正好 7 天', wk.n === 7, JSON.stringify(wk.n));
  ck('今天那一格高亮', wk.today === 1, String(wk.today));
  ck('星期标在每一格上', wk.heads.every(h => /[一二三四五六日]/.test(h)), JSON.stringify(wk.heads.slice(0, 3)));
  const wkPlan = await p.evaluate(() => {
    const plan = weekPlan();
    return {
      days: plan.length,
      srcs: [...new Set(plan.flatMap(d => d.items.map(i => i.src)))],
      sorted: plan.every(d => {
        const ts = d.items.map(i => i.t || 'zz');
        return ts.every((v, i) => i === 0 || ts[i - 1] <= v);
      }),
    };
  });
  ck('weekPlan 返回 7 天', wkPlan.days === 7, JSON.stringify(wkPlan));
  ck('每天内部按时间排好序', wkPlan.sorted, JSON.stringify(wkPlan));
  ck('会把多个来源合并进来', wkPlan.srcs.length >= 1, JSON.stringify(wkPlan.srcs));

  console.log('\n=== 9. 多选批量操作 ===');
  await p.evaluate(() => go('conferences'));
  await p.waitForTimeout(600);
  const boxes = await p.evaluate(() => document.querySelectorAll('.pickbox').length);
  ck('会议列表每行都有勾选框', boxes > 0, String(boxes));
  await p.evaluate(() => { document.querySelector('.pickbox').click(); });
  await p.waitForTimeout(300);
  ck('选中后底部弹出操作条', await p.isVisible('#pickbar'));
  ck('操作条上写了已选几条', (await p.textContent('#pickbar')).includes('已选'));
  await p.click('#pkNone');
  await p.waitForTimeout(400);
  ck('取消选择后操作条消失', !(await p.isVisible('#pickbar').catch(() => false)));
  ck('选中集合被清空', await p.evaluate(() => PICK.size) === 0);

  console.log('\n=== 10. 工作台名称可自定义、角标固定 ===');
  await p.evaluate(async () => { await saveConfig({ brand: { title: '老王的工作台', sub: 'Lab Bench' } }); applyBrand(); });
  await p.waitForTimeout(300);
  ck('侧边栏标题跟着改', (await p.textContent('#brandTitle')) === '老王的工作台');
  ck('副标题跟着改', (await p.textContent('#brandSub')) === 'Lab Bench');
  ck('网页标题也跟着改', (await p.title()).includes('老王的工作台'));
  const mark = await p.evaluate(() => {
    const el = document.querySelector('.brand-mark');
    return { svg: !!el.querySelector('svg'), editable: el.hasAttribute('contenteditable'), text: el.textContent.trim() };
  });
  ck('角标是固定的 SVG，不是可改的文字', mark.svg && !mark.editable && !mark.text, JSON.stringify(mark));
  await p.evaluate(async () => { await saveConfig({ brand: { title: '学术工作台', sub: 'Scholar Workspace' } }); applyBrand(); });

  console.log('\n=== 11. 记完一条会给回应和「问 AI」 ===');
  const tpl = await p.evaluate(() => ({
    diet: CAP.aiPrompt('diet', { title: '牛肉面', kcal: 600 }),
    idea: CAP.aiPrompt('ideas', { title: '某个想法', kind: 'idea' }),
    reading: CAP.aiPrompt('reading', { title: 'Some Paper', journal: 'JF' }),
    none: CAP.aiPrompt('unknown-coll', {}),
  }));
  ck('饮食有模板且带上了内容', tpl.diet.includes('牛肉面') && tpl.diet.length > 40);
  ck('想法有模板', tpl.idea.includes('某个想法'));
  ck('文献有模板', tpl.reading.includes('Some Paper'));
  ck('不认识的类型不硬凑', tpl.none === '');
  const replies = await p.evaluate(() => ({
    idea: CAP_REPLY.ideas({ kind: 'idea' }),
    q: CAP_REPLY.ideas({ kind: 'question' }),
    ex: CAP_REPLY.exercise({}),
  }));
  ck('灵感和疑问给的是不同回应', replies.idea !== replies.q, JSON.stringify(replies));
  ck('回应里有具体的话', replies.idea.length > 6 && replies.ex.length > 4, JSON.stringify(replies));

  console.log('\n控制台错误:', errs.length ? errs.slice(0, 4) : '无');
  ck('全程无脚本错误', errs.length === 0, errs.slice(0, 2).join(' | '));
  await b.close();
  console.log('\n' + '='.repeat(56));
  console.log(FAIL.length ? `界面改动检查：${FAIL.length} 项失败` : '界面改动检查：全部通过 ✓');
  FAIL.forEach(f => console.log('   ✗', f));
})();
