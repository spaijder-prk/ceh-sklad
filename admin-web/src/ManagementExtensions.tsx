import { FormEvent, useEffect, useState } from 'react'

type User = { role: 'representative' | 'admin' | 'manager' }
type ManagedUser = { id: string; name: string; login: string; role: string; is_active: boolean }
type Location = { id: string; name: string; kind: 'warehouse' | 'representative' }
type Product = { id: string; name: string; sku: string }
type ReportRow = {
  representative_location_id: string
  representative_name: string
  sales_count: number
  sales_amount: number | string
  cash_handover_amount: number | string
  current_debt: number | string
}
type ApiError = { detail?: string }

const API = 'http://localhost:8000/api/v1'

async function request<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Authorization', `Bearer ${token}`)
  if (options.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API}${path}`, { ...options, headers })
  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const body = await response.json() as ApiError
      if (body.detail) message = body.detail
    } catch {
      // Ответ без JSON.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

function toIsoStart(value: string) {
  return value ? `${value}T00:00:00Z` : ''
}

function toIsoEnd(value: string) {
  return value ? `${value}T23:59:59.999Z` : ''
}

function exportReport(rows: ReportRow[], dateFrom: string, dateTo: string) {
  const escape = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`
  const lines = [
    ['Представитель', 'Продаж', 'Сумма продаж', 'Сдано денег', 'Текущий долг'].map(escape).join(';'),
    ...rows.map((row) => [
      row.representative_name,
      row.sales_count,
      row.sales_amount,
      row.cash_handover_amount,
      row.current_debt,
    ].map(escape).join(';')),
  ]
  const blob = new Blob([`\ufeff${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `ceh-sklad-report-${dateFrom || 'all'}-${dateTo || 'all'}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

export default function ManagementExtensions() {
  const [token, setToken] = useState(() => localStorage.getItem('ceh-token') ?? '')
  const [role, setRole] = useState<User['role'] | null>(null)
  const [locations, setLocations] = useState<Location[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [managedUsers, setManagedUsers] = useState<ManagedUser[]>([])
  const [report, setReport] = useState<ReportRow[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    const timer = window.setInterval(() => {
      const actual = localStorage.getItem('ceh-token') ?? ''
      setToken((current) => current === actual ? current : actual)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!token) {
      setRole(null)
      setReport([])
      setManagedUsers([])
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const me = await request<User>('/auth/me', token)
        if (cancelled || me.role === 'representative') return
        setRole(me.role)
        const rows = await request<ReportRow[]>('/reports/representatives', token)
        if (!cancelled) setReport(rows)
        if (me.role === 'admin') {
          const [locationRows, productRows, userRows] = await Promise.all([
            request<Location[]>('/locations', token),
            request<Product[]>('/products', token),
            request<ManagedUser[]>('/admin/managed-users', token),
          ])
          if (!cancelled) {
            setLocations(locationRows)
            setProducts(productRows)
            setManagedUsers(userRows)
          }
        }
      } catch (e) {
        if (!cancelled) setError(String(e).replace('Error: ', ''))
      }
    })()
    return () => { cancelled = true }
  }, [token])

  if (!token || role == null || role === 'representative') return null

  async function loadFilteredReport(event?: FormEvent) {
    event?.preventDefault()
    setError('')
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', toIsoStart(dateFrom))
    if (dateTo) params.set('date_to', toIsoEnd(dateTo))
    try {
      setReport(await request<ReportRow[]>(`/reports/representatives${params.size ? `?${params}` : ''}`, token))
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    }
  }

  async function resetReport() {
    setDateFrom('')
    setDateTo('')
    setError('')
    try {
      setReport(await request<ReportRow[]>('/reports/representatives', token))
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    }
  }

  async function acceptReturn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')
    const form = new FormData(event.currentTarget)
    try {
      await request('/stock/representative-return', token, {
        method: 'POST',
        body: JSON.stringify({
          source_location_id: form.get('source_location_id'),
          destination_location_id: form.get('destination_location_id'),
          items: [{ product_id: form.get('product_id'), quantity: Number(form.get('quantity')) }],
          comment: form.get('comment') || 'Возврат принят через web-панель',
          operation_key: crypto.randomUUID(),
        }),
      })
      setNotice('Возврат принят и проведён отдельным складским документом')
      event.currentTarget.reset()
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    }
  }

  async function setUserStatus(user: ManagedUser, isActive: boolean) {
    setError('')
    setNotice('')
    try {
      const updated = await request<ManagedUser>(`/admin/users/${user.id}/status`, token, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: isActive }),
      })
      setManagedUsers((rows) => rows.map((row) => row.id === updated.id ? updated : row))
      setNotice(isActive ? `Пользователь ${updated.name} разблокирован` : `Пользователь ${updated.name} заблокирован`)
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    }
  }

  const warehouses = locations.filter((item) => item.kind === 'warehouse')
  const representatives = locations.filter((item) => item.kind === 'representative')

  return (
    <main className="management-extension">
      {error && <p className="message error">{error}</p>}
      {notice && <p className="message notice">{notice}</p>}

      <section className="panel">
        <div className="toolbar">
          <div><h2>Отчёт за период</h2><small>Продажи и сдача денег считаются только внутри выбранного периода; текущий долг показывается на настоящий момент.</small></div>
          <button className="secondary" type="button" onClick={() => exportReport(report, dateFrom, dateTo)}>Экспорт CSV</button>
        </div>
        <form className="actions" onSubmit={loadFilteredReport}>
          <label>С<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
          <label>По<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
          <button type="submit">Применить период</button>
          <button className="secondary" type="button" onClick={() => void resetReport()}>Сбросить</button>
        </form>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Представитель</th><th>Продаж</th><th>Сумма продаж</th><th>Сдано денег</th><th>Текущий долг</th></tr></thead>
            <tbody>{report.map((row) => <tr key={row.representative_location_id}><td>{row.representative_name}</td><td>{row.sales_count}</td><td>{row.sales_amount}</td><td>{row.cash_handover_amount}</td><td>{row.current_debt}</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      {role === 'admin' && (
        <>
          <section className="panel">
            <h2>Пользователи</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Имя</th><th>Логин</th><th>Роль</th><th>Статус</th><th>Действие</th></tr></thead>
                <tbody>{managedUsers.map((user) => <tr key={user.id}><td>{user.name}</td><td>{user.login}</td><td>{user.role}</td><td>{user.is_active ? 'Активен' : 'Заблокирован'}</td><td><button className={user.is_active ? 'secondary' : ''} onClick={() => void setUserStatus(user, !user.is_active)}>{user.is_active ? 'Заблокировать' : 'Разблокировать'}</button></td></tr>)}</tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>Приём возврата от представителя</h2>
            <form className="forms-grid" onSubmit={acceptReturn}>
              <label>Представитель<select name="source_location_id" required><option value="">Выберите</option>{representatives.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Склад приёмки<select name="destination_location_id" required><option value="">Выберите</option>{warehouses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Товар<select name="product_id" required><option value="">Выберите</option>{products.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.sku}</option>)}</select></label>
              <label>Количество<input name="quantity" type="number" min="0.001" step="0.001" required /></label>
              <label>Комментарий<input name="comment" placeholder="Комментарий к возврату" /></label>
              <button type="submit">Принять возврат</button>
            </form>
          </section>
        </>
      )}
    </main>
  )
}
