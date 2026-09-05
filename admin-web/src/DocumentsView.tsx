import { useCallback, useEffect, useState } from "react";
import "./documents.css";

type DocumentType =
  | "receipt"
  | "issue_to_representative"
  | "representative_return"
  | "warehouse_transfer"
  | "sale"
  | "adjustment";
type DocumentStatus = "posted" | "cancelled";

interface DocumentLine {
  product_id: string;
  sku: string;
  product_name: string;
  warehouse_id: string | null;
  warehouse_name: string | null;
  representative_id: string | null;
  representative_name: string | null;
  quantity: string | number;
  unit_price: string | number | null;
}

interface StockDocument {
  id: string;
  document_type: DocumentType;
  status: DocumentStatus;
  external_id: string | null;
  comment: string | null;
  created_at: string;
  posted_at: string;
  sale_amount: string | number;
  lines: DocumentLine[];
}

const typeLabels: Record<DocumentType, string> = {
  receipt: "Приход",
  issue_to_representative: "Выдача представителю",
  representative_return: "Возврат от представителя",
  warehouse_transfer: "Перемещение",
  sale: "Продажа",
  adjustment: "Корректировка",
};
const number = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });
const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  minimumFractionDigits: 2,
});
const TOKEN_KEY = "ceh-admin-access-token";

export function DocumentsView({
  isAdmin,
  onChanged,
}: {
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}) {
  const [documents, setDocuments] = useState<StockDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await request<StockDocument[]>("/api/v1/documents?limit=100");
      setDocuments(rows);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить журнал документов");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const cancel = async (document: StockDocument) => {
    if (!window.confirm(`Сторнировать документ «${typeLabels[document.document_type]}»? Исходные проводки останутся в журнале.`)) {
      return;
    }
    setBusyId(document.id);
    setError(null);
    setMessage(null);
    try {
      await request(`/api/v1/documents/${document.id}/cancel`, { method: "POST" });
      setMessage("Документ сторнирован. Остатки и задолженность пересчитаны.");
      await Promise.all([load(), onChanged()]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сторнировать документ");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="panel">
      <div className="panel-heading document-heading">
        <div>
          <h2>Журнал документов</h2>
          <p>Последние 100 товарных документов. Сторно не удаляет исходные проводки.</p>
        </div>
        <button className="secondary-button" disabled={loading} onClick={() => void load()}>
          {loading ? "Загрузка…" : "Обновить журнал"}
        </button>
      </div>
      {message && <div className="alert success">{message}</div>}
      {error && <div className="alert error">{error}</div>}
      <div className="table-wrap">
        <table className="documents-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Документ</th>
              <th>Статус</th>
              <th>Состав</th>
              <th>Сумма продажи</th>
              <th>Комментарий</th>
              {isAdmin && <th>Действие</th>}
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.id}>
                <td>
                  <strong>{formatDate(document.posted_at)}</strong>
                  <small>{document.id.slice(0, 8)}</small>
                </td>
                <td><strong>{typeLabels[document.document_type]}</strong></td>
                <td>
                  <span className={`status ${document.status === "posted" ? "ok" : "cancelled"}`}>
                    {document.status === "posted" ? "проведен" : "сторнирован"}
                  </span>
                </td>
                <td className="document-lines">
                  {document.lines.map((line) => (
                    <span key={`${line.product_id}:${line.warehouse_id ?? line.representative_id}`}>
                      <strong>{line.product_name}</strong> · {formatSigned(line.quantity)} · {line.warehouse_name ?? line.representative_name ?? "—"}
                    </span>
                  ))}
                  {document.lines.length === 0 && <span>Нет товарных строк</span>}
                </td>
                <td>{Number(document.sale_amount) !== 0 ? money.format(Number(document.sale_amount)) : "—"}</td>
                <td className="document-comment">{document.comment || "—"}</td>
                {isAdmin && (
                  <td>
                    {document.status === "posted" ? (
                      <button
                        className="danger-button"
                        disabled={busyId === document.id}
                        onClick={() => void cancel(document)}
                      >
                        {busyId === document.id ? "Сторно…" : "Сторнировать"}
                      </button>
                    ) : (
                      <span className="muted-text">История сохранена</span>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!loading && documents.length === 0 && <div className="empty">Документов пока нет</div>}
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

function formatSigned(value: string | number): string {
  const numeric = Number(value);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${number.format(numeric)}`;
}
