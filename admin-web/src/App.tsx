import { FormEvent, useEffect, useMemo, useState } from 'react'

type Amount = number | string

type Stock = {
  location_id: string
  location_name: string
  product_id: string
  sku: string
  product_name: string
  unit_name: string
  quantity: Amount
  retail_price: Amount
  wholesale_price: Amount
}

type Location = { id: string; name: string; kind: 'warehouse' | 'representative'; external_1c_id?: string | null }
type Product = { id: string; sku: string; name: string; unit_name: string; retail_price: Amount; wholesale_price: Amount }
type User = { id: string; name: string; login: string; role: 'representative' | 'admin' | 'manager'; location_id?: string | null }
type Debt = { representative_location_id: string; representative_name: string; debt: Amount }
type StockOperationLine = { product_id: string; sku: string; product_name: string; unit_name: string; quantity: Amount; unit_price?: Amount | null }
type StockOperation = {
  id: string
  kind: string
  source_location_name?: string | null
  destination_location_name?: string | null
  created_by_name?: string | null
  comment?: string | null
  created_at: string
  external_1c_id?: string | null
  synced_1c_at?: string | null
  lines: StockOperationLine[]
}
type MoneyOperation = {
  id: string
  representative_name: string
  kind: string
  amount: Amount
  created_by_name?: string | null
  comment?: string | null
  created_at: string
  external_1c_id?: string | null
  synced_1c_at?: string | null
}
type RepresentativeReport = {
  representative_location_id: string
  representative_name: string
  sales_count: number
  sales_amount: Amount
  cash_handover_amount: Amount
  current_debt: Amount
}
type IntegrationLog = {
  id: string
  direction: string
  operation_key: string
  entity_type: string
  external_1c_id?: string | null
  status: string
  error_message?: string | null
  created_at: string
}

type ApiError = { detail?: string }

const API = 'http://localhost:8000/api/v1'

const stockKindLabel: Record<string, string> = {
  transfer: 'Перемещение',
  issue_to_representative: 'Выдача представителю',
  representative_return: 'Возврат от представителя',
  sale: 'Продажа',
  adjustment: 'Корректировка',
}

