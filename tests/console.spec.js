const { test, expect } = require('@playwright/test');

/** Collect console errors and uncaught exceptions for the whole test. */
function watchErrors(page) {
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  return errors;
}

async function forestCellClientPoint(page, near = [60, 40]) {
  return page.evaluate(([nx0, ny0]) => {
    const { land } = EMBER;
    for (let r = 0; r < 40; r++)
      for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
        const x = nx0 + dx, y = ny0 + dy, i = y * 180 + x;
        if (land.cls[i] === 3 || land.cls[i] === 4) {
          const b = document.querySelector('[data-testid=map]').getBoundingClientRect();
          return { x: b.left + (x + 0.5) / 180 * b.width, y: b.top + (y + 0.5) / 112 * b.height };
        }
      }
    return null;
  }, near);
}

const num = (s) => parseFloat(s.replace(/[^0-9.]/g, ''));

test.describe('EMBER console', () => {
  test('loads with zero console errors', async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto('/');
    await expect(page.getByTestId('ffdi-value')).toBeVisible();
    await page.waitForTimeout(1500);
    expect(errors).toEqual([]);
  });

  test('Black Saturday preset gives FFDI ≈ 172, catastrophic', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('preset-mild').click();
    await expect(page.getByTestId('ffdi-band')).toHaveText('LOW-MODERATE');
    await page.getByTestId('preset-bs').click();
    expect(num(await page.getByTestId('ffdi-value').textContent())).toBeGreaterThanOrEqual(172);
    expect(num(await page.getByTestId('ffdi-value').textContent())).toBeLessThanOrEqual(173);
    await expect(page.getByTestId('ffdi-band')).toHaveText('CATASTROPHIC');
    await expect(page.getByTestId('feed')).toContainText("Black Saturday '09");
  });

  test('every preset lands in the expected legacy McArthur band', async ({ page }) => {
    await page.goto('/');
    const expected = { mild: 'LOW-MODERATE', summer: 'VERY HIGH', north: 'EXTREME', ash: 'CATASTROPHIC', bs: 'CATASTROPHIC' };
    for (const [id, band] of Object.entries(expected)) {
      await page.getByTestId(`preset-${id}`).click();
      await expect(page.getByTestId('ffdi-band')).toHaveText(band);
    }
  });

  test('sliders drive the FFDI gauge', async ({ page }) => {
    await page.goto('/');
    const before = num(await page.getByTestId('ffdi-value').textContent());
    await page.getByTestId('slider-rh').fill('40');
    const wetter = num(await page.getByTestId('ffdi-value').textContent());
    expect(wetter).toBeLessThan(before);
    await page.getByTestId('slider-temp').fill('20');
    await page.getByTestId('slider-wind').fill('10');
    await page.getByTestId('slider-df').fill('3');
    expect(num(await page.getByTestId('ffdi-value').textContent())).toBeLessThan(12);
    await expect(page.getByTestId('ffdi-band')).toHaveText('LOW-MODERATE');
    const js = await page.evaluate(() => EMBER.Model.ffdi(20, 40, 10, 3));
    expect(num(await page.getByTestId('ffdi-value').textContent())).toBeCloseTo(js, 1);
  });

  test('wind compass can be dragged and keyed', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('compass').scrollIntoViewIfNeeded();
    const c = await page.getByTestId('compass').boundingBox();
    await page.mouse.move(c.x + c.width / 2, c.y + 12);
    await page.mouse.down();
    await page.mouse.move(c.x + c.width - 10, c.y + c.height / 2, { steps: 6 });   // drag to east
    await page.mouse.move(c.x + c.width / 2, c.y + c.height - 10, { steps: 6 });  // then south
    await page.mouse.up();
    const from = await page.evaluate(() => EMBER.state.wx.windFrom);
    expect(from).toBeGreaterThanOrEqual(170);
    expect(from).toBeLessThanOrEqual(190);
    await page.getByTestId('compass').focus();
    await page.keyboard.press('ArrowRight');
    expect(await page.evaluate(() => EMBER.state.wx.windFrom)).toBe(from + 5);
    await expect(page.getByTestId('compass')).toHaveAttribute('aria-valuenow', String(from + 5));
  });

  test('click to ignite: fire spreads, KPIs and feed update, no errors', async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto('/');
    await page.getByTestId('preset-bs').click();
    const pt = await forestCellClientPoint(page);
    await page.mouse.click(pt.x, pt.y);
    await expect(page.getByTestId('feed')).toContainText('Fire start');
    await page.getByTestId('speed-16').click();
    await expect.poll(async () => num(await page.getByTestId('kpi-area').textContent()), { timeout: 15_000 }).toBeGreaterThan(200);
    const a1 = num(await page.getByTestId('kpi-area').textContent());
    await page.waitForTimeout(1500);
    expect(num(await page.getByTestId('kpi-area').textContent())).toBeGreaterThan(a1);
    await expect(page.getByTestId('sim-elapsed')).not.toHaveText('T+00:00');
    // Time to first asset shows a projection or an actual time
    await expect(page.getByTestId('kpi-time')).toContainText(/\d\d:\d\d/);
    expect(errors).toEqual([]);
  });

  test('a Black Saturday demo fire reaches a township', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('btn-demo').click();
    await page.getByTestId('speed-16').click();
    await expect(page.getByTestId('rank-body')).toContainText('IMPACT', { timeout: 30_000 });
    expect(num(await page.getByTestId('kpi-pop').textContent())).toBeGreaterThan(0);
    await expect(page.getByTestId('feed')).toContainText('fire front has reached the township');
  });

  test('water cannot be ignited', async ({ page }) => {
    await page.goto('/');
    const ok = await page.evaluate(() => {
      const i = EMBER.land.cls.findIndex((c) => c === 0);
      return EMBER.ignite(i % 180, Math.floor(i / 180));
    });
    expect(ok).toBe(false);
    await expect(page.getByTestId('feed')).toContainText('Ignition rejected');
  });

  test('downwind spread outruns upwind spread on the real map', async ({ page }) => {
    await page.goto('/');
    const r = await page.evaluate(() => {
      EMBER.setWeather({ temp: 35, rh: 15, wind: 30, df: 9, windFrom: 270 });
      EMBER.state.spot = false;
      EMBER.ignite(40, 20);
      const T = EMBER.state.T, horizon = 1.0;
      let minX = 1e9, maxX = -1;
      for (let i = 0; i < T.length; i++) if (T[i] <= horizon && Math.floor(i / 180) === 20) { minX = Math.min(minX, i % 180); maxX = Math.max(maxX, i % 180); }
      return { down: maxX - 40, up: 40 - minX };
    });
    expect(r.down).toBeGreaterThan(r.up * 2);
  });

  test('pause, reset and toggles work', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('btn-demo').click();
    await page.getByTestId('btn-play').click();
    await expect(page.getByTestId('btn-play')).toContainText('RUN');
    const t = await page.evaluate(() => EMBER.state.t);
    await page.waitForTimeout(500);
    expect(await page.evaluate(() => EMBER.state.t)).toBe(t);
    await page.getByTestId('btn-reset').click();
    await expect(page.getByTestId('kpi-area')).toContainText('0');
    await expect(page.getByTestId('kpi-time')).toHaveText('—');
  });
});

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1200, height: 800 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'mobile', width: 390, height: 844 },
];

for (const vp of VIEWPORTS) {
  test(`layout @ ${vp.name} ${vp.width}px: no horizontal scroll, no errors, screenshot`, async ({ page }) => {
    const errors = watchErrors(page);
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const tableFits = await page.evaluate(() => { const t = document.querySelector('[data-testid=rank-body]').closest('table'); return t.scrollWidth <= t.parentElement.clientWidth; });
    expect(tableFits).toBe(true);
    await expect(page.getByTestId('map')).toBeVisible();
    const map = await page.getByTestId('map').boundingBox();
    expect(map.width).toBeGreaterThan(vp.width * (vp.width >= 1200 ? 0.4 : 0.9));
    // Deterministic mid-fire scene for the screenshot
    await page.evaluate(() => { Math.random = (() => { let s = 7; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })(); });
    await page.getByTestId('btn-demo').click();
    await page.getByTestId('speed-4').click();
    await page.waitForTimeout(5000);
    await page.getByTestId('btn-play').click();
    await page.screenshot({ path: `screenshots/${vp.name}.png`, fullPage: !['desktop', 'laptop'].includes(vp.name) });
    expect(errors).toEqual([]);
  });
}
