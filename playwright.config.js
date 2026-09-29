// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 60_000,
  fullyParallel: true,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:8766', deviceScaleFactor: 1 },
  webServer: {
    command: 'python3 -m http.server 8766 --bind 127.0.0.1',
    url: 'http://127.0.0.1:8766/index.html',
    reuseExistingServer: true,
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