const moneyKindLabel: Record<string, string> = {
  sale: 'Продажа',
  cash_handover: 'Сдача денег',
  adjustment: 'Корректировка',
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('ru-RU')
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('ceh-token') ?? '')
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [stocks, setStocks] = useState<Stock[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [debts, setDebts] = useState<Debt[]>([])
  const [stockOperations, setStockOperations] = useState<StockOperation[]>([])
  const [moneyOperations, setMoneyOperations] = useState<MoneyOperation[]>([])
  const [report, setReport] = useState<RepresentativeReport[]>([])
  const [integrationLogs, setIntegrationLogs] = useState<IntegrationLog[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function api<T>(path: string, options: RequestInit = {}, currentToken = token): Promise<T> {
    const headers = new Headers(options.headers)
    if (currentToken) headers.set('Authorization', `Bearer ${currentToken}`)
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    const response = await fetch(`${API}${path}`, { ...options, headers })
    if (response.status === 401) {
      signOut()
      throw new Error('Сессия завершена')
    }
    if (!response.ok) {
      let message = `HTTP ${response.status}`
      try {
        const body = await response.json() as ApiError
        if (body.detail) message = body.detail
      } catch {
        // Сервер мог вернуть ответ без JSON.
      }
      throw new Error(message)
    }
    return response.json() as Promise<T>
  }

  async function signIn(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ login, password }),
      })
      if (!response.ok) throw new Error('Неверный логин или пароль')
      const data = await response.json() as { access_token: string }
      localStorage.setItem('ceh-token', data.access_token)
      setToken(data.access_token)
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    }
  }

  function signOut() {
    localStorage.removeItem('ceh-token')
    setToken('')
    setCurrentUser(null)
    setStocks([])
    setLocations([])
    setProducts([])
    setUsers([])
    setDebts([])
    setStockOperations([])
    setMoneyOperations([])
    setReport([])
    setIntegrationLogs([])
  }

  async function load(currentToken = token) {
    if (!currentToken) return
    setError('')
    try {
      const me = await api<User>('/auth/me', {}, currentToken)
      setCurrentUser(me)
      const [stockRows, locationRows, productRows] = await Promise.all([
        api<Stock[]>('/stocks', {}, currentToken),
        api<Location[]>('/locations', {}, currentToken),
        api<Product[]>('/products', {}, currentToken),
      ])
      setStocks(stockRows)
      setLocations(locationRows)
      setProducts(productRows)
      if (me.role === 'admin') setUsers(await api<User[]>('/admin/users', {}, currentToken))
      else setUsers([])
      if (me.role === 'admin' || me.role === 'manager') {
        const [debtRows, stockHistory, moneyHistory, reportRows, syncRows] = await Promise.all([
          api<Debt[]>('/representatives/debts/all', {}, currentToken),
          api<StockOperation[]>('/operations/stock?limit=100', {}, currentToken),
          api<MoneyOperation[]>('/operations/money?limit=100', {}, currentToken),
          api<RepresentativeReport[]>('/reports/representatives', {}, currentToken),
          api<IntegrationLog[]>('/admin/integration-1c/logs?limit=50', {}, currentToken),
        ])
        setDebts(debtRows)
        setStockOperations(stockHistory)
        setMoneyOperations(moneyHistory)
        setReport(reportRows)
        setIntegrationLogs(syncRows)
      } else {
        setDebts([])
        setStockOperations([])
        setMoneyOperations([])
        setReport([])
        setIntegrationLogs([])
      }
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    }
  }

  async function action(path: string, body: unknown, success: string) {
    setError('')
    setNotice('')
    try {
      await api(path, { method: 'POST', body: JSON.stringify(body) })
      setNotice(success)
      await load()
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    }
  }

  useEffect(() => { if (token) void load(token) }, [token])

  useEffect(() => {
    if (!token) return
    const wsBase = API.replace('http://', 'ws://').replace('https://', 'wss://').replace('/api/v1', '')
    const socket = new WebSocket(`${wsBase}/api/v1/realtime?token=${encodeURIComponent(token)}`)
    socket.onmessage = () => void load(token)
    return () => socket.close()
  }, [token])

  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return stocks
    return stocks.filter((item) => `${item.product_name} ${item.sku} ${item.location_name}`.toLowerCase().includes(value))
  }, [stocks, query])

  if (!token) {
    return (
      <main className="login-page">
        <form className="login-card" onSubmit={signIn}>
          <p className="eyebrow">Панель управления</p>
          <h1>Цех Склад</h1>
          <label>Логин<input value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" /></label>
          <label>Пароль<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
          {error && <p className="error">{error}</p>}
          <button type="submit">Войти</button>
        </form>
      </main>
    )
  }

  if (currentUser?.role === 'representative') {
    return <main><section className="panel"><h1>Цех Склад</h1><p>Для торгового представителя предназначено Android-приложение.</p><button onClick={signOut}>Выйти</button></section></main>
  }

  const totalPositions = new Set(stocks.map((item) => item.product_id)).size
  const warehouseCount = locations.filter((item) => item.kind === 'warehouse').length
  const representativeCount = locations.filter((item) => item.kind === 'representative').length

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">{currentUser?.role === 'manager' ? 'Панель руководителя' : 'Панель администратора'}</p>
          <h1>Цех Склад</h1>
          <small>{currentUser?.name}</small>
        </div>
        <div className="actions"><button onClick={() => void load()}>Обновить</button><button className="secondary" onClick={signOut}>Выйти</button></div>
      </header>

      {error && <p className="message error">{error}</p>}
      {notice && <p className="message notice">{notice}</p>}

      <section className="metrics">
        <article><span>Товарных позиций</span><strong>{totalPositions}</strong></article>
        <article><span>Складов</span><strong>{warehouseCount}</strong></article>
        <article><span>Представителей</span><strong>{representativeCount}</strong></article>
      </section>

      <section className="panel">
        <div className="toolbar"><h2>Остатки и цены</h2><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Товар, артикул или склад" /></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Склад / представитель</th><th>Товар</th><th>Остаток</th><th>Розница</th><th>Опт</th></tr></thead>
            <tbody>{filtered.map((item) => <tr key={`${item.location_id}:${item.product_id}`}><td>{item.location_name}</td><td><b>{item.product_name}</b><small>{item.sku}</small></td><td>{item.quantity} {item.unit_name}</td><td>{item.retail_price}</td><td>{item.wholesale_price}</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h2>Финансовый отчет по представителям</h2>
        <div className="table-wrap"><table><thead><tr><th>Представитель</th><th>Продаж</th><th>Сумма продаж</th><th>Сдано денег</th><th>Текущий долг</th></tr></thead><tbody>{report.map((item) => <tr key={item.representative_location_id}><td>{item.representative_name}</td><td>{item.sales_count}</td><td>{item.sales_amount}</td><td>{item.cash_handover_amount}</td><td>{item.current_debt}</td></tr>)}</tbody></table></div>
      </section>

      <section className="panel">
        <h2>Задолженность торговых представителей</h2>
        <div className="table-wrap"><table><thead><tr><th>Представитель</th><th>Задолженность</th></tr></thead><tbody>{debts.map((item) => <tr key={item.representative_location_id}><td>{item.representative_name}</td><td>{item.debt}</td></tr>)}</tbody></table></div>
      </section>

      <section className="panel">
        <h2>Журнал товарных операций</h2>
        <div className="table-wrap"><table><thead><tr><th>Дата</th><th>Операция</th><th>Направление</th><th>Товары</th><th>Пользователь</th><th>1С</th></tr></thead><tbody>{stockOperations.map((item) => <tr key={item.id}><td>{formatDate(item.created_at)}</td><td><b>{stockKindLabel[item.kind] ?? item.kind}</b><small>{item.comment}</small></td><td>{item.source_location_name ?? '—'} → {item.destination_location_name ?? '—'}</td><td>{item.lines.map((line) => <small key={line.product_id}>{line.product_name}: {line.quantity} {line.unit_name}{line.unit_price != null ? ` × ${line.unit_price}` : ''}</small>)}</td><td>{item.created_by_name ?? 'Система / 1С'}</td><td>{item.synced_1c_at ? `✓ ${item.external_1c_id ?? ''}` : 'Ожидает'}</td></tr>)}</tbody></table></div>
      </section>

      <section className="panel">
        <h2>Журнал денежных операций</h2>
        <div className="table-wrap"><table><thead><tr><th>Дата</th><th>Представитель</th><th>Операция</th><th>Сумма в регистре</th><th>Пользователь</th><th>1С</th></tr></thead><tbody>{moneyOperations.map((item) => <tr key={item.id}><td>{formatDate(item.created_at)}</td><td>{item.representative_name}</td><td><b>{moneyKindLabel[item.kind] ?? item.kind}</b><small>{item.comment}</small></td><td>{item.amount}</td><td>{item.created_by_name ?? 'Система'}</td><td>{item.kind === 'sale' ? 'В составе продажи' : item.synced_1c_at ? `✓ ${item.external_1c_id ?? ''}` : 'Ожидает'}</td></tr>)}</tbody></table></div>
      </section>

      <section className="panel">
        <h2>Журнал обмена с 1С</h2>
        <div className="table-wrap"><table><thead><tr><th>Дата</th><th>Направление</th><th>Объект</th><th>Ключ</th><th>Статус</th><th>Ошибка</th></tr></thead><tbody>{integrationLogs.map((item) => <tr key={item.id}><td>{formatDate(item.created_at)}</td><td>{item.direction === 'inbound' ? '1С → Склад' : 'Склад → 1С'}</td><td>{item.entity_type}<small>{item.external_1c_id}</small></td><td>{item.operation_key}</td><td>{item.status}</td><td>{item.error_message ?? '—'}</td></tr>)}</tbody></table></div>
      </section>

      {currentUser?.role === 'admin' && <AdminTools locations={locations} products={products} users={users} action={action} />}
    </main>
  )
}

