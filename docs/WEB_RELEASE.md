# Production-сборка web-панели

Web-панель использует Vite-переменную `VITE_API_BASE_URL`. Development по умолчанию работает с `http://localhost:8000/api/v1`, но production-сборка без явно заданного URL завершается ошибкой.

## Сборка

```bash
cd admin-web
npm install
VITE_API_BASE_URL=https://sklad.example.ru/api/v1 npm run build
```

Для production разрешается только HTTPS URL. WebSocket-адрес вычисляется из того же значения автоматически (`https://` → `wss://`).

CI дополнительно проверяет, что строка `localhost:8000` отсутствует в готовом каталоге `dist`.

## Backend

На backend задайте соответствующий HTTPS origin панели:

```env
ENVIRONMENT=production
CORS_ORIGINS=["https://sklad.example.ru"]
```

Сам FastAPI рекомендуется публиковать через TLS reverse proxy. Пользовательские JWT и ключ `X-1C-Key` не должны передаваться по незашифрованному HTTP.
