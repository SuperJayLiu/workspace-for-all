/* 极端测试 12 · 跨库关联的界面部分（想法 ↔ 稿件 ↔ 文献 ↔ 会议）
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
  await p.evaluate(async () => { await saveConfig({ hide_samples: false }); render(); });
  await p.waitForTimeout(400);

  // 造两条自己的记录，跑完删掉，绝不动用户的数据
  const made = await p.evaluate(async () => {
    const a = await API.save('ideas', { title: 'ZZ关联测试·想法', kind: 'idea' });
    const c = await API.save('manuscripts', { title: 'ZZ关联测试·稿件', stage: 'drafting' });
    await reload(); render(); renderNav();
    return { idea: a.id, ms: c.id };
  });

  try {
    console.log('\n=== 1. 新建时不给关联，但要说清楚为什么 ===');
    await p.evaluate(() => UI.editRecord('ideas', null, schema_ideas()));
    await p.waitForTimeout(300);
    const newTxt = await p.textContent('#modal');
    ck('新建里出现「先保存」的提示', /先保存/.test(newTxt), newTxt.slice(-90));
    ck('新建里没有关联按钮', await p.evaluate(() => !document.querySelector('#linkAdd')));
    await p.evaluate(() => UI.closeModal());

    console.log('\n=== 2. 编辑里能关联，选择器搜得到 ===');
    await p.evaluate(id => UI.openRecord('ideas', id), made.idea);
    await p.waitForTimeout(350);
    ck('编辑里有关联区', await p.evaluate(() => !!document.querySelector('#linkAdd')));
    ck('一开始是空的', /还没有关联/.test(await p.textContent('#linkList')));
    await p.click('#linkAdd');
    await p.waitForTimeout(300);
    ck('选择器打开了', await p.evaluate(() => !!document.querySelector('#lkq')));
    const selfInList = await p.evaluate(id =>
      !!document.querySelector(`#lkList [data-ref="ideas:${id}"]`), made.idea);
    ck('自己不在候选里', !selfInList);
    await p.fill('#lkq', 'ZZ关联测试·稿件');
    await p.waitForTimeout(250);
    const n = await p.evaluate(() => document.querySelectorAll('#lkList .pickrow').length);
    ck('搜得到那条稿件', n >= 1, String(n));
    await p.click('#lkList .pickrow');
    await p.waitForTimeout(900);

    console.log('\n=== 3. 关联是双向的，两头都看得见 ===');
    ck('回到了原来那条的编辑器', await p.evaluate(() => !!document.querySelector('#linkAdd')));
    ck('想法这头出现了 chip', await p.evaluate(() =>
      document.querySelectorAll('#linkList .chip.link').length === 1));
    ck('chip 上标了对面是哪个库', /稿件/.test(await p.textContent('#linkList')));
    const both = await p.evaluate(m => {
      const ms = (S.data.manuscripts || []).find(x => x.id === m.ms);
      const id = (S.data.ideas || []).find(x => x.id === m.idea);
      return { ms: (ms.links || []), idea: (id.links || []) };
    }, made);
    ck('稿件那头也记下了', both.ms.includes('ideas:' + made.idea), JSON.stringify(both));
    ck('想法这头记的是稿件', both.idea.includes('manuscripts:' + made.ms), JSON.stringify(both));
    await p.evaluate(() => UI.closeModal());

    console.log('\n=== 4. 列表里能一眼看出这条连着别的 ===');
    const badge = await p.evaluate(m => {
      const ms = (S.data.manuscripts || []).find(x => x.id === m.ms);
      return UI.linkBadge(ms);
    }, made);
    ck('稿件上有 🔗 1 的小标', /🔗 1/.test(badge), badge);
    ck('小标的 tooltip 写了对面的标题', /ZZ关联测试·想法/.test(badge), badge);
    ck('没关联的记录不显示小标',
      await p.evaluate(() => UI.linkBadge({ title: 'x' })) === '');

    console.log('\n=== 5. 点 chip 能跳到对面那条 ===');
    await p.evaluate(id => UI.openRecord('ideas', id), made.idea);
    await p.waitForTimeout(300);
    await p.click('#linkList .chip-go');
    await p.waitForTimeout(700);
    const jumped = await p.evaluate(() => {
      const v = document.querySelector('#modal .modal-body input#f_title');
      return v ? v.value : (document.querySelector('#modal') || {}).textContent || '';
    });
    ck('跳到了那条稿件的编辑器', /ZZ关联测试·稿件/.test(jumped), String(jumped).slice(0, 80));

    console.log('\n=== 6. 解除也是双向的 ===');
    await p.click('#linkList .chip-x');
    await p.waitForTimeout(900);
    const after = await p.evaluate(m => {
      const ms = (S.data.manuscripts || []).find(x => x.id === m.ms);
      const id = (S.data.ideas || []).find(x => x.id === m.idea);
      return { ms: (ms.links || []), idea: (id.links || []) };
    }, made);
    ck('两头的关联都没了', !after.ms.length && !after.idea.length, JSON.stringify(after));
    ck('界面上也变回「还没有关联」', /还没有关联/.test(await p.textContent('#linkList')));
    await p.evaluate(() => UI.closeModal());

    console.log('\n=== 7. 指向已删记录的关联不能让页面崩 ===');
    const dead = await p.evaluate(async m => {
      await API.save('ideas', { id: m.idea, title: 'ZZ关联测试·想法', kind: 'idea',
                                links: ['manuscripts:根本没有这条'] });
      await reload(); render(); renderNav();
      const r = (S.data.ideas || []).find(x => x.id === m.idea);
      return UI.linkBadge(r);
    }, made);
    ck('小标还是画得出来', /🔗 1/.test(dead), dead);
    await p.evaluate(id => UI.openRecord('ideas', id), made.idea);
    await p.waitForTimeout(350);
    ck('chip 标成「已删除」', /已删除/.test(await p.textContent('#linkList')));
    ck('并且画了删除线', await p.evaluate(() => !!document.querySelector('#linkList .chip.dead')));
    await p.evaluate(() => UI.closeModal());
    await p.waitForTimeout(200);
  } finally {
    await p.evaluate(async m => {
      await API.del('records/ideas/' + encodeURIComponent(m.idea));
      await API.del('records/manuscripts/' + encodeURIComponent(m.ms));
    }, made);
  }

  ck('全程没有 JS 报错', errs.length === 0, errs.join(' | '));
  await b.close();
  console.log('\n' + '='.repeat(56));
  console.log('关联测试：' + (FAIL.length ? FAIL.length + ' 项失败' : '全部通过 ✓'));
  FAIL.forEach(f => console.log('   ✗', f));
  process.exit(FAIL.length ? 1 : 0);
})();
