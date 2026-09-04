import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  DashboardData,
  clearToken,
  createProduct,
  createRepresentative,
  createWarehouse,
  hasToken,
  loadDashboard,
  login,
  registerPayment,
} from "./api";

type View = "overview" | "warehouses" | "catalog" | "representatives" | "admin";

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  minimumFractionDigits: 2,
});
const number = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [view, setView] = useState<View>("overview");
  const [loading, setLoading] = useState(hasToken());
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const next = await loadDashboard();
      setData(next);
      setError(null);
      setLastUpdated(new Date());
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Не удалось загрузить данные";
      setError(message);
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
        clearToken();
        setData(null);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (hasToken()) void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!data) return;
    const timer = window.setInterval(() => void refresh(true), 15_000);
    return () => window.clearInterval(timer);
  }, [data, refresh]);

  const onLoggedIn = async () => {
    setLoading(true);
    await refresh();
  };

  const logout = () => {
    clearToken();
    setData(null);
    setError(null);
    setView("overview");
  };

  if (!data) {
    return <LoginScreen loading={loading} error={error} onLoggedIn={onLoggedIn} />;
  }

  const isAdmin = data.user.role === "admin";
  if (!isAdmin && view === "admin") setView("overview");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">Ц</div>
          <div>
            <strong>Цех</strong>
            <span>складской учет</span>
          </div>
        </div>
        <nav className="nav">
          <NavButton active={view === "overview"} onClick={() => setView("overview")}>Обзор</NavButton>
          <NavButton active={view === "warehouses"} onClick={() => setView("warehouses")}>Склады</NavButton>
          <NavButton active={view === "catalog"} onClick={() => setView("catalog")}>Товары</NavButton>
          <NavButton active={view === "representatives"} onClick={() => setView("representatives")}>Представители</NavButton>
          {isAdmin && (
            <NavButton active={view === "admin"} onClick={() => setView("admin")}>Администрирование</NavButton>
          )}
        </nav>
        <div className="sidebar-footer">
          <span className="role-badge">{isAdmin ? "Администратор" : "Руководитель"}</span>
          <strong>{data.user.full_name}</strong>
          <span>{data.user.email}</span>
          <button className="ghost-button" onClick={logout}>Выйти</button>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Панель управления</p>
            <h1>{viewTitle(view)}</h1>
          </div>
          <div className="refresh-area">
            <span>{lastUpdated ? `Обновлено ${lastUpdated.toLocaleTimeString("ru-RU")}` : ""}</span>
            <span className="auto-refresh">Автообновление · 15 сек</span>
            <button className="secondary-button" disabled={loading} onClick={() => void refresh()}>
              {loading ? "Обновление…" : "Обновить"}
            </button>
          </div>
        </header>

        {error && <div className="alert error">{error}</div>}

        {view === "overview" && <Overview data={data} />}
        {view === "warehouses" && <Warehouses data={data} />}
        {view === "catalog" && <Catalog data={data} />}
        {view === "representatives" && <Representatives data={data} />}
        {view === "admin" && isAdmin && <AdminTools data={data} onChanged={() => refresh()} />}
      </main>
    </div>
  );
}

function LoginScreen({ loading, error, onLoggedIn }: { loading: boolean; error: string | null; onLoggedIn: () => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLocalError(null);
    try {
      const user = await login(email, password);
      if (user.role === "representative") {
        clearToken();
        throw new Error("Веб-панель предназначена для администратора и руководителя");
      }
      await onLoggedIn();
    } catch (caught) {
      setLocalError(caught instanceof Error ? caught.message : "Не удалось выполнить вход");
    }
  };

  return (
    <div className="login-page">
      <section className="login-intro">
        <div className="brand large"><div className="brand-mark">Ц</div><div><strong>Цех</strong><span>управление складом</span></div></div>
        <h1>Остатки, продажи и задолженность в одном окне.</h1>
        <p>Рабочее место администратора и руководителя. Данные загружаются напрямую из серверного регистра учета.</p>
        <div className="login-points"><span>Несколько складов</span><span>Розница и опт</span><span>Контроль представителей</span></div>
      </section>
      <form className="login-card" onSubmit={submit}>
        <p className="eyebrow">Авторизация</p>
        <h2>Вход в панель</h2>
        <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
        <label>Пароль<input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
        {(localError || error) && <div className="alert error">{localError || error}</div>}
        <button className="primary-button" disabled={loading}>{loading ? "Вход…" : "Войти"}</button>
        <small>Доступ разрешен ролям администратора и руководителя.</small>
      </form>
    </div>
  );
}

