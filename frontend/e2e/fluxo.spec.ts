import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

/** Critério de aceite: zero violações graves (serious) ou críticas (critical) do axe-core. */
async function checarAxe(page: Page, contexto: string) {
  await page.waitForTimeout(500);
  const resultado = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .exclude('.leaflet-tile-pane')
    .analyze();
  const graves = resultado.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  const descricao = graves.map((v) => `${v.id} (${v.impact}): ${v.help}\n   ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join('\n   ')}`).join('\n');
  expect(graves, `Violações em ${contexto}:\n${descricao}`).toEqual([]);
}

test('passageiro: pino pelo teclado → pontos próximos com previsão → detalhe da linha', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Início/);
  await expect(page.getByRole('heading', { name: 'Pontos perto de você' })).toBeVisible();
  const titulos = page.locator('.lista-pontos .titulo-ponto');
  await expect(titulos.first()).toHaveText('Centro (Praça Sete de Setembro)');
  await expect(page.locator('.lista-pontos .chegada').first()).toBeVisible();
  await expect(page.locator('.lista-pontos .chegada-tempo .tempo').first()).toHaveText(/min|agora|chegando|sem previsão/);
  await checarAxe(page, 'Início');

  // move o pino ~800 m para oeste só com o teclado (Shift + seta = ~100 m)
  const pino = page.locator('[aria-roledescription="pino de localização"]');
  await pino.focus();
  for (let i = 0; i < 8; i++) await page.keyboard.press('Shift+ArrowLeft');
  await page.keyboard.press('Enter');
  await expect(page.locator('[aria-live="polite"]')).toContainText('Ponto mais próximo', { timeout: 15_000 });
  await expect(titulos.first()).not.toHaveText('Centro (Praça Sete de Setembro)');

  // abre o detalhe da primeira linha do primeiro ponto
  await page.locator('.lista-pontos .chegada').first().click();
  await expect(page).toHaveURL(/\/linha\//);
  await expect(page.getByRole('heading', { level: 1 })).toContainText(/Linha (Azul|Verde|Vermelha)/);
  await expect(page.getByRole('tab', { name: 'Próximos' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('sujeito a variação').first()).toBeVisible();
  await checarAxe(page, 'Detalhe da linha');

  await page.getByRole('tab', { name: 'Trajeto' }).click();
  await expect(page.locator('ol.trajeto li').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Horários' }).click();
  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Quadro oficial de horários' })).toBeVisible();
  await page.getByLabel('Sábado').check();
  await expect(page.getByRole('list', { name: /Saídas do Centro/ })).toBeVisible();
});

test.describe('localização real', () => {
  test.use({ permissions: ['geolocation'], geolocation: { latitude: -21.6005, longitude: -48.364 } });

  test('passageiro: usa a localização do aparelho em tempo real', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Linhas de Matão' })).toBeVisible();
    await page.getByRole('button', { name: 'Usar minha localização' }).click();
    await expect(page.getByText('Localização em tempo real ativa.')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Sua localização em tempo real')).toBeVisible();
    await checarAxe(page, 'Início com GPS');
    await page.getByRole('button', { name: 'Parar de usar minha localização' }).click();
    await expect(page.getByRole('button', { name: 'Usar minha localização' })).toBeVisible();
  });
});

test('passageiro: mapa, busca, acessibilidade e histórico sem violações', async ({ page }) => {
  await page.goto('/mapa');
  await expect(page).toHaveTitle(/Mapa ao vivo/);
  await expect(page.locator('.onibus-icone').first()).toBeAttached();
  await page.getByRole('button', { name: 'Linhas', exact: true }).click();
  await expect(page.getByRole('group', { name: /Mostrar ou ocultar linhas/ })).toBeVisible();
  await checarAxe(page, 'Mapa');

  await page.goto('/busca?q=azul&tipo=todos');
  await expect(page.locator('.resultado-linha').first()).toBeVisible();
  await checarAxe(page, 'Busca');

  await page.goto('/acessibilidade');
  await page.getByRole('switch', { name: 'Somente veículos acessíveis' }).check();
  await checarAxe(page, 'Acessibilidade');
  await page.getByRole('link', { name: /Início/ }).first().click();
  await expect(page.getByText(/Filtros ligados: somente ônibus acessíveis/)).toBeVisible();

  await page.goto('/historico');
  await expect(page.getByText(/ficam guardadas só neste aparelho/)).toBeVisible();
  await checarAxe(page, 'Histórico');
});

test('gestor: login e as quatro telas', async ({ page }) => {
  await page.goto('/gestor');
  await expect(page).toHaveURL(/\/gestor\/login/);
  await checarAxe(page, 'Login');
  await page.getByLabel('Usuário').fill(process.env.GESTOR_USUARIO ?? 'gestor');
  await page.getByLabel('Senha').fill(process.env.GESTOR_SENHA ?? 'movecidade');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByRole('heading', { name: 'Painel operacional' })).toBeVisible();

  const menu = page.getByRole('navigation', { name: 'Menu do gestor' }).getByRole('link');
  await expect(menu).toHaveCount(4);
  await expect(page.locator('.kpi')).toHaveCount(5);
  await checarAxe(page, 'Painel');

  for (const [item, titulo] of [['Alertas', 'Alertas da IA'], ['Linhas', 'Linhas cadastradas'], ['Pontos', 'Pontos de parada']]) {
    await menu.filter({ hasText: item }).click();
    await expect(page.getByRole('heading', { level: 1 })).toContainText(titulo);
    await checarAxe(page, item);
  }
});
