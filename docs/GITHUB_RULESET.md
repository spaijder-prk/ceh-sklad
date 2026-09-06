# Защита ветки main

Репозиторий хранит декларативный ruleset в `.github/rulesets/main.json`.

Ruleset запрещает удаление и force-push основной ветки, требует внесения изменений через pull request, требует закрытия review threads и не разрешает merge, пока не успешны оба обязательных check:

- `Итоговая проверка проекта`;
- `Проверить production и Android release-контракты`.

## Первичное применение

GitHub Actions `GITHUB_TOKEN` не получает Repository administration write. Поэтому для однократного применения создайте fine-grained token с доступом **Administration: Read and write** только к репозиторию `ceh-sklad` и сохраните его как repository secret `CEH_GITHUB_ADMIN_TOKEN`.

После этого вручную запустите workflow **«Применить защиту main»**. Workflow вызывает `scripts/apply_github_ruleset.py`; скрипт идемпотентен: создает ruleset, если его еще нет, либо обновляет существующий ruleset `Защита main`.

После POST/PUT скрипт повторно читает сохранённый ruleset из GitHub API и fail-closed проверяет, что фактическая конфигурация совпадает с `.github/rulesets/main.json` по критичным параметрам: имя/target/enforcement, отсутствие bypass actors, default branch condition, набор правил, параметры pull request и оба обязательных status check.

После успешного применения удалите `CEH_GITHUB_ADMIN_TOKEN`, если автоматическое изменение ruleset больше не требуется. Для последующих изменений можно временно вернуть отдельный admin token и снова запустить workflow.

## Read-only проверка

Проверить уже применённый ruleset без POST/PUT можно командой:

```bash
python scripts/apply_github_ruleset.py --check-only
```

Для публичного репозитория проверка может выполняться без admin token. Если GitHub API требует авторизацию для текущего режима доступа к репозиторию, передайте `GH_TOKEN` только с необходимым правом чтения. Значение token в консоль не выводится.

Команда завершается ошибкой, если `Защита main` отсутствует, имеет неактивное enforcement, содержит bypass actor, защищает не тот ref, потеряла запрет удаления/force-push/PR rule или не содержит точный набор обязательных checks.

После автоматической проверки всё равно откройте GitHub **Settings → Rules → Rulesets** и убедитесь, что `Защита main` имеет состояние **Active** и применяется к default branch.

## Обновление lock-файлов

Workflow `Обновление lock-файлов` больше не пишет напрямую в `main`. Если снимок зависимостей изменился, он создает ветку `automation/dependency-locks-<run-id>` и pull request, который проходит те же обязательные проверки перед merge.

## Проверка Gate 0

Gate 0 считается пройденным только когда одновременно:

1. `python scripts/apply_github_ruleset.py --check-only` завершается успешно;
2. в GitHub Settings ruleset имеет состояние **Active**;
3. оба обязательных checks реально существуют и зелёные на выбранном release commit;
4. изменения `main` идут через pull request, а force-push/удаление запрещены.