function Overview({ data }: { data: DashboardData }) {
  const stockRetail = data.warehouseBalances.reduce((sum, row) => sum + Number(row.quantity) * Number(row.retail_price), 0);
  const totalDebt = Object.values(data.debts).reduce((sum, value) => sum + value, 0);
  const debtRows = data.representatives
    .map((representative) => ({ ...representative, debt: data.debts[representative.id] ?? 0 }))
    .sort((a, b) => b.debt - a.debt)
    .slice(0, 6);

  const warehouseStats = data.warehouses.map((warehouse) => {
    const rows = data.warehouseBalances.filter((row) => row.warehouse_id === warehouse.id);
    return {
      ...warehouse,
      positions: rows.length,
      value: rows.reduce((sum, row) => sum + Number(row.quantity) * Number(row.retail_price), 0),
    };
  });

  return (
    <>
      <section className="kpi-grid">
        <Kpi label="Складов" value={String(data.warehouses.length)} hint={`${data.warehouseBalances.length} позиций с остатком`} />
        <Kpi label="Товаров" value={String(data.products.length)} hint="активный каталог" />
        <Kpi label="Остаток по рознице" value={money.format(stockRetail)} hint="оценка текущего склада" />
        <Kpi label="Долг представителей" value={money.format(totalDebt)} hint={`${data.representatives.length} представителей`} danger={totalDebt > 0} />
      </section>

      <section className="two-column">
        <Panel title="Склады" subtitle="Розничная оценка текущих остатков">
          <div className="stack-list">
            {warehouseStats.map((warehouse) => (
              <div className="stack-row" key={warehouse.id}>
                <div><strong>{warehouse.name}</strong><span>{warehouse.code} · {warehouse.positions} позиций</span></div>
                <strong>{money.format(warehouse.value)}</strong>
              </div>
            ))}
            {warehouseStats.length === 0 && <Empty text="Склады еще не созданы" />}
          </div>
        </Panel>
        <Panel title="Задолженность" subtitle="Представители с наибольшей текущей задолженностью">
          <div className="stack-list">
            {debtRows.map((representative) => (
              <div className="stack-row" key={representative.id}>
                <div><strong>{representative.name}</strong><span>{representative.code}</span></div>
                <strong className={representative.debt > 0 ? "danger-text" : ""}>{money.format(representative.debt)}</strong>
              </div>
            ))}
            {debtRows.length === 0 && <Empty text="Представителей еще нет" />}
          </div>
        </Panel>
      </section>
    </>
  );
}

function Warehouses({ data }: { data: DashboardData }) {
  return (
    <Panel title="Остатки по складам" subtitle="Количество и две действующие цены для каждой позиции">
      <div className="table-wrap"><table><thead><tr><th>Склад</th><th>Артикул</th><th>Товар</th><th>Остаток</th><th>Розница</th><th>Опт</th></tr></thead><tbody>
        {data.warehouseBalances.map((row) => <tr key={`${row.warehouse_id}:${row.product_id}`}><td><strong>{row.warehouse_name}</strong><small>{row.warehouse_code}</small></td><td>{row.sku}</td><td>{row.product_name}</td><td>{number.format(Number(row.quantity))} {row.unit}</td><td>{money.format(Number(row.retail_price))}</td><td>{money.format(Number(row.wholesale_price))}</td></tr>)}
      </tbody></table></div>
      {data.warehouseBalances.length === 0 && <Empty text="На складах нет текущих остатков" />}
    </Panel>
  );
}

