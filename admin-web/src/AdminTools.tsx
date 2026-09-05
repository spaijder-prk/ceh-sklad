import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  DashboardData,
  UserRole,
  createProduct,
  createRepresentative,
  createUser,
  createWarehouse,
  issueToRepresentative,
  receiveGoods,
  registerPayment,
  transferBetweenWarehouses,
  updateProductPrices,
  updateRepresentativeUser,
} from "./api";

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  minimumFractionDigits: 2,
});

const number = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });

type Runner = (action: () => Promise<void>, success: string) => Promise<boolean>;

export function AdminTools({ data, onChanged }: { data: DashboardData; onChanged: () => Promise<void> }) {
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run: Runner = async (action, success) => {
    setBusy(true);
    setActionError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await onChanged();
      return true;
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Операция не выполнена");
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {(message || actionError) && (
        <div className={`alert ${actionError ? "error" : "success"}`}>
          {actionError || message}
        </div>
      )}

      <div className="section-heading">
        <div>
          <p className="eyebrow">Движение товара</p>
          <h2>Складские операции</h2>
          <p>Документы сразу проводят товар по регистру и обновляют текущие остатки.</p>
        </div>
      </div>
      <section className="admin-grid operations-grid">
        <ReceiptForm data={data} disabled={busy} run={run} />
        <IssueForm data={data} disabled={busy} run={run} />
        <TransferForm data={data} disabled={busy} run={run} />
        <PaymentForm data={data} disabled={busy} run={run} />
      </section>

      <div className="section-heading spaced-heading">
        <div>
          <p className="eyebrow">Доступ и цены</p>
          <h2>Учетные записи и прайс</h2>
          <p>Создание пользователей, привязка представителей и изменение действующих цен.</p>
        </div>
      </div>
      <section className="admin-grid">
        <UserForm disabled={busy} run={run} />
        <RepresentativeAccountForm data={data} disabled={busy} run={run} />
        <ProductPriceForm data={data} disabled={busy} run={run} />
      </section>

      <div className="section-heading spaced-heading">
        <div>
          <p className="eyebrow">Справочники</p>
          <h2>Настройка учета</h2>
          <p>Создание складов, товарных позиций и торговых представителей.</p>
        </div>
      </div>
      <section className="admin-grid">
        <WarehouseForm disabled={busy} run={run} />
        <ProductForm disabled={busy} run={run} />
        <RepresentativeForm data={data} disabled={busy} run={run} />
      </section>
    </>
  );
}

function ReceiptForm({ data, disabled, run }: CommonFormProps) {
  const [warehouseId, setWarehouseId] = useState(data.warehouses[0]?.id ?? "");
  const [productId, setProductId] = useState(data.products[0]?.id ?? "");
  const [quantity, setQuantity] = useState("");

  useFirstSelection(data.warehouses, warehouseId, setWarehouseId);
  useFirstSelection(data.products, productId, setProductId);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validQuantity(quantity)) return;
    const ok = await run(
      () => receiveGoods(warehouseId, productId, quantity),
      "Приход проведен",
    );
    if (ok) setQuantity("");
  };

  return (
    <FormCard title="Приход товара" subtitle="Зачислить товар на склад" onSubmit={submit} disabled={disabled || !warehouseId || !productId || !validQuantity(quantity)} submitLabel="Провести приход">
      <SelectField label="Склад" value={warehouseId} onChange={setWarehouseId} options={data.warehouses.map((row) => ({ value: row.id, label: `${row.name} · ${row.code}` }))} />
      <ProductSelect data={data} value={productId} onChange={setProductId} />
      <QuantityField value={quantity} onChange={setQuantity} />
    </FormCard>
  );
}

function IssueForm({ data, disabled, run }: CommonFormProps) {
  const [warehouseId, setWarehouseId] = useState(data.warehouses[0]?.id ?? "");
  const [representativeId, setRepresentativeId] = useState(data.representatives[0]?.id ?? "");
  const [productId, setProductId] = useState(data.products[0]?.id ?? "");
  const [quantity, setQuantity] = useState("");

  useFirstSelection(data.warehouses, warehouseId, setWarehouseId);
  useFirstSelection(data.representatives, representativeId, setRepresentativeId);
  useFirstSelection(data.products, productId, setProductId);

  const available = useMemo(
    () => warehouseQuantity(data, warehouseId, productId),
    [data, warehouseId, productId],
  );
  const quantityOk = validQuantity(quantity) && Number(normalizeDecimal(quantity)) <= available;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!quantityOk) return;
    const ok = await run(
      () => issueToRepresentative(warehouseId, representativeId, productId, quantity),
      "Товар выдан представителю",
    );
    if (ok) setQuantity("");
  };

  return (
    <FormCard title="Выдача представителю" subtitle="Списать со склада и поставить на остаток представителя" onSubmit={submit} disabled={disabled || !warehouseId || !representativeId || !productId || !quantityOk} submitLabel="Выдать товар">
      <SelectField label="Склад" value={warehouseId} onChange={setWarehouseId} options={data.warehouses.map((row) => ({ value: row.id, label: `${row.name} · ${row.code}` }))} />
      <SelectField label="Представитель" value={representativeId} onChange={setRepresentativeId} options={data.representatives.map((row) => ({ value: row.id, label: `${row.name} · ${row.code}` }))} />
      <ProductSelect data={data} value={productId} onChange={setProductId} />
      <QuantityField value={quantity} onChange={setQuantity} hint={`Доступно на складе: ${number.format(available)}`} error={quantity.length > 0 && !quantityOk ? "Количество превышает доступный остаток или имеет неверный формат" : undefined} />
    </FormCard>
  );
}

