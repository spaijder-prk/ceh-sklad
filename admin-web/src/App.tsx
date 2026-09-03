import { useEffect, useMemo, useState } from 'react'

type Stock = {
  location_id: string
  location_name: string
  product_id: string
  sku: string
  product_name: string
  unit_name: string
  quantity: number
  retail_price: number
  wholesale_price: number
}

const API = 'http://localhost:8000/api/v1'

export default function App() {
  const [stocks, setStocks] = useState<Stock[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')

  async function load() {
    setError('')
    try {
      const response = await fetch(`${API}/stocks`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setStocks(await response.json())
    } catch (e) {
      setError(`Не удалось получить остатки: ${String(e)}`)
    }
  }

  useEffect(() => { void load() }, [])

  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return stocks
    return stocks.filter((item) =>
      `${item.product_name} ${item.sku} ${item.location_name}`.toLowerCase().includes(value),
    )
  }, [stocks, query])

  const totalPositions = new Set(stocks.map((item) => item.product_id)).size
  const warehouses = new Set(stocks.map((item) => item.location_id)).size

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Панель администратора / руководителя</p>
          <h1>Цех Склад</h1>
        </div>
        <button onClick={() => void load()}>Обновить</button>
      </header>

      <section className="metrics">
        <article><span>Товарных позиций</span><strong>{totalPositions}</strong></article>
        <article><span>Мест хранения</span><strong>{warehouses}</strong></article>
        <article><span>Строк остатков</span><strong>{stocks.length}</strong></article>
      </section>

      <section className="panel">
        <div className="toolbar">
          <h2>Остатки и цены</h2>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Товар, артикул или склад" />
        </div>
        {error && <p className="error">{error}</p>}
        <div className="table-wrap">
          <table>
            <thead><tr><th>Склад / представитель</th><th>Товар</th><th>Остаток</th><th>Розница</th><th>Опт</th></tr></thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={`${item.location_id}:${item.product_id}`}>
                  <td>{item.location_name}</td>
                  <td><b>{item.product_name}</b><small>{item.sku}</small></td>
                  <td>{item.quantity} {item.unit_name}</td>
                  <td>{item.retail_price}</td>
                  <td>{item.wholesale_price}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