function Catalog({ data }: { data: DashboardData }) {
  return <Panel title="Каталог товаров" subtitle="Актуальные розничные и оптовые цены"><div className="table-wrap"><table><thead><tr><th>Артикул</th><th>Наименование</th><th>Ед.</th><th>Розница</th><th>Опт</th></tr></thead><tbody>{data.products.map((product) => <tr key={product.id}><td>{product.sku}</td><td><strong>{product.name}</strong></td><td>{product.unit}</td><td>{money.format(Number(product.retail_price))}</td><td>{money.format(Number(product.wholesale_price))}</td></tr>)}</tbody></table></div>{data.products.length === 0 && <Empty text="Каталог пуст" />}</Panel>;
}

function Representatives({ data }: { data: DashboardData }) {
  return <Panel title="Торговые представители" subtitle="Товар на руках и текущая задолженность"><div className="table-wrap"><table><thead><tr><th>Код</th><th>Представитель</th><th>Позиций</th><th>Количество</th><th>Задолженность</th><th>Учетная запись</th></tr></thead><tbody>{data.representatives.map((representative) => {
    const rows = data.representativeBalances.filter((row) => row.representative_id === representative.id);
    const quantity = rows.reduce((sum, row) => sum + Number(row.quantity), 0);
    const debt = data.debts[representative.id] ?? 0;
    return <tr key={representative.id}><td>{representative.code}</td><td><strong>{representative.name}</strong></td><td>{rows.length}</td><td>{number.format(quantity)}</td><td className={debt > 0 ? "danger-text" : ""}>{money.format(debt)}</td><td>{representative.user_id ? <span className="status ok">привязана</span> : <span className="status muted">не привязана</span>}</td></tr>;
  })}</tbody></table></div>{data.representatives.length === 0 && <Empty text="Представителей нет" />}</Panel>;
}

function AdminTools({ data, onChanged }: { data: DashboardData; onChanged: () => Promise<void> }) {
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<void>, success: string) => {
    setBusy(true); setActionError(null); setMessage(null);
    try { await action(); setMessage(success); await onChanged(); }
    catch (caught) { setActionError(caught instanceof Error ? caught.message : "Операция не выполнена"); }
    finally { setBusy(false); }
  };

  return <>
    {(message || actionError) && <div className={`alert ${actionError ? "error" : "success"}`}>{actionError || message}</div>}
    <section className="admin-grid">
      <WarehouseForm disabled={busy} onSubmit={(code, name) => run(() => createWarehouse(code, name), "Склад создан")} />
      <ProductForm disabled={busy} onSubmit={(payload) => run(() => createProduct(payload), "Товар создан")} />
      <RepresentativeForm disabled={busy} onSubmit={(code, name) => run(() => createRepresentative(code, name), "Представитель создан")} />
      <PaymentForm data={data} disabled={busy} onSubmit={(id, amount, comment) => run(() => registerPayment(id, amount, comment), "Сдача денег зарегистрирована")} />
    </section>
  </>;
}

function WarehouseForm({ disabled, onSubmit }: { disabled: boolean; onSubmit: (code: string, name: string) => Promise<void> }) {
  const [code, setCode] = useState(""); const [name, setName] = useState("");
  return <FormCard title="Новый склад" subtitle="Добавить склад в справочник" onSubmit={async (e) => { e.preventDefault(); await onSubmit(code, name); setCode(""); setName(""); }} disabled={disabled}><label>Код<input required value={code} onChange={(e) => setCode(e.target.value)} /></label><label>Название<input required value={name} onChange={(e) => setName(e.target.value)} /></label></FormCard>;
}

