# Защита ветки main

Репозиторий хранит декларативный ruleset в `.github/rulesets/main.json`.

Ruleset запрещает удаление и force-push основной ветки, требует внесения изменений через pull request, требует закрытия review threads и не разрешает merge, пока не успешны оба обязательных check:

- `Итоговая проверка проекта`;
- `Проверить production и Android release-контракты`.

## Первичное применение

GitHub Actions `GITHUB_TOKEN` не получает Repository administration write. Поэтому для однократного применения создайте fine-grained token с доступом **Administration: Read and write** только к репозиторию `ceh-sklad` и сохраните его как repository secret `CEH_GITHUB_ADMIN_TOKEN`.

После этого вручную запустите workflow **«Применить защиту main»**. Workflow вызывает `scripts/apply_github_ruleset.py`; скрипт идемпотентен: создает ruleset, если его еще нет, либо обновляет существующий ruleset `Защита main`.

После успешного применения удалите `CEH_GITHUB_ADMIN_TOKEN`, если автоматическое изменение ruleset больше не требуется. Для последующих изменений можно временно вернуть отдельный admin token и снова запустить workflow.

## Обновление lock-файлов

Workflow `Обновление lock-файлов` больше не пишет напрямую в `main`. Если снимок зависимостей изменился, он создает ветку `automation/dependency-locks-<run-id>` и pull request, который проходит те же обязательные проверки перед merge.

## Проверка

Текущую конфигурацию можно посмотреть в GitHub: **Settings → Rules → Rulesets**. Ожидаемое имя — `Защита main`, состояние — Active, target — default branch.
