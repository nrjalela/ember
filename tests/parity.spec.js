// Checks the JS model in index.html against fixtures exported from the
// validated Python reference (validation/export_fixtures.py).
const { test, expect } = require('@playwright/test');
const fixture = require('./fixtures/parity.json');

test.beforeEach(async ({ page }) => { await page.goto('/'); });

test('FFDI and danger bands match Python', async ({ page }) => {
  const out = await page.evaluate((cases) => cases.map((c) => ({
    ffdi: EMBER.Model.ffdi(c.t, c.rh, c.v, c.df),
    band: EMBER.Model.dangerBand(EMBER.Model.ffdi(c.t, c.rh, c.v, c.df)),
  })), fixture.ffdi);
  fixture.ffdi.forEach((c, k) => {
    expect(out[k].ffdi).toBeCloseTo(c.ffdi, 9);
    expect(out[k].band).toBe(c.band);
  });
  expect(out[0].ffdi).toBeCloseTo(172.5, 0);
});

test('rate of spread matches Python', async ({ page }) => {
  const out = await page.evaluate((cases) => cases.map((c) => EMBER.Model.rateOfSpread(c.ffdi, c.w, c.slope)), fixture.ros);
  fixture.ros.forEach((c, k) => expect(out[k]).toBeCloseTo(c.ros, 9));
});

test('CA arrival-time field matches Python cell-for-cell', async ({ page }) => {
  const sp = fixture.spread;
  const out = await page.evaluate((sp) => {
    const t = EMBER.Model.arrivalTimes(
      { nx: sp.nx, ny: sp.ny, cellM: sp.cellM, fuel: sp.fuel, elev: sp.elev },
      { temp: sp.weather.temp, rh: sp.weather.rh, wind: sp.weather.wind, df: sp.weather.df, windFrom: sp.weather.windFrom },
      sp.sources.map((s) => [s.i, s.t]));
    return Array.from(t, (v) => (isFinite(v) ? v : null));
  }, sp);
  expect(out.length).toBe(sp.arrival.length);
  let reached = 0;
  sp.arrival.forEach((ref, i) => {
    if (ref === null) { expect(out[i], `cell ${i}`).toBeNull(); return; }
    reached++;
    expect(Math.abs(out[i] - ref) / Math.max(ref, 1e-9), `cell ${i}`).toBeLessThan(1e-9);
  });
  expect(reached).toBeGreaterThan(sp.arrival.length / 2);
});
