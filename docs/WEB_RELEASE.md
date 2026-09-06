# Production-сборка web-панели

Web-панель использует Vite-переменную `VITE_API_BASE_URL`. Development по умолчанию работает с `http://localhost:8000/api/v1`, но production-сборка без явно заданного URL завершается ошибкой.

## Сборка

```bash
cd admin-web
npm ci
VITE_API_BASE_URL=https://<PUBLIC_IP>:<HTTPS_PORT>/api/v1 npm run build
```

Для production разрешается только HTTPS URL. В штатном Docker deployment значение формируется из `${CEH_PUBLIC_ORIGIN}/api/v1`, поэтому web, backend CORS, Caddy и Android используют один и тот же `https://IP:PORT` origin.

CI дополнительно проверяет, что строка `localhost:8000` отсутствует в готовом `dist`.

## Backend

Backend должен разрешать только фактический HTTPS origin панели:

```env
ENVIRONMENT=production
CORS_ORIGINS=["https://<PUBLIC_IP>:<HTTPS_PORT>"]
```

Production Compose задаёт это автоматически через `CEH_PUBLIC_ORIGIN`. FastAPI напрямую наружу не публикуется; трафик идёт через Caddy. Пользовательские JWT и ключ `X-1C-Key` нельзя передавать по незашифрованному HTTP.