function ProductForm({ disabled, onSubmit }: { disabled: boolean; onSubmit: (payload: { sku: string; name: string; unit: string; retailPrice: string; wholesalePrice: string }) => Promise<void> }) {
  const [sku, setSku] = useState(""); const [name, setName] = useState(""); const [unit, setUnit] = useState("шт"); const [retailPrice, setRetailPrice] = useState(""); const [wholesalePrice, setWholesalePrice] = useState("");
  return <FormCard title="Новый товар" subtitle="Создать позицию и две цены" onSubmit={async (e) => { e.preventDefault(); await onSubmit({ sku, name, unit, retailPrice, wholesalePrice }); setSku(""); setName(""); setRetailPrice(""); setWholesalePrice(""); }} disabled={disabled}><label>Артикул<input required value={sku} onChange={(e) => setSku(e.target.value)} /></label><label>Название<input required value={name} onChange={(e) => setName(e.target.value)} /></label><div className="form-row"><label>Единица<input required value={unit} onChange={(e) => setUnit(e.target.value)} /></label><label>Розница<input required inputMode="decimal" value={retailPrice} onChange={(e) => setRetailPrice(e.target.value)} /></label><label>Опт<input required inputMode="decimal" value={wholesalePrice} onChange={(e) => setWholesalePrice(e.target.value)} /></label></div></FormCard>;
}

function RepresentativeForm({ disabled, onSubmit }: { disabled: boolean; onSubmit: (code: string, name: string) => Promise<void> }) {
  const [code, setCode] = useState(""); const [name, setName] = useState("");
  return <FormCard title="Новый представитель" subtitle="Создать карточку представителя" onSubmit={async (e) => { e.preventDefault(); await onSubmit(code, name); setCode(""); setName(""); }} disabled={disabled}><label>Код<input required value={code} onChange={(e) => setCode(e.target.value)} /></label><label>Имя<input required value={name} onChange={(e) => setName(e.target.value)} /></label></FormCard>;
}

function PaymentForm({ data, disabled, onSubmit }: { data: DashboardData; disabled: boolean; onSubmit: (id: string, amount: string, comment: string) => Promise<void> }) {
  const [id, setId] = useState(data.representatives[0]?.id ?? ""); const [amount, setAmount] = useState(""); const [comment, setComment] = useState("");
  useEffect(() => { if (!id && data.representatives[0]) setId(data.representatives[0].id); }, [data.representatives, id]);
  return <FormCard title="Сдача денег" subtitle="Уменьшить задолженность представителя" onSubmit={async (e) => { e.preventDefault(); await onSubmit(id, amount, comment); setAmount(""); setComment(""); }} disabled={disabled || !id}><label>Представитель<select required value={id} onChange={(e) => setId(e.target.value)}>{data.representatives.map((representative) => <option key={representative.id} value={representative.id}>{representative.name} · {money.format(data.debts[representative.id] ?? 0)}</option>)}</select></label><label>Сумма<input required inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label><label>Комментарий<input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Номер квитанции или примечание" /></label></FormCard>;
}

function FormCard({ title, subtitle, children, disabled, onSubmit }: { title: string; subtitle: string; children: React.ReactNode; disabled: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return <form className="panel form-card" onSubmit={onSubmit}><div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div></div>{children}<button className="primary-button" disabled={disabled}>{disabled ? "Выполнение…" : "Сохранить"}</button></form>;
}

function Kpi({ label, value, hint, danger = false }: { label: string; value: string; hint: string; danger?: boolean }) {
  return <article className="kpi"><span>{label}</span><strong className={danger ? "danger-text" : ""}>{value}</strong><small>{hint}</small></article>;
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="panel"><div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div></div>{children}</section>;
}

function Empty({ text }: { text: string }) { return <div className="empty">{text}</div>; }
function NavButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) { return <button className={active ? "active" : ""} onClick={onClick}>{children}</button>; }
function viewTitle(view: View): string { return ({ overview: "Обзор", warehouses: "Склады и остатки", catalog: "Каталог товаров", representatives: "Торговые представители", admin: "Администрирование" })[view]; }