function TransferForm({ data, disabled, run }: CommonFormProps) {
  const [sourceId, setSourceId] = useState(data.warehouses[0]?.id ?? "");
  const [targetId, setTargetId] = useState(data.warehouses[1]?.id ?? data.warehouses[0]?.id ?? "");
  const [productId, setProductId] = useState(data.products[0]?.id ?? "");
  const [quantity, setQuantity] = useState("");

  useFirstSelection(data.warehouses, sourceId, setSourceId);
  useFirstSelection(data.products, productId, setProductId);

  useEffect(() => {
    if (sourceId && targetId === sourceId) {
      const alternative = data.warehouses.find((warehouse) => warehouse.id !== sourceId);
      if (alternative) setTargetId(alternative.id);
    }
  }, [data.warehouses, sourceId, targetId]);

  const available = useMemo(
    () => warehouseQuantity(data, sourceId, productId),
    [data, sourceId, productId],
  );
  const quantityOk = validQuantity(quantity) && Number(normalizeDecimal(quantity)) <= available;
  const differentWarehouses = Boolean(sourceId && targetId && sourceId !== targetId);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!quantityOk || !differentWarehouses) return;
    const ok = await run(
      () => transferBetweenWarehouses(sourceId, targetId, productId, quantity),
      "Перемещение проведено",
    );
    if (ok) setQuantity("");
  };

  return (
    <FormCard title="Перемещение" subtitle="Перенести товар между складами" onSubmit={submit} disabled={disabled || data.warehouses.length < 2 || !productId || !quantityOk || !differentWarehouses} submitLabel="Переместить">
      <SelectField label="Со склада" value={sourceId} onChange={setSourceId} options={data.warehouses.map((row) => ({ value: row.id, label: `${row.name} · ${row.code}` }))} />
      <SelectField label="На склад" value={targetId} onChange={setTargetId} options={data.warehouses.filter((row) => row.id !== sourceId).map((row) => ({ value: row.id, label: `${row.name} · ${row.code}` }))} />
      <ProductSelect data={data} value={productId} onChange={setProductId} />
      <QuantityField value={quantity} onChange={setQuantity} hint={`Доступно на складе-источнике: ${number.format(available)}`} error={quantity.length > 0 && !quantityOk ? "Количество превышает доступный остаток или имеет неверный формат" : undefined} />
      {data.warehouses.length < 2 && <div className="inline-warning">Для перемещения необходимо минимум два склада.</div>}
    </FormCard>
  );
}

function PaymentForm({ data, disabled, run }: CommonFormProps) {
  const [representativeId, setRepresentativeId] = useState(data.representatives[0]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  useFirstSelection(data.representatives, representativeId, setRepresentativeId);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validMoney(amount)) return;
    const ok = await run(
      () => registerPayment(representativeId, amount, comment),
      "Сдача денег зарегистрирована",
    );
    if (ok) {
      setAmount("");
      setComment("");
    }
  };

  return (
    <FormCard title="Сдача денег" subtitle="Уменьшить задолженность представителя" onSubmit={submit} disabled={disabled || !representativeId || !validMoney(amount)} submitLabel="Принять деньги">
      <SelectField label="Представитель" value={representativeId} onChange={setRepresentativeId} options={data.representatives.map((row) => ({ value: row.id, label: `${row.name} · долг ${money.format(data.debts[row.id] ?? 0)}` }))} />
      <label>Сумма<input required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0,00" /></label>
      <label>Комментарий<input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Номер квитанции или примечание" /></label>
    </FormCard>
  );
}

