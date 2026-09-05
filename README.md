# Цех — учет складских остатков

Система учета продукции на нескольких складах и у торговых представителей. Репозиторий содержит Android-приложение представителя, веб-панель администратора/руководителя и FastAPI backend с защищенным контуром интеграции с 1С.

## Реализовано

### Backend

- несколько складов, товары и торговые представители;
- розничная и оптовая цена товара;
- приход, выдача представителю, перемещение между складами и возврат;
- продажи, сдача денег и расчет задолженности;
- неизменяемые товарные и денежные проводки;
- текущие регистры остатков с транзакционной защитой от конкурентного списания;
- безопасное сторнирование документов и ошибочных платежей;
- аудит создания и сторно: пользователь и время операции;
- идемпотентность операций по `external_id`;
- JWT-аутентификация и роли `admin`, `manager`, `representative`;
- пользователи и привязка учетной записи к существующему представителю;
- управленческие отчеты;
- WebSocket-события по остаткам, задолженности и каталогу;
- отдельный одноразовый WebSocket-ticket для браузера;
- Redis Pub/Sub fan-out для real-time между несколькими экземплярами backend;
- Alembic-миграции, PostgreSQL/SQLite, pytest и Ruff;
- защищенный API интеграции с 1С;
- production Docker-контур с PostgreSQL, Redis, Nginx/TLS и Docker secrets;
- эксплуатационные скрипты резервного копирования и восстановления PostgreSQL.

### Android

- Kotlin + Jetpack Compose;
- вход представителя через JWT, токен защищен Android Keystore;
- складские остатки и две цены в реальном времени;
- собственные остатки и задолженность;
- продажа по розничной или оптовой цене;
- возврат товара на выбранный склад;
- собственная товарная и денежная история;
- отображение сторно;
- Room3-очередь продаж/возвратов при отсутствии сети;
- WorkManager для автоматической повторной отправки;
- детальный экран ожидающих и отклоненных операций;
- ручной повтор отклоненных операций;
- изоляция офлайн-очереди по торговому представителю;
- защита от повторного проведения через исходный `external_id`;
- WebSocket real-time;
- отдельная GitHub Actions сборка debug APK.

### Веб-панель

- React + TypeScript + Vite;
- доступ ролям администратора и руководителя;
- KPI, склады, товары, представители и задолженность;
- создание складов, товаров, представителей и пользователей;
- назначение/замена/снятие учетной записи представителя;
- изменение розничной и оптовой цены;
- приход, выдача, перемещение и прием денег;
- журнал товарных документов и сторно;
- денежный журнал и сторно платежа;
- аудит авторов и отмен;
- отчеты по периоду и представителям;
- единый браузерный WebSocket с короткоживущим одноразовым ticket;
- real-time обновление обзора, журналов и отчетов;
- резервное REST-обновление раз в 60 секунд при отсутствии события;
- production-сборка в Nginx с HTTPS/reverse proxy;
- адаптивная верстка и отдельная CI-сборка.

### Интеграция с 1С

- отдельный заголовок `X-Integration-Key`;
- snapshot складов, товаров, представителей, остатков и долгов;
- товарный и денежный журналы;
- курсорная инкрементальная выгрузка без повторного полного чтения;
- сторнированный старый документ снова появляется в потоке изменений;
- импорт прихода, выдачи, перемещения, возврата, продажи и платежа;
- обязательный `external_id` и защита от повторного проведения;
- постоянный реестр соответствий UUID backend ↔ ссылка 1С для складов, товаров и представителей;
- получение всего реестра соответствий и разрешение ссылки 1С в UUID backend;
- соответствия включаются в полный snapshot.

Подробный контракт: `docs/1c-integration.md`.

## Структура

- `backend/` — FastAPI, SQLAlchemy, Alembic и бизнес-логика;
- `android/` — Android-приложение торгового представителя;
- `admin-web/` — веб-панель администратора и руководителя;
- `ops/` — эксплуатационные скрипты;
- `docs/` — архитектура, правила учета, production и интеграция.

## Быстрый запуск backend

```bash
docker compose up
```

Backend выполняет `alembic upgrade head` перед запуском API.

После запуска:

- API: `http://localhost:8000`;
- Swagger UI: `http://localhost:8000/docs`;
- healthcheck: `http://localhost:8000/health`.

Для первого администратора в новой базе один раз вызовите:

```http
POST /api/v1/auth/bootstrap
Content-Type: application/json

{
  "email": "admin@example.local",
  "password": "replace-with-strong-password",
  "full_name": "Администратор"
}
```

Далее токен выдается `POST /api/v1/auth/token`; в поле `username` OAuth2-формы передается email.

## Роли

- `admin` — справочники, пользователи, цены, учетные операции и сторно;
- `manager` — просмотр складов, товаров, остатков, задолженности, журналов и отчетов;
- `representative` — просмотр складских цен/остатков, собственных остатков, задолженности и истории, регистрация своих продаж и возвратов.

