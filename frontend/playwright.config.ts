import { defineConfig, devices } from '@playwright/test';

// Sobe API e front se ainda não estiverem rodando (reaproveita o "npm run dev" se já estiver no ar).
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:5173', locale: 'pt-BR', trace: 'retain-on-failure' },
  webServer: [
    { command: 'node ../scripts/api.mjs', url: 'http://127.0.0.1:8000/api/status', reuseExistingServer: true, timeout: 180_000 },
    { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true, timeout: 120_000 },
  ],
  projects: [
    { name: 'celular', use: { ...devices['Pixel 7'] } },
    { name: 'computador', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
  ],
});