function UserForm({ disabled, run }: Pick<CommonFormProps, "disabled" | "run">) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("representative");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password.length < 8) return;
    const ok = await run(
      () => createUser({ email, password, fullName, role }),
      "Учетная запись создана",
    );
    if (ok) {
      setEmail("");
      setFullName("");
      setPassword("");
      setRole("representative");
    }
  };

  return (
    <FormCard title="Новая учетная запись" subtitle="Создать вход для представителя, руководителя или администратора" onSubmit={submit} disabled={disabled || password.length < 8} submitLabel="Создать пользователя">
      <label>ФИО<input required value={fullName} onChange={(event) => setFullName(event.target.value)} /></label>
      <label>Email<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
      <label>Роль<select value={role} onChange={(event) => setRole(event.target.value as UserRole)}><option value="representative">Торговый представитель</option><option value="manager">Руководитель</option><option value="admin">Администратор</option></select></label>
      <label>Временный пароль<input required minLength={8} type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /><small className="field-hint">Минимум 8 символов.</small></label>
    </FormCard>
  );
}

function RepresentativeAccountForm({ data, disabled, run }: CommonFormProps) {
  const [representativeId, setRepresentativeId] = useState(data.representatives[0]?.id ?? "");
  const [userId, setUserId] = useState("");
  useFirstSelection(data.representatives, representativeId, setRepresentativeId);

  const representative = data.representatives.find((row) => row.id === representativeId);
  useEffect(() => {
    setUserId(representative?.user_id ?? "");
  }, [representativeId, representative?.user_id]);

  const users = freeRepresentativeUsers(data, representativeId);
  const currentUser = data.users.find((user) => user.id === representative?.user_id);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const ok = await run(
      () => updateRepresentativeUser(representativeId, userId || null),
      userId ? "Учетная запись привязана" : "Привязка учетной записи снята",
    );
    if (ok && !userId) setUserId("");
  };

  return (
    <FormCard title="Доступ представителя" subtitle="Привязать или заменить учетную запись существующего представителя" onSubmit={submit} disabled={disabled || !representativeId} submitLabel="Сохранить привязку">
      <SelectField label="Представитель" value={representativeId} onChange={setRepresentativeId} options={data.representatives.map((row) => ({ value: row.id, label: `${row.name} · ${row.code}` }))} />
      <label>Учетная запись<select value={userId} onChange={(event) => setUserId(event.target.value)}><option value="">Без учетной записи</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>)}</select></label>
      <small className="field-hint">{currentUser ? `Сейчас: ${currentUser.email}` : "Сейчас вход для этого представителя не назначен."}</small>
      {users.length === 0 && !currentUser && <div className="inline-warning">Сначала создайте пользователя с ролью «Торговый представитель».</div>}
    </FormCard>
  );
}

function ProductPriceForm({ data, disabled, run }: CommonFormProps) {
  const [productId, setProductId] = useState(data.products[0]?.id ?? "");
  const [retailPrice, setRetailPrice] = useState("");
  const [wholesalePrice, setWholesalePrice] = useState("");
  useFirstSelection(data.products, productId, setProductId);

  const product = data.products.find((row) => row.id === productId);
  useEffect(() => {
    if (!product) {
      setRetailPrice("");
      setWholesalePrice("");
      return;
    }
    setRetailPrice(String(product.retail_price));
    setWholesalePrice(String(product.wholesale_price));
  }, [productId, product?.retail_price, product?.wholesale_price]);

  const pricesOk = validMoney(retailPrice, true) && validMoney(wholesalePrice, true);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!productId || !pricesOk) return;
    await run(
      () => updateProductPrices(productId, retailPrice, wholesalePrice),
      "Цены товара обновлены",
    );
  };

  return (
    <FormCard title="Изменение цен" subtitle="Обновить розничную и оптовую цену товара" onSubmit={submit} disabled={disabled || !productId || !pricesOk} submitLabel="Обновить цены">
      <ProductSelect data={data} value={productId} onChange={setProductId} />
      <label>Розничная цена<input required inputMode="decimal" value={retailPrice} onChange={(event) => setRetailPrice(event.target.value)} /></label>
      <label>Оптовая цена<input required inputMode="decimal" value={wholesalePrice} onChange={(event) => setWholesalePrice(event.target.value)} /></label>
      <small className="field-hint">Новые цены сразу становятся видны торговым представителям.</small>
    </FormCard>
  );
}

function WarehouseForm({ disabled, run }: Pick<CommonFormProps, "disabled" | "run">) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const ok = await run(() => createWarehouse(code, name), "Склад создан");
    if (ok) { setCode(""); setName(""); }
  };
  return <FormCard title="Новый склад" subtitle="Добавить склад в справочник" onSubmit={submit} disabled={disabled}><label>Код<input required value={code} onChange={(event) => setCode(event.target.value)} /></label><label>Название<input required value={name} onChange={(event) => setName(event.target.value)} /></label></FormCard>;
}

