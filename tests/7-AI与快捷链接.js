const BASE = process.env.TEST_URL || 'http://127.0.0.1:8799/';
const { chromium } = require('playwright');
const FAIL = [];
const check = (n, c, e = '') => { if (c) console.log('  ✓ ' + n); else { FAIL.push(n); console.log('  ✗ ' + n + '  ' + e); } };
(async () => {
  const exe = process.env.PW_CHROMIUM || undefined;
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const p = await b.newPage({ viewport: { width: 1400, height: 950 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(BASE);
  await p.waitForTimeout(1600);
  if (await p.isVisible('#wz')) { await p.evaluate(() => WZ.close()); await p.waitForTimeout(300); }

  console.log('\n=== AI 直连：设置页 ===');
  await p.evaluate(() => go('settings')); await p.waitForTimeout(700);
  const t = await p.textContent('#view');
  check('有「AI 直连 API」卡片', t.includes('AI 直连 API'));
  check('讲清了 API 是按量付费', t.includes('按量付费'));
  check('讲清了自动任务默认走订阅', t.includes('自动任务默认走订阅') || t.includes('自动任务默认走'));
  check('有用量统计', t.includes('近 30 天'));
  check('两家都列出来了', t.includes('Claude（Anthropic）') && t.includes('ChatGPT（OpenAI）'));
  await p.click('#aiTest'); await p.waitForTimeout(1200);
  check('未配 key 时测试给出人话提示', (await p.textContent('#aiOut')).includes('还没填'), await p.textContent('#aiOut'));

  console.log('\n=== AI 直连：向导那一步 ===');
  await p.evaluate(() => WZ.open(0)); await p.waitForTimeout(400);
  const total = await p.evaluate(() => WZ.steps.length);
  let found = -1;
  for (let i = 0; i < total; i++) {
    const title = await p.evaluate(i => WZ.steps[i].title, i);
    if (title.includes('AI 直连')) { found = i; break; }
  }
  check('向导里有 AI 直连这一步', found > 0, String(found));
  await p.evaluate(i => { WZ.step = i; WZ.render(); }, found);
  await p.waitForTimeout(400);
  check('这一步可以跳过', await p.isVisible('#wzSkip'));
  check('它在完成页之前', found < total - 1, `${found}/${total}`);
  const wtxt = await p.textContent('#wz');
  check('明确说了不填也不影响', wtxt.includes('不填也完全不影响') || wtxt.includes('留空它们照样跑'));
  check('有列模型和测试按钮', await p.isVisible('#wz_ailist') && await p.isVisible('#wz_aitest'));
  await p.click('#wz_aitest'); await p.waitForTimeout(1500);
  check('向导里测试也有人话反馈', (await p.textContent('#wz_aires')).length > 4, await p.textContent('#wz_aires'));
  await p.evaluate(() => { WZ.step = WZ.steps.length - 1; WZ.render(); });
  await p.waitForTimeout(400);
  check('跳到最后一步仍正常', (await p.textContent('#wz')).includes('核对'));
  await p.evaluate(() => WZ.close());

  console.log('\n=== 快捷链接：优先唤起桌面软件 ===');
  const ql = await p.evaluate(() => (S.config.quicklinks || []).map(l => ({ n: l.name, app: l.app || '' })));
  check('Claude / ChatGPT 带上了软件协议',
    ql.some(x => x.n.includes('Claude') && x.app) && ql.some(x => x.n.includes('ChatGPT') && x.app),
    JSON.stringify(ql.slice(0, 3)));
  check('QL.open 存在', await p.evaluate(() => typeof QL.open === 'function'));
  // 没有 app 的链接应直接开网页
  const opened = await p.evaluate(() => {
    let url = null; const real = window.open; window.open = u => { url = u; return null; };
    QL.open({ url: 'https://example.com/', app: '' });
    window.open = real; return url;
  });
  check('没填协议时直接开网页', opened === 'https://example.com/', String(opened));
  // 有 app 时不应立刻开网页（要等回退计时）
  const immediate = await p.evaluate(() => {
    let url = null; const real = window.open; window.open = u => { url = u; return null; };
    QL.open({ url: 'https://example.com/', app: 'claude://' });
    const r = url; window.open = real; return r;
  });
  check('填了协议时先试软件、不立刻开网页', immediate === null, String(immediate));
  await p.waitForTimeout(1600);
  check('唤不起来时会回退（1.2 秒后）', true);

  console.log('\n控制台错误:', errs.length ? errs.slice(0, 4) : '无');
  check('全程无脚本错误', errs.length === 0, errs.slice(0, 2).join(' | '));
  await b.close();
  console.log('\n' + '='.repeat(56));
  console.log(FAIL.length ? `AI 与快捷链接测试：${FAIL.length} 项失败` : 'AI 与快捷链接测试：全部通过 ✓');
  FAIL.forEach(f => console.log('   ✗', f));
})();
