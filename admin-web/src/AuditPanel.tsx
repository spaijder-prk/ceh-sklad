import { useEffect, useState } from 'react'

type User = { role: 'representative' | 'admin' | 'manager' }
type AuditRow = {
  id: string
  actor_type: string
  user_name?: string | null
  method: string
  path: string
  status_code: number
  created_at: string
}

const API = 'http://localhost:8000/api/v1'

function actorLabel(row: AuditRow) {
  if (row.actor_type === '1c') return '1С'
  if (row.actor_type === 'user') return row.user_name ?? 'Пользователь'
  if (row.actor_type === 'invalid_token') return 'Недействительный токен'
  return 'Без авторизации'
}

export default function AuditPanel() {
  const [token, setToken] = useState(() => localStorage.getItem('ceh-token') ?? '')
  const [rows, setRows] = useState<AuditRow[]>([])
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const timer = window.setInterval(() => {
      const actual = localStorage.getItem('ceh-token') ?? ''
      setToken((current) => current === actual ? current : actual)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!token) {
      setVisible(false)
      setRows([])
      return
    }

    let cancelled = false
    const headers = { Authorization: `Bearer ${token}` }

    async function load() {
      try {
        const meResponse = await fetch(`${API}/auth/me`, { headers })
        if (!meResponse.ok) return
        const me = await meResponse.json() as User
        if (me.role !== 'admin' && me.role !== 'manager') {
          if (!cancelled) setVisible(false)
          return
        }
        const response = await fetch(`${API}/admin/audit?limit=100`, { headers })
        if (!response.ok) return
        const data = await response.json() as AuditRow[]
        if (!cancelled) {
          setRows(data)
          setVisible(true)
        }
      } catch {
        // Основная панель самостоятельно показывает сетевые ошибки; аудит не должен мешать ей работать.
      }
    }

    void load()
    const timer = window.setInterval(() => void load(), 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [token])

  if (!visible) return null

  return (
    <main className="audit-extension">
      <section className="panel">
        <div className="toolbar"><h2>Аудит изменяющих запросов</h2><small>Тела запросов, пароли, JWT и ключи 1С не сохраняются</small></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Дата</th><th>Кто</th><th>Метод</th><th>Операция</th><th>Результат</th></tr></thead>
            <tbody>{rows.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.created_at).toLocaleString('ru-RU')}</td>
                <td>{actorLabel(row)}</td>
                <td>{row.method}</td>
                <td>{row.path}</td>
                <td>{row.status_code}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
