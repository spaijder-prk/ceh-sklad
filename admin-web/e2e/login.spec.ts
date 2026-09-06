import { expect, test, type Route } from '@playwright/test'

const API = 'http://localhost:8000/api/v1'

async function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers,
    body: JSON.stringify(body),
  })
}

test('администратор входит через cookie-сессию без JWT в браузере и WebSocket URL', async ({ page }) => {
  let authenticated = false
  const websocketUrls: string[] = []
  page.on('websocket', (socket) => websocketUrls.push(socket.url()))

  await page.route(`${API}/**`, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/v1', '')

    if (path === '/auth/me') {
      if (!authenticated) return json(route, { detail: 'Требуется авторизация' }, 401)
      return json(route, { id: 'admin-1', name: 'Администратор', login: 'admin', role: 'admin', location_id: null })
    }
    if (path === '/auth/web-login' && route.request().method() === 'POST') {
      authenticated = true
      return json(
        route,
        { message: 'Браузерная сессия создана' },
        200,
        { 'set-cookie': 'ceh_session=test-session; HttpOnly; Path=/; SameSite=Strict, ceh_csrf=e2e-csrf; Path=/; SameSite=Strict' },
      )
    }
    if (path === '/auth/web-logout' && route.request().method() === 'POST') {
      expect(route.request().headers()['x-csrf-token']).toBe('e2e-csrf')
      authenticated = false
      return json(
        route,
        { message: 'Браузерная сессия завершена' },
        200,
        { 'set-cookie': 'ceh_session=; Max-Age=0; Path=/, ceh_csrf=; Max-Age=0; Path=/' },
      )
    }

    const emptyLists = new Set([
      '/stocks', '/locations', '/products', '/admin/users', '/representatives/debts/all',
      '/operations/stock', '/operations/money', '/reports/representatives', '/admin/integration-1c/logs',
    ])
    if (emptyLists.has(path)) return json(route, [])

    return json(route, { detail: `Неожиданный E2E запрос ${path}` }, 500)
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Цех Склад' })).toBeVisible()
  await page.getByLabel('Логин').fill('admin')
  await page.getByLabel('Пароль').fill('WebSecure123')
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page.getByText('Панель администратора')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('ceh-token'))).toBeNull()
  await expect.poll(() => websocketUrls.length).toBeGreaterThan(0)
  expect(websocketUrls[0]).toBe('ws://localhost:8000/api/v1/realtime')
  expect(websocketUrls[0]).not.toContain('token=')

  await page.getByRole('button', { name: 'Выйти' }).click()
  await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible()
})
