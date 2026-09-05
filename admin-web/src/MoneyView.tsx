import { useCallback, useEffect, useMemo, useState } from "react";
import "./money.css";

type MoneyOperation = "sale" | "payment" | "adjustment";
type DecimalValue = string | number;

interface MoneyPosting {
  id: string;
  representative_id: string;
  representative_code: string;
  representative_name: string;
  document_id: string | null;
  operation: MoneyOperation;
  amount: DecimalValue;
  comment: string | null;
  external_id: string | null;
  created_by_user_id: string | null;
  created_by_name: string | null;
  created_at: string;
  reversed: boolean;
  reversed_by_user_id: string | null;
  reversed_by_name: string | null;
  reversed_at: string | null;
}

const operationLabels: Record<MoneyOperation, string> = {
  sale: "Продажа",
  payment: "Сдача денег",
  adjustment: "Корректировка",
};
const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  minimumFractionDigits: 2,
});
const TOKEN_KEY = "ceh-admin-access-token";

export function MoneyView({
  isAdmin,
  onChanged,
}: {
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}) {
  const [rows, setRows] = useState<MoneyPosting[]>([]);
  const [operation, setOperation] = useState<"all" | MoneyOperation>("all");
  const [representativeId, setRepresentativeId] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await request<MoneyPosting[]>("/api/v1/money-postings?limit=100"));
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить денежный журнал");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const representatives = useMemo(() => {
    const unique = new Map<string, { id: string; name: string; code: string }>();
    rows.forEach((row) => unique.set(row.representative_id, {
      id: row.representative_id,
      name: row.representative_name,
      code: row.representative_code,
    }));
    return [...unique.values()].sort((left, right) => left.name.localeCompare(right.name, "ru"));
  }, [rows]);

  const filtered = rows.filter(
    (row) =>
      (operation === "all" || row.operation === operation) &&
      (representativeId === "all" || row.representative_id === representativeId),
  );

  const periodEffect = filtered.reduce((sum, row) => sum + Number(row.amount), 0);

  const reverse = async (row: MoneyPosting) => {
    if (!window.confirm(`Сторнировать сдачу денег ${money.format(Math.abs(Number(row.amount)))} от ${row.representative_name}?`)) {
      return;
    }
    setBusyId(row.id);
    setMessage(null);
    setError(null);
    try {
      await request(`/api/v1/money-postings/${row.id}/reverse`, { method: "POST" });
      setMessage("Сдача денег сторнирована. Задолженность восстановлена компенсирующей проводкой.");
      await Promise.all([load(), onChanged()]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сторнировать сдачу денег");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="panel">
      <div className="panel-heading money-heading">
        <div>
          <h2>Денежный журнал</h2>
          <p>Последние 100 движений задолженности с аудитом создания и сторно.</p>
        </div>
        <button className="secondary-button" disabled={loading} onClick={() => void load()}>
          {loading ? "Загрузка…" : "Обновить журнал"}
        </button>
      </div>

      <div className="money-toolbar">
        <label>Операция<select value={operation} onChange={(event) => setOperation(event.target.value as "all" | MoneyOperation)}><option value="all">Все операции</option><option value="sale">Продажи</option><option value="payment">Сдача денег</option><option value="adjustment">Корректировки</option></select></label>
        <label>Представитель<select value={representativeId} onChange={(event) => setRepresentativeId(event.target.value)}><option value="all">Все представители</option>{representatives.map((representative) => <option key={representative.id} value={representative.id}>{representative.name} · {representative.code}</option>)}</select></label>
        <div className="money-effect"><span>Изменение долга по выборке</span><strong className={periodEffect > 0 ? "danger-text" : periodEffect < 0 ? "positive-text" : ""}>{formatSignedMoney(periodEffect)}</strong></div>
      </div>

      {message && <div className="alert success">{message}</div>}
      {error && <div className="alert error">{error}</div>}

      <div className="table-wrap">
        <table className="money-table">
          <thead><tr><th>Дата</th><th>Представитель</th><th>Операция</th><th>Изменение долга</th><th>Автор</th><th>Статус</th><th>Комментарий</th>{isAdmin && <th>Действие</th>}</tr></thead>
          <tbody>
            {filtered.map((row) => {
              const amount = Number(row.amount);
              return (
                <tr key={row.id}>
                  <td><strong>{formatDate(row.created_at)}</strong><small>{row.id.slice(0, 8)}</small></td>
                  <td><strong>{row.representative_name}</strong><small>{row.representative_code}</small></td>
                  <td>{operationLabels[row.operation]}</td>
                  <td className={amount > 0 ? "danger-text" : amount < 0 ? "positive-text" : ""}><strong>{formatSignedMoney(amount)}</strong></td>
                  <td><strong>{row.created_by_name || integrationAuthor(row.external_id)}</strong>{row.created_by_user_id && <small>{row.created_by_user_id.slice(0, 8)}</small>}</td>
                  <td>
                    {row.reversed ? <span className="status cancelled">сторнирована</span> : <span className="status ok">учтена</span>}
                    {row.reversed_at && <small>{formatDate(row.reversed_at)} · {row.reversed_by_name || "автор не зафиксирован"}</small>}
                  </td>
                  <td className="money-comment">{row.comment || "—"}</td>
                  {isAdmin && <td>{row.operation === "payment" && !row.reversed ? <button className="danger-button" disabled={busyId === row.id} onClick={() => void reverse(row)}>{busyId === row.id ? "Сторно…" : "Сторнировать"}</button> : <span className="muted-text">—</span>}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!loading && filtered.length === 0 && <div className="empty">Нет денежных операций по выбранному фильтру</div>}
    </section>
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let message = `Ошибка сервера ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Ответ сервера не содержит JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function formatSignedMoney(value: number): string {
  if (value > 0) return `+${money.format(value)}`;
  return money.format(value);
}

function integrationAuthor(externalId: string | null): string {
  return externalId?.startsWith("1c:") ? "1С" : "Не зафиксирован";
}
