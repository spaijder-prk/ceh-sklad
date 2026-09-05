import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { REALTIME_CHANGE_EVENT } from "./realtime";
import "./reports.css";

type DecimalValue = string | number;

interface ReportSummary {
  date_from: string | null;
  date_to: string | null;
  sales_amount: DecimalValue;
  sales_documents: number;
  payments_amount: DecimalValue;
  current_debt: DecimalValue;
  warehouse_retail_value: DecimalValue;
  representative_stock_retail_value: DecimalValue;
}

interface RepresentativeReportLine {
  representative_id: string;
  representative_code: string;
  representative_name: string;
  sales_amount: DecimalValue;
  sales_documents: number;
  payments_amount: DecimalValue;
  current_debt: DecimalValue;
  stock_positions: number;
  stock_retail_value: DecimalValue;
}

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  minimumFractionDigits: 2,
});
const TOKEN_KEY = "ceh-admin-access-token";

export function ReportsView() {
  const today = useMemo(() => localDate(new Date()), []);
  const monthStart = useMemo(() => {
    const now = new Date();
    return localDate(new Date(now.getFullYear(), now.getMonth(), 1));
  }, []);
  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo, setDateTo] = useState(today);
  const [appliedFrom, setAppliedFrom] = useState(monthStart);
  const [appliedTo, setAppliedTo] = useState(today);
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [representatives, setRepresentatives] = useState<RepresentativeReportLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (from: string, to: string) => {
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams();
      if (from) query.set("date_from", from);
      if (to) query.set("date_to", to);
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const [summaryRow, representativeRows] = await Promise.all([
        request<ReportSummary>(`/api/v1/reports/summary${suffix}`),
        request<RepresentativeReportLine[]>(`/api/v1/reports/representatives${suffix}`),
      ]);
      setSummary(summaryRow);
      setRepresentatives(
        [...representativeRows].sort(
          (left, right) => Number(right.sales_amount) - Number(left.sales_amount),
        ),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить отчет");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(appliedFrom, appliedTo);
    const onRealtimeChange = () => void load(appliedFrom, appliedTo);
    window.addEventListener(REALTIME_CHANGE_EVENT, onRealtimeChange);
    const timer = window.setInterval(() => void load(appliedFrom, appliedTo), 60_000);
    return () => {
      window.removeEventListener(REALTIME_CHANGE_EVENT, onRealtimeChange);
      window.clearInterval(timer);
    };
  }, [appliedFrom, appliedTo, load]);

  const applyPeriod = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (dateFrom && dateTo && dateFrom > dateTo) {
      setError("Дата начала периода не может быть позже даты окончания");
      return;
    }
    setAppliedFrom(dateFrom);
    setAppliedTo(dateTo);
  };

  const showAllTime = () => {
    setDateFrom("");
    setDateTo("");
    setAppliedFrom("");
    setAppliedTo("");
  };

  const maxSales = Math.max(0, ...representatives.map((row) => Number(row.sales_amount)));

  return (
    <>
      <section className="panel report-filter-panel">
        <div className="panel-heading report-heading">
          <div>
            <h2>Период отчета</h2>
            <p>Продажи и принятые деньги считаются за выбранный период; долг и остатки показываются на текущий момент.</p>
          </div>
        </div>
        <form className="report-filter" onSubmit={applyPeriod}>
          <label>С даты<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
          <label>По дату<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
          <button className="primary-button" disabled={loading}>{loading ? "Расчет…" : "Показать"}</button>
          <button className="secondary-button" type="button" disabled={loading} onClick={showAllTime}>За всё время</button>
        </form>
        {error && <div className="alert error">{error}</div>}
      </section>

      {summary && (
        <section className="report-kpi-grid">
          <ReportKpi label="Продажи за период" value={money.format(Number(summary.sales_amount))} hint={`${summary.sales_documents} документов`} />
          <ReportKpi label="Принято денег" value={money.format(Number(summary.payments_amount))} hint="сдача денег за период" />
          <ReportKpi label="Текущий долг" value={money.format(Number(summary.current_debt))} hint="по всем представителям" danger={Number(summary.current_debt) > 0} />
          <ReportKpi label="Товар на складах" value={money.format(Number(summary.warehouse_retail_value))} hint="оценка по розничным ценам" />
          <ReportKpi label="Товар у представителей" value={money.format(Number(summary.representative_stock_retail_value))} hint="текущий остаток по рознице" />
        </section>
      )}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Эффективность представителей</h2>
            <p>Оборот и принятые деньги за период, текущая задолженность и товар на руках.</p>
          </div>
        </div>
        <div className="table-wrap">
          <table className="reports-table">
            <thead>
              <tr>
                <th>Представитель</th>
                <th>Продажи</th>
                <th>Документов</th>
                <th>Принято денег</th>
                <th>Текущий долг</th>
                <th>Товар на руках</th>
                <th>Позиций</th>
              </tr>
            </thead>
            <tbody>
              {representatives.map((row) => (
                <tr key={row.representative_id}>
                  <td><strong>{row.representative_name}</strong><small>{row.representative_code}</small></td>
                  <td className="sales-cell">
                    <strong>{money.format(Number(row.sales_amount))}</strong>
                    <span className="sales-bar"><i style={{ width: maxSales > 0 ? `${Math.max(3, Number(row.sales_amount) / maxSales * 100)}%` : "0%" }} /></span>
                  </td>
                  <td>{row.sales_documents}</td>
                  <td>{money.format(Number(row.payments_amount))}</td>
                  <td className={Number(row.current_debt) > 0 ? "danger-text" : ""}>{money.format(Number(row.current_debt))}</td>
                  <td>{money.format(Number(row.stock_retail_value))}</td>
                  <td>{row.stock_positions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && representatives.length === 0 && <div className="empty">Представителей пока нет</div>}
      </section>
    </>
  );
}

function ReportKpi({ label, value, hint, danger = false }: { label: string; value: string; hint: string; danger?: boolean }) {
  return (
    <article className="kpi report-kpi">
      <span>{label}</span>
      <strong className={danger ? "danger-text" : ""}>{value}</strong>
      <small>{hint}</small>
    </article>
  );
}

async function request<T>(path: string): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { headers });
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
  return (await response.json()) as T;
}

function localDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
