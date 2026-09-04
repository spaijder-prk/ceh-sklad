# Цех — учет складских остатков

Система учета продукции на нескольких складах и у торговых представителей.

## Возможности первой версии

- остатки по нескольким складам;
- розничная и оптовая цена товара;
- выдача товара торговому представителю;
- продажа и списание товара с остатка представителя;
- учет задолженности и сдачи денег;
- возврат товара от представителя;
- перемещение товара между складами;
- роли: торговый представитель, администратор, руководитель;
- журнал движений товара и денег;
- основа для интеграции с 1С через `external_id`.

## Структура репозитория

- `backend/` — FastAPI, SQLAlchemy, бизнес-логика и REST API;
- `android/` — Android-приложение торгового представителя, будет добавлено следующим этапом;
- `admin-web/` — панель администратора и руководителя, будет добавлена следующим этапом;
- `docs/` — архитектура и правила учета.

## Запуск backend

Самый простой запуск PostgreSQL и API:

```bash
docker compose up
```

После запуска:

- API: `http://localhost:8000`;
- Swagger UI: `http://localhost:8000/docs`;
- проверка состояния: `http://localhost:8000/health`.

Для локального запуска без Docker backend по умолчанию может использовать SQLite:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

На Windows команда активации окружения: `.venv\\Scripts\\activate`.

## Реализованные API

Справочники:

- `GET/POST /api/v1/warehouses`;
- `GET/POST /api/v1/representatives`;
- `GET/POST /api/v1/products`.

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

## Принцип учета

Остатки не редактируются напрямую. Каждая операция создает документ и товарные проводки. История движения сохраняется, а текущий остаток вычисляется как сумма проводок.

Продажа увеличивает задолженность представителя перед компанией, а сдача денег уменьшает ее. Подробности описаны в `docs/domain-model.md`.

## Следующий этап

- Alembic-миграции;
- аутентификация JWT и разграничение ролей;
- конкурентно-безопасное списание остатков;
- WebSocket-обновления в реальном времени;
- Android-клиент;
- веб-панель администратора и руководителя;
- контур обмена с 1С.
