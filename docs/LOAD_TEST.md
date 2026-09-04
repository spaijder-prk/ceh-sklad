# Нагрузочный тест продаж

`scripts/load_test.py` предназначен только для отдельного staging/приемочного окружения. Он создает реальные документы продаж и увеличивает задолженность торгового представителя.

## Подготовка

Установите dev-зависимости backend:

```bash
cd backend
pip install -e '.[dev]'
```

Подготовьте отдельного пользователя `representative`, его виртуальный склад и товар с заведомо достаточным остатком.

Пароль передается только через окружение, чтобы не попадать в shell history:

```bash
export CEH_LOAD_PASSWORD='пароль-staging-представителя'
```

## Dry-run

Без `--execute` скрипт только входит в систему, проверяет роль, привязанный виртуальный склад и остаток. Продажи не создаются:

```bash
python ../scripts/load_test.py \
  --base-url https://staging-sklad.example.ru \
  --login load-representative \
  --location-id 11111111-1111-1111-1111-111111111111 \
  --product-id 22222222-2222-2222-2222-222222222222 \
  --requests 100 \
  --concurrency 20 \
  --output /tmp/ceh-load-dry-run.json
```

Dry-run JSON намеренно не содержит выдуманных latency/throughput: соответствующие поля равны `null`.

## Реальный тест

Для фактической отправки требуется одновременно `--execute` и явное подтверждение:

```bash
export CEH_LOAD_TEST_CONFIRM=I_UNDERSTAND_THIS_CREATES_REAL_SALES
python ../scripts/load_test.py \
  --base-url https://staging-sklad.example.ru \
  --login load-representative \
  --location-id 11111111-1111-1111-1111-111111111111 \
  --product-id 22222222-2222-2222-2222-222222222222 \
  --requests 100 \
  --concurrency 20 \
  --quantity 1 \
  --output /tmp/ceh-load-execute.json \
  --execute
```

Перед стартом скрипт проверяет, что подтвержденного остатка хватит на весь заявленный тест. Вне localhost реальный запуск разрешен только через HTTPS.

Каждая продажа получает уникальный `operation_key`. После успешного прогона первая операция отправляется повторно с тем же ключом; document ID обязан совпасть. Поле `idempotency_verified=true` в JSON означает, что этот реальный повтор успешно подтвержден.

## Машинный результат

С `--output` сохраняется JSON с:

- режимом `dry-run|execute`, run id и входными параметрами;
- количеством success/failure и `success_rate` в процентах;
- общим временем и `throughput_rps`;
- min / p50 / p95 / max latency в миллисекундах;
- результатом идемпотентного повтора;
- первыми 10 ошибками без токена/пароля.

Консольный вывод остается для оператора, но production-приемка должна ссылаться именно на JSON artifact из workflow `Staging-приемка`.

## Критерии приемки

Пороговые значения p95/throughput/success rate задаются исходя из реального числа представителей и инфраструктуры до финального прогона. Их нельзя подгонять после получения результата.

После фактического execute-прогона зафиксируйте в release record:

- `success_rate`;
- `throughput_rps`;
- `latency_p95_ms`;
- `idempotency_verified`;
- SHA release commit и ссылку на `staging-load-test-results` artifact.
