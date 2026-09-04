# Цех — учет складских остатков

Система учета продукции на нескольких складах и у торговых представителей.

## Уже реализовано

- несколько складов и торговых представителей;
- товары с розничной и оптовой ценой;
- приход товара;
- выдача товара торговому представителю;
- перемещение между складами;
- возврат от торгового представителя;
- продажа с фиксацией цены на момент операции;
- сдача денег и расчет задолженности представителя;
- журнал товарных и денежных проводок;
- идемпотентность операций через `external_id` для будущей интеграции с 1С;
- JWT-аутентификация;
- роли `representative`, `admin`, `manager`;
- Alembic-миграции;
- PostgreSQL через Docker Compose.

## Структура репозитория

- `backend/` — FastAPI, SQLAlchemy, Alembic и бизнес-логика;
- `android/` — Android-приложение торгового представителя, следующий этап;
- `admin-web/` — панель администратора и руководителя, следующий этап;
- `docs/` — архитектура и правила учета.

## Запуск

```bash
docker compose up
```

Контейнер backend автоматически выполняет `alembic upgrade head`, после чего запускает API.

После запуска доступны:

- API: `http://localhost:8000`;
- Swagger UI: `http://localhost:8000/docs`;
- проверка состояния: `http://localhost:8000/health`.

## Первый администратор

В новой базе один раз вызовите:

```http
POST /api/v1/auth/bootstrap
Content-Type: application/json

{
  "email": "admin@example.local",
  "password": "replace-with-strong-password",
  "full_name": "Администратор"
}
```

После создания первого пользователя bootstrap автоматически перестает принимать новые запросы.

Токен выдается маршрутом `POST /api/v1/auth/token`. Он использует стандартную OAuth2-форму: поле `username` содержит email, поле `password` — пароль. В Swagger UI можно авторизоваться кнопкой **Authorize**.

## Роли

- `admin` — управление справочниками, пользователями и учетными операциями;
- `manager` — просмотр складов, товаров, остатков и задолженности;
- `representative` — просмотр складских остатков и цен, просмотр только собственных остатков/задолженности, регистрация собственных продаж и возвратов.

Сдача денег фиксируется администратором: представитель не может самостоятельно уменьшить свою задолженность.

## Основные API

Справочники:

- `GET/POST /api/v1/warehouses`;
- `GET/POST /api/v1/representatives`;
- `GET/POST /api/v1/products`;
- `GET/POST /api/v1/users`.

Остатки и задолженность:

- `GET /api/v1/balances/warehouses`;
- `GET /api/v1/balances/representatives`;
- `GET /api/v1/representatives/{id}/debt`.

Операции:

- `POST /api/v1/operations/receipt`;
- `POST /api/v1/operations/issue-to-representative`;
- `POST /api/v1/operations/warehouse-transfer`;
- `POST /api/v1/operations/representative-return`;
- `POST /api/v1/operations/sale`;
- `POST /api/v1/operations/payment`.

## Локальный запуск без Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

На Windows команда активации окружения: `.venv\\Scripts\\activate`.

Если переменная `CEH_DATABASE_URL` не задана, для быстрого локального запуска используется SQLite.

## Принцип учета

Остатки не редактируются напрямую. Каждая операция создает документ и товарные проводки. Текущий остаток вычисляется как сумма проводок, поэтому история движения сохраняется полностью.

Продажа увеличивает задолженность представителя перед компанией, сдача денег уменьшает ее. Подробности описаны в `docs/domain-model.md`.

## Следующий этап

- конкурентно-безопасный регистр текущих остатков;
- WebSocket-обновления остатков в реальном времени;
- тесты API и CI;
- Android-клиент;
- веб-панель администратора и руководителя;
- полноценный контур обмена с 1С.