function ProductForm({ disabled, run }: Pick<CommonFormProps, "disabled" | "run">) {
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("шт");
  const [retailPrice, setRetailPrice] = useState("");
  const [wholesalePrice, setWholesalePrice] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const ok = await run(() => createProduct({ sku, name, unit, retailPrice, wholesalePrice }), "Товар создан");
    if (ok) { setSku(""); setName(""); setRetailPrice(""); setWholesalePrice(""); }
  };
  return <FormCard title="Новый товар" subtitle="Создать позицию и две цены" onSubmit={submit} disabled={disabled || !validMoney(retailPrice, true) || !validMoney(wholesalePrice, true)}><label>Артикул<input required value={sku} onChange={(event) => setSku(event.target.value)} /></label><label>Название<input required value={name} onChange={(event) => setName(event.target.value)} /></label><div className="form-row"><label>Единица<input required value={unit} onChange={(event) => setUnit(event.target.value)} /></label><label>Розница<input required inputMode="decimal" value={retailPrice} onChange={(event) => setRetailPrice(event.target.value)} /></label><label>Опт<input required inputMode="decimal" value={wholesalePrice} onChange={(event) => setWholesalePrice(event.target.value)} /></label></div></FormCard>;
}

function RepresentativeForm({ data, disabled, run }: CommonFormProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [userId, setUserId] = useState("");
  const availableUsers = freeRepresentativeUsers(data);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const ok = await run(
      () => createRepresentative(code, name, userId || undefined),
      "Представитель создан",
    );
    if (ok) {
      setCode("");
      setName("");
      setUserId("");
    }
  };

  return (
    <FormCard title="Новый представитель" subtitle="Создать карточку и при необходимости сразу назначить вход" onSubmit={submit} disabled={disabled}>
      <label>Код<input required value={code} onChange={(event) => setCode(event.target.value)} /></label>
      <label>Имя<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label>Учетная запись<select value={userId} onChange={(event) => setUserId(event.target.value)}><option value="">Назначить позже</option>{availableUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>)}</select></label>
    </FormCard>
  );
}

function ProductSelect({ data, value, onChange }: { data: DashboardData; value: string; onChange: (value: string) => void }) {
  return <SelectField label="Товар" value={value} onChange={onChange} options={data.products.map((product) => ({ value: product.id, label: `${product.name} · ${product.sku} · ${product.unit}` }))} />;
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: { value: string; label: string }[] }) {
  return <label>{label}<select required value={value} onChange={(event) => onChange(event.target.value)}>{options.length === 0 && <option value="">Нет доступных вариантов</option>}{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}

function QuantityField({ value, onChange, hint, error }: { value: string; onChange: (value: string) => void; hint?: string; error?: string }) {
  return <label>Количество<input required inputMode="decimal" value={value} onChange={(event) => onChange(event.target.value)} placeholder="0,000" />{hint && <small className="field-hint">{hint}</small>}{error && <small className="field-error">{error}</small>}</label>;
}

function FormCard({ title, subtitle, children, disabled, onSubmit, submitLabel = "Сохранить" }: { title: string; subtitle: string; children: React.ReactNode; disabled: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void; submitLabel?: string }) {
  return <form className="panel form-card" onSubmit={onSubmit}><div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div></div>{children}<button className="primary-button" disabled={disabled}>{disabled ? "Недоступно" : submitLabel}</button></form>;
}

interface CommonFormProps {
  data: DashboardData;
  disabled: boolean;
  run: Runner;
}

function warehouseQuantity(data: DashboardData, warehouseId: string, productId: string): number {
  const row = data.warehouseBalances.find(
    (balance) => balance.warehouse_id === warehouseId && balance.product_id === productId,
  );
  return Number(row?.quantity ?? 0);
}

function freeRepresentativeUsers(data: DashboardData, excludeRepresentativeId?: string) {
  const usedUserIds = new Set(
    data.representatives
      .filter((representative) => representative.id !== excludeRepresentativeId)
      .map((representative) => representative.user_id)
      .filter((userId): userId is string => Boolean(userId)),
  );
  return data.users.filter(
    (user) => user.role === "representative" && !usedUserIds.has(user.id),
  );
}

function validQuantity(value: string): boolean {
  const normalized = normalizeDecimal(value);
  if (!/^\d+(\.\d{1,3})?$/.test(normalized)) return false;
  return Number(normalized) > 0;
}

function validMoney(value: string, allowZero = false): boolean {
  const normalized = normalizeDecimal(value);
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return false;
  return allowZero ? Number(normalized) >= 0 : Number(normalized) > 0;
}

function normalizeDecimal(value: string): string {
  return value.trim().replace(",", ".");
}

function useFirstSelection<T extends { id: string }>(items: T[], value: string, setValue: (value: string) => void) {
  useEffect(() => {
    if (!value && items[0]) setValue(items[0].id);
    if (value && !items.some((item) => item.id === value)) setValue(items[0]?.id ?? "");
  }, [items, value, setValue]);
}
