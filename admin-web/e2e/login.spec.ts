import { expect, test, type Route } from '@playwright/test'

const API = 'http://localhost:8000/api/v1'

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
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
      await page.context().addCookies([
        {
          name: 'ceh_session',
          value: 'test-session',
          domain: 'localhost',
          path: '/',
          httpOnly: true,
          sameSite: 'Strict',
        },
        {
          name: 'ceh_csrf',
          value: 'e2e-csrf',
          domain: 'localhost',
          path: '/',
          sameSite: 'Strict',
        },
      ])
      return json(route, { message: 'Браузерная сессия создана' })
    }
    if (path === '/auth/web-logout' && route.request().method() === 'POST') {
      expect(route.request().headers()['x-csrf-token']).toBe('e2e-csrf')
      authenticated = false
      await page.context().clearCookies()
      return json(route, { message: 'Браузерная сессия завершена' })
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
  expect(await page.evaluate(() => document.cookie)).toContain('ceh_csrf=e2e-csrf')
  expect(await page.evaluate(() => document.cookie)).not.toContain('ceh_session=')

  await expect.poll(() => websocketUrls.filter((url) => url.includes('/api/v1/realtime')).length).toBeGreaterThan(0)
  const applicationWebSocket = websocketUrls.find((url) => url.includes('/api/v1/realtime'))
  expect(applicationWebSocket).toBe('ws://localhost:8000/api/v1/realtime')
  expect(applicationWebSocket).not.toContain('token=')

  await page.getByRole('button', { name: 'Выйти' }).click()
  await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible()
})
