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
  --output /tmp/load-test-dry-run.json
```

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
  --min-success-rate 100 \
  --max-p95-ms 500 \
  --min-throughput-rps 10 \
  --output /tmp/load-test-execute.json \
  --execute
```

Перед стартом скрипт проверяет, что подтвержденного остатка хватит на весь заявленный тест. Вне localhost реальный запуск разрешен только через HTTPS.

Каждая продажа получает уникальный `operation_key`. После успешного прогона первая операция отправляется повторно с тем же ключом; document ID обязан совпасть, что дополнительно проверяет идемпотентность под реальным HTTP-контуром.

## Acceptance-пороги

`--min-success-rate` по умолчанию равен `100`, поэтому любой неуспешный запрос делает execute-прогон красным. `--max-p95-ms=0` и `--min-throughput-rps=0` означают, что соответствующий performance-порог пока не применяется. После согласования staging-инфраструктуры задайте реальные значения явно.

Execute-прогон также считается неуспешным, если не удалось подтвердить идемпотентный повтор первого успешного запроса. Примененные пороги и причины их нарушения сохраняются в JSON (`threshold_*`, `thresholds_passed`, `threshold_violations`).

## Результат

Скрипт печатает и при `--output` сохраняет в JSON:

- количество успешных/ошибочных запросов и success rate;
- общее время и throughput;
- min / p50 / p95 / max latency;
- результат идемпотентного повтора;
- примененные acceptance-пороги и причины нарушения;
- первые 10 ошибок.

Workflow `Staging-приемка` сохраняет dry-run и execute JSON в artifact `staging-load-test-results`. Для production-приемки укажите согласованные p95/throughput thresholds во входных параметрах workflow и приложите artifact к release checklist.
