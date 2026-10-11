import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'

/**
 * 浏览器 E2E 配置。
 *
 * 复用已缓存的 chromium（受限网络下不重新下载）：~/.cache/ms-playwright/chromium-1223
 * 若该路径不存在则回退到 Playwright 默认解析逻辑（需要本机已装浏览器）。
 *
 * 运行前置：先起 E2E 开发栈 —— `bash scripts/e2e_dev_stack.sh`
 * 运行：    `npx playwright test --config e2e/playwright.config.ts`
 */
const CACHED_CHROMIUM = `${homedir()}/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`
const hasCached = existsSync(CACHED_CHROMIUM)

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.e2e.ts',
  // 产物固定落在 e2e/test-results（相对本配置文件），避免因 cwd 不同散落到项目根
  outputDir: './test-results',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
    launchOptions: hasCached ? { executablePath: CACHED_CHROMIUM } : {},
  },
})
