/* 极端测试 6 · 手机布局 + 远程只读界面
   跑之前先起一个测试用的服务：python3 server.py --port 8799 --no-open &     */
const BASE = process.env.TEST_URL || 'http://127.0.0.1:8799/';
const { chromium } = require('playwright');

const FAIL = [];
const check = (name, cond, extra = '') => {
  if (cond) console.log('  ✓ ' + name);
  else { FAIL.push(name); console.log('  ✗ ' + name + '  ' + extra); }
};
const PHONES = [
  { name: 'iPhone SE', width: 375, height: 667 },
  { name: 'iPhone 15 Pro', width: 393, height: 852 },
  { name: '小屏安卓', width: 360, height: 740 },
  { name: 'iPad 竖屏', width: 768, height: 1024 },
];
const PAGES = ['today', 'hub', 'manuscripts', 'papers', 'conferences',
  'reading', 'ideas', 'schedule', 'life', 'ai', 'settings'];

(async () => {
  const exe = process.env.PW_CHROMIUM || undefined;
  const b = await chromium.launch(exe ? { executablePath: exe } : {});

  console.log('\n=== 1. 各种手机尺寸下不横向滚、不遮挡 ===');
  for (const ph of PHONES) {
    const p = await b.newPage({
      viewport: { width: ph.width, height: ph.height },
      isMobile: true, hasTouch: true, deviceScaleFactor: 2,
    });
    const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    await p.goto(BASE);
    await p.waitForTimeout(1500);
    if (await p.isVisible('#wz')) { await p.evaluate(() => WZ.close()); await p.waitForTimeout(250); }
    let worst = 0, worstPage = '';
    for (const pg of PAGES) {
      await p.evaluate(id => go(id), pg);
      await p.waitForTimeout(160);
      const over = await p.evaluate(() =>
        document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (over > worst) { worst = over; worstPage = pg; }
    }
    check(`${ph.name} (${ph.width}px) 11 页都不横向滚`, worst <= 2, `最宽溢出 ${worst}px @ ${worstPage}`);
    // 顶栏按钮不能重叠、不能被挤出屏幕
    const btns = await p.evaluate(() => [...document.querySelectorAll('.topbar-actions .btn')]
      .filter(e => !e.hidden).map(e => { const r = e.getBoundingClientRect();
        return { x: r.x, w: r.width, h: r.height, right: r.right }; }));
    check(`${ph.name} 顶栏按钮都在屏幕内且够大`,
      btns.every(x => x.right <= ph.width + 1 && x.h >= 28), JSON.stringify(btns.slice(0, 3)));
    check(`${ph.name} 无脚本错误`, errs.length === 0, errs.slice(0, 2).join(' | '));
    await p.close();
  }

  console.log('\n=== 2. 侧边栏抽屉在手机上能开能关 ===');
  const p = await b.newPage({ viewport: { width: 375, height: 667 }, isMobile: true, hasTouch: true });
  await p.goto(BASE);
  await p.waitForTimeout(1400);
  if (await p.isVisible('#wz')) { await p.evaluate(() => WZ.close()); await p.waitForTimeout(250); }
  const hiddenAtFirst = await p.evaluate(() =>
    document.querySelector('#sidebar').getBoundingClientRect().right <= 1);
  check('默认收起，不挡内容', hiddenAtFirst);
  await p.click('#menuBtn'); await p.waitForTimeout(320);
  check('点菜单键能拉出来', await p.evaluate(() =>
    document.querySelector('#sidebar').getBoundingClientRect().right > 100));
  await p.evaluate(() => go('reading')); await p.waitForTimeout(320);
  check('选完一项自动收回去', await p.evaluate(() =>
    !document.querySelector('#sidebar').classList.contains('open')));

  console.log('\n=== 3. 设置页的远程与设备两张卡 ===');
  await p.evaluate(() => go('settings')); await p.waitForTimeout(400);
  const txt = await p.textContent('#view');
  check('有「远程访问与手机」卡', txt.includes('远程访问与手机'));
  check('有「我的设备」卡', txt.includes('我的设备'));
  check('说明里写清了默认只读', txt.includes('默认只读') || txt.includes('默认是只读'));
  check('设备卡列出了本机', txt.includes('本机'));
  // 没填访问码就想开远程 → 必须被拦下
  await p.evaluate(() => {
    document.querySelector('[data-pill="secOn"] [data-v="1"]').click();
  });
  await p.waitForTimeout(120);
  const before = await p.evaluate(() => JSON.stringify(S.config.security || {}));
  await p.click('#secSave'); await p.waitForTimeout(500);
  const msg = await p.textContent('#remoteOut');
  const after = await p.evaluate(() => JSON.stringify(S.config.security || {}));
  const hadCode = await p.evaluate(() => !!(S.secretsStatus || {}).remote_code);
  check('没设访问码就开远程会被拦住', hadCode || (msg.includes('访问码') && before === after),
    `msg=${msg.slice(0, 40)}`);
  // 太短的访问码也要拦
  await p.fill('#sec_code', '123');
  await p.click('#secSave'); await p.waitForTimeout(400);
  check('访问码太短会被拦住', (await p.textContent('#remoteOut')).includes('太短'));
  await p.fill('#sec_code', '');

  console.log('\n=== 4. 入口页与简报能生成 ===');
  await p.click('#portalBuild'); await p.waitForTimeout(900);
  check('生成手机入口页有结果反馈', /portal\.html|入口页|失败|地址记录/.test(await p.textContent('#remoteOut')),
    (await p.textContent('#remoteOut')).slice(0, 60));
  await p.click('#digestBuild'); await p.waitForTimeout(900);
  check('生成只读简报有结果反馈', /digest|简报/.test(await p.textContent('#remoteOut')),
    (await p.textContent('#remoteOut')).slice(0, 60));

  console.log('\n=== 5. 只读模式下界面确实变样 ===');
  await p.evaluate(() => { S.auth = { local: false, can_write: false }; updateLockChip(); });
  await p.waitForTimeout(200);
  check('顶栏出现锁标记', await p.isVisible('#unlockBtn'));
  check('锁显示"只读"', (await p.textContent('#unlockBtn')).includes('只读'));
  check('body 带上 readonly 标记', await p.evaluate(() => document.body.classList.contains('readonly')));
  await p.click('#unlockBtn'); await p.waitForTimeout(350);
  check('点锁弹出解锁框', (await p.textContent('#modal')).includes('解锁写入'));
  await p.evaluate(() => UI.closeModal());
  await p.evaluate(() => { S.auth = { local: false, can_write: true }; updateLockChip(); });
  await p.waitForTimeout(200);
  check('解锁后锁变成可编辑', (await p.textContent('#unlockBtn')).includes('可编辑'));
  await p.evaluate(() => { S.auth = { local: true, can_write: true }; updateLockChip(); });
  await p.waitForTimeout(150);
  check('本机模式下锁自动隐藏', !(await p.isVisible('#unlockBtn')));

  console.log('\n=== 6. 手机上弹窗与向导不会溢出屏幕 ===');
  await p.evaluate(() => quickCapture()); await p.waitForTimeout(400);
  const modalBox = await p.evaluate(() => {
    const m = document.querySelector('#modal'); if (!m) return null;
    const r = m.getBoundingClientRect();
    return { w: r.width, h: r.height, top: r.top, vw: innerWidth, vh: innerHeight };
  });
  check('捕捉弹窗在屏幕内', modalBox && modalBox.w <= modalBox.vw + 1 && modalBox.h <= modalBox.vh + 1,
    JSON.stringify(modalBox));
  await p.evaluate(() => UI.closeModal()); await p.waitForTimeout(200);
  await p.evaluate(() => WZ.open(0)); await p.waitForTimeout(500);
  const wzBox = await p.evaluate(() => {
    const m = document.querySelector('.wz'); if (!m) return null;
    const r = m.getBoundingClientRect();
    return { w: r.width, h: r.height, vw: innerWidth, vh: innerHeight };
  });
  check('向导在手机上不溢出', wzBox && wzBox.w <= wzBox.vw + 1 && wzBox.h <= wzBox.vh + 1,
    JSON.stringify(wzBox));
  await p.evaluate(() => WZ.close());

  await b.close();
  console.log('\n' + '='.repeat(56));
  console.log(FAIL.length ? `手机与远程界面测试：${FAIL.length} 项失败` : '手机与远程界面测试：全部通过 ✓');
  FAIL.forEach(f => console.log('   ✗', f));
})();
