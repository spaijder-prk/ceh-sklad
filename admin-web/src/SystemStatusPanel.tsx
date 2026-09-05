import { useEffect, useState } from 'react'

type User = { role: 'representative' | 'admin' | 'manager' }
type ApiError = { detail?: string }
type SystemStatus = {
  schema_revision: string
  temporarily_locked_users: number
  integration_1c_configured: boolean
  pending_1c_stock_documents: number
  pending_1c_cash_handovers: number
  failed_1c_last_24h: number
  oldest_pending_1c_at?: string | null
  unf_unmapped_products: number
  unf_unmapped_warehouses: number
  unf_unmapped_representatives: number
  unf_mapping_ready: boolean
}

const API = 'http://localhost:8000/api/v1'

async function request<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
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

function formatAge(value?: string | null) {
  if (!value) return 'нет очереди'
  const milliseconds = Date.now() - new Date(value).getTime()
  if (milliseconds <= 0) return 'только что'
  const minutes = Math.floor(milliseconds / 60_000)
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours} ч`
  return `${Math.floor(hours / 24)} дн`
}

export default function SystemStatusPanel() {
  const [token, setToken] = useState(() => localStorage.getItem('ceh-token') ?? '')
  const [role, setRole] = useState<User['role'] | null>(null)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [error, setError] = useState('')

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
      setStatus(null)
      setError('')
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const me = await request<User>('/auth/me', token)
        if (cancelled) return
        setRole(me.role)
        if (me.role === 'representative') {
          setStatus(null)
          return
        }
        const current = await request<SystemStatus>('/system/status', token)
        if (!cancelled) {
          setStatus(current)
          setError('')
        }
      } catch (e) {
        if (!cancelled) setError(String(e).replace('Error: ', ''))
      }
    })()
    return () => { cancelled = true }
  }, [token])

  if (!token || role == null || role === 'representative') return null

  return (
    <section className="panel">
      <div className="toolbar">
        <div>
          <p className="eyebrow">Эксплуатационный контроль</p>
          <h2>Состояние УНФ Cloud и системы</h2>
        </div>
        {status && <small>Схема БД: {status.schema_revision}</small>}
      </div>

      {error && <p className="message error">Не удалось получить системный статус: {error}</p>}
      {!status && !error && <p>Получение состояния…</p>}

      {status && <>
        <section className="metrics">
          <article>
            <span>Сопоставления УНФ</span>
            <strong>{status.unf_mapping_ready ? 'Готовы' : 'Не готовы'}</strong>
          </article>
          <article>
            <span>Документов ждут 1С</span>
            <strong>{status.pending_1c_stock_documents + status.pending_1c_cash_handovers}</strong>
          </article>
          <article>
            <span>Ошибок обмена за 24 ч</span>
            <strong>{status.failed_1c_last_24h}</strong>
          </article>
          <article>
            <span>Возраст старейшего</span>
            <strong>{formatAge(status.oldest_pending_1c_at)}</strong>
          </article>
        </section>

        <div className="table-wrap">
          <table>
            <thead><tr><th>Проверка</th><th>Состояние</th><th>Детали</th></tr></thead>
            <tbody>
              <tr>
                <td>Сервисный контур 1С</td>
                <td>{status.integration_1c_configured ? 'Настроен' : 'Не настроен'}</td>
                <td>{status.integration_1c_configured ? 'X-1C-Key задан на backend' : 'Обмен отключен до задания production secret'}</td>
              </tr>
              <tr>
                <td>Номенклатура УНФ</td>
                <td>{status.unf_unmapped_products === 0 ? 'Готово' : 'Требуется сопоставление'}</td>
                <td>Без external_1c_id: {status.unf_unmapped_products}</td>
              </tr>
              <tr>
                <td>Склады УНФ</td>
                <td>{status.unf_unmapped_warehouses === 0 ? 'Готово' : 'Требуется сопоставление'}</td>
                <td>Обычных складов без external_1c_id: {status.unf_unmapped_warehouses}</td>
              </tr>
              <tr>
                <td>Склады представителей</td>
                <td>{status.unf_unmapped_representatives === 0 ? 'Готово' : 'Требуется сопоставление'}</td>
                <td>Представителей без external_1c_id: {status.unf_unmapped_representatives}</td>
              </tr>
              <tr>
                <td>Временная блокировка входа</td>
                <td>{status.temporarily_locked_users === 0 ? 'Нет' : 'Есть'}</td>
                <td>Заблокировано учетных записей: {status.temporarily_locked_users}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </>}
    </section>
  )
}