Сдача денег регистрируется администратором или доверенным контуром 1С. Представитель не может самостоятельно уменьшить собственную задолженность.

## Основные API

### Справочники

- `GET/POST /api/v1/warehouses`;
- `GET/POST /api/v1/representatives`;
- `PATCH /api/v1/representatives/{id}`;
- `GET/POST /api/v1/products`;
- `PATCH /api/v1/products/{id}`;
- `GET/POST /api/v1/users`.

### Остатки и деньги

- `GET /api/v1/balances/warehouses`;
- `GET /api/v1/balances/representatives`;
- `GET /api/v1/representatives/{id}/debt`;
- `GET /api/v1/money-postings`;
- `POST /api/v1/money-postings/{id}/reverse`.

### Операции

- `POST /api/v1/operations/receipt`;
- `POST /api/v1/operations/issue-to-representative`;
- `POST /api/v1/operations/warehouse-transfer`;
- `POST /api/v1/operations/representative-return`;
- `POST /api/v1/operations/sale`;
- `POST /api/v1/operations/payment`.

### История и отчеты

- `GET /api/v1/documents`;
- `POST /api/v1/documents/{id}/cancel`;
- `GET /api/v1/my/documents`;
- `GET /api/v1/my/money-postings`;
- `GET /api/v1/reports/summary`;
- `GET /api/v1/reports/representatives`.

### Интеграция 1С

- `GET /api/v1/integration/1c/snapshot`;
- `GET /api/v1/integration/1c/documents/changes`;
- `GET /api/v1/integration/1c/money-postings/changes`;
- `GET /api/v1/integration/1c/entity-links`;
- `PUT /api/v1/integration/1c/entity-links`;
- `GET /api/v1/integration/1c/entity-links/resolve`;
- `POST /api/v1/integration/1c/operations/...`.

## Real-time

Android подключается к `/api/v1/ws/updates` и передает `Authorization: Bearer <access-token>`.

Браузер сначала получает короткоживущий одноразовый ticket через `POST /api/v1/auth/ws-ticket`, затем подключается к `/api/v1/ws/browser-updates?ticket=<ticket>`. Основной JWT не попадает в URL WebSocket.

При заданном `CEH_REDIS_URL` backend публикует события через общий Redis-канал, поэтому WebSocket-клиенты разных экземпляров backend получают одинаковые изменения. Без Redis сохраняется локальный in-memory режим для разработки.

## Production

Production-контур включает PostgreSQL, Redis, backend и Nginx/TLS. Секреты БД, JWT, Redis, интеграции 1С и TLS-ключ не хранятся в Git и подключаются через Docker secrets.

Инструкция: `docs/production.md`.

GitHub Actions отдельно проверяет production Compose и реально собирает backend/web Docker-образы.

## Резервные копии

Создать проверенную custom-format копию PostgreSQL:

```bash
ops/backup-postgres.sh
```

Восстановление требует явного подтверждения:

```bash
CEH_CONFIRM_RESTORE=YES ops/restore-postgres.sh ./backups/<файл>.dump
```

Копия проверяется через `pg_restore --list` и сопровождается SHA-256. При неудачном restore backend/web остаются остановленными.

Подробная процедура: `docs/backups.md`.

## Учет и сторнирование

Все товарные движения записываются в `stock_postings`. Текущие остатки дополнительно поддерживаются в отдельных таблицах и блокируются в транзакции при списании.

Сторно не удаляет исходную историю. Документ получает `cancelled`, текущие остатки получают обратное движение, а денежное влияние компенсируется новой проводкой. Перед сторно проверяется, что обратное движение не создаст отрицательный остаток. Повторное сторно идемпотентно.

## Офлайн Android

При временной сетевой ошибке продажа или возврат сохраняется в Room3. WorkManager повторяет отправку с тем же `external_id`. Локальный клиент не меняет подтвержденные серверные остатки до успешного ответа backend. Постоянно отклоненные операции переходят в состояние проверки и могут быть повторены вручную.

## Локальный запуск без Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

На Windows: `.venv\\Scripts\\activate`.

## Веб-панель

```bash
cd admin-web
npm install
npm run dev
```

По умолчанию Vite доступен на `http://localhost:5173` и проксирует `/api` на локальный FastAPI.

## Android

Откройте каталог `android/` в Android Studio. Debug-клиент по умолчанию обращается к backend эмулятора через `http://10.0.2.2:8000/`.

## Следующий этап

- подготовка подписанной Android release-сборки без хранения ключей подписи в репозитории;
- эксплуатационный мониторинг/метрики и централизованные логи;
- автоматизированная проверка восстановления production-бэкапа на изолированной БД;
- нагрузочные тесты конкурентных складских операций и WebSocket fan-out.