function AdminTools({ locations, products, users, action }: { locations: Location[]; products: Product[]; users: User[]; action: (path: string, body: unknown, success: string) => Promise<void> }) {
  const warehouses = locations.filter((item) => item.kind === 'warehouse')
  const representatives = locations.filter((item) => item.kind === 'representative')

  async function createLocation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await action('/admin/locations', { name: form.get('name'), kind: form.get('kind') }, 'Место хранения создано')
    event.currentTarget.reset()
  }

  async function createProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await action('/admin/products', {
      sku: form.get('sku'), name: form.get('name'), unit_name: form.get('unit_name'),
      retail_price: Number(form.get('retail_price')), wholesale_price: Number(form.get('wholesale_price')),
    }, 'Товар создан')
    event.currentTarget.reset()
  }

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const role = String(form.get('role'))
    await action('/admin/users', {
      name: form.get('name'), login: form.get('login'), password: form.get('password'), role,
      location_id: role === 'representative' ? form.get('location_id') : null,
    }, 'Пользователь создан')
    event.currentTarget.reset()
  }

  async function adjust(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await action('/stock/adjustments', {
      location_id: form.get('location_id'),
      items: [{ product_id: form.get('product_id'), quantity_delta: Number(form.get('quantity_delta')) }],
      comment: form.get('comment'),
    }, 'Остаток скорректирован')
  }

  async function move(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const operation = String(form.get('operation'))
    const path = operation === 'issue' ? '/stock/issue-to-representative' : '/stock/transfers'
    await action(path, {
      source_location_id: form.get('source_location_id'), destination_location_id: form.get('destination_location_id'),
      items: [{ product_id: form.get('product_id'), quantity: Number(form.get('quantity')) }], comment: form.get('comment') || null,
    }, operation === 'issue' ? 'Товар выдан представителю' : 'Перемещение проведено')
  }

  return (
    <>
      <section className="panel"><h2>Администрирование справочников</h2><div className="forms-grid">
        <form onSubmit={createLocation}><h3>Новое место хранения</h3><input name="name" required placeholder="Название" /><select name="kind"><option value="warehouse">Склад</option><option value="representative">Торговый представитель</option></select><button>Создать</button></form>
        <form onSubmit={createProduct}><h3>Новый товар</h3><input name="sku" required placeholder="Артикул" /><input name="name" required placeholder="Название" /><input name="unit_name" defaultValue="шт" required placeholder="Единица" /><input name="retail_price" type="number" min="0" step="0.01" required placeholder="Розничная цена" /><input name="wholesale_price" type="number" min="0" step="0.01" required placeholder="Оптовая цена" /><button>Создать</button></form>
        <form onSubmit={createUser}><h3>Новый пользователь</h3><input name="name" required placeholder="Имя" /><input name="login" required minLength={3} placeholder="Логин" /><input name="password" type="password" required minLength={8} placeholder="Пароль" /><select name="role"><option value="representative">Торговый представитель</option><option value="manager">Руководитель</option><option value="admin">Администратор</option></select><select name="location_id"><option value="">Виртуальный склад</option>{representatives.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><button>Создать</button><small>Пользователей: {users.length}</small></form>
      </div></section>

      <section className="panel"><h2>Операции склада</h2><div className="forms-grid">
        <form onSubmit={adjust}><h3>Начальный остаток / корректировка</h3><select name="location_id" required><option value="">Место хранения</option>{locations.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><select name="product_id" required><option value="">Товар</option>{products.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><input name="quantity_delta" type="number" step="0.001" required placeholder="Изменение количества" /><input name="comment" required minLength={3} placeholder="Причина корректировки" /><button>Провести</button></form>
        <form onSubmit={move}><h3>Перемещение / выдача</h3><select name="operation"><option value="transfer">Склад → склад</option><option value="issue">Выдача представителю</option></select><select name="source_location_id" required><option value="">Источник</option>{warehouses.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><select name="destination_location_id" required><option value="">Получатель</option>{locations.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><select name="product_id" required><option value="">Товар</option>{products.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><input name="quantity" type="number" min="0.001" step="0.001" required placeholder="Количество" /><input name="comment" placeholder="Комментарий" /><button>Провести</button></form>
      </div></section>
    </>
  )
}
