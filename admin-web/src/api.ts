export type DecimalValue = string | number;
export type UserRole = "admin" | "manager" | "representative";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface UserAccess extends User {
  is_active: boolean;
}

export interface Warehouse {
  id: string;
  code: string;
  name: string;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  unit: string;
  retail_price: DecimalValue;
  wholesale_price: DecimalValue;
}

export interface Representative {
  id: string;
  code: string;
  name: string;
  user_id: string | null;
}

export interface WarehouseBalance {
  warehouse_id: string;
  warehouse_code: string;
  warehouse_name: string;
  product_id: string;
  sku: string;
  product_name: string;
  unit: string;
  retail_price: DecimalValue;
  wholesale_price: DecimalValue;
  quantity: DecimalValue;
}

export interface RepresentativeBalance {
  representative_id: string;
  representative_code: string;
  representative_name: string;
  product_id: string;
  sku: string;
  product_name: string;
  unit: string;
  retail_price: DecimalValue;
  wholesale_price: DecimalValue;
  quantity: DecimalValue;
}

export interface Debt {
  representative_id: string;
  debt: DecimalValue;
}

export interface DashboardData {
  user: User;
  users: User[];
  warehouses: Warehouse[];
  products: Product[];
  representatives: Representative[];
  warehouseBalances: WarehouseBalance[];
  representativeBalances: RepresentativeBalance[];
  debts: Record<string, number>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const TOKEN_KEY = "ceh-admin-access-token";

export function hasToken(): boolean {
  return Boolean(sessionStorage.getItem(TOKEN_KEY));
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function login(email: string, password: string): Promise<User> {
  const body = new URLSearchParams({ username: email.trim(), password });
  const response = await fetch("/api/v1/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Неверный email или пароль");
  }
  const payload = (await response.json()) as { access_token: string };
  sessionStorage.setItem(TOKEN_KEY, payload.access_token);
  try {
    return await request<User>("/api/v1/auth/me");
  } catch (error) {
    clearToken();
    throw error;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let message = `Ошибка сервера ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (data.detail) message = data.detail;
    } catch {
      // Ответ без JSON.
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function loadDashboard(): Promise<DashboardData> {
  const user = await request<User>("/api/v1/auth/me");
  if (user.role === "representative") {
    throw new ApiError(403, "Веб-панель предназначена для администратора и руководителя");
  }

  const [warehouses, products, representatives, warehouseBalances, representativeBalances, users] =
    await Promise.all([
      request<Warehouse[]>("/api/v1/warehouses"),
      request<Product[]>("/api/v1/products"),
      request<Representative[]>("/api/v1/representatives"),
      request<WarehouseBalance[]>("/api/v1/balances/warehouses"),
      request<RepresentativeBalance[]>("/api/v1/balances/representatives"),
      user.role === "admin" ? request<User[]>("/api/v1/users") : Promise.resolve([]),
    ]);

  const debtRows = await Promise.all(
    representatives.map((representative) =>
      request<Debt>(`/api/v1/representatives/${representative.id}/debt`),
    ),
  );
  const debts = Object.fromEntries(
    debtRows.map((row) => [row.representative_id, Number(row.debt)]),
  );

  return {
    user,
    users,
    warehouses,
    products,
    representatives,
    warehouseBalances,
    representativeBalances,
    debts,
  };
}

export async function loadUserAccess(): Promise<UserAccess[]> {
  return request<UserAccess[]>("/api/v1/users/access");
}

export async function updateUserAccess(
  userId: string,
  payload: { isActive?: boolean; newPassword?: string },
): Promise<UserAccess> {
  const body: { is_active?: boolean; new_password?: string } = {};
  if (payload.isActive !== undefined) body.is_active = payload.isActive;
  if (payload.newPassword !== undefined) body.new_password = payload.newPassword;
  return request<UserAccess>(`/api/v1/users/${userId}/access`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function createUser(payload: {
  email: string;
  password: string;
  fullName: string;
  role: UserRole;
}): Promise<void> {
  await request("/api/v1/users", {
    method: "POST",
    body: JSON.stringify({
      email: payload.email.trim(),
      password: payload.password,
      full_name: payload.fullName.trim(),
      role: payload.role,
    }),
  });
}

export async function createWarehouse(code: string, name: string): Promise<void> {
  await request("/api/v1/warehouses", {
    method: "POST",
    body: JSON.stringify({ code: code.trim(), name: name.trim() }),
  });
}

export async function createProduct(payload: {
  sku: string;
  name: string;
  unit: string;
  retailPrice: string;
  wholesalePrice: string;
}): Promise<void> {
  await request("/api/v1/products", {
    method: "POST",
    body: JSON.stringify({
      sku: payload.sku.trim(),
      name: payload.name.trim(),
      unit: payload.unit.trim(),
      retail_price: normalizeDecimal(payload.retailPrice),
      wholesale_price: normalizeDecimal(payload.wholesalePrice),
    }),
  });
}

export async function updateProductPrices(
  productId: string,
  retailPrice: string,
  wholesalePrice: string,
): Promise<void> {
  await request(`/api/v1/products/${productId}`, {
    method: "PATCH",
    body: JSON.stringify({
      retail_price: normalizeDecimal(retailPrice),
      wholesale_price: normalizeDecimal(wholesalePrice),
    }),
  });
}

export async function createRepresentative(
  code: string,
  name: string,
  userId?: string,
): Promise<void> {
  await request("/api/v1/representatives", {
    method: "POST",
    body: JSON.stringify({
      code: code.trim(),
      name: name.trim(),
      user_id: userId || null,
    }),
  });
}

export async function updateRepresentativeUser(
  representativeId: string,
  userId: string | null,
): Promise<void> {
  await request(`/api/v1/representatives/${representativeId}`, {
    method: "PATCH",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function registerPayment(
  representativeId: string,
  amount: string,
  comment: string,
): Promise<void> {
  await request("/api/v1/operations/payment", {
    method: "POST",
    body: JSON.stringify({
      representative_id: representativeId,
      amount: normalizeDecimal(amount),
      comment: comment.trim() || "Сдача денег через веб-панель",
      external_id: `web-payment-${crypto.randomUUID()}`,
    }),
  });
}

export async function receiveGoods(
  warehouseId: string,
  productId: string,
  quantity: string,
): Promise<void> {
  await request("/api/v1/operations/receipt", {
    method: "POST",
    body: JSON.stringify({
      warehouse_id: warehouseId,
      lines: [{ product_id: productId, quantity: normalizeDecimal(quantity) }],
      comment: "Приход через веб-панель",
      external_id: `web-receipt-${crypto.randomUUID()}`,
    }),
  });
}

export async function issueToRepresentative(
  warehouseId: string,
  representativeId: string,
  productId: string,
  quantity: string,
): Promise<void> {
  await request("/api/v1/operations/issue-to-representative", {
    method: "POST",
    body: JSON.stringify({
      warehouse_id: warehouseId,
      representative_id: representativeId,
      lines: [{ product_id: productId, quantity: normalizeDecimal(quantity) }],
      comment: "Выдача представителю через веб-панель",
      external_id: `web-issue-${crypto.randomUUID()}`,
    }),
  });
}

export async function transferBetweenWarehouses(
  sourceWarehouseId: string,
  targetWarehouseId: string,
  productId: string,
  quantity: string,
): Promise<void> {
  await request("/api/v1/operations/warehouse-transfer", {
    method: "POST",
    body: JSON.stringify({
      source_warehouse_id: sourceWarehouseId,
      target_warehouse_id: targetWarehouseId,
      lines: [{ product_id: productId, quantity: normalizeDecimal(quantity) }],
      comment: "Перемещение между складами через веб-панель",
      external_id: `web-transfer-${crypto.randomUUID()}`,
    }),
  });
}

function normalizeDecimal(value: string): string {
  return value.trim().replace(",", ".");
}
