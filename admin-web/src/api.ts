export type DecimalValue = string | number;
export type UserRole = "admin" | "manager" | "representative";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
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
  const [user, warehouses, products, representatives, warehouseBalances, representativeBalances] =
    await Promise.all([
      request<User>("/api/v1/auth/me"),
      request<Warehouse[]>("/api/v1/warehouses"),
      request<Product[]>("/api/v1/products"),
      request<Representative[]>("/api/v1/representatives"),
      request<WarehouseBalance[]>("/api/v1/balances/warehouses"),
      request<RepresentativeBalance[]>("/api/v1/balances/representatives"),
    ]);

  if (user.role === "representative") {
    throw new ApiError(403, "Веб-панель предназначена для администратора и руководителя");
  }

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
    warehouses,
    products,
    representatives,
    warehouseBalances,
    representativeBalances,
    debts,
  };
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
      retail_price: payload.retailPrice.replace(",", "."),
      wholesale_price: payload.wholesalePrice.replace(",", "."),
    }),
  });
}

export async function createRepresentative(code: string, name: string): Promise<void> {
  await request("/api/v1/representatives", {
    method: "POST",
    body: JSON.stringify({ code: code.trim(), name: name.trim() }),
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
      amount: amount.replace(",", "."),
      comment: comment.trim() || "Сдача денег через веб-панель",
      external_id: `web-payment-${crypto.randomUUID()}`,
    }),
  });
}
