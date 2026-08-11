/* English runtime, accessibility and narrow-screen regression test. */
const BASE = process.env.TEST_URL || 'http://127.0.0.1:8799/';
const { [process.env.PW_BROWSER || 'chromium']: chromium } = require('playwright');

const FAIL = [];
const check = (name, cond, extra = '') => {
  if (cond) console.log('  ✓ ' + name);
  else { FAIL.push(name); console.log('  ✗ ' + name + '  ' + extra); }
};
const hasHan = s => /[\u3400-\u9fff]/.test(s || '');

(async () => {
  const exe = process.env.PW_CHROMIUM || undefined;
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => {
    if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text());
  });
  await page.goto(BASE); await page.waitForTimeout(1000);

  const original = await page.evaluate(() => ({
    language: S.config.language || 'zh-CN',
    setup: JSON.parse(JSON.stringify(S.config.setup || {})),
  }));
  try {
    if (await page.isVisible('#wz')) await page.evaluate(() => WZ.close());
    await page.evaluate(async setup => {
      await saveConfig({ language: 'zh-CN', setup: Object.assign({}, setup, { done: false, step: 0 }) });
    }, original.setup);
    await page.reload(); await page.waitForTimeout(900);
    if (await page.isVisible('#wz')) await page.evaluate(() => WZ.close());

    console.log('\n=== 1. Real language control and first-run UI ===');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      page.click('#langBtn'),
    ]);
    await page.waitForTimeout(1000);
    check('real language button persists English', await page.getAttribute('html', 'lang') === 'en');
    check('language control offers Chinese', (await page.textContent('#langBtn')).includes('中文'));
    check('search placeholder is English', /Search records/.test(await page.getAttribute('#globalSearch', 'placeholder')));
    check('first-run wizard remains open in English', await page.isVisible('#wz'));
    const wizardChrome = await page.textContent('#wz .wz-head, #wz .wz-foot');
    check('wizard heading and controls contain no Chinese chrome', !hasHan(wizardChrome), wizardChrome.slice(0, 120));
    check('wizard has dialog semantics', await page.getAttribute('#wz', 'role') === 'dialog'
      && await page.getAttribute('#wz', 'aria-modal') === 'true');
    await page.evaluate(() => WZ.close());

    const nav = await page.textContent('#nav');
    check('navigation is English', nav.includes('Today') && nav.includes('Research') && nav.includes('Settings'));
    check('active route is exposed', await page.getAttribute('#nav [aria-current="page"]', 'aria-current') === 'page');

    console.log('\n=== 2. Late UI, dates and user content ===');
    await page.evaluate(() => go('hub')); await page.waitForTimeout(250);
    const hub = await page.textContent('#view');
    check('research card chrome is English', hub.includes('Active projects') && hub.includes('Local PDF library'));
    const dates = await page.evaluate(() => [daysChip(-2), daysChip(0), daysChip(1), daysChip(4)]);
    check('relative dates render in English', dates.join(' ').includes('2 days overdue')
      && dates.join(' ').includes('Tomorrow') && dates.join(' ').includes('In 4 days'), JSON.stringify(dates));

    await page.evaluate(() => UI.modal('编辑', `<div class="field"><label for="auditName">名称</label><input id="auditName"></div>`,
      `<button class="btn primary">保存</button><button class="btn" data-close>取消</button>`));
    await page.waitForTimeout(100);
    const modalText = await page.textContent('#modal');
    check('late modal is translated', modalText.includes('Edit') && modalText.includes('Save') && modalText.includes('Cancel'));
    check('modal semantics and associated label exist', await page.getAttribute('#modal', 'role') === 'dialog'
      && await page.getAttribute('#modal label', 'for') === 'auditName');
    check('modal receives focus', await page.evaluate(() => document.querySelector('#modal').contains(document.activeElement)));
    await page.keyboard.press('Escape');
    check('Escape closes modal', !(await page.isVisible('#modalBack')));

    await page.evaluate(() => {
      S.data.ideas.push({ id: 'i18n-user-content', title: '想法', kind: 'idea' });
      go('ideas');
    });
    await page.waitForTimeout(250);
    check('user-authored Chinese title is preserved', (await page.textContent('#view')).includes('想法'));
    await page.evaluate(() => { S.data.ideas = S.data.ideas.filter(x => x.id !== 'i18n-user-content'); });

    console.log('\n=== 3. Failed toggle does not reload or lie ===');
    await page.route('**/api/config', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"offline"}' }));
    await page.click('#langBtn'); await page.waitForTimeout(500);
    check('failed save keeps English document', await page.getAttribute('html', 'lang') === 'en');
    check('failed save leaves control usable', !(await page.isDisabled('#langBtn')));
    check('failure is announced in English', /Language was not saved/.test(await page.textContent('#toast')),
      await page.textContent('#toast'));
    await page.unroute('**/api/config');

    console.log('\n=== 4. Private Git confirmation ===');
    await page.evaluate(() => go('settings')); await page.waitForTimeout(250);
    const initBodies = [];
    await page.route('**/api/git/init', async route => {
      initBodies.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.fill('#git_remote', 'https://github.com/example/private-workspace.git');
    await page.click('#gitInit'); await page.waitForTimeout(100);
    check('Git init is blocked until privacy is confirmed', initBodies.length === 0
      && /private|私有/.test(await page.textContent('#gitOut')));
    await page.check('#git_private_confirm');
    await page.click('#gitInit'); await page.waitForTimeout(300);
    check('Git init sends explicit private confirmation', initBodies.length === 1
      && initBodies[0].private_confirmed === true, JSON.stringify(initBodies));
    await page.unroute('**/api/git/init');

    console.log('\n=== 5. Mobile drawer and responsive English header ===');
    await page.setViewportSize({ width: 360, height: 740 }); await page.waitForTimeout(200);
    check('closed mobile navigation is inert', await page.getAttribute('#sidebar', 'inert') !== null);
    await page.click('#menuBtn');
    check('menu exposes expanded state', await page.getAttribute('#menuBtn', 'aria-expanded') === 'true');
    await page.keyboard.press('Escape');
    check('Escape closes and inerts menu', await page.getAttribute('#menuBtn', 'aria-expanded') === 'false'
      && await page.getAttribute('#sidebar', 'inert') !== null);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const overflowSources = overflow <= 2 ? [] : await page.evaluate(() => Array.from(document.querySelectorAll('body *'))
      .map(el => {
        const r = el.getBoundingClientRect();
        return { el, right: r.right, left: r.left, extra: Math.max(r.right - innerWidth, el.scrollWidth - el.clientWidth) };
      })
      .filter(x => x.right > innerWidth + 2 || x.extra > 2)
      .sort((a, b) => b.extra - a.extra)
      .slice(0, 8)
      .map(x => `${x.el.tagName.toLowerCase()}#${x.el.id}.${x.el.className}:${Math.round(x.right)}/${x.el.scrollWidth}/${Math.round(x.extra)}`));
    check('English mobile topbar does not cause horizontal overflow', overflow <= 2,
      `${overflow}; ${overflowSources.join(' | ')}`);

    console.log('\n=== 6. Standalone pages inherit language ===');
    await page.goto(BASE + 'jot.html'); await page.waitForTimeout(150);
    check('quick-capture page is English', await page.getAttribute('html', 'lang') === 'en'
      && (await page.textContent('body')).includes('Save to workspace'));
    await page.goto(BASE + 'login.html'); await page.waitForTimeout(150);
    check('login page is English', await page.getAttribute('html', 'lang') === 'en'
      && (await page.textContent('body')).includes('Access code required'));

    check('no page or console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
  } finally {
    await page.unroute('**/api/config').catch(() => {});
    await page.goto(BASE); await page.waitForTimeout(700);
    if (await page.isVisible('#wz')) await page.evaluate(() => WZ.close());
    await page.evaluate(async state => {
      await saveConfig({ language: state.language, setup: state.setup });
      try { localStorage.setItem('sw_language', state.language); } catch (e) {}
    }, original).catch(() => {});
    await browser.close();
  }

  console.log('\n' + '='.repeat(56));
  console.log(FAIL.length ? `English UI test: ${FAIL.length} failures` : 'English UI test: 全部通过 ✓');
  FAIL.forEach(f => console.log('   ✗', f));
  process.exitCode = FAIL.length ? 1 : 0;
})();
